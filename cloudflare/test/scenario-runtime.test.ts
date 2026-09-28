import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import {
  applyScenarioCommand,
  buildScenarioProgress,
  presentGameState,
  startScenario,
  type RuntimeActor,
  type ScenarioDocument,
} from "../src/scenario-runtime";

async function chronosScenario(): Promise<ScenarioDocument> {
  const response = await env.ASSETS.fetch("https://example.test/scenarios/chronos_online.json");
  expect(response.status).toBe(200);
  return response.json<ScenarioDocument>();
}

describe("deterministic Cloudflare scenario runtime", () => {
  it("starts the compiled scenario with its real phase, message and progress", async () => {
    const scenario = await chronosScenario();
    const started = startScenario(scenario, 20, "2026-09-28T12:00:00.000Z");
    expect(started.state).toMatchObject({ phase: "comms_offline", score: 1020 });
    expect(started.state.phase_hints).toMatchObject({ count: 1, unlocked: 0, costs: [5] });
    expect(started.messages[0].payload.text).toContain("Tady Kapitánka");
    expect(buildScenarioProgress(scenario, started.state)).toMatchObject({
      scenario_id: "chronos_online_rescue",
      current_phase: "comms_offline",
      score: 1020,
    });
  });

  it("advances the opening narrative and applies progressive hints", async () => {
    const scenario = await chronosScenario();
    const started = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z");
    const confirmed = applyScenarioCommand(
      scenario,
      started.state,
      "player.message",
      { text: "Slyšíme se" },
      "2026-09-28T12:00:01.000Z",
    );
    expect(confirmed.state.phase).toBe("searching_lost");
    expect(confirmed.messages[0].payload.text).toContain("nouzový záznam");

    const hinted = applyScenarioCommand(
      scenario,
      confirmed.state,
      "phase.hint",
      { phase_id: "searching_lost", hint_index: 0 },
      "2026-09-28T12:00:02.000Z",
    );
    expect(hinted.state.score).toBe(990);
    expect(hinted.state.phase_hints).toMatchObject({ unlocked: 1 });
    expect(hinted.messages.map((message) => message.type)).toEqual(["score.update", "bot.message"]);

    const connected = applyScenarioCommand(
      scenario,
      hinted.state,
      "player.message",
      { text: "Frekvence je 734" },
      "2026-09-28T12:00:03.000Z",
    );
    expect(connected.state.phase).toBe("navigating");
    expect(connected.state.flags.chronomap_unlocked).toBe(true);
    expect(connected.messages).toHaveLength(3);
  });

  it("rejects a line-game move before its checkpoint is found", async () => {
    const scenario = await chronosScenario();
    const started = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z");
    const rejected = applyScenarioCommand(
      scenario,
      started.state,
      "line_game.move",
      { puzzle_id: "timeline_lines" },
      "2026-09-28T12:00:01.000Z",
    );

    expect(rejected.messages[0]).toMatchObject({
      type: "line_game.result",
      payload: { success: false, reason: "Interaktivní úloha zatím nebyla nalezena." },
    });
    expect(rejected.state.score).toBe(started.state.score);
  });

  it("persists a solo line game, scores completion and solves its checkpoint", async () => {
    const scenario = await chronosScenario();
    const actor: RuntimeActor = {
      clientId: "alice",
      participantIds: ["alice"],
      participantNames: { alice: "Alice" },
      teamMode: "solo",
    };
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z", actor).state;
    state.checkpoint_states.timeline_calibration = { status: "found", first_scanned_at: "2026-09-28T12:00:00.000Z" };
    state = presentGameState(scenario, state, actor, "2026-09-28T12:00:00.000Z");
    const game = state.interactive_games.timeline_lines;
    game.progress = { "3": 5, "4": 2, "5": 0 };
    game.board = Array.from({ length: 7 }, (_, row) =>
      Array.from({ length: 7 }, (_, column) => (row + column) % 2 ? "green" : "violet"),
    );
    game.board[0][0] = game.board[0][1] = game.board[0][3] = game.board[1][2] = "cyan";
    game.board[0][2] = "violet";

    const completed = applyScenarioCommand(
      scenario,
      state,
      "line_game.move",
      { puzzle_id: "timeline_lines", first: [0, 2], second: [0, 3] },
      "2026-09-28T12:00:10.000Z",
      actor,
    );

    expect(completed.messages.map((message) => message.type)).toEqual([
      "line_game.result",
      "score.update",
      "score.update",
      "puzzle.result",
      "bot.message",
      "bot.message",
    ]);
    expect(completed.messages[0].payload).toMatchObject({ success: true, game_complete: true, team_complete: true });
    expect(completed.state.checkpoint_states.timeline_calibration.status).toBe("solved");
    expect(completed.state.flags.timeline_calibrated).toBe(true);
    expect(completed.state.game_results.timeline_lines.alice).toMatchObject({
      elapsed_seconds: 10,
      conditions: ["3", "4"],
    });
    expect(completed.state.puzzles).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "timeline_lines", status: "solved", game: expect.objectContaining({ status: "complete" }) }),
    ]));
  });

  it("presents only the current player's board with shared team progress", async () => {
    const scenario = await chronosScenario();
    const baseActor: RuntimeActor = {
      clientId: "alice",
      participantIds: ["alice", "bob"],
      participantNames: { alice: "Alice", bob: "Bob" },
      teamMode: "team",
    };
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z", baseActor).state;
    state.checkpoint_states.bowling_diagnostics = { status: "solved" };
    state = applyScenarioCommand(
      scenario,
      state,
      "qr.detected",
      { value: `escapebot://checkpoint/${scenario.checkpoints.timeline_calibration.token}` },
      "2026-09-28T12:00:00.000Z",
      baseActor,
    ).state;
    expect(Object.keys(state.interactive_games.timeline_lines.players).sort()).toEqual(["alice", "bob"]);
    state.interactive_games.timeline_lines.players.alice.board[0][0] = "alice-only";

    const alice = presentGameState(scenario, state, baseActor, "2026-09-28T12:00:01.000Z");
    const bob = presentGameState(scenario, state, { ...baseActor, clientId: "bob" }, "2026-09-28T12:00:01.000Z");
    const alicePuzzle = alice.puzzles.find((puzzle: Record<string, unknown>) => puzzle.id === "timeline_lines");
    const bobPuzzle = bob.puzzles.find((puzzle: Record<string, unknown>) => puzzle.id === "timeline_lines");
    expect(alicePuzzle.game.board[0][0]).toBe("alice-only");
    expect(bobPuzzle.game.board[0][0]).not.toBe("alice-only");
    expect(alicePuzzle.team_progress.players).toEqual([
      expect.objectContaining({ id: "alice", name: "Alice" }),
      expect.objectContaining({ id: "bob", name: "Bob" }),
    ]);
  });

  it("activates and solves the first answer puzzle in checkpoint order", async () => {
    const scenario = await chronosScenario();
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z").state;
    state = applyScenarioCommand(
      scenario,
      state,
      "player.message",
      { text: "Slyšíme se" },
      "2026-09-28T12:00:01.000Z",
    ).state;
    state = applyScenarioCommand(
      scenario,
      state,
      "player.message",
      { text: "Frekvence 734" },
      "2026-09-28T12:00:02.000Z",
    ).state;

    const token = scenario.checkpoints.reception_archive.token;
    const scanned = applyScenarioCommand(
      scenario,
      state,
      "qr.detected",
      { value: `escapebot://checkpoint/${token}` },
      "2026-09-28T12:00:03.000Z",
    );
    expect(scanned.messages.map((message) => message.type)).toEqual([
      "qr.result",
      "bot.message",
      "effect.trigger",
    ]);
    expect(scanned.state.checkpoint_states.reception_archive.status).toBe("found");
    expect(scanned.state.puzzles).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: "reception_deduction", status: "found" }),
      ]),
    );

    const failed = applyScenarioCommand(
      scenario,
      scanned.state,
      "puzzle.submit",
      { puzzle_id: "reception_deduction", answer: "0000" },
      "2026-09-28T12:00:04.000Z",
    );
    expect(failed.messages[0]).toMatchObject({
      type: "puzzle.result",
      payload: { correct: false, attempts: 1 },
    });

    const hinted = applyScenarioCommand(
      scenario,
      failed.state,
      "puzzle.hint",
      { puzzle_id: "reception_deduction", hint_index: 0 },
      "2026-09-28T12:00:05.000Z",
    );
    expect(hinted.state).toMatchObject({ score: 990 });
    expect(hinted.state.puzzles).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: "reception_deduction", hints_unlocked: 1 }),
      ]),
    );
    const lockedHint = applyScenarioCommand(
      scenario,
      hinted.state,
      "puzzle.hint",
      { puzzle_id: "reception_deduction", hint_index: 2 },
      "2026-09-28T12:00:05.500Z",
    );
    expect(lockedHint.messages[0].payload.message).toContain("předchozí");
    expect(lockedHint.state.score).toBe(990);

    const solved = applyScenarioCommand(
      scenario,
      hinted.state,
      "puzzle.submit",
      { puzzle_id: "reception_deduction", answer: "2 1 4 7" },
      "2026-09-28T12:00:06.000Z",
    );
    expect(solved.messages[0]).toMatchObject({
      type: "puzzle.result",
      payload: { correct: true, attempts: 2 },
    });
    expect(solved.state.checkpoint_states.reception_archive.status).toBe("solved");
    expect(solved.state.flags.reception_archive_unlocked).toBe(true);
    expect(buildScenarioProgress(scenario, solved.state).nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: "reception_archive", status: "complete" }),
        expect.objectContaining({ id: "staircase_signal", status: "available" }),
      ]),
    );
  });

  it("rejects checkpoints before their phase or predecessor is complete", async () => {
    const scenario = await chronosScenario();
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z").state;
    const earlyReception = applyScenarioCommand(
      scenario,
      state,
      "qr.detected",
      { value: `escapebot://checkpoint/${scenario.checkpoints.reception_archive.token}` },
      "2026-09-28T12:00:01.000Z",
    );
    expect(earlyReception.messages[0]).toMatchObject({
      type: "qr.result",
      payload: { accepted: false, required_phase: "navigating" },
    });
    expect(earlyReception.state.checkpoint_states).toEqual({});

    state = applyScenarioCommand(
      scenario,
      state,
      "player.message",
      { text: "Slyšíme se" },
      "2026-09-28T12:00:02.000Z",
    ).state;
    state = applyScenarioCommand(
      scenario,
      state,
      "player.message",
      { text: "734" },
      "2026-09-28T12:00:03.000Z",
    ).state;
    const skippedReception = applyScenarioCommand(
      scenario,
      state,
      "qr.detected",
      { value: `escapebot://checkpoint/${scenario.checkpoints.staircase_signal.token}` },
      "2026-09-28T12:00:04.000Z",
    );
    expect(skippedReception.messages[0]).toMatchObject({
      type: "qr.result",
      payload: { accepted: false, missing: ["reception_archive"] },
    });
    expect(skippedReception.state.checkpoint_states).toEqual({});
  });
});
