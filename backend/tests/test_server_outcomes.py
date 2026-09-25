from pathlib import Path

from escape_bot.scenario import ScenarioLoader
from escape_bot.server import apply_deadline_end, apply_operational_end, apply_outcome_score
from escape_bot.state_machine import EscapeBotStateMachine


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


def machine() -> EscapeBotStateMachine:
    return EscapeBotStateMachine(ScenarioLoader.load(str(SCENARIO_PATH)))


def test_completion_bonus_is_applied_exactly_once_with_score_audit() -> None:
    state_machine = machine()

    update = apply_outcome_score(state_machine, "completed", 100)

    assert update is not None
    assert state_machine.state.score == 1100
    assert apply_outcome_score(state_machine, "completed", 100) is None
    adjustment = state_machine.state.flags["admin_score_adjustments"][-1]
    assert adjustment["score_before"] == 1000
    assert adjustment["score_after"] == 1100
    assert adjustment["automatic"] is True


def test_deadline_penalty_is_applied_exactly_once() -> None:
    state_machine = machine()

    apply_deadline_end(state_machine, "2026-08-23T12:00:00+00:00", 100)
    apply_deadline_end(state_machine, "2026-08-23T12:01:00+00:00", 100)

    assert state_machine.state.score == 900
    assert state_machine.state.flags["administratively_ended_reason"] == "deadline"
    assert len(state_machine.state.flags["admin_score_adjustments"]) == 1


def test_abandoned_end_records_reason_and_one_time_penalty() -> None:
    state_machine = machine()

    updates = apply_operational_end(
        state_machine,
        "2026-08-23T12:00:00+00:00",
        "abandoned",
        75,
        "Opuštěná hra",
    )

    assert state_machine.state.score == 925
    assert state_machine.state.flags["administratively_ended_reason"] == "abandoned"
    assert any(update.type == "operations.stopped" for update in updates)
    assert state_machine.state.flags["admin_actions"][-1]["reason"] == "abandoned"


def test_deadline_choice_survives_restore_and_allows_play_only_after_continue() -> None:
    import asyncio
    from escape_bot.protocol import Message

    original = machine()
    apply_deadline_end(original, "2026-08-23T12:00:00+00:00", 100)
    restored = machine()
    restored.restore_state(original.state.snapshot())
    assert restored.state.flags["deadline_choice_pending"]
    blocked = asyncio.run(restored.handle(Message("room.hint", {"room_id": "missing"})))
    assert blocked[0].type == "error"
    asyncio.run(restored.handle(Message("game.deadline_choice", {"choice": "continue"})))
    assert restored.state.flags["out_of_competition"]
    assert not restored.state.flags["administratively_ended"]
    assert not restored.state.flags["deadline_choice_pending"]
    assert apply_deadline_end(restored, "2026-08-23T12:01:00+00:00", 100) == []
    assert apply_outcome_score(restored, "completed", 100) is None
    assert restored.state.score == 900
    duplicate = asyncio.run(restored.handle(Message("game.deadline_choice", {"choice": "end"})))
    assert duplicate[0].type == "error"
    assert not restored.state.flags["administratively_ended"]


def test_deadline_end_choice_is_final_and_cannot_be_requested_early() -> None:
    import asyncio
    from escape_bot.protocol import Message

    state_machine = machine()
    result = asyncio.run(state_machine.handle(Message("game.deadline_choice", {"choice": "continue"})))
    assert result[0].type == "error"
    apply_deadline_end(state_machine, "2026-08-23T12:00:00+00:00", 0)
    asyncio.run(state_machine.handle(Message("game.deadline_choice", {"choice": "end"})))
    assert state_machine.state.flags["administratively_ended"]
    assert not state_machine.state.flags.get("out_of_competition")
    assert not state_machine.state.flags["deadline_choice_pending"]


def test_out_of_competition_team_is_not_ranked() -> None:
    from escape_bot import server

    state_machine = machine()
    state_machine.state.flags["out_of_competition"] = True
    from unittest.mock import patch
    with patch.object(server, "active_sessions", {"overtime": state_machine}), patch.object(server, "global_leaderboard", [{"session_id": "overtime", "score": 9999}]):
        assert server.leaderboard_entries() == []
