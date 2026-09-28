from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping

from .command_validation import validate_game_command
from .protocol import Message
from .scenario import Scenario
from .state_machine import EscapeBotStateMachine


ENGINE_SNAPSHOT_VERSION = 1
MAX_OPERATION_RECEIPTS = 500


@dataclass(frozen=True, slots=True)
class ActorContext:
    client_id: str
    participant_ids: tuple[str, ...] = ()
    team_mode: str = "solo"
    participant_names: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GameCommand:
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    operation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.type.strip():
            raise ValueError("Command type must be a non-empty string.")
        if self.operation_id is not None and not (1 <= len(self.operation_id) <= 128):
            raise ValueError("operation_id must contain 1 to 128 characters.")


@dataclass(frozen=True, slots=True)
class ApplyResult:
    snapshot: dict[str, Any]
    responses: tuple[Message, ...]
    audit_events: tuple[dict[str, Any], ...]
    next_deadline_at: str | None
    operation_id: str | None
    replayed: bool = False


class GameEngine:
    """Transport-independent application boundary around the current game rules."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    async def apply(
        self,
        snapshot: Mapping[str, Any] | None,
        command: GameCommand,
        actor: ActorContext,
        now: datetime,
    ) -> ApplyResult:
        command_time = _as_utc(now)
        state_data, receipts = _restore_envelope(snapshot)
        if command.operation_id and command.operation_id in receipts:
            receipt = receipts[command.operation_id]
            return ApplyResult(
                snapshot=deepcopy(dict(snapshot or {})),
                responses=tuple(Message.from_json(item) for item in receipt.get("responses", [])),
                audit_events=tuple(deepcopy(receipt.get("audit_events", []))),
                next_deadline_at=receipt.get("next_deadline_at"),
                operation_id=command.operation_id,
                replayed=True,
            )

        validate_game_command(command.type, command.payload)

        machine = EscapeBotStateMachine(self.scenario, clock=lambda: command_time)
        if state_data:
            machine.restore_state(deepcopy(state_data), migrate_legacy=False)
        history_before = deepcopy(machine.state.event_history)
        payload = deepcopy(dict(command.payload))
        payload.update({
            "_client_id": actor.client_id,
            "_participant_ids": list(actor.participant_ids or (actor.client_id,)),
            "_team_mode": actor.team_mode,
            "_participant_names": dict(actor.participant_names),
        })
        raw_responses = tuple(
            await machine.handle(
                Message(command.type, payload, command.request_id),
                now=command_time,
            )
        )
        responses = tuple(
            Message(
                response.type,
                response.payload,
                response.request_id,
                response.operation_id or command.operation_id,
            )
            for response in raw_responses
        )
        state = machine.state.snapshot()
        audit_events = tuple(_new_suffix(history_before, machine.state.event_history))
        next_deadline = _next_deadline(state, command_time)

        updated_receipts = deepcopy(receipts)
        if command.operation_id:
            updated_receipts[command.operation_id] = {
                "responses": [message.to_json() for message in responses],
                "audit_events": deepcopy(list(audit_events)),
                "next_deadline_at": next_deadline,
                "applied_at": command_time.isoformat(),
            }
            while len(updated_receipts) > MAX_OPERATION_RECEIPTS:
                del updated_receipts[next(iter(updated_receipts))]

        updated_snapshot = {
            "schema_version": ENGINE_SNAPSHOT_VERSION,
            "state": state,
            "operation_receipts": updated_receipts,
        }
        return ApplyResult(
            snapshot=updated_snapshot,
            responses=responses,
            audit_events=audit_events,
            next_deadline_at=next_deadline,
            operation_id=command.operation_id,
        )


def _restore_envelope(snapshot: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if not snapshot:
        return {}, {}
    if "schema_version" not in snapshot:
        # Temporary compatibility with existing raw GameState snapshots.
        return deepcopy(dict(snapshot)), {}
    version = snapshot.get("schema_version")
    if version != ENGINE_SNAPSHOT_VERSION:
        raise ValueError(f"Unsupported game snapshot schema version: {version!r}.")
    state = snapshot.get("state")
    receipts = snapshot.get("operation_receipts", {})
    if not isinstance(state, Mapping) or not isinstance(receipts, Mapping):
        raise ValueError("Invalid game snapshot envelope.")
    return deepcopy(dict(state)), deepcopy(dict(receipts))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _new_suffix(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    maximum = min(len(before), len(after))
    overlap = next(
        (
            size
            for size in range(maximum, -1, -1)
            if size == 0 or before[-size:] == after[:size]
        ),
        0,
    )
    return deepcopy(after[overlap:])


def _next_deadline(state: Mapping[str, Any], now: datetime) -> str | None:
    candidates: list[datetime] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key == "deadline_at":
                    try:
                        parsed = datetime.fromisoformat(str(child))
                        parsed = _as_utc(parsed)
                        if parsed > now:
                            candidates.append(parsed)
                    except (TypeError, ValueError):
                        pass
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(state)
    return min(candidates).isoformat() if candidates else None
