import asyncio
import json
import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import websockets

from .protocol import Message
from .state_machine import EscapeBotStateMachine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EscapeBot")

# Dynamické nalezení absolutní cesty do složky client/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_DIR = os.path.join(BASE_DIR, "client")

# Úložiště pro nezávislé relace hráčů (session_id -> state_machine)
active_sessions: dict[str, EscapeBotStateMachine] = {}

class ClientHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=CLIENT_DIR, **kwargs)
        
    def log_message(self, format, *args):
        # Potlačení logování každého requestu na statické soubory pro čistší konzoli
        pass

def start_http_server():
    port = 8080
    httpd = ThreadingHTTPServer(("", port), ClientHTTPRequestHandler)
    logger.info(f"Webový klient interkomu je dostupný na: http://localhost:{port}")
    httpd.serve_forever()

async def handle_client(websocket):
    logger.info("Nový klient připojen, čekám na relaci...")
    session_id = None
    state_machine = None

    try:
        async for message_str in websocket:
            try:
                data = json.loads(message_str)
                msg = Message.from_json(data)
                
                # První zpráva musí být client.hello pro ustavení relace
                if msg.type == "client.hello":
                    session_id = msg.payload.get("session_id", "default_session")
                    if session_id not in active_sessions:
                        logger.info(f"Vytvářím novou herní relaci pro: {session_id}")
                        active_sessions[session_id] = EscapeBotStateMachine()
                    else:
                        logger.info(f"Obnovuji existující relaci pro: {session_id}")
                        
                    state_machine = active_sessions[session_id]

                if state_machine:
                    responses = state_machine.handle(msg)
                    for response in responses:
                        await websocket.send(json.dumps(response.to_json()))
                else:
                    logger.warning("Přijata zpráva před inicializací relace (client.hello chybí).")

            except Exception as e:
                logger.error(f"Chyba při zpracování zprávy: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        logger.info(f"Klient odpojen (Relace: {session_id}).")

async def main():
    # 1. Spuštění HTTP serveru (klienta) ve vedlejším vlákně
    threading.Thread(target=start_http_server, daemon=True).start()

    # 2. Inicializace WebSocket serveru s podporou relací
    logger.info("Spouštím herní WebSocket server s podporou relací (port 8765)...")
    async with websockets.serve(handle_client, "0.0.0.0", 8765):
        await asyncio.Future()  # Běží donekonečna

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server byl ukončen.")