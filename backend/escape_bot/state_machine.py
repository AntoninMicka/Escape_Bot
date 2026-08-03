from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .protocol import Message, reply
from .scenario import Scenario
from .ollama_adapter import OllamaAdapter
from .line_game import new_game, public_game, reset_game, swap
from .sokoban import (
    execute as execute_sokoban,
    new_game as new_sokoban,
    parse_commands as parse_sokoban_commands,
    public_game as public_sokoban,
    reset_level as reset_sokoban,
    undo as undo_sokoban,
)
from .mine_karel import execute as execute_karel, new_game as new_karel, public_game as public_karel, reset as reset_karel
from .triad_game import new_game as new_triad, place as place_triad, public_game as public_triad, reset as reset_triad

LLM_ENABLED = os.getenv("ESCAPEBOT_LLM_ENABLED", "").lower() in {"1", "true", "yes", "on"}


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
    checkpoint_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    unlocked_cipher_tools: set[str] = field(default_factory=set)
    paid_cipher_tools: set[str] = field(default_factory=set)
    puzzle_attempts: dict[str, int] = field(default_factory=dict)
    interactive_games: dict[str, dict[str, Any]] = field(default_factory=dict)
    sokoban_games: dict[str, dict[str, Any]] = field(default_factory=dict)
    karel_games: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_activity_at: str = ""
    triad_games: dict[str, dict[str, Any]] = field(default_factory=dict)
    archive_games: dict[str, dict[str, Any]] = field(default_factory=dict)
    event_history: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "unlocked_discoveries": sorted(self.unlocked_discoveries),
            "inventory": list(self.inventory),
            "flags": self.flags,
            "chat_history": self.chat_history,
            "score": self.score,
            "hints_used": self.hints_used,
            "checkpoint_states": self.checkpoint_states,
            "unlocked_cipher_tools": sorted(self.unlocked_cipher_tools),
            "paid_cipher_tools": sorted(self.paid_cipher_tools),
            "puzzle_attempts": self.puzzle_attempts,
            "interactive_games": self.interactive_games,
            "sokoban_games": self.sokoban_games,
            "karel_games": self.karel_games,
            "last_activity_at": self.last_activity_at,
            "triad_games": self.triad_games,
            "archive_games": self.archive_games,
            "event_history": self.event_history,
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
        state.checkpoint_states = dict(data.get("checkpoint_states", {}))
        state.unlocked_cipher_tools = set(data.get("unlocked_cipher_tools", []))
        state.paid_cipher_tools = set(data.get("paid_cipher_tools", []))
        state.puzzle_attempts = dict(data.get("puzzle_attempts", {}))
        state.interactive_games = dict(data.get("interactive_games", {}))
        state.sokoban_games = dict(data.get("sokoban_games", {}))
        state.karel_games = dict(data.get("karel_games", {}))
        state.last_activity_at = str(data.get("last_activity_at", ""))
        state.triad_games = dict(data.get("triad_games", {}))
        state.archive_games = dict(data.get("archive_games", {}))
        state.event_history = list(data.get("event_history", []))
        return state


