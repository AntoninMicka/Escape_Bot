from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

DIRECTIONS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def new_game(config: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    rows, columns = int(config["rows"]), int(config["columns"])
    mines = {_position(item) for item in config.get("mines", [])}
    start, exit_position = _position(config["start"]), _position(config["exit"])
    if start in mines or exit_position in mines:
        raise ValueError("Start ani východ nesmí obsahovat minu.")
    revealed = {_position(item) for item in config.get("revealed", [])} | {start, exit_position}
    current = now or datetime.now(UTC)
    return {
        "rows": rows, "columns": columns, "mines": [list(item) for item in sorted(mines)],
        "start": list(start), "exit": list(exit_position), "player": list(start),
        "revealed": [list(item) for item in sorted(revealed)], "triggered_mines": [],
        "moves": 0, "strikes": 0, "status": "playing", "history": [],
        "started_at": current.isoformat(),
        "deadline_at": (current + timedelta(seconds=int(config.get("time_limit_seconds", 240)))).isoformat(),
    }


def public_game(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    remaining = max(0, int((datetime.fromisoformat(state["deadline_at"]) - current).total_seconds()))
    if remaining == 0 and state["status"] == "playing": state["status"] = "expired"
    mines = {_position(item) for item in state["mines"]}
    revealed = {_position(item) for item in state["revealed"]}
    result = {key: deepcopy(value) for key, value in state.items() if key not in {"mines", "history"}}
    result["clues"] = {f"{r}:{c}": _adjacent_mines((r, c), mines) for r, c in revealed if (r, c) not in mines}
    result["remaining_seconds"] = remaining
    return result


def execute(state: dict[str, Any], config: dict[str, Any], commands: list[str], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    if state["status"] != "playing" or current >= datetime.fromisoformat(state["deadline_at"]):
        state["status"] = "expired"
        raise ValueError("Čas navigace vypršel. Obnovte pole povelem RESET.")
    if not commands or len(commands) > 30 or any(item not in DIRECTIONS for item in commands):
        raise ValueError("Neplatná navigační sekvence.")
    mines = {_position(item) for item in state["mines"]}
    frames, score_delta, hit_mine, blocked = [], 0, False, False
    for command in commands:
        dr, dc = DIRECTIONS[command]
        target = (state["player"][0] + dr, state["player"][1] + dc)
        if not (0 <= target[0] < state["rows"] and 0 <= target[1] < state["columns"]):
            blocked = True; break
        state["history"].append(list(state["player"]))
        state["moves"] += 1
        if target in mines:
            state["strikes"] += 1
            state["triggered_mines"].append(list(target))
            state["player"] = list(state["start"])
            score_delta -= int(config.get("mine_penalty", 20))
            hit_mine = True
        else:
            state["player"] = list(target)
            if list(target) not in state["revealed"]: state["revealed"].append(list(target))
        frames.append({"command": command, "player": list(state["player"]), "hit_mine": hit_mine})
        if hit_mine or state["player"] == state["exit"]: break
    complete = state["player"] == state["exit"]
    if complete:
        state["status"] = "complete"
        score_delta += int(config.get("completion_bonus", 50))
    return {"success": True, "frames": frames, "hit_mine": hit_mine, "blocked": blocked,
            "game_complete": complete, "score_delta": score_delta}


def reset(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> None:
    strikes = int(state.get("strikes", 0))
    state.clear(); state.update(new_game(config, now)); state["strikes"] = strikes


def _position(value: Any) -> tuple[int, int]: return int(value[0]), int(value[1])


def _adjacent_mines(position: tuple[int, int], mines: set[tuple[int, int]]) -> int:
    r, c = position
    return sum((r + dr, c + dc) in mines for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)
