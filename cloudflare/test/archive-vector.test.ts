import { describe, expect, it } from "vitest";
import {
  arrangeArchive,
  newArchiveGame,
  publicArchiveGame,
  validArchiveGame,
} from "../src/archive-vector";

const config = {
  mode: "cards",
  grid_size: 3,
  image: "archive.png",
  cards: [
    { id: "a", label: "A", color: "cyan", icon: "◇", source_index: 0 },
    { id: "b", label: "B", source_index: 1 },
    { id: "c", label: "C", source_index: 2 },
  ],
  initial_order: ["b", "a", "c"],
  initial_rotations: { b: 0 },
  correct_order: ["a", "b", "c"],
  correct_rotations: { b: 90 },
  revealed_key: "CHRONOS",
  module_order: ["MOTOR", "STABILIZÁTOR", "KRYSTAL"],
};

describe("Cloudflare archive vector", () => {
  it("initializes and publishes card metadata without revealing the solution", () => {
    const game = newArchiveGame(config);
    expect(validArchiveGame(game, config)).toBe(true);
    expect(game).toMatchObject({ order: ["b", "a", "c"], rotations: { a: 0, b: 0, c: 0 }, moves: 0 });
    expect(publicArchiveGame(config, game)).toMatchObject({
      assembled: false,
      revealed_key: "",
      module_order: [],
      cards: { a: { label: "A", source_index: 0 }, b: { label: "B", source_index: 1 } },
    });
  });

  it("supports swaps and rotations before revealing the key", () => {
    const game = newArchiveGame(config);
    expect(arrangeArchive(game, config, "b", "swap", "a")).toMatchObject({ assembled: false });
    expect(arrangeArchive(game, config, "b", "rotate")).toMatchObject({ assembled: true });
    expect(game).toMatchObject({ order: ["a", "b", "c"], rotations: { b: 90 }, moves: 2, assembled: true });
    expect(publicArchiveGame(config, game)).toMatchObject({
      revealed_key: "CHRONOS",
      module_order: ["MOTOR", "STABILIZÁTOR", "KRYSTAL"],
    });
  });

  it("rejects unknown cards, identical swaps and blocked directions", () => {
    const game = newArchiveGame(config);
    expect(() => arrangeArchive(game, config, "missing", "rotate")).toThrow("Neznámá archivní karta");
    expect(() => arrangeArchive(game, config, "a", "swap", "a")).toThrow("dva různé dílky");
    expect(() => arrangeArchive(game, config, "b", "left")).toThrow("nelze posunout");
    expect(game.moves).toBe(0);
  });
});
