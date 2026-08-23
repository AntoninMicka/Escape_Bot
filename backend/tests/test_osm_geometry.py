import json
import math
import unittest
from pathlib import Path

from backend.tools.build_osm_geometry import local_xy
from escape_bot.scenario_catalog import load_scenario_catalog


BACKEND = Path(__file__).resolve().parents[1]
GEOMETRY = BACKEND / "content" / "maps" / "pardubice_center.geometry.json"


def point_segment_distance(point, start, end) -> float:
    px, py = point; ax, ay = start; bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == dy == 0: return math.hypot(px - ax, py - ay)
    ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy))


class OsmGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
        cls.catalog = load_scenario_catalog(BACKEND / "content" / "templates", BACKEND / "content" / "realizations")

    def test_geometry_has_metric_osm_layers_and_attribution(self) -> None:
        self.assertEqual(self.geometry["meters_per_unit"], 1)
        self.assertGreaterEqual(len(self.geometry["buildings"]), 300)
        self.assertGreaterEqual(len(self.geometry["paths"]), 500)
        self.assertEqual(self.geometry["source"]["license"], "ODbL-1.0")
        self.assertIn("OpenStreetMap", self.geometry["source"]["attribution"])
        self.assertTrue(all(item["polygon_m"][0] == item["polygon_m"][-1] for item in self.geometry["buildings"]))

    def test_projection_preserves_real_world_scale(self) -> None:
        origin = self.geometry["origin"]
        _, north = local_xy(origin["lat"] + 0.001, origin["lon"])
        self.assertAlmostEqual(north, 111.2, delta=0.5)

    def test_every_doom_checkpoint_is_near_an_osm_path(self) -> None:
        world = self.catalog.entries["pardubice_jury_doom"].scenario.data["world"]
        segments = [segment for path in self.geometry["paths"] for segment in zip(path["line_m"], path["line_m"][1:])]
        for checkpoint in world["checkpoints"]:
            distance = min(point_segment_distance((checkpoint["x_m"], checkpoint["y_m"]), *segment) for segment in segments)
            self.assertLess(distance, 35, checkpoint["name"])

    def test_building_passages_survive_osm_conversion(self) -> None:
        passages = [path for path in self.geometry["paths"] if path.get("passage")]
        self.assertGreaterEqual(len(passages), 10)
        self.assertTrue(any(path.get("name") == "Zelenobranská" for path in passages))
        self.assertTrue(any(path.get("name") == "Příhrádek" for path in passages))


if __name__ == "__main__":
    unittest.main()
