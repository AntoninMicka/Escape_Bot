import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from escape_bot import server
from escape_bot.scenario import ScenarioLoader
from escape_bot.state_machine import EscapeBotStateMachine
from escape_bot.team_lobby import Lobby, LobbyRegistry


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


class AdminOverviewTests(unittest.TestCase):
    def test_admin_capabilities_match_implemented_legacy_actions(self):
        self.assertEqual(server.admin_capabilities_payload(), {
            "actions": [
                "managed_team_create", "managed_start", "managed_start_override",
                "event_runtime", "leaderboard_finalize", "event_settings",
                "score_adjustment", "session_extend", "session_end", "support_message",
                "checkpoint", "scenario_play_modes", "terminal_catalog", "terminal_reservation", "spectate",
                "game_reset", "game_player", "team_finalize", "player_recovery", "team_delete",
            ],
            "http_actions": [],
            "checkpoint_states": ["found", "solved"],
            "game_reset_adapters": ["line_game", "mine_karel", "triad", "sokoban"],
            "game_player_actions": ["exclude", "include", "reset"],
            "terminal_reservation": True,
            "scenario_play_modes": True,
            "terminal_catalog": True,
            "terminal_assignment": True,
        })

    def test_admin_puzzle_catalog_exposes_effective_terminal_modes(self):
        with patch.dict(server.runtime_settings, {
            "puzzle_play_modes": {"timeline_lines": "supplemental"},
            "terminal_puzzle_ids": [],
        }, clear=False):
            catalog = {item["id"]: item for item in server.admin_puzzle_catalog()}

        self.assertEqual(catalog["timeline_lines"]["play_mode"], "supplemental")
        self.assertIn("title", catalog["timeline_lines"])
        self.assertIn("checkpoint_id", catalog["timeline_lines"])

    def test_global_terminal_admin_messages_reach_authenticated_dispatch(self):
        self.assertTrue({
            "admin.scenario_play_modes",
            "admin.terminal_catalog",
            "admin.terminal_reserve",
            "admin.terminal_assign",
        }.issubset(server.ADMIN_MESSAGE_TYPES))

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
        machine = EscapeBotStateMachine(ScenarioLoader.load(str(SCENARIO_PATH)), clock=lambda: datetime.now(UTC))
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
