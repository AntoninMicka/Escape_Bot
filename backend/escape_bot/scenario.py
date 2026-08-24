import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .puzzle_components import component_for

@dataclass
class Scenario:
    data: dict[str, Any]
    provenance: dict[str, str | int] | None = None

    def get_phase_data(self, phase: str) -> dict[str, Any]:
        return self.data.get("phases", {}).get(phase, {})

    def get_room_data(self, room_id: str) -> dict[str, Any]:
        return self.data.get("rooms", {}).get(room_id, {})

class ScenarioLoader:
    @staticmethod
    def load(filepath: str) -> Scenario:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        scenario = Scenario(data)
        validate_checkpoint_navigation(scenario)
        validate_phase_engine(scenario)
        validate_puzzle_components(scenario)
        return scenario

    @staticmethod
    def load_composed(template_path: str, realization_path: str) -> Scenario:
        # Local import keeps the legacy single-file loader independent.
        from .scenario_composer import compose_files

        compiled = compose_files(template_path, realization_path)
        scenario = Scenario(compiled.data, compiled.provenance)
        validate_checkpoint_navigation(scenario)
        validate_phase_engine(scenario)
        validate_puzzle_components(scenario)
        return scenario


def validate_phase_engine(scenario: Scenario) -> None:
    engine = scenario.data.get("phase_engine")
    if engine is None:
        return
    if not isinstance(engine, dict):
        raise ValueError("phase_engine musí být objekt.")
    phases = scenario.data.get("phases", {})
    initial = str(engine.get("initial_phase", ""))
    if initial not in phases:
        raise ValueError(f"Počáteční fáze {initial or '—'} neexistuje.")
    transitions = engine.get("transitions", {})
    if not isinstance(transitions, dict):
        raise ValueError("phase_engine.transitions musí být objekt.")
    for phase_id, transition in transitions.items():
        if phase_id not in phases or not isinstance(transition, dict):
            raise ValueError(f"Neplatné pravidlo přechodu fáze {phase_id}.")
        next_phase = str(transition.get("next_phase", ""))
        if next_phase not in phases:
            raise ValueError(f"Přechod z {phase_id} míří na neexistující fázi {next_phase or '—'}.")
        if transition.get("match", "any") not in {"any", "contains", "equals"}:
            raise ValueError(f"Fáze {phase_id} používá nepodporovanou podmínku přechodu.")


def validate_puzzle_components(scenario: Scenario) -> None:
    declarations = scenario.data.get("puzzle_components")
    if declarations is not None and not isinstance(declarations, dict):
        raise ValueError("puzzle_components musí být objekt.")
    for puzzle_id, puzzle in scenario.data.get("puzzles", {}).items():
        component_type = str(puzzle.get("type", "answer"))
        if isinstance(declarations, dict) and component_type not in declarations:
            raise ValueError(f"Hádanka {puzzle_id} používá nedeklarovanou komponentu {component_type}.")
        if component_for(scenario.data, puzzle) is None:
            raise ValueError(f"Hádanka {puzzle_id} používá neznámý adaptér komponenty {component_type}.")
        component = component_for(scenario.data, puzzle)
        if component and component.adapter in {"line_game", "mine_karel", "triad", "sokoban"} and not isinstance(puzzle.get("game"), dict):
            raise ValueError(f"Komponenta {component_type} hádanky {puzzle_id} vyžaduje objekt game.")
        if component and component.adapter == "archive_vector" and not isinstance(puzzle.get("assembly"), dict):
            raise ValueError(f"Komponenta {component_type} hádanky {puzzle_id} vyžaduje objekt assembly.")


