import json
from dataclasses import dataclass
from typing import Any

@dataclass
class Scenario:
    data: dict[str, Any]

    def get_phase_data(self, phase: str) -> dict[str, Any]:
        return self.data.get("phases", {}).get(phase, {})

    def get_room_data(self, room_id: str) -> dict[str, Any]:
        return self.data.get("rooms", {}).get(room_id, {})

class ScenarioLoader:
    @staticmethod
    def load(filepath: str) -> Scenario:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Scenario(data)


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
