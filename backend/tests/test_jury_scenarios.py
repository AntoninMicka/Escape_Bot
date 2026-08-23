import unittest
from pathlib import Path

from escape_bot.protocol import Message
from escape_bot.scenario_catalog import load_scenario_catalog
from escape_bot.state_machine import EscapeBotStateMachine, GamePhase


BACKEND = Path(__file__).resolve().parents[1]


class JuryScenarioTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.catalog = load_scenario_catalog(BACKEND / "content" / "templates", BACKEND / "content" / "realizations")

    def test_geo_and_doom_share_story_and_checkpoint_contracts(self) -> None:
        geo = self.catalog.entries["pardubice_jury_geo"]
        doom = self.catalog.entries["pardubice_jury_doom"]

        self.assertEqual(geo.template_id, "jury_deliberation")
        self.assertEqual(doom.template_id, "jury_deliberation")
        self.assertEqual(geo.scenario.data["world"]["mode"], "geo")
        self.assertEqual(doom.scenario.data["world"]["mode"], "doom")
        self.assertEqual(doom.scenario.data["world"]["virtual_map"]["meters_per_unit"], 1)
        self.assertEqual(
            [item["contract"] for item in geo.scenario.data["world"]["checkpoints"]],
            [item["contract"] for item in doom.scenario.data["world"]["checkpoints"]],
        )

    async def test_geo_position_unlocks_checkpoint_on_server(self) -> None:
        scenario = self.catalog.entries["pardubice_jury_geo"].scenario
        machine = EscapeBotStateMachine(scenario)
        machine.state.phase = GamePhase.NAVIGATING
        point = scenario.data["world"]["checkpoints"][0]

        responses = await machine.handle(Message("geo.position", {
            "lat": point["lat"], "lon": point["lon"], "accuracy": 5,
        }))

        geo_result = next(item for item in responses if item.type == "geo.result")
        self.assertTrue(geo_result.payload["accepted"])
        self.assertIn(point["node_id"], machine.state.checkpoint_states)

    async def test_geo_position_rejects_inaccurate_fix(self) -> None:
        scenario = self.catalog.entries["pardubice_jury_geo"].scenario
        machine = EscapeBotStateMachine(scenario)
        point = scenario.data["world"]["checkpoints"][0]

        responses = await machine.handle(Message("geo.position", {
            "lat": point["lat"], "lon": point["lon"], "accuracy": 80,
        }))

        self.assertFalse(responses[0].payload["accepted"])
        self.assertIn("nepřesná", responses[0].payload["reason"])
