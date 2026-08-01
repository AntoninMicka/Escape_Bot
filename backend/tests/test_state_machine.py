import unittest
from pathlib import Path

from escape_bot.protocol import Message
from escape_bot.scenario import ScenarioLoader, build_demo_checkpoint_catalog, build_scenario_progress
from escape_bot.state_machine import EscapeBotStateMachine, GamePhase


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


class StateMachineCheckpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.scenario = ScenarioLoader.load(str(SCENARIO_PATH))
        self.machine = EscapeBotStateMachine(self.scenario)
        self.machine.state.phase = GamePhase.NAVIGATING

    async def scan(self, checkpoint_id: str):
        token = self.scenario.data["checkpoints"][checkpoint_id]["token"]
        return await self.machine.handle(
            Message("qr.detected", {"value": f"escapebot://checkpoint/{token}"})
        )

    async def solve_reception(self):
        await self.scan("reception_archive")
        return await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "reception_deduction", "answer": "2147"})
        )

    @staticmethod
    def response(responses, message_type: str):
        return next(item for item in responses if item.type == message_type)

    async def test_unknown_qr_is_rejected(self) -> None:
        responses = await self.machine.handle(
            Message("qr.detected", {"value": "escapebot://checkpoint/not-a-real-token"})
        )

        result = self.response(responses, "qr.result")
        self.assertFalse(result.payload["accepted"])
        self.assertEqual(self.machine.state.checkpoint_states, {})

    async def test_checkpoint_order_is_enforced(self) -> None:
        responses = await self.scan("staircase_signal")

        result = self.response(responses, "qr.result")
        self.assertFalse(result.payload["accepted"])
        self.assertEqual(result.payload["missing"], ["reception_archive"])
        self.assertNotIn("semaphore", self.machine.state.unlocked_cipher_tools)

    async def test_checkpoint_reward_is_idempotent(self) -> None:
        await self.solve_reception()
        first = await self.scan("staircase_signal")
        second = await self.scan("staircase_signal")

        self.assertFalse(self.response(first, "qr.result").payload["duplicate"])
        self.assertTrue(self.response(second, "qr.result").payload["duplicate"])
        self.assertIn("semaphore", self.machine.state.unlocked_cipher_tools)
        self.assertEqual(len(self.machine.state.checkpoint_states), 2)

    async def test_paid_tool_is_only_charged_once(self) -> None:
        first = await self.machine.handle(Message("cipher_tool.unlock", {"tool_id": "pigpen"}))
        second = await self.machine.handle(Message("cipher_tool.unlock", {"tool_id": "pigpen"}))

        self.assertEqual(self.response(first, "cipher_tool.result").payload["charged"], 35)
        self.assertEqual(self.response(second, "cipher_tool.result").payload["charged"], 0)
        self.assertEqual(self.machine.state.score, 965)
        self.assertIn("pigpen", self.machine.state.paid_cipher_tools)

    async def test_room_requires_physical_checkpoint_even_with_correct_pin(self) -> None:
        denied = await self.machine.handle(Message("room.unlock", {"pin": "104"}))
        self.assertFalse(self.response(denied, "room.unlock_result").payload["success"])

        await self.solve_reception()
        granted = await self.machine.handle(Message("room.unlock", {"pin": "104"}))
        self.assertTrue(self.response(granted, "room.unlock_result").payload["success"])
        self.assertTrue(self.machine.state.flags["room_104_unlocked"])

    def test_default_tools_survive_old_session_restore(self) -> None:
        self.machine.restore_state({"score": 900})

        self.assertIn("morse", self.machine.state.unlocked_cipher_tools)
        self.assertIn("a1z26", self.machine.state.unlocked_cipher_tools)

    async def test_restart_unlocks_chronomap(self) -> None:
        self.machine.state.phase = GamePhase.CONNECTION_LOST
        await self.machine.handle(Message("player.message", {"text": "restart"}))

        self.assertEqual(self.machine.state.phase, GamePhase.NAVIGATING)
        self.assertTrue(self.machine.state.flags["chronomap_unlocked"])

    def test_demo_catalog_contains_every_checkpoint_in_scenario_order(self) -> None:
        catalog = build_demo_checkpoint_catalog(self.scenario)

        self.assertEqual([item["id"] for item in catalog], list(self.scenario.data["checkpoints"]))
        self.assertTrue(all(item["value"].startswith("escapebot://checkpoint/") for item in catalog))
        self.assertNotIn("token", catalog[0])

    def test_scenario_progress_marks_current_and_available_nodes(self) -> None:
        progress = build_scenario_progress(self.scenario, self.machine.state.snapshot())
        statuses = {node["id"]: node["status"] for node in progress["nodes"]}

        self.assertEqual(statuses["navigating"], "active")
        self.assertEqual(statuses["reception_archive"], "available")
        self.assertEqual(statuses["staircase_signal"], "locked")

    async def test_first_checkpoint_requires_navigating_phase(self) -> None:
        self.machine.state.phase = GamePhase.SEARCHING_LOST
        responses = await self.scan("reception_archive")

        result = self.response(responses, "qr.result")
        self.assertFalse(result.payload["accepted"])
        self.assertEqual(result.payload["required_phase"], "navigating")

    async def test_reception_puzzle_controls_checkpoint_completion(self) -> None:
        scanned = await self.scan("reception_archive")
        self.assertEqual(self.response(scanned, "qr.result").payload["status"], "found")
        self.assertEqual(self.machine.state.checkpoint_states["reception_archive"]["status"], "found")

        blocked = await self.scan("staircase_signal")
        self.assertFalse(self.response(blocked, "qr.result").payload["accepted"])

        wrong = await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "reception_deduction", "answer": "1234"})
        )
        self.assertFalse(self.response(wrong, "puzzle.result").payload["correct"])

        solved = await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "reception_deduction", "answer": "2147"})
        )
        self.assertTrue(self.response(solved, "puzzle.result").payload["correct"])
        self.assertEqual(self.machine.state.checkpoint_states["reception_archive"]["status"], "solved")
        self.assertTrue(self.machine.state.flags["reception_archive_unlocked"])

    async def test_reception_hint_charges_each_level_only_once(self) -> None:
        await self.scan("reception_archive")
        await self.machine.handle(Message("puzzle.hint", {"puzzle_id": "reception_deduction"}))

        self.assertEqual(self.machine.state.score, 990)
        self.assertEqual(self.machine.state.hints_used["puzzle.reception_deduction"], 1)


if __name__ == "__main__":
    unittest.main()
