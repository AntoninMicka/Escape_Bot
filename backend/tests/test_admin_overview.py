import unittest
from pathlib import Path
from unittest.mock import patch

from escape_bot import server
from escape_bot.scenario import ScenarioLoader
from escape_bot.state_machine import EscapeBotStateMachine
from escape_bot.team_lobby import Lobby, LobbyRegistry


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


class AdminOverviewTests(unittest.TestCase):
    def test_lobby_without_game_does_not_break_admin_overview(self):
        registry = LobbyRegistry()
        lobby = Lobby("waiting-session", "team", "alice", "Waiting team")
        lobby.add_player("alice", "Alice")
        registry.by_session[lobby.session_id] = lobby

        with patch.object(server, "lobby_registry", registry), patch.object(server, "active_sessions", {}):
            teams = server.admin_overview()

        self.assertEqual(len(teams), 1)
        self.assertEqual(teams[0]["team_name"], "Waiting team")
        self.assertEqual(teams[0]["terminal_options"], [])
        self.assertEqual(teams[0]["progress"], {"nodes": []})

    def test_active_team_game_lists_and_can_exclude_player_without_a_board_or_connection(self):
        registry = LobbyRegistry()
        lobby = Lobby("offline-player-session", "team", "alice", "Offline team", started=True)
        lobby.add_player("alice", "Alice")
        lobby.add_player("bob", "Bob")
        registry.by_session[lobby.session_id] = lobby
        machine = EscapeBotStateMachine(ScenarioLoader.load(str(SCENARIO_PATH)))
        machine._team_mode = "team"
        machine._participant_ids = ["alice", "bob"]
        machine._participant_names = {"alice": "Alice", "bob": "Bob"}
        config = machine.scenario.data["puzzles"]["timeline_lines"]["game"]
        machine._line_game_state("timeline_lines", config, "alice")
        machine.state.checkpoint_states["timeline_calibration"] = {"status": "found"}

        with patch.object(server, "lobby_registry", registry), patch.object(
            server, "active_sessions", {lobby.session_id: machine}
        ), patch.object(server, "session_connections", {}):
            team = server.admin_overview()[0]

        players = {item["player_id"]: item for item in team["game_metrics"]["line"]}
        self.assertEqual(set(players), {"alice", "bob"})
        self.assertFalse(players["bob"]["connected"])
        self.assertEqual(players["bob"]["status"], "not_started")
        result = machine.admin_set_game_player("timeline_lines", "bob", "exclude")
        self.assertEqual(result["action"], "exclude")
        self.assertIn("bob", machine.state.game_exclusions["timeline_lines"])
