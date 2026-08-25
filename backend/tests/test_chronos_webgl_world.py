import json
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
WORLD_PATH = PROJECT_DIR / "client" / "chronos-webgl" / "public" / "worlds" / "chronos-institute.json"
HORIZON_PATH = PROJECT_DIR / "client" / "chronos-webgl" / "public" / "assets" / "textures" / "chronos-horizon-v3.webp"
CLOUDS_PATH = PROJECT_DIR / "client" / "chronos-webgl" / "public" / "assets" / "textures" / "chronos-clouds-v1.png"
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

    def test_internal_stairs_share_a_clear_non_overlapping_shaft(self) -> None:
        stairs = [stair for stair in self.world["stairs"] if not stair.get("exterior")]
        for stair in stairs:
            with self.subTest(stair=stair["id"]):
                self.assertGreaterEqual(stair["x1"], 9)
                self.assertLessEqual(stair["x2"], 16)
                self.assertEqual((stair["z_from"], stair["z_to"]), (6, -4))

        for level in {-1, 0, 1}:
            landings = [
                stair for stair in stairs
                if level in {stair["from_level"], stair["to_level"]}
            ]
            self.assertEqual(len(landings), 2)
            self.assertTrue(
                landings[0]["x2"] < landings[1]["x1"]
                or landings[1]["x2"] < landings[0]["x1"]
            )

    def test_basement_has_a_separate_emergency_exit_to_ground_level(self) -> None:
        emergency = next(stair for stair in self.world["stairs"] if stair["id"] == "stairs_emergency")
        self.assertEqual((emergency["from_level"], emergency["to_level"]), (-1, 0))
        self.assertTrue(emergency["exterior"])
        self.assertLess(emergency["z_from"], -13)
        self.assertLess(emergency["z_to"], emergency["z_from"])

    def test_outdoor_layout_separates_terrace_stairs_and_sports_field(self) -> None:
        terrace_stairs = next(stair for stair in self.world["stairs"] if stair["id"] == "stairs_terrace")
        sports = next(zone for zone in self.world["zones"] if zone["id"] == "sports")
        pond = next(zone for zone in self.world["zones"] if zone["id"] == "pond")

        self.assertGreaterEqual(terrace_stairs["z_to"] - sports["bounds"][3], 1)
        self.assertLess(pond["bounds"][3], sports["bounds"][2])
        self.assertTrue(HORIZON_PATH.is_file())
        self.assertTrue(CLOUDS_PATH.is_file())

    def test_player_starts_inside_the_gate_next_to_the_car(self) -> None:
        spawn = self.world["spawn"]
        self.assertEqual(spawn["level"], 0)
        self.assertGreater(spawn["z"], -58)
        self.assertLess(spawn["z"], -48)
        self.assertLessEqual(abs(spawn["x"]), 4)

    def test_dining_room_and_two_level_lecture_hall_have_zones(self) -> None:
        zones = {(zone["id"], zone["level"]) for zone in self.world["zones"]}
        self.assertIn(("dining", 0), zones)
        self.assertIn(("lecture_hall_lower", 1), zones)
        self.assertIn(("lecture_hall_gallery", 2), zones)

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
