from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping

from .game_engine import ActorContext, ENGINE_SNAPSHOT_VERSION, GameCommand, GameEngine
from .protocol import Message
from .state_machine import EscapeBotStateMachine


PERSISTED_ENGINE_KEY = "_game_engine"


@dataclass(slots=True)
class GameSessionAdapter:
    """Connect the deterministic engine to the mutable FastAPI session registry."""

    operation_receipts: dict[str, Any] = field(default_factory=dict)
    _command_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @classmethod
    def restore(
        cls,
        machine: EscapeBotStateMachine,
        persisted: Mapping[str, Any],
    ) -> "GameSessionAdapter":
        state, receipts = _split_persisted_snapshot(persisted)
        machine.restore_state(state)
        return cls(operation_receipts=receipts)

    def snapshot(self, machine: EscapeBotStateMachine) -> dict[str, Any]:
        """Keep the legacy state shape so an older server can still restore it."""
        state = machine.state.snapshot()
        state[PERSISTED_ENGINE_KEY] = {
            "schema_version": ENGINE_SNAPSHOT_VERSION,
            "operation_receipts": deepcopy(self.operation_receipts),
        }
        return state

    async def apply(
        self,
        machine: EscapeBotStateMachine,
        message: Message,
        *,
        now: datetime | None = None,
    ) -> list[Message]:
        async with self._command_lock:
            return await self._apply_locked(machine, message, now=now)

    async def _apply_locked(
        self,
        machine: EscapeBotStateMachine,
        message: Message,
        *,
        now: datetime | None,
    ) -> list[Message]:
        actor = _actor_context(machine, message.payload)
        envelope = {
            "schema_version": ENGINE_SNAPSHOT_VERSION,
            "state": machine.state.snapshot(),
            "operation_receipts": deepcopy(self.operation_receipts),
        }
        result = await GameEngine(machine.scenario).apply(
            envelope,
            GameCommand(
                message.type,
                message.payload,
                request_id=message.request_id,
                operation_id=message.operation_id,
            ),
            actor,
            now or datetime.now(UTC),
        )
        machine.restore_state(result.snapshot["state"], migrate_legacy=False)
        machine._current_player_id = actor.client_id
        machine._participant_ids = list(actor.participant_ids)
        machine._team_mode = actor.team_mode
        machine._participant_names = dict(actor.participant_names)
        self.operation_receipts = deepcopy(result.snapshot["operation_receipts"])
        return list(result.responses)


def _split_persisted_snapshot(
    persisted: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if persisted.get("schema_version") == ENGINE_SNAPSHOT_VERSION and isinstance(
        persisted.get("state"), Mapping
    ):
        receipts = persisted.get("operation_receipts", {})
        if not isinstance(receipts, Mapping):
            raise ValueError("Invalid operation receipts in engine snapshot.")
        return deepcopy(dict(persisted["state"])), deepcopy(dict(receipts))

    state = deepcopy(dict(persisted))
    metadata = state.pop(PERSISTED_ENGINE_KEY, {})
    if not metadata:
        return state, {}
    if not isinstance(metadata, Mapping) or metadata.get("schema_version") != ENGINE_SNAPSHOT_VERSION:
        raise ValueError("Unsupported persisted game engine metadata.")
    receipts = metadata.get("operation_receipts", {})
    if not isinstance(receipts, Mapping):
        raise ValueError("Invalid persisted operation receipts.")
    return state, deepcopy(dict(receipts))


def _actor_context(machine: EscapeBotStateMachine, payload: Mapping[str, Any]) -> ActorContext:
    client_id = str(payload.get("_client_id", machine._current_player_id)) or "legacy-client"
    raw_participants = payload.get("_participant_ids", machine._participant_ids)
    participants = (
        tuple(str(item) for item in raw_participants if str(item))
        if isinstance(raw_participants, (list, tuple))
        else (client_id,)
    )
    raw_names = payload.get("_participant_names", machine._participant_names)
    names = (
        {str(key): str(value) for key, value in raw_names.items()}
        if isinstance(raw_names, Mapping)
        else {}
    )
    return ActorContext(
        client_id=client_id,
        participant_ids=participants or (client_id,),
        team_mode=str(payload.get("_team_mode", machine._team_mode)),
        participant_names=names,
    )
