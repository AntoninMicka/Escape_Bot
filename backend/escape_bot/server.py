import asyncio
import json
import logging
import os
import subprocess
import socket
import threading
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .protocol import Message
from .state_machine import EscapeBotStateMachine
from .scenario import ScenarioLoader, build_demo_checkpoint_catalog
from .ollama_adapter import OllamaAdapter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EscapeBot")

# Dynamické nalezení absolutní cesty do složky client/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_DIR = os.path.join(BASE_DIR, "client")
SESSIONS_FILE = os.path.join(BASE_DIR, "backend", "sessions.json")

# Úložiště pro nezávislé relace hráčů (session_id -> state_machine)
active_sessions: dict[str, EscapeBotStateMachine] = {}
DEMO_MODE_ENABLED = os.getenv("ESCAPEBOT_DEMO_MODE", "").lower() in {"1", "true", "yes", "on"}

LEADERBOARD_FILE = os.path.join(BASE_DIR, "backend", "leaderboard.json")
global_leaderboard = []

def save_leaderboard():
    with open(LEADERBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(global_leaderboard, f, indent=2, ensure_ascii=False)

def load_leaderboard():
    global global_leaderboard
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
                global_leaderboard = json.load(f)
            logger.info(f"Úspěšně načtena Síň slávy ({len(global_leaderboard)} záznamů).")
        except Exception as e:
            logger.error(f"Chyba při načítání Síně slávy: {e}")

def save_sessions():
    data = {sid: sm.state.snapshot() for sid, sm in active_sessions.items()}
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_sessions(scenario):
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sid, s_data in data.items():
                sm = EscapeBotStateMachine(scenario)
                sm.restore_state(s_data)
                active_sessions[sid] = sm
            logger.info(f"Úspěšně obnoveno {len(active_sessions)} uložených relací ze souboru sessions.json.")
        except Exception as e:
            logger.error(f"Chyba při načítání souboru relací: {e}")

scenario_path = os.path.join(BASE_DIR, "backend", "scenario.json")
scenario = ScenarioLoader.load(scenario_path)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_leaderboard()
    # 1. Načtení uložených stavů her z předchozího běhu
    load_sessions(scenario)
    # 2. Kontrola AI modelů na pozadí 
    ai_checker = OllamaAdapter()
    asyncio.create_task(ai_checker.ensure_model())
    yield

# --- Inicializace FastAPI ---
app = FastAPI(title="Escape Bot", lifespan=lifespan)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Nový klient připojen přes WebSockets, čekám na relaci...")
    session_id = None
    state_machine = None
    
    if not hasattr(app.state, "active_websockets"):
        app.state.active_websockets = set()
    app.state.active_websockets.add(websocket)

    try:
        while True:
            message_str = await websocket.receive_text()
            try:
                data = json.loads(message_str)
                msg = Message.from_json(data)
                
                # Zpracování požadavků na Síň slávy (mimo state machine)
                if msg.type == "leaderboard.get":
                    await websocket.send_text(json.dumps(Message("leaderboard.update", {"entries": global_leaderboard}).to_json()))
                    continue
                    
                if msg.type == "leaderboard.save":
                    name = str(msg.payload.get("name", "")).strip()
                    score = int(msg.payload.get("score", 0))
                    if name and not any(e["name"] == name and e["score"] == score for e in global_leaderboard):
                        global_leaderboard.append({"name": name, "score": score})
                        save_leaderboard()
                    
                    update_msg = json.dumps(Message("leaderboard.update", {"entries": global_leaderboard}).to_json())
                    for ws in list(app.state.active_websockets):
                        try:
                            await ws.send_text(update_msg)
                        except Exception:
                            pass
                    continue

                if msg.type == "client.hello":
                    session_id = msg.payload.get("session_id", "default_session")
                    if session_id not in active_sessions:
                        logger.info(f"Vytvářím novou herní relaci pro: {session_id}")
                        active_sessions[session_id] = EscapeBotStateMachine(scenario)
                    else:
                        logger.info(f"Obnovuji existující relaci pro: {session_id}")
                        
                    state_machine = active_sessions[session_id]

                if state_machine:
                    responses = await state_machine.handle(msg)
                    if msg.type == "client.hello" and bool(msg.payload.get("demo_mode")):
                        if DEMO_MODE_ENABLED:
                            checkpoints = build_demo_checkpoint_catalog(scenario)
                            responses.append(Message("demo.catalog", {"enabled": True, "checkpoints": checkpoints}))
                        else:
                            responses.append(Message("demo.catalog", {
                                "enabled": False,
                                "checkpoints": [],
                                "reason": "Backend nebyl spuštěn s parametrem --demo.",
                            }))
                    for response in responses:
                        save_sessions()
                        await websocket.send_text(json.dumps(response.to_json()))
                else:
                    logger.warning("Přijata zpráva před inicializací relace (client.hello chybí).")

            except Exception as e:
                logger.error(f"Chyba při zpracování zprávy: {e}")
    except WebSocketDisconnect:
        app.state.active_websockets.discard(websocket)
        logger.info(f"Klient odpojen (Relace: {session_id}).")

# Servírování statických souborů (klienta) napřímo pod stejným portem
app.mount("/", StaticFiles(directory=CLIENT_DIR, html=True), name="client")

def generate_ssl_certs(cert_path, key_path):
    try:
        logger.info("OpenSSL certifikáty nenalezeny. Pokouším se je automaticky vygenerovat...")
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-out", cert_path, "-keyout", key_path, "-days", "365",
            "-subj", "/CN=localhost"
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Certifikáty úspěšně vygenerovány.")
        return True
    except Exception as e:
        logger.warning(f"Automatické generování certifikátů selhalo (je nainstalován OpenSSL?): {e}")
        return False

def start_http_redirect_server(http_port=8087, https_port=8088):
    def _run():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', http_port))
                s.listen(5)
                logger.info(f"Spuštěn pomocný HTTP server (port {http_port}) pro přesměrování na HTTPS (port {https_port}).")
                while True:
                    conn, addr = s.accept()
                    try:
                        data = conn.recv(1024).decode('utf-8', errors='ignore')
                        if not data:
                            continue
                        host = "localhost"
                        for line in data.split('\r\n'):
                            if line.lower().startswith("host:"):
                                host = line.split(":", 1)[1].strip().split(":")[0]
                                break
                        redirect_url = f"https://{host}:{https_port}/"
                        response = f"HTTP/1.1 301 Moved Permanently\r\nLocation: {redirect_url}\r\nConnection: close\r\n\r\n"
                        conn.sendall(response.encode('utf-8'))
                    except Exception:
                        pass
                    finally:
                        conn.close()
        except Exception as e:
            logger.error(f"Nelze spustit HTTP redirect server: {e}")
    threading.Thread(target=_run, daemon=True).start()

def main():
    ssl_cert_path = os.path.join(BASE_DIR, "backend", "cert.pem")
    ssl_key_path = os.path.join(BASE_DIR, "backend", "key.pem")
    
    if not (os.path.exists(ssl_cert_path) and os.path.exists(ssl_key_path)):
        generate_ssl_certs(ssl_cert_path, ssl_key_path)

    if os.path.exists(ssl_cert_path) and os.path.exists(ssl_key_path):
        logger.info("Nalezeny SSL certifikáty. Spouštím zabezpečený centrální uzel (HTTPS/WSS na portu 8088)...")
        start_http_redirect_server(http_port=8087, https_port=8088)
        uvicorn.run("escape_bot.server:app", host="0.0.0.0", port=8088, log_level="info", ssl_keyfile=ssl_key_path, ssl_certfile=ssl_cert_path)
    else:
        logger.info("Bez SSL certifikátů. Spouštím nezabezpečený centrální uzel (HTTP/WS na portu 8088)...")
        uvicorn.run("escape_bot.server:app", host="0.0.0.0", port=8088, log_level="info")

if __name__ == "__main__":
    main()
