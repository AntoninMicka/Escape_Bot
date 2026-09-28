import { describe, expect, it } from "vitest";
import { newTriadGame, placeTriad, publicTriadGame, resetTriadGame } from "../src/triad-game";

const config = {
  size: 6,
  symbols: ["cyan", "amber"],
  blocked: [],
  required_orientation_count: 2,
  time_limit_seconds: 180,
};

describe("Cloudflare triad game", () => {
  it("uses the deterministic opponent to block an immediate line", () => {
    const game = newTriadGame(config, "2026-09-28T12:00:00.000Z");
    placeTriad(game, config, 0, 0, "cyan", "2026-09-28T12:00:01.000Z");
    const result = placeTriad(game, config, 0, 1, "cyan", "2026-09-28T12:00:02.000Z");
    expect(result.opponent_move).toEqual({ row: 0, column: 2, symbol: "opponent" });
    expect(game.board[0][2]).toBe("opponent");
  });

  it("normalizes both diagonal directions into one objective", () => {
    const game = newTriadGame(config, "2026-09-28T12:00:00.000Z");
    game.board[0][2] = game.board[1][1] = "amber";
    const result = placeTriad(game, config, 2, 0, "amber", "2026-09-28T12:00:01.000Z");
    expect(result.new_lines).toEqual(expect.arrayContaining([
      expect.objectContaining({ orientation: "anti_diagonal", cells: ["0:2", "1:1", "2:0"] }),
    ]));
    expect(game.completed_orientations).toEqual(["diagonal"]);
  });

  it("completes after the configured number of distinct orientations", () => {
    const game = newTriadGame(config, "2026-09-28T12:00:00.000Z");
    game.completed_orientations = ["vertical"];
    game.board[5][1] = game.board[5][2] = "cyan";
    const result = placeTriad(game, config, 5, 3, "cyan", "2026-09-28T12:00:10.000Z");
    expect(result).toMatchObject({ game_complete: true, opponent_move: null });
    expect(game).toMatchObject({ status: "complete", completed_orientations: ["vertical", "horizontal"] });
  });

  it("publishes timing metadata and resets the full board", () => {
    const game = newTriadGame(config, "2026-09-28T12:00:00.000Z");
    placeTriad(game, config, 0, 0, "cyan", "2026-09-28T12:00:01.000Z");
    expect(publicTriadGame(config, game, "2026-09-28T12:00:10.000Z")).toMatchObject({
      remaining_seconds: 170,
      required_orientations: ["horizontal", "vertical", "diagonal"],
      required_orientation_count: 2,
    });
    resetTriadGame(config, game, "2026-09-28T12:01:00.000Z");
    expect(game).toMatchObject({ placements: 0, opponent_moves: 0, restarts: 1, status: "playing" });
    expect(game.board.flat().every((value: unknown) => value === null)).toBe(true);
  });
});
