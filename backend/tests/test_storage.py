import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from escape_bot.storage import JsonStorage


class JsonStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.data_dir = Path(self.temporary_directory.name)
        self.storage = JsonStorage(self.data_dir)

    def test_missing_datasets_have_empty_compatible_defaults(self) -> None:
        self.assertEqual(self.storage.load_sessions(), {})
        self.assertEqual(self.storage.load_lobbies(), [])
        self.assertEqual(self.storage.load_runtime_settings(), {})
        self.assertEqual(self.storage.load_leaderboard(), [])

    def test_all_datasets_round_trip(self) -> None:
        sessions = {"session-1": {"score": 930}}
        lobbies = [{"session_id": "session-1", "players": {}}]
        settings = {"opening_time": "08:00"}
        leaderboard = [{"team_name": "Test", "score": 930}]

        self.storage.save_sessions(sessions)
        self.storage.save_lobbies(lobbies)
        self.storage.save_runtime_settings(settings)
        self.storage.save_leaderboard(leaderboard)

        self.assertEqual(self.storage.load_sessions(), sessions)
        self.assertEqual(self.storage.load_lobbies(), lobbies)
        self.assertEqual(self.storage.load_runtime_settings(), settings)
        self.assertEqual(self.storage.load_leaderboard(), leaderboard)

    def test_save_atomically_replaces_existing_dataset(self) -> None:
        self.storage.save_sessions({"old": {}})
        self.storage.save_sessions({"new": {"score": 1000}})

        self.assertEqual(self.storage.load_sessions(), {"new": {"score": 1000}})
        self.assertEqual(list(self.data_dir.glob(".escape-bot-*")), [])

    def test_invalid_dataset_shape_is_rejected(self) -> None:
        (self.data_dir / "sessions.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.storage.load_sessions()

    def test_readiness_performs_write_without_leaving_probe_file(self) -> None:
        result = self.storage.check_ready()
        self.assertEqual(result, {"backend": "json", "writable": True})
        self.assertEqual(list(self.data_dir.glob(".escape-bot-ready-*")), [])


class OperationalEndpointTests(unittest.TestCase):
    def test_health_is_liveness_only(self) -> None:
        from escape_bot.server import health

        result = asyncio.run(health())
        self.assertEqual(result["status"], "ok")
        self.assertNotIn("storage_writable", result)

    def test_readiness_returns_503_when_storage_fails(self) -> None:
        from escape_bot import server

        class FailingStorage:
            backend_name = "test"

            def check_ready(self):
                raise OSError("unavailable")

        with patch.object(server, "storage", FailingStorage()):
            response = asyncio.run(server.ready())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body), {"status": "not_ready", "storage": {"backend": "test"}})

    def test_readiness_reports_storage_backend(self) -> None:
        from escape_bot import server

        response = asyncio.run(server.ready())
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["storage"]["backend"], "json")
