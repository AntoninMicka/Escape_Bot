from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from .protocol import Message
from .state_machine import EscapeBotStateMachine


HOST = "127.0.0.1"
PORT = 8765


async def send_message(websocket: WebSocketServerProtocol, message: Message) -> None:
    await websocket.send(json.dumps(message.to_json(), ensure_ascii=True))


async def handle_client(websocket: WebSocketServerProtocol) -> None:
    machine = EscapeBotStateMachine()

    async for raw in websocket:
        try:
            data: Any = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Root message must be an object.")
            incoming = Message.from_json(data)
            responses = machine.handle(incoming)
        except Exception as exc:
            responses = [Message("error", {"message": str(exc)})]

        for response in responses:
            await send_message(websocket, response)


async def main() -> None:
    async with websockets.serve(handle_client, HOST, PORT):
        print(f"Escape Bot backend listening on ws://{HOST}:{PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

