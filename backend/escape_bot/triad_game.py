from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

VECTORS = {"horizontal": (0, 1), "vertical": (1, 0), "diagonal": (1, 1), "anti_diagonal": (1, -1)}


def _lines(size: int) -> list[tuple[str, list[tuple[int, int]]]]:
    lines = []
    for orientation, (dr, dc) in VECTORS.items():
        for start_row in range(size):
            for start_column in range(size):
                cells = [(start_row + i * dr, start_column + i * dc) for i in range(3)]
                if all(0 <= row < size and 0 <= column < size for row, column in cells):
                    lines.append((orientation, cells))
    return lines


def _opponent_move(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    """Choose a deterministic blocking move, strongest immediate threat first."""
    symbols = set(config.get("symbols", ["cyan", "amber"]))
    completed = set(state["completed_orientations"])
    candidates: dict[tuple[int, int], int] = {}
    for orientation, cells in _lines(state["size"]):
        normalized = "diagonal" if orientation in {"diagonal", "anti_diagonal"} else orientation
        values = [state["board"][row][column] for row, column in cells]
        empty = [(row, column) for (row, column), value in zip(cells, values) if value is None and [row, column] not in state["blocked"]]
        player_values = [value for value in values if value in symbols]
        if not empty or any(value == "opponent" for value in values):
            continue
        same_pair = len(player_values) == 2 and player_values[0] == player_values[1]
        for cell in empty:
            # An immediate uncompleted objective is vastly more important than general coverage.
            score = (1000 if same_pair and normalized not in completed else 0) + len(player_values) * 20
            score += 8 if normalized not in completed else 1
            candidates[cell] = candidates.get(cell, 0) + score
    available = [(row, column) for row in range(state["size"]) for column in range(state["size"])
                 if state["board"][row][column] is None and [row, column] not in state["blocked"]]
    if not available:
        return None
    center = (state["size"] - 1) / 2
    row, column = max(available, key=lambda cell: (
        candidates.get(cell, 0),
        -(abs(cell[0] - center) + abs(cell[1] - center)),
        -cell[0], -cell[1],
    ))
    state["board"][row][column] = "opponent"
    state["opponent_moves"] = int(state.get("opponent_moves", 0)) + 1
    return {"row": row, "column": column, "symbol": "opponent"}


def new_game(config: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC); size = int(config.get("size", 5))
    return {"size": size, "board": [[None for _ in range(size)] for _ in range(size)], "blocked": deepcopy(config.get("blocked", [])),
            "completed_orientations": [], "scored_lines": [], "placements": 0, "opponent_moves": 0, "restarts": 0, "status": "playing",
            "started_at": current.isoformat(), "deadline_at": (current + timedelta(seconds=int(config.get("time_limit_seconds", 180)))).isoformat()}


def public_game(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC); remaining = max(0, int((datetime.fromisoformat(state["deadline_at"]) - current).total_seconds()))
    if remaining == 0 and state["status"] == "playing": state["status"] = "expired"
    # Scenario layout changes also apply to already persisted games.
    state["blocked"] = deepcopy(config.get("blocked", []))
    result = deepcopy(state); result.update({"remaining_seconds": remaining, "symbols": list(config.get("symbols", ["cyan", "amber"])),
                                             "required_orientations": ["horizontal", "vertical", "diagonal"],
                                             "required_orientation_count": int(config.get("required_orientation_count", 3))})
    return result


def place(state: dict[str, Any], config: dict[str, Any], row: int, column: int, symbol: str, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    if state["status"] != "playing" or current >= datetime.fromisoformat(state["deadline_at"]): state["status"] = "expired"; raise ValueError("Čas stabilizace vypršel. Spusťte nové pole.")
    if symbol not in config.get("symbols", ["cyan", "amber"]): raise ValueError("Neplatný typ uzlu.")
    if not (0 <= row < state["size"] and 0 <= column < state["size"]): raise ValueError("Pole leží mimo mřížku.")
    if [row, column] in state["blocked"] or state["board"][row][column] is not None: raise ValueError("Toto pole nelze obsadit.")
    state["board"][row][column] = symbol; state["placements"] += 1
    new_lines = []
    for orientation, cells in _lines(state["size"]):
        key = [f"{r}:{c}" for r, c in cells]
        if key in state["scored_lines"]: continue
        if all(state["board"][r][c] == symbol for r, c in cells):
            state["scored_lines"].append(key); new_lines.append({"orientation": orientation, "cells": key, "symbol": symbol})
            normalized = "diagonal" if orientation in {"diagonal", "anti_diagonal"} else orientation
            if normalized not in state["completed_orientations"]: state["completed_orientations"].append(normalized)
    required_count = int(config.get("required_orientation_count", 3))
    complete = len(set(state["completed_orientations"]) & {"horizontal", "vertical", "diagonal"}) >= required_count
    if complete: state["status"] = "complete"
    opponent_move = None if complete else _opponent_move(state, config)
    return {"success": True, "row": row, "column": column, "symbol": symbol,
            "new_lines": new_lines, "opponent_move": opponent_move, "game_complete": complete}


def reset(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> None:
    restarts = int(state.get("restarts", 0)) + 1; state.clear(); state.update(new_game(config, now)); state["restarts"] = restarts
