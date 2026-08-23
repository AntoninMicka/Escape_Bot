"""Rebuild the first layered scenario from the legacy runtime during schema-v1 migration."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


BACKEND = Path(__file__).resolve().parents[1]
LEGACY = BACKEND / "scenario.json"
TEMPLATE = BACKEND / "content" / "templates" / "lost_in_time.json"
REALIZATION = BACKEND / "content" / "realizations" / "hotel_kraskov.json"


CONTRACTS = {
    "first_contact": {"kind": "phase", "requires_capabilities": ["intercom"]},
    "carrier_frequency": {"kind": "phase", "requires_capabilities": ["intercom", "cipher"]},
    "mission_route": {"kind": "phase", "requires_capabilities": ["map"]},
    "public_archive": {"kind": "checkpoint", "requires_capabilities": ["physical_presence", "logic_puzzle"]},
    "signal_transition": {"kind": "checkpoint", "requires_capabilities": ["physical_presence", "visual_cipher"]},
    "hazard_navigation": {"kind": "checkpoint", "requires_capabilities": ["navigation_game"]},
    "machine_part_one": {"kind": "checkpoint", "requires_capabilities": ["physical_presence", "cipher"]},
    "timeline_calibration": {"kind": "checkpoint", "requires_capabilities": ["team_game"]},
    "machine_part_two": {"kind": "checkpoint", "requires_capabilities": ["physical_presence", "cipher"]},
    "alignment_game": {"kind": "checkpoint", "requires_capabilities": ["team_game"]},
    "spatial_archive": {"kind": "checkpoint", "requires_capabilities": ["navigation_game"]},
    "machine_part_three": {"kind": "checkpoint", "requires_capabilities": ["physical_presence", "cipher"]},
    "return_archive": {"kind": "checkpoint", "requires_capabilities": ["assembly_game"]},
    "final_console": {"kind": "checkpoint", "requires_capabilities": ["physical_presence"]},
    "optional_archive": {"kind": "room", "requires_capabilities": ["code_entry"]},
    "return_finale": {"kind": "finale", "requires_capabilities": ["finale"]},
}

BINDINGS = {
    "first_contact": ("comms_offline", ["intercom"]),
    "carrier_frequency": ("searching_lost", ["intercom", "cipher"]),
    "mission_route": ("navigating", ["map"]),
    "public_archive": ("reception_archive", ["physical_presence", "logic_puzzle", "qr"]),
    "signal_transition": ("staircase_signal", ["physical_presence", "visual_cipher", "qr"]),
    "hazard_navigation": ("courtyard_minefield", ["navigation_game"]),
    "machine_part_one": ("bowling_diagnostics", ["physical_presence", "cipher", "qr"]),
    "timeline_calibration": ("timeline_calibration", ["team_game"]),
    "machine_part_two": ("terrace_echo", ["physical_presence", "cipher", "qr"]),
    "alignment_game": ("courtyard_alignment", ["team_game"]),
    "spatial_archive": ("sports_archive", ["navigation_game"]),
    "machine_part_three": ("sports_cipher", ["physical_presence", "cipher", "qr"]),
    "return_archive": ("future_archive", ["assembly_game"]),
    "final_console": ("time_machine_console", ["physical_presence", "qr"]),
    "optional_archive": ("room_104", ["code_entry"]),
    "return_finale": ("time_machine_finale", ["finale"]),
}


def transform(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {replacements.get(key, key): transform(child, replacements) for key, child in value.items()}
    if isinstance(value, list):
        return [transform(child, replacements) for child in value]
    if isinstance(value, str):
        rendered = replacements.get(value, value)
        return rendered.replace("Hotelu Kraskov", "${location.name_locative}").replace("Hotel Kraskov", "${location.name}")
    return deepcopy(value)


def main() -> None:
    runtime = json.loads(LEGACY.read_text(encoding="utf-8"))
    checkpoint_contracts = {
        contract: node_id
        for contract, (node_id, _) in BINDINGS.items()
        if CONTRACTS[contract]["kind"] == "checkpoint"
    }
    replacements = {node_id: "${checkpoints." + contract + ".id}" for contract, node_id in checkpoint_contracts.items()}
    replacements["room_104"] = "${rooms.optional_archive.node_id}"
    templated_runtime = transform(runtime, replacements)
    templated_runtime["id"] = "${game.id}"
    templated_runtime["knowledge_base"] = {"$var": "location.knowledge_base"}

    variables: dict[str, Any] = {
        "game": {"id": runtime["id"]},
        "location": {
            "name": "Hotel Kraskov",
            "name_locative": "Hotelu Kraskov",
            "knowledge_base": runtime["knowledge_base"],
        },
        "checkpoints": {},
        "rooms": {
            "optional_archive": {
                "node_id": "room_104",
                "number": "104",
                "pin": runtime["rooms"]["104"]["pin"],
            }
        },
    }
    variable_schema: dict[str, Any] = {
        "game.id": {"type": "string"},
        "location.name": {"type": "string"},
        "location.name_locative": {"type": "string"},
        "location.knowledge_base": {"type": "string"},
        "rooms.optional_archive.node_id": {"type": "string"},
        "rooms.optional_archive.number": {"type": "string"},
        "rooms.optional_archive.pin": {"type": "string"},
    }

    original_flow = {node["id"]: node for node in runtime["scenario_flow"]}
    for contract, node_id in checkpoint_contracts.items():
        checkpoint = runtime["checkpoints"][node_id]
        variables["checkpoints"][contract] = {
            "id": node_id,
            "name": checkpoint["label"],
            "route_name": original_flow[node_id]["label"],
            "token": checkpoint["token"],
        }
        for field in ("id", "name", "route_name", "token"):
            variable_schema[f"checkpoints.{contract}.{field}"] = {"type": "string"}
        placeholder = "${checkpoints." + contract
        checkpoint_key = placeholder + ".id}"
        templated_runtime["checkpoints"][checkpoint_key]["label"] = placeholder + ".name}"
        templated_runtime["checkpoints"][checkpoint_key]["token"] = placeholder + ".token}"
        for node in templated_runtime["scenario_flow"]:
            if node["id"] == checkpoint_key:
                node["label"] = placeholder + ".route_name}"

    room = templated_runtime["rooms"].pop("104")
    room["pin"] = "${rooms.optional_archive.pin}"
    templated_runtime["rooms"]["${rooms.optional_archive.number}"] = room

    node_bindings = {}
    for contract, (node_id, capabilities) in BINDINGS.items():
        if contract in checkpoint_contracts:
            node_id = "${checkpoints." + contract + ".id}"
        elif contract == "optional_archive":
            node_id = "${rooms.optional_archive.node_id}"
        node_bindings[contract] = {"runtime_node_id": node_id, "capabilities": capabilities}

    template = {
        "schema_version": 1,
        "kind": "story_template",
        "id": "lost_in_time",
        "version": "1.1.0",
        "title": "Ztracená v čase",
        "description": "Příběh, šifry, herní objekty a postup záchrany vědkyně uvězněné v jiné časové vrstvě.",
        "variable_schema": variable_schema,
        "node_contracts": CONTRACTS,
        "node_bindings": node_bindings,
        "runtime": templated_runtime,
    }
    realization = {
        "schema_version": 1,
        "kind": "realization",
        "id": "hotel_kraskov",
        "version": "1.1.0",
        "title": "Hotel Kraskov",
        "template": {"id": "lost_in_time", "version": "1.1.0"},
        "modes": ["physical_indoor", "physical_outdoor", "hybrid"],
        "variables": variables,
    }
    TEMPLATE.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REALIZATION.write_text(json.dumps(realization, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