class EscapeBotStateMachine:
    def __init__(self, scenario: Scenario) -> None:
        self.state = GameState()
        self.scenario = scenario
        self._unlock_default_cipher_tools()
        self.ai = OllamaAdapter(model="llama3") # Možno změnit model např. na llama3.1

    def restore_state(self, data: dict[str, Any]) -> None:
        self.state = GameState.restore(data)
        if self.state.phase in {GamePhase.NAVIGATING, GamePhase.PORTAL_OPEN}:
            self.state.flags["chronomap_unlocked"] = True
        self._unlock_default_cipher_tools()

    def _unlock_default_cipher_tools(self) -> None:
        for tool_id, tool in self.scenario.data.get("cipher_tools", {}).items():
            if tool.get("default_unlocked", False):
                self.state.unlocked_cipher_tools.add(tool_id)

    async def handle(self, message: Message) -> list[Message]:
        now = datetime.now(UTC).isoformat()
        self.state.last_activity_at = now
        if message.type not in {"client.hello", "camera.frame"}:
            detail_keys = {
                "player.message": ("channel",),
                "qr.detected": ("code", "value"),
                "arg.verify": ("id", "answer"),
                "room.unlock": ("room",),
                "room.hint": ("room_id",),
                "cipher_tool.unlock": ("tool_id",),
                "puzzle.submit": ("puzzle_id",),
                "puzzle.hint": ("puzzle_id",),
                "phase.hint": ("phase_id", "hint_index"),
                "line_game.move": ("puzzle_id",),
                "line_game.reset": ("puzzle_id",),
                "sokoban.command": ("puzzle_id", "commands"),
                "sokoban.undo": ("puzzle_id",),
                "sokoban.reset": ("puzzle_id",),
                "karel.command": ("puzzle_id", "commands"),
                "karel.reset": ("puzzle_id",),
                "triad.place": ("puzzle_id",),
                "triad.reset": ("puzzle_id",),
                "finale.activate": (),
                "archive.arrange": ("puzzle_id",),
            }
            details = {key: str(message.payload.get(key, ""))[:120] for key in detail_keys.get(message.type, ()) if message.payload.get(key) is not None and message.payload.get(key) != ""}
            self.state.event_history.append({"at": now, "type": message.type, "details": details})
            self.state.event_history = self.state.event_history[-500:]
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
            "room.hint": self._handle_room_hint,
            "cipher_tool.unlock": self._handle_cipher_tool_unlock,
            "puzzle.submit": self._handle_puzzle_submit,
            "puzzle.hint": self._handle_puzzle_hint,
            "phase.hint": self._handle_phase_hint,
            "line_game.move": self._handle_line_game_move,
            "line_game.reset": self._handle_line_game_reset,
            "sokoban.command": self._handle_sokoban_command,
            "sokoban.undo": self._handle_sokoban_undo,
            "sokoban.reset": self._handle_sokoban_reset,
            "karel.command": self._handle_karel_command,
            "karel.reset": self._handle_karel_reset,
            "triad.place": self._handle_triad_place,
            "triad.reset": self._handle_triad_reset,
            "finale.activate": self._handle_finale_activate,
            "archive.arrange": self._handle_archive_arrange,
        }
        handler = handlers.get(message.type, self._handle_unknown)
        responses = await handler(message)

        # Automatické uložení odpovědí bota do historie
        for resp in responses:
            if resp.type == "bot.message":
                self.state.chat_history.append({
                    "role": "bot",
                    "channel": resp.payload.get("channel", "general"),
                    "text": resp.payload.get("text", ""),
                    **({"voice_id": resp.payload["voice_id"]} if resp.payload.get("voice_id") else {}),
                    **({"audio_url": resp.payload["audio_url"]} if resp.payload.get("audio_url") else {}),
                })

        return responses

    def _state_message(self) -> Message:
        snapshot = self.state.snapshot()
        phase_id = self.state.phase.value
        phase_hints = self.scenario.get_phase_data(phase_id).get("hints", [])
        snapshot["phase_hints"] = {
            "phase_id": phase_id,
            "count": len(phase_hints),
            "unlocked": min(self.state.hints_used.get(phase_id, 0), len(phase_hints)),
            "costs": [int(hint.get("penalty", 10)) for hint in phase_hints],
        }
        tools = self.scenario.data.get("cipher_tools", {})
        snapshot["cipher_tools"] = [
            {
                "id": tool_id,
                "label": tool.get("label", tool_id),
                "status": "unlocked" if tool_id in self.state.unlocked_cipher_tools else "available_for_points",
                "unlock_cost": int(tool.get("unlock_cost", 0)),
            }
            for tool_id, tool in tools.items()
        ]
        snapshot["puzzles"] = self._puzzle_state()
        return Message("game.state", snapshot)

    def _puzzle_state(self) -> list[dict[str, Any]]:
        result = []
        for puzzle_id, puzzle in self.scenario.data.get("puzzles", {}).items():
            checkpoint_id = puzzle.get("checkpoint_id")
            checkpoint_state = self.state.checkpoint_states.get(checkpoint_id, {})
            status = checkpoint_state.get("status", "locked")
            item = {
                "id": puzzle_id,
                "title": puzzle.get("title", puzzle_id),
                "type": puzzle.get("type", "text"),
                "status": status,
                "attempts": self.state.puzzle_attempts.get(puzzle_id, 0),
                "has_hints": bool(puzzle.get("hints")),
                "hint_count": len(puzzle.get("hints", [])),
                "hints_unlocked": min(self.state.hints_used.get(f"puzzle.{puzzle_id}", 0), len(puzzle.get("hints", []))),
                "hint_costs": [int(hint.get("penalty", 10)) for hint in puzzle.get("hints", [])],
            }
            if status in {"found", "solved"}:
                item.update({
                    "instructions": puzzle.get("instructions", ""),
                    "image": puzzle.get("image"),
                    "categories": puzzle.get("categories", {}),
                    "clues": puzzle.get("clues", []),
                    "ciphertext": puzzle.get("ciphertext", ""),
                })
                if puzzle.get("type") == "line_game":
                    config = puzzle.get("game", {})
                    game = self._line_game_state(puzzle_id, config)
                    item["game"] = public_game(config, game)
                elif puzzle.get("type") == "sokoban":
                    game = self._sokoban_state(puzzle_id, puzzle.get("game", {}))
                    item["game"] = public_sokoban(puzzle.get("game", {}), game)
                elif puzzle.get("type") == "mine_karel":
                    game = self._karel_state(puzzle_id, puzzle.get("game", {}))
                    item["game"] = public_karel(puzzle.get("game", {}), game)
                elif puzzle.get("type") == "triad":
                    game = self._triad_state(puzzle_id, puzzle.get("game", {})); item["game"] = public_triad(puzzle.get("game", {}), game)
                elif puzzle.get("type") == "finale":
                    item["finale"] = {
                        "module_labels": list(puzzle.get("module_labels", [])),
                        "countdown_seconds": int(puzzle.get("countdown_seconds", 10)),
                    }
                elif puzzle.get("type") == "archive_vector":
                    item["archive_game"] = self._public_archive_game(puzzle_id, puzzle)
            result.append(item)
        room = self.scenario.get_room_data("104")
        reception_solved = self.state.checkpoint_states.get("reception_archive", {}).get("status") == "solved"
        if room and reception_solved:
            hints = room.get("hints", [])
            result.append({
                "id": "room_104_panel",
                "room_id": "104",
                "title": "Přístupový panel dveří 104",
                "type": "room_pin",
                "status": "solved" if self.state.flags.get("room_104_unlocked") else "found",
                "instructions": room.get("clue", ""),
                "attempts": 0,
                "has_hints": bool(hints),
                "hint_count": len(hints),
                "hints_unlocked": min(self.state.hints_used.get("room_104", 0), len(hints)),
                "hint_costs": [int(hint.get("penalty", 10)) for hint in hints],
            })
        return result

    def _apply_rewards(self, rewards: dict[str, Any]) -> None:
        for item in rewards.get("inventory", []):
            if item not in self.state.inventory:
                self.state.inventory.append(item)
        for tool_id in rewards.get("cipher_tools", []):
            if tool_id in self.scenario.data.get("cipher_tools", {}):
                self.state.unlocked_cipher_tools.add(tool_id)
        for flag in rewards.get("flags", []):
            self.state.flags[str(flag)] = True

    def _apply_checkpoint_rewards(self, checkpoint: dict[str, Any]) -> None:
        self._apply_rewards(checkpoint.get("rewards", {}))

    def _navigation_message(self, checkpoint_id: str, message: Message) -> Message | None:
        navigation = self.scenario.data.get("checkpoints", {}).get(checkpoint_id, {}).get("navigation_message")
        return reply("bot.message", navigation, message) if navigation else None

    def admin_set_checkpoint(self, checkpoint_id: str, status: str) -> dict[str, Any]:
        """Apply an explicit Game Master override without gameplay score bonuses."""
        checkpoint = self.scenario.data.get("checkpoints", {}).get(checkpoint_id)
        if checkpoint is None:
            raise ValueError("Neznámý checkpoint.")
        if status not in {"found", "solved"}:
            raise ValueError("Neplatný cílový stav checkpointu.")

        now = datetime.now(UTC).isoformat()
        checkpoint_state = self.state.checkpoint_states.get(checkpoint_id)
        previous_status = checkpoint_state.get("status") if checkpoint_state else "locked"
        if previous_status == "solved":
            raise ValueError("Checkpoint už je dokončený.")
        if previous_status == "found" and status == "found":
            raise ValueError("Checkpoint už byl potvrzen jako nalezený.")

        if checkpoint_state is None:
            checkpoint_state = {"status": "found", "first_scanned_at": now}
            self.state.checkpoint_states[checkpoint_id] = checkpoint_state
            self.state.unlocked_discoveries.add(checkpoint_id)
            self._apply_rewards(checkpoint.get("found_rewards", {}))
        checkpoint_state["status"] = status
        checkpoint_state["admin_override_at"] = now
        if status == "solved":
            checkpoint_state["solved_at"] = now
            self._apply_checkpoint_rewards(checkpoint)
        self.state.last_activity_at = now
        return {"checkpoint_id": checkpoint_id, "previous_status": previous_status, "status": status}

    def admin_reset_game(self, puzzle_id: str) -> dict[str, Any]:
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id)
        if puzzle is None:
            raise ValueError("Neznámá minihra.")
        checkpoint_id = str(puzzle.get("checkpoint_id", ""))
        checkpoint_state = self.state.checkpoint_states.get(checkpoint_id)
        if not checkpoint_state or checkpoint_state.get("status") != "found":
            raise ValueError("Restartovat lze pouze aktivní, nedokončenou minihru.")
        config = puzzle.get("game", {})
        game_type = puzzle.get("type")
        if game_type == "line_game":
            reset_game(config, self._line_game_state(puzzle_id, config))
        elif game_type == "mine_karel":
            reset_karel(config, self._karel_state(puzzle_id, config))
        elif game_type == "triad":
            reset_triad(config, self._triad_state(puzzle_id, config))
        elif game_type == "sokoban":
            reset_sokoban(config, self._sokoban_state(puzzle_id, config))
        else:
            raise ValueError("Tato hádanka nemá restartovatelnou minihru.")
        self.state.last_activity_at = datetime.now(UTC).isoformat()
        return {"puzzle_id": puzzle_id, "checkpoint_id": checkpoint_id, "game_type": game_type}

    def _provide_hint(self, phase: str, message: Message) -> list[Message]:
        p_data = self.scenario.get_phase_data(phase)
        return self._provide_hint_list(phase, p_data.get("hints", []), message)

    def _provide_hint_list(self, key: str, hints: list[dict[str, Any]], message: Message, requested_index: int | None = None) -> list[Message]:
        
        if not hints:
            return [reply("bot.message", {"text": "Systém: Pro tuto situaci nemám v databázi žádné další nápovědy.", "mood": "error", "channel": "general"}, message)]
            
        unlocked = min(self.state.hints_used.get(key, 0), len(hints))
        idx = min(unlocked, len(hints) - 1) if requested_index is None else requested_index
        if idx < 0 or idx >= len(hints):
            return [reply("error", {"message": "Neplatný stupeň nápovědy."}, message)]
        if idx > unlocked:
            return [reply("error", {"message": "Nejprve odemkněte předchozí nápovědu."}, message)]
        is_new_hint = idx == unlocked
            
        hint = hints[idx]
        responses = []
        
        if is_new_hint:
            self.state.score -= hint.get("penalty", 10)
            self.state.hints_used[key] = unlocked + 1
            responses.append(reply("score.update", {"score": self.state.score, "penalty": hint.get("penalty", 10)}, message))
            
        responses.append(reply("bot.message", {"text": f"NÁPOVĚDA SYSTÉMU: {hint.get('text', '')}", "mood": "info", "channel": "general"}, message))
        responses.append(self._state_message())
        return responses

    async def _handle_hello(self, message: Message) -> list[Message]:
        # Vygenerování avatarů pro postavy pomocí promptů ze scénáře
        avatar_msgs = []
        characters = self.scenario.data.get("characters", {})
        for channel, char_data in characters.items():
            prompt = char_data.get("avatar_prompt")
            if prompt:
                # Zástupný AI Image Generator (Pollinations.ai). 
                # Až budete mít ComfyUI, stačí tuto URL změnit na váš lokální uzel.
                encoded_prompt = urllib.parse.quote(prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=128&height=128&nologo=true&seed=42"
                avatar_msgs.append(Message("avatar.update", {"channel": channel, "url": url}))

        if self.state.phase == GamePhase.BOOT:
            self.state.phase = GamePhase.COMMS_OFFLINE
            p_data = self.scenario.get_phase_data("comms_offline")
            return avatar_msgs + [
                reply("bot.message", p_data.get("enter_message", {}), message),
                self._state_message(),
            ]
        else:
            # Znovupřipojení během hry – pošleme historii a neresetujeme stav
            msg_reconnect = self.scenario.data.get("global_events", {}).get("reconnect", {})
            return avatar_msgs + [
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
                self.state.flags["chronomap_unlocked"] = True
                return [
                    reply("bot.message", p_data.get("success_message", {}), message),
                    self._state_message(),
                ]
            else:
                return [
                    reply("bot.message", p_data.get("fail_message", {}), message),
                    self._state_message(),
                ]

        # Výchozí odpověď pro fázi NAVIGATING
        if str(message.payload.get("channel", "general")) == "lost":
            sokoban_id = self._active_sokoban_id()
            if sokoban_id:
                try:
                    commands = parse_sokoban_commands(text)
                except ValueError as error:
                    return [
                        reply("bot.message", {"text": str(error), "mood": "error", "channel": "lost"}, message),
                        self._state_message(),
                    ]
                if commands == ["undo"]:
                    return await self._handle_sokoban_undo(Message("sokoban.undo", {"puzzle_id": sokoban_id, "_client_id": message.payload.get("_client_id")}, message.request_id))
                if commands == ["reset"]:
                    return await self._handle_sokoban_reset(Message("sokoban.reset", {"puzzle_id": sokoban_id, "_client_id": message.payload.get("_client_id")}, message.request_id))
                if commands:
                    return await self._execute_sokoban_commands(sokoban_id, commands, message)
            karel_id = self._active_karel_id()
            if karel_id:
                try:
                    commands = parse_sokoban_commands(text)
                except ValueError as error:
                    return [reply("bot.message", {"text": str(error), "mood": "error", "channel": "lost"}, message), self._state_message()]
                if commands == ["reset"]:
                    return await self._handle_karel_reset(Message("karel.reset", {"puzzle_id": karel_id}, message.request_id))
                if commands and commands != ["undo"]:
                    return await self._handle_karel_command(Message("karel.command", {"puzzle_id": karel_id, "commands": commands}, message.request_id))

        p_data = self.scenario.get_phase_data("navigating")
        
        ai_prompt = p_data.get("ai_system_prompt")
        if LLM_ENABLED and ai_prompt:
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
        prefix = "escapebot://checkpoint/"
        token = value.removeprefix(prefix)
        if not token or token == value:
            return [reply("qr.result", {"accepted": False, "reason": "Neznámý formát QR kódu."}, message)]

        checkpoints = self.scenario.data.get("checkpoints", {})
        match = next(((checkpoint_id, data) for checkpoint_id, data in checkpoints.items() if data.get("token") == token), None)
        if match is None:
            return [reply("qr.result", {"accepted": False, "reason": "Tato časová kotva nepatří do aktuálního scénáře."}, message)]

        checkpoint_id, checkpoint = match
        if checkpoint_id in self.state.checkpoint_states:
            return [
                reply("qr.result", {"accepted": True, "duplicate": True, "checkpoint_id": checkpoint_id}, message),
                self._state_message(),
            ]

        required_phase = checkpoint.get("requires_phase")
        if required_phase and self.state.phase.value != required_phase:
            return [
                reply("qr.result", {
                    "accepted": False,
                    "reason": "Časová kotva zatím nereaguje. Pokračujte nejprve v hlavním příběhu.",
                    "required_phase": required_phase,
                }, message),
                self._state_message(),
            ]

        missing = [
            required for required in checkpoint.get("requires", [])
            if self.state.checkpoint_states.get(required, {}).get("status") != "solved"
        ]
        if missing:
            return [
                reply("qr.result", {
                    "accepted": False,
                    "reason": "Časová kotva je mimo sekvenci. Nejprve dokončete předchozí stanoviště.",
                    "missing": missing,
                }, message),
                self._state_message(),
            ]

        now = datetime.now(UTC).isoformat()
        puzzle_id = checkpoint.get("puzzle_id")
        checkpoint_status = "found" if puzzle_id else "solved"
        self.state.checkpoint_states[checkpoint_id] = {"status": checkpoint_status, "first_scanned_at": now}
        if checkpoint_status == "solved":
            self.state.checkpoint_states[checkpoint_id]["solved_at"] = now
        self.state.unlocked_discoveries.add(checkpoint_id)
        self._apply_rewards(checkpoint.get("found_rewards", {}))
        if checkpoint_status == "solved":
            self._apply_checkpoint_rewards(checkpoint)

        msg_template = checkpoint.get("message", self.scenario.data.get("global_events", {}).get("qr_detected", {})).copy()
        msg_template["text"] = msg_template.get("text", "").replace("{checkpoint_id}", checkpoint_id)

        responses = [
            reply("qr.result", {
                "accepted": True,
                "duplicate": False,
                "checkpoint_id": checkpoint_id,
                "puzzle_id": puzzle_id,
                "status": checkpoint_status,
            }, message),
            reply("bot.message", msg_template, message),
        ]
        warning = checkpoint.get("warning_if_missing_flag")
        if warning and not self.state.flags.get(str(warning.get("flag", ""))):
            responses.append(reply("bot.message", warning.get("message", {}), message))
        responses.extend([Message("effect.trigger", {"effect": "glitch", "intensity": 0.35, "duration_ms": 900}), self._state_message()])
        return responses

    async def _handle_puzzle_submit(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        answer = str(message.payload.get("answer", "")).strip().replace(" ", "").upper()
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id)
        if puzzle is None:
            return [reply("puzzle.result", {"correct": False, "reason": "Neznámá hádanka."}, message)]
        if puzzle.get("type") in {"line_game", "sokoban", "mine_karel", "triad", "finale"}:
            return [reply("puzzle.result", {"correct": False, "reason": "Tato úloha se řeší přímo na herní mřížce."}, message)]

        checkpoint_id = str(puzzle.get("checkpoint_id", ""))
        checkpoint_state = self.state.checkpoint_states.get(checkpoint_id)
        if checkpoint_state is None:
            return [reply("puzzle.result", {"correct": False, "reason": "Hádanka zatím nebyla nalezena."}, message)]
        if checkpoint_state.get("status") == "solved":
            return [reply("puzzle.result", {"correct": True, "puzzle_id": puzzle_id, "already_solved": True}, message), self._state_message()]
        if puzzle.get("type") == "archive_vector" and not self._archive_game_state(puzzle_id, puzzle).get("assembled"):
            return [
                reply("puzzle.result", {"correct": False, "reason": "Nejprve správně sestavte obraz stroje času."}, message),
                self._state_message(),
            ]

        self.state.puzzle_attempts[puzzle_id] = self.state.puzzle_attempts.get(puzzle_id, 0) + 1
        accepted_answers = puzzle.get("answers", [puzzle.get("answer", "")])
        normalized_answers = {
            str(candidate).strip().replace(" ", "").upper()
            for candidate in accepted_answers
        }
        if answer not in normalized_answers:
            return [
                reply("puzzle.result", {"correct": False, "puzzle_id": puzzle_id, "attempts": self.state.puzzle_attempts[puzzle_id]}, message),
                reply("bot.message", puzzle.get("failure_message", {}), message),
                self._state_message(),
            ]

        now = datetime.now(UTC).isoformat()
        checkpoint_state["status"] = "solved"
        checkpoint_state["solved_at"] = now
        checkpoint = self.scenario.data.get("checkpoints", {}).get(checkpoint_id, {})
        self._apply_checkpoint_rewards(checkpoint)
        responses = [
            reply("puzzle.result", {"correct": True, "puzzle_id": puzzle_id, "attempts": self.state.puzzle_attempts[puzzle_id]}, message),
            reply("bot.message", puzzle.get("success_message", {}), message),
        ]
        navigation = self._navigation_message(checkpoint_id, message)
        if navigation: responses.append(navigation)
        responses.append(self._state_message())
        return responses

    def _archive_game_state(self, puzzle_id: str, puzzle: dict[str, Any]) -> dict[str, Any]:
        config = puzzle.get("assembly", {})
        card_ids = [str(card.get("id")) for card in config.get("cards", [])]
        game = self.state.archive_games.get(puzzle_id)
        if not isinstance(game, dict) or set(game.get("order", [])) != set(card_ids):
            game = {
                "order": list(config.get("initial_order", card_ids)),
                "rotations": {str(key): int(value) % 360 for key, value in config.get("initial_rotations", {}).items()},
                "moves": 0,
                "assembled": False,
            }
            self.state.archive_games[puzzle_id] = game
        for card_id in card_ids:
            game.setdefault("rotations", {}).setdefault(card_id, 0)
        return game

    def _public_archive_game(self, puzzle_id: str, puzzle: dict[str, Any]) -> dict[str, Any]:
        game = self._archive_game_state(puzzle_id, puzzle)
        cards = {str(card["id"]): {"id": str(card["id"]), "label": card.get("label", card["id"]), "color": card.get("color", "cyan"), "icon": card.get("icon", "◇")} for card in puzzle.get("assembly", {}).get("cards", [])}
        for card in puzzle.get("assembly", {}).get("cards", []):
            cards[str(card["id"])]["source_index"] = int(card.get("source_index", 0))
        config = puzzle.get("assembly", {})
        return {
            "order": list(game["order"]),
            "rotations": dict(game["rotations"]),
            "moves": int(game.get("moves", 0)),
            "assembled": bool(game.get("assembled")),
            "cards": cards,
            "mode": config.get("mode", "cards"),
            "image": config.get("image", ""),
            "grid_size": int(config.get("grid_size", 3)),
            "revealed_key": puzzle.get("assembly", {}).get("revealed_key", "") if game.get("assembled") else "",
            "module_order": list(puzzle.get("assembly", {}).get("module_order", [])) if game.get("assembled") else [],
        }

    async def _handle_archive_arrange(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id)
        checkpoint_id = str(puzzle.get("checkpoint_id", "")) if puzzle else ""
        checkpoint = self.state.checkpoint_states.get(checkpoint_id)
        if not puzzle or puzzle.get("type") != "archive_vector" or not checkpoint or checkpoint.get("status") != "found":
            return [reply("archive.result", {"success": False, "reason": "Archivní skládačka nyní není aktivní."}, message)]
        game = self._archive_game_state(puzzle_id, puzzle)
        card_id = str(message.payload.get("card_id", ""))
        action = str(message.payload.get("action", ""))
        if card_id not in game["order"]:
            return [reply("archive.result", {"success": False, "reason": "Neznámá archivní karta."}, message)]
        index = game["order"].index(card_id)
        if action == "left" and index > 0:
            game["order"][index - 1], game["order"][index] = game["order"][index], game["order"][index - 1]
        elif action == "right" and index < len(game["order"]) - 1:
            game["order"][index + 1], game["order"][index] = game["order"][index], game["order"][index + 1]
        elif action == "rotate":
            game["rotations"][card_id] = (int(game["rotations"].get(card_id, 0)) + 90) % 360
        elif action == "swap":
            target_id = str(message.payload.get("target_id", ""))
            if target_id not in game["order"] or target_id == card_id:
                return [reply("archive.result", {"success": False, "reason": "Vyberte dva různé dílky."}, message), self._state_message()]
            target_index = game["order"].index(target_id)
            game["order"][index], game["order"][target_index] = game["order"][target_index], game["order"][index]
        else:
            return [reply("archive.result", {"success": False, "reason": "Kartu tímto směrem nelze posunout."}, message), self._state_message()]
        game["moves"] = int(game.get("moves", 0)) + 1
        config = puzzle.get("assembly", {})
        correct_order = [str(item) for item in config.get("correct_order", [])]
        correct_rotations = {str(key): int(value) % 360 for key, value in config.get("correct_rotations", {}).items()}
        game["assembled"] = game["order"] == correct_order and all(int(game["rotations"].get(card_id, 0)) == rotation for card_id, rotation in correct_rotations.items())
        return [
            reply("archive.result", {"success": True, "assembled": game["assembled"]}, message),
            self._state_message(),
        ]

    async def _handle_puzzle_hint(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id)
        if puzzle is None:
            return [reply("error", {"message": "Neznámá hádanka."}, message)]
        checkpoint_id = puzzle.get("checkpoint_id")
        if self.state.checkpoint_states.get(checkpoint_id, {}).get("status") != "found":
            return [reply("error", {"message": "Pro tuto hádanku nyní nelze použít nápovědu."}, message)]

        hints = puzzle.get("hints", [])
        if not hints:
            return [reply("error", {"message": "Nejsou dostupné žádné nápovědy."}, message)]
        try:
            requested_index = int(message.payload.get("hint_index", self.state.hints_used.get(f"puzzle.{puzzle_id}", 0)))
        except (TypeError, ValueError):
            return [reply("error", {"message": "Neplatný stupeň nápovědy."}, message)]
        return self._provide_hint_list(f"puzzle.{puzzle_id}", hints, message, requested_index)

    async def _handle_phase_hint(self, message: Message) -> list[Message]:
        phase_id = str(message.payload.get("phase_id", "")).strip()
        if phase_id != self.state.phase.value:
            return [reply("error", {"message": "Tato fáze už není aktivní."}, message)]
        hints = self.scenario.get_phase_data(phase_id).get("hints", [])
        try:
            requested_index = int(message.payload.get("hint_index", self.state.hints_used.get(phase_id, 0)))
        except (TypeError, ValueError):
            return [reply("error", {"message": "Neplatný stupeň nápovědy."}, message)]
        return self._provide_hint_list(phase_id, hints, message, requested_index)

    def _active_line_game(self, puzzle_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id)
        if puzzle is None or puzzle.get("type") != "line_game":
            raise ValueError("Neznámá interaktivní úloha.")
        checkpoint_id = str(puzzle.get("checkpoint_id", ""))
        checkpoint_state = self.state.checkpoint_states.get(checkpoint_id)
        if checkpoint_state is None:
            raise ValueError("Interaktivní úloha zatím nebyla nalezena.")
        if checkpoint_state.get("status") == "solved":
            raise ValueError("Interaktivní úloha už byla dokončena.")
        config = puzzle.get("game", {})
        game = self._line_game_state(puzzle_id, config)
        return puzzle, checkpoint_state, game

    def _line_game_state(self, puzzle_id: str, config: dict[str, Any]) -> dict[str, Any]:
        game = self.state.interactive_games.get(puzzle_id)
        is_current_format = (
            isinstance(game, dict)
            and isinstance(game.get("progress"), dict)
            and isinstance(game.get("board"), list)
            and bool(game.get("deadline_at"))
        )
        if not is_current_format:
            game = new_game(config)
            self.state.interactive_games[puzzle_id] = game
        return game

    async def _handle_line_game_move(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        try:
            puzzle, checkpoint_state, game = self._active_line_game(puzzle_id)
            first = message.payload.get("first", [])
            second = message.payload.get("second", [])
            if not isinstance(first, list) or not isinstance(second, list) or len(first) != 2 or len(second) != 2:
                raise ValueError("Tah musí obsahovat dvě souřadnice.")
            result = swap(
                puzzle.get("game", {}), game,
                (int(first[0]), int(first[1])), (int(second[0]), int(second[1])),
            )
        except (TypeError, ValueError) as error:
            return [reply("line_game.result", {"success": False, "reason": str(error)}, message), self._state_message()]

        responses = [reply("line_game.result", {"success": True, **result}, message)]
        if result["game_complete"]:
            now = datetime.now(UTC).isoformat()
            checkpoint_state["status"] = "solved"
            checkpoint_state["solved_at"] = now
            checkpoint = self.scenario.data.get("checkpoints", {}).get(puzzle.get("checkpoint_id"), {})
            self._apply_checkpoint_rewards(checkpoint)
            score_delta = int(result.get("score_delta", 0))
            self.state.score += score_delta
            responses.append(reply("score.update", {
                "score": self.state.score,
                "delta": score_delta,
                "bonus": max(0, score_delta),
                "penalty": max(0, -score_delta),
                "reason": "line_game_time",
            }, message))
            responses.extend([
                reply("puzzle.result", {"correct": True, "puzzle_id": puzzle_id}, message),
                reply("bot.message", puzzle.get("success_message", {}), message),
            ])
            navigation = self._navigation_message(str(puzzle.get("checkpoint_id", "")), message)
            if navigation: responses.append(navigation)
        responses.append(self._state_message())
        return responses

    async def _handle_line_game_reset(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        try:
            puzzle, _, game = self._active_line_game(puzzle_id)
            reset_game(puzzle.get("game", {}), game)
        except ValueError as error:
            return [reply("line_game.result", {"success": False, "reason": str(error)}, message), self._state_message()]
        return [
            reply("line_game.result", {"success": True, "reset": True}, message),
            self._state_message(),
        ]

    def _active_karel_id(self) -> str | None:
        for puzzle_id, puzzle in self.scenario.data.get("puzzles", {}).items():
            checkpoint = self.state.checkpoint_states.get(str(puzzle.get("checkpoint_id", "")), {})
            if puzzle.get("type") == "mine_karel" and checkpoint.get("status") == "found": return puzzle_id
        return None

    def _karel_state(self, puzzle_id: str, config: dict[str, Any]) -> dict[str, Any]:
        game = self.state.karel_games.get(puzzle_id)
        if not isinstance(game, dict) or not game.get("deadline_at"):
            game = new_karel(config); self.state.karel_games[puzzle_id] = game
        return game

    async def _handle_karel_command(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", ""))
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id, {})
        checkpoint_id = str(puzzle.get("checkpoint_id", ""))
        checkpoint_state = self.state.checkpoint_states.get(checkpoint_id)
        if puzzle.get("type") != "mine_karel" or not checkpoint_state or checkpoint_state.get("status") != "found":
            return [reply("karel.result", {"success": False, "reason": "Navigační pole není aktivní."}, message)]
        try:
            result = execute_karel(self._karel_state(puzzle_id, puzzle.get("game", {})), puzzle.get("game", {}), list(message.payload.get("commands", [])))
        except ValueError as error:
            return [reply("karel.result", {"success": False, "reason": str(error)}, message), self._state_message()]
        if result["score_delta"]:
            self.state.score += result["score_delta"]
        command_names = {"up": "NAHORU", "down": "DOLŮ", "left": "VLEVO", "right": "VPRAVO"}
        understood = ", ".join(command_names.get(item, item.upper()) for item in message.payload.get("commands", []))
        responses = [
            reply("bot.message", {"text": f"Rozumím sekvenci: {understood}. Provádím.", "mood": "focused", "channel": "lost"}, message),
            reply("karel.result", result, message),
        ]
        if result["hit_mine"]:
            responses.append(reply("bot.message", {"text": "Pozor! Narazila jsem na nestabilní pole a nouzový systém mě vrátil na začátek.", "mood": "tense", "channel": "lost", "voice_id": "elara_anomaly_hit"}, message))
        elif result["blocked"]:
            responses.append(reply("bot.message", {"text": "Tudy cesta nevede. Poslední povel by mě vyvedl mimo stabilní oblast.", "mood": "alert", "channel": "lost"}, message))
        elif result["frames"]:
            last_frame = result["frames"][-1]
            clue = int(last_frame.get("clue") or 0)
            if last_frame.get("revisited"):
                text = f"Toto pole už znám. Sonda stále hlásí {clue} okolních anomálií."
            elif clue >= 3:
                text = f"Silné rušení. V osmi okolních polích jsou {clue} anomálie."
            elif clue:
                text = f"Sonda hlásí {clue} okolní anomálie. Postupuji opatrně."
            else:
                text = "Okolí je čisté, sonda nehlásí žádnou anomálii."
            responses.append(reply("bot.message", {"text": text, "mood": "focused", "channel": "lost"}, message))
        if result["game_complete"]:
            checkpoint_state["status"] = "solved"; checkpoint_state["solved_at"] = datetime.now(UTC).isoformat()
            self._apply_checkpoint_rewards(self.scenario.data.get("checkpoints", {}).get(checkpoint_id, {}))
            responses.extend([reply("puzzle.result", {"correct": True, "puzzle_id": puzzle_id}, message), reply("bot.message", puzzle.get("success_message", {}), message)])
            navigation = self._navigation_message(checkpoint_id, message)
            if navigation: responses.append(navigation)
        if result["score_delta"]:
            responses.append(reply("score.update", {"score": self.state.score, "delta": result["score_delta"], "bonus": max(0, result["score_delta"]), "penalty": max(0, -result["score_delta"]), "reason": "mine_karel"}, message))
        responses.append(self._state_message())
        return responses

    async def _handle_karel_reset(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")); puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id, {})
        if puzzle.get("type") != "mine_karel": return [reply("karel.result", {"success": False, "reason": "Neznámé pole."}, message)]
        reset_karel(puzzle.get("game", {}), self._karel_state(puzzle_id, puzzle.get("game", {})))
        return [reply("karel.result", {"success": True, "reset": True}, message), self._state_message()]

    def _triad_state(self, puzzle_id: str, config: dict[str, Any]) -> dict[str, Any]:
        game = self.state.triad_games.get(puzzle_id)
        if not isinstance(game, dict) or not game.get("deadline_at"):
            game = new_triad(config); self.state.triad_games[puzzle_id] = game
        return game

    async def _handle_triad_place(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")); puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id, {})
        checkpoint_id = str(puzzle.get("checkpoint_id", "")); checkpoint = self.state.checkpoint_states.get(checkpoint_id)
        if puzzle.get("type") != "triad" or not checkpoint or checkpoint.get("status") != "found": return [reply("triad.result", {"success": False, "reason": "Pole není aktivní."}, message)]
        try:
            result = place_triad(self._triad_state(puzzle_id, puzzle.get("game", {})), puzzle.get("game", {}), int(message.payload.get("row", -1)), int(message.payload.get("column", -1)), str(message.payload.get("symbol", "")))
        except (ValueError, TypeError) as error: return [reply("triad.result", {"success": False, "reason": str(error)}, message), self._state_message()]
        responses = [reply("triad.result", result, message)]
        if result["game_complete"]:
            checkpoint["status"] = "solved"; checkpoint["solved_at"] = datetime.now(UTC).isoformat(); self._apply_checkpoint_rewards(self.scenario.data.get("checkpoints", {}).get(checkpoint_id, {}))
            bonus = int(puzzle.get("game", {}).get("completion_bonus", 60)); self.state.score += bonus
            responses.extend([reply("score.update", {"score": self.state.score, "delta": bonus, "bonus": bonus, "penalty": 0, "reason": "triad"}, message), reply("puzzle.result", {"correct": True, "puzzle_id": puzzle_id}, message), reply("bot.message", puzzle.get("success_message", {}), message)])
            navigation = self._navigation_message(checkpoint_id, message)
            if navigation: responses.append(navigation)
        responses.append(self._state_message()); return responses

    async def _handle_triad_reset(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")); puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id, {})
        if puzzle.get("type") != "triad": return [reply("triad.result", {"success": False, "reason": "Neznámé pole."}, message)]
        reset_triad(puzzle.get("game", {}), self._triad_state(puzzle_id, puzzle.get("game", {})))
        return [reply("triad.result", {"success": True, "reset": True}, message), self._state_message()]

    def _active_sokoban_id(self) -> str | None:
        for puzzle_id, puzzle in self.scenario.data.get("puzzles", {}).items():
            if puzzle.get("type") != "sokoban":
                continue
            checkpoint = self.state.checkpoint_states.get(str(puzzle.get("checkpoint_id", "")), {})
            if checkpoint.get("status") == "found":
                return puzzle_id
        return None

    def _sokoban_state(self, puzzle_id: str, config: dict[str, Any]) -> dict[str, Any]:
        game = self.state.sokoban_games.get(puzzle_id)
        if (
            not isinstance(game, dict)
            or not isinstance(game.get("boxes"), list)
            or not game.get("player")
            or not game.get("level_id")
            or not game.get("deadline_at")
        ):
            game = new_sokoban(config)
            self.state.sokoban_games[puzzle_id] = game
        return game

    def _active_sokoban(self, puzzle_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id)
        if puzzle is None or puzzle.get("type") != "sokoban":
            raise ValueError("Neznámá sokobanová úloha.")
        checkpoint_state = self.state.checkpoint_states.get(str(puzzle.get("checkpoint_id", "")))
        if checkpoint_state is None:
            raise ValueError("Energetická mřížka zatím nebyla nalezena.")
        if checkpoint_state.get("status") == "solved":
            raise ValueError("Energetická mřížka už byla stabilizovaná.")
        return puzzle, checkpoint_state, self._sokoban_state(puzzle_id, puzzle.get("game", {}))

    async def _handle_sokoban_command(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        commands = message.payload.get("commands", [])
        if not isinstance(commands, list):
            return [reply("sokoban.result", {"success": False, "reason": "Neplatná sekvence."}, message)]
        return await self._execute_sokoban_commands(puzzle_id, [str(command) for command in commands], message)

    async def _execute_sokoban_commands(self, puzzle_id: str, commands: list[str], message: Message) -> list[Message]:
        try:
            puzzle, checkpoint_state, game = self._active_sokoban(puzzle_id)
            client_id = str(message.payload.get("_client_id", "")).strip()
            existing_speakers = list(game.setdefault("level_speakers", []))
            speaker_warning = bool(client_id and existing_speakers and client_id not in existing_speakers)
            if client_id and client_id not in existing_speakers:
                game["level_speakers"].append(client_id)
            result = execute_sokoban(game, puzzle.get("game", {}), commands)
        except ValueError as error:
            return [reply("sokoban.result", {"success": False, "reason": str(error)}, message), self._state_message()]

        responses = [reply("sokoban.result", {"success": True, "speaker_warning": speaker_warning, **result}, message)]
        if speaker_warning:
            responses.append(reply("bot.message", {
                "text": "Počkejte! Teď na mě mluví někdo jiný než před chvílí. V téhle tmě se podle překřikujících hlasů opravdu orientovat nedá — domluvte si jednoho navigátora!",
                "mood": "tense",
                "channel": "lost",
            }, message))
        if result["blocked"]:
            text = f"Provedla jsem {result['executed']} z {result['requested']} kroků. Další pohyb blokuje stěna nebo energetický článek."
        else:
            text = f"Sekvence potvrzena: {result['executed']} kroků, přesunuté články: {result['pushes']}."
        if result["level_complete"] and not result["game_complete"]:
            text += " Úroveň je stabilní; přepínám na další servisní sektor."
        responses.append(reply("bot.message", {"text": text, "mood": "focused", "channel": "lost"}, message))
        score_delta = int(result.get("score_delta", 0))
        if score_delta:
            self.state.score += score_delta
            responses.append(reply("score.update", {
                "score": self.state.score,
                "delta": score_delta,
                "bonus": score_delta,
                "penalty": 0,
                "reason": "sokoban_level",
                "level_id": result.get("completed_level_id"),
            }, message))
        if result["game_complete"]:
            now = datetime.now(UTC).isoformat()
            checkpoint_state["status"] = "solved"
            checkpoint_state["solved_at"] = now
            checkpoint = self.scenario.data.get("checkpoints", {}).get(puzzle.get("checkpoint_id"), {})
            self._apply_checkpoint_rewards(checkpoint)
            responses.extend([
                reply("puzzle.result", {"correct": True, "puzzle_id": puzzle_id}, message),
                reply("bot.message", puzzle.get("success_message", {}), message),
            ])
            navigation = self._navigation_message(str(puzzle.get("checkpoint_id", "")), message)
            if navigation: responses.append(navigation)
        responses.append(self._state_message())
        return responses

    async def _handle_sokoban_undo(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        try:
            _, _, game = self._active_sokoban(puzzle_id)
            changed = undo_sokoban(game)
        except ValueError as error:
            return [reply("sokoban.result", {"success": False, "reason": str(error)}, message), self._state_message()]
        text = "Vrátila jsem poslední krok." if changed else "Nemám žádný krok, ke kterému se mohu vrátit."
        return [
            reply("sokoban.result", {"success": changed, "undo": changed, "reason": "" if changed else text}, message),
            reply("bot.message", {"text": text, "mood": "focused", "channel": "lost"}, message),
            self._state_message(),
        ]

    async def _handle_sokoban_reset(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        try:
            puzzle, _, game = self._active_sokoban(puzzle_id)
            reset_sokoban(puzzle.get("game", {}), game)
        except ValueError as error:
            return [reply("sokoban.result", {"success": False, "reason": str(error)}, message), self._state_message()]
        return [
            reply("sokoban.result", {"success": True, "reset": True}, message),
            reply("bot.message", {"text": "Vracíme se k poslední stabilní časové kotvě. Mřížka je znovu v počáteční poloze.", "mood": "alert", "channel": "lost"}, message),
            self._state_message(),
        ]

    async def _handle_cipher_tool_unlock(self, message: Message) -> list[Message]:
        tool_id = str(message.payload.get("tool_id", "")).strip()
        tool = self.scenario.data.get("cipher_tools", {}).get(tool_id)
        if tool is None:
            return [reply("cipher_tool.result", {"success": False, "reason": "Neznámá pomůcka."}, message)]

        if tool_id in self.state.unlocked_cipher_tools:
            return [reply("cipher_tool.result", {"success": True, "tool_id": tool_id, "charged": 0}, message), self._state_message()]

        cost = max(0, int(tool.get("unlock_cost", 0)))
        if self.state.score < cost:
            return [reply("cipher_tool.result", {"success": False, "reason": "Nedostatek bodů."}, message)]

        self.state.score -= cost
        self.state.unlocked_cipher_tools.add(tool_id)
        self.state.paid_cipher_tools.add(tool_id)
        return [
            reply("cipher_tool.result", {"success": True, "tool_id": tool_id, "charged": cost}, message),
            reply("score.update", {"score": self.state.score, "penalty": cost, "reason": "cipher_tool"}, message),
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
                missing_checkpoints = [
                    checkpoint_id
                    for checkpoint_id in r_data.get("requires_checkpoints", [])
                    if self.state.checkpoint_states.get(checkpoint_id, {}).get("status") != "solved"
                ]
                if missing_checkpoints:
                    return [
                        reply("room.unlock_result", {
                            "success": False,
                            "reason": "missing_checkpoints",
                            "missing": missing_checkpoints,
                        }, message),
                        reply("bot.message", {
                            "text": "PIN je správný, ale zámek nemá potvrzenou předchozí časovou kotvu.",
                            "mood": "error",
                            "channel": "general",
                        }, message),
                        self._state_message(),
                    ]
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

    async def _handle_room_hint(self, message: Message) -> list[Message]:
        room_id = str(message.payload.get("room_id", "")).strip()
        room = self.scenario.get_room_data(room_id)
        if not room:
            return [reply("error", {"message": "Neznámý přístupový panel."}, message)]
        missing = [checkpoint_id for checkpoint_id in room.get("requires_checkpoints", []) if self.state.checkpoint_states.get(checkpoint_id, {}).get("status") != "solved"]
        if missing:
            return [reply("bot.message", {"text": "Nápověda k panelu je uzamčena, dokud neobnovíte příslušný archivní záznam.", "mood": "error", "channel": "general"}, message)]
        try:
            requested_index = int(message.payload.get("hint_index", self.state.hints_used.get(f"room_{room_id}", 0)))
        except (TypeError, ValueError):
            return [reply("error", {"message": "Neplatný stupeň nápovědy."}, message)]
        return self._provide_hint_list(f"room_{room_id}", room.get("hints", []), message, requested_index)

    async def _handle_finale_activate(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id)
        if not puzzle or puzzle.get("type") != "finale":
            return [reply("finale.result", {"success": False, "reason": "Neznámý finální terminál."}, message)]
        checkpoint_id = str(puzzle.get("checkpoint_id", ""))
        checkpoint_state = self.state.checkpoint_states.get(checkpoint_id)
        if not checkpoint_state:
            return [reply("finale.result", {"success": False, "reason": "Finální terminál zatím nebyl nalezen."}, message)]
        if checkpoint_state.get("status") == "solved" or self.state.flags.get("game_completed"):
            return [reply("finale.result", {"success": True, "already_complete": True, "score": self.state.score}, message), self._state_message()]

        missing_checkpoints = [
            item for item in puzzle.get("requires_checkpoints", [])
            if self.state.checkpoint_states.get(str(item), {}).get("status") != "solved"
        ]
        missing_inventory = [item for item in puzzle.get("requires_inventory", []) if item not in self.state.inventory]
        missing_flags = [item for item in puzzle.get("requires_flags", []) if not self.state.flags.get(str(item))]
        if missing_checkpoints or missing_inventory or missing_flags:
            return [
                reply("finale.result", {
                    "success": False,
                    "reason": "Stroj není kompletní. Chybí povinné kotvy, součásti nebo archivní potvrzení.",
                    "missing_checkpoints": missing_checkpoints,
                    "missing_inventory": missing_inventory,
                    "missing_flags": missing_flags,
                }, message),
                self._state_message(),
            ]

        def normalized(value: Any) -> str:
            return "".join(str(value).upper().split()).replace(":", "").replace("-", "")

        year = normalized(message.payload.get("year", ""))
        time_value = normalized(message.payload.get("time", ""))
        modules = message.payload.get("modules", [])
        if not isinstance(modules, list):
            modules = []
        submitted_modules = [normalized(item) for item in modules]
        expected_modules = [normalized(item) for item in puzzle.get("module_order", [])]
        self.state.puzzle_attempts[puzzle_id] = self.state.puzzle_attempts.get(puzzle_id, 0) + 1
        if year != normalized(puzzle.get("year")) or time_value != normalized(puzzle.get("time")) or submitted_modules != expected_modules:
            return [
                reply("finale.result", {"success": False, "reason": "Časové souřadnice nebo pořadí modulů nesouhlasí.", "attempts": self.state.puzzle_attempts[puzzle_id]}, message),
                reply("bot.message", puzzle.get("failure_message", {}), message),
                self._state_message(),
            ]

        now = datetime.now(UTC).isoformat()
        checkpoint_state.update({"status": "solved", "solved_at": now})
        self._apply_checkpoint_rewards(self.scenario.data.get("checkpoints", {}).get(checkpoint_id, {}))
        self.state.phase = GamePhase.PORTAL_OPEN
        self.state.flags.update({"game_completed": True, "completed_at": now})
        thresholds = puzzle.get("rating_thresholds", {})
        rating = next((label for minimum, label in sorted(((int(score), label) for score, label in thresholds.items()), reverse=True) if self.state.score >= minimum), "STABILIZOVÁNO")
        self.state.flags["final_rating"] = rating
        responses = [reply("finale.result", {
            "success": True,
            "score": self.state.score,
            "rating": rating,
            "countdown_seconds": int(puzzle.get("countdown_seconds", 10)),
        }, message)]
        responses.extend(reply("bot.message", item, message) for item in puzzle.get("success_messages", []))
        responses.extend([
            Message("effect.trigger", {"effect": "finale", "intensity": 1, "duration_ms": int(puzzle.get("countdown_seconds", 10)) * 1000}),
            reply("game.complete", {"score": self.state.score, "rating": rating, "completed_at": now}, message),
            self._state_message(),
        ])
        return responses

    async def _handle_unknown(self, message: Message) -> list[Message]:
        return [reply("error", {"message": f"Unsupported message type: {message.type}"}, message)]
