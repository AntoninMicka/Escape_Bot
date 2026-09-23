from pathlib import Path

from escape_bot import server


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
