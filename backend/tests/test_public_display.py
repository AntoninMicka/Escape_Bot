import unittest
from pathlib import Path

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


ROOT = Path(__file__).resolve().parents[2]


def test_leaderboard_visibility_is_enabled_by_default_and_in_runtime_payload() -> None:
    original = dict(server.runtime_settings)
    try:
        assert server.runtime_settings["display_leaderboard"] is True
        server.runtime_settings["display_leaderboard"] = False
        assert server.runtime_payload()["display_leaderboard"] is False
    finally:
        server.runtime_settings.clear()
        server.runtime_settings.update(original)


def test_public_display_hides_ranking_panel_from_runtime_setting() -> None:
    display = (ROOT / "client" / "display.html").read_text(encoding="utf-8")
    admin = (ROOT / "client" / "index.html").read_text(encoding="utf-8")
    backend = (ROOT / "backend" / "escape_bot" / "server.py").read_text(encoding="utf-8")

    assert "showLeaderboard=message.payload.display_leaderboard!==false" in display
    assert "classList.toggle('rankings-hidden',!showLeaderboard)" in display
    assert ".dashboard.rankings-hidden .ranking-panel{display:none}" in display
    assert "sendAdmin('admin.display_leaderboard', {enabled:!displayLeaderboardEnabled})" in admin
    assert 'if msg.type == "admin.display_leaderboard":' in backend
    assert 'runtime_settings["display_leaderboard"] = bool(msg.payload.get("enabled"))' in backend


def test_outro_uses_recognizable_elara_character_asset() -> None:
    client = (ROOT / "client" / "index.html").read_text(encoding="utf-8")
    service_worker = (ROOT / "client" / "sw.js").read_text(encoding="utf-8")
    asset = ROOT / "client" / "assets" / "characters" / "elara-outro.png"
    image = asset.read_bytes()

    assert '<img class="rescue-elara" src="/assets/characters/elara-outro.png"' in client
    assert ".rescue-elara::before" not in client
    assert "./assets/characters/elara-outro.png" in service_worker
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert image[25] == 6  # PNG color type RGBA


def test_terminal_resets_and_renders_minigame_before_revealing_it() -> None:
    client = (ROOT / "client" / "index.html").read_text(encoding="utf-8")

    attached = client.split("else if (msg.type === 'terminal.attached')", 1)[1].split(
        "else if (msg.type === 'terminal.released')", 1
    )[0]
    assert attached.index("resetTerminalMiniGameUiState();") < attached.index(
        "terminalAssignmentPendingReveal = true;"
    )
    assert "terminal-pair-overlay').classList.add('hidden')" not in attached

    state = client.split("else if (msg.type === 'game.state')", 1)[1].split(
        "else if (msg.type === 'cipher_tool.result')", 1
    )[0]
    assert state.index("renderPuzzles();") < state.index(
        "if (terminalAssignmentPendingReveal && terminalAssignedPuzzleId)"
    ) < state.index("terminal-pair-overlay').classList.add('hidden')")

    reset = client.split("function resetTerminalMiniGameUiState()", 1)[1].split(
        "function finaleModuleImagePosition", 1
    )[0]
    for transient_state in (
        "pendingSokobanAnimation = null",
        "pendingKarelAnimation = null",
        "pendingLineAnimation = null",
        "pendingTriadEffect = null",
        "deferredPuzzlesState = null",
        "finaleUiState.clear()",
    ):
        assert transient_state in reset


def test_scanner_restarts_after_ios_page_resume_and_recovers_ended_track() -> None:
    client = (ROOT / "client" / "index.html").read_text(encoding="utf-8")

    assert "reviveScannerAfterResume();" in client
    revive = client.split("function reviveScannerAfterResume()", 1)[1].split("function tickScanner()", 1)[0]
    assert "tab-scanner').classList.contains('active')" in revive
    assert revive.index("stopScanner();") < revive.index("startScanner();")
    scanner = client.split("function startScanner()", 1)[1].split("function stopScanner()", 1)[0]
    assert "track.readyState === 'live'" in scanner
    assert "track.addEventListener('ended'" in scanner
    assert "setTimeout(startScanner, 250)" in scanner
    assert "document.getElementById('qr-retry').style.display = 'block'" in scanner


if __name__ == "__main__":
    unittest.main()
