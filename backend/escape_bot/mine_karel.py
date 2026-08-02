from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

DIRECTIONS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def new_game(config: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    levels = _levels(config); active = list(config.get("active_level_ids", []))
    if not active or any(item not in levels for item in active): raise ValueError("Karel vyžaduje platné aktivní úrovně.")
    state = {"active_level_ids": active, "level_index": 0, "completed_levels": [], "awarded_points": 0,
             "total_moves": 0, "total_strikes": 0, "restarts": 0, "status": "playing"}
    _load_level(state, config, now or datetime.now(UTC)); return state


def public_game(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    remaining = max(0, int((datetime.fromisoformat(state["deadline_at"]) - current).total_seconds()))
    if remaining == 0 and state["status"] == "playing": state["status"] = "expired"
    mines = {_pos(item) for item in state["mines"]}; revealed = {_pos(item) for item in state["revealed"]}
    result = {key: deepcopy(value) for key, value in state.items() if key not in {"mines", "history"}}
    result["clues"] = {f"{r}:{c}": _adjacent((r, c), mines) for r, c in revealed if (r, c) not in mines}
    result.update({"remaining_seconds": remaining, "total_levels": len(state["active_level_ids"]),
                   "points_per_level": int(config.get("points_per_level", 40)),
                   "reserve_levels": max(0, len(config.get("levels", [])) - len(state["active_level_ids"]))})
    return result


def execute(state: dict[str, Any], config: dict[str, Any], commands: list[str], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    if state["status"] != "playing" or current >= datetime.fromisoformat(state["deadline_at"]):
        state["status"] = "expired"; raise ValueError("Čas navigace vypršel. Obnovte pole povelem RESET.")
    if not commands or len(commands) > 30 or any(item not in DIRECTIONS for item in commands): raise ValueError("Neplatná navigační sekvence.")
    mines = {_pos(item) for item in state["mines"]}; frames, score_delta, hit_mine, blocked = [], 0, False, False
    for command in commands:
        dr, dc = DIRECTIONS[command]; target = state["player"][0] + dr, state["player"][1] + dc
        if not (0 <= target[0] < state["rows"] and 0 <= target[1] < state["columns"]): blocked = True; break
        state["history"].append(list(state["player"])); state["moves"] += 1; state["total_moves"] += 1
        if target in mines:
            state["strikes"] += 1; state["total_strikes"] += 1; state["triggered_mines"].append(list(target)); state["player"] = list(state["start"])
            score_delta -= int(config.get("mine_penalty", 20)); hit_mine = True
        else:
            state["player"] = list(target)
            if list(target) not in state["revealed"]: state["revealed"].append(list(target))
        frames.append({"command": command, "player": list(state["player"]), "hit_mine": hit_mine})
        if hit_mine or state["player"] == state["exit"]: break
    level_complete = state["player"] == state["exit"]; game_complete = False; completed_level_id = None
    if level_complete:
        completed_level_id = state["level_id"]
        if completed_level_id not in state["completed_levels"]:
            state["completed_levels"].append(completed_level_id); score_delta += int(config.get("points_per_level", 40)); state["awarded_points"] += int(config.get("points_per_level", 40))
        if state["level_index"] + 1 >= len(state["active_level_ids"]): state["status"] = "complete"; game_complete = True
        else: state["level_index"] += 1; _load_level(state, config, current)
    return {"success": True, "frames": frames, "hit_mine": hit_mine, "blocked": blocked, "level_complete": level_complete,
            "completed_level_id": completed_level_id, "game_complete": game_complete, "score_delta": score_delta}


def reset(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> None:
    state["restarts"] += 1; _load_level(state, config, now or datetime.now(UTC))


def _load_level(state: dict[str, Any], config: dict[str, Any], now: datetime) -> None:
    level = _levels(config)[state["active_level_ids"][state["level_index"]]]
    state.update({"level_id": level["id"], "level_label": level.get("label", level["id"]), "rows": int(level["rows"]), "columns": int(level["columns"]),
                  "mines": deepcopy(level["mines"]), "start": deepcopy(level["start"]), "exit": deepcopy(level["exit"]), "player": deepcopy(level["start"]),
                  "revealed": deepcopy(level.get("revealed", [])) + [deepcopy(level["start"]), deepcopy(level["exit"])], "triggered_mines": [], "moves": 0, "strikes": 0,
                  "history": [], "status": "playing", "started_at": now.isoformat(),
                  "deadline_at": (now + timedelta(seconds=int(config.get("level_time_seconds", 180)))).isoformat()})


def _levels(config: dict[str, Any]) -> dict[str, dict[str, Any]]: return {str(item["id"]): item for item in config.get("levels", [])}
def _pos(value: Any) -> tuple[int, int]: return int(value[0]), int(value[1])
def _adjacent(position: tuple[int, int], mines: set[tuple[int, int]]) -> int:
    r, c = position; return sum((r + dr, c + dc) in mines for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)
