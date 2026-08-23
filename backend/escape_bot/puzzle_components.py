from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PuzzleComponent:
    adapter: str
    submission: str = "answer"
    presenter: str | None = None
    resetter: str | None = None
    pre_submit: str | None = None
    events: dict[str, str] = field(default_factory=dict)
    event_details: dict[str, tuple[str, ...]] = field(default_factory=dict)
    editor_group: str = "cipher"
    completion_signal: str = "answer"


BUILTIN_COMPONENTS = {
    "answer": PuzzleComponent("answer"),
    "archive_vector": PuzzleComponent(
        "archive_vector", presenter="_present_archive_vector", pre_submit="_validate_archive_submission",
        events={"archive.arrange": "_handle_archive_arrange"},
        event_details={"archive.arrange": ("puzzle_id",)}, editor_group="assembly", completion_signal="assembled_then_answer",
    ),
    "line_game": PuzzleComponent(
        "line_game", submission="interactive", presenter="_present_line_game", resetter="_reset_line_game_component",
        events={"line_game.move": "_handle_line_game_move", "line_game.reset": "_handle_line_game_reset"},
        event_details={"line_game.move": ("puzzle_id",), "line_game.reset": ("puzzle_id",)}, editor_group="grid", completion_signal="team_complete",
    ),
    "sokoban": PuzzleComponent(
        "sokoban", submission="interactive", presenter="_present_sokoban", resetter="_reset_sokoban_component",
        events={"sokoban.command": "_handle_sokoban_command", "sokoban.undo": "_handle_sokoban_undo", "sokoban.reset": "_handle_sokoban_reset"},
        event_details={"sokoban.command": ("puzzle_id", "commands"), "sokoban.undo": ("puzzle_id",), "sokoban.reset": ("puzzle_id",)}, editor_group="grid", completion_signal="game_complete",
    ),
    "mine_karel": PuzzleComponent(
        "mine_karel", submission="interactive", presenter="_present_mine_karel", resetter="_reset_mine_karel_component",
        events={"karel.command": "_handle_karel_command", "karel.reset": "_handle_karel_reset"},
        event_details={"karel.command": ("puzzle_id", "commands"), "karel.reset": ("puzzle_id",)}, editor_group="grid", completion_signal="game_complete",
    ),
    "triad": PuzzleComponent(
        "triad", submission="interactive", presenter="_present_triad", resetter="_reset_triad_component",
        events={"triad.place": "_handle_triad_place", "triad.reset": "_handle_triad_reset"},
        event_details={"triad.place": ("puzzle_id",), "triad.reset": ("puzzle_id",)}, editor_group="grid", completion_signal="team_complete",
    ),
    "finale": PuzzleComponent(
        "finale", submission="interactive", presenter="_present_finale",
        events={"finale.activate": "_handle_finale_activate"},
        event_details={"finale.activate": ()}, editor_group="finale", completion_signal="activation",
    ),
}


def component_for(scenario_data: dict[str, Any], puzzle: dict[str, Any]) -> PuzzleComponent | None:
    component_type = str(puzzle.get("type", "answer"))
    declarations = scenario_data.get("puzzle_components", {})
    explicitly_declared = isinstance(declarations, dict) and component_type in declarations
    declaration = declarations.get(component_type, {}) if isinstance(declarations, dict) else {}
    adapter = str(declaration.get("adapter", component_type)) if isinstance(declaration, dict) else component_type
    # Cipher and textual puzzle types share the generic answer adapter.
    if not explicitly_declared and adapter not in BUILTIN_COMPONENTS and puzzle.get("answer") is not None:
        adapter = "answer"
    return BUILTIN_COMPONENTS.get(adapter)


def declared_components(scenario_data: dict[str, Any]) -> dict[str, PuzzleComponent]:
    result: dict[str, PuzzleComponent] = {}
    for puzzle in scenario_data.get("puzzles", {}).values():
        component_type = str(puzzle.get("type", "answer"))
        component = component_for(scenario_data, puzzle)
        if component is not None:
            result[component_type] = component
    return result
