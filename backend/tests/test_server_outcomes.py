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
