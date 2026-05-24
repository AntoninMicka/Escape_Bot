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

async def handle_client(websocket, state_machine):
    logger.info("Nový hráč připojen k interkomu.")
    try:
        async for message_str in websocket:
            try:
                data = json.loads(message_str)
                msg = Message.from_json(data)
                responses = state_machine.handle(msg)
                for response in responses:
                    await websocket.send(json.dumps(response.to_json()))
            except Exception as e:
                logger.error(f"Chyba při zpracování zprávy: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        logger.info("Hráč odpojen.")

async def main():
    # 1. Spuštění HTTP serveru (klienta) ve vedlejším vlákně
    threading.Thread(target=start_http_server, daemon=True).start()

    # 2. Inicializace herní state machine a WebSocket serveru
    state_machine = EscapeBotStateMachine()
    logger.info("Spouštím herní WebSocket server (port 8765)...")
    async with websockets.serve(lambda ws: handle_client(ws, state_machine), "0.0.0.0", 8765):
        await asyncio.Future()  # Běží donekonečna

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server byl ukončen.")