import unittest
from datetime import UTC, datetime

from escape_bot.line_game import _find_runs, new_game


def board_with(cells: list[tuple[int, int]], color: str = "cyan") -> list[list[str]]:
    board = [["" for _ in range(7)] for _ in range(7)]
    for row, column in cells:
        board[row][column] = color
    return board


class BentLineDetectionTests(unittest.TestCase):
    def assert_single_run(self, cells: list[tuple[int, int]], expected_length: int) -> None:
        runs = _find_runs(board_with(cells))

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0][0], "cyan")
        self.assertEqual(set(runs[0][1]), set(cells))
        self.assertEqual(len(runs[0][1]), expected_length)

    def test_three_plus_two_corner_counts_as_four(self) -> None:
        self.assert_single_run([(3, 2), (3, 3), (3, 4), (4, 4)], 4)

    def test_three_plus_two_supports_all_corner_orientations(self) -> None:
        for horizontal, vertical in [
            ([3, 4, 5], [3, 4]),
            ([3, 4, 5], [2, 3]),
            ([1, 2, 3], [3, 4]),
            ([1, 2, 3], [2, 3]),
        ]:
            with self.subTest(horizontal=horizontal, vertical=vertical):
                cells = [(3, column) for column in horizontal]
                cells.extend((row, 3) for row in vertical if row != 3)
                self.assert_single_run(cells, 4)

    def test_three_plus_two_can_share_middle_stone(self) -> None:
        self.assert_single_run([(3, 2), (3, 3), (3, 4), (4, 3)], 4)

    def test_three_plus_three_corner_counts_as_five(self) -> None:
        self.assert_single_run([(3, 2), (3, 3), (3, 4), (4, 4), (5, 4)], 5)

    def test_three_plus_three_can_cross_at_middle_stone(self) -> None:
        self.assert_single_run([(3, 2), (3, 3), (3, 4), (2, 3), (4, 3)], 5)

    def test_two_plus_two_does_not_count_as_a_run(self) -> None:
        self.assertEqual(_find_runs(board_with([(3, 3), (3, 4), (4, 3)])), [])

    def test_straight_runs_keep_their_original_length(self) -> None:
        self.assert_single_run([(3, 1), (3, 2), (3, 3), (3, 4)], 4)

    def test_new_board_contains_no_straight_or_bent_run(self) -> None:
        config = {
            "size": 7,
            "colors": ["cyan", "amber", "violet", "green", "red"],
            "objectives": {"3": 5, "4": 3, "5": 1},
        }

        for seed in range(20):
            with self.subTest(seed=seed):
                game = new_game({**config, "seed": seed}, datetime(2026, 9, 28, tzinfo=UTC))
                self.assertEqual(_find_runs(game["board"]), [])


if __name__ == "__main__":
    unittest.main()