def validate_checkpoint_navigation(scenario: Scenario) -> None:
    """Ensure the declared route cannot silently skip a checkpoint."""
    ordered = [
        str(node["id"]) for node in scenario.data.get("scenario_flow", [])
        if node.get("kind") == "checkpoint"
    ]
    checkpoints = scenario.data.get("checkpoints", {})
    if set(ordered) != set(checkpoints):
        missing = sorted(set(ordered) ^ set(checkpoints))
        raise ValueError(f"Checkpointy a scenario_flow se liší: {', '.join(missing)}")
    for index, checkpoint_id in enumerate(ordered):
        checkpoint = checkpoints[checkpoint_id]
        expected_next = ordered[index + 1] if index + 1 < len(ordered) else None
        declared_next = checkpoint.get("next_checkpoint")
        if declared_next != expected_next:
            raise ValueError(f"Checkpoint {checkpoint_id} musí odkazovat na {expected_next or 'konec trasy'}.")
        if expected_next and not checkpoint.get("navigation_message", {}).get("text"):
            raise ValueError(f"Checkpoint {checkpoint_id} nemá navigační zprávu.")
        if index and ordered[index - 1] not in checkpoint.get("requires", []):
            raise ValueError(f"Checkpoint {checkpoint_id} může přeskočit předchozí stanoviště {ordered[index - 1]}.")


