import { env, evictDurableObject, runInDurableObject, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

type ProtocolMessage = {
  type: string;
  payload: Record<string, any>;
  operation_id?: string;
};

function nextMessage(socket: WebSocket, expectedType: string): Promise<ProtocolMessage> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${expectedType}`)), 3000);
    const listener = (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as ProtocolMessage;
      if (message.type !== expectedType) return;
      clearTimeout(timeout);
      socket.removeEventListener("message", listener);
      resolve(message);
    };
    socket.addEventListener("message", listener);
  });
}

function nextMatchingMessage(
  socket: WebSocket,
  expectedType: string,
  predicate: (message: ProtocolMessage) => boolean,
): Promise<ProtocolMessage> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for matching ${expectedType}`)), 3000);
    const listener = (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as ProtocolMessage;
      if (message.type !== expectedType || !predicate(message)) return;
      clearTimeout(timeout);
      socket.removeEventListener("message", listener);
      resolve(message);
    };
    socket.addEventListener("message", listener);
  });
}

function messagesUntil(socket: WebSocket, finalType: string): Promise<ProtocolMessage[]> {
  return new Promise((resolve, reject) => {
    const messages: ProtocolMessage[] = [];
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${finalType}`)), 5000);
    const listener = (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as ProtocolMessage;
      messages.push(message);
      if (message.type !== finalType) return;
      clearTimeout(timeout);
      socket.removeEventListener("message", listener);
      resolve(messages);
    };
    socket.addEventListener("message", listener);
  });
}

function messagesUntilOperation(socket: WebSocket, operationId: string): Promise<ProtocolMessage[]> {
  return new Promise((resolve, reject) => {
    const messages: ProtocolMessage[] = [];
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${operationId}`)), 5000);
    const listener = (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as ProtocolMessage;
      if (message.operation_id === operationId) messages.push(message);
      if (message.type !== "scenario.progress" || message.operation_id !== operationId) return;
      clearTimeout(timeout);
      socket.removeEventListener("message", listener);
      resolve(messages);
    };
    socket.addEventListener("message", listener);
  });
}

async function openSocket(url: string): Promise<WebSocket> {
  const response = await SELF.fetch(url, { headers: { Upgrade: "websocket" } });
  expect(response.status).toBe(101);
  const socket = response.webSocket;
  if (!socket) throw new Error("WebSocket response is missing a socket");
  socket.accept();
  await nextMessage(socket, "session.connected");
  return socket;
}

function closeSocket(socket: WebSocket): Promise<void> {
  if (socket.readyState === WebSocket.CLOSED) return Promise.resolve();
  return new Promise((resolve) => {
    socket.addEventListener("close", () => resolve(), { once: true });
    socket.close(1000, "done");
  });
}

function messageOf(messages: ProtocolMessage[], type: string): ProtocolMessage {
  const message = messages.find((candidate) => candidate.type === type);
  if (!message) throw new Error(`Response does not contain ${type}: ${messages.map((item) => item.type).join(", ")}`);
  return message;
}

function gameStateOf(messages: ProtocolMessage[]): Record<string, any> {
  return messageOf(messages, "game.state").payload;
}

