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

    async def solve_staircase(self):
        await self.solve_reception()
        await self.scan("staircase_signal")
        return await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "staircase_semaphore", "answer": "BOWLING"})
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
        solutions = {node["id"]: node["solution"] for node in progress["nodes"]}
        self.assertEqual(solutions["searching_lost"], "734")
        self.assertIn("2147", solutions["reception_archive"])

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

    async def test_staircase_puzzle_unlocks_bowling_checkpoint(self) -> None:
        await self.solve_reception()
        scanned = await self.scan("staircase_signal")
        self.assertEqual(self.response(scanned, "qr.result").payload["status"], "found")
        self.assertIn("semaphore", self.machine.state.unlocked_cipher_tools)

        blocked = await self.scan("bowling_diagnostics")
        self.assertFalse(self.response(blocked, "qr.result").payload["accepted"])

        solved = await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "staircase_semaphore", "answer": "bowling"})
        )
        self.assertTrue(self.response(solved, "puzzle.result").payload["correct"])
        self.assertTrue(self.machine.state.flags["bowling_route_unlocked"])

        allowed = await self.scan("bowling_diagnostics")
        self.assertTrue(self.response(allowed, "qr.result").payload["accepted"])

    async def test_staircase_puzzle_has_no_hints(self) -> None:
        await self.solve_reception()
        await self.scan("staircase_signal")
        puzzle_state = next(item for item in self.machine._puzzle_state() if item["id"] == "staircase_semaphore")
        self.assertFalse(puzzle_state["has_hints"])
        self.assertEqual(puzzle_state["image"], "assets/puzzles/elara-clock-gallery.png")
        self.assertEqual(puzzle_state["categories"], {})
        self.assertEqual(puzzle_state["clues"], [])

        responses = await self.machine.handle(Message("puzzle.hint", {"puzzle_id": "staircase_semaphore"}))
        error = self.response(responses, "error")
        self.assertIn("Nejsou dostupné", error.payload["message"])
        self.assertEqual(self.machine.state.score, 1000)

    async def test_bowling_binary_puzzle_awards_temporal_motor(self) -> None:
        await self.solve_staircase()
        scanned = await self.scan("bowling_diagnostics")

        self.assertEqual(self.response(scanned, "qr.result").payload["status"], "found")
        self.assertIn("binary_ascii", self.machine.state.unlocked_cipher_tools)
        self.assertNotIn("TEMPORÁLNÍ MOTOR", self.machine.state.inventory)

        wrong = await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "bowling_binary", "answer": "KUZELKY"})
        )
        self.assertFalse(self.response(wrong, "puzzle.result").payload["correct"])

        solved = await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "bowling_binary", "answer": "motor"})
        )
        self.assertTrue(self.response(solved, "puzzle.result").payload["correct"])
        self.assertIn("TEMPORÁLNÍ MOTOR", self.machine.state.inventory)
        self.assertTrue(self.machine.state.flags["temporal_motor_recovered"])

    async def test_bowling_puzzle_is_image_only_and_has_no_hints(self) -> None:
        await self.solve_staircase()
        await self.scan("bowling_diagnostics")
        puzzle_state = next(item for item in self.machine._puzzle_state() if item["id"] == "bowling_binary")

        self.assertEqual(puzzle_state["image"], "assets/puzzles/bowling-binary-motor-v3.png")
        self.assertFalse(puzzle_state["has_hints"])
        self.assertEqual(puzzle_state["categories"], {})
        self.assertEqual(puzzle_state["clues"], [])


if __name__ == "__main__":
    unittest.main()
