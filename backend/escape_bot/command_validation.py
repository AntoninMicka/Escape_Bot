from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any


class CommandValidationError(ValueError):
    """A public game command does not match its transport-independent contract."""


Validator = Callable[[Mapping[str, Any]], None]


def validate_game_command(command_type: str, payload: Mapping[str, Any]) -> None:
    validator = COMMAND_VALIDATORS.get(command_type)
    if validator is None:
        raise CommandValidationError(f"Unsupported game command: {command_type}")
    if not isinstance(payload, Mapping):
        raise CommandValidationError("Command payload must be an object.")
    validator(payload)


def _schema(
    required: Mapping[str, Callable[[Any, str], None]] | None = None,
    optional: Mapping[str, Callable[[Any, str], None]] | None = None,
) -> Validator:
    required_fields = dict(required or {})
    optional_fields = dict(optional or {})
    allowed = set(required_fields) | set(optional_fields)

    def validate(payload: Mapping[str, Any]) -> None:
        missing = [key for key in required_fields if key not in payload]
        if missing:
            raise CommandValidationError(f"Missing command field: {missing[0]}")
        unexpected = [key for key in payload if key not in allowed]
        if unexpected:
            raise CommandValidationError(f"Unexpected command field: {unexpected[0]}")
        for key, field_validator in required_fields.items():
            field_validator(payload[key], key)
        for key, field_validator in optional_fields.items():
            if key in payload:
                field_validator(payload[key], key)

    return validate


def _string(*, minimum: int = 1, maximum: int = 256) -> Callable[[Any, str], None]:
    def validate(value: Any, field: str) -> None:
        if not isinstance(value, str) or not (minimum <= len(value.strip()) <= maximum):
            raise CommandValidationError(
                f"Command field '{field}' must be a string with {minimum} to {maximum} characters."
            )

    return validate


def _integer(*, minimum: int = 0, maximum: int = 10_000) -> Callable[[Any, str], None]:
    def validate(value: Any, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not (minimum <= value <= maximum):
            raise CommandValidationError(
                f"Command field '{field}' must be an integer between {minimum} and {maximum}."
            )

    return validate


def _number(*, minimum: float, maximum: float) -> Callable[[Any, str], None]:
    def validate(value: Any, field: str) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not (minimum <= float(value) <= maximum)
        ):
            raise CommandValidationError(
                f"Command field '{field}' must be a finite number between {minimum} and {maximum}."
            )

    return validate


def _boolean(value: Any, field: str) -> None:
    if not isinstance(value, bool):
        raise CommandValidationError(f"Command field '{field}' must be a boolean.")


def _mapping(value: Any, field: str) -> None:
    if not isinstance(value, Mapping):
        raise CommandValidationError(f"Command field '{field}' must be an object.")


def _choice(*choices: str) -> Callable[[Any, str], None]:
    allowed = set(choices)

    def validate(value: Any, field: str) -> None:
        if not isinstance(value, str) or value not in allowed:
            raise CommandValidationError(
                f"Command field '{field}' must be one of: {', '.join(choices)}."
            )

    return validate


def _string_list(
    *,
    minimum: int = 1,
    maximum: int = 30,
    choices: set[str] | None = None,
) -> Callable[[Any, str], None]:
    def validate(value: Any, field: str) -> None:
        if not isinstance(value, list) or not (minimum <= len(value) <= maximum):
            raise CommandValidationError(
                f"Command field '{field}' must be a list with {minimum} to {maximum} items."
            )
        for item in value:
            if not isinstance(item, str) or not item.strip() or len(item) > 128:
                raise CommandValidationError(f"Command field '{field}' must contain non-empty strings.")
            if choices is not None and item not in choices:
                raise CommandValidationError(f"Command field '{field}' contains an unsupported value.")

    return validate


def _coordinate(value: Any, field: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) or not (0 <= item <= 1_000) for item in value)
    ):
        raise CommandValidationError(
            f"Command field '{field}' must contain two non-negative integer coordinates."
        )


IDENTIFIER = _string(maximum=128)
DIRECTIONS = {"up", "down", "left", "right"}

COMMAND_VALIDATORS: dict[str, Validator] = {
    "client.hello": _schema(optional={
        "session_id": IDENTIFIER,
        "demo_mode": _boolean,
        "client_id": IDENTIFIER,
        "client_name": _string(maximum=128),
        "protocol_version": _integer(minimum=1, maximum=100),
    }),
    "player.message": _schema(
        {"text": _string(maximum=500)},
        {"channel": _choice("general", "captain", "lost", "support")},
    ),
    "qr.detected": _schema({"value": _string(maximum=2_048)}),
    "geo.position": _schema(
        {
            "lat": _number(minimum=-90, maximum=90),
            "lon": _number(minimum=-180, maximum=180),
            "accuracy": _number(minimum=0, maximum=100_000),
        }
    ),
    "arg.verify": _schema(
        {"discovery_id": IDENTIFIER},
        {"evidence": _mapping},
    ),
    "camera.frame": _schema(
        {"mime_type": _choice("image/jpeg", "image/png", "image/webp"), "data": _string(maximum=7_000_000)}
    ),
    "room.unlock": _schema({"pin": _string(maximum=128)}),
    "room.hint": _schema({"room_id": IDENTIFIER}, {"hint_index": _integer(maximum=100)}),
    "cipher_tool.unlock": _schema({"tool_id": IDENTIFIER}),
    "puzzle.submit": _schema({"puzzle_id": IDENTIFIER, "answer": _string(maximum=2_000)}),
    "puzzle.hint": _schema({"puzzle_id": IDENTIFIER}, {"hint_index": _integer(maximum=100)}),
    "phase.hint": _schema({"phase_id": IDENTIFIER}, {"hint_index": _integer(maximum=100)}),
    "game.deadline_choice": _schema({"choice": _choice("end", "continue")}),
    "archive.arrange": _schema(
        {"puzzle_id": IDENTIFIER, "card_id": IDENTIFIER, "action": _choice("left", "right", "rotate", "swap")},
        {"target_id": IDENTIFIER},
    ),
    "line_game.move": _schema(
        {"puzzle_id": IDENTIFIER, "first": _coordinate, "second": _coordinate}
    ),
    "line_game.reset": _schema({"puzzle_id": IDENTIFIER}),
    "sokoban.command": _schema(
        {"puzzle_id": IDENTIFIER, "commands": _string_list(maximum=30, choices=DIRECTIONS)}
    ),
    "sokoban.undo": _schema({"puzzle_id": IDENTIFIER}),
    "sokoban.reset": _schema({"puzzle_id": IDENTIFIER}),
    "karel.command": _schema(
        {"puzzle_id": IDENTIFIER, "commands": _string_list(maximum=30, choices=DIRECTIONS)}
    ),
    "karel.reset": _schema({"puzzle_id": IDENTIFIER}),
    "triad.place": _schema(
        {
            "puzzle_id": IDENTIFIER,
            "row": _integer(maximum=1_000),
            "column": _integer(maximum=1_000),
            "symbol": IDENTIFIER,
        }
    ),
    "triad.reset": _schema({"puzzle_id": IDENTIFIER}),
    "finale.activate": _schema(
        {
            "puzzle_id": IDENTIFIER,
            "year": _string(maximum=32),
            "time": _string(maximum=32),
            "modules": _string_list(maximum=20),
        }
    ),
}
