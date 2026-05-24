from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .protocol import Message, reply


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

    def snapshot(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "unlocked_discoveries": sorted(self.unlocked_discoveries),
            "inventory": list(self.inventory),
            "flags": self.flags,
            "chat_history": self.chat_history,
        }


class EscapeBotStateMachine:
    def __init__(self) -> None:
        self.state = GameState()

    def handle(self, message: Message) -> list[Message]:
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
        responses = handler(message)

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

    def _handle_hello(self, message: Message) -> list[Message]:
        if self.state.phase == GamePhase.BOOT:
            self.state.phase = GamePhase.COMMS_OFFLINE
            return [
                reply(
                    "bot.message",
                    {
                        "text": "*ššš*... Tady Kapitánka. Slyšíme se? Interkom konečně naběhl. Potvrď příjem!",
                        "mood": "alert",
                        "channel": "captain",
                    },
                    message,
                ),
                self._state_message(),
            ]
        else:
            # Znovupřipojení během hry – pošleme historii a neresetujeme stav
            return [
                Message("chat.history", {"messages": self.state.chat_history}),
                reply(
                    "bot.message",
                    {
                        "text": "[Systém]: Spojení bylo úspěšně obnoveno. Relace je aktivní.",
                        "mood": "info",
                        "channel": "general",
                    },
                    message,
                ),
                self._state_message(),
            ]

    def _handle_player_message(self, message: Message) -> list[Message]:
        text = str(message.payload.get("text", "")).strip()
        if not text:
            return [reply("error", {"message": "Text message is empty."}, message)]

        if self.state.phase == GamePhase.COMMS_OFFLINE:
            self.state.phase = GamePhase.SEARCHING_LOST
            return [
                reply(
                    "bot.message",
                    {
                        "text": "Výborně, spojení funguje. Máme krizovou situaci. Naše kolegyně uvízla v jiné dimenzi. Potřebuji, abys rozluštil její dimenzionální frekvenci z materiálů v místnosti a zadal ji sem.",
                        "mood": "focused",
                        "channel": "captain",
                    },
                    message),
                self._state_message(),
            ]

        if self.state.phase == GamePhase.SEARCHING_LOST:
            # Jednoduchá demo validace fáze 2 - správná frekvence
            if "734" in text:
                self.state.phase = GamePhase.LOST_CONNECTED
                return [
                    reply("bot.message", {"text": "Frekvence 734 přijata! Přepojuji tě na ni... *píp*", "mood": "relieved", "channel": "captain"}, message),
                    reply("bot.message", {"text": "Haló? Kapitánko? Jsi tam? Tady je hrozná tma, nevím, co mám dělat! Můžeš mi pomoct se zorientovat v téhle budově?", "mood": "tense", "channel": "lost"}, message),
                    self._state_message(),
                ]
            else:
                return [
                    reply("bot.message", {"text": f"*šum* Frekvence '{text}' je hluchá. Zkus to znovu, musíme ji najít!", "mood": "tense", "channel": "captain"}, message),
                    self._state_message(),
                ]

        if self.state.phase == GamePhase.LOST_CONNECTED:
            self.state.phase = GamePhase.CONNECTION_LOST
            return [
                reply("bot.message", {"text": f"Snažím se postupovat podle tvých instrukcí '{text}', ale... *GLITCH* něco mě tu ruší... *šum*", "mood": "glitchy", "channel": "lost"}, message),
                Message("effect.trigger", {"effect": "glitch", "intensity": 0.8, "duration_ms": 2000}),
                reply("bot.message", {"text": "SYSTEM ERROR: Spojení ztraceno. Proveďte tvrdý restart (napište 'restart').", "mood": "error", "channel": "general"}, message),
                self._state_message(),
            ]

        if self.state.phase == GamePhase.CONNECTION_LOST:
            if "restart" in text.lower():
                self.state.phase = GamePhase.NAVIGATING
                return [
                    reply("bot.message", {"text": "Uf, jsem zpět! Bylo to těsné, dimenzionální bouře nás odpojila. Našla jsem nějaké mapy hotelu. Kam mám jít dál?", "mood": "alert", "channel": "lost"}, message),
                    self._state_message(),
                ]
            else:
                return [
                    reply("bot.message", {"text": "SYSTEM ERROR: Spojení nelze navázat. Zadejte 'restart'.", "mood": "error", "channel": "general"}, message),
                    self._state_message(),
                ]

        # Výchozí odpověď pro fázi NAVIGATING
        return [
            reply(
                "bot.message",
                {
                    "text": f"Slyším tě: '{text}'. Musíme najít ten portál ven.",
                    "mood": "alert",
                    "channel": "lost",
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
        return [
            reply(
                "bot.message",
                {
                    "text": f"Našla jsem podivný symbol: '{discovery_id}'. To nám asi pomůže se zámkem.",
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

        self.state.flags[f"verified.{discovery_id}"] = True
        return [
            reply("arg.result", {"verified": True, "discovery_id": discovery_id}, message),
            reply(
                "bot.message",
                {
                    "text": "Máš pravdu! Ten symbol vážně zapadl do panelu u dveří.",
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

    def _handle_room_unlock(self, message: Message) -> list[Message]:
        pin = str(message.payload.get("pin", "")).strip()
        
        # Pro ukázku odemkneme "Pokoj 104" pomocí PINu "104"
        if pin == "104":
            # TODO: Přidat flag do self.state.flags, že je místnost odemčena
            return [
                reply("room.unlock_result", {"success": True}, message),
                reply("bot.message", {
                    "text": "Přístupový panel 104 odemčen. Elektromagnetický zámek uvolněn.",
                    "mood": "success",
                    "channel": "general"
                }, message),
                reply("bot.message", {
                    "text": "Slyšela jsem cvaknutí! Ty dveře do pokoje 104 se právě otevřely. Jdu dovnitř...",
                    "mood": "relieved",
                    "channel": "lost"
                }, message),
                self._state_message(),
            ]
        else:
            return [
                reply("room.unlock_result", {"success": False}, message),
                reply("bot.message", {"text": f"Chybný PIN kód '{pin}'. Přístup odepřen.", "mood": "error", "channel": "general"}, message),
                self._state_message(),
            ]

    def _handle_unknown(self, message: Message) -> list[Message]:
        return [reply("error", {"message": f"Unsupported message type: {message.type}"}, message)]
