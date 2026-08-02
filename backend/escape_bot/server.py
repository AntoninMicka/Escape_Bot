import asyncio
import json
import logging
import os
import subprocess
import socket
import secrets
import threading
import uvicorn
from io import BytesIO
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .protocol import Message
from .state_machine import EscapeBotStateMachine
from .scenario import ScenarioLoader, build_demo_checkpoint_catalog, build_scenario_progress
from .ollama_adapter import OllamaAdapter
from .team_lobby import Lobby, LobbyRegistry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EscapeBot")

# Dynamické nalezení absolutní cesty do složky client/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_DIR = os.path.join(BASE_DIR, "client")
SESSIONS_FILE = os.path.join(BASE_DIR, "backend", "sessions.json")
LOBBIES_FILE = os.path.join(BASE_DIR, "backend", "lobbies.json")

# Úložiště pro nezávislé relace hráčů (session_id -> state_machine)
active_sessions: dict[str, EscapeBotStateMachine] = {}
lobby_registry = LobbyRegistry()
session_connections: dict[str, set[WebSocket]] = {}
connection_info: dict[WebSocket, dict[str, object]] = {}
waiting_players: dict[str, dict[str, object]] = {}
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

def save_lobbies():
    with open(LOBBIES_FILE, "w", encoding="utf-8") as file:
        json.dump(lobby_registry.snapshot(), file, indent=2, ensure_ascii=False)

def load_lobbies():
    if not os.path.exists(LOBBIES_FILE):
        return
    try:
        with open(LOBBIES_FILE, "r", encoding="utf-8") as file:
            lobby_registry.restore(json.load(file))
    except Exception as error:
        logger.error(f"Chyba při načítání týmových lobby: {error}")

scenario_path = os.path.join(BASE_DIR, "backend", "scenario.json")
scenario = ScenarioLoader.load(scenario_path)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_leaderboard()
    load_lobbies()
    # 1. Načtení uložených stavů her z předchozího běhu
    load_sessions(scenario)
    # 2. Kontrola AI modelů na pozadí 
    ai_checker = OllamaAdapter()
    asyncio.create_task(ai_checker.ensure_model())
    yield

# --- Inicializace FastAPI ---
app = FastAPI(title="Escape Bot", lifespan=lifespan)


def connected_client_ids(session_id: str) -> set[str]:
    return {
        str(connection_info[websocket].get("client_id", ""))
        for websocket in session_connections.get(session_id, set())
        if websocket in connection_info
    }


async def send_message(websocket: WebSocket, message: Message) -> None:
    await websocket.send_text(json.dumps(message.to_json()))


async def broadcast_session(session_id: str, messages: list[Message], exclude: WebSocket | None = None) -> None:
    for websocket in list(session_connections.get(session_id, set())):
        if websocket is exclude:
            continue
        for message in messages:
            try:
                await send_message(websocket, message)
            except Exception:
                pass


async def broadcast_lobby(lobby: Lobby) -> None:
    connected = connected_client_ids(lobby.session_id)
    for websocket in list(session_connections.get(lobby.session_id, set())):
        info = connection_info.get(websocket, {})
        payload = lobby.public(str(info.get("client_id", "")), connected)
        try:
            await send_message(websocket, Message("lobby.state", payload))
        except Exception:
            pass


def attach_to_lobby(websocket: WebSocket, lobby: Lobby, client_id: str, demo_client: bool) -> None:
    previous = connection_info.get(websocket, {}).get("session_id")
    if previous:
        session_connections.get(str(previous), set()).discard(websocket)
    connection_info[websocket] = {
        "session_id": lobby.session_id,
        "client_id": client_id,
        "demo": demo_client,
    }
    session_connections.setdefault(lobby.session_id, set()).add(websocket)


def ensure_state_machine(session_id: str) -> EscapeBotStateMachine:
    if session_id not in active_sessions:
        active_sessions[session_id] = EscapeBotStateMachine(scenario)
    return active_sessions[session_id]


def apply_lobby_score(lobby: Lobby, state_machine: EscapeBotStateMachine) -> list[Message]:
    delta = lobby.score_delta()
    if not delta:
        return []
    state_machine.state.score += delta
    return [
        Message("score.update", {
            "score": state_machine.state.score,
            "delta": delta,
            "bonus": max(0, delta),
            "penalty": max(0, -delta),
            "reason": "team_size",
            "players": lobby.max_players,
        }),
        state_machine._state_message(),
    ]


