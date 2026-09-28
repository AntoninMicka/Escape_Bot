import { DurableObject } from "cloudflare:workers";
import {
  applyAdminGamePlayerExclusion,
  applyScenarioCommand,
  buildScenarioProgress,
  presentGameState,
  startScenario,
  type GameStateDocument,
  type RuntimeActor,
  type ScenarioDocument,
} from "./scenario-runtime";

interface Env {
  APP_ENV: string;
  ADMIN_TOKEN?: string;
  GAME_DURATION_MINUTES?: string;
  DEADLINE_PENALTY?: string;
  ASSETS: Fetcher;
  GAME_SESSIONS: DurableObjectNamespace<GameSession>;
}

interface SocketAttachment {
  clientId: string;
  connectedAt: string;
  role: "bootstrap" | "session";
}

interface ProtocolMessage {
  type: string;
  payload?: Record<string, unknown>;
  request_id?: string;
  operation_id?: string;
}

interface LobbyPlayer {
  id: string;
  name: string;
  joinedAt: string;
}

interface LobbySnapshot {
  mode: "solo" | "team";
  creatorId: string;
  teamName: string;
  joinCode: string | null;
  started: boolean;
  lobbyType: string;
  scenarioId: string;
  players: Record<string, LobbyPlayer>;
  maxPlayers: number;
  appliedScoreAdjustment: number;
}

interface SessionSnapshot {
  schemaVersion: 2;
  sessionId: string;
  revision: number;
  lobby: LobbySnapshot;
  chatHistory: Array<Record<string, unknown>>;
  gameState: GameStateDocument;
  scenarioProgress: Record<string, unknown>;
  operationReceipts: Record<string, ProtocolMessage[]>;
  deadlineAt: number | null;
  deadlineKind: "game" | "spike" | null;
  updatedAt: string;
}

interface DirectorySnapshot {
  schemaVersion: 1;
  joinCodes: Record<string, string>;
  teamKeys: Record<string, string>;
  creatorKeys: Record<string, string>;
}

interface RuntimeGame {
  id: string;
  title: string;
  template_id: string;
  template_version: string;
  realization_version: string;
  modes: string[];
  lobby_types: string[];
}

const SNAPSHOT_KEY = "session-snapshot";
const DIRECTORY_KEY = "lobby-directory";
const DIRECTORY_OBJECT_NAME = "__escape_bot_lobby_directory__";
const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{8,128}$/;
const CLIENT_ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const JOIN_CODE_PATTERN = /^[A-F0-9]{8}$/;

function json(data: unknown, status = 200): Response {
  const response = Response.json(data, { status });
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()");
  response.headers.set("Referrer-Policy", "same-origin");
  response.headers.set("X-Content-Type-Options", "nosniff");
  return response;
}

function protocolMessage(
  type: string,
  payload: Record<string, unknown>,
  requestId?: string,
  operationId?: string,
): string {
  return JSON.stringify({
    type,
    payload,
    ...(requestId ? { request_id: requestId } : {}),
    ...(operationId ? { operation_id: operationId } : {}),
  });
}

function defaultSnapshot(sessionId = ""): SessionSnapshot {
  return {
    schemaVersion: 2,
    sessionId,
    revision: 0,
    lobby: {
      mode: "team",
      creatorId: "",
      teamName: "",
      joinCode: null,
      started: false,
      lobbyType: "on_site_qr",
      scenarioId: "hotel_kraskov",
      players: {},
      maxPlayers: 0,
      appliedScoreAdjustment: 0,
    },
    chatHistory: [],
    gameState: { phase: "lobby", score: 0, flags: {} },
    scenarioProgress: { completed: [], available: [] },
    operationReceipts: {},
    deadlineAt: null,
    deadlineKind: null,
    updatedAt: new Date(0).toISOString(),
  };
}

function normalizeSnapshot(
  stored: SessionSnapshot | (Omit<SessionSnapshot, "schemaVersion" | "lobby"> & {
    schemaVersion?: number;
    lobby?: Partial<LobbySnapshot>;
  }) | undefined,
): SessionSnapshot {
  const fallback = defaultSnapshot(stored?.sessionId ?? "");
  if (!stored) return fallback;
  return {
    ...fallback,
    ...stored,
    schemaVersion: 2,
    lobby: { ...fallback.lobby, ...stored.lobby },
    gameState: { ...fallback.gameState, ...stored.gameState },
    scenarioProgress: { ...fallback.scenarioProgress, ...stored.scenarioProgress },
  };
}

function defaultDirectory(): DirectorySnapshot {
  return { schemaVersion: 1, joinCodes: {}, teamKeys: {}, creatorKeys: {} };
}

function cleanText(value: unknown, maximum: number): string {
  return String(value ?? "").trim().replace(/\s+/g, " ").slice(0, maximum);
}

function normalizedTeamKey(lobbyType: string, scenarioId: string, teamName: string): string {
  return `${lobbyType}\u0000${scenarioId}\u0000${teamName.normalize("NFKC").toLocaleLowerCase("cs-CZ")}`;
}

function teamSizeAdjustment(mode: "solo" | "team", maximumPlayers: number): number {
  if (mode === "solo") return 20;
  if (maximumPlayers < 3) return (3 - maximumPlayers) * 10;
  if (maximumPlayers > 3) return -(maximumPlayers - 3) * 30;
  return 0;
}

function boundedInteger(value: unknown, fallback: number, minimum: number, maximum: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : fallback;
}

