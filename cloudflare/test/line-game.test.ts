import { describe, expect, it } from "vitest";
import { findLineGameRuns, newLineGame, swapLineGame } from "../src/line-game";

function emptyBoard(): string[][] {
  return Array.from({ length: 7 }, () => Array.from({ length: 7 }, () => ""));
}

describe("Cloudflare line game", () => {
  it("recognizes right-angle 3+2 and 3+3 runs by unique stones", () => {
    const four = emptyBoard();
    four[2][1] = four[2][2] = four[2][3] = four[3][3] = "cyan";
    expect(findLineGameRuns(four)).toEqual([["cyan", [[2, 1], [2, 2], [2, 3], [3, 3]]]]);

    const five = emptyBoard();
    five[2][1] = five[2][2] = five[2][3] = five[1][2] = five[3][2] = "amber";
    expect(findLineGameRuns(five)).toEqual([["amber", [[1, 2], [2, 1], [2, 2], [2, 3], [3, 2]]]]);
  });

  it("does not count a 2+2 corner without an arm of three", () => {
    const board = emptyBoard();
    board[2][2] = board[2][3] = board[3][3] = "cyan";
    expect(findLineGameRuns(board)).toEqual([]);
  });

  it("creates a deterministic board without an existing match", () => {
    const config = {
      size: 7,
      colors: ["cyan", "amber", "violet", "green", "red"],
      scoring_colors: ["cyan", "amber"],
      objectives: { "3": 5, "4": 3, "5": 1 },
      seed: 5312026,
      time_limit_seconds: 300,
    };
    const first = newLineGame(config, "2026-09-28T12:00:00.000Z");
    const second = newLineGame(config, "2026-09-28T12:00:00.000Z");
    expect(first.board).toEqual(second.board);
    expect(findLineGameRuns(first.board)).toEqual([]);
  });

  it("scores a bent four created by a neighboring swap", () => {
    const config = {
      size: 7,
      colors: ["cyan", "amber", "violet", "green", "red"],
      scoring_colors: ["cyan", "amber"],
      objectives: { "3": 5, "4": 3, "5": 1 },
      required_condition_count: 2,
      seed: 5312026,
      time_limit_seconds: 300,
      neutral_time_seconds: 180,
      score_interval_seconds: 10,
      score_points_per_interval: 5,
    };
    const game = newLineGame(config, "2026-09-28T12:00:00.000Z");
    game.board = Array.from({ length: 7 }, (_, row) =>
      Array.from({ length: 7 }, (_, column) => (row + column) % 2 ? "green" : "violet"),
    );
    game.board[0][0] = game.board[0][1] = game.board[0][3] = game.board[1][2] = "cyan";
    game.board[0][2] = "violet";

    const result = swapLineGame(config, game, [0, 2], [0, 3], "2026-09-28T12:00:10.000Z");
    expect(result.scored["4"]).toBe(1);
    expect(result.animation_frames[0]).toMatchObject({ phase: "swap", first: [0, 2], second: [0, 3] });
  });
});
