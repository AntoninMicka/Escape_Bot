from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any


DIRECTIONS = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}
COMMAND_NAMES = {
    "NAHORU": "up", "HORE": "up", "N": "up",
    "DOLU": "down", "D": "down", "J": "down",
    "VLEVO": "left", "LEVA": "left", "L": "left", "Z": "left",
    "VPRAVO": "right", "PRAVA": "right", "P": "right", "V": "right",
}


def new_game(config: dict[str, Any]) -> dict[str, Any]:
    rows = list(config.get("map", []))
    if not rows or len({len(row) for row in rows}) != 1:
        raise ValueError("Sokoban map must be a non-empty rectangle.")
    walls: list[list[int]] = []
    targets: list[list[int]] = []
    boxes: list[list[int]] = []
    player: list[int] | None = None
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row):
            position = [row_index, column_index]
            if cell == "#":
                walls.append(position)
            elif cell in ".+*":
                targets.append(position)
            if cell in "$*":
                boxes.append(position)
            if cell in "@+":
                if player is not None:
                    raise ValueError("Sokoban map contains multiple players.")
                player = position
    if player is None or not boxes or len(boxes) != len(targets):
        raise ValueError("Sokoban map requires one player and the same number of boxes and targets.")
    return {
        "player": player,
        "boxes": boxes,
        "walls": walls,
        "targets": targets,
        "rows": len(rows),
        "columns": len(rows[0]),
        "moves": 0,
        "pushes": 0,
        "restarts": 0,
        "status": "playing",
        "history": [],
        "command_history": [],
    }


def public_game(state: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(state)
    result.pop("history", None)
    return result


def execute(state: dict[str, Any], commands: list[str], max_commands: int = 30) -> dict[str, Any]:
    if state.get("status") != "playing":
        raise ValueError("Energetická mřížka už je stabilizovaná.")
    if not commands or len(commands) > max_commands:
        raise ValueError(f"Sekvence musí obsahovat 1 až {max_commands} pohybů.")
    if any(command not in DIRECTIONS for command in commands):
        raise ValueError("Sekvence obsahuje neznámý pohyb.")

    executed = 0
    blocked = False
    pushed = 0
    for command in commands:
        snapshot = {"player": list(state["player"]), "boxes": deepcopy(state["boxes"])}
        moved, did_push = _move(state, command)
        if not moved:
            blocked = True
            break
        state["history"].append(snapshot)
        state["history"] = state["history"][-200:]
        state["moves"] += 1
        state["pushes"] += int(did_push)
        executed += 1
        pushed += int(did_push)
        if _is_complete(state):
            state["status"] = "complete"
            break
    state["command_history"].append({"commands": list(commands), "executed": executed, "blocked": blocked})
    state["command_history"] = state["command_history"][-100:]
    return {
        "executed": executed,
        "requested": len(commands),
        "blocked": blocked,
        "pushes": pushed,
        "game_complete": state["status"] == "complete",
    }


def undo(state: dict[str, Any]) -> bool:
    if not state.get("history"):
        return False
    snapshot = state["history"].pop()
    state["player"] = snapshot["player"]
    state["boxes"] = snapshot["boxes"]
    state["moves"] = max(0, int(state["moves"]) - 1)
    state["status"] = "playing"
    return True


def reset_game(config: dict[str, Any], state: dict[str, Any]) -> None:
    restarts = int(state.get("restarts", 0)) + 1
    state.clear()
    state.update(new_game(config))
    state["restarts"] = restarts


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


def _move(state: dict[str, Any], command: str) -> tuple[bool, bool]:
    row_step, column_step = DIRECTIONS[command]
    player = tuple(state["player"])
    destination = (player[0] + row_step, player[1] + column_step)
    walls = {tuple(position) for position in state["walls"]}
    boxes = {tuple(position) for position in state["boxes"]}
    if destination in walls:
        return False, False
    pushed = destination in boxes
    if pushed:
        box_destination = (destination[0] + row_step, destination[1] + column_step)
        if box_destination in walls or box_destination in boxes:
            return False, False
        boxes.remove(destination)
        boxes.add(box_destination)
        state["boxes"] = [list(position) for position in sorted(boxes)]
    state["player"] = [destination[0], destination[1]]
    return True, pushed


def _is_complete(state: dict[str, Any]) -> bool:
    return {tuple(position) for position in state["boxes"]} == {tuple(position) for position in state["targets"]}


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip().upper())
    return " ".join("".join(character for character in decomposed if not unicodedata.combining(character)).split())