async function equalSecret(left: string, right: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const [leftHash, rightHash] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(left)),
    crypto.subtle.digest("SHA-256", encoder.encode(right)),
  ]);
  const leftBytes = new Uint8Array(leftHash);
  const rightBytes = new Uint8Array(rightHash);
  let difference = leftBytes.length ^ rightBytes.length;
  for (let index = 0; index < leftBytes.length; index += 1) {
    difference |= leftBytes[index] ^ (rightBytes[index] ?? 0);
  }
  return difference === 0;
}

async function authorizeAdmin(request: Request, env: Env): Promise<Response | null> {
  const configured = String(env.ADMIN_TOKEN || "");
  if (!configured) return json({ error: "admin_disabled" }, 503);
  const authorization = request.headers.get("Authorization") || "";
  const supplied = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!supplied || !(await equalSecret(supplied, configured))) {
    return json({ error: "unauthorized" }, 401);
  }
  return null;
}

function randomJoinCode(): string {
  const values = crypto.getRandomValues(new Uint8Array(4));
  return [...values].map((value) => value.toString(16).padStart(2, "0")).join("").toUpperCase();
}

export class GameSession extends DurableObject<Env> {
  private snapshot: SessionSnapshot = defaultSnapshot();
  private readonly runtimeEnv: Env;
  private directoryQueue: Promise<void> = Promise.resolve();
  private stateQueue: Promise<void> = Promise.resolve();

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.runtimeEnv = env;
    ctx.blockConcurrencyWhile(async () => {
      this.snapshot = normalizeSnapshot(await ctx.storage.get<SessionSnapshot>(SNAPSHOT_KEY));
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/internal/admin/game-player" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Admin") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeState(() => this.excludeGamePlayer(payload));
    }
    if (url.pathname === "/internal/lobby/initialize" && request.method === "POST") {
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeState(() => this.initializeLobby(payload));
    }
    if (url.pathname === "/internal/lobby/join" && request.method === "POST") {
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeState(() => this.joinLobby(payload));
    }
    if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket") {
      return json({ error: "websocket_upgrade_required" }, 426);
    }

    const clientId = url.searchParams.get("client_id") ?? "";
    const bootstrap = request.headers.get("X-EscapeBot-Bootstrap") === "1";
    const sessionId = request.headers.get("X-EscapeBot-Session-Id") ?? "";
    if (!CLIENT_ID_PATTERN.test(clientId) || (!bootstrap && !SESSION_ID_PATTERN.test(sessionId))) {
      return json({ error: "invalid_session_or_client_id" }, 400);
    }
    if (!bootstrap && this.snapshot.sessionId && this.snapshot.sessionId !== sessionId) {
      return json({ error: "session_routing_mismatch" }, 409);
    }
    if (!bootstrap && !this.snapshot.sessionId) {
      this.snapshot = { ...this.snapshot, sessionId, updatedAt: new Date().toISOString() };
      await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    }

    const pair = new WebSocketPair();
    const client = pair[0];
    const server = pair[1];
    const attachment: SocketAttachment = {
      clientId,
      connectedAt: new Date().toISOString(),
      role: bootstrap ? "bootstrap" : "session",
    };
    server.serializeAttachment(attachment);
    this.ctx.acceptWebSocket(server);
    server.send(
      protocolMessage("session.connected", {
        session_id: sessionId,
        client_id: clientId,
        revision: this.snapshot.revision,
        bootstrap,
      }),
    );
    if (bootstrap) await this.sendRuntimeSettings(server);

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(socket: WebSocket, rawMessage: string | ArrayBuffer): Promise<void> {
    const attachment = socket.deserializeAttachment() as SocketAttachment | null;
    if (!attachment) {
      socket.close(1011, "Missing connection metadata");
      return;
    }

    let message: ProtocolMessage;
    try {
      const rawText =
        typeof rawMessage === "string" ? rawMessage : new TextDecoder().decode(rawMessage);
      message = JSON.parse(rawText) as ProtocolMessage;
      if (!message || typeof message.type !== "string") throw new Error("invalid message");
    } catch {
      this.send(socket, "error", { message: "Neplatná JSON zpráva." });
      return;
    }

    if (attachment.role === "bootstrap") {
      await this.handleBootstrapMessage(socket, attachment, message);
      return;
    }

    switch (message.type) {
      case "leaderboard.get":
        this.send(socket, "leaderboard.update", { entries: [] });
        return;
      case "lobby.resume":
        await this.resumeLobby(socket, attachment, message.payload ?? {});
        return;
      case "lobby.start":
        await this.startLobby(socket, attachment);
        return;
      case "player.message":
      case "phase.hint":
      case "qr.detected":
      case "puzzle.submit":
      case "puzzle.hint":
      case "line_game.move":
      case "line_game.reset":
      case "karel.command":
      case "karel.reset":
      case "sokoban.command":
      case "sokoban.undo":
      case "sokoban.reset":
      case "archive.arrange":
      case "finale.activate":
      case "game.deadline_choice":
      case "team_game.player.restore":
      case "triad.place":
      case "triad.reset":
        await this.handleGameCommand(socket, attachment, message);
        return;
      case "spike.broadcast": {
        const text = String(message.payload?.text ?? "").trim();
        if (!text) {
          this.send(socket, "error", { message: "Prázdný broadcast." });
          return;
        }
        this.broadcast("spike.broadcast", { client_id: attachment.clientId, text });
        return;
      }
      case "spike.state.patch":
        await this.applyStatePatch(socket, message.payload ?? {});
        return;
      case "spike.deadline.schedule":
        await this.scheduleDeadline(socket, message.payload ?? {});
        return;
      default:
        if (message.operation_id) {
          await this.handleGameCommand(socket, attachment, message);
        } else {
          this.send(socket, "error", { message: `Neznámý typ zprávy: ${message.type}` });
        }
    }
  }

  private async handleBootstrapMessage(
    socket: WebSocket,
    attachment: SocketAttachment,
    message: ProtocolMessage,
  ): Promise<void> {
    if (message.type === "leaderboard.get") {
      this.send(socket, "leaderboard.update", { entries: [] });
      return;
    }
    if (!new Set(["lobby.solo", "lobby.create", "lobby.join"]).has(message.type)) {
      this.send(socket, "lobby.error", { message: "Nejprve založte tým nebo se k němu připojte." });
      return;
    }

    const payload = message.payload ?? {};
    const requestedClientId = cleanText(payload.client_id, 128);
    if (requestedClientId !== attachment.clientId) {
      this.send(socket, "lobby.error", { message: "Identifikátor zařízení neodpovídá spojení." });
      return;
    }

    try {
      await this.serializeDirectory(async () => {
        if (message.type === "lobby.join") {
          await this.routeLobbyJoin(socket, attachment.clientId, payload);
        } else {
          await this.routeLobbyCreation(
            socket,
            attachment.clientId,
            message.type === "lobby.solo" ? "solo" : "team",
            payload,
          );
        }
      });
    } catch (error) {
      this.send(socket, "lobby.error", {
        message: error instanceof Error ? error.message : "Týmovou relaci nelze otevřít.",
      });
    }
  }

  private async routeLobbyCreation(
    socket: WebSocket,
    clientId: string,
    mode: "solo" | "team",
    payload: Record<string, unknown>,
  ): Promise<void> {
    const name = cleanText(payload.name, 24);
    const teamName = cleanText(payload.team_name, 32);
    const lobbyType = cleanText(payload.lobby_type || "on_site_qr", 32);
    const scenarioId = cleanText(payload.scenario_id, 64);
    if (!name) throw new Error("Jméno hráče je povinné.");
    if (!teamName) throw new Error("Název týmu je povinný.");
    if (!new Set(["online_doom", "on_site_qr", "geo"]).has(lobbyType)) {
      throw new Error("Neznámý typ herní lobby.");
    }

    const games = await this.loadRuntimeGames();
    const game = games.find((candidate) => candidate.id === scenarioId);
    if (!game || !game.lobby_types.includes(lobbyType)) {
      throw new Error("Vybraná hra není pro tento typ lobby dostupná.");
    }

    const directory = (await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY)) ?? defaultDirectory();
    const teamKey = normalizedTeamKey(lobbyType, scenarioId, teamName);
    const creatorKey = `${clientId}\u0000${mode}\u0000${teamKey}`;
    const existingForCreator = directory.creatorKeys[creatorKey];
    if (existingForCreator) {
      const existingJoinCode = Object.entries(directory.joinCodes).find(
        ([, sessionId]) => sessionId === existingForCreator,
      )?.[0] ?? null;
      this.send(socket, "lobby.route", {
        session_id: existingForCreator,
        client_id: clientId,
        mode,
        join_code: existingJoinCode,
      });
      return;
    }
    if (directory.teamKeys[teamKey]) {
      throw new Error("Tým s tímto názvem už existuje. Zvolte jiný název.");
    }

    const sessionId = crypto.randomUUID().replaceAll("-", "");
    let joinCode: string | null = null;
    if (mode === "team") {
      do joinCode = randomJoinCode(); while (directory.joinCodes[joinCode]);
    }
    const initialized = await this.runtimeEnv.GAME_SESSIONS.getByName(sessionId).fetch(
      "https://internal/internal/lobby/initialize",
      {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          mode,
          creator_id: clientId,
          team_name: teamName,
          join_code: joinCode,
          lobby_type: lobbyType,
          scenario_id: scenarioId,
          player_name: name,
        }),
      },
    );
    const initializationResult = await initialized.json<{ error?: string }>();
    if (!initialized.ok) {
      throw new Error(initializationResult.error || "Cloudovou týmovou relaci se nepodařilo vytvořit.");
    }

    directory.teamKeys[teamKey] = sessionId;
    directory.creatorKeys[creatorKey] = sessionId;
    if (joinCode) directory.joinCodes[joinCode] = sessionId;
    await this.ctx.storage.put(DIRECTORY_KEY, directory);
    this.send(socket, "lobby.route", {
      session_id: sessionId,
      client_id: clientId,
      mode,
      join_code: joinCode,
    });
  }

  private async routeLobbyJoin(
    socket: WebSocket,
    clientId: string,
    payload: Record<string, unknown>,
  ): Promise<void> {
    const name = cleanText(payload.name, 24);
    const joinCode = cleanText(payload.join_code, 32).toUpperCase().replace("ESCAPEBOT://TEAM/", "");
    if (!name) throw new Error("Jméno hráče je povinné.");
    if (!JOIN_CODE_PATTERN.test(joinCode)) throw new Error("Připojovací kód není platný.");
    const directory = (await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY)) ?? defaultDirectory();
    const sessionId = directory.joinCodes[joinCode];
    if (!sessionId) throw new Error("Připojovací kód není platný nebo relace už neexistuje.");

    const joined = await this.runtimeEnv.GAME_SESSIONS.getByName(sessionId).fetch(
      "https://internal/internal/lobby/join",
      {
        method: "POST",
        body: JSON.stringify({ client_id: clientId, player_name: name }),
      },
    );
    const joinResult = await joined.json<{ error?: string }>();
    if (!joined.ok) {
      throw new Error(joinResult.error || "K týmu se nepodařilo připojit.");
    }
    this.send(socket, "lobby.route", {
      session_id: sessionId,
      client_id: clientId,
      mode: "team",
      join_code: joinCode,
    });
  }

  private async initializeLobby(payload: Record<string, unknown>): Promise<Response> {
    const sessionId = cleanText(payload.session_id, 128);
    const clientId = cleanText(payload.creator_id, 128);
    const name = cleanText(payload.player_name, 24);
    const teamName = cleanText(payload.team_name, 32);
    const mode = payload.mode === "solo" ? "solo" : "team";
    if (!SESSION_ID_PATTERN.test(sessionId) || !CLIENT_ID_PATTERN.test(clientId) || !name || !teamName) {
      return json({ error: "invalid_lobby" }, 400);
    }
    if (this.snapshot.lobby.creatorId) {
      const sameLobby =
        this.snapshot.sessionId === sessionId &&
        this.snapshot.lobby.creatorId === clientId &&
        this.snapshot.lobby.teamName === teamName;
      return sameLobby ? json({ status: "exists" }) : json({ error: "lobby_already_initialized" }, 409);
    }

    const now = new Date().toISOString();
    const started = mode === "solo";
    const adjustment = started ? teamSizeAdjustment(mode, 1) : 0;
    const scenario = started ? await this.loadScenario(cleanText(payload.scenario_id, 64)) : null;
    const startedScenario = scenario ? startScenario(scenario, adjustment, now) : null;
    const deadlineAt = started
      ? Date.parse(now) + boundedInteger(this.runtimeEnv.GAME_DURATION_MINUTES, 165, 15, 720) * 60_000
      : null;
    if (startedScenario && deadlineAt !== null) {
      startedScenario.state.flags.game_deadline_at = new Date(deadlineAt).toISOString();
    }
    const chatHistory = (startedScenario?.messages ?? [])
      .filter((message) => message.type === "bot.message")
      .map((message) => ({ role: "bot", ...message.payload }));
    this.snapshot = {
      ...defaultSnapshot(sessionId),
      revision: 1,
      lobby: {
        mode,
        creatorId: clientId,
        teamName,
        joinCode: payload.join_code ? cleanText(payload.join_code, 8) : null,
        started,
        lobbyType: cleanText(payload.lobby_type || "on_site_qr", 32),
        scenarioId: cleanText(payload.scenario_id, 64),
        players: { [clientId]: { id: clientId, name, joinedAt: now } },
        maxPlayers: 1,
        appliedScoreAdjustment: adjustment,
      },
      chatHistory,
      gameState: startedScenario?.state ?? {
        phase: "lobby",
        score: 1000,
        flags: {},
      },
      scenarioProgress: startedScenario && scenario
        ? buildScenarioProgress(scenario, startedScenario.state)
        : { completed: [], available: [] },
      deadlineAt,
      deadlineKind: started ? "game" : null,
      updatedAt: now,
    };
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    if (deadlineAt !== null) await this.ctx.storage.setAlarm(deadlineAt);
    return json({ status: "created", session_id: sessionId });
  }

  private async joinLobby(payload: Record<string, unknown>): Promise<Response> {
    const clientId = cleanText(payload.client_id, 128);
    const name = cleanText(payload.player_name, 24);
    if (!this.snapshot.lobby.creatorId) return json({ error: "Týmová relace neexistuje." }, 404);
    if (!CLIENT_ID_PATTERN.test(clientId) || !name) return json({ error: "Jméno hráče je povinné." }, 400);
    const previousAdjustment = this.snapshot.lobby.appliedScoreAdjustment;
    if (!this.snapshot.lobby.players[clientId]) {
      this.snapshot.lobby.players[clientId] = {
        id: clientId,
        name,
        joinedAt: new Date().toISOString(),
      };
    } else {
      this.snapshot.lobby.players[clientId].name = name;
    }
    this.snapshot.lobby.maxPlayers = Math.max(
      this.snapshot.lobby.maxPlayers,
      Object.keys(this.snapshot.lobby.players).length,
    );
    const desiredAdjustment = this.snapshot.lobby.started
      ? teamSizeAdjustment(this.snapshot.lobby.mode, this.snapshot.lobby.maxPlayers)
      : previousAdjustment;
    const scoreDelta = desiredAdjustment - previousAdjustment;
    this.snapshot.lobby.appliedScoreAdjustment = desiredAdjustment;
    this.snapshot.gameState.score += scoreDelta;
    if (this.snapshot.lobby.started) {
      const scenario = await this.loadScenario(this.snapshot.lobby.scenarioId);
      this.snapshot.gameState = presentGameState(
        scenario,
        this.snapshot.gameState,
        this.runtimeActor(clientId),
        new Date().toISOString(),
      );
      this.snapshot.scenarioProgress = buildScenarioProgress(scenario, this.snapshot.gameState);
    }
    this.snapshot.revision += 1;
    this.snapshot.updatedAt = new Date().toISOString();
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    this.broadcastLobbyState();
    if (scoreDelta) {
      this.broadcast("score.update", {
        score: this.snapshot.gameState.score,
        delta: scoreDelta,
        reason: "team_size",
      });
      await this.broadcastGameState();
    }
    return json({ status: "joined", session_id: this.snapshot.sessionId });
  }

  private async excludeGamePlayer(payload: Record<string, unknown>): Promise<Response> {
    if (!this.snapshot.lobby.creatorId) return json({ error: "session_not_found" }, 404);
    if (!this.snapshot.lobby.started) return json({ error: "game_not_started" }, 409);
    if (payload.action !== "exclude") return json({ error: "unsupported_admin_action" }, 400);
    const puzzleId = cleanText(payload.puzzle_id, 64);
    const playerId = cleanText(payload.player_id, 128);
    if (!puzzleId || !CLIENT_ID_PATTERN.test(playerId)) {
      return json({ error: "invalid_admin_game_player_request" }, 400);
    }
    try {
      const scenario = await this.loadScenario(this.snapshot.lobby.scenarioId);
      const now = new Date().toISOString();
      const result = applyAdminGamePlayerExclusion(
        scenario,
        this.snapshot.gameState,
        puzzleId,
        playerId,
        now,
        this.runtimeActor(this.snapshot.lobby.creatorId),
      );
      if (result.result.changed === false) {
        return json({ ...result.result, session_id: this.snapshot.sessionId, revision: this.snapshot.revision });
      }
      for (const message of result.messages) {
        if (message.type === "bot.message") {
          this.snapshot.chatHistory.push({ role: "bot", ...message.payload });
        }
      }
      this.snapshot.gameState = result.state;
      this.snapshot.scenarioProgress = buildScenarioProgress(scenario, result.state);
      this.snapshot.revision += 1;
      this.snapshot.updatedAt = now;
      await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);

      for (const message of result.messages) {
        if (message.type !== "admin.game_player") this.broadcastProtocol(message);
      }
      await this.broadcastGameState(scenario, undefined, now);
      this.broadcast("scenario.progress", this.snapshot.scenarioProgress);
      return json({ ...result.result, session_id: this.snapshot.sessionId, revision: this.snapshot.revision });
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Hráče se nepodařilo vyřadit." }, 400);
    }
  }

  private async resumeLobby(
    socket: WebSocket,
    attachment: SocketAttachment,
    payload: Record<string, unknown>,
  ): Promise<void> {
    if (!this.snapshot.lobby.creatorId) {
      await this.sendAuthoritativeSnapshot(socket);
      return;
    }
    const requestedSession = cleanText(payload.session_id || this.snapshot.sessionId, 128);
    if (
      requestedSession !== this.snapshot.sessionId ||
      !this.snapshot.lobby.players[attachment.clientId]
    ) {
      this.send(socket, "lobby.error", { message: "Uloženou týmovou relaci se nepodařilo obnovit." });
      return;
    }
    this.broadcastLobbyState();
    if (this.snapshot.lobby.started) await this.sendAuthoritativeSnapshot(socket, false);
  }

  private async startLobby(socket: WebSocket, attachment: SocketAttachment): Promise<void> {
    await this.serializeState(() => this.startLobbyMutation(socket, attachment));
  }

  private async startLobbyMutation(socket: WebSocket, attachment: SocketAttachment): Promise<void> {
    if (attachment.clientId !== this.snapshot.lobby.creatorId) {
      this.send(socket, "lobby.error", { message: "Hru může spustit pouze zakladatel týmu." });
      return;
    }
    if (this.snapshot.lobby.started) {
      await this.sendAuthoritativeSnapshot(socket);
      return;
    }
    const now = new Date().toISOString();
    const adjustment = teamSizeAdjustment(this.snapshot.lobby.mode, this.snapshot.lobby.maxPlayers);
    const scenario = await this.loadScenario(this.snapshot.lobby.scenarioId);
    const startedScenario = startScenario(scenario, adjustment, now, this.runtimeActor(attachment.clientId));
    const deadlineAt = Date.parse(now) +
      boundedInteger(this.runtimeEnv.GAME_DURATION_MINUTES, 165, 15, 720) * 60_000;
    startedScenario.state.flags.game_deadline_at = new Date(deadlineAt).toISOString();
    const initialMessages = startedScenario.messages
      .filter((message) => message.type === "bot.message")
      .map((message) => ({ role: "bot", ...message.payload }));
    this.snapshot = {
      ...this.snapshot,
      revision: this.snapshot.revision + 1,
      lobby: { ...this.snapshot.lobby, started: true, appliedScoreAdjustment: adjustment },
      chatHistory: initialMessages,
      gameState: startedScenario.state,
      scenarioProgress: buildScenarioProgress(scenario, startedScenario.state),
      deadlineAt,
      deadlineKind: "game",
      updatedAt: now,
    };
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    await this.ctx.storage.setAlarm(deadlineAt);
    this.broadcastLobbyState();
    for (const candidate of this.ctx.getWebSockets()) await this.sendAuthoritativeSnapshot(candidate, false, scenario);
  }

  private async serializeDirectory<T>(operation: () => Promise<T>): Promise<T> {
    const previous = this.directoryQueue;
    let release: () => void = () => {};
    this.directoryQueue = new Promise<void>((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      return await operation();
    } finally {
      release();
    }
  }

  private async serializeState<T>(operation: () => Promise<T>): Promise<T> {
    const previous = this.stateQueue;
    let release: () => void = () => {};
    this.stateQueue = new Promise<void>((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      return await operation();
    } finally {
      release();
    }
  }

  private async handleGameCommand(
    socket: WebSocket,
    attachment: SocketAttachment,
    message: ProtocolMessage,
  ): Promise<void> {
    await this.serializeState(async () => {
      if (!this.snapshot.lobby.started || !this.snapshot.lobby.players[attachment.clientId]) {
        this.send(socket, "command.rejected", { reason: "Nejprve spusťte týmovou hru." }, message.request_id, message.operation_id);
        return;
      }
      const operationId = String(message.operation_id || "");
      if (!operationId || operationId.length > 128) {
        this.send(socket, "command.rejected", { reason: "Hernímu příkazu chybí platné operation_id." }, message.request_id, operationId || undefined);
        return;
      }
      const receiptKey = `${attachment.clientId}:${operationId}`;
      const receipt = this.snapshot.operationReceipts[receiptKey]
        ?? this.snapshot.operationReceipts[operationId];
      if (receipt) {
        for (const response of receipt) this.sendProtocol(socket, response);
        return;
      }

      const scenario = await this.loadScenario(this.snapshot.lobby.scenarioId);
      const payload = message.payload ?? {};
      const now = new Date().toISOString();
      const result = applyScenarioCommand(
        scenario,
        this.snapshot.gameState,
        message.type,
        payload,
        now,
        this.runtimeActor(attachment.clientId),
      );
      const senderName = this.snapshot.lobby.players[attachment.clientId]?.name || "Hráč";
      let teamMessage: ProtocolMessage | null = null;
      if (message.type === "player.message") {
        const text = cleanText(payload.text, 1000);
        const channel = cleanText(payload.channel || "general", 32);
        if (text) {
          this.snapshot.chatHistory.push({
            role: "player",
            channel,
            text,
            sender: senderName,
          });
          teamMessage = {
            type: "team.player_message",
            payload: { client_id: attachment.clientId, channel, text, sender: senderName },
          };
        }
      }
      for (const response of result.messages) {
        if (response.type === "bot.message") {
          this.snapshot.chatHistory.push({ role: "bot", ...response.payload });
        }
      }

      this.snapshot.gameState = result.state;
      this.snapshot.scenarioProgress = buildScenarioProgress(scenario, result.state);
      this.snapshot.revision += 1;
      this.snapshot.updatedAt = now;
      const responses: ProtocolMessage[] = [
        ...result.messages.map((response) => ({
          ...response,
          ...(message.request_id ? { request_id: message.request_id } : {}),
          operation_id: operationId,
        })),
        {
          type: "game.state",
          payload: this.gameStatePayload(
            presentGameState(scenario, this.snapshot.gameState, this.runtimeActor(attachment.clientId), now),
          ),
          operation_id: operationId,
        },
        {
          type: "scenario.progress",
          payload: this.snapshot.scenarioProgress,
          operation_id: operationId,
        },
      ];
      this.snapshot.operationReceipts[receiptKey] = responses;
      while (Object.keys(this.snapshot.operationReceipts).length > 500) {
        delete this.snapshot.operationReceipts[Object.keys(this.snapshot.operationReceipts)[0]];
      }
      await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);

      if (teamMessage) this.broadcastProtocol(teamMessage, socket);
      for (const response of responses) {
        this.sendProtocol(socket, response);
        if (!new Set(["line_game.result", "game.state"]).has(response.type)) {
          this.broadcastProtocol({ type: response.type, payload: response.payload }, socket);
        }
      }
      await this.broadcastGameState(scenario, socket, now);
    });
  }

  private async loadScenario(scenarioId: string): Promise<ScenarioDocument> {
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(scenarioId)) throw new Error("Neplatné ID scénáře.");
    const response = await this.runtimeEnv.ASSETS.fetch(
      `https://assets.local/scenarios/${encodeURIComponent(scenarioId)}.json`,
    );
    if (!response.ok) throw new Error("Cloudový scénář není dostupný.");
    return response.json<ScenarioDocument>();
  }

  private async loadRuntimeGames(): Promise<RuntimeGame[]> {
    const response = await this.runtimeEnv.ASSETS.fetch("https://assets.local/runtime-catalog.json");
    if (!response.ok) throw new Error("Cloudový katalog her není dostupný.");
    return response.json<RuntimeGame[]>();
  }

  private async sendRuntimeSettings(socket: WebSocket): Promise<void> {
    try {
      const games = await this.loadRuntimeGames();
      this.send(socket, "runtime.settings", {
        online_mode: false,
        gameplay_enabled: true,
        display_leaderboard: true,
        leaderboard_finalized: false,
        games,
        configurable_games: games,
        start_queue: [],
        checkpoints: [],
        availability: null,
        availability_by_lobby_type: {},
        mapillary: { enabled: false, access_token: "" },
        event: {},
      });
    } catch (error) {
      this.send(socket, "lobby.error", {
        message: error instanceof Error ? error.message : "Cloudový katalog her není dostupný.",
      });
    }
  }

  webSocketClose(socket: WebSocket, code: number, reason: string): void {
    socket.close(code, reason);
  }

  async alarm(): Promise<void> {
    if (this.snapshot.deadlineAt === null) return;
    if (this.snapshot.deadlineKind === "game") {
      const flags = { ...this.snapshot.gameState.flags };
      if (flags.game_completed || flags.deadline_reached_at || flags.out_of_competition) {
        this.snapshot = { ...this.snapshot, deadlineAt: null, deadlineKind: null };
        await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
        return;
      }
      const now = new Date().toISOString();
      const penalty = boundedInteger(this.runtimeEnv.DEADLINE_PENALTY, 100, 0, 1000);
      const scoreBefore = Number(this.snapshot.gameState.score || 0);
      const score = scoreBefore - penalty;
      const adjustment = {
        delta: -penalty,
        amount: penalty,
        reason: "Nedokončení hry v časovém limitu",
        at: now,
        score_before: scoreBefore,
        score_after: score,
        automatic: true,
      };
      flags.deadline_reached_at = now;
      flags.deadline_choice_pending = true;
      flags.administratively_ended = true;
      flags.administratively_ended_at = now;
      flags.administratively_ended_reason = "deadline";
      flags.competition_score = score;
      flags.competition_score_frozen_at = now;
      if (penalty > 0) {
        flags.deadline_penalty_applied = true;
        flags.admin_score_adjustments = [
          ...(Array.isArray(flags.admin_score_adjustments) ? flags.admin_score_adjustments : []),
          adjustment,
        ];
        flags.admin_penalties = [
          ...(Array.isArray(flags.admin_penalties) ? flags.admin_penalties : []),
          adjustment,
        ];
      }
      const scenario = await this.loadScenario(this.snapshot.lobby.scenarioId);
      const gameState = { ...this.snapshot.gameState, score, flags };
      this.snapshot = {
        ...this.snapshot,
        revision: this.snapshot.revision + 1,
        deadlineAt: null,
        deadlineKind: null,
        gameState,
        scenarioProgress: buildScenarioProgress(scenario, gameState),
        updatedAt: now,
      };
      await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
      if (penalty > 0) {
        this.broadcast("score.update", {
          score,
          delta: -penalty,
          bonus: 0,
          penalty,
          reason: "deadline_penalty",
          description: adjustment.reason,
        });
      }
      const suffix = penalty ? ` Byl odečten postih ${penalty} bodů.` : "";
      this.broadcast("operations.stopped", {
        reason: "deadline",
        penalty,
        message: `Časový limit hry vypršel.${suffix} Můžete hru ukončit, nebo dohrát mimo soutěž.`,
      });
      this.broadcast("game.deadline", {
        session_id: this.snapshot.sessionId,
        revision: this.snapshot.revision,
      });
      await this.broadcastGameState(scenario);
      this.broadcast("scenario.progress", this.snapshot.scenarioProgress);
      return;
    }
    this.snapshot = {
      ...this.snapshot,
      revision: this.snapshot.revision + 1,
      deadlineAt: null,
      deadlineKind: null,
      gameState: {
        ...this.snapshot.gameState,
        flags: { ...this.snapshot.gameState.flags, deadline_reached: true },
      },
      updatedAt: new Date().toISOString(),
    };
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    this.broadcast("game.deadline", {
      session_id: this.snapshot.sessionId,
      revision: this.snapshot.revision,
    });
    await this.broadcastGameState();
  }

  private async applyStatePatch(
    socket: WebSocket,
    payload: Record<string, unknown>,
  ): Promise<void> {
    const phase = payload.phase;
    const score = payload.score;
    if (phase !== undefined && typeof phase !== "string") {
      this.send(socket, "error", { message: "Fáze musí být text." });
      return;
    }
    if (score !== undefined && (typeof score !== "number" || !Number.isFinite(score))) {
      this.send(socket, "error", { message: "Skóre musí být konečné číslo." });
      return;
    }
    this.snapshot = {
      ...this.snapshot,
      revision: this.snapshot.revision + 1,
      gameState: {
        ...this.snapshot.gameState,
        ...(phase === undefined ? {} : { phase }),
        ...(score === undefined ? {} : { score }),
      },
      updatedAt: new Date().toISOString(),
    };
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    await this.broadcastGameState();
  }

  private async scheduleDeadline(
    socket: WebSocket,
    payload: Record<string, unknown>,
  ): Promise<void> {
    const deadlineAt = payload.deadline_at;
    if (typeof deadlineAt !== "number" || !Number.isFinite(deadlineAt)) {
      this.send(socket, "error", { message: "deadline_at musí být čas v milisekundách." });
      return;
    }
    this.snapshot = {
      ...this.snapshot,
      deadlineAt,
      deadlineKind: "spike",
      updatedAt: new Date().toISOString(),
    };
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    await this.ctx.storage.setAlarm(deadlineAt);
    this.send(socket, "spike.deadline.scheduled", { deadline_at: deadlineAt });
  }

  private connectedClientIds(): Set<string> {
    return new Set(
      this.ctx
        .getWebSockets()
        .map((socket) => socket.deserializeAttachment() as SocketAttachment | null)
        .filter((attachment) => attachment?.role === "session")
        .map((attachment) => attachment?.clientId ?? ""),
    );
  }

  private lobbyPayload(clientId: string): Record<string, unknown> {
    const connected = this.connectedClientIds();
    const players = Object.values(this.snapshot.lobby.players);
    return {
      session_id: this.snapshot.sessionId,
      revision: this.snapshot.revision,
      mode: this.snapshot.lobby.mode,
      lobby_type: this.snapshot.lobby.lobbyType,
      scenario_id: this.snapshot.lobby.scenarioId,
      team_name: this.snapshot.lobby.teamName,
      join_code: this.snapshot.lobby.joinCode,
      started: this.snapshot.lobby.started,
      is_creator: clientId === this.snapshot.lobby.creatorId,
      player_count: players.length,
      registered_players: players.length,
      online_count: players.filter((player) => connected.has(player.id)).length,
      max_players: this.snapshot.lobby.maxPlayers,
      score_adjustment: this.snapshot.lobby.appliedScoreAdjustment,
      players: players.map((player) => ({
        id: player.id,
        name: player.name,
        joined_at: player.joinedAt,
        connected: connected.has(player.id),
      })),
    };
  }

  private broadcastLobbyState(): void {
    for (const socket of this.ctx.getWebSockets()) {
      const attachment = socket.deserializeAttachment() as SocketAttachment | null;
      if (attachment?.role === "session") {
        this.send(socket, "lobby.state", this.lobbyPayload(attachment.clientId));
      }
    }
  }

  private runtimeActor(clientId: string): RuntimeActor {
    const players = this.snapshot.lobby.players;
    return {
      clientId,
      participantIds: Object.keys(players),
      participantNames: Object.fromEntries(
        Object.values(players).map((player) => [player.id, player.name]),
      ),
      teamMode: this.snapshot.lobby.mode,
    };
  }

  private async sendAuthoritativeSnapshot(
    socket: WebSocket,
    includeLobby = true,
    scenarioValue?: ScenarioDocument,
  ): Promise<void> {
    const attachment = socket.deserializeAttachment() as SocketAttachment | null;
    if (includeLobby) this.send(socket, "lobby.state", this.lobbyPayload(attachment?.clientId ?? ""));
    this.send(socket, "chat.history", { messages: this.snapshot.chatHistory });
    let gameState = this.snapshot.gameState;
    if (this.snapshot.lobby.started && attachment?.role === "session") {
      const scenario = scenarioValue ?? await this.loadScenario(this.snapshot.lobby.scenarioId);
      gameState = presentGameState(
        scenario,
        this.snapshot.gameState,
        this.runtimeActor(attachment.clientId),
        new Date().toISOString(),
      );
    }
    this.send(socket, "game.state", this.gameStatePayload(gameState));
    this.send(socket, "scenario.progress", {
      scenario_id: this.snapshot.lobby.scenarioId,
      phase: this.snapshot.gameState.phase,
      score: this.snapshot.gameState.score,
      inventory: [],
      nodes: [],
      ...this.snapshot.scenarioProgress,
    });
  }

  private gameStatePayload(state = this.snapshot.gameState): Record<string, unknown> {
    const {
      interactive_games: _privateLineGames,
      karel_games: _privateKarelGames,
      sokoban_games: _privateSokobanGames,
      archive_games: _privateArchiveGames,
      triad_games: _privateTriadGames,
      ...publicState
    } = state;
    return {
      session_id: this.snapshot.sessionId,
      revision: this.snapshot.revision,
      ...publicState,
    };
  }

  private async broadcastGameState(
    scenarioValue?: ScenarioDocument,
    exclude?: WebSocket,
    now = new Date().toISOString(),
  ): Promise<void> {
    const scenario = this.snapshot.lobby.started
      ? scenarioValue ?? await this.loadScenario(this.snapshot.lobby.scenarioId)
      : null;
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === exclude) continue;
      const attachment = socket.deserializeAttachment() as SocketAttachment | null;
      if (attachment?.role !== "session") continue;
      const state = scenario
        ? presentGameState(scenario, this.snapshot.gameState, this.runtimeActor(attachment.clientId), now)
        : this.snapshot.gameState;
      this.send(socket, "game.state", this.gameStatePayload(state));
    }
  }

  private send(
    socket: WebSocket,
    type: string,
    payload: Record<string, unknown>,
    requestId?: string,
    operationId?: string,
  ): void {
    socket.send(protocolMessage(type, payload, requestId, operationId));
  }

  private sendProtocol(socket: WebSocket, message: ProtocolMessage): void {
    this.send(
      socket,
      message.type,
      message.payload ?? {},
      message.request_id,
      message.operation_id,
    );
  }

  private broadcastProtocol(message: ProtocolMessage, exclude?: WebSocket): void {
    const encoded = protocolMessage(
      message.type,
      message.payload ?? {},
      message.request_id,
      message.operation_id,
    );
    for (const socket of this.ctx.getWebSockets()) {
      if (socket === exclude) continue;
      try {
        socket.send(encoded);
      } catch {
        socket.close(1011, "Broadcast failed");
      }
    }
  }

  private broadcast(type: string, payload: Record<string, unknown>): void {
    this.broadcastProtocol({ type, payload });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/api/health") {
      return json({ status: "ok", runtime: "cloudflare", environment: env.APP_ENV });
    }
    if (url.pathname === "/api/admin/game-player" && request.method === "POST") {
      const unauthorized = await authorizeAdmin(request, env);
      if (unauthorized) return unauthorized;
      let payload: Record<string, unknown>;
      try {
        payload = await request.json<Record<string, unknown>>();
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      const sessionId = cleanText(payload.session_id, 128);
      if (!SESSION_ID_PATTERN.test(sessionId)) return json({ error: "invalid_session_id" }, 400);
      const forwarded = new Request("https://internal/internal/admin/game-player", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-EscapeBot-Internal-Admin": "1",
        },
        body: JSON.stringify(payload),
      });
      return env.GAME_SESSIONS.getByName(sessionId).fetch(forwarded);
    }
    if (url.pathname.startsWith("/api/")) return json({ error: "not_found" }, 404);
    if (url.pathname !== "/ws") return env.ASSETS.fetch(request);
    if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket") {
      return json({ error: "websocket_upgrade_required" }, 426);
    }

    const sessionId = url.searchParams.get("session_id") ?? "";
    const clientId = url.searchParams.get("client_id") ?? "";
    if (!CLIENT_ID_PATTERN.test(clientId) || (sessionId && !SESSION_ID_PATTERN.test(sessionId))) {
      return json({ error: "invalid_session_or_client_id" }, 400);
    }

    const forwarded = new Request(request);
    if (sessionId) {
      forwarded.headers.set("X-EscapeBot-Session-Id", sessionId);
      return env.GAME_SESSIONS.getByName(sessionId).fetch(forwarded);
    }
    forwarded.headers.set("X-EscapeBot-Bootstrap", "1");
    return env.GAME_SESSIONS.getByName(DIRECTORY_OBJECT_NAME).fetch(forwarded);
  },
} satisfies ExportedHandler<Env>;
