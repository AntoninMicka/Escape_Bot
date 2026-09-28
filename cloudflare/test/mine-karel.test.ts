import { describe, expect, it } from "vitest";
import {
  executeKarel,
  newKarelGame,
  publicKarelGame,
  safeKarelPath,
  validateKarelLevel,
} from "../src/mine-karel";

const config = {
  level_time_seconds: 180,
  mine_penalty: 20,
  points_per_level: 40,
  active_level_ids: ["field_a", "field_b"],
  levels: [
    {
      id: "field_a",
      rows: 3,
      columns: 3,
      start: [0, 0],
      exit: [2, 2],
      mines: [[0, 2]],
      revealed: [[0, 1]],
    },
    {
      id: "field_b",
      rows: 2,
      columns: 2,
      start: [1, 0],
      exit: [0, 1],
      mines: [],
      revealed: [],
    },
  ],
};

describe("Cloudflare mine Karel", () => {
  it("publishes clues and an accessible grid without mines or movement history", () => {
    const game = newKarelGame(config, "2026-09-28T12:00:00.000Z");
    const presented = publicKarelGame(config, game, "2026-09-28T12:00:10.000Z");
    expect(presented).not.toHaveProperty("mines");
    expect(presented).not.toHaveProperty("history");
    expect(presented.remaining_seconds).toBe(170);
    expect(presented.text_grid).toHaveLength(3);
    expect(presented.text_grid.every((row: string) => row.split(" ").length === 3)).toBe(true);
  });

  it("returns to start and applies a penalty after entering a mine", () => {
    const game = newKarelGame(config, "2026-09-28T12:00:00.000Z");
    const result = executeKarel(game, config, ["right", "right"], "2026-09-28T12:00:10.000Z");
    expect(result).toMatchObject({ hit_mine: true, score_delta: -20 });
    expect(result.frames.at(-1)).toMatchObject({ entered: [0, 2], player: [0, 0], hit_mine: true });
    expect(game.player).toEqual([0, 0]);
  });

  it("advances through levels and awards each level once", () => {
    const game = newKarelGame(config, "2026-09-28T12:00:00.000Z");
    const first = executeKarel(game, config, ["down", "down", "right", "right"], "2026-09-28T12:00:10.000Z");
    expect(first).toMatchObject({ level_complete: true, game_complete: false, score_delta: 40 });
    expect(game.level_id).toBe("field_b");
    const second = executeKarel(game, config, ["up", "right"], "2026-09-28T12:00:20.000Z");
    expect(second).toMatchObject({ level_complete: true, game_complete: true, score_delta: 40 });
    expect(game).toMatchObject({ status: "complete", awarded_points: 80, completed_levels: ["field_a", "field_b"] });
  });

  it("validates that every level has a safe route", () => {
    expect(safeKarelPath(config.levels[0])).toEqual([[0, 0], [1, 0], [2, 0], [2, 1], [2, 2]]);
    expect(() => validateKarelLevel({
      id: "blocked",
      rows: 2,
      columns: 2,
      start: [0, 0],
      exit: [1, 1],
      mines: [[0, 1], [1, 0]],
    })).toThrow("nemá bezpečnou trasu");
  });
});
