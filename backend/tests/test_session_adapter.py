import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from escape_bot.protocol import Message
from escape_bot.scenario import ScenarioLoader
from escape_bot.session_adapter import GameSessionAdapter, PERSISTED_ENGINE_KEY
from escape_bot.state_machine import EscapeBotStateMachine, GameState


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


class GameSessionAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.scenario = ScenarioLoader.load(str(SCENARIO_PATH))
        self.now = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)

    async def test_idempotency_receipt_survives_persistence_and_restart(self) -> None:
        machine = EscapeBotStateMachine(self.scenario)
        adapter = GameSessionAdapter()
        first = await adapter.apply(
            machine,
            Message(
                "player.message",
                {"text": "Jednou", "_client_id": "alice"},
                operation_id="message-1",
            ),
            now=self.now,
        )
        persisted = adapter.snapshot(machine)

        restored_machine = EscapeBotStateMachine(self.scenario)
        restored_adapter = GameSessionAdapter.restore(restored_machine, persisted)
        replayed = await restored_adapter.apply(
            restored_machine,
            Message(
                "player.message",
                {"text": "Podruhé", "_client_id": "alice"},
                operation_id="message-1",
            ),
            now=self.now + timedelta(minutes=5),
        )

        self.assertEqual([item.to_json() for item in replayed], [item.to_json() for item in first])
        self.assertEqual(
            [item["text"] for item in restored_machine.state.chat_history if item["role"] == "player"],
            ["Jednou"],
        )
        self.assertEqual(restored_machine.state.last_activity_at, self.now.isoformat())

    async def test_concurrent_commands_are_serialized_without_lost_state(self) -> None:
        machine = EscapeBotStateMachine(self.scenario)
        adapter = GameSessionAdapter()

        await asyncio.gather(
            adapter.apply(
                machine,
                Message("player.message", {"text": "První"}, operation_id="message-1"),
                now=self.now,
            ),
            adapter.apply(
                machine,
                Message("player.message", {"text": "Druhý"}, operation_id="message-2"),
                now=self.now + timedelta(seconds=1),
            ),
        )

        player_messages = [
            item["text"] for item in machine.state.chat_history if item["role"] == "player"
        ]
        self.assertEqual(len(player_messages), 2)
        self.assertEqual(set(player_messages), {"První", "Druhý"})
        self.assertEqual(set(adapter.operation_receipts), {"message-1", "message-2"})

    async def test_transport_actor_fields_are_not_part_of_public_command_payload(self) -> None:
        machine = EscapeBotStateMachine(self.scenario)
        adapter = GameSessionAdapter()

        responses = await adapter.apply(
            machine,
            Message("client.hello", {
                "session_id": "session-1",
                "_client_id": "alice",
                "_participant_ids": ["alice", "bob"],
                "_team_mode": "team",
                "_participant_names": {"alice": "Alice", "bob": "Bob"},
            }),
            now=self.now,
        )

        self.assertTrue(responses)
        self.assertEqual(machine._current_player_id, "alice")
        self.assertEqual(machine._participant_ids, ["alice", "bob"])

    def test_persisted_snapshot_remains_readable_by_legacy_state_restore(self) -> None:
        machine = EscapeBotStateMachine(self.scenario)
        machine.state.score = 875
        persisted = GameSessionAdapter().snapshot(machine)

        self.assertIn(PERSISTED_ENGINE_KEY, persisted)
        legacy_state = GameState.restore(persisted)
        self.assertEqual(legacy_state.score, 875)

    def test_restore_accepts_legacy_raw_snapshot(self) -> None:
        machine = EscapeBotStateMachine(self.scenario)
        adapter = GameSessionAdapter.restore(machine, {"score": 640, "phase": "navigating"})

        self.assertEqual(machine.state.score, 640)
        self.assertEqual(machine.state.phase, "navigating")
        self.assertEqual(adapter.operation_receipts, {})


class OperationIdProtocolTests(unittest.TestCase):
    def test_operation_id_round_trips(self) -> None:
        message = Message.from_json({
            "type": "player.message",
            "payload": {"text": "Příjem"},
            "request_id": "request-1",
            "operation_id": "operation-1",
        })

        self.assertEqual(message.operation_id, "operation-1")
        self.assertEqual(message.to_json()["operation_id"], "operation-1")

    def test_invalid_operation_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "operation_id"):
            Message.from_json({"type": "player.message", "operation_id": ""})


class ServerSessionPersistenceTests(unittest.TestCase):
    def test_server_save_and_load_preserves_engine_metadata(self) -> None:
        from escape_bot import server

        class SessionStorage:
            data = {}

            def save_sessions(self, data):
                self.data = data

            def load_sessions(self):
                return self.data

        session_id = "adapter-persistence-test"
        machine = EscapeBotStateMachine(server.scenario)
        machine.state.score = 930
        adapter = GameSessionAdapter(operation_receipts={"operation-1": {"responses": []}})
        storage = SessionStorage()

        with (
            patch.object(server, "storage", storage),
            patch.object(server, "active_sessions", {session_id: machine}),
            patch.object(server, "session_command_adapters", {session_id: adapter}),
        ):
            server.save_sessions()

        self.assertIn(PERSISTED_ENGINE_KEY, storage.data[session_id])

        restored_sessions = {}
        restored_adapters = {}
        with (
            patch.object(server, "storage", storage),
            patch.object(server, "active_sessions", restored_sessions),
            patch.object(server, "session_command_adapters", restored_adapters),
        ):
            server.load_sessions(None)

        self.assertEqual(restored_sessions[session_id].state.score, 930)
        self.assertIn("operation-1", restored_adapters[session_id].operation_receipts)
