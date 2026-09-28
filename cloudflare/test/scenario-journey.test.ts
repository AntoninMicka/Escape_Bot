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

async function openSocket(url: string): Promise<WebSocket> {
  const response = await SELF.fetch(url, { headers: { Upgrade: "websocket" } });
  expect(response.status).toBe(101);
  const socket = response.webSocket;
  if (!socket) throw new Error("WebSocket response is missing a socket");
  socket.accept();
  await nextMessage(socket, "session.connected");
  return socket;
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
    expect(gameStateOf(completed)).toMatchObject({
      phase: "portal_open",
      flags: { game_completed: true, elara_rescued: true, room_108_unlocked: true },
      inventory: ["TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"],
    });
    expect(gameStateOf(completed).score).toBeGreaterThan(0);
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

    bootstrap.close(1000, "done");
    session.close(1000, "done");
  }, 20_000);
});
