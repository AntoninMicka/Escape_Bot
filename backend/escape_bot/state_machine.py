from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .protocol import Message, reply
from .scenario import Scenario
from .ollama_adapter import OllamaAdapter
from .line_game import new_game, public_game, reset_game, swap


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
            "cipher_tool.unlock": self._handle_cipher_tool_unlock,
            "puzzle.submit": self._handle_puzzle_submit,
            "puzzle.hint": self._handle_puzzle_hint,
            "line_game.move": self._handle_line_game_move,
            "line_game.reset": self._handle_line_game_reset,
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
        snapshot = self.state.snapshot()
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
            }
            if status in {"found", "solved"}:
                item.update({
                    "instructions": puzzle.get("instructions", ""),
                    "image": puzzle.get("image"),
                    "categories": puzzle.get("categories", {}),
                    "clues": puzzle.get("clues", []),
                })
                if puzzle.get("type") == "line_game":
                    config = puzzle.get("game", {})
                    game = self._line_game_state(puzzle_id, config)
                    item["game"] = public_game(config, game)
            result.append(item)
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
                self.state.flags["chronomap_unlocked"] = True
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

        return [
            reply("qr.result", {
                "accepted": True,
                "duplicate": False,
                "checkpoint_id": checkpoint_id,
                "puzzle_id": puzzle_id,
                "status": checkpoint_status,
            }, message),
            reply("bot.message", msg_template, message),
            Message("effect.trigger", {"effect": "glitch", "intensity": 0.35, "duration_ms": 900}),
            self._state_message(),
        ]

    async def _handle_puzzle_submit(self, message: Message) -> list[Message]:
        puzzle_id = str(message.payload.get("puzzle_id", "")).strip()
        answer = str(message.payload.get("answer", "")).strip().replace(" ", "").upper()
        puzzle = self.scenario.data.get("puzzles", {}).get(puzzle_id)
        if puzzle is None:
            return [reply("puzzle.result", {"correct": False, "reason": "Neznámá hádanka."}, message)]
        if puzzle.get("type") == "line_game":
            return [reply("puzzle.result", {"correct": False, "reason": "Tato úloha se řeší přímo na herní mřížce."}, message)]

        checkpoint_id = str(puzzle.get("checkpoint_id", ""))
        checkpoint_state = self.state.checkpoint_states.get(checkpoint_id)
        if checkpoint_state is None:
            return [reply("puzzle.result", {"correct": False, "reason": "Hádanka zatím nebyla nalezena."}, message)]
        if checkpoint_state.get("status") == "solved":
            return [reply("puzzle.result", {"correct": True, "puzzle_id": puzzle_id, "already_solved": True}, message), self._state_message()]

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
        return [
            reply("puzzle.result", {"correct": True, "puzzle_id": puzzle_id, "attempts": self.state.puzzle_attempts[puzzle_id]}, message),
            reply("bot.message", puzzle.get("success_message", {}), message),
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
        hint_key = f"puzzle.{puzzle_id}"
        index = self.state.hints_used.get(hint_key, 0)
        if not hints:
            return [reply("error", {"message": "Nejsou dostupné žádné nápovědy."}, message)]
        charged = index < len(hints)
        hint = hints[min(index, len(hints) - 1)]
        responses = []
        if charged:
            penalty = int(hint.get("penalty", 10))
            self.state.score -= penalty
            self.state.hints_used[hint_key] = index + 1
            responses.append(reply("score.update", {"score": self.state.score, "penalty": penalty, "reason": "puzzle_hint"}, message))
        responses.extend([
            reply("bot.message", {"text": f"NÁPOVĚDA: {hint.get('text', '')}", "mood": "info", "channel": "general"}, message),
            self._state_message(),
        ])
        return responses

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

    async def _handle_unknown(self, message: Message) -> list[Message]:
        return [reply("error", {"message": f"Unsupported message type: {message.type}"}, message)]
