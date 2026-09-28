import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import {
  applyAdminGamePlayerExclusion,
  applyScenarioCommand,
  buildScenarioProgress,
  presentGameState,
  startScenario,
  transferPlayerIdentity,
  type RuntimeActor,
  type ScenarioDocument,
} from "../src/scenario-runtime";
import { safeKarelPath } from "../src/mine-karel";

async function chronosScenario(): Promise<ScenarioDocument> {
  const response = await env.ASSETS.fetch("https://example.test/scenarios/chronos_online.json");
  expect(response.status).toBe(200);
  return response.json<ScenarioDocument>();
}

function pathCommands(path: number[][]): string[] {
  return path.slice(1).map(([row, column], index) => {
    const [previousRow, previousColumn] = path[index];
    if (row === previousRow - 1) return "up";
    if (row === previousRow + 1) return "down";
    if (column === previousColumn - 1) return "left";
    return "right";
  });
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

  it("keeps Karel mines private and applies a strike to the shared score", async () => {
    const scenario = await chronosScenario();
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z").state;
    state.checkpoint_states.courtyard_minefield = { status: "found" };
    state = presentGameState(scenario, state, undefined, "2026-09-28T12:00:00.000Z");
    const puzzle = state.puzzles.find((item: Record<string, unknown>) => item.id === "courtyard_karel");
    expect(state.karel_games.courtyard_karel.mines).toContainEqual([0, 3]);
    expect(puzzle.game).not.toHaveProperty("mines");

    const result = applyScenarioCommand(
      scenario,
      state,
      "karel.command",
      { puzzle_id: "courtyard_karel", commands: ["right", "right", "right"] },
      "2026-09-28T12:00:10.000Z",
    );
    expect(result.messages.map((message) => message.type)).toEqual([
      "bot.message",
      "karel.result",
      "bot.message",
      "score.update",
    ]);
    expect(result.messages[1].payload).toMatchObject({ hit_mine: true, score_delta: -20 });
    expect(result.state.score).toBe(980);
    expect(result.state.karel_games.courtyard_karel.player).toEqual([0, 0]);
  });

  it("completes every active Karel field and unlocks the next checkpoint", async () => {
    const scenario = await chronosScenario();
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z").state;
    state.checkpoint_states.courtyard_minefield = { status: "found" };
    const config = scenario.puzzles.courtyard_karel.game;
    let lastMessages: Array<{ type: string; payload: Record<string, unknown> }> = [];
    for (const levelId of config.active_level_ids) {
      const level = config.levels.find((item: Record<string, unknown>) => item.id === levelId);
      const result = applyScenarioCommand(
        scenario,
        state,
        "karel.command",
        { puzzle_id: "courtyard_karel", commands: pathCommands(safeKarelPath(level)) },
        "2026-09-28T12:00:10.000Z",
      );
      state = result.state;
      lastMessages = result.messages;
    }
    expect(state).toMatchObject({ score: 1120, flags: { courtyard_route_stable: true } });
    expect(state.checkpoint_states.courtyard_minefield.status).toBe("solved");
    expect(state.karel_games.courtyard_karel).toMatchObject({
      status: "complete",
      awarded_points: 120,
      completed_levels: ["field_a", "field_b", "field_c"],
    });
    expect(lastMessages.map((message) => message.type)).toEqual(expect.arrayContaining([
      "karel.result",
      "puzzle.result",
      "score.update",
    ]));
  });

  it("keeps Triad boards private while combining team orientations", async () => {
    const scenario = await chronosScenario();
    const alice = {
      clientId: "alice",
      participantIds: ["alice", "bob"],
      participantNames: { alice: "Alice", bob: "Bob" },
      teamMode: "team" as const,
    };
    const bob = { ...alice, clientId: "bob" };
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z", alice).state;
    state.checkpoint_states.terrace_echo = { status: "solved" };
    state = applyScenarioCommand(
      scenario,
      state,
      "qr.detected",
      { value: `escapebot://checkpoint/${scenario.checkpoints.courtyard_alignment.token}` },
      "2026-09-28T12:00:00.000Z",
      alice,
    ).state;
    expect(Object.keys(state.triad_games.temporal_triad.players).sort()).toEqual(["alice", "bob"]);

    const aliceGame = state.triad_games.temporal_triad.players.alice;
    aliceGame.completed_orientations = ["vertical"];
    aliceGame.board[5][1] = aliceGame.board[5][2] = "cyan";
    let result = applyScenarioCommand(
      scenario,
      state,
      "triad.place",
      { puzzle_id: "temporal_triad", row: 5, column: 3, symbol: "cyan" },
      "2026-09-28T12:00:10.000Z",
      alice,
    );
    state = result.state;
    expect(result.messages.map((message) => message.type)).toEqual(["triad.result", "score.update"]);
    expect(result.messages[0].payload).toMatchObject({ game_complete: true, team_complete: false });
    expect(state.score).toBe(1020);

    const bobGame = state.triad_games.temporal_triad.players.bob;
    bobGame.completed_orientations = ["horizontal"];
    bobGame.board[0][0] = bobGame.board[1][1] = "amber";
    result = applyScenarioCommand(
      scenario,
      state,
      "triad.place",
      { puzzle_id: "temporal_triad", row: 2, column: 2, symbol: "amber" },
      "2026-09-28T12:00:20.000Z",
      bob,
    );
    expect(result.messages.map((message) => message.type)).toEqual([
      "triad.result",
      "score.update",
      "score.update",
      "puzzle.result",
      "bot.message",
      "bot.message",
    ]);
    expect(result.messages[0].payload).toMatchObject({
      game_complete: true,
      team_complete: true,
      team_summary: expect.objectContaining({ covered_conditions: ["diagonal", "horizontal", "vertical"] }),
    });
    expect(result.state).toMatchObject({
      score: 1100,
      flags: { temporal_nodes_aligned: true },
      checkpoint_states: { courtyard_alignment: { status: "solved" } },
    });
    const aliceView = presentGameState(scenario, result.state, alice, "2026-09-28T12:00:21.000Z");
    const bobView = presentGameState(scenario, result.state, bob, "2026-09-28T12:00:21.000Z");
    const alicePuzzle = aliceView.puzzles.find((item: Record<string, unknown>) => item.id === "temporal_triad");
    const bobPuzzle = bobView.puzzles.find((item: Record<string, unknown>) => item.id === "temporal_triad");
    expect(alicePuzzle.game.board).not.toEqual(bobPuzzle.game.board);
    expect(alicePuzzle.team_progress).toEqual(bobPuzzle.team_progress);
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

  it("completes shared Sokoban from Czech intercom commands and unlocks Pigpen", async () => {
    const scenario = await chronosScenario();
    const actor: RuntimeActor = {
      clientId: "alice",
      participantIds: ["alice", "bob"],
      participantNames: { alice: "Alice", bob: "Bob" },
      teamMode: "team",
    };
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z", actor).state;
    state.phase = "navigating";
    state.checkpoint_states.sports_archive = { status: "found", first_scanned_at: "2026-09-28T12:00:00.000Z" };
    const sequences = [
      "4x nahoru, vlevo, 2x dolů, vpravo, dolů, vlevo, vpravo, dolů, 2x vlevo",
      "nahoru, 2x vpravo, dolů, vpravo, dolů, vlevo, 3x nahoru, vpravo, dolů, vlevo, dolů, vlevo, dolů, vpravo, dolů, vlevo",
      "nahoru, 3x vpravo, dolů, vlevo, nahoru, vlevo, dolů, vpravo, dolů, 2x vlevo, 2x dolů, 2x vpravo, nahoru, 2x vpravo, 2x dolů, vlevo, nahoru",
    ];
    let lastMessages: Array<{ type: string; payload: Record<string, unknown> }> = [];
    for (const [index, text] of sequences.entries()) {
      const result = applyScenarioCommand(
        scenario,
        state,
        "player.message",
        { channel: "lost", text },
        `2026-09-28T12:00:${String(10 + index).padStart(2, "0")}.000Z`,
        actor,
      );
      state = result.state;
      lastMessages = result.messages;
    }

    expect(state.score).toBe(1090);
    expect(state.checkpoint_states.sports_archive.status).toBe("solved");
    expect(state.unlocked_cipher_tools).toContain("pigpen");
    expect(state.sokoban_games.sports_sokoban).toMatchObject({
      status: "complete",
      awarded_points: 90,
      completed_levels: ["sector_a", "sector_b", "sector_c"],
    });
    const puzzle = state.puzzles.find((item: Record<string, unknown>) => item.id === "sports_sokoban");
    expect(puzzle.game).not.toHaveProperty("history");
    expect(lastMessages.map((message) => message.type)).toEqual(expect.arrayContaining([
      "sokoban.result",
      "score.update",
      "puzzle.result",
    ]));
  });

  it("warns when another device takes over an active Sokoban level", async () => {
    const scenario = await chronosScenario();
    const alice: RuntimeActor = {
      clientId: "alice",
      participantIds: ["alice", "bob"],
      participantNames: { alice: "Alice", bob: "Bob" },
      teamMode: "team",
    };
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z", alice).state;
    state.checkpoint_states.sports_archive = { status: "found" };
    state = applyScenarioCommand(
      scenario,
      state,
      "sokoban.command",
      { puzzle_id: "sports_sokoban", commands: ["left"] },
      "2026-09-28T12:00:01.000Z",
      alice,
    ).state;
    const takeover = applyScenarioCommand(
      scenario,
      state,
      "sokoban.command",
      { puzzle_id: "sports_sokoban", commands: ["left"] },
      "2026-09-28T12:00:02.000Z",
      { ...alice, clientId: "bob" },
    );
    expect(takeover.messages[0]).toMatchObject({
      type: "sokoban.result",
      payload: { success: true, speaker_warning: true },
    });
    expect(takeover.messages[1].payload.text).toContain("jiný než před chvílí");
  });

  it("persists the archive assembly and requires it before accepting the return vector", async () => {
    const scenario = await chronosScenario();
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z").state;
    state.phase = "navigating";
    state.checkpoint_states.future_archive = { status: "found", first_scanned_at: "2026-09-28T12:00:00.000Z" };

    const blocked = applyScenarioCommand(
      scenario,
      state,
      "puzzle.submit",
      { puzzle_id: "future_archive_cipher", answer: "ROK DVA NULA TRI SEDM" },
      "2026-09-28T12:00:01.000Z",
    );
    expect(blocked.messages[0]).toMatchObject({
      type: "puzzle.result",
      payload: { correct: false, reason: "Nejprve správně sestavte obraz rekonstrukce." },
    });
    expect(blocked.state.puzzle_attempts.future_archive_cipher).toBeUndefined();
    state = blocked.state;

    const assembly = scenario.puzzles.future_archive_cipher.assembly;
    const currentOrder = [...assembly.initial_order];
    let arrangedMessages: Array<{ type: string; payload: Record<string, unknown> }> = [];
    for (const [index, cardId] of assembly.correct_order.entries()) {
      if (currentOrder[index] === cardId) continue;
      const displaced = currentOrder[index];
      const cardIndex = currentOrder.indexOf(cardId);
      const arranged = applyScenarioCommand(
        scenario,
        state,
        "archive.arrange",
        { puzzle_id: "future_archive_cipher", card_id: cardId, target_id: displaced, action: "swap" },
        `2026-09-28T12:00:${String(10 + index).padStart(2, "0")}.000Z`,
      );
      state = arranged.state;
      arrangedMessages = arranged.messages;
      [currentOrder[index], currentOrder[cardIndex]] = [currentOrder[cardIndex], currentOrder[index]];
    }
    expect(arrangedMessages[0]).toMatchObject({ type: "archive.result", payload: { success: true, assembled: true } });
    expect(state.archive_games.future_archive_cipher).toMatchObject({ assembled: true });
    const puzzle = state.puzzles.find((item: Record<string, unknown>) => item.id === "future_archive_cipher");
    expect(puzzle.archive_game).toMatchObject({
      assembled: true,
      revealed_key: "CHRONOS",
      module_order: ["TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"],
    });

    const solved = applyScenarioCommand(
      scenario,
      state,
      "puzzle.submit",
      {
        puzzle_id: "future_archive_cipher",
        answer: "ROK DVA NULA TRI SEDM CAS DVA JEDNA CTYRI NULA PORADI MOTOR STABILIZATOR KRYSTAL",
      },
      "2026-09-28T12:01:00.000Z",
    );
    expect(solved.messages[0]).toMatchObject({ type: "puzzle.result", payload: { correct: true, attempts: 1 } });
    expect(solved.state.checkpoint_states.future_archive.status).toBe("solved");
    expect(solved.state.flags.return_vector_recovered).toBe(true);
  });

  it("reports everything missing from an activated finale", async () => {
    const scenario = await chronosScenario();
    const state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z").state;
    state.checkpoint_states.time_machine_console = { status: "found" };
    const result = applyScenarioCommand(
      scenario,
      state,
      "finale.activate",
      { puzzle_id: "time_machine_finale", year: "2037", time: "21:40", modules: [] },
      "2026-09-28T12:01:00.000Z",
    );
    expect(result.messages[0]).toMatchObject({
      type: "finale.result",
      payload: {
        success: false,
        missing_checkpoints: expect.arrayContaining(["sports_cipher", "future_archive"]),
        missing_inventory: expect.arrayContaining(["TEMPORÁLNÍ MOTOR", "KRYSTAL ČASOVÉ KOTVY"]),
        missing_flags: ["room_108_unlocked"],
      },
    });
    expect(result.state.puzzle_attempts.time_machine_finale).toBeUndefined();
  });

  it("rejects a wrong finale vector and then completes the game exactly once", async () => {
    const scenario = await chronosScenario();
    let state = startScenario(scenario, 250, "2026-09-28T12:00:00.000Z").state;
    const puzzle = scenario.puzzles.time_machine_finale;
    for (const checkpointId of puzzle.requires_checkpoints) {
      state.checkpoint_states[checkpointId] = { status: "solved" };
    }
    state.checkpoint_states.time_machine_console = { status: "found" };
    state.inventory = [...puzzle.requires_inventory];
    state.flags.room_108_unlocked = true;
    state = presentGameState(scenario, state, undefined, "2026-09-28T12:00:01.000Z");
    const presented = state.puzzles.find((item: Record<string, unknown>) => item.id === "time_machine_finale");
    expect(presented).toMatchObject({
      status: "found",
      instructions: expect.stringContaining("návratový rok"),
      terminal: { mode: "exclusive", label: "Finální konzole stroje času" },
      finale: {
        module_labels: ["TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"],
        countdown_seconds: 10,
      },
    });

    const wrong = applyScenarioCommand(
      scenario,
      state,
      "finale.activate",
      {
        puzzle_id: "time_machine_finale",
        year: "2037",
        time: "21:40",
        modules: [...puzzle.module_order].reverse(),
      },
      "2026-09-28T12:01:00.000Z",
    );
    expect(wrong.messages.map((message) => message.type)).toEqual(["finale.result", "bot.message"]);
    expect(wrong.messages[0].payload).toMatchObject({ success: false, attempts: 1 });

    const completedAt = "2026-09-28T12:01:01.000Z";
    const completed = applyScenarioCommand(
      scenario,
      wrong.state,
      "finale.activate",
      {
        puzzle_id: "time_machine_finale",
        year: "20-37",
        time: "21:40",
        modules: puzzle.module_order,
      },
      completedAt,
    );
    expect(completed.messages.map((message) => message.type)).toEqual([
      "finale.result",
      "bot.message",
      "bot.message",
      "effect.trigger",
      "game.complete",
    ]);
    expect(completed.messages[0].payload).toMatchObject({
      success: true,
      score: 1250,
      rating: "CHRONOMISTR",
      countdown_seconds: 10,
    });
    expect(completed.state).toMatchObject({
      phase: "portal_open",
      flags: {
        game_completed: true,
        completed_at: completedAt,
        final_rating: "CHRONOMISTR",
        elara_rescued: true,
      },
      checkpoint_states: { time_machine_console: { status: "solved", solved_at: completedAt } },
    });

    const replay = applyScenarioCommand(
      scenario,
      completed.state,
      "finale.activate",
      { puzzle_id: "time_machine_finale", year: "", time: "", modules: [] },
      "2026-09-28T12:02:00.000Z",
    );
    expect(replay.messages).toEqual([{
      type: "finale.result",
      payload: { success: true, already_complete: true, score: 1250 },
    }]);
    expect(replay.state.flags.completed_at).toBe(completedAt);
    expect(replay.state.puzzle_attempts.time_machine_finale).toBe(2);
  });

  it("continues after the deadline without changing the frozen competitive score", async () => {
    const scenario = await chronosScenario();
    let state = startScenario(scenario, -100, "2026-09-28T12:00:00.000Z").state;
    state.flags = {
      ...state.flags,
      deadline_choice_pending: true,
      administratively_ended: true,
      administratively_ended_reason: "deadline",
      competition_score: 900,
      competition_score_frozen_at: "2026-09-28T12:10:00.000Z",
    };
    const blocked = applyScenarioCommand(
      scenario,
      state,
      "phase.hint",
      { phase_id: "comms_offline", hint_index: 0 },
      "2026-09-28T12:10:01.000Z",
    );
    expect(blocked.messages[0]).toMatchObject({ type: "error", payload: { message: expect.stringContaining("Hra je ukončena") } });

    const continued = applyScenarioCommand(
      scenario,
      blocked.state,
      "game.deadline_choice",
      { choice: "continue" },
      "2026-09-28T12:10:02.000Z",
    );
    expect(continued.state.flags).toMatchObject({
      deadline_choice_pending: false,
      deadline_choice: "continue",
      out_of_competition: true,
      administratively_ended: false,
      competition_score: 900,
    });

    const laterPenalty = applyScenarioCommand(
      scenario,
      continued.state,
      "phase.hint",
      { phase_id: "comms_offline", hint_index: 0 },
      "2026-09-28T12:10:03.000Z",
    );
    expect(laterPenalty.state.score).toBe(895);
    expect(laterPenalty.state.flags.competition_score).toBe(900);
    const duplicate = applyScenarioCommand(
      scenario,
      laterPenalty.state,
      "game.deadline_choice",
      { choice: "end" },
      "2026-09-28T12:10:04.000Z",
    );
    expect(duplicate.messages[0]).toMatchObject({ type: "error", payload: { message: expect.stringContaining("už není dostupná") } });
  });

  it("lets a player restore, but never exclude, an administratively excluded teammate", async () => {
    const scenario = await chronosScenario();
    const actor: RuntimeActor = {
      clientId: "alice",
      participantIds: ["alice", "bob"],
      participantNames: { alice: "Alice", bob: "Bob" },
      teamMode: "team",
    };
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z", actor).state;
    state.checkpoint_states.timeline_calibration = { status: "found" };
    state.game_exclusions.timeline_lines = ["bob"];
    state = presentGameState(scenario, state, actor, "2026-09-28T12:00:01.000Z");

    const restored = applyScenarioCommand(
      scenario,
      state,
      "team_game.player.restore",
      { puzzle_id: "timeline_lines", player_id: "bob" },
      "2026-09-28T12:00:02.000Z",
      actor,
    );
    expect(restored.messages[0]).toMatchObject({
      type: "team_game.player.result",
      payload: { success: true, restored: true, player_id: "bob", player_name: "Bob" },
    });
    expect(restored.state.game_exclusions.timeline_lines).toEqual([]);
    const puzzle = restored.state.puzzles.find((item: Record<string, unknown>) => item.id === "timeline_lines");
    expect(puzzle.team_progress.players).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "bob", status: "playing" }),
    ]));

    const selfRestore = applyScenarioCommand(
      scenario,
      restored.state,
      "team_game.player.restore",
      { puzzle_id: "timeline_lines", player_id: "alice" },
      "2026-09-28T12:00:03.000Z",
      actor,
    );
    expect(selfRestore.messages[0]).toMatchObject({
      type: "team_game.player.result",
      payload: { success: false, reason: expect.stringContaining("spoluhráč") },
    });
    const forbidden = applyScenarioCommand(
      scenario,
      restored.state,
      "team_game.player.exclude",
      { puzzle_id: "timeline_lines", player_id: "bob" },
      "2026-09-28T12:00:04.000Z",
      actor,
    );
    expect(forbidden.messages[0]).toMatchObject({ type: "command.rejected" });
    expect(forbidden.state.game_exclusions.timeline_lines).toEqual([]);
  });

  it("lets only the admin boundary exclude a registered player without a game board", async () => {
    const scenario = await chronosScenario();
    const actor: RuntimeActor = {
      clientId: "alice",
      participantIds: ["alice", "bob"],
      participantNames: { alice: "Alice", bob: "Bob" },
      teamMode: "team",
    };
    let state = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z", actor).state;
    state.checkpoint_states.timeline_calibration = { status: "found" };
    state = presentGameState(scenario, state, actor, "2026-09-28T12:00:01.000Z");
    state.interactive_games.timeline_lines.players.alice.status = "complete";

    const excluded = applyAdminGamePlayerExclusion(
      scenario,
      state,
      "timeline_lines",
      "bob",
      "2026-09-28T12:00:02.000Z",
      actor,
    );

    expect(excluded.result).toMatchObject({
      success: true,
      action: "exclude",
      changed: true,
      player_id: "bob",
      player_name: "Bob",
      team_complete: true,
    });
    expect(excluded.state.game_exclusions.timeline_lines).toEqual(["bob"]);
    expect(excluded.state.checkpoint_states.timeline_calibration.status).toBe("solved");
    expect(excluded.state.score).toBe(1040);
    expect(excluded.messages.map((message) => message.type)).toEqual([
      "admin.game_player",
      "score.update",
      "puzzle.result",
      "bot.message",
      "bot.message",
    ]);
    expect(state.interactive_games.timeline_lines.players).not.toHaveProperty("bob");

    const repeated = applyAdminGamePlayerExclusion(
      scenario,
      excluded.state,
      "timeline_lines",
      "bob",
      "2026-09-28T12:00:03.000Z",
      actor,
    );
    expect(repeated.result).toMatchObject({ changed: false, team_complete: true });
    expect(repeated.state.score).toBe(1040);
    expect(repeated.messages).toHaveLength(1);
  });

  it("transfers every player-owned game reference to a recovered device identity", () => {
    const transferred = transferPlayerIdentity({
      interactive_games: { line: { players: { old: { board: [["cyan"]] } } } },
      triad_games: { triad: { players: { old: { board: [["X"]] } } } },
      sokoban_games: { sokoban: { level_speakers: ["alice", "old", "old"] } },
      game_exclusions: { line: ["old"], triad: ["alice", "old"] },
      game_results: { line: { old: { score_delta: 12 } } },
    }, "old", "new");

    expect(transferred.interactive_games.line.players).toEqual({ new: { board: [["cyan"]] } });
    expect(transferred.triad_games.triad.players).toEqual({ new: { board: [["X"]] } });
    expect(transferred.sokoban_games.sokoban.level_speakers).toEqual(["alice", "new"]);
    expect(transferred.game_exclusions).toEqual({ line: ["new"], triad: ["alice", "new"] });
    expect(transferred.game_results.line).toEqual({ new: { score_delta: 12 } });
  });
});
