import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from escape_bot.protocol import Message
from escape_bot.line_game import completion_time_score
from escape_bot.mine_karel import new_game as new_karel, public_game as public_karel, safe_path, validate_level
from escape_bot.sokoban import execute as execute_sokoban, new_game as new_sokoban, parse_commands
from escape_bot.team_lobby import LobbyRegistry, classify_activity, team_size_adjustment
from escape_bot.scenario import Scenario, ScenarioLoader, build_checkpoint_qr_set, build_demo_checkpoint_catalog, build_puzzle_telemetry, build_scenario_progress, validate_checkpoint_navigation
from escape_bot.state_machine import EscapeBotStateMachine, GamePhase


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


class StateMachineCheckpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.scenario = ScenarioLoader.load(str(SCENARIO_PATH))
        self.machine = EscapeBotStateMachine(self.scenario)
        self.machine.state.phase = GamePhase.NAVIGATING

    def test_every_declared_voice_has_a_local_audio_file(self) -> None:
        declarations = []

        def collect(value):
            if isinstance(value, dict):
                if value.get("voice_id"):
                    declarations.append(value)
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(self.scenario.data)
        self.assertTrue(declarations)
        for declaration in declarations:
            audio_url = declaration.get("audio_url", "")
            self.assertTrue(audio_url.startswith("/assets/voices/"), declaration["voice_id"])
            audio_path = SCENARIO_PATH.parents[1] / "client" / audio_url.lstrip("/")
            self.assertTrue(audio_path.is_file(), declaration["voice_id"])
            self.assertGreater(audio_path.stat().st_size, 10_000, declaration["voice_id"])

    def test_team_line_games_are_independent_and_require_full_team_coverage(self) -> None:
        self.machine._team_mode = "team"
        self.machine._participant_ids = ["alice", "bob"]
        config = self.scenario.data["puzzles"]["timeline_lines"]["game"]
        alice = self.machine._line_game_state("timeline_lines", config, "alice")
        bob = self.machine._line_game_state("timeline_lines", config, "bob")
        self.assertIsNot(alice, bob)
        alice["progress"] = {"3": 5, "4": 3, "5": 0}; alice["status"] = "complete"
        bob["progress"] = {"3": 5, "4": 3, "5": 0}; bob["status"] = "complete"
        self.assertFalse(self.machine._team_conditions_complete("timeline_lines", "line_game"))
        bob["progress"] = {"3": 0, "4": 3, "5": 1}
        self.assertTrue(self.machine._team_conditions_complete("timeline_lines", "line_game"))
        progress = self.machine._team_game_progress("timeline_lines", "line_game")
        self.assertEqual(progress["missing_conditions"], [])
        self.assertEqual(len(progress["players"]), 2)

    def test_team_triad_games_require_each_player_and_all_three_directions(self) -> None:
        self.machine._team_mode = "team"
        self.machine._participant_ids = ["alice", "bob"]
        config = self.scenario.data["puzzles"]["temporal_triad"]["game"]
        alice = self.machine._triad_state("temporal_triad", config, "alice")
        bob = self.machine._triad_state("temporal_triad", config, "bob")
        alice["completed_orientations"] = ["horizontal", "vertical"]; alice["status"] = "complete"
        bob["completed_orientations"] = ["horizontal", "vertical"]
        self.assertFalse(self.machine._team_conditions_complete("temporal_triad", "triad"))
        bob["status"] = "complete"
        self.assertFalse(self.machine._team_conditions_complete("temporal_triad", "triad"))
        bob["completed_orientations"] = ["vertical", "diagonal"]
        self.assertTrue(self.machine._team_conditions_complete("temporal_triad", "triad"))

    def test_team_progress_recommends_only_the_single_missing_condition_and_honors_exclusion(self) -> None:
        self.machine._team_mode = "team"; self.machine._participant_ids = ["alice", "bob", "cara"]
        self.machine._participant_names = {"alice": "Alice", "bob": "Bob", "cara": "Cara"}
        config = self.scenario.data["puzzles"]["temporal_triad"]["game"]
        for player_id in self.machine._participant_ids:
            game = self.machine._triad_state("temporal_triad", config, player_id)
            game["completed_orientations"] = ["horizontal", "vertical"]
        progress = self.machine._team_game_progress("temporal_triad", "triad")
        self.assertEqual(progress["recommendation"], "diagonal")
        self.machine.state.game_exclusions["temporal_triad"] = ["cara"]
        progress = self.machine._team_game_progress("temporal_triad", "triad")
        self.assertEqual(next(item for item in progress["players"] if item["id"] == "cara")["status"], "excluded")
        for player_id in ("alice", "bob"):
            self.machine.state.triad_games["temporal_triad"]["players"][player_id]["status"] = "complete"
        self.assertTrue(self.machine._team_conditions_complete("temporal_triad", "triad"))

    def test_operating_hours_reserve_enough_time_to_finish_before_closing(self) -> None:
        from escape_bot.server import runtime_settings, start_availability
        original = dict(runtime_settings)
        try:
            runtime_settings.update({"gameplay_enabled": True, "opening_time": "08:00", "closing_time": "20:00",
                                     "game_duration_minutes": 120, "start_interval_minutes": 0,
                                     "max_active_teams": 4, "timezone": "Europe/Prague"})
            zone = ZoneInfo("Europe/Prague")
            self.assertFalse(start_availability(datetime(2026, 8, 21, 7, 59, tzinfo=zone))["start_allowed"])
            self.assertTrue(start_availability(datetime(2026, 8, 21, 17, 59, tzinfo=zone))["start_allowed"])
            result = start_availability(datetime(2026, 8, 21, 18, 1, tzinfo=zone))
            self.assertFalse(result["start_allowed"])
            self.assertEqual(datetime.fromisoformat(result["latest_start_at"]).strftime("%H:%M"), "18:00")
            runtime_settings["gameplay_enabled"] = False
            self.assertFalse(start_availability(datetime(2026, 8, 21, 10, 0, tzinfo=zone))["start_allowed"])
        finally:
            runtime_settings.clear(); runtime_settings.update(original)

    def test_deadline_closes_game_and_applies_penalty_only_once(self) -> None:
        from escape_bot.server import apply_deadline_end
        ended_at = datetime.now(UTC).isoformat()
        initial_score = self.machine.state.score

        updates = apply_deadline_end(self.machine, ended_at, 100)

        self.assertTrue(self.machine.state.flags["administratively_ended"])
        self.assertEqual(self.machine.state.flags["administratively_ended_reason"], "deadline")
        self.assertEqual(self.machine.state.score, initial_score - 100)
        self.assertEqual(len(self.machine.state.flags["admin_score_adjustments"]), 1)
        self.assertEqual(updates[0].type, "score.update")
        self.assertEqual(updates[0].payload["reason"], "deadline_penalty")

        apply_deadline_end(self.machine, ended_at, 100)
        self.assertEqual(self.machine.state.score, initial_score - 100)
        self.assertEqual(len(self.machine.state.flags["admin_score_adjustments"]), 1)

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

    async def solve_bowling(self):
        await self.solve_staircase()
        await self.solve_karel()
        await self.scan("bowling_diagnostics")
        return await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "bowling_binary", "answer": "MOTOR"})
        )

    async def solve_karel(self):
        await self.scan("courtyard_minefield")
        solutions = [
            ["down"] * 4 + ["right"] * 2 + ["down"] + ["right"] * 2 + ["down"] + ["right"] * 2,
            ["up"] * 2 + ["right"] * 2 + ["up"] * 2 + ["right"] * 2 + ["up"] * 2 + ["right"] * 2,
            ["down"] * 3 + ["right"] * 2 + ["up"] + ["right"] * 3 + ["down"] * 3 + ["right"] * 2 + ["down"] * 2,
        ]
        response = None
        for commands in solutions:
            response = await self.machine.handle(Message("karel.command", {"puzzle_id": "courtyard_karel", "commands": commands}))
        return response

    async def unlock_timeline_game(self):
        await self.solve_bowling()
        return await self.scan("timeline_calibration")

    async def line_swap(self, first: list[int], second: list[int]):
        return await self.machine.handle(Message("line_game.move", {
            "puzzle_id": "timeline_lines", "first": first, "second": second,
        }))

    def prepare_five_match(self):
        game = self.machine.state.interactive_games["timeline_lines"]
        colors = self.scenario.data["puzzles"]["timeline_lines"]["game"]["colors"]
        game["board"] = [[colors[(row + column) % len(colors)] for column in range(7)] for row in range(7)]
        for column in range(4):
            game["board"][0][column] = "cyan"
        game["board"][0][4] = "violet"
        game["board"][1][4] = "cyan"
        return game

    async def unlock_sokoban(self):
        await self.unlock_timeline_game()
        game = self.prepare_five_match()
        game["progress"] = {"3": 5, "4": 3, "5": 0}
        await self.line_swap([0, 4], [1, 4])
        await self.scan("terrace_echo")
        await self.machine.handle(Message("puzzle.submit", {"puzzle_id": "terrace_morse", "answer": "HŘIŠTĚ"}))
        await self.scan("courtyard_alignment")
        for row, column, symbol in [(5,1,"cyan"),(0,0,"cyan"),(2,1,"cyan"),(3,4,"cyan"),(5,2,"cyan"),(2,4,"cyan"),(0,2,"cyan"),(5,3,"cyan"),(4,0,"cyan"),(1,1,"amber"),(3,0,"cyan"),(3,2,"cyan"),(1,0,"cyan")]:
            await self.machine.handle(Message("triad.place", {"puzzle_id":"temporal_triad","row":row,"column":column,"symbol":symbol}))
        return await self.scan("sports_archive")

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

    def test_admin_qr_set_matches_scenario_order(self) -> None:
        qr_set = build_checkpoint_qr_set(self.scenario)
        self.assertEqual([item["id"] for item in qr_set], [node["id"] for node in self.scenario.data["scenario_flow"] if node["id"] in self.scenario.data["checkpoints"]])
        self.assertTrue(all(str(item["value"]).startswith("escapebot://checkpoint/") for item in qr_set))

    def test_every_checkpoint_points_to_immediate_next_station(self) -> None:
        validate_checkpoint_navigation(self.scenario)
        broken = deepcopy(self.scenario.data)
        broken["checkpoints"]["staircase_signal"]["next_checkpoint"] = "bowling_diagnostics"
        with self.assertRaisesRegex(ValueError, "courtyard_minefield"):
            validate_checkpoint_navigation(Scenario(broken))

    async def test_staircase_warns_when_room_104_was_skipped(self) -> None:
        self.machine.admin_set_checkpoint("reception_archive", "solved")
        scanned = await self.scan("staircase_signal")
        messages = [item.payload.get("text", "") for item in scanned if item.type == "bot.message"]
        self.assertTrue(any("pokoj 104" in text for text in messages))

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

    def test_scenario_can_present_every_cipher_tool_without_paid_unlock(self) -> None:
        payload = self.machine._state_message().payload

        self.assertEqual(self.scenario.data["cipher_tools_access"], "all")
        self.assertTrue(payload["cipher_tools"])
        self.assertTrue(all(tool["status"] == "unlocked" for tool in payload["cipher_tools"]))

    async def test_room_requires_physical_checkpoint_even_with_correct_pin(self) -> None:
        room_pin = self.scenario.data["rooms"]["104"]["pin"]
        denied = await self.machine.handle(Message("room.unlock", {"pin": room_pin}))
        self.assertFalse(self.response(denied, "room.unlock_result").payload["success"])

        await self.solve_reception()
        granted = await self.machine.handle(Message("room.unlock", {"pin": room_pin}))
        self.assertTrue(self.response(granted, "room.unlock_result").payload["success"])
        self.assertTrue(self.machine.state.flags["room_104_unlocked"])

    async def test_room_pin_has_locked_progressive_hints(self) -> None:
        room = self.scenario.data["rooms"]["104"]
        self.assertEqual(room["pin"], "1104")
        self.assertNotIn(room["pin"], room["clue"])

        locked = await self.machine.handle(Message("room.hint", {"room_id": "104"}))
        self.assertNotIn("Tři skupiny", self.response(locked, "bot.message").payload["text"])

        await self.solve_reception()
        room_puzzle = next(item for item in self.machine._puzzle_state() if item["id"] == "room_104_panel")
        self.assertEqual(room_puzzle["type"], "room_pin")
        self.assertEqual(room_puzzle["hint_count"], 3)
        score_before = self.machine.state.score
        hint = await self.machine.handle(Message("room.hint", {"room_id": "104"}))
        self.assertIn("Tři skupiny", self.response(hint, "bot.message").payload["text"])
        self.assertEqual(self.machine.state.score, score_before - 10)
        self.assertEqual(self.machine.state.hints_used["room_104"], 1)

    def test_default_tools_survive_old_session_restore(self) -> None:
        self.machine.restore_state({"score": 900})

        self.assertIn("morse", self.machine.state.unlocked_cipher_tools)
        self.assertIn("a1z26", self.machine.state.unlocked_cipher_tools)

    async def test_game_events_are_audited_and_restored(self) -> None:
        await self.machine.handle(Message("puzzle.hint", {"puzzle_id": "reception_deduction"}))

        event = self.machine.state.event_history[-1]
        self.assertEqual(event["type"], "puzzle.hint")
        self.assertEqual(event["details"]["puzzle_id"], "reception_deduction")
        self.assertTrue(event["at"])

        restored = EscapeBotStateMachine(self.scenario)
        restored.restore_state(self.machine.state.snapshot())
        self.assertEqual(restored.state.event_history, self.machine.state.event_history)

    def test_puzzle_telemetry_reports_duration_attempts_hints_and_actions(self) -> None:
        self.machine.state.checkpoint_states["reception_archive"] = {
            "status": "solved",
            "first_scanned_at": "2026-08-03T10:00:00+00:00",
            "solved_at": "2026-08-03T10:20:00+00:00",
        }
        self.machine.state.puzzle_attempts["reception_deduction"] = 3
        self.machine.state.hints_used["puzzle.reception_deduction"] = 2
        self.machine.state.event_history = [
            {"at": "2026-08-03T10:02:00+00:00", "type": "puzzle.submit", "details": {"puzzle_id": "reception_deduction"}},
            {"at": "2026-08-03T10:18:00+00:00", "type": "puzzle.hint", "details": {"puzzle_id": "reception_deduction"}},
        ]

        metric = next(item for item in build_puzzle_telemetry(self.scenario, self.machine.state.snapshot()) if item["puzzle_id"] == "reception_deduction")

        self.assertEqual(metric["elapsed_seconds"], 1200)
        self.assertEqual(metric["active_seconds"], 540)
        self.assertEqual(metric["attempts"], 3)
        self.assertEqual(metric["hints"], 2)
        self.assertEqual(metric["actions"], 2)

    async def test_frequency_connects_elara_and_unlocks_chronomap(self) -> None:
        self.machine.state.phase = GamePhase.SEARCHING_LOST
        responses = await self.machine.handle(Message("player.message", {"text": "734"}))
        self.assertEqual(self.machine.state.phase, GamePhase.NAVIGATING)
        self.assertTrue(self.machine.state.flags["chronomap_unlocked"])
        messages = " ".join(item.payload.get("text", "") for item in responses if item.type == "bot.message")
        self.assertIn("recepčního archivu", messages)
        self.assertNotIn("CHRONOSIGNÁL ZTRACEN", messages)

    def test_legacy_connection_failure_session_migrates_to_navigation(self) -> None:
        for legacy_phase in (GamePhase.LOST_CONNECTED, GamePhase.CONNECTION_LOST):
            with self.subTest(legacy_phase=legacy_phase):
                snapshot = self.machine.state.snapshot()
                snapshot["phase"] = legacy_phase.value
                snapshot["flags"] = {}
                restored = EscapeBotStateMachine(self.scenario)
                restored.restore_state(snapshot)
                self.assertEqual(restored.state.phase, GamePhase.NAVIGATING)
                self.assertTrue(restored.state.flags["chronomap_unlocked"])

    def test_story_bible_data_defines_timeline_and_time_travel_rules(self) -> None:
        self.assertGreaterEqual(len(self.scenario.data["time_travel_rules"]), 7)
        timeline_ids = {item["id"] for item in self.scenario.data["story_timeline"]}
        self.assertIn("accident", timeline_ids)
        self.assertIn("return", timeline_ids)
        self.assertIn("není v jiné budově, dimenzi", self.scenario.data["knowledge_base"])

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
        self.assertIn("2037", solutions["time_machine_finale"])

    def test_every_puzzle_has_an_admin_solution(self) -> None:
        missing = [puzzle_id for puzzle_id, puzzle in self.scenario.data["puzzles"].items() if not puzzle.get("admin_solution")]
        self.assertEqual(missing, [])

    async def test_intro_frequency_puzzle_provides_signal_without_revealing_answer(self) -> None:
        self.machine.state.phase = GamePhase.COMMS_OFFLINE
        responses = await self.machine.handle(Message("player.message", {"text": "Příjem."}))
        message = self.response(responses, "bot.message").payload["text"]

        self.assertIn("NOSNÁ VLNA C-17", message)
        self.assertIn("━━", message)
        self.assertIn("●", message)
        self.assertNotIn("734", message)
        self.assertNotIn("734", self.scenario.data["scenario_flow"][1]["label"])

        state = self.machine._state_message().payload["phase_hints"]
        self.assertEqual(state["count"], 3)
        first = await self.machine.handle(Message("phase.hint", {"phase_id": "searching_lost", "hint_index": 0}))
        score_after_unlock = self.machine.state.score
        repeated = await self.machine.handle(Message("phase.hint", {"phase_id": "searching_lost", "hint_index": 0}))
        self.assertEqual(self.machine.state.score, score_after_unlock)
        self.assertIn("Každá skupina", self.response(first, "bot.message").payload["text"])
        self.assertIn("Každá skupina", self.response(repeated, "bot.message").payload["text"])

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
        await self.machine.handle(Message("puzzle.hint", {"puzzle_id": "reception_deduction", "hint_index": 0}))
        await self.machine.handle(Message("puzzle.hint", {"puzzle_id": "reception_deduction", "hint_index": 0}))

        self.assertEqual(self.machine.state.score, 990)
        self.assertEqual(self.machine.state.hints_used["puzzle.reception_deduction"], 1)

        locked = await self.machine.handle(Message("puzzle.hint", {"puzzle_id": "reception_deduction", "hint_index": 2}))
        self.assertIn("předchozí", self.response(locked, "error").payload["message"])

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
        messages = [item.payload.get("text", "") for item in solved if item.type == "bot.message"]
        self.assertTrue(any("nádvoří" in text for text in messages))

        await self.solve_karel()
        allowed = await self.scan("bowling_diagnostics")
        self.assertTrue(self.response(allowed, "qr.result").payload["accepted"])

    async def test_staircase_puzzle_has_three_hints(self) -> None:
        await self.solve_reception()
        await self.scan("staircase_signal")
        puzzle_state = next(item for item in self.machine._puzzle_state() if item["id"] == "staircase_semaphore")
        self.assertTrue(puzzle_state["has_hints"])
        self.assertEqual(puzzle_state["hint_count"], 3)
        self.assertEqual(puzzle_state["image"], "assets/puzzles/elara-clock-gallery.png")
        self.assertEqual(puzzle_state["categories"], {})
        self.assertEqual(puzzle_state["clues"], [])

        responses = await self.machine.handle(Message("puzzle.hint", {"puzzle_id": "staircase_semaphore", "hint_index": 0}))
        self.assertIn("ručiček", self.response(responses, "bot.message").payload["text"])
        self.assertEqual(self.machine.state.score, 990)

    def test_every_cipher_puzzle_has_exactly_three_hints(self) -> None:
        cipher_types = {"semaphore", "binary_image", "morse_image", "pigpen", "archive_vector"}
        cipher_puzzles = [puzzle for puzzle in self.scenario.data["puzzles"].values() if puzzle.get("type") in cipher_types]
        self.assertTrue(cipher_puzzles)
        self.assertTrue(all(len(puzzle.get("hints", [])) == 3 for puzzle in cipher_puzzles))

    async def test_bowling_binary_puzzle_awards_temporal_motor(self) -> None:
        await self.solve_staircase()
        await self.solve_karel()
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

    async def test_bowling_puzzle_is_image_only_and_has_three_hints(self) -> None:
        await self.solve_staircase()
        await self.solve_karel()
        await self.scan("bowling_diagnostics")
        puzzle_state = next(item for item in self.machine._puzzle_state() if item["id"] == "bowling_binary")

        self.assertEqual(puzzle_state["image"], "assets/puzzles/bowling-binary-motor-v3.png")
        self.assertTrue(puzzle_state["has_hints"])
        self.assertEqual(puzzle_state["hint_count"], 3)
        self.assertEqual(puzzle_state["categories"], {})
        self.assertEqual(puzzle_state["clues"], [])

    async def test_terrace_morse_awards_phase_stabilizer(self) -> None:
        await self.unlock_timeline_game()
        game = self.prepare_five_match(); game["progress"] = {"3": 5, "4": 3, "5": 0}
        await self.line_swap([0, 4], [1, 4])
        scanned = await self.scan("terrace_echo")

        self.assertEqual(self.response(scanned, "qr.result").payload["status"], "found")
        self.assertNotIn("FÁZOVÝ STABILIZÁTOR", self.machine.state.inventory)
        blocked = await self.scan("sports_archive")
        self.assertFalse(self.response(blocked, "qr.result").payload["accepted"])

        solved = await self.machine.handle(
            Message("puzzle.submit", {"puzzle_id": "terrace_morse", "answer": "hřiště"})
        )
        self.assertTrue(self.response(solved, "puzzle.result").payload["correct"])
        self.assertIn("FÁZOVÝ STABILIZÁTOR", self.machine.state.inventory)
        self.assertTrue(self.machine.state.flags["phase_stabilizer_recovered"])

        triad = await self.scan("courtyard_alignment")
        self.assertTrue(self.response(triad, "qr.result").payload["accepted"])
        sports = await self.scan("sports_archive")
        self.assertFalse(self.response(sports, "qr.result").payload["accepted"])

    async def test_terrace_puzzle_is_image_only_and_has_three_hints(self) -> None:
        await self.unlock_timeline_game()
        game = self.prepare_five_match(); game["progress"] = {"3": 5, "4": 3, "5": 0}
        await self.line_swap([0, 4], [1, 4])
        await self.scan("terrace_echo")
        puzzle_state = next(item for item in self.machine._puzzle_state() if item["id"] == "terrace_morse")

        self.assertEqual(puzzle_state["image"], "assets/puzzles/terrace-morse-cats-hriste-v2.png")
        self.assertTrue(puzzle_state["has_hints"])
        self.assertEqual(puzzle_state["hint_count"], 3)
        self.assertEqual(puzzle_state["categories"], {})
        self.assertEqual(puzzle_state["clues"], [])

    async def test_line_game_is_locked_until_its_qr_is_scanned(self) -> None:
        responses = await self.line_swap([0, 0], [0, 1])

        result = self.response(responses, "line_game.result")
        self.assertFalse(result.payload["success"])
        self.assertNotIn("timeline_lines", self.machine.state.interactive_games)

    async def test_line_game_rejects_non_adjacent_swap_and_persists_state(self) -> None:
        await self.unlock_timeline_game()
        game = self.machine.state.interactive_games["timeline_lines"]
        original_board = [row[:] for row in game["board"]]
        rejected = await self.line_swap([0, 0], [2, 2])

        self.assertFalse(self.response(rejected, "line_game.result").payload["success"])
        self.assertEqual(game["board"], original_board)
        self.assertEqual(game["swaps"], 0)
        restored = EscapeBotStateMachine(self.scenario)
        restored.restore_state(self.machine.state.snapshot())
        self.assertEqual(restored.state.interactive_games["timeline_lines"], game)

    async def test_line_game_objectives_can_be_completed_in_free_order(self) -> None:
        await self.unlock_timeline_game()
        game = self.prepare_five_match()
        response = await self.line_swap([0, 4], [1, 4])

        result = self.response(response, "line_game.result").payload
        self.assertTrue(result["success"])
        self.assertEqual(result["animation_frames"][0]["phase"], "swap")
        self.assertIn("clear", {frame["phase"] for frame in result["animation_frames"]})
        self.assertEqual(result["animation_frames"][-1]["board"], game["board"])
        self.assertEqual(game["progress"]["5"], 1)
        self.assertLess(game["progress"]["3"], 5)
        self.assertLess(game["progress"]["4"], 3)
        self.assertEqual(game["status"], "playing")

    async def test_line_game_completion_unlocks_sports(self) -> None:
        await self.unlock_timeline_game()
        game = self.prepare_five_match()
        game["progress"] = {"3": 5, "4": 3, "5": 0}
        score_before = self.machine.state.score
        final_response = await self.line_swap([0, 4], [1, 4])

        self.assertTrue(self.response(final_response, "line_game.result").payload["game_complete"])
        score_update = self.response(final_response, "score.update")
        self.assertGreater(score_update.payload["delta"], 0)
        self.assertEqual(self.machine.state.score, score_before + score_update.payload["delta"])
        self.assertEqual(self.machine.state.checkpoint_states["timeline_calibration"]["status"], "solved")
        self.assertTrue(self.machine.state.flags["timeline_calibrated"])
        directions = " ".join(
            str(item.payload.get("text", ""))
            for item in final_response
            if item.type == "bot.message"
        ).casefold()
        self.assertIn("terasu u rybníka", directions)
        terrace = await self.scan("terrace_echo")
        self.assertTrue(self.response(terrace, "qr.result").payload["accepted"])

    async def test_line_game_time_limit_and_reset(self) -> None:
        await self.unlock_timeline_game()
        game = self.machine.state.interactive_games["timeline_lines"]
        game["progress"] = {"3": 4, "4": 2, "5": 0}
        game["deadline_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        expired = await self.line_swap([0, 0], [0, 1])
        self.assertFalse(self.response(expired, "line_game.result").payload["success"])
        self.assertEqual(game["status"], "expired")

        responses = await self.machine.handle(Message("line_game.reset", {"puzzle_id": "timeline_lines"}))

        self.assertTrue(self.response(responses, "line_game.result").payload["reset"])
        self.assertEqual(game["progress"], {"3": 0, "4": 0, "5": 0})
        self.assertEqual(game["swaps"], 0)
        self.assertEqual(game["status"], "playing")

    def test_line_game_time_score_changes_sign_at_three_minutes(self) -> None:
        config = self.scenario.data["puzzles"]["timeline_lines"]["game"]
        started = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        game = {"started_at": started.isoformat()}

        self.assertEqual(completion_time_score(config, game, started + timedelta(seconds=60)), 60)
        self.assertEqual(completion_time_score(config, game, started + timedelta(seconds=180)), 0)
        self.assertEqual(completion_time_score(config, game, started + timedelta(seconds=240)), -30)

    def test_sokoban_parser_accepts_czech_sequences_and_repetition(self) -> None:
        self.assertEqual(
            parse_commands("vpravo, nahoru, 2x vlevo, dolů"),
            ["right", "up", "left", "left", "down"],
        )
        self.assertEqual(parse_commands("zpět"), ["undo"])
        self.assertIsNone(parse_commands("co vidíš kolem sebe?"))

    async def test_sokoban_rewards_are_delayed_until_intercom_solution(self) -> None:
        scanned = await self.unlock_sokoban()
        self.assertEqual(self.response(scanned, "qr.result").payload["status"], "found")
        self.assertNotIn("KRYSTAL ČASOVÉ KOTVY", self.machine.state.inventory)
        self.assertNotIn("pigpen", self.machine.state.unlocked_cipher_tools)

        score_before = self.machine.state.score
        solutions = [
            "4x nahoru, vlevo, 2x dolů, vpravo, dolů, vlevo, vpravo, dolů, 2x vlevo",
            "nahoru, 2x vpravo, dolů, vpravo, dolů, vlevo, 3x nahoru, vpravo, dolů, vlevo, dolů, vlevo, dolů, vpravo, dolů, vlevo",
            "nahoru, 3x vpravo, dolů, vlevo, nahoru, vlevo, dolů, vpravo, dolů, 2x vlevo, 2x dolů, 2x vpravo, nahoru, 2x vpravo, 2x dolů, vlevo, nahoru",
        ]
        responses = None
        for index, solution in enumerate(solutions):
            responses = await self.machine.handle(Message("player.message", {"channel": "lost", "text": solution}))
            self.assertEqual(self.response(responses, "score.update").payload["delta"], 30)
            animation = self.response(responses, "sokoban.result").payload["frames"]
            self.assertTrue(animation)
            self.assertIn(animation[0]["command"], {"up", "down", "left", "right"})
            self.assertIn("player", animation[0])
            self.assertIn("boxes", animation[0])
            if index < 2:
                self.assertTrue(self.response(responses, "sokoban.result").payload["level_complete"])
                self.assertFalse(self.response(responses, "sokoban.result").payload["game_complete"])

        result = self.response(responses, "sokoban.result")
        self.assertTrue(result.payload["game_complete"])
        self.assertEqual(self.machine.state.score, score_before + 90)
        self.assertEqual(self.machine.state.checkpoint_states["sports_archive"]["status"], "solved")
        self.assertNotIn("KRYSTAL ČASOVÉ KOTVY", self.machine.state.inventory)
        self.assertIn("pigpen", self.machine.state.unlocked_cipher_tools)
        bot_messages = [item.payload for item in responses if item.type == "bot.message"]
        self.assertTrue(any(item.get("suppress_unread") for item in bot_messages))
        self.assertIn("sportovní šifrovací kotvě", " ".join(str(item.get("text", "")) for item in bot_messages).casefold())
        next_checkpoint = await self.scan("sports_cipher")
        self.assertTrue(self.response(next_checkpoint, "qr.result").payload["accepted"])
        captain_message = self.scenario.data["checkpoints"]["sports_cipher"]["message"]["text"].casefold()
        self.assertNotIn("polského kříže", captain_message)

    async def test_sokoban_blocked_sequence_undo_and_restore(self) -> None:
        await self.unlock_sokoban()
        blocked = await self.machine.handle(Message("sokoban.command", {
            "puzzle_id": "sports_sokoban", "commands": ["up", "right"],
        }))
        result = self.response(blocked, "sokoban.result")
        self.assertTrue(result.payload["blocked"])
        self.assertEqual(result.payload["executed"], 1)
        self.assertEqual(len(result.payload["frames"]), 1)
        self.assertEqual(result.payload["blocked_command"], "right")

        undone = await self.machine.handle(Message("sokoban.undo", {"puzzle_id": "sports_sokoban"}))
        self.assertTrue(self.response(undone, "sokoban.result").payload["undo"])
        game = self.machine.state.sokoban_games["sports_sokoban"]
        restored = EscapeBotStateMachine(self.scenario)
        restored.restore_state(self.machine.state.snapshot())
        self.assertEqual(restored.state.sokoban_games["sports_sokoban"], game)

    async def test_sokoban_level_expires_and_reset_preserves_campaign_progress(self) -> None:
        await self.unlock_sokoban()
        game = self.machine.state.sokoban_games["sports_sokoban"]
        game["completed_levels"] = ["sector_a"]
        game["awarded_points"] = 30
        game["deadline_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

        expired = await self.machine.handle(Message("sokoban.command", {
            "puzzle_id": "sports_sokoban", "commands": ["right"],
        }))
        self.assertFalse(self.response(expired, "sokoban.result").payload["success"])
        self.assertEqual(game["status"], "expired")

        reset = await self.machine.handle(Message("sokoban.reset", {"puzzle_id": "sports_sokoban"}))
        self.assertTrue(self.response(reset, "sokoban.result").payload["reset"])
        self.assertEqual(game["completed_levels"], ["sector_a"])
        self.assertEqual(game["awarded_points"], 30)
        self.assertEqual(game["status"], "playing")
        self.assertGreater(datetime.fromisoformat(game["deadline_at"]), datetime.now(UTC))

    def test_sokoban_reserve_levels_are_valid_and_solvable(self) -> None:
        base = self.scenario.data["puzzles"]["sports_sokoban"]["game"]
        solutions = {
            "reserve_d": ["down", "left", "left", "left", "down", "down", "down", "right", "left", "up", "up", "right", "right", "up", "right", "down"],
            "reserve_e": ["down", "left", "down", "down", "down", "right", "right", "up", "left", "up", "up", "left", "up", "right", "right", "right", "down", "left", "left", "down", "down", "down", "left", "up", "up", "up", "left", "up", "right", "right", "right"],
        }
        for level_id, commands in solutions.items():
            config = {**base, "active_level_ids": [level_id]}
            game = new_sokoban(config)
            result = None
            for offset in range(0, len(commands), 30):
                result = execute_sokoban(game, config, commands[offset:offset + 30])
            self.assertIsNotNone(result)
            self.assertTrue(result["game_complete"], level_id)
            self.assertEqual(result["score_delta"], 30)

    async def test_sokoban_warns_when_another_device_starts_commanding(self) -> None:
        await self.unlock_sokoban()
        first = await self.machine.handle(Message("sokoban.command", {
            "puzzle_id": "sports_sokoban", "commands": ["right"], "_client_id": "player-a",
        }))
        second = await self.machine.handle(Message("sokoban.command", {
            "puzzle_id": "sports_sokoban", "commands": ["left"], "_client_id": "player-b",
        }))

        self.assertFalse(self.response(first, "sokoban.result").payload["speaker_warning"])
        self.assertTrue(self.response(second, "sokoban.result").payload["speaker_warning"])
        warnings = [item.payload["text"] for item in second if item.type == "bot.message"]
        self.assertTrue(any("překřikujících" in text for text in warnings))

    async def test_mine_karel_penalizes_mine_and_returns_to_start(self) -> None:
        await self.solve_staircase()
        await self.scan("courtyard_minefield")
        score_before = self.machine.state.score
        result = await self.machine.handle(Message("karel.command", {
            "puzzle_id": "courtyard_karel", "commands": ["right", "right", "right"],
        }))
        payload = self.response(result, "karel.result").payload
        self.assertTrue(payload["hit_mine"])
        self.assertEqual(payload["frames"][-1]["entered"], [0, 3])
        self.assertTrue(payload["frames"][-1]["hit_mine"])
        self.assertEqual(payload["frames"][-1]["player"], [0, 0])
        self.assertNotIn("mines", payload)
        movement_messages = [item.payload for item in result if item.type == "bot.message"]
        self.assertTrue(movement_messages)
        self.assertTrue(all(item.get("suppress_unread") for item in movement_messages))
        self.assertNotIn("clues", payload)
        self.assertEqual(self.machine.state.karel_games["courtyard_karel"]["player"], [0, 0])
        self.assertEqual(self.machine.state.score, score_before - 20)
        self.assertEqual(self.machine.state.chat_history[-1]["voice_id"], "elara_anomaly_hit")

    def test_every_karel_level_has_safe_path_and_accessible_grid(self) -> None:
        config = self.scenario.data["puzzles"]["courtyard_karel"]["game"]
        for level in config["levels"]:
            validate_level(level)
            self.assertGreater(len(safe_path(level)), 1, level["id"])
        game = new_karel({**config, "active_level_ids": ["field_a"]})
        public = public_karel(config, game)
        self.assertEqual(len(public["text_grid"]), public["rows"])
        self.assertTrue(all(len(row.split()) == public["columns"] for row in public["text_grid"]))
        self.assertNotIn("mines", public)

    def test_karel_rejects_level_without_safe_route(self) -> None:
        blocked = {"id": "blocked", "rows": 2, "columns": 2, "start": [0, 0], "exit": [1, 1], "mines": [[0, 1], [1, 0]]}
        with self.assertRaisesRegex(ValueError, "nemá bezpečnou trasu"):
            validate_level(blocked)

    async def test_karel_repeats_sequence_and_describes_sonda(self) -> None:
        await self.solve_staircase()
        await self.scan("courtyard_minefield")
        responses = await self.machine.handle(Message("karel.command", {
            "puzzle_id": "courtyard_karel", "commands": ["down", "down"],
        }))
        messages = [item.payload.get("text", "") for item in responses if item.type == "bot.message"]
        self.assertTrue(any("DOLŮ, DOLŮ" in text for text in messages))
        self.assertTrue(any("Sonda hlásí" in text or "Okolí je čisté" in text for text in messages))

    async def test_mine_karel_completion_unlocks_bowling(self) -> None:
        await self.solve_staircase()
        completed = await self.solve_karel()
        self.assertTrue(self.response(completed, "karel.result").payload["game_complete"])
        self.assertEqual(self.machine.state.checkpoint_states["courtyard_minefield"]["status"], "solved")
        game = self.machine.state.karel_games["courtyard_karel"]
        self.assertEqual(game["completed_levels"], ["field_a", "field_b", "field_c"])
        self.assertEqual(game["awarded_points"], 120)
        bowling = await self.scan("bowling_diagnostics")
        self.assertTrue(self.response(bowling, "qr.result").payload["accepted"])

    async def test_triad_requires_two_orientations_and_unlocks_sokoban(self) -> None:
        await self.unlock_timeline_game()
        game = self.prepare_five_match(); game["progress"] = {"3": 5, "4": 3, "5": 0}
        await self.line_swap([0, 4], [1, 4])
        await self.scan("terrace_echo")
        await self.machine.handle(Message("puzzle.submit", {"puzzle_id":"terrace_morse","answer":"HŘIŠTĚ"}))
        await self.scan("courtyard_alignment")
        response = None
        for row, column, symbol in [(5,1,"cyan"),(0,0,"cyan"),(2,1,"cyan"),(3,4,"cyan"),(5,2,"cyan"),(2,4,"cyan"),(0,2,"cyan"),(5,3,"cyan"),(4,0,"cyan"),(1,1,"amber"),(3,0,"cyan"),(3,2,"cyan"),(1,0,"cyan")]:
            response = await self.machine.handle(Message("triad.place", {"puzzle_id":"temporal_triad","row":row,"column":column,"symbol":symbol}))
        self.assertTrue(self.response(response, "triad.result").payload["game_complete"])
        self.assertEqual(set(self.machine.state.triad_games["temporal_triad"]["completed_orientations"]), {"horizontal","diagonal"})
        sports = await self.scan("sports_archive")
        self.assertTrue(self.response(sports, "qr.result").payload["accepted"])

    async def test_triad_opponent_blocks_an_immediate_player_line(self) -> None:
        await self.unlock_timeline_game()
        game = self.prepare_five_match(); game["progress"] = {"3": 5, "4": 3, "5": 0}
        await self.line_swap([0, 4], [1, 4])
        await self.scan("terrace_echo")
        await self.machine.handle(Message("puzzle.submit", {"puzzle_id":"terrace_morse","answer":"HŘIŠTĚ"}))
        await self.scan("courtyard_alignment")
        await self.machine.handle(Message("triad.place", {"puzzle_id":"temporal_triad","row":0,"column":0,"symbol":"cyan"}))
        response = await self.machine.handle(Message("triad.place", {"puzzle_id":"temporal_triad","row":0,"column":1,"symbol":"cyan"}))
        result = self.response(response, "triad.result").payload
        self.assertEqual(result["opponent_move"], {"row": 0, "column": 2, "symbol": "opponent"})
        self.assertEqual(self.machine.state.triad_games["temporal_triad"]["board"][0][2], "opponent")

    def test_team_size_score_adjustments(self) -> None:
        self.assertEqual(team_size_adjustment("solo", 1), 20)
        self.assertEqual(team_size_adjustment("team", 1), 20)
        self.assertEqual(team_size_adjustment("team", 2), 10)
        self.assertEqual(team_size_adjustment("team", 3), 0)
        self.assertEqual(team_size_adjustment("team", 4), -30)
        self.assertEqual(team_size_adjustment("team", 5), -60)

    def test_inactive_game_classification_ignores_lobbies_and_completed_games(self) -> None:
        self.assertEqual(classify_activity(True, False, 1799), "active")
        self.assertEqual(classify_activity(True, False, 1800), "suspicious")
        self.assertEqual(classify_activity(True, False, 3600), "abandoned")
        self.assertEqual(classify_activity(False, False, 7200), "active")
        self.assertEqual(classify_activity(True, True, 7200), "active")

    def test_team_lobby_join_code_and_maximum_player_count(self) -> None:
        registry = LobbyRegistry()
        lobby = registry.create("creator", "team", "Alice", "Chrononauti")
        joined = registry.join(lobby.join_code, "navigator", "Bob")
        registry.join(lobby.join_code.lower(), "third", "Cyril")

        self.assertIs(joined, lobby)
        self.assertEqual(lobby.max_players, 3)
        self.assertEqual(lobby.score_delta(), 0)
        disconnected_view = lobby.public("creator", {"creator"})
        self.assertEqual(disconnected_view["player_count"], 3)
        self.assertEqual(disconnected_view["online_count"], 1)
        self.assertEqual(disconnected_view["mode"], "team")
        self.assertIs(registry.resume(lobby.session_id, "navigator"), lobby)
        restored = LobbyRegistry()
        restored.restore(registry.snapshot())
        self.assertEqual(restored.join(lobby.join_code, "fourth", "Dana").max_players, 4)

    def test_team_lobby_requires_player_and_unique_team_names(self) -> None:
        registry = LobbyRegistry()
        with self.assertRaisesRegex(ValueError, "Název týmu"):
            registry.create("creator", "team", "Alice", "   ")
        with self.assertRaisesRegex(ValueError, "Jméno hráče"):
            registry.create("creator", "team", "", "Chrononauti")

        registry.create("creator", "team", "Alice", "Časoví   skokani")
        with self.assertRaisesRegex(ValueError, "už existuje"):
            registry.create("other", "team", "Bob", " časoví skokani ")

    def test_team_creation_retry_recovers_pending_creator_lobby(self) -> None:
        registry = LobbyRegistry()
        lobby = registry.create("iphone", "team", "Alice", "Chrononauti")

        recovered = registry.pending_team_for_creator("iphone", " chrononauti ")

        self.assertIs(recovered, lobby)
        self.assertIsNone(registry.pending_team_for_creator("other-device", "Chrononauti"))
        lobby.started = True
        self.assertIsNone(registry.pending_team_for_creator("iphone", "Chrononauti"))

    def test_player_identity_transfer_preserves_team_size_and_creator(self) -> None:
        registry = LobbyRegistry()
        lobby = registry.create("old-device", "team", "Alice", "Chrononauti")
        lobby.join_code and registry.join(lobby.join_code, "navigator", "Bob")
        maximum_before = lobby.max_players

        player = lobby.transfer_player("old-device", "new-device")

        self.assertEqual(player["name"], "Alice")
        self.assertNotIn("old-device", lobby.players)
        self.assertIn("new-device", lobby.players)
        self.assertEqual(lobby.creator_id, "new-device")
        self.assertEqual(lobby.max_players, maximum_before)
        self.assertEqual(len(lobby.players), 2)
        with self.assertRaisesRegex(ValueError, "jinému hráči"):
            lobby.transfer_player("new-device", "navigator")

    def test_admin_can_confirm_and_complete_checkpoint_without_score_bonus(self) -> None:
        score_before = self.machine.state.score
        found = self.machine.admin_set_checkpoint("sports_archive", "found")
        self.assertEqual(found["previous_status"], "locked")
        self.assertEqual(self.machine.state.checkpoint_states["sports_archive"]["status"], "found")

        solved = self.machine.admin_set_checkpoint("sports_archive", "solved")
        self.assertEqual(solved["previous_status"], "found")
        self.assertEqual(self.machine.state.checkpoint_states["sports_archive"]["status"], "solved")
        self.assertIn("pigpen", self.machine.state.unlocked_cipher_tools)
        self.assertNotIn("KRYSTAL ČASOVÉ KOTVY", self.machine.state.inventory)
        self.machine.admin_set_checkpoint("sports_cipher", "solved")
        self.assertIn("KRYSTAL ČASOVÉ KOTVY", self.machine.state.inventory)
        self.assertEqual(self.machine.state.score, score_before)
        with self.assertRaisesRegex(ValueError, "už je dokončený"):
            self.machine.admin_set_checkpoint("sports_archive", "solved")

    def test_admin_can_reset_only_active_interactive_game(self) -> None:
        self.machine.admin_set_checkpoint("courtyard_minefield", "found")
        game = self.machine._karel_state("courtyard_karel", self.scenario.data["puzzles"]["courtyard_karel"]["game"])
        game["player"] = [1, 0]
        result = self.machine.admin_reset_game("courtyard_karel")
        self.assertEqual(result["game_type"], "mine_karel")
        self.assertEqual(game["player"], game["start"])
        self.assertEqual(game["restarts"], 1)

        self.machine.admin_set_checkpoint("courtyard_minefield", "solved")
        with self.assertRaisesRegex(ValueError, "aktivní"):
            self.machine.admin_reset_game("courtyard_karel")

    async def test_production_finale_requires_full_route_and_completes_game(self) -> None:
        for checkpoint_id in [
            "reception_archive", "staircase_signal", "courtyard_minefield", "bowling_diagnostics",
            "timeline_calibration", "terrace_echo", "courtyard_alignment", "sports_archive",
        ]:
            self.machine.admin_set_checkpoint(checkpoint_id, "solved")
        await self.machine.handle(Message("room.unlock", {"pin": self.scenario.data["rooms"]["104"]["pin"]}))

        await self.scan("sports_cipher")
        pigpen = await self.machine.handle(Message("puzzle.submit", {"puzzle_id": "sports_pigpen", "answer": "HODINY"}))
        self.assertTrue(self.response(pigpen, "puzzle.result").payload["correct"])
        self.assertIn("KRYSTAL ČASOVÉ KOTVY", self.machine.state.inventory)

        await self.scan("future_archive")
        assembly = self.scenario.data["puzzles"]["future_archive_cipher"]["assembly"]
        current_order = list(assembly["initial_order"])
        arranged = None
        for index, card_id in enumerate(assembly["correct_order"]):
            if current_order[index] == card_id:
                continue
            target_id = current_order[index]
            arranged = await self.machine.handle(Message("archive.arrange", {
                "puzzle_id": "future_archive_cipher", "card_id": card_id,
                "target_id": target_id, "action": "swap",
            }))
            card_index = current_order.index(card_id)
            current_order[index], current_order[card_index] = current_order[card_index], current_order[index]
        self.assertIsNotNone(arranged)
        self.assertTrue(self.response(arranged, "archive.result").payload["assembled"])
        restored = EscapeBotStateMachine(self.scenario)
        restored.restore_state(self.machine.state.snapshot())
        archive_puzzle = next(item for item in restored._puzzle_state() if item["id"] == "future_archive_cipher")
        self.assertTrue(archive_puzzle["archive_game"]["assembled"])
        self.assertEqual(archive_puzzle["archive_game"]["revealed_key"], "CHRONOS")
        archive = await self.machine.handle(Message("puzzle.submit", {
            "puzzle_id": "future_archive_cipher",
            "answer": "ROK DVA NULA TŘI SEDM / ČAS DVA JEDNA ČTYŘI NULA / POŘADÍ MOTOR STABILIZÁTOR KRYSTAL",
        }))
        self.assertTrue(self.response(archive, "puzzle.result").payload["correct"])
        self.assertTrue(self.machine.state.flags["return_vector_recovered"])

        await self.scan("time_machine_console")
        wrong = await self.machine.handle(Message("finale.activate", {
            "puzzle_id": "time_machine_finale", "year": "2037", "time": "21:40",
            "modules": ["KRYSTAL ČASOVÉ KOTVY", "FÁZOVÝ STABILIZÁTOR", "TEMPORÁLNÍ MOTOR"],
        }))
        self.assertFalse(self.response(wrong, "finale.result").payload["success"])

        completed = await self.machine.handle(Message("finale.activate", {
            "puzzle_id": "time_machine_finale", "year": "2037", "time": "21:40",
            "modules": ["TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"],
        }))
        result = self.response(completed, "finale.result")
        self.assertTrue(result.payload["success"])
        self.assertEqual(self.machine.state.phase, GamePhase.PORTAL_OPEN)
        self.assertTrue(self.machine.state.flags["game_completed"])
        self.assertTrue(self.machine.state.flags["elara_rescued"])
        self.assertEqual(self.machine.state.checkpoint_states["time_machine_console"]["status"], "solved")
        self.assertIsNotNone(self.response(completed, "game.complete"))

    async def test_finale_reports_missing_inventory_and_checkpoints(self) -> None:
        self.machine.admin_set_checkpoint("time_machine_console", "found")
        result = await self.machine.handle(Message("finale.activate", {
            "puzzle_id": "time_machine_finale", "year": "2037", "time": "21:40", "modules": [],
        }))
        payload = self.response(result, "finale.result").payload
        self.assertFalse(payload["success"])
        self.assertIn("sports_cipher", payload["missing_checkpoints"])
        self.assertIn("TEMPORÁLNÍ MOTOR", payload["missing_inventory"])


if __name__ == "__main__":
    unittest.main()
