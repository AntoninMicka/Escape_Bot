from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any


DIRECTIONS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
COMMAND_NAMES = {
    "NAHORU": "up", "HORE": "up", "N": "up",
    "DOLU": "down", "D": "down", "J": "down",
    "VLEVO": "left", "LEVA": "left", "L": "left", "Z": "left",
    "VPRAVO": "right", "PRAVA": "right", "P": "right", "V": "right",
}


def new_game(config: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    levels = _levels_by_id(config)
    active_ids = list(config.get("active_level_ids", []))
    if not active_ids or any(level_id not in levels for level_id in active_ids):
        raise ValueError("Sokoban requires valid active_level_ids.")
    state: dict[str, Any] = {
        "active_level_ids": active_ids,
        "level_index": 0,
        "completed_levels": [],
        "awarded_points": 0,
        "moves": 0,
        "pushes": 0,
        "total_moves": 0,
        "total_pushes": 0,
        "restarts": 0,
        "status": "playing",
        "command_history": [],
    }
    _load_level(state, config, now or datetime.now(UTC))
    return state


def public_game(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    remaining = max(0, int((_parse_time(state["deadline_at"]) - current).total_seconds()))
    if remaining == 0 and state.get("status") == "playing":
        state["status"] = "expired"
    result = deepcopy(state)
    result.pop("history", None)
    result.update({
        "remaining_seconds": remaining,
        "level_time_seconds": int(config.get("level_time_seconds", 120)),
        "points_per_level": int(config.get("points_per_level", 30)),
        "total_levels": len(state["active_level_ids"]),
        "reserve_levels": max(0, len(config.get("levels", [])) - len(state["active_level_ids"])),
    })
    return result


def execute(
    state: dict[str, Any], config: dict[str, Any], commands: list[str],
    max_commands: int = 30, now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    if state.get("status") == "expired":
        raise ValueError("Čas této úrovně vypršel. Obnovte ji povelem RESET.")
    if state.get("status") != "playing":
        raise ValueError("Energetická mřížka už je stabilizovaná.")
    if current >= _parse_time(state["deadline_at"]):
        state["status"] = "expired"
        raise ValueError("Čas této úrovně vypršel. Obnovte ji povelem RESET.")
    if not commands or len(commands) > max_commands:
        raise ValueError(f"Sekvence musí obsahovat 1 až {max_commands} pohybů.")
    if any(command not in DIRECTIONS for command in commands):
        raise ValueError("Sekvence obsahuje neznámý pohyb.")

    executed = 0
    blocked = False
    pushed = 0
    for command in commands:
        snapshot = {
            "player": list(state["player"]),
            "boxes": deepcopy(state["boxes"]),
            "moves": state["moves"],
            "pushes": state["pushes"],
            "total_moves": state["total_moves"],
            "total_pushes": state["total_pushes"],
        }
        moved, did_push = _move(state, command)
        if not moved:
            blocked = True
            break
        state["history"].append(snapshot)
        state["history"] = state["history"][-200:]
        state["moves"] += 1
        state["pushes"] += int(did_push)
        state["total_moves"] += 1
        state["total_pushes"] += int(did_push)
        executed += 1
        pushed += int(did_push)
        if _is_complete(state):
            break

    level_complete = _is_complete(state)
    game_complete = False
    score_delta = 0
    completed_level_id: str | None = None
    if level_complete:
        completed_level_id = state["level_id"]
        if completed_level_id not in state["completed_levels"]:
            state["completed_levels"].append(completed_level_id)
            score_delta = int(config.get("points_per_level", 30))
            state["awarded_points"] += score_delta
        if state["level_index"] + 1 >= len(state["active_level_ids"]):
            state["status"] = "complete"
            game_complete = True
        else:
            state["level_index"] += 1
            _load_level(state, config, current)

    state["command_history"].append({"commands": list(commands), "executed": executed, "blocked": blocked})
    state["command_history"] = state["command_history"][-100:]
    return {
        "executed": executed,
        "requested": len(commands),
        "blocked": blocked,
        "pushes": pushed,
        "level_complete": level_complete,
        "completed_level_id": completed_level_id,
        "score_delta": score_delta,
        "game_complete": game_complete,
    }


def undo(state: dict[str, Any]) -> bool:
    if state.get("status") != "playing" or not state.get("history"):
        return False
    snapshot = state["history"].pop()
    state["player"] = snapshot["player"]
    state["boxes"] = snapshot["boxes"]
    state["moves"] = snapshot["moves"]
    state["pushes"] = snapshot["pushes"]
    state["total_moves"] = snapshot["total_moves"]
    state["total_pushes"] = snapshot["total_pushes"]
    return True


def reset_level(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> None:
    if state.get("status") == "complete":
        raise ValueError("Všechny úrovně už byly dokončeny.")
    state["status"] = "playing"
    state["restarts"] = int(state.get("restarts", 0)) + 1
    _load_level(state, config, now or datetime.now(UTC))


def parse_commands(text: str, max_commands: int = 30) -> list[str] | None:
    normalized = _normalize(text)
    if normalized in {"ZPET", "UNDO", "KROK ZPET"}:
        return ["undo"]
    if normalized in {"RESET", "RESTART", "ZNOVU", "OBNOVIT"}:
        return ["reset"]
    parts = [part.strip() for part in re.split(r"[,;]+", normalized) if part.strip()]
    if not parts:
        return None
    commands: list[str] = []
    for part in parts:
        match = re.fullmatch(r"(?:(\d+)\s*[X×]?\s*)?([A-Z]+)(?:\s+(\d+)\s*[X×]?)?", part)
        if not match:
            return None
        name = COMMAND_NAMES.get(match.group(2))
        if name is None:
            return None
        count = int(match.group(1) or match.group(3) or 1)
        if count < 1 or len(commands) + count > max_commands:
            raise ValueError(f"Sekvence může obsahovat nejvýše {max_commands} pohybů.")
        commands.extend([name] * count)
    return commands


def _levels_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    levels = {str(level.get("id", "")): level for level in config.get("levels", [])}
    if "" in levels or len(levels) != len(config.get("levels", [])):
        raise ValueError("Every Sokoban level requires a unique id.")
    return levels


def _load_level(state: dict[str, Any], config: dict[str, Any], now: datetime) -> None:
    level_id = state["active_level_ids"][state["level_index"]]
    level = _levels_by_id(config)[level_id]
    parsed = _parse_map(level.get("map", []))
    state.update(parsed)
    state["level_id"] = level_id
    state["level_label"] = str(level.get("label", level_id))
    state["moves"] = 0
    state["pushes"] = 0
    state["history"] = []
    state["started_at"] = now.isoformat()
    state["deadline_at"] = (now + timedelta(seconds=int(config.get("level_time_seconds", 120)))).isoformat()


def _parse_map(rows: list[str]) -> dict[str, Any]:
    if not rows or len({len(row) for row in rows}) != 1:
        raise ValueError("Sokoban map must be a non-empty rectangle.")
    walls: list[list[int]] = []
    targets: list[list[int]] = []
    boxes: list[list[int]] = []
    player: list[int] | None = None
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row):
            position = [row_index, column_index]
            if cell == "#": walls.append(position)
            elif cell in ".+*": targets.append(position)
            if cell in "$*": boxes.append(position)
            if cell in "@+":
                if player is not None: raise ValueError("Sokoban map contains multiple players.")
                player = position
    if player is None or not boxes or len(boxes) != len(targets):
        raise ValueError("Sokoban map requires one player and the same number of boxes and targets.")
    return {"player": player, "boxes": boxes, "walls": walls, "targets": targets, "rows": len(rows), "columns": len(rows[0])}


def _move(state: dict[str, Any], command: str) -> tuple[bool, bool]:
    row_step, column_step = DIRECTIONS[command]
    player = tuple(state["player"])
    destination = (player[0] + row_step, player[1] + column_step)
    walls = {tuple(position) for position in state["walls"]}
    boxes = {tuple(position) for position in state["boxes"]}
    if destination in walls: return False, False
    pushed = destination in boxes
    if pushed:
        box_destination = (destination[0] + row_step, destination[1] + column_step)
        if box_destination in walls or box_destination in boxes: return False, False
        boxes.remove(destination)
        boxes.add(box_destination)
        state["boxes"] = [list(position) for position in sorted(boxes)]
    state["player"] = [destination[0], destination[1]]
    return True, pushed


def _is_complete(state: dict[str, Any]) -> bool:
    return {tuple(position) for position in state["boxes"]} == {tuple(position) for position in state["targets"]}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip().upper())
    return " ".join("".join(character for character in decomposed if not unicodedata.combining(character)).split())
