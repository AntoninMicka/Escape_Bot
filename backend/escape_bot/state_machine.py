from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .protocol import Message, reply
from .scenario import Scenario
from .ollama_adapter import OllamaAdapter


class GamePhase(StrEnum):
    BOOT = "boot"
    COMMS_OFFLINE = "comms_offline"
    CAPTAIN_CONNECTED = "captain_connected"
    SEARCHING_LOST = "searching_lost"
    LOST_CONNECTED = "lost_connected"
    CONNECTION_LOST = "connection_lost"
    NAVIGATING = "navigating"
    PORTAL_OPEN = "portal_open"


@dataclass(slots=True)
class GameState:
    phase: GamePhase = GamePhase.BOOT
    unlocked_discoveries: set[str] = field(default_factory=set)
    inventory: list[str] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    chat_history: list[dict[str, str]] = field(default_factory=list)
    score: int = 1000
    hints_used: dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "unlocked_discoveries": sorted(self.unlocked_discoveries),
            "inventory": list(self.inventory),
            "flags": self.flags,
            "chat_history": self.chat_history,
            "score": self.score,
            "hints_used": self.hints_used,
        }

    @classmethod
    def restore(cls, data: dict[str, Any]) -> "GameState":
        state = cls()
        state.phase = GamePhase(data.get("phase", GamePhase.BOOT.value))
        state.unlocked_discoveries = set(data.get("unlocked_discoveries", []))
        state.inventory = list(data.get("inventory", []))
        state.flags = dict(data.get("flags", {}))
        state.chat_history = list(data.get("chat_history", []))
        state.score = int(data.get("score", 1000))
        state.hints_used = dict(data.get("hints_used", {}))
        return state


