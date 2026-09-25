import unittest
from unittest.mock import patch

from escape_bot import server
from escape_bot.team_lobby import Lobby, LobbyRegistry


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
