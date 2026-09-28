import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from escape_bot.game_engine import ActorContext, GameCommand, GameEngine
from escape_bot.protocol import Message
from escape_bot.scenario import ScenarioLoader
from escape_bot.state_machine import EscapeBotStateMachine


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


class GameEngineBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = GameEngine(ScenarioLoader.load(str(SCENARIO_PATH)))
        self.actor = ActorContext(
            client_id="alice",
            participant_ids=("alice", "bob"),
            team_mode="team",
            participant_names={"alice": "Alice", "bob": "Bob"},
        )
        self.now = datetime(2026, 9, 28, 12, 30, tzinfo=UTC)

    async def test_apply_uses_authoritative_time_and_returns_versioned_snapshot(self) -> None:
        result = await self.engine.apply(
            None,
            GameCommand("player.message", {"text": "Příjem"}, operation_id="message-1"),
            self.actor,
            self.now,
        )

        self.assertEqual(result.snapshot["schema_version"], 1)
        self.assertEqual(result.snapshot["state"]["last_activity_at"], self.now.isoformat())
        self.assertEqual(result.audit_events[0]["at"], self.now.isoformat())
        self.assertEqual(result.audit_events[0]["type"], "player.message")
        self.assertFalse(result.replayed)

    async def test_operation_retry_returns_original_receipt_without_duplicate_mutation(self) -> None:
        command = GameCommand("player.message", {"text": "Jednou"}, operation_id="stable-operation")
        first = await self.engine.apply(None, command, self.actor, self.now)
        retried = await self.engine.apply(
            first.snapshot,
            GameCommand("player.message", {"text": "Podruhé"}, operation_id="stable-operation"),
            self.actor,
            self.now + timedelta(minutes=5),
        )

        self.assertTrue(retried.replayed)
        self.assertEqual(retried.snapshot, first.snapshot)
        self.assertEqual(retried.responses, first.responses)
        self.assertEqual(
            [item["text"] for item in retried.snapshot["state"]["chat_history"] if item["role"] == "player"],
            ["Jednou"],
        )

    async def test_raw_legacy_snapshot_is_accepted_and_upgraded(self) -> None:
        legacy = {"score": 725, "phase": "navigating"}
        result = await self.engine.apply(
            legacy,
            GameCommand("client.hello"),
            self.actor,
            self.now,
        )

        self.assertEqual(result.snapshot["schema_version"], 1)
        self.assertEqual(result.snapshot["state"]["score"], 725)
        self.assertEqual(result.snapshot["state"]["phase"], "navigating")

    async def test_reports_earliest_future_deadline(self) -> None:
        first_deadline = self.now + timedelta(seconds=30)
        later_deadline = self.now + timedelta(seconds=90)
        legacy = {
            "interactive_games": {
                "one": {"deadline_at": later_deadline.isoformat()},
                "two": {"deadline_at": first_deadline.isoformat()},
            }
        }
        result = await self.engine.apply(
            legacy,
            GameCommand("client.hello"),
            self.actor,
            self.now,
        )

        self.assertEqual(result.next_deadline_at, first_deadline.isoformat())

    async def test_rejects_unknown_snapshot_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported game snapshot schema version"):
            await self.engine.apply(
                {"schema_version": 99, "state": {}, "operation_receipts": {}},
                GameCommand("client.hello"),
                self.actor,
                self.now,
            )

    async def test_command_boundary_matches_legacy_state_machine(self) -> None:
        scenario = ScenarioLoader.load(str(SCENARIO_PATH))
        legacy = EscapeBotStateMachine(scenario)
        snapshot = None
        commands = (
            GameCommand("client.hello", request_id="hello", operation_id="operation-1"),
            GameCommand(
                "player.message",
                {"text": "Příjem"},
                request_id="message-1",
                operation_id="operation-2",
            ),
            GameCommand(
                "player.message",
                {"text": "734"},
                request_id="message-2",
                operation_id="operation-3",
            ),
        )

        for offset, command in enumerate(commands):
            command_time = self.now + timedelta(seconds=offset)
            legacy_payload = dict(command.payload)
            legacy_payload.update({
                "_client_id": self.actor.client_id,
                "_participant_ids": list(self.actor.participant_ids),
                "_team_mode": self.actor.team_mode,
                "_participant_names": dict(self.actor.participant_names),
            })
            legacy_responses = await legacy.handle(
                Message(command.type, legacy_payload, command.request_id),
                now=command_time,
            )
            result = await self.engine.apply(snapshot, command, self.actor, command_time)
            snapshot = result.snapshot

            self.assertEqual(
                [message.to_json() for message in result.responses],
                [message.to_json() for message in legacy_responses],
            )
            self.assertEqual(result.snapshot["state"], legacy.state.snapshot())
