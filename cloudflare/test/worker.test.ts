import { env, runInDurableObject, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

type ProtocolMessage = {
  type: string;
  payload: Record<string, unknown>;
  operation_id?: string;
};

function nextMessage(socket: WebSocket, expectedType: string): Promise<ProtocolMessage> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${expectedType}`)), 2000);
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

function nextMessageOf(socket: WebSocket, expectedTypes: string[]): Promise<ProtocolMessage> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${expectedTypes.join("/")}`)), 2000);
    const listener = (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as ProtocolMessage;
      if (!expectedTypes.includes(message.type)) return;
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
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${finalType}`)), 2000);
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

function send(socket: WebSocket, type: string, payload: Record<string, unknown> = {}) {
  socket.send(JSON.stringify({ type, payload }));
}

function closeSocket(socket: WebSocket, reason: string): Promise<void> {
  if (socket.readyState === WebSocket.CLOSED) return Promise.resolve();
  return new Promise((resolve) => {
    socket.addEventListener("close", () => resolve(), { once: true });
    socket.close(1000, reason);
  });
}

describe("Cloudflare spike router", () => {
  it("serves the application shell from Static Assets", async () => {
    const response = await SELF.fetch("https://example.test/");
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("text/html; charset=utf-8");
    expect(response.headers.get("Cache-Control")).toBe("no-cache");
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
    const html = await response.text();
    expect(html).toContain("Escape Bot · Chronoterminál");
    const applicationScript = html.match(/src="(assets\/app\/operation-queue-[a-f0-9]{12}\.js)"/);
    expect(applicationScript).not.toBeNull();
    const script = await SELF.fetch(`https://example.test/${applicationScript?.[1]}`);
    expect(script.status).toBe(200);
    expect(script.headers.get("Cache-Control")).toContain("immutable");
  });

  it.each(["/admin", "/terminal"])("serves the application shell at %s", async (path) => {
    const response = await SELF.fetch(`https://example.test${path}`);
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-cache");
    expect(await response.text()).toContain("Escape Bot · Chronoterminál");
  });

  it("serves the public display and WebGL build", async () => {
    const display = await SELF.fetch("https://example.test/display");
    expect(display.status).toBe(200);
    expect(await display.text()).toContain("Escape Bot · Fronta a pořadí");

    const webgl = await SELF.fetch("https://example.test/chronos-webgl/dist/index.html");
    expect(webgl.status).toBe(200);
    expect(webgl.headers.get("Cache-Control")).toContain("max-age=0");
    const webglHtml = await webgl.text();
    const webglScript = webglHtml.match(/src="\.\/(assets\/chronos-[A-Za-z0-9_-]+\.js)"/);
    expect(webglScript).not.toBeNull();
    const webglAsset = await SELF.fetch(
      `https://example.test/chronos-webgl/dist/${webglScript?.[1]}`,
    );
    expect(webglAsset.status).toBe(200);
    expect(webglAsset.headers.get("Cache-Control")).toContain("immutable");
  });

  it("reports health without touching a game session", async () => {
    const response = await SELF.fetch("https://example.test/api/health");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      status: "ok",
      runtime: "cloudflare",
      environment: "local",
    });
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
  });

  it("keeps unknown API routes in the Worker instead of the SPA fallback", async () => {
    const response = await SELF.fetch("https://example.test/api/unknown");
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "not_found" });
  });

  it("authenticates admin exclusion and persists it for an offline registered player", async () => {
    const sessionId = "admin-offline-session";
    const stub = env.GAME_SESSIONS.getByName(sessionId);
    const initialized = await stub.fetch("https://internal/internal/lobby/initialize", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        mode: "team",
        creator_id: "admin-alice",
        team_name: "Offline Admin Team",
        join_code: "A0B1C2D3",
        lobby_type: "on_site_qr",
        scenario_id: "chronos_online",
        player_name: "Alice",
      }),
    });
    expect(initialized.status).toBe(200);
    const joined = await stub.fetch("https://internal/internal/lobby/join", {
      method: "POST",
      body: JSON.stringify({ client_id: "offline-bob", player_name: "Bob" }),
    });
    expect(joined.status).toBe(200);

    const creator = await openSocket(
      `https://example.test/ws?session_id=${sessionId}&client_id=admin-alice`,
    );
    const startedState = nextMessage(creator, "game.state");
    send(creator, "lobby.start");
    await startedState;
    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as {
        snapshot: { gameState: { checkpoint_states: Record<string, Record<string, unknown>> } };
      };
      target.snapshot.gameState.checkpoint_states.timeline_calibration = { status: "found" };
      await state.storage.put("session-snapshot", target.snapshot);
    });

    const payload = {
      session_id: sessionId,
      puzzle_id: "timeline_lines",
      player_id: "offline-bob",
      action: "exclude",
    };
    const unauthorized = await SELF.fetch("https://example.test/api/admin/game-player", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer wrong-token" },
      body: JSON.stringify(payload),
    });
    expect(unauthorized.status).toBe(401);
    expect(await unauthorized.json()).toEqual({ error: "unauthorized" });

    const response = await SELF.fetch("https://example.test/api/admin/game-player", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer local-test-admin-token",
      },
      body: JSON.stringify(payload),
    });
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      success: true,
      action: "exclude",
      changed: true,
      session_id: sessionId,
      player_id: "offline-bob",
      player_name: "Bob",
    });
    const duplicate = await SELF.fetch("https://example.test/api/admin/game-player", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer local-test-admin-token",
      },
      body: JSON.stringify(payload),
    });
    expect(duplicate.status).toBe(200);
    expect(await duplicate.json()).toMatchObject({ changed: false, revision: 4 });
    const exclusions = await runInDurableObject(stub, (instance) => {
      const target = instance as unknown as {
        snapshot: { gameState: { game_exclusions: Record<string, string[]> } };
      };
      return target.snapshot.gameState.game_exclusions.timeline_lines;
    });
    expect(exclusions).toEqual(["offline-bob"]);
    await closeSocket(creator, "done");
  });

  it("loads registered teams through the authenticated Cloudflare admin overview", async () => {
    const bootstrap = await openSocket("https://example.test/ws?client_id=overview-alice");
    const routePromise = nextMessage(bootstrap, "lobby.route");
    send(bootstrap, "lobby.create", {
      client_id: "overview-alice",
      name: "Alice",
      team_name: "Admin Overview Team",
      lobby_type: "online_doom",
      scenario_id: "chronos_online",
    });
    const route = await routePromise;

    const unauthorized = await SELF.fetch("https://example.test/api/admin/overview");
    expect(unauthorized.status).toBe(401);
    const response = await SELF.fetch("https://example.test/api/admin/overview", {
      headers: { Authorization: "Bearer local-test-admin-token" },
    });
    expect(response.status).toBe(200);
    const overview = await response.json<Record<string, any>>();
    expect(overview.cloudflare_limited).toBe(true);
    expect(overview.teams).toEqual(expect.arrayContaining([
      expect.objectContaining({
        session_id: route.payload.session_id,
        team_name: "Admin Overview Team",
        registered_players: 1,
        online_count: 0,
        started: false,
        players: [expect.objectContaining({ id: "overview-alice", name: "Alice", connected: false })],
      }),
    ]));
    await closeSocket(bootstrap, "done");
  });

  it("rejects invalid session routing", async () => {
    const response = await SELF.fetch("https://example.test/ws?session_id=x&client_id=phone", {
      headers: { Upgrade: "websocket" },
    });
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid_session_or_client_id" });
  });

  it("routes a valid WebSocket to its session object", async () => {
    const response = await SELF.fetch(
      "https://example.test/ws?session_id=router-session&client_id=phone",
      { headers: { Upgrade: "websocket" } },
    );
    expect(response.status).toBe(101);
    const socket = response.webSocket;
    if (!socket) throw new Error("WebSocket response is missing a socket");
    socket.accept();

    const connected = await new Promise<{ type: string; payload: Record<string, unknown> }>(
      (resolve) => {
        socket.addEventListener(
          "message",
          (event) => resolve(JSON.parse(String(event.data))),
          { once: true },
        );
      },
    );
    expect(connected).toEqual({
      type: "session.connected",
      payload: {
        session_id: "router-session",
        client_id: "phone",
        revision: 0,
        bootstrap: false,
      },
    });
    await closeSocket(socket, "done");
  });

  it("creates a solo lobby through bootstrap and resumes its authoritative snapshot", async () => {
    const bootstrap = await openSocket("https://example.test/ws?client_id=solo-phone");
    const runtime = nextMessage(bootstrap, "runtime.settings");
    const route = nextMessageOf(bootstrap, ["lobby.route", "lobby.error"]);
    send(bootstrap, "lobby.solo", {
      client_id: "solo-phone",
      name: "Alice",
      team_name: "Solo Chronos",
      lobby_type: "online_doom",
      scenario_id: "chronos_online",
    });
    expect((await runtime).payload.games).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: "chronos_online" })]),
    );
    const routed = await route;
    expect(routed.type, JSON.stringify(routed.payload)).toBe("lobby.route");
    expect(routed.payload.session_id).toMatch(/^[a-f0-9]{32}$/);
    expect(routed.payload.mode).toBe("solo");

    const session = await openSocket(
      `https://example.test/ws?session_id=${routed.payload.session_id}&client_id=solo-phone`,
    );
    const lobby = nextMessage(session, "lobby.state");
    const history = nextMessage(session, "chat.history");
    const game = nextMessage(session, "game.state");
    const progress = nextMessage(session, "scenario.progress");
    send(session, "lobby.resume", { session_id: routed.payload.session_id });

    expect((await lobby).payload).toMatchObject({
      mode: "solo",
      team_name: "Solo Chronos",
      started: true,
      player_count: 1,
      online_count: 1,
    });
    expect((await history).payload.messages).toEqual([
      expect.objectContaining({ role: "bot", channel: "captain" }),
    ]);
    expect((await game).payload).toMatchObject({ phase: "comms_offline", score: 1020 });
    expect((await progress).payload).toMatchObject({
      scenario_id: "chronos_online_rescue",
      current_phase: "comms_offline",
      score: 1020,
    });

    await Promise.all([closeSocket(bootstrap, "routed"), closeSocket(session, "done")]);
  });

  it("persists an idempotent checkpoint and answer-puzzle journey", async () => {
    const bootstrap = await openSocket("https://example.test/ws?client_id=checkpoint-phone");
    const routePromise = nextMessage(bootstrap, "lobby.route");
    send(bootstrap, "lobby.solo", {
      client_id: "checkpoint-phone",
      name: "Alice",
      team_name: "Checkpoint Team",
      lobby_type: "online_doom",
      scenario_id: "chronos_online",
    });
    const route = await routePromise;
    const session = await openSocket(
      `https://example.test/ws?session_id=${route.payload.session_id}&client_id=checkpoint-phone`,
    );

    const connectedState = nextMessage(session, "game.state");
    const connectedProgress = nextMessage(session, "scenario.progress");
    session.send(JSON.stringify({
      type: "player.message",
      operation_id: "checkpoint-intro-1",
      payload: { text: "Slyšíme se" },
    }));
    expect((await connectedState).payload.phase).toBe("searching_lost");
    await connectedProgress;

    const navigatingState = nextMessage(session, "game.state");
    const navigatingProgress = nextMessage(session, "scenario.progress");
    session.send(JSON.stringify({
      type: "player.message",
      operation_id: "checkpoint-intro-2",
      payload: { text: "Frekvence je 734" },
    }));
    expect((await navigatingState).payload.phase).toBe("navigating");
    await navigatingProgress;

    const qrResult = nextMessage(session, "qr.result");
    const foundState = nextMessage(session, "game.state");
    const foundProgress = nextMessage(session, "scenario.progress");
    session.send(JSON.stringify({
      type: "qr.detected",
      operation_id: "checkpoint-scan-1",
      payload: {
        value: "escapebot://checkpoint/4ec67b900c4a491ba180c8a48d5309f2",
      },
    }));
    expect((await qrResult).payload).toMatchObject({
      accepted: true,
      checkpoint_id: "reception_archive",
      puzzle_id: "reception_deduction",
      status: "found",
    });
    expect((await foundState).payload.checkpoint_states).toMatchObject({
      reception_archive: { status: "found" },
    });
    await foundProgress;

    const hintScore = nextMessage(session, "score.update");
    const hintedState = nextMessage(session, "game.state");
    const hintedProgress = nextMessage(session, "scenario.progress");
    session.send(JSON.stringify({
      type: "puzzle.hint",
      operation_id: "checkpoint-hint-1",
      payload: { puzzle_id: "reception_deduction", hint_index: 0 },
    }));
    expect((await hintScore).payload).toMatchObject({ score: 1010, penalty: 10 });
    expect((await hintedState).payload.score).toBe(1010);
    await hintedProgress;

    const puzzleResult = nextMessage(session, "puzzle.result");
    const solvedState = nextMessage(session, "game.state");
    const solvedProgress = nextMessage(session, "scenario.progress");
    session.send(JSON.stringify({
      type: "puzzle.submit",
      operation_id: "checkpoint-answer-1",
      payload: { puzzle_id: "reception_deduction", answer: "2 1 4 7" },
    }));
    expect((await puzzleResult).payload).toMatchObject({ correct: true, attempts: 1 });
    expect((await solvedState).payload).toMatchObject({
      score: 1010,
      puzzle_attempts: { reception_deduction: 1 },
      checkpoint_states: { reception_archive: { status: "solved" } },
      flags: { reception_archive_unlocked: true },
    });
    expect((await solvedProgress).payload.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: "staircase_signal", status: "available" }),
      ]),
    );

    const replay = nextMessage(session, "puzzle.result");
    const replayState = nextMessage(session, "game.state");
    const replayProgress = nextMessage(session, "scenario.progress");
    session.send(JSON.stringify({
      type: "puzzle.submit",
      operation_id: "checkpoint-answer-1",
      payload: { puzzle_id: "reception_deduction", answer: "wrong retry payload" },
    }));
    expect(await replay).toMatchObject({
      operation_id: "checkpoint-answer-1",
      payload: { correct: true, attempts: 1 },
    });
    await replayState;
    await replayProgress;

    const restoredState = nextMessage(session, "game.state");
    const restoredProgress = nextMessage(session, "scenario.progress");
    send(session, "lobby.resume", { session_id: route.payload.session_id });
    expect((await restoredState).payload).toMatchObject({
      score: 1010,
      puzzle_attempts: { reception_deduction: 1 },
      checkpoint_states: { reception_archive: { status: "solved" } },
    });
    await restoredProgress;

    await Promise.all([closeSocket(bootstrap, "routed"), closeSocket(session, "done")]);
  });

  it("resolves a team join code and broadcasts both registered players", async () => {
    const creatorBootstrap = await openSocket("https://example.test/ws?client_id=creator-phone");
    const creatorRoutePromise = nextMessage(creatorBootstrap, "lobby.route");
    send(creatorBootstrap, "lobby.create", {
      client_id: "creator-phone",
      name: "Alice",
      team_name: "Cloud Team",
      lobby_type: "online_doom",
      scenario_id: "chronos_online",
    });
    const creatorRoute = await creatorRoutePromise;
    expect(creatorRoute.payload.join_code).toMatch(/^[A-F0-9]{8}$/);

    const creator = await openSocket(
      `https://example.test/ws?session_id=${creatorRoute.payload.session_id}&client_id=creator-phone`,
    );
    const creatorLobby = nextMessage(creator, "lobby.state");
    send(creator, "lobby.resume", { session_id: creatorRoute.payload.session_id });
    expect((await creatorLobby).payload.player_count).toBe(1);

    const playerBootstrap = await openSocket("https://example.test/ws?client_id=second-phone");
    const playerRoutePromise = nextMessage(playerBootstrap, "lobby.route");
    const joinedLobby = nextMessage(creator, "lobby.state");
    send(playerBootstrap, "lobby.join", {
      client_id: "second-phone",
      name: "Bob",
      join_code: creatorRoute.payload.join_code,
    });
    const playerRoute = await playerRoutePromise;
    expect(playerRoute.payload.session_id).toBe(creatorRoute.payload.session_id);
    expect((await joinedLobby).payload).toMatchObject({ player_count: 2, online_count: 1 });

    const player = await openSocket(
      `https://example.test/ws?session_id=${playerRoute.payload.session_id}&client_id=second-phone`,
    );
    const bothOnline = nextMessage(creator, "lobby.state");
    send(player, "lobby.resume", { session_id: playerRoute.payload.session_id });
    expect((await bothOnline).payload).toMatchObject({ player_count: 2, online_count: 2 });

    const startedLobby = nextMessage(player, "lobby.state");
    const startedHistory = nextMessage(player, "chat.history");
    const startedGame = nextMessage(player, "game.state");
    const startedProgress = nextMessage(player, "scenario.progress");
    send(creator, "lobby.start", { client_id: "creator-phone" });
    expect((await startedLobby).payload.started).toBe(true);
    expect((await startedHistory).payload.messages).toEqual([
      expect.objectContaining({ role: "bot", channel: "captain" }),
    ]);
    expect((await startedGame).payload).toMatchObject({ phase: "comms_offline", score: 1010 });
    expect((await startedProgress).payload).toMatchObject({ scenario_id: "chronos_online_rescue" });

    const privateLineResult = nextMessage(creator, "line_game.result");
    const privateLineState = nextMessage(creator, "game.state");
    const privateLineProgress = nextMessage(creator, "scenario.progress");
    const teammateTraffic = messagesUntil(player, "game.state");
    creator.send(JSON.stringify({
      type: "line_game.move",
      operation_id: "early-line-game-1",
      payload: { puzzle_id: "timeline_lines", first: [0, 0], second: [0, 1] },
    }));
    expect((await privateLineResult).payload).toMatchObject({
      success: false,
      reason: "Interaktivní úloha zatím nebyla nalezena.",
    });
    expect((await privateLineState).payload).not.toHaveProperty("interactive_games");
    await privateLineProgress;
    expect((await teammateTraffic).map((message) => message.type)).not.toContain("line_game.result");

    const creatorKarel = nextMessage(creator, "karel.result");
    const creatorKarelState = nextMessage(creator, "game.state");
    const creatorKarelProgress = nextMessage(creator, "scenario.progress");
    const teammateKarel = nextMessage(player, "karel.result");
    const teammateKarelState = nextMessage(player, "game.state");
    const teammateKarelProgress = nextMessage(player, "scenario.progress");
    creator.send(JSON.stringify({
      type: "karel.command",
      operation_id: "early-karel-1",
      payload: { puzzle_id: "courtyard_karel", commands: ["right"] },
    }));
    expect((await creatorKarel).payload).toMatchObject({
      success: false,
      reason: "Navigační pole není aktivní.",
    });
    expect((await teammateKarel).payload).toMatchObject({ success: false });
    expect((await creatorKarelState).payload).not.toHaveProperty("karel_games");
    expect((await teammateKarelState).payload).not.toHaveProperty("karel_games");
    await creatorKarelProgress;
    await teammateKarelProgress;

    const creatorSokoban = nextMessage(creator, "sokoban.result");
    const creatorSokobanState = nextMessage(creator, "game.state");
    const creatorSokobanProgress = nextMessage(creator, "scenario.progress");
    const teammateSokoban = nextMessage(player, "sokoban.result");
    const teammateSokobanState = nextMessage(player, "game.state");
    const teammateSokobanProgress = nextMessage(player, "scenario.progress");
    creator.send(JSON.stringify({
      type: "sokoban.command",
      operation_id: "early-sokoban-1",
      payload: { puzzle_id: "sports_sokoban", commands: ["left"] },
    }));
    expect((await creatorSokoban).payload).toMatchObject({
      success: false,
      reason: "Energetická mřížka zatím nebyla nalezena.",
    });
    expect((await teammateSokoban).payload).toMatchObject({ success: false });
    expect((await creatorSokobanState).payload).not.toHaveProperty("sokoban_games");
    expect((await teammateSokobanState).payload).not.toHaveProperty("sokoban_games");
    await creatorSokobanProgress;
    await teammateSokobanProgress;

    const creatorArchive = nextMessage(creator, "archive.result");
    const creatorArchiveState = nextMessage(creator, "game.state");
    const creatorArchiveProgress = nextMessage(creator, "scenario.progress");
    const teammateArchive = nextMessage(player, "archive.result");
    const teammateArchiveState = nextMessage(player, "game.state");
    const teammateArchiveProgress = nextMessage(player, "scenario.progress");
    creator.send(JSON.stringify({
      type: "archive.arrange",
      operation_id: "early-archive-1",
      payload: { puzzle_id: "future_archive_cipher", card_id: "tile_1", target_id: "tile_2", action: "swap" },
    }));
    expect((await creatorArchive).payload).toMatchObject({
      success: false,
      reason: "Archivní skládačka nyní není aktivní.",
    });
    expect((await teammateArchive).payload).toMatchObject({ success: false });
    expect((await creatorArchiveState).payload).not.toHaveProperty("archive_games");
    expect((await teammateArchiveState).payload).not.toHaveProperty("archive_games");
    await creatorArchiveProgress;
    await teammateArchiveProgress;

    const creatorFinale = nextMessage(creator, "finale.result");
    const creatorFinaleState = nextMessage(creator, "game.state");
    const creatorFinaleProgress = nextMessage(creator, "scenario.progress");
    const teammateFinale = nextMessage(player, "finale.result");
    const teammateFinaleState = nextMessage(player, "game.state");
    const teammateFinaleProgress = nextMessage(player, "scenario.progress");
    creator.send(JSON.stringify({
      type: "finale.activate",
      operation_id: "early-finale-1",
      payload: { puzzle_id: "time_machine_finale", year: "2037", time: "21:40", modules: [] },
    }));
    expect((await creatorFinale).payload).toMatchObject({
      success: false,
      reason: "Finální terminál zatím nebyl nalezen.",
    });
    expect((await teammateFinale).payload).toMatchObject({ success: false });
    await creatorFinaleState;
    await teammateFinaleState;
    await creatorFinaleProgress;
    await teammateFinaleProgress;

    const creatorRestore = nextMessage(creator, "team_game.player.result");
    const creatorRestoreState = nextMessage(creator, "game.state");
    const creatorRestoreProgress = nextMessage(creator, "scenario.progress");
    const teammateRestore = nextMessage(player, "team_game.player.result");
    const teammateRestoreState = nextMessage(player, "game.state");
    const teammateRestoreProgress = nextMessage(player, "scenario.progress");
    creator.send(JSON.stringify({
      type: "team_game.player.restore",
      operation_id: "early-player-restore-1",
      payload: { puzzle_id: "timeline_lines", player_id: "second-phone" },
    }));
    expect((await creatorRestore).payload).toMatchObject({
      success: false,
      reason: "Spoluhráče lze obnovit pouze v aktivní týmové minihře.",
    });
    expect((await teammateRestore).payload).toMatchObject({ success: false });
    await creatorRestoreState;
    await teammateRestoreState;
    await creatorRestoreProgress;
    await teammateRestoreProgress;

    const creatorTriad = nextMessage(creator, "triad.result");
    const creatorTriadState = nextMessage(creator, "game.state");
    const creatorTriadProgress = nextMessage(creator, "scenario.progress");
    const teammateTriad = nextMessage(player, "triad.result");
    const teammateTriadState = nextMessage(player, "game.state");
    const teammateTriadProgress = nextMessage(player, "scenario.progress");
    creator.send(JSON.stringify({
      type: "triad.place",
      operation_id: "early-triad-1",
      payload: { puzzle_id: "temporal_triad", row: 0, column: 0, symbol: "cyan" },
    }));
    expect((await creatorTriad).payload).toMatchObject({ success: false, reason: "Pole není aktivní." });
    expect((await teammateTriad).payload).toMatchObject({ success: false });
    expect((await creatorTriadState).payload).not.toHaveProperty("triad_games");
    expect((await teammateTriadState).payload).not.toHaveProperty("triad_games");
    await creatorTriadProgress;
    await teammateTriadProgress;

    const teammateMessage = nextMessage(player, "team.player_message");
    const narrativeReply = nextMessage(player, "bot.message");
    const narrativeState = nextMessage(player, "game.state");
    const narrativeProgress = nextMessage(player, "scenario.progress");
    creator.send(JSON.stringify({
      type: "player.message",
      operation_id: "narrative-step-1",
      payload: { text: "Slyšíme se", channel: "captain" },
    }));
    expect((await teammateMessage).payload.text).toBe("Slyšíme se");
    expect((await narrativeReply).payload.text).toContain("spojení funguje");
    expect((await narrativeState).payload).toMatchObject({ phase: "searching_lost", score: 1010 });
    await narrativeProgress;

    const replayReply = nextMessage(creator, "bot.message");
    const replay = nextMessage(creator, "game.state");
    const replayProgress = nextMessage(creator, "scenario.progress");
    creator.send(JSON.stringify({
      type: "player.message",
      operation_id: "narrative-step-1",
      payload: { text: "Slyšíme se", channel: "captain" },
    }));
    await replayReply;
    expect((await replay).operation_id).toBe("narrative-step-1");
    await replayProgress;

    const hintScore = nextMessage(player, "score.update");
    const hintMessage = nextMessage(player, "bot.message");
    const hintedState = nextMessage(player, "game.state");
    const hintedProgress = nextMessage(player, "scenario.progress");
    player.send(JSON.stringify({
      type: "phase.hint",
      operation_id: "phase-hint-1",
      payload: { phase_id: "searching_lost", hint_index: 0 },
    }));
    expect((await hintScore).payload).toMatchObject({ score: 1000, penalty: 10 });
    expect((await hintMessage).payload.text).toContain("NÁPOVĚDA SYSTÉMU");
    expect((await hintedState).payload).toMatchObject({ score: 1000 });
    await hintedProgress;

    const restoredHistory = nextMessage(creator, "chat.history");
    const restoredGame = nextMessage(creator, "game.state");
    const restoredProgress = nextMessage(creator, "scenario.progress");
    send(creator, "lobby.resume", { session_id: creatorRoute.payload.session_id });
    expect(((await restoredHistory).payload.messages as unknown[]).length).toBe(4);
    expect((await restoredGame).payload).toMatchObject({
      phase: "searching_lost",
      score: 1000,
      phase_hints: { unlocked: 1 },
    });
    await restoredProgress;
    await Promise.all([
      closeSocket(creatorBootstrap, "routed"),
      closeSocket(playerBootstrap, "routed"),
      closeSocket(creator, "done"),
      closeSocket(player, "done"),
    ]);
  });
});