def _parse_event_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def build_puzzle_telemetry(scenario: Scenario, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive comparable puzzle metrics without mutating persisted game state."""
    checkpoints = dict(state.get("checkpoint_states", {}))
    attempts = dict(state.get("puzzle_attempts", {}))
    hints = dict(state.get("hints_used", {}))
    events = list(state.get("event_history", []))
    event_times = sorted(filter(None, (_parse_event_time(item.get("at")) for item in events)))
    result: list[dict[str, Any]] = []
    for puzzle_id, puzzle in scenario.data.get("puzzles", {}).items():
        checkpoint_id = str(puzzle.get("checkpoint_id", ""))
        checkpoint = checkpoints.get(checkpoint_id)
        if not isinstance(checkpoint, dict):
            continue
        started_at = checkpoint.get("first_scanned_at") or checkpoint.get("found_at")
        completed_at = checkpoint.get("solved_at")
        start = _parse_event_time(started_at)
        end = _parse_event_time(completed_at) or datetime.now(UTC)
        elapsed_seconds = max(0, int((end - start).total_seconds())) if start else 0
        bounded = [time for time in event_times if start and start <= time <= end]
        activity_points = [start, *bounded, end] if start else []
        active_seconds = sum(min(300, max(0, int((later - earlier).total_seconds()))) for earlier, later in zip(activity_points, activity_points[1:]))
        puzzle_events = [item for item in events if str(item.get("details", {}).get("puzzle_id", "")) == puzzle_id]
        result.append({
            "puzzle_id": puzzle_id, "checkpoint_id": checkpoint_id,
            "title": str(puzzle.get("title", puzzle_id)), "type": str(puzzle.get("type", "puzzle")),
            "status": str(checkpoint.get("status", "found")), "started_at": str(started_at or ""),
            "completed_at": str(completed_at or ""), "elapsed_seconds": elapsed_seconds,
            "active_seconds": active_seconds, "attempts": int(attempts.get(puzzle_id, 0)),
            "hints": int(hints.get(f"puzzle.{puzzle_id}", hints.get(puzzle_id, 0))), "actions": len(puzzle_events),
        })
    return result


def build_demo_checkpoint_catalog(scenario: Scenario) -> list[dict[str, Any]]:
    return [
        {
            "id": checkpoint_id,
            "label": checkpoint.get("label", checkpoint_id),
            "value": f"escapebot://checkpoint/{checkpoint.get('token', '')}",
            "requires": checkpoint.get("requires", []),
        }
        for checkpoint_id, checkpoint in scenario.data.get("checkpoints", {}).items()
    ]


def build_checkpoint_qr_set(scenario: Scenario) -> list[dict[str, Any]]:
    flow_order = {node.get("id"): index for index, node in enumerate(scenario.data.get("scenario_flow", []))}
    checkpoints = [
        {"id": checkpoint_id, "label": checkpoint.get("label", checkpoint_id),
         "value": f"escapebot://checkpoint/{checkpoint.get('token', '')}",
         "requires": list(checkpoint.get("requires", [])), "order": flow_order.get(checkpoint_id, 9999)}
        for checkpoint_id, checkpoint in scenario.data.get("checkpoints", {}).items()
    ]
    return sorted(checkpoints, key=lambda item: (int(item["order"]), str(item["label"])))


def build_scenario_progress(scenario: Scenario, state: dict[str, Any]) -> dict[str, Any]:
    """Build a presentation-neutral progress snapshot usable by demo and admin UIs."""
    flow = scenario.data.get("scenario_flow", [])
    current_phase = str(state.get("phase", "boot"))
    checkpoint_states = state.get("checkpoint_states", {})
    flags = state.get("flags", {})

    phase_ids = [node["id"] for node in flow if node.get("kind") == "phase"]
    current_phase_index = phase_ids.index(current_phase) if current_phase in phase_ids else -1
    resolved: set[str] = set()
    nodes: list[dict[str, Any]] = []

    for index, phase_id in enumerate(phase_ids):
        if index <= current_phase_index:
            resolved.add(phase_id)

    for checkpoint_id, checkpoint_state in checkpoint_states.items():
        if checkpoint_state.get("status") == "solved":
            resolved.add(checkpoint_id)
    for node in flow:
        completion_flag = node.get("completion_flag")
        if completion_flag and flags.get(completion_flag):
            resolved.add(node["id"])

    for node in flow:
        node_id = node["id"]
        kind = node.get("kind", "checkpoint")
        requires = list(node.get("requires", []))
        if kind == "phase":
            phase_index = phase_ids.index(node_id)
            if node_id == current_phase:
                status = "active"
            elif current_phase_index >= 0 and phase_index < current_phase_index:
                status = "complete"
            else:
                status = "locked"
        elif node_id in resolved:
            status = "complete"
        elif checkpoint_states.get(node_id, {}).get("status") == "found":
            status = "active"
        elif all(required in resolved for required in requires):
            status = "available"
        else:
            status = "locked"

        puzzle = scenario.data.get("puzzles", {}).get(node_id)
        if not puzzle and kind == "checkpoint":
            puzzle = next(
                (item for item in scenario.data.get("puzzles", {}).values() if item.get("checkpoint_id") == node_id),
                None,
            )
        solution = node.get("solution")
        if not solution and puzzle:
            solution = puzzle.get("admin_solution", puzzle.get("answer"))
        if not solution and kind == "room":
            room_id = node_id.removeprefix("room_")
            solution = scenario.data.get("rooms", {}).get(room_id, {}).get("pin")

        nodes.append({
            "id": node_id,
            "label": node.get("label", node_id),
            "kind": kind,
            "status": status,
            "requires": requires,
            "solution": solution,
            "puzzle_id": next((puzzle_id for puzzle_id, item in scenario.data.get("puzzles", {}).items() if item is puzzle), None),
            "puzzle_type": puzzle.get("type") if puzzle else None,
            "activation_value": (
                f"escapebot://checkpoint/{scenario.data.get('checkpoints', {}).get(node_id, {}).get('token', '')}"
                if kind == "checkpoint" else ""
            ),
        })

    completed = sum(node["status"] == "complete" for node in nodes)
    return {
        "scenario_id": scenario.data.get("id", "default"),
        "title": scenario.data.get("title", "Escape Bot"),
        "current_phase": current_phase,
        "score": int(state.get("score", 0)),
        "inventory": list(state.get("inventory", [])),
        "unlocked_cipher_tools": list(state.get("unlocked_cipher_tools", [])),
        "nodes": nodes,
        "completed_nodes": completed,
        "total_nodes": len(nodes),
        "world": scenario.data.get("world", {}),
    }