class EscapeBotStateMachine:
    def __init__(self, scenario: Scenario) -> None:
        self.state = GameState()
        self.scenario = scenario
        self.ai = OllamaAdapter(model="llama3") # Možno změnit model např. na llama3.1

    def restore_state(self, data: dict[str, Any]) -> None:
        self.state = GameState.restore(data)

    async def handle(self, message: Message) -> list[Message]:
        # Automatické uložení příchozí zprávy hráče do historie
        if message.type == "player.message":
            text = str(message.payload.get("text", "")).strip()
            channel = str(message.payload.get("channel", "general")).strip()
            if text:
                self.state.chat_history.append({"role": "player", "channel": channel, "text": text})

        handlers = {
            "client.hello": self._handle_hello,
            "player.message": self._handle_player_message,
            "qr.detected": self._handle_qr_detected,
            "arg.verify": self._handle_arg_verify,
            "camera.frame": self._handle_camera_frame,
            "room.unlock": self._handle_room_unlock,
        }
        handler = handlers.get(message.type, self._handle_unknown)
        responses = await handler(message)

        # Automatické uložení odpovědí bota do historie
        for resp in responses:
            if resp.type == "bot.message":
                self.state.chat_history.append({
                    "role": "bot",
                    "channel": resp.payload.get("channel", "general"),
                    "text": resp.payload.get("text", "")
                })

        return responses

    def _state_message(self) -> Message:
        return Message("game.state", self.state.snapshot())

    def _provide_hint(self, phase: str, message: Message) -> list[Message]:
        p_data = self.scenario.get_phase_data(phase)
        hints = p_data.get("hints", [])
        
        if not hints:
            return [reply("bot.message", {"text": "Systém: Pro tuto situaci nemám v databázi žádné další nápovědy.", "mood": "error", "channel": "general"}, message)]
            
        idx = self.state.hints_used.get(phase, 0)
        is_new_hint = False
        
        if idx >= len(hints):
            idx = len(hints) - 1 # Zopakuje poslední známou nápovědu bez stržení dalších bodů
        else:
            is_new_hint = True
            
        hint = hints[idx]
        responses = []
        
        if is_new_hint:
            self.state.score -= hint.get("penalty", 10)
            self.state.hints_used[phase] = idx + 1
            responses.append(reply("score.update", {"score": self.state.score, "penalty": hint.get("penalty", 10)}, message))
            
        responses.append(reply("bot.message", {"text": f"NÁPOVĚDA SYSTÉMU: {hint.get('text', '')}", "mood": "info", "channel": "general"}, message))
        responses.append(self._state_message())
        return responses

    async def _handle_hello(self, message: Message) -> list[Message]:
        if self.state.phase == GamePhase.BOOT:
            self.state.phase = GamePhase.COMMS_OFFLINE
            p_data = self.scenario.get_phase_data("comms_offline")
            return [
                reply("bot.message", p_data.get("enter_message", {}), message),
                self._state_message(),
            ]
        else:
            # Znovupřipojení během hry – pošleme historii a neresetujeme stav
            msg_reconnect = self.scenario.data.get("global_events", {}).get("reconnect", {})
            return [
                Message("chat.history", {"messages": self.state.chat_history}),
                reply("bot.message", msg_reconnect, message),
                self._state_message(),
            ]

    async def _handle_player_message(self, message: Message) -> list[Message]:
        text = str(message.payload.get("text", "")).strip()
        if not text:
            return [reply("error", {"message": "Text message is empty."}, message)]

        if self.state.phase == GamePhase.COMMS_OFFLINE:
            self.state.phase = GamePhase.SEARCHING_LOST
            p_data = self.scenario.get_phase_data("searching_lost")
            return [
                reply("bot.message", p_data.get("enter_message", {}), message),
                self._state_message(),
            ]

        if self.state.phase == GamePhase.SEARCHING_LOST:
            p_data = self.scenario.get_phase_data("searching_lost")
            if p_data.get("success_keyword", "734") in text:
                self.state.phase = GamePhase.LOST_CONNECTED
                responses = [reply("bot.message", m, message) for m in p_data.get("success_messages", [])]
                responses.append(self._state_message())
                return responses
            else:
                # Vyhodnocení, zda hráč neprosí o pomoc pomocí AI
                if await self.ai.is_hint_request(text):
                    return self._provide_hint("searching_lost", message)
                else:
                    fail_msg = p_data.get("fail_message", {}).copy()
                    fail_msg["text"] = fail_msg.get("text", "").replace("{text}", text)
                    return [reply("bot.message", fail_msg, message), self._state_message()]

        if self.state.phase == GamePhase.LOST_CONNECTED:
            self.state.phase = GamePhase.CONNECTION_LOST
            p_data = self.scenario.get_phase_data("lost_connected")
            glitch_msg = p_data.get("glitch_message", {}).copy()
            glitch_msg["text"] = glitch_msg.get("text", "").replace("{text}", text)
            return [
                reply("bot.message", glitch_msg, message),
                Message("effect.trigger", {"effect": "glitch", "intensity": 0.8, "duration_ms": 2000}),
                reply("bot.message", p_data.get("error_message", {}), message),
                self._state_message(),
            ]

        if self.state.phase == GamePhase.CONNECTION_LOST:
            p_data = self.scenario.get_phase_data("connection_lost")
            if p_data.get("success_keyword", "restart") in text.lower():
                self.state.phase = GamePhase.NAVIGATING
                return [
                    reply("bot.message", p_data.get("success_message", {}), message),
                    self._state_message(),
                ]
            else:
                if await self.ai.is_hint_request(text):
                    return self._provide_hint("connection_lost", message)
                else:
                    return [
                        reply("bot.message", p_data.get("fail_message", {}), message),
                        self._state_message(),
                    ]

        # Výchozí odpověď pro fázi NAVIGATING
        p_data = self.scenario.get_phase_data("navigating")
        
        ai_prompt = p_data.get("ai_system_prompt")
        if ai_prompt:
            knowledge_base = self.scenario.data.get("knowledge_base", "")
            if knowledge_base:
                ai_prompt += f"\n\nDŮLEŽITÉ INFORMACE O SVĚTĚ A PŘÍBĚHU (ZNALOSTNÍ BÁZE):\n{knowledge_base}"
                
            # Zkusíme vygenerovat odpověď pomocí AI
            ai_response = await self.ai.generate_response(ai_prompt, self.state.chat_history)
            if ai_response:
                return [reply("bot.message", {"text": ai_response, "mood": "alert", "channel": "lost"}, message)]
                
        def_msg = p_data.get("default_message", {}).copy()
        def_msg["text"] = def_msg.get("text", "").replace("{text}", text)
        return [reply("bot.message", def_msg, message)]

    async def _handle_qr_detected(self, message: Message) -> list[Message]:
        value = str(message.payload.get("value", "")).strip()
        discovery_id = value.removeprefix("escapebot://clue/")
        if not discovery_id or discovery_id == value:
            return [reply("error", {"message": "Unknown QR format."}, message)]

        self.state.unlocked_discoveries.add(discovery_id)
        
        msg_template = self.scenario.data.get("global_events", {}).get("qr_detected", {}).copy()
        msg_template["text"] = msg_template.get("text", "").replace("{discovery_id}", discovery_id)
        
        return [
            reply("bot.message", msg_template, message),
            Message("effect.trigger", {"effect": "glitch", "intensity": 0.35, "duration_ms": 900}),
            self._state_message(),
        ]

    async def _handle_arg_verify(self, message: Message) -> list[Message]:
        discovery_id = str(message.payload.get("discovery_id", "")).strip()
        if discovery_id not in self.state.unlocked_discoveries:
            return [reply("arg.result", {"verified": False, "reason": "Discovery is not unlocked."}, message)]

        self.state.flags[f"verified.{discovery_id}"] = True
        
        msg_template = self.scenario.data.get("global_events", {}).get("arg_verified", {}).copy()
        msg_template["text"] = msg_template.get("text", "").replace("{discovery_id}", discovery_id)
        
        return [
            reply("arg.result", {"verified": True, "discovery_id": discovery_id}, message),
            reply("bot.message", msg_template, message),
            self._state_message(),
        ]

    async def _handle_camera_frame(self, message: Message) -> list[Message]:
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

    async def _handle_room_unlock(self, message: Message) -> list[Message]:
        pin = str(message.payload.get("pin", "")).strip()
        
        # Vyhledání PINu ve scénáři
        rooms_data = self.scenario.data.get("rooms", {})
        for room_id, r_data in rooms_data.items():
            if r_data.get("pin") == pin:
                self.state.flags[f"room_{room_id}_unlocked"] = True
                responses = [reply("room.unlock_result", {"success": True}, message)]
                for msg in r_data.get("success_messages", []):
                    responses.append(reply("bot.message", msg, message))
                responses.append(self._state_message())
                return responses
                
        # Pokud PIN není nalezen
        fail_msg = self.scenario.data.get("room_defaults", {}).get("fail_message", {}).copy()
        fail_msg["text"] = fail_msg.get("text", "").replace("{pin}", pin)
        
        return [
            reply("room.unlock_result", {"success": False}, message),
            reply("bot.message", fail_msg, message),
            self._state_message(),
        ]

    async def _handle_unknown(self, message: Message) -> list[Message]:
        return [reply("error", {"message": f"Unsupported message type: {message.type}"}, message)]
