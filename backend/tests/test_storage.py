import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from escape_bot.storage import JsonStorage, create_storage
from escape_bot.storage_migration import migrate_storage
from escape_bot.event_lifecycle import RESET_CONFIRMATION, archive_event, reset_event


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

    def test_factory_allows_explicit_backend_override(self) -> None:
        configured = create_storage("json", data_dir=self.data_dir / "override")
        self.assertEqual(configured.backend_name, "json")
        self.assertEqual(configured.data_dir, (self.data_dir / "override").resolve())

    def test_migration_dry_run_does_not_modify_target(self) -> None:
        self.storage.save_sessions({"session-1": {"score": 1000}})
        self.storage.save_lobbies([{"session_id": "session-1", "players": {"a": {}}}])
        target = JsonStorage(self.data_dir / "target")

        report = migrate_storage(self.storage, target, apply=False)

        self.assertEqual(report["sessions"], 1)
        self.assertEqual(report["players"], 1)
        self.assertFalse(target.data_dir.exists())

    def test_migration_apply_is_idempotent(self) -> None:
        self.storage.save_sessions({"session-1": {"score": 1000}})
        self.storage.save_lobbies([{"session_id": "session-1", "players": {}}])
        target = JsonStorage(self.data_dir / "target")

        migrate_storage(self.storage, target, apply=True)
        migrate_storage(self.storage, target, apply=True)

        self.assertEqual(target.load_sessions(), {"session-1": {"score": 1000}})
        self.assertEqual(len(target.load_lobbies()), 1)

    def test_migration_rejects_lobby_without_session(self) -> None:
        self.storage.save_lobbies([{"session_id": "missing", "players": {}}])
        with self.assertRaisesRegex(ValueError, "Lobby bez odpovídající relace"):
            migrate_storage(self.storage)

    def test_schema_only_rejects_json_target_before_opening_storage(self) -> None:
        from escape_bot import storage_migration

        with patch("sys.argv", ["storage_migration", "--schema-only", "--target", "json"]):
            with self.assertRaises(SystemExit) as raised:
                storage_migration.main()
        self.assertEqual(raised.exception.code, 2)

    def test_event_reset_archives_first_and_preserves_schedule(self) -> None:
        self.storage.save_sessions({"session-1": {"score": 900}})
        self.storage.save_lobbies([{"session_id": "session-1", "players": {}}])
        self.storage.save_leaderboard([{"team_name": "Test", "score": 900}])
        self.storage.save_runtime_settings({"opening_time": "08:00", "gameplay_enabled": True})

        archive_path, report = archive_event(self.storage, self.data_dir / "archives", "test-run")
        reset_event(self.storage, RESET_CONFIRMATION)

        archive = JsonStorage(archive_path)
        self.assertEqual(report["sessions"], 1)
        self.assertEqual(archive.load_sessions(), {"session-1": {"score": 900}})
        self.assertEqual(self.storage.load_sessions(), {})
        self.assertEqual(self.storage.load_lobbies(), [])
        self.assertEqual(self.storage.load_leaderboard(), [])
        self.assertEqual(self.storage.load_runtime_settings()["opening_time"], "08:00")
        self.assertFalse(self.storage.load_runtime_settings()["gameplay_enabled"])

    def test_event_reset_requires_explicit_confirmation(self) -> None:
        with self.assertRaisesRegex(ValueError, RESET_CONFIRMATION):
            reset_event(self.storage, "wrong")


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
