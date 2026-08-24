import json
import tempfile
import unittest
from pathlib import Path

from escape_bot.scenario_catalog import load_scenario_catalog


BACKEND_DIR = Path(__file__).resolve().parents[1]


class ScenarioCatalogTest(unittest.TestCase):
    def test_chronos_online_compiles_as_selectable_webgl_game(self) -> None:
        catalog = load_scenario_catalog(
            BACKEND_DIR / "content" / "templates",
            BACKEND_DIR / "content" / "realizations",
        )

        entry = catalog.entries["chronos_online"]
        self.assertIn("online_doom", entry.modes)
        self.assertEqual(entry.realization_version, "0.2.0")
        self.assertEqual(entry.scenario.data["world"]["mode"], "webgl")
        self.assertIn("104", entry.scenario.data["rooms"])
        self.assertEqual(entry.scenario.data["rooms"]["104"]["pin"], "1104")

    def test_invalid_realization_does_not_hide_valid_game(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            templates = root / "templates"
            realizations = root / "realizations"
            templates.mkdir(); realizations.mkdir()
            valid_template = BACKEND_DIR / "content" / "templates" / "lost_in_time.json"
            valid_realization = BACKEND_DIR / "content" / "realizations" / "hotel_kraskov.json"
            (templates / valid_template.name).write_text(valid_template.read_text(encoding="utf-8"), encoding="utf-8")
            (realizations / valid_realization.name).write_text(valid_realization.read_text(encoding="utf-8"), encoding="utf-8")
            (realizations / "broken.json").write_text('{"kind":', encoding="utf-8")

            catalog = load_scenario_catalog(templates, realizations)

            self.assertIn("hotel_kraskov", catalog.entries)
            self.assertEqual(len(catalog.errors), 1)
            self.assertTrue(catalog.errors[0]["path"].endswith("broken.json"))

    def test_missing_template_only_rejects_affected_realization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            templates = root / "templates"
            realizations = root / "realizations"
            templates.mkdir(); realizations.mkdir()
            realization = {
                "schema_version": 1, "kind": "realization", "id": "missing",
                "version": "1.0.0", "template": {"id": "absent", "version": "1.0.0"},
                "variables": {},
            }
            (realizations / "missing.json").write_text(json.dumps(realization), encoding="utf-8")

            catalog = load_scenario_catalog(templates, realizations)

            self.assertFalse(catalog.entries)
            self.assertIn("Chybí šablona", catalog.errors[0]["message"])
