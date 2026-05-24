import asyncio
import json
import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .protocol import Message
from .state_machine import EscapeBotStateMachine
from .scenario import ScenarioLoader
from .ollama_adapter import OllamaAdapter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EscapeBot")

# Dynamické nalezení absolutní cesty do složky client/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_DIR = os.path.join(BASE_DIR, "client")
SESSIONS_FILE = os.path.join(BASE_DIR, "backend", "sessions.json")

# Úložiště pro nezávislé relace hráčů (session_id -> state_machine)
active_sessions: dict[str, EscapeBotStateMachine] = {}

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

    try:
        while True:
            message_str = await websocket.receive_text()
            try:
                data = json.loads(message_str)
                msg = Message.from_json(data)
                
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
                    for response in responses:
                        save_sessions()
                        await websocket.send_text(json.dumps(response.to_json()))
                else:
                    logger.warning("Přijata zpráva před inicializací relace (client.hello chybí).")

            except Exception as e:
                logger.error(f"Chyba při zpracování zprávy: {e}")
    except WebSocketDisconnect:
        logger.info(f"Klient odpojen (Relace: {session_id}).")

# Servírování statických souborů (klienta) napřímo pod stejným portem
app.mount("/", StaticFiles(directory=CLIENT_DIR, html=True), name="client")

def main():
    logger.info("Spouštím centrální uzel (HTTP i WS na stejném portu 8088)...")
    uvicorn.run("escape_bot.server:app", host="0.0.0.0", port=8088, log_level="info")

if __name__ == "__main__":
    main()