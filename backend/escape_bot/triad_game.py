from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

VECTORS = {"horizontal": (0, 1), "vertical": (1, 0), "diagonal": (1, 1), "anti_diagonal": (1, -1)}


def new_game(config: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC); size = int(config.get("size", 5))
    return {"size": size, "board": [[None for _ in range(size)] for _ in range(size)], "blocked": deepcopy(config.get("blocked", [])),
            "completed_orientations": [], "scored_lines": [], "placements": 0, "restarts": 0, "status": "playing",
            "started_at": current.isoformat(), "deadline_at": (current + timedelta(seconds=int(config.get("time_limit_seconds", 180)))).isoformat()}


def public_game(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC); remaining = max(0, int((datetime.fromisoformat(state["deadline_at"]) - current).total_seconds()))
    if remaining == 0 and state["status"] == "playing": state["status"] = "expired"
    result = deepcopy(state); result.update({"remaining_seconds": remaining, "symbols": list(config.get("symbols", ["cyan", "amber"])), "required_orientations": ["horizontal", "vertical", "diagonal"]})
    return result


def place(state: dict[str, Any], config: dict[str, Any], row: int, column: int, symbol: str, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    if state["status"] != "playing" or current >= datetime.fromisoformat(state["deadline_at"]): state["status"] = "expired"; raise ValueError("Čas stabilizace vypršel. Spusťte nové pole.")
    if symbol not in config.get("symbols", ["cyan", "amber"]): raise ValueError("Neplatný typ uzlu.")
    if not (0 <= row < state["size"] and 0 <= column < state["size"]): raise ValueError("Pole leží mimo mřížku.")
    if [row, column] in state["blocked"] or state["board"][row][column] is not None: raise ValueError("Toto pole nelze obsadit.")
    state["board"][row][column] = symbol; state["placements"] += 1
    new_lines = []
    for orientation, (dr, dc) in VECTORS.items():
        for start_row in range(state["size"]):
            for start_column in range(state["size"]):
                cells = [(start_row + i * dr, start_column + i * dc) for i in range(3)]
                if any(not (0 <= r < state["size"] and 0 <= c < state["size"]) for r, c in cells): continue
                key = [f"{r}:{c}" for r, c in cells]
                if key in state["scored_lines"]: continue
                if all(state["board"][r][c] == symbol for r, c in cells):
                    state["scored_lines"].append(key); new_lines.append({"orientation": orientation, "cells": key, "symbol": symbol})
                    normalized = "diagonal" if orientation in {"diagonal", "anti_diagonal"} else orientation
                    if normalized not in state["completed_orientations"]: state["completed_orientations"].append(normalized)
    complete = all(item in state["completed_orientations"] for item in ("horizontal", "vertical", "diagonal"))
    if complete: state["status"] = "complete"
    return {"success": True, "new_lines": new_lines, "game_complete": complete}


def reset(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> None:
    restarts = int(state.get("restarts", 0)) + 1; state.clear(); state.update(new_game(config, now)); state["restarts"] = restarts
