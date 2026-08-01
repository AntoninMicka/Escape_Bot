from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any


def new_game(config: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    size = int(config.get("size", 7))
    colors = list(config.get("colors", []))
    if size < 5 or len(colors) != 5:
        raise ValueError("Swap game requires a board of at least 5×5 and exactly five colors.")
    started = now or datetime.now(UTC)
    state = {
        "progress": {str(length): 0 for length in config.get("objectives", {})},
        "status": "playing",
        "started_at": started.isoformat(),
        "deadline_at": (started + timedelta(seconds=int(config.get("time_limit_seconds", 300)))).isoformat(),
        "swaps": 0,
        "rng": int(config.get("seed", 5312026)) & 0x7FFFFFFF,
        "board": [["" for _ in range(size)] for _ in range(size)],
    }
    _refill(state, config, avoid_initial_matches=True)
    return state


def public_game(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    remaining = max(0, int((_parse_time(state["deadline_at"]) - current).total_seconds()))
    if remaining == 0 and state.get("status") == "playing":
        state["status"] = "expired"
    result = deepcopy(state)
    result.update({
        "size": int(config.get("size", 7)),
        "colors": list(config.get("colors", [])),
        "scoring_colors": list(config.get("scoring_colors", [])),
        "objectives": {str(length): int(required) for length, required in config.get("objectives", {}).items()},
        "time_limit_seconds": int(config.get("time_limit_seconds", 300)),
        "remaining_seconds": remaining,
    })
    return result


def swap(
    config: dict[str, Any],
    state: dict[str, Any],
    first: tuple[int, int],
    second: tuple[int, int],
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    if state.get("status") != "playing":
        raise ValueError("Kalibrace není aktivní; spusťte nový pokus.")
    if current >= _parse_time(state["deadline_at"]):
        state["status"] = "expired"
        raise ValueError("Časový limit vypršel.")
    size = int(config.get("size", 7))
    for row, column in (first, second):
        if not (0 <= row < size and 0 <= column < size):
            raise ValueError("Pole leží mimo herní mřížku.")
    if abs(first[0] - second[0]) + abs(first[1] - second[1]) != 1:
        raise ValueError("Prohodit lze pouze dvě sousední barvy.")

    board = state["board"]
    board[first[0]][first[1]], board[second[0]][second[1]] = (
        board[second[0]][second[1]], board[first[0]][first[1]],
    )
    runs = _find_runs(board)
    if not runs:
        board[first[0]][first[1]], board[second[0]][second[1]] = (
            board[second[0]][second[1]], board[first[0]][first[1]],
        )
        raise ValueError("Tato výměna nevytvoří žádnou řadu.")

    state["swaps"] += 1
    scored = {"3": 0, "4": 0, "5": 0}
    cascades = 0
    while runs and cascades < 20:
        cascades += 1
        clear_cells: set[tuple[int, int]] = set()
        for color, cells in runs:
            clear_cells.update(cells)
            if color in config.get("scoring_colors", []):
                length = "5" if len(cells) >= 5 else str(len(cells))
                if length in state["progress"]:
                    required = int(config["objectives"][length])
                    if state["progress"][length] < required:
                        state["progress"][length] += 1
                        scored[length] += 1
        for row, column in clear_cells:
            board[row][column] = ""
        _collapse(board)
        _refill(state, config)
        runs = _find_runs(board)

    complete = all(
        state["progress"].get(str(length), 0) >= int(required)
        for length, required in config.get("objectives", {}).items()
    )
    if complete:
        state["status"] = "complete"
    return {
        "scored": scored,
        "cascades": cascades,
        "game_complete": complete,
        "score_delta": completion_time_score(config, state, current) if complete else 0,
    }


def reset_game(config: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> None:
    state.clear()
    state.update(new_game(config, now))


def completion_time_score(
    config: dict[str, Any], state: dict[str, Any], now: datetime | None = None
) -> int:
    current = now or datetime.now(UTC)
    elapsed = max(0, int((current - _parse_time(state["started_at"])).total_seconds()))
    neutral = int(config.get("neutral_time_seconds", 180))
    interval = max(1, int(config.get("score_interval_seconds", 10)))
    points = max(0, int(config.get("score_points_per_interval", 5)))
    difference = neutral - elapsed
    if difference == 0:
        return 0
    magnitude = ceil(abs(difference) / interval) * points
    return magnitude if difference > 0 else -magnitude


def _find_runs(board: list[list[str]]) -> list[tuple[str, list[tuple[int, int]]]]:
    size = len(board)
    runs: list[tuple[str, list[tuple[int, int]]]] = []
    for row in range(size):
        _scan_line([(row, column) for column in range(size)], board, runs)
    for column in range(size):
        _scan_line([(row, column) for row in range(size)], board, runs)
    return runs


def _scan_line(
    coordinates: list[tuple[int, int]],
    board: list[list[str]],
    runs: list[tuple[str, list[tuple[int, int]]]],
) -> None:
    start = 0
    while start < len(coordinates):
        color = board[coordinates[start][0]][coordinates[start][1]]
        end = start + 1
        while end < len(coordinates) and board[coordinates[end][0]][coordinates[end][1]] == color:
            end += 1
        if color and end - start >= 3:
            runs.append((color, coordinates[start:end]))
        start = end


def _collapse(board: list[list[str]]) -> None:
    size = len(board)
    for column in range(size):
        values = [board[row][column] for row in range(size) if board[row][column]]
        empty = size - len(values)
        for row in range(size):
            board[row][column] = "" if row < empty else values[row - empty]


def _refill(state: dict[str, Any], config: dict[str, Any], avoid_initial_matches: bool = False) -> None:
    board = state["board"]
    colors = list(config["colors"])
    for row in range(len(board)):
        for column in range(len(board)):
            if board[row][column]:
                continue
            candidates = list(colors)
            if avoid_initial_matches:
                if column >= 2 and board[row][column - 1] == board[row][column - 2]:
                    candidates.remove(board[row][column - 1])
                if row >= 2 and board[row - 1][column] == board[row - 2][column]:
                    forbidden = board[row - 1][column]
                    if forbidden in candidates:
                        candidates.remove(forbidden)
            state["rng"] = (1103515245 * state["rng"] + 12345) & 0x7FFFFFFF
            board[row][column] = candidates[state["rng"] % len(candidates)]


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
