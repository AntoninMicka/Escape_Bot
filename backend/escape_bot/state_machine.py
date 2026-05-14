from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .protocol import Message, reply


class GamePhase(StrEnum):
    BOOT = "boot"
    INVESTIGATING = "investigating"
    PUZZLE_LOCKED = "puzzle_locked"
    PUZZLE_SOLVED = "puzzle_solved"
    FINALE = "finale"


@dataclass(slots=True)
class GameState:
    phase: GamePhase = GamePhase.BOOT
    unlocked_discoveries: set[str] = field(default_factory=set)
    inventory: list[str] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "unlocked_discoveries": sorted(self.unlocked_discoveries),
            "inventory": list(self.inventory),
            "flags": self.flags,
        }


class EscapeBotStateMachine:
    def __init__(self) -> None:
        self.state = GameState()

    def handle(self, message: Message) -> list[Message]:
        handlers = {
            "client.hello": self._handle_hello,
            "player.message": self._handle_player_message,
            "qr.detected": self._handle_qr_detected,
            "arg.verify": self._handle_arg_verify,
            "camera.frame": self._handle_camera_frame,
        }
        handler = handlers.get(message.type, self._handle_unknown)
        return handler(message)

    def _state_message(self) -> Message:
        return Message("game.state", self.state.snapshot())

    def _handle_hello(self, message: Message) -> list[Message]:
        self.state.phase = GamePhase.INVESTIGATING
        return [
            reply(
                "bot.message",
                {
                    "text": "Spojeni navazano. Zacni popisem prostoru nebo naskenuj prvni stopu.",
                    "mood": "calm",
                },
                message,
            ),
            self._state_message(),
        ]

    def _handle_player_message(self, message: Message) -> list[Message]:
        text = str(message.payload.get("text", "")).strip()
        if not text:
            return [reply("error", {"message": "Text message is empty."}, message)]

        return [
            reply(
                "bot.message",
                {
                    "text": "Zapsano. Jakmile pridas vizualni dukaz nebo QR stopu, muzu to overit.",
                    "mood": "focused",
                },
                message,
            )
        ]

    def _handle_qr_detected(self, message: Message) -> list[Message]:
        value = str(message.payload.get("value", "")).strip()
        discovery_id = value.removeprefix("escapebot://clue/")
        if not discovery_id or discovery_id == value:
            return [reply("error", {"message": "Unknown QR format."}, message)]

        self.state.unlocked_discoveries.add(discovery_id)
        self.state.phase = GamePhase.PUZZLE_LOCKED
        return [
            reply(
                "bot.message",
                {
                    "text": f"Stopa '{discovery_id}' je aktivni. Ted potrebujeme potvrdit jeji vyznam.",
                    "mood": "tense",
                },
                message,
            ),
            Message("effect.trigger", {"effect": "glitch", "intensity": 0.35, "duration_ms": 900}),
            self._state_message(),
        ]

    def _handle_arg_verify(self, message: Message) -> list[Message]:
        discovery_id = str(message.payload.get("discovery_id", "")).strip()
        if discovery_id not in self.state.unlocked_discoveries:
            return [reply("arg.result", {"verified": False, "reason": "Discovery is not unlocked."}, message)]

        self.state.phase = GamePhase.PUZZLE_SOLVED
        self.state.flags[f"verified.{discovery_id}"] = True
        return [
            reply("arg.result", {"verified": True, "discovery_id": discovery_id}, message),
            reply(
                "bot.message",
                {
                    "text": "Potvrzeno. Tohle neni nahoda, je to soucast zamku.",
                    "mood": "alert",
                },
                message,
            ),
            self._state_message(),
        ]

    def _handle_camera_frame(self, message: Message) -> list[Message]:
        return [
            reply(
                "bot.message",
                {
                    "text": "Snimek prijat. V dalsim kroku ho posleme do vizualni analyzy.",
                    "mood": "focused",
                },
                message,
            )
        ]

    def _handle_unknown(self, message: Message) -> list[Message]:
        return [reply("error", {"message": f"Unsupported message type: {message.type}"}, message)]

