import unittest

from escape_bot.command_validation import CommandValidationError, validate_game_command


class CommandValidationTests(unittest.TestCase):
    def test_accepts_every_supported_command_shape(self) -> None:
        commands = {
            "client.hello": {},
            "player.message": {"text": "Příjem", "channel": "general"},
            "qr.detected": {"value": "escapebot://checkpoint/token"},
            "geo.position": {"lat": 50.08, "lon": 14.43, "accuracy": 4.5},
            "arg.verify": {"discovery_id": "panel-a", "evidence": {"qr_value": "token"}},
            "camera.frame": {"mime_type": "image/jpeg", "data": "base64"},
            "room.unlock": {"pin": "2147"},
            "room.hint": {"room_id": "108", "hint_index": 0},
            "cipher_tool.unlock": {"tool_id": "pigpen"},
            "puzzle.submit": {"puzzle_id": "reception", "answer": "2147"},
            "puzzle.hint": {"puzzle_id": "reception", "hint_index": 0},
            "phase.hint": {"phase_id": "searching", "hint_index": 0},
            "game.deadline_choice": {"choice": "continue"},
            "archive.arrange": {"puzzle_id": "archive", "card_id": "a", "action": "left"},
            "line_game.move": {"puzzle_id": "lines", "first": [1, 2], "second": [1, 3]},
            "line_game.reset": {"puzzle_id": "lines"},
            "sokoban.command": {"puzzle_id": "grid", "commands": ["up", "left"]},
            "sokoban.undo": {"puzzle_id": "grid"},
            "sokoban.reset": {"puzzle_id": "grid"},
            "karel.command": {"puzzle_id": "mine", "commands": ["right"]},
            "karel.reset": {"puzzle_id": "mine"},
            "triad.place": {"puzzle_id": "triad", "row": 0, "column": 1, "symbol": "cyan"},
            "triad.reset": {"puzzle_id": "triad"},
            "finale.activate": {"puzzle_id": "finale", "year": "2037", "time": "21:40", "modules": ["A", "B"]},
        }

        for command_type, payload in commands.items():
            with self.subTest(command_type=command_type):
                validate_game_command(command_type, payload)

    def test_rejects_unknown_commands_missing_fields_and_unexpected_fields(self) -> None:
        invalid = (
            ("unknown.command", {}),
            ("puzzle.submit", {"puzzle_id": "reception"}),
            ("room.unlock", {"pin": "2147", "admin": True}),
            ("geo.position", {"lat": 91, "lon": 14.43, "accuracy": 4}),
            ("triad.place", {"puzzle_id": "triad", "row": True, "column": 1, "symbol": "cyan"}),
            ("sokoban.command", {"puzzle_id": "grid", "commands": ["jump"]}),
        )

        for command_type, payload in invalid:
            with self.subTest(command_type=command_type, payload=payload):
                with self.assertRaises(CommandValidationError):
                    validate_game_command(command_type, payload)
