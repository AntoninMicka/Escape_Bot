from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_gameplay_commands_use_persistent_operation_queue() -> None:
    client = (ROOT / "client" / "index.html").read_text(encoding="utf-8")

    assert '<script src="operation-queue.js"></script>' in client
    assert "gameOperationQueue.acknowledge(msg.operation_id);" in client
    assert "replayPendingGameOperations();" in client
    for message_type in (
        "cipher_tool.unlock",
        "room.unlock",
        "room.hint",
        "phase.hint",
        "archive.arrange",
        "finale.activate",
        "triad.place",
        "triad.reset",
        "karel.command",
        "karel.reset",
        "game.deadline_choice",
        "line_game.move",
        "line_game.reset",
        "sokoban.command",
        "sokoban.undo",
        "sokoban.reset",
        "puzzle.submit",
    ):
        assert f"sendGameCommand('{message_type}'" in client


def test_operation_queue_is_part_of_current_offline_cache() -> None:
    service_worker = (ROOT / "client" / "sw.js").read_text(encoding="utf-8")

    assert "const CACHE_NAME = 'escape-bot-v127';" in service_worker
    assert "'./operation-queue.js'" in service_worker


def test_personalized_game_state_keeps_operation_correlation() -> None:
    server = (ROOT / "backend" / "escape_bot" / "server.py").read_text(encoding="utf-8")
    personalization = server.split('if message.type == "game.state"', 1)[1].split(
        "await send_message(websocket, outgoing)", 1
    )[0]

    assert "outgoing.operation_id = message.operation_id" in personalization
    assert '"operation.ack"' in server
