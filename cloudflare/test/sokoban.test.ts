import { describe, expect, it } from "vitest";
import {
  executeSokoban,
  newSokobanGame,
  parseSokobanCommands,
  publicSokobanGame,
  resetSokobanLevel,
  undoSokoban,
} from "../src/sokoban";

const config = {
  level_time_seconds: 120,
  points_per_level: 30,
  active_level_ids: ["vertical", "horizontal"],
  levels: [
    {
      id: "vertical",
      label: "Svislý sektor",
      map: ["#####", "# . #", "# $ #", "# @ #", "#####"],
    },
    {
      id: "horizontal",
      label: "Vodorovný sektor",
      map: ["#####", "#@$.#", "#####"],
    },
    {
      id: "reserve",
      map: ["#####", "#@$.#", "#####"],
    },
  ],
};

describe("Cloudflare Sokoban", () => {
  it("parses Czech commands, repetition, undo and reset", () => {
    expect(parseSokobanCommands("2x nahoru, vlevo, vpravo 3x")).toEqual([
      "up", "up", "left", "right", "right", "right",
    ]);
    expect(parseSokobanCommands("krok zpět")).toEqual(["undo"]);
    expect(parseSokobanCommands("obnovit")).toEqual(["reset"]);
    expect(parseSokobanCommands("běž k cíli")).toBeNull();
    expect(() => parseSokobanCommands("31x nahoru")).toThrow("nejvýše 30");
  });

  it("stops before a wall, records frames and restores the last actual move", () => {
    const game = newSokobanGame(config, "2026-09-28T12:00:00.000Z");
    const result = executeSokoban(game, config, ["left", "left"], "2026-09-28T12:00:10.000Z");
    expect(result).toMatchObject({ executed: 1, requested: 2, blocked: true, blocked_command: "left" });
    expect(result.frames).toHaveLength(1);
    expect(game.player).toEqual([3, 1]);
    expect(undoSokoban(game)).toBe(true);
    expect(game.player).toEqual([3, 2]);
  });

  it("advances through levels and awards each level once", () => {
    const game = newSokobanGame(config, "2026-09-28T12:00:00.000Z");
    const first = executeSokoban(game, config, ["up"], "2026-09-28T12:00:10.000Z");
    expect(first).toMatchObject({ level_complete: true, game_complete: false, score_delta: 30 });
    expect(game.level_id).toBe("horizontal");
    const second = executeSokoban(game, config, ["right"], "2026-09-28T12:00:20.000Z");
    expect(second).toMatchObject({ level_complete: true, game_complete: true, score_delta: 30 });
    expect(game).toMatchObject({ status: "complete", awarded_points: 60, completed_levels: ["vertical", "horizontal"] });
  });

  it("keeps history private and resets an expired level without losing campaign progress", () => {
    const game = newSokobanGame(config, "2026-09-28T12:00:00.000Z");
    executeSokoban(game, config, ["up"], "2026-09-28T12:00:10.000Z");
    const expired = publicSokobanGame(config, game, "2026-09-28T12:03:00.000Z");
    expect(expired).not.toHaveProperty("history");
    expect(expired).toMatchObject({ status: "expired", remaining_seconds: 0, total_levels: 2, reserve_levels: 1 });
    resetSokobanLevel(config, game, "2026-09-28T12:03:01.000Z");
    expect(game).toMatchObject({ status: "playing", restarts: 1, awarded_points: 30, completed_levels: ["vertical"] });
  });
});
