import { SELF } from "cloudflare:test";
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
    socket.close(1000, "done");
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

    bootstrap.close(1000, "routed");
    session.close(1000, "done");
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
    creatorBootstrap.close(1000, "routed");
    playerBootstrap.close(1000, "routed");
    creator.close(1000, "done");
    player.close(1000, "done");
  });
});
