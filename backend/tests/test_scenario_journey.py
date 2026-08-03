import unittest
from pathlib import Path

from escape_bot.protocol import Message
from escape_bot.scenario import ScenarioLoader
from escape_bot.state_machine import EscapeBotStateMachine, GamePhase
from escape_bot.team_lobby import LobbyRegistry


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


class CompleteScenarioJourneyTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.scenario = ScenarioLoader.load(str(SCENARIO_PATH))
        self.machine = EscapeBotStateMachine(self.scenario)

    @staticmethod
    def response(responses, message_type):
        return next(item for item in responses if item.type == message_type)

    async def send(self, message_type, **payload):
        return await self.machine.handle(Message(message_type, payload))

    async def scan(self, checkpoint_id):
        token = self.scenario.data["checkpoints"][checkpoint_id]["token"]
        responses = await self.send("qr.detected", value=f"escapebot://checkpoint/{token}")
        self.assertTrue(self.response(responses, "qr.result").payload["accepted"], checkpoint_id)
        return responses

    async def test_complete_journey_with_lobby_and_midgame_restore(self) -> None:
        registry = LobbyRegistry()
        solo = registry.create("solo-device", "solo", "Sólista", "Smoke sólo")
        team = registry.create("leader", "team", "Alice", "Smoke tým")
        registry.join(team.join_code, "map", "Bob")
        registry.join(team.join_code, "navigator", "Cyril")
        restored_registry = LobbyRegistry(); restored_registry.restore(registry.snapshot())
        self.assertTrue(solo.started)
        self.assertEqual(restored_registry.by_session[team.session_id].max_players, 3)

        await self.send("client.hello")
        await self.send("player.message", text="Příjem")
        await self.send("player.message", text="734")
        await self.send("player.message", text="Slyšíme tě")
        await self.send("player.message", text="restart")
        self.assertEqual(self.machine.state.phase, GamePhase.NAVIGATING)

        await self.scan("reception_archive")
        solved = await self.send("puzzle.submit", puzzle_id="reception_deduction", answer="2147")
        self.assertTrue(self.response(solved, "puzzle.result").payload["correct"])
        room = await self.send("room.unlock", pin="1104")
        self.assertTrue(self.response(room, "room.unlock_result").payload["success"])

        await self.scan("staircase_signal")
        await self.send("puzzle.submit", puzzle_id="staircase_semaphore", answer="BOWLING")
        await self.scan("courtyard_minefield")
        karel_solutions = [
            ["down"] * 4 + ["right"] * 2 + ["down"] + ["right"] * 2 + ["down"] + ["right"] * 2,
            ["up"] * 2 + ["right"] * 2 + ["up"] * 2 + ["right"] * 2 + ["up"] * 2 + ["right"] * 2,
            ["down"] * 3 + ["right"] * 2 + ["up"] + ["right"] * 3 + ["down"] * 3 + ["right"] * 2 + ["down"] * 2,
        ]
        for commands in karel_solutions:
            await self.send("karel.command", puzzle_id="courtyard_karel", commands=commands)

        restored_machine = EscapeBotStateMachine(self.scenario)
        restored_machine.restore_state(self.machine.state.snapshot())
        self.machine = restored_machine
        reconnect = await self.send("client.hello")
        self.assertIsNotNone(self.response(reconnect, "chat.history"))
        self.assertEqual(self.machine.state.checkpoint_states["courtyard_minefield"]["status"], "solved")

        await self.scan("bowling_diagnostics")
        await self.send("puzzle.submit", puzzle_id="bowling_binary", answer="MOTOR")
        await self.scan("timeline_calibration")
        line_game = self.machine.state.interactive_games["timeline_lines"]
        colors = self.scenario.data["puzzles"]["timeline_lines"]["game"]["colors"]
        line_game["board"] = [[colors[(row + column) % len(colors)] for column in range(7)] for row in range(7)]
        for column in range(4): line_game["board"][0][column] = "cyan"
        line_game["board"][0][4] = "violet"; line_game["board"][1][4] = "cyan"
        line_game["progress"] = {"3": 5, "4": 3, "5": 0}
        calibrated = await self.send("line_game.move", puzzle_id="timeline_lines", first=[0, 4], second=[1, 4])
        self.assertTrue(self.response(calibrated, "line_game.result").payload["game_complete"])

        await self.scan("terrace_echo")
        await self.send("puzzle.submit", puzzle_id="terrace_morse", answer="HŘIŠTĚ")
        await self.scan("courtyard_alignment")
        for row, column in [(0, 0), (0, 1), (0, 2), (1, 0), (2, 0), (1, 1)]:
            triad = await self.send("triad.place", puzzle_id="temporal_triad", row=row, column=column, symbol="cyan")
        self.assertTrue(self.response(triad, "triad.result").payload["game_complete"])

        await self.scan("sports_archive")
        sokoban_solutions = [
            "4x nahoru, vlevo, 2x dolů, vpravo, dolů, vlevo, vpravo, dolů, 2x vlevo",
            "nahoru, 2x vpravo, dolů, vpravo, dolů, vlevo, 3x nahoru, vpravo, dolů, vlevo, dolů, vlevo, dolů, vpravo, dolů, vlevo",
            "nahoru, 3x vpravo, dolů, vlevo, nahoru, vlevo, dolů, vpravo, dolů, 2x vlevo, 2x dolů, 2x vpravo, nahoru, 2x vpravo, 2x dolů, vlevo, nahoru",
        ]
        for solution in sokoban_solutions:
            sokoban = await self.send("player.message", channel="lost", text=solution)
        self.assertTrue(self.response(sokoban, "sokoban.result").payload["game_complete"])

        await self.scan("sports_cipher")
        await self.send("puzzle.submit", puzzle_id="sports_pigpen", answer="HODINY")
        await self.scan("future_archive")
        assembly = self.scenario.data["puzzles"]["future_archive_cipher"]["assembly"]
        current_order = list(assembly["initial_order"])
        for index, tile_id in enumerate(assembly["correct_order"]):
            if current_order[index] == tile_id: continue
            displaced = current_order[index]; tile_index = current_order.index(tile_id)
            await self.send("archive.arrange", puzzle_id="future_archive_cipher", card_id=tile_id, target_id=displaced, action="swap")
            current_order[index], current_order[tile_index] = current_order[tile_index], current_order[index]
        await self.send("puzzle.submit", puzzle_id="future_archive_cipher", answer="ROK DVA NULA TRI SEDM CAS DVA JEDNA CTYRI NULA PORADI MOTOR STABILIZATOR KRYSTAL")

        await self.scan("time_machine_console")
        completed = await self.send("finale.activate", puzzle_id="time_machine_finale", year="2037", time="21:40", modules=[
            "TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY",
        ])
        self.assertTrue(self.response(completed, "finale.result").payload["success"])
        self.assertEqual(self.machine.state.phase, GamePhase.PORTAL_OPEN)
        self.assertEqual(set(self.machine.state.inventory), {"TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"})
        self.assertTrue(self.machine.state.flags["game_completed"])
        self.assertGreater(self.machine.state.score, 0)

