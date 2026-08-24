import json
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
WORLD_PATH = PROJECT_DIR / "client" / "chronos-webgl" / "public" / "worlds" / "chronos-institute.json"
REALIZATION_PATH = BACKEND_DIR / "content" / "realizations" / "chronos_online.json"


class ChronosWebglWorldTest(unittest.TestCase):
    def setUp(self) -> None:
        self.world = json.loads(WORLD_PATH.read_text(encoding="utf-8"))
        self.realization = json.loads(REALIZATION_PATH.read_text(encoding="utf-8"))

    def test_world_and_realization_share_checkpoint_contract(self) -> None:
        scenario_ids = {
            checkpoint["id"]
            for checkpoint in self.realization["variables"]["checkpoints"].values()
        }
        world_ids = {checkpoint["id"] for checkpoint in self.world["checkpoints"]}

        self.assertEqual(world_ids, scenario_ids)
        self.assertEqual(self.world["optional_room"]["id"], "room_104")
        self.assertEqual(self.realization["variables"]["rooms"]["optional_archive"]["number"], "104")

    def test_all_levels_are_connected_by_physical_stairs(self) -> None:
        level_ids = {level["id"] for level in self.world["levels"]}
        graph = {level_id: set() for level_id in level_ids}
        for stair in self.world["stairs"]:
            source, target = stair["from_level"], stair["to_level"]
            self.assertIn(source, level_ids)
            self.assertIn(target, level_ids)
            self.assertNotEqual(source, target)
            graph[source].add(target)
            graph[target].add(source)

        reachable, pending = set(), [0]
        while pending:
            level = pending.pop()
            if level in reachable:
                continue
            reachable.add(level)
            pending.extend(graph[level] - reachable)

        self.assertEqual(reachable, level_ids)

    def test_every_interaction_lies_inside_a_declared_zone(self) -> None:
        points = [*self.world["checkpoints"], self.world["optional_room"]]
        level_ids = {level["id"] for level in self.world["levels"]}
        for point in points:
            with self.subTest(point=point["id"]):
                self.assertIn(point["level"], level_ids)
                x, _, z = point["position"]
                self.assertTrue(any(
                    zone["level"] == point["level"]
                    and zone["bounds"][0] <= x <= zone["bounds"][1]
                    and zone["bounds"][2] <= z <= zone["bounds"][3]
                    for zone in self.world["zones"]
                ))

        final_console = next(point for point in points if point["id"] == "time_machine_console")
        self.assertEqual(final_console["level"], -2)


if __name__ == "__main__":
    unittest.main()
