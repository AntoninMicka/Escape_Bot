import unittest

from escape_bot import server
from escape_bot.team_lobby import LobbyRegistry


class PublicDisplayTests(unittest.TestCase):
    def test_legacy_announcement_is_unwrapped(self) -> None:
        item = server.normalize_display_announcement(
            "{'text': \"{'text': 'Nový rekord', 'priority': 'emergency'}\", 'priority': 'normal'}"
        )
        self.assertEqual(item["text"], "Nový rekord")
        self.assertEqual(item["priority"], "emergency")
        self.assertTrue(item["published"])

    def test_waiting_on_site_teams_form_public_queue(self) -> None:
        original_registry = server.lobby_registry
        original_settings = dict(server.runtime_settings)
        try:
            server.lobby_registry = LobbyRegistry()
            server.runtime_settings.update({"gameplay_enabled": True, "opening_time": "00:00", "closing_time": "23:59",
                                            "game_duration_minutes": 60, "start_interval_minutes": 15,
                                            "max_active_teams": 4, "event": {}})
            first = server.lobby_registry.create("one", "team", "Ada", "První")
            second = server.lobby_registry.create("two", "team", "Boris", "Druhý")
            online = server.lobby_registry.create("three", "team", "Cyril", "Online", lobby_type="online_doom")
            online.started = False

            queue = server.public_start_queue()

            self.assertEqual([item["session_id"] for item in queue], [first.session_id, second.session_id])
            self.assertEqual([item["position"] for item in queue], [1, 2])
            self.assertEqual([item["team_name"] for item in queue], ["První", "Druhý"])
        finally:
            server.lobby_registry = original_registry
            server.runtime_settings.clear()
            server.runtime_settings.update(original_settings)

    def test_public_display_routes_are_registered(self) -> None:
        paths = {route.path for route in server.app.routes}
        self.assertIn("/display", paths)
        self.assertIn("/api/qr", paths)

    def test_legacy_event_gets_one_primary_game(self) -> None:
        event = server.normalize_event({"id": "demo", "scenario_ids": ["main", "second"]})
        self.assertEqual(event["primary_game_id"], "main")
        self.assertEqual([game["role"] for game in event["games"]], ["primary", "competitive"])
        self.assertEqual(event["status"], "open")

    def test_side_game_is_not_added_to_public_queue(self) -> None:
        original_registry = server.lobby_registry
        original_settings = dict(server.runtime_settings)
        try:
            server.lobby_registry = LobbyRegistry()
            server.runtime_settings["event"] = {
                "id": "demo", "status": "open", "primary_game_id": "main",
                "games": [
                    {"game_id": "main", "role": "primary", "queue_enabled": True},
                    {"game_id": "bonus", "role": "side", "queue_enabled": False},
                ],
            }
            main = server.lobby_registry.create("one", "team", "Ada", "Hlavní", scenario_id="main")
            server.lobby_registry.create("two", "team", "Boris", "Bonus", scenario_id="bonus")

            queue = server.public_start_queue()

            self.assertEqual([item["session_id"] for item in queue], [main.session_id])
            self.assertEqual(queue[0]["event_role"], "primary")
        finally:
            server.lobby_registry = original_registry
            server.runtime_settings.clear()
            server.runtime_settings.update(original_settings)


if __name__ == "__main__":
    unittest.main()
