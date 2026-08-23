import json
import unittest
from copy import deepcopy
from pathlib import Path

from escape_bot.scenario import ScenarioLoader
from escape_bot.scenario_composer import ScenarioCompositionError, compose_documents, compose_files


BACKEND_DIR = Path(__file__).resolve().parents[1]
LEGACY_PATH = BACKEND_DIR / "scenario.json"
TEMPLATE_PATH = BACKEND_DIR / "content" / "templates" / "lost_in_time.json"
REALIZATION_PATH = BACKEND_DIR / "content" / "realizations" / "hotel_kraskov.json"


class ScenarioComposerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.realization = json.loads(REALIZATION_PATH.read_text(encoding="utf-8"))

    def test_kraskov_compiles_to_the_existing_runtime_without_changes(self) -> None:
        compiled = compose_files(TEMPLATE_PATH, REALIZATION_PATH)
        legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))

        self.assertEqual(compiled.data, legacy)
        self.assertEqual(compiled.provenance["template_id"], "lost_in_time")
        self.assertEqual(compiled.provenance["realization_id"], "hotel_kraskov")

    def test_composed_loader_validates_and_exposes_provenance(self) -> None:
        scenario = ScenarioLoader.load_composed(str(TEMPLATE_PATH), str(REALIZATION_PATH))

        self.assertEqual(scenario.data["id"], "kraskov_time_rescue")
        self.assertEqual(scenario.provenance["realization_version"], "1.1.0")

    def test_rejects_missing_contract_binding(self) -> None:
        template = deepcopy(self.template)
        template["node_bindings"].pop("final_console")

        with self.assertRaisesRegex(ScenarioCompositionError, "chybí vazby: final_console"):
            compose_documents(template, self.realization)

    def test_rejects_incompatible_template_version(self) -> None:
        realization = deepcopy(self.realization)
        realization["template"]["version"] = "2.0.0"

        with self.assertRaisesRegex(ScenarioCompositionError, "jinou šablonu"):
            compose_documents(self.template, realization)

    def test_rejects_missing_required_variable(self) -> None:
        realization = deepcopy(self.realization)
        realization["variables"]["checkpoints"]["public_archive"].pop("token")

        with self.assertRaisesRegex(ScenarioCompositionError, "checkpoints.public_archive.token"):
            compose_documents(self.template, realization)

    def test_rejects_missing_required_capability(self) -> None:
        template = deepcopy(self.template)
        template["node_bindings"]["hazard_navigation"]["capabilities"] = []

        with self.assertRaisesRegex(ScenarioCompositionError, "navigation_game"):
            compose_documents(template, self.realization)

    def test_supports_text_object_and_dynamic_key_variables(self) -> None:
        template = deepcopy(self.template)
        template["variable_schema"]["extension"] = {"type": "object"}
        template["runtime"]["${game.id}-extension"] = {"$var": "extension"}
        realization = deepcopy(self.realization)
        realization["variables"]["extension"] = {"enabled": True, "items": [1, 2]}

        compiled = compose_documents(template, realization)

        self.assertEqual(compiled.data["kraskov_time_rescue-extension"], {"enabled": True, "items": [1, 2]})


if __name__ == "__main__":
    unittest.main()
