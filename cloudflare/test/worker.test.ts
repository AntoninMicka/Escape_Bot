import { env, runDurableObjectAlarm, runInDurableObject, SELF } from "cloudflare:test";
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

  it("generates same-origin QR images with bounded input", async () => {
    const response = await SELF.fetch("https://example.test/api/qr?data=https%3A%2F%2Fexample.test%2F%3Fteam%3D1");
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("image/svg+xml; charset=utf-8");
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.text()).toMatch(/^<svg[^>]+xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);

    expect((await SELF.fetch("https://example.test/api/qr")).status).toBe(400);
    const oversized = new URL("https://example.test/api/qr");
    oversized.searchParams.set("data", "x".repeat(2049));
    expect((await SELF.fetch(oversized)).status).toBe(400);
  });

  it("keeps unknown API routes in the Worker instead of the SPA fallback", async () => {
    const response = await SELF.fetch("https://example.test/api/unknown");
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "not_found" });
  });

  it("reserves a terminal for a puzzle, attaches it without adding a player, and releases it safely", async () => {
    const bootstrap = await openSocket("https://example.test/ws?client_id=terminal-player");
    const routePromise = nextMessage(bootstrap, "lobby.route");
    send(bootstrap, "lobby.solo", {
      client_id: "terminal-player",
      name: "Alice",
      team_name: "Terminal Team",
      lobby_type: "on_site_qr",
      scenario_id: "hotel_kraskov",
    });
    const route = await routePromise;
    const sessionId = String(route.payload.session_id);
    const player = await openSocket(`https://example.test/ws?session_id=${sessionId}&client_id=terminal-player`);
    const playerLobby = nextMessage(player, "lobby.state");
    send(player, "lobby.resume", { session_id: sessionId });
    expect((await playerLobby).payload.player_count).toBe(1);

    const stub = env.GAME_SESSIONS.getByName(sessionId);
    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as {
        snapshot: {
          gameState: { phase: string; checkpoint_states: Record<string, Record<string, unknown>> };
        };
      };
      target.snapshot.gameState.phase = "navigating";
      target.snapshot.gameState.checkpoint_states.future_archive = { status: "solved" };
      await state.storage.put("session-snapshot", target.snapshot);
    });

    const waitingTerminal = await openSocket("https://example.test/ws?client_id=terminal-device-1");
    const readyPromise = nextMessage(waitingTerminal, "terminal.ready");
    send(waitingTerminal, "terminal.register", {
      terminal_id: "terminal-device-1",
      terminal_label: "Tablet A",
    });
    const ready = await readyPromise;
    expect(ready.payload.value).toMatch(/^escapebot:\/\/terminal\/[A-F0-9]{16}$/);
    expect(ready.payload.reserved).toBe(false);

    const reserved = await SELF.fetch("https://example.test/api/admin/terminal-reserve", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer local-test-admin-token",
      },
      body: JSON.stringify({ terminal_id: "terminal-device-1", puzzle_id: "time_machine_finale" }),
    });
    expect(reserved.status).toBe(200);

    const terminalRoutePromise = nextMessage(waitingTerminal, "terminal.route");
    const attachResultPromise = nextMessage(player, "terminal.attach_result");
    send(player, "qr.detected", { value: ready.payload.value });
    expect((await attachResultPromise).payload).toMatchObject({ success: true, session_id: sessionId });
    const terminalRoute = await terminalRoutePromise;
    const routedTerminal = await openSocket(
      `https://example.test/ws?session_id=${sessionId}&client_id=terminal-device-1&terminal_id=terminal-device-1&terminal_token=${terminalRoute.payload.attach_token}`,
    );
    const attachedPromise = nextMessage(routedTerminal, "terminal.attached");
    const terminalStatePromise = nextMessage(routedTerminal, "game.state");
    expect((await attachedPromise).payload.team_name).toBe("Terminal Team");
    const terminalState = await terminalStatePromise;
    expect((terminalState.payload.puzzles as Array<Record<string, any>>).find(
      (puzzle) => puzzle.id === "time_machine_finale",
    )?.terminal).toMatchObject({ device: true, assigned: true, attached: true });

    const overview = await SELF.fetch("https://example.test/api/admin/overview", {
      headers: { Authorization: "Bearer local-test-admin-token" },
    });
    const overviewPayload = await overview.json<Record<string, any>>();
    expect(overviewPayload.teams.find((team: Record<string, unknown>) => team.session_id === sessionId)).toMatchObject({
      player_count: 1,
      registered_players: 1,
      terminal_online: true,
      terminal_assignment: "time_machine_finale",
    });
    expect(overviewPayload.terminals).toContainEqual(expect.objectContaining({
      id: "terminal-device-1",
      status: "attached",
      puzzle_id: "time_machine_finale",
    }));

    await Promise.all([
      closeSocket(waitingTerminal, "routed"),
      closeSocket(routedTerminal, "connection lost"),
    ]);
    const replacementTerminal = await openSocket("https://example.test/ws?client_id=terminal-device-1");
    const replacementReadyPromise = nextMessage(replacementTerminal, "terminal.ready");
    send(replacementTerminal, "terminal.register", {
      terminal_id: "terminal-device-1",
      terminal_label: "Tablet A",
    });
    const replacementReady = await replacementReadyPromise;
    expect(replacementReady.payload).toMatchObject({
      reserved: true,
      puzzle_id: "time_machine_finale",
    });
    const replacementRoutePromise = nextMessage(replacementTerminal, "terminal.route");
    const replacementAttachResultPromise = nextMessage(player, "terminal.attach_result");
    send(player, "qr.detected", { value: replacementReady.payload.value });
    expect((await replacementAttachResultPromise).payload.success).toBe(true);
    const replacementRoute = await replacementRoutePromise;
    const replacementRoutedTerminal = await openSocket(
      `https://example.test/ws?session_id=${sessionId}&client_id=terminal-device-1&terminal_id=terminal-device-1&terminal_token=${replacementRoute.payload.attach_token}`,
    );
    const replacementAttachedPromise = nextMessage(replacementRoutedTerminal, "terminal.attached");
    const replacementStatePromise = nextMessage(replacementRoutedTerminal, "game.state");
    await replacementAttachedPromise;
    await replacementStatePromise;

    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as {
        snapshot: {
          gameState: { checkpoint_states: Record<string, Record<string, unknown>> };
        };
      };
      target.snapshot.gameState.checkpoint_states.time_machine_console = { status: "solved" };
      await state.storage.put("session-snapshot", target.snapshot);
    });
    const releaseScheduledState = nextMessage(player, "game.state");
    const releaseScheduledProgress = nextMessage(player, "scenario.progress");
    player.send(JSON.stringify({
      type: "player.message",
      operation_id: "schedule-terminal-release",
      payload: { text: "Terminál dokončen", channel: "general" },
    }));
    await releaseScheduledState;
    await releaseScheduledProgress;
    expect(await runInDurableObject(stub, (instance) => {
      const target = instance as unknown as { snapshot: { terminalReleaseAt: number | null } };
      return target.snapshot.terminalReleaseAt;
    })).not.toBeNull();
    const releasedPromise = nextMessage(replacementRoutedTerminal, "terminal.released");
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    expect((await releasedPromise).payload.reason).toContain("dokončena");

    const rereadyPromise = nextMessage(replacementTerminal, "terminal.ready");
    send(replacementTerminal, "terminal.register", {
      terminal_id: "terminal-device-1",
      terminal_label: "Tablet A",
    });
    expect((await rereadyPromise).payload).toMatchObject({
      reserved: true,
      puzzle_id: "time_machine_finale",
    });

    const releasedOverview = await SELF.fetch("https://example.test/api/admin/overview", {
      headers: { Authorization: "Bearer local-test-admin-token" },
    });
    const releasedPayload = await releasedOverview.json<Record<string, any>>();
    expect(releasedPayload.terminals).toContainEqual(expect.objectContaining({
      id: "terminal-device-1",
      status: "free",
      puzzle_id: "time_machine_finale",
    }));
    await Promise.all([
      closeSocket(bootstrap, "done"),
      closeSocket(player, "done"),
      closeSocket(replacementTerminal, "done"),
    ]);
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

  it("sends persistent support messages and spectates any registered team player", async () => {
    const sessionId = "admin-support-spectator-session";
    const stub = env.GAME_SESSIONS.getByName(sessionId);
    expect((await stub.fetch("https://internal/internal/lobby/initialize", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        mode: "team",
        creator_id: "spectator-alice",
        team_name: "Support Team",
        join_code: "B0B1C2D3",
        lobby_type: "on_site_qr",
        scenario_id: "hotel_kraskov",
        player_name: "Alice",
      }),
    })).status).toBe(200);
    expect((await stub.fetch("https://internal/internal/lobby/join", {
      method: "POST",
      body: JSON.stringify({ client_id: "spectator-bob", player_name: "Bob" }),
    })).status).toBe(200);

    const creator = await openSocket(
      `https://example.test/ws?session_id=${sessionId}&client_id=spectator-alice`,
    );
    const started = nextMessage(creator, "game.state");
    send(creator, "lobby.start");
    await started;
    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as { snapshot: { revision: number; gameState: Record<string, any> } };
      const game = (marker: string) => ({
        board: Array.from({ length: 7 }, () => Array.from({ length: 7 }, () => marker)),
        deadline_at: "2026-10-10T12:10:00.000Z",
        progress: { "3": 0, "4": 0, "5": 0 },
        status: "active",
      });
      target.snapshot.gameState.checkpoint_states.timeline_calibration = { status: "found" };
      target.snapshot.gameState.interactive_games.timeline_lines = {
        players: {
          "spectator-alice": game("alice-only"),
          "spectator-bob": game("bob-only"),
        },
      };
      target.snapshot.revision += 1;
      await state.storage.put("session-snapshot", target.snapshot);
    });

    const unauthorized = await SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/spectate?player_id=spectator-bob`,
    );
    expect(unauthorized.status).toBe(401);

    const bobView = await SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/spectate?player_id=spectator-bob`,
      { headers: { Authorization: "Bearer local-test-admin-token" } },
    );
    expect(bobView.status).toBe(200);
    const bobPayload = await bobView.json<Record<string, any>>();
    expect(bobPayload).toMatchObject({
      session_id: sessionId,
      team_name: "Support Team",
      player_id: "spectator-bob",
      player_name: "Bob",
    });
    expect(bobPayload.messages.find((message: ProtocolMessage) => message.type === "lobby.state")?.payload)
      .toMatchObject({ is_creator: false, online_count: 1 });
    const bobGameState = bobPayload.messages.find((message: ProtocolMessage) => message.type === "game.state")?.payload;
    expect(bobGameState.puzzles.find((puzzle: Record<string, any>) => puzzle.id === "timeline_lines").game.board[0][0])
      .toBe("bob-only");

    const aliceView = await SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/spectate?player_id=spectator-alice`,
      { headers: { Authorization: "Bearer local-test-admin-token" } },
    );
    const alicePayload = await aliceView.json<Record<string, any>>();
    expect(alicePayload.messages.find((message: ProtocolMessage) => message.type === "lobby.state")?.payload)
      .toMatchObject({ is_creator: true });
    const aliceGameState = alicePayload.messages.find((message: ProtocolMessage) => message.type === "game.state")?.payload;
    expect(aliceGameState.puzzles.find((puzzle: Record<string, any>) => puzzle.id === "timeline_lines").game.board[0][0])
      .toBe("alice-only");

    const delivered = nextMessage(creator, "bot.message");
    const supportRequest = {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer local-test-admin-token",
      },
      body: JSON.stringify({ text: "Jsme připojeni, jak vám můžeme pomoci?", operation_id: "support-message-001" }),
    };
    const support = await SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/support`,
      supportRequest,
    );
    expect(support.status).toBe(200);
    expect(await support.json()).toMatchObject({
      changed: true,
      session_id: sessionId,
      support_chat: [expect.objectContaining({
        role: "bot",
        channel: "support",
        sender: "Game Master",
        text: "Jsme připojeni, jak vám můžeme pomoci?",
      })],
    });
    expect((await delivered).payload).toMatchObject({
      channel: "support",
      sender: "Game Master",
    });

    const duplicate = await SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/support`,
      supportRequest,
    );
    expect(await duplicate.json()).toMatchObject({ changed: false });
    const supportMessages = await runInDurableObject(stub, (instance) => {
      const target = instance as unknown as { snapshot: { chatHistory: Array<Record<string, unknown>> } };
      return target.snapshot.chatHistory.filter((message) => message.channel === "support");
    });
    expect(supportMessages).toHaveLength(1);

    const missingPlayer = await SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/spectate?player_id=missing-player`,
      { headers: { Authorization: "Bearer local-test-admin-token" } },
    );
    expect(missingPlayer.status).toBe(404);
    expect(await missingPlayer.json()).toEqual({ error: "player_not_found" });
    await closeSocket(creator, "done");
  });

  it("exposes idempotent session actions to the Cloudflare admin", async () => {
    const sessionId = "admin-session-actions";
    const stub = env.GAME_SESSIONS.getByName(sessionId);
    expect((await stub.fetch("https://internal/internal/lobby/initialize", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        mode: "solo",
        creator_id: "admin-actions-alice",
        team_name: "Admin Actions Team",
        lobby_type: "on_site_qr",
        scenario_id: "hotel_kraskov",
        player_name: "Alice",
      }),
    })).status).toBe(200);

    const action = (name: string, body: Record<string, unknown>) => SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/${name}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer local-test-admin-token" },
        body: JSON.stringify(body),
      },
    );
    const before = await runInDurableObject(stub, (instance) => {
      const target = instance as unknown as { snapshot: { deadlineAt: number; gameState: { score: number } } };
      return { deadlineAt: target.snapshot.deadlineAt, score: target.snapshot.gameState.score };
    });

    const adjusted = await action("score-adjustment", {
      operation_id: "score-adjustment-001",
      delta: 25,
      reason: "Kompenzace technického výpadku",
    });
    expect(adjusted.status).toBe(200);
    expect(await adjusted.json()).toMatchObject({ changed: true, score: before.score + 25 });
    expect(await (await action("score-adjustment", {
      operation_id: "score-adjustment-001",
      delta: 25,
      reason: "Kompenzace technického výpadku",
    })).json()).toMatchObject({ changed: false, score: before.score + 25 });

    const extended = await action("extend", { operation_id: "extend-001", minutes: 15 });
    expect(extended.status).toBe(200);
    const afterExtension = await runInDurableObject(stub, (instance) => {
      const target = instance as unknown as { snapshot: { deadlineAt: number } };
      return target.snapshot.deadlineAt;
    });
    expect(afterExtension).toBe(before.deadlineAt + 15 * 60_000);

    const ended = await action("end", { operation_id: "end-001", reason: "abandoned" });
    expect(ended.status).toBe(200);
    expect(await ended.json()).toMatchObject({ changed: true, reason: "abandoned", penalty: 100 });
    const finalState = await runInDurableObject(stub, (instance) => {
      const target = instance as unknown as {
        snapshot: { deadlineAt: number | null; gameState: { score: number; flags: Record<string, unknown> } };
      };
      return target.snapshot;
    });
    expect(finalState.deadlineAt).toBeNull();
    expect(finalState.gameState.score).toBe(before.score - 75);
    expect(finalState.gameState.flags).toMatchObject({
      administratively_ended: true,
      administratively_ended_reason: "abandoned",
      deadline_extension_minutes: 15,
    });
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
    expect(overview.admin_capabilities).toEqual({
      checkpoint_states: [],
      game_reset_adapters: [],
      game_player_actions: ["exclude"],
      terminal_reservation: true,
      scenario_play_modes: false,
      terminal_catalog: false,
      terminal_assignment: false,
    });
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

  it("recovers a player onto a new device and transfers persisted game identity once", async () => {
    const creatorBootstrap = await openSocket("https://example.test/ws?client_id=recover-alice");
    const creatorRoutePromise = nextMessage(creatorBootstrap, "lobby.route");
    send(creatorBootstrap, "lobby.create", {
      client_id: "recover-alice",
      name: "Alice",
      team_name: "Recovery Team",
      lobby_type: "online_doom",
      scenario_id: "chronos_online",
    });
    const creatorRoute = await creatorRoutePromise;
    const sessionId = String(creatorRoute.payload.session_id);
    const joinCode = String(creatorRoute.payload.join_code);

    const bobBootstrap = await openSocket("https://example.test/ws?client_id=recover-bob");
    const bobRoutePromise = nextMessage(bobBootstrap, "lobby.route");
    send(bobBootstrap, "lobby.join", {
      client_id: "recover-bob",
      name: "Bob",
      join_code: joinCode,
    });
    await bobRoutePromise;
    const creator = await openSocket(
      `https://example.test/ws?session_id=${sessionId}&client_id=recover-alice`,
    );
    const bob = await openSocket(
      `https://example.test/ws?session_id=${sessionId}&client_id=recover-bob`,
    );
    const startedState = nextMessage(creator, "game.state");
    send(creator, "lobby.start");
    await startedState;

    const stub = env.GAME_SESSIONS.getByName(sessionId);
    await runInDurableObject(stub, async (instance, state) => {
      const target = instance as unknown as {
        snapshot: {
          gameState: Record<string, any>;
          operationReceipts: Record<string, ProtocolMessage[]>;
          identityRecoveryReceipts: Record<string, Record<string, unknown>>;
        };
      };
      target.snapshot.gameState.interactive_games = {
        timeline_lines: { players: { "recover-bob": { marker: "line-board" } } },
      };
      target.snapshot.gameState.triad_games = {
        temporal_triad: { players: { "recover-bob": { marker: "triad-board" } } },
      };
      target.snapshot.gameState.sokoban_games = {
        temporal_sokoban: { level_speakers: ["recover-alice", "recover-bob"] },
      };
      target.snapshot.gameState.game_exclusions = { timeline_lines: ["recover-bob"] };
      target.snapshot.gameState.game_results = {
        timeline_lines: { "recover-bob": { score_delta: 15 } },
      };
      target.snapshot.operationReceipts["recover-bob:move-1"] = [{
        type: "line_game.result",
        payload: { success: true },
      }];
      await state.storage.put("session-snapshot", target.snapshot);
    });

    const recoveryResponse = await SELF.fetch("https://example.test/api/admin/player-recovery", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer local-test-admin-token",
      },
      body: JSON.stringify({ session_id: sessionId, player_id: "recover-bob" }),
    });
    expect(recoveryResponse.status).toBe(200);
    const recovery = await recoveryResponse.json<Record<string, any>>();
    expect(recovery).toMatchObject({ player_name: "Bob", team_name: "Recovery Team", expires_in_seconds: 600 });
    expect(recovery.token).toMatch(/^[A-F0-9]{16}$/);
    const storedRecoveryTokens = await runInDurableObject(
      env.GAME_SESSIONS.getByName("__escape_bot_lobby_directory__"),
      async (_instance, state) => {
        const directory = await state.storage.get<Record<string, any>>("lobby-directory");
        return directory?.recoveryTokens || {};
      },
    );
    expect(Object.keys(storedRecoveryTokens)).toHaveLength(1);
    expect(Object.keys(storedRecoveryTokens)).not.toContain(recovery.token);
    expect(JSON.stringify(storedRecoveryTokens)).not.toContain(recovery.token);
    const recoveryId = Object.keys(storedRecoveryTokens)[0];

    const replacementBootstrap = await openSocket("https://example.test/ws?client_id=recover-bob-new");
    const oldRemoved = nextMessage(bob, "admin.session_removed");
    const recoveredMessage = nextMessage(replacementBootstrap, "lobby.recovered");
    const replacementRoute = nextMessage(replacementBootstrap, "lobby.route");
    send(replacementBootstrap, "lobby.recover", {
      client_id: "recover-bob-new",
      recovery_token: recovery.token,
    });
    expect((await oldRemoved).payload.message).toContain("novém zařízení");
    expect((await recoveredMessage).payload).toMatchObject({ player_name: "Bob", team_name: "Recovery Team" });
    expect((await replacementRoute).payload).toMatchObject({ session_id: sessionId, client_id: "recover-bob-new" });

    const transferred = await runInDurableObject(stub, (instance) => {
      const target = instance as unknown as {
        snapshot: {
          lobby: { players: Record<string, unknown> };
          gameState: Record<string, any>;
          operationReceipts: Record<string, ProtocolMessage[]>;
          identityRecoveryReceipts: Record<string, Record<string, unknown>>;
        };
      };
      return {
        playerIds: Object.keys(target.snapshot.lobby.players),
        line: target.snapshot.gameState.interactive_games.timeline_lines.players,
        triad: target.snapshot.gameState.triad_games.temporal_triad.players,
        speakers: target.snapshot.gameState.sokoban_games.temporal_sokoban.level_speakers,
        exclusions: target.snapshot.gameState.game_exclusions.timeline_lines,
        results: target.snapshot.gameState.game_results.timeline_lines,
        receiptKeys: Object.keys(target.snapshot.operationReceipts),
        recoveryReceiptCount: Object.keys(target.snapshot.identityRecoveryReceipts).length,
      };
    });
    expect(transferred.playerIds).toEqual(["recover-alice", "recover-bob-new"]);
    expect(transferred.line).toEqual({ "recover-bob-new": { marker: "line-board" } });
    expect(transferred.triad).toEqual({ "recover-bob-new": { marker: "triad-board" } });
    expect(transferred.speakers).toEqual(["recover-alice", "recover-bob-new"]);
    expect(transferred.exclusions).toEqual(["recover-bob-new"]);
    expect(transferred.results).toEqual({ "recover-bob-new": { score_delta: 15 } });
    expect(transferred.receiptKeys).toContain("recover-bob-new:move-1");
    expect(transferred.receiptKeys).not.toContain("recover-bob:move-1");
    expect(transferred.recoveryReceiptCount).toBe(1);

    const retry = await stub.fetch("https://internal/internal/lobby/recover", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-EscapeBot-Internal-Recovery": "1",
      },
      body: JSON.stringify({
        old_client_id: "recover-bob",
        new_client_id: "recover-bob-new",
        recovery_id: recoveryId,
      }),
    });
    expect(retry.status).toBe(200);
    expect(await retry.json()).toMatchObject({ revision: 4, new_client_id: "recover-bob-new" });

    const reused = nextMessage(replacementBootstrap, "lobby.error");
    send(replacementBootstrap, "lobby.recover", {
      client_id: "recover-bob-new",
      recovery_token: recovery.token,
    });
    expect((await reused).payload.message).toContain("už byl použit");
    await Promise.all([
      closeSocket(creatorBootstrap, "done"),
      closeSocket(bobBootstrap, "done"),
      closeSocket(creator, "done"),
      closeSocket(replacementBootstrap, "done"),
    ]);
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