describe("Cloudflare complete scenario journey", () => {
  it("finishes the complete solo scenario and survives a mid-game eviction", async () => {
    const scenarioResponse = await env.ASSETS.fetch("https://assets.local/scenarios/hotel_kraskov.json");
    expect(scenarioResponse.ok).toBe(true);
    const scenario = await scenarioResponse.json<Record<string, any>>();

    const bootstrap = await openSocket("https://example.test/ws?client_id=journey-player");
    const routePromise = nextMessage(bootstrap, "lobby.route");
    bootstrap.send(JSON.stringify({
      type: "lobby.solo",
      payload: {
        client_id: "journey-player",
        name: "Alice",
        team_name: "Complete Journey",
        lobby_type: "on_site_qr",
        scenario_id: "hotel_kraskov",
      },
    }));
    const route = await routePromise;
    const sessionId = String(route.payload.session_id);
    const session = await openSocket(
      `https://example.test/ws?session_id=${sessionId}&client_id=journey-player`,
    );
    const stub = env.GAME_SESSIONS.getByName(sessionId);
    let operationIndex = 0;

    const command = async (type: string, payload: Record<string, unknown> = {}) => {
      operationIndex += 1;
      const result = messagesUntil(session, "scenario.progress");
      session.send(JSON.stringify({
        type,
        operation_id: `journey-${String(operationIndex).padStart(3, "0")}`,
        payload,
      }));
      return result;
    };
    const scan = async (checkpointId: string) => {
      const messages = await command("qr.detected", {
        value: `escapebot://checkpoint/${scenario.checkpoints[checkpointId].token}`,
      });
      expect(messageOf(messages, "qr.result").payload).toMatchObject({
        accepted: true,
        checkpoint_id: checkpointId,
      });
      return messages;
    };

    expect(gameStateOf(await command("player.message", { text: "Příjem" })).phase).toBe("searching_lost");
    expect(gameStateOf(await command("player.message", { text: "734" })).phase).toBe("navigating");

    await scan("reception_archive");
    expect(messageOf(await command("puzzle.submit", {
      puzzle_id: "reception_deduction",
      answer: "2147",
    }), "puzzle.result").payload.correct).toBe(true);
    const room = await command("room.unlock", { pin: "1108" });
    expect(messageOf(room, "room.unlock_result").payload.success).toBe(true);
    expect(gameStateOf(room).flags.room_108_unlocked).toBe(true);

    await scan("staircase_signal");
    await command("puzzle.submit", { puzzle_id: "staircase_semaphore", answer: "BOWLING" });

    await scan("courtyard_minefield");
    const karelSolutions = [
      [...Array(4).fill("down"), ...Array(2).fill("right"), "down", ...Array(2).fill("right"), "down", ...Array(2).fill("right")],
      [...Array(2).fill("up"), ...Array(2).fill("right"), ...Array(2).fill("up"), ...Array(2).fill("right"), ...Array(2).fill("up"), ...Array(2).fill("right")],
      [...Array(3).fill("down"), ...Array(2).fill("right"), "up", ...Array(3).fill("right"), ...Array(3).fill("down"), ...Array(2).fill("right"), ...Array(2).fill("down")],
    ];
    for (const commands of karelSolutions) {
      await command("karel.command", { puzzle_id: "courtyard_karel", commands });
    }

    await evictDurableObject(stub);
    const restoredStatePromise = nextMessage(session, "game.state");
    const restoredProgressPromise = nextMessage(session, "scenario.progress");
    session.send(JSON.stringify({ type: "lobby.resume", payload: { session_id: sessionId } }));
    expect((await restoredStatePromise).payload.checkpoint_states.courtyard_minefield.status).toBe("solved");
    await restoredProgressPromise;

    await scan("bowling_diagnostics");
    await command("puzzle.submit", { puzzle_id: "bowling_binary", answer: "MOTOR" });

    await scan("timeline_calibration");
    // Detailed swap/refill behavior has focused tests. The journey fixture moves the
    // deterministic board one legal swap from completion so this test stays about
    // transport, persistence and scenario sequencing rather than match-3 search.
    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as {
        snapshot: { gameState: Record<string, any> };
      };
      const game = target.snapshot.gameState.interactive_games.timeline_lines;
      game.progress = { "3": 5, "4": 2, "5": 0 };
      game.board = Array.from({ length: 7 }, (_, row) =>
        Array.from({ length: 7 }, (_, column) => (row + column) % 2 ? "green" : "violet"),
      );
      game.board[0][0] = game.board[0][1] = game.board[0][3] = game.board[1][2] = "cyan";
      game.board[0][2] = "violet";
      await state.storage.put("session-snapshot", target.snapshot);
    });
    const line = await command("line_game.move", {
      puzzle_id: "timeline_lines",
      first: [0, 2],
      second: [0, 3],
    });
    expect(messageOf(line, "line_game.result").payload).toMatchObject({ game_complete: true, team_complete: true });

    await scan("terrace_echo");
    await command("puzzle.submit", { puzzle_id: "terrace_morse", answer: "HŘIŠTĚ" });

    await scan("courtyard_alignment");
    const triadPlacements: Array<[number, number, string]> = [
      [5, 1, "cyan"], [0, 0, "cyan"], [2, 1, "cyan"], [3, 4, "cyan"], [5, 2, "cyan"],
      [2, 4, "cyan"], [0, 2, "cyan"], [5, 3, "cyan"], [4, 0, "cyan"], [1, 1, "amber"],
      [3, 0, "cyan"], [3, 2, "cyan"], [1, 0, "cyan"],
    ];
    let triad: ProtocolMessage[] = [];
    for (const [row, column, symbol] of triadPlacements) {
      triad = await command("triad.place", { puzzle_id: "temporal_triad", row, column, symbol });
    }
    expect(messageOf(triad, "triad.result").payload.game_complete).toBe(true);

    await scan("sports_archive");
    const sokobanSolutions = [
      "4x nahoru, vlevo, 2x dolů, vpravo, dolů, vlevo, vpravo, dolů, 2x vlevo",
      "nahoru, 2x vpravo, dolů, vpravo, dolů, vlevo, 3x nahoru, vpravo, dolů, vlevo, dolů, vlevo, dolů, vpravo, dolů, vlevo",
      "nahoru, 3x vpravo, dolů, vlevo, nahoru, vlevo, dolů, vpravo, dolů, 2x vlevo, 2x dolů, 2x vpravo, nahoru, 2x vpravo, 2x dolů, vlevo, nahoru",
    ];
    let sokoban: ProtocolMessage[] = [];
    for (const text of sokobanSolutions) {
      sokoban = await command("player.message", { channel: "lost", text });
    }
    expect(messageOf(sokoban, "sokoban.result").payload.game_complete).toBe(true);

    await scan("sports_cipher");
    await command("puzzle.submit", { puzzle_id: "sports_pigpen", answer: "HODINY" });

    await scan("future_archive");
    const assembly = scenario.puzzles.future_archive_cipher.assembly;
    const currentOrder = [...assembly.initial_order];
    for (const [index, tileId] of assembly.correct_order.entries()) {
      if (currentOrder[index] === tileId) continue;
      const displaced = currentOrder[index];
      const tileIndex = currentOrder.indexOf(tileId);
      await command("archive.arrange", {
        puzzle_id: "future_archive_cipher",
        card_id: tileId,
        target_id: displaced,
        action: "swap",
      });
      [currentOrder[index], currentOrder[tileIndex]] = [currentOrder[tileIndex], currentOrder[index]];
    }
    await command("puzzle.submit", {
      puzzle_id: "future_archive_cipher",
      answer: "ROK DVA NULA TRI SEDM CAS DVA JEDNA CTYRI NULA PORADI MOTOR STABILIZATOR KRYSTAL",
    });

    await scan("time_machine_console");
    const completed = await command("finale.activate", {
      puzzle_id: "time_machine_finale",
      year: "2037",
      time: "21:40",
      modules: ["TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"],
    });
    expect(messageOf(completed, "finale.result").payload.success).toBe(true);
    expect(completed.map((message) => message.type)).toContain("game.complete");
    expect(messageOf(completed, "score.update").payload).toMatchObject({
      bonus: 100,
      reason: "completion_bonus",
    });
    expect(messageOf(completed, "game.complete").payload).toMatchObject({
      score: gameStateOf(completed).score,
      leaderboard_score: gameStateOf(completed).score,
      score_frozen: false,
    });
    expect(gameStateOf(completed)).toMatchObject({
      phase: "portal_open",
      flags: { game_completed: true, elara_rescued: true, room_108_unlocked: true },
      inventory: ["TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"],
    });
    expect(gameStateOf(completed).score).toBeGreaterThan(0);
    const lockedScore = gameStateOf(completed).score;
    const rejectedAfterCompletion = await command("puzzle.hint", { puzzle_id: "future_archive_cipher" });
    expect(messageOf(rejectedAfterCompletion, "command.rejected").payload.reason).toContain("výsledek je uzamčen");
    expect(gameStateOf(rejectedAfterCompletion).score).toBe(lockedScore);
    expect(operationIndex).toBeGreaterThanOrEqual(40);

    await evictDurableObject(stub);
    const finalStatePromise = nextMessage(session, "game.state");
    const finalProgressPromise = nextMessage(session, "scenario.progress");
    session.send(JSON.stringify({ type: "lobby.resume", payload: { session_id: sessionId } }));
    expect((await finalStatePromise).payload).toMatchObject({
      phase: "portal_open",
      flags: { game_completed: true },
    });
    await finalProgressPromise;

    await Promise.all([closeSocket(bootstrap), closeSocket(session)]);
  }, 20_000);

  it("finishes a three-player team journey without leaking private minigame state", async () => {
    const scenarioResponse = await env.ASSETS.fetch("https://assets.local/scenarios/hotel_kraskov.json");
    expect(scenarioResponse.ok).toBe(true);
    const scenario = await scenarioResponse.json<Record<string, any>>();

    const playerIds = ["team-alice", "team-bob", "team-carol"];
    const playerNames = ["Alice", "Bob", "Carol"];
    const bootstrapSockets: WebSocket[] = [];

    const leaderBootstrap = await openSocket(`https://example.test/ws?client_id=${playerIds[0]}`);
    bootstrapSockets.push(leaderBootstrap);
    const createRoutePromise = nextMessage(leaderBootstrap, "lobby.route");
    leaderBootstrap.send(JSON.stringify({
      type: "lobby.create",
      payload: {
        client_id: playerIds[0],
        name: playerNames[0],
        team_name: "Three Player Journey",
        lobby_type: "on_site_qr",
        scenario_id: "hotel_kraskov",
      },
    }));
    const createRoute = await createRoutePromise;
    const sessionId = String(createRoute.payload.session_id);
    const joinCode = String(createRoute.payload.join_code);

    for (let index = 1; index < playerIds.length; index += 1) {
      const bootstrap = await openSocket(`https://example.test/ws?client_id=${playerIds[index]}`);
      bootstrapSockets.push(bootstrap);
      const joinRoutePromise = nextMessage(bootstrap, "lobby.route");
      bootstrap.send(JSON.stringify({
        type: "lobby.join",
        payload: {
          client_id: playerIds[index],
          name: playerNames[index],
          join_code: joinCode,
        },
      }));
      expect((await joinRoutePromise).payload.session_id).toBe(sessionId);
    }

    const sessions = await Promise.all(playerIds.map((clientId) =>
      openSocket(`https://example.test/ws?session_id=${sessionId}&client_id=${clientId}`)
    ));
    for (const session of sessions) {
      const resumed = nextMessage(session, "lobby.state");
      session.send(JSON.stringify({ type: "lobby.resume", payload: { session_id: sessionId } }));
      expect((await resumed).payload).toMatchObject({
        mode: "team",
        player_count: 3,
        registered_players: 3,
        online_count: 3,
        max_players: 3,
      });
    }

    const started = sessions.map((session) => messagesUntil(session, "scenario.progress"));
    sessions[0].send(JSON.stringify({ type: "lobby.start", payload: {} }));
    const startedMessages = await Promise.all(started);
    for (const messages of startedMessages) {
      const lobbyState = messages.filter((message) => message.type === "lobby.state").at(-1);
      expect(lobbyState?.payload).toMatchObject({
        started: true,
        player_count: 3,
        score_adjustment: 0,
      });
      expect(gameStateOf(messages).score).toBe(1000);
    }

    const stub = env.GAME_SESSIONS.getByName(sessionId);
    let operationIndex = 0;
    const command = async (
      playerIndex: number,
      type: string,
      payload: Record<string, unknown> = {},
    ) => {
      operationIndex += 1;
      const operationId = `team-journey-${String(operationIndex).padStart(3, "0")}`;
      const result = messagesUntilOperation(sessions[playerIndex], operationId);
      sessions[playerIndex].send(JSON.stringify({
        type,
        operation_id: operationId,
        payload,
      }));
      return result;
    };
    const scan = async (checkpointId: string) => {
      const messages = await command(0, "qr.detected", {
        value: `escapebot://checkpoint/${scenario.checkpoints[checkpointId].token}`,
      });
      expect(messageOf(messages, "qr.result").payload).toMatchObject({
        accepted: true,
        checkpoint_id: checkpointId,
      });
      return messages;
    };
    const puzzleGame = (gameState: Record<string, any>, puzzleId: string) => {
      const puzzle = gameState.puzzles.find((candidate: Record<string, any>) => candidate.id === puzzleId);
      if (!puzzle?.game) throw new Error(`Response does not contain game state for ${puzzleId}`);
      return puzzle.game as Record<string, any>;
    };

    expect(gameStateOf(await command(0, "player.message", { text: "Příjem" })).phase).toBe("searching_lost");
    expect(gameStateOf(await command(1, "player.message", { text: "734" })).phase).toBe("navigating");

    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as { snapshot: { gameState: Record<string, any> } };
      for (const checkpointId of [
        "reception_archive",
        "staircase_signal",
        "courtyard_minefield",
        "bowling_diagnostics",
      ]) {
        target.snapshot.gameState.checkpoint_states[checkpointId] = { status: "solved" };
      }
      target.snapshot.gameState.flags.room_108_unlocked = true;
      await state.storage.put("session-snapshot", target.snapshot);
    });

    await scan("timeline_calibration");
    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as { snapshot: { gameState: Record<string, any> } };
      const players = target.snapshot.gameState.interactive_games.timeline_lines.players;
      for (const [index, playerId] of playerIds.entries()) {
        const game = players[playerId];
        game.status = "playing";
        game.progress = index === 1 ? { "3": 0, "4": 2, "5": 1 } : { "3": 5, "4": 2, "5": 0 };
        game.board = Array.from({ length: 7 }, (_, row) =>
          Array.from({ length: 7 }, (_, column) => (row + column) % 2 ? "green" : "violet"),
        );
        game.board[0][0] = game.board[0][1] = game.board[0][3] = game.board[1][2] = "cyan";
        game.board[0][2] = "violet";
        game.board[6][6] = ["green", "red", "amber"][index];
      }
      await state.storage.put("session-snapshot", target.snapshot);
    });

    const lineStates: Record<string, any>[] = [];
    for (let index = 0; index < sessions.length; index += 1) {
      const messages = await command(index, "line_game.move", {
        puzzle_id: "timeline_lines",
        first: [0, 2],
        second: [0, 3],
      });
      expect(messageOf(messages, "line_game.result").payload).toMatchObject({
        game_complete: true,
        team_complete: index === sessions.length - 1,
      });
      lineStates.push(gameStateOf(messages));
    }
    expect(lineStates[0]).not.toHaveProperty("interactive_games");
    expect(puzzleGame(lineStates[0], "timeline_lines").board[6][6]).toBe("green");
    expect(puzzleGame(lineStates[1], "timeline_lines").board[6][6]).toBe("red");
    expect(lineStates[2].checkpoint_states.timeline_calibration.status).toBe("solved");

    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as { snapshot: { gameState: Record<string, any> } };
      target.snapshot.gameState.checkpoint_states.terrace_echo = { status: "solved" };
      await state.storage.put("session-snapshot", target.snapshot);
    });
    await scan("courtyard_alignment");
    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as { snapshot: { gameState: Record<string, any> } };
      const players = target.snapshot.gameState.triad_games.temporal_triad.players;
      for (const [index, playerId] of playerIds.entries()) {
        const game = players[playerId];
        game.status = "playing";
        game.board = Array.from({ length: 6 }, () => Array(6).fill(null));
        game.board[0][0] = "amber";
        game.board[1][1] = "amber";
        game.completed_orientations = [index === 1 ? "vertical" : "horizontal"];
        game.scored_lines = [];
        game.board[5 - index][5] = "cyan";
      }
      await state.storage.put("session-snapshot", target.snapshot);
    });

    const triadStates: Record<string, any>[] = [];
    for (let index = 0; index < sessions.length; index += 1) {
      const messages = await command(index, "triad.place", {
        puzzle_id: "temporal_triad",
        row: 2,
        column: 2,
        symbol: "amber",
      });
      expect(messageOf(messages, "triad.result").payload).toMatchObject({
        game_complete: true,
        team_complete: index === sessions.length - 1,
      });
      triadStates.push(gameStateOf(messages));
    }
    expect(triadStates[0]).not.toHaveProperty("triad_games");
    expect(puzzleGame(triadStates[0], "temporal_triad").board[5][5]).toBe("cyan");
    expect(puzzleGame(triadStates[1], "temporal_triad").board[5][5]).toBe(null);
    expect(triadStates[2].checkpoint_states.courtyard_alignment.status).toBe("solved");

    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as { snapshot: { gameState: Record<string, any> } };
      const finale = scenario.puzzles.time_machine_finale;
      for (const checkpointId of finale.requires_checkpoints) {
        target.snapshot.gameState.checkpoint_states[checkpointId] = {
          ...target.snapshot.gameState.checkpoint_states[checkpointId],
          status: "solved",
        };
      }
      target.snapshot.gameState.checkpoint_states.time_machine_console = { status: "found" };
      target.snapshot.gameState.inventory = [...finale.requires_inventory];
      target.snapshot.gameState.flags.room_108_unlocked = true;
      await state.storage.put("session-snapshot", target.snapshot);
    });
    const finaleBroadcast = nextMatchingMessage(
      sessions[1],
      "game.state",
      (message) => message.payload.phase === "portal_open",
    );
    const completed = await command(0, "finale.activate", {
      puzzle_id: "time_machine_finale",
      year: "2037",
      time: "21:40",
      modules: ["TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"],
    });
    expect(messageOf(completed, "finale.result").payload.success).toBe(true);
    expect(completed.map((message) => message.type)).toContain("game.complete");
    expect(gameStateOf(completed)).toMatchObject({
      phase: "portal_open",
      flags: { game_completed: true },
    });
    await finaleBroadcast;

    await evictDurableObject(stub);
    const restored = messagesUntil(sessions[2], "scenario.progress");
    sessions[2].send(JSON.stringify({ type: "lobby.resume", payload: { session_id: sessionId } }));
    const restoredMessages = await restored;
    expect(messageOf(restoredMessages, "lobby.state").payload).toMatchObject({
      player_count: 3,
      registered_players: 3,
      max_players: 3,
    });
    expect(gameStateOf(restoredMessages)).toMatchObject({
      phase: "portal_open",
      flags: { game_completed: true },
    });

    await Promise.all([...bootstrapSockets, ...sessions].map(closeSocket));
  }, 20_000);
});