@app.get("/api/qr")
async def qr_code(data: str) -> Response:
    if not data or len(data) > 500:
        return Response(status_code=400)
    try:
        import qrcode
        image = qrcode.make(data)
        output = BytesIO()
        image.save(output, format="PNG")
        return Response(content=output.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})
    except ImportError:
        return Response(content="QR generator není nainstalován.", status_code=503, media_type="text/plain")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Nový klient připojen přes WebSockets, čekám na relaci...")
    session_id = None
    state_machine = None
    demo_client = False
    client_id = None
    
    if not hasattr(app.state, "active_websockets"):
        app.state.active_websockets = set()
    app.state.active_websockets.add(websocket)

    try:
        while True:
            message_str = await websocket.receive_text()
            try:
                data = json.loads(message_str)
                msg = Message.from_json(data)

                if msg.type in {"lobby.solo", "lobby.create", "lobby.join", "lobby.resume", "lobby.start", "lobby.identify", "lobby.add_player"}:
                    try:
                        requested_client_id = str(msg.payload.get("client_id", "")).strip()
                        if not requested_client_id:
                            raise ValueError("Chybí identifikátor zařízení.")
                        name = str(msg.payload.get("name", "")).strip()
                        requested_demo = DEMO_MODE_ENABLED and bool(msg.payload.get("demo_mode"))
                        if msg.type == "lobby.identify":
                            previous_code = str(connection_info.get(websocket, {}).get("player_code", ""))
                            if previous_code:
                                waiting_players.pop(previous_code, None)
                            player_code = secrets.token_hex(4).upper()
                            while player_code in waiting_players:
                                player_code = secrets.token_hex(4).upper()
                            waiting_players[player_code] = {
                                "websocket": websocket,
                                "client_id": requested_client_id,
                                "name": name,
                                "demo": requested_demo,
                            }
                            connection_info[websocket] = {"client_id": requested_client_id, "player_code": player_code, "demo": requested_demo}
                            await send_message(websocket, Message("lobby.player_identity", {"player_code": player_code}))
                            continue
                        if msg.type == "lobby.add_player":
                            info = connection_info.get(websocket, {})
                            lobby = lobby_registry.by_session.get(str(info.get("session_id", "")))
                            if lobby is None or requested_client_id != lobby.creator_id:
                                raise ValueError("Hráče může tímto způsobem přidat pouze zakladatel týmu.")
                            player_code = str(msg.payload.get("player_code", "")).strip().upper().removeprefix("ESCAPEBOT://PLAYER/")
                            waiting = waiting_players.pop(player_code, None)
                            if waiting is None:
                                raise ValueError("Hráčské ID není platné nebo už bylo použito.")
                            waiting_socket = waiting["websocket"]
                            waiting_client_id = str(waiting["client_id"])
                            lobby.add_player(waiting_client_id, str(waiting.get("name", "")))
                            attach_to_lobby(waiting_socket, lobby, waiting_client_id, bool(waiting.get("demo")))
                            session_id = lobby.session_id
                            client_id = requested_client_id
                            state_machine = ensure_state_machine(session_id)
                            save_lobbies()
                            await broadcast_lobby(lobby)
                            if lobby.started:
                                await send_message(waiting_socket, Message("chat.history", {"messages": state_machine.state.chat_history}))
                                await send_message(waiting_socket, state_machine._state_message())
                                if bool(waiting.get("demo")):
                                    await send_message(waiting_socket, Message("demo.catalog", {
                                        "enabled": True,
                                        "checkpoints": build_demo_checkpoint_catalog(scenario),
                                    }))
                                score_messages = apply_lobby_score(lobby, state_machine)
                                if score_messages:
                                    await broadcast_session(session_id, score_messages)
                            continue
                        if msg.type == "lobby.solo":
                            lobby = lobby_registry.create(requested_client_id, "solo", name)
                        elif msg.type == "lobby.create":
                            lobby = lobby_registry.create(requested_client_id, "team", name)
                        elif msg.type == "lobby.join":
                            lobby = lobby_registry.join(str(msg.payload.get("join_code", "")), requested_client_id, name)
                        elif msg.type == "lobby.resume":
                            lobby = lobby_registry.resume(str(msg.payload.get("session_id", "")), requested_client_id, name)
                        else:
                            info = connection_info.get(websocket, {})
                            lobby = lobby_registry.by_session.get(str(info.get("session_id", "")))
                            if lobby is None or requested_client_id != lobby.creator_id:
                                raise ValueError("Hru může spustit pouze zakladatel týmu.")
                            lobby.started = True

                        session_id = lobby.session_id
                        client_id = requested_client_id
                        demo_client = requested_demo
                        attach_to_lobby(websocket, lobby, client_id, demo_client)
                        state_machine = ensure_state_machine(session_id)
                        save_lobbies()
                        await broadcast_lobby(lobby)

                        if lobby.started:
                            score_messages = apply_lobby_score(lobby, state_machine)
                            if msg.type in {"lobby.solo", "lobby.start"}:
                                hello = Message("client.hello", {"session_id": session_id, "demo_mode": demo_client})
                                responses = await state_machine.handle(hello)
                                responses.extend(score_messages)
                                if demo_client:
                                    responses.append(Message("demo.catalog", {
                                        "enabled": True,
                                        "checkpoints": build_demo_checkpoint_catalog(scenario),
                                    }))
                                    responses.append(Message("scenario.progress", build_scenario_progress(scenario, state_machine.state.snapshot())))
                                await broadcast_session(session_id, responses)
                            else:
                                await send_message(websocket, Message("chat.history", {"messages": state_machine.state.chat_history}))
                                await send_message(websocket, state_machine._state_message())
                                if demo_client:
                                    await send_message(websocket, Message("demo.catalog", {
                                        "enabled": True,
                                        "checkpoints": build_demo_checkpoint_catalog(scenario),
                                    }))
                                if score_messages:
                                    await broadcast_session(session_id, score_messages)
                        continue
                    except ValueError as error:
                        await send_message(websocket, Message("lobby.error", {"message": str(error)}))
                        continue
                
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
                    demo_client = DEMO_MODE_ENABLED and bool(msg.payload.get("demo_mode"))
                    if session_id not in active_sessions:
                        logger.info(f"Vytvářím novou herní relaci pro: {session_id}")
                        active_sessions[session_id] = EscapeBotStateMachine(scenario)
                    else:
                        logger.info(f"Obnovuji existující relaci pro: {session_id}")
                        
                    state_machine = active_sessions[session_id]
                    client_id = str(msg.payload.get("client_id", "legacy-client"))
                    connection_info[websocket] = {"session_id": session_id, "client_id": client_id, "demo": demo_client}
                    session_connections.setdefault(session_id, set()).add(websocket)

                if state_machine:
                    if client_id:
                        msg.payload["_client_id"] = client_id
                    responses = await state_machine.handle(msg)
                    if msg.type == "client.hello" and bool(msg.payload.get("demo_mode")):
                        if demo_client:
                            checkpoints = build_demo_checkpoint_catalog(scenario)
                            responses.append(Message("demo.catalog", {"enabled": True, "checkpoints": checkpoints}))
                        else:
                            responses.append(Message("demo.catalog", {
                                "enabled": False,
                                "checkpoints": [],
                                "reason": "Backend nebyl spuštěn s parametrem --demo.",
                            }))
                    if demo_client:
                        responses.append(Message(
                            "scenario.progress",
                            build_scenario_progress(scenario, state_machine.state.snapshot()),
                        ))
                    if msg.type == "player.message" and session_id:
                        await broadcast_session(session_id, [Message("team.player_message", {
                            "client_id": client_id,
                            "channel": msg.payload.get("channel", "general"),
                            "text": msg.payload.get("text", ""),
                        })], exclude=websocket)
                    save_sessions()
                    if session_id:
                        await broadcast_session(session_id, responses)
                    else:
                        for response in responses:
                            await send_message(websocket, response)
                else:
                    logger.warning("Přijata zpráva před inicializací relace (client.hello chybí).")

            except Exception as e:
                logger.error(f"Chyba při zpracování zprávy: {e}")
    except WebSocketDisconnect:
        app.state.active_websockets.discard(websocket)
        info = connection_info.pop(websocket, {})
        player_code = str(info.get("player_code", ""))
        if player_code:
            waiting_players.pop(player_code, None)
        disconnected_session = str(info.get("session_id", ""))
        if disconnected_session:
            session_connections.get(disconnected_session, set()).discard(websocket)
            lobby = lobby_registry.by_session.get(disconnected_session)
            if lobby:
                await broadcast_lobby(lobby)
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
