import { DurableObject } from "cloudflare:workers";
export { EventCoordinator } from "./event-coordinator";
import { EVENT_ID_PATTERN, type EventCoordinator } from "./event-coordinator";
import {
  applyAdminGamePlayerExclusion,
  applyScenarioCommand,
  buildScenarioProgress,
  presentGameState,
  startScenario,
  transferPlayerIdentity,
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
  EVENTS: DurableObjectNamespace<EventCoordinator>;
}

interface SocketAttachment {
  clientId: string;
  connectedAt: string;
  role: "bootstrap" | "session" | "terminal_waiting" | "terminal";
  terminalId?: string;
  terminalLabel?: string;
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
  recoveredAt?: string;
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
  schemaVersion: 4;
  sessionId: string;
  revision: number;
  lobby: LobbySnapshot;
  chatHistory: Array<Record<string, unknown>>;
  gameState: GameStateDocument;
  scenarioProgress: Record<string, unknown>;
  operationReceipts: Record<string, ProtocolMessage[]>;
  identityRecoveryReceipts: Record<string, Record<string, unknown>>;
  deadlineAt: number | null;
  deadlineKind: "game" | "spike" | null;
  terminalReleaseAt: number | null;
  updatedAt: string;
}

interface RecoveryTokenRecord {
  sessionId: string;
  playerId: string;
  expiresAt: number;
}

interface TerminalDeviceRecord {
  id: string;
  label: string;
  status: "free" | "routing" | "attached";
  puzzleId: string;
  sessionId: string;
  controllerId: string;
  online: boolean;
  updatedAt: string;
}

interface TerminalPairingRecord {
  terminalId: string;
  expiresAt: number;
}

interface TerminalRouteRecord {
  terminalId: string;
  sessionId: string;
  controllerId: string;
  puzzleId: string;
  expiresAt: number;
}

interface DirectorySnapshot {
  schemaVersion: 3;
  joinCodes: Record<string, string>;
  teamKeys: Record<string, string>;
  creatorKeys: Record<string, string>;
  recoveryTokens: Record<string, RecoveryTokenRecord>;
  terminalDevices: Record<string, TerminalDeviceRecord>;
  terminalPairings: Record<string, TerminalPairingRecord>;
  terminalRoutes: Record<string, TerminalRouteRecord>;
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
const TERMINAL_CODE_PATTERN = /^[A-F0-9]{16}$/;

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
    schemaVersion: 4,
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
    identityRecoveryReceipts: {},
    deadlineAt: null,
    deadlineKind: null,
    terminalReleaseAt: null,
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
    schemaVersion: 4,
    lobby: { ...fallback.lobby, ...stored.lobby },
    gameState: { ...fallback.gameState, ...stored.gameState },
    scenarioProgress: { ...fallback.scenarioProgress, ...stored.scenarioProgress },
  };
}

function defaultDirectory(): DirectorySnapshot {
  return {
    schemaVersion: 3,
    joinCodes: {},
    teamKeys: {},
    creatorKeys: {},
    recoveryTokens: {},
    terminalDevices: {},
    terminalPairings: {},
    terminalRoutes: {},
  };
}

function normalizeDirectory(stored: Partial<DirectorySnapshot> | undefined): DirectorySnapshot {
  const fallback = defaultDirectory();
  return stored ? { ...fallback, ...stored, schemaVersion: 3 } : fallback;
}

function cleanText(value: unknown, maximum: number): string {
  return String(value ?? "").trim().replace(/\s+/g, " ").slice(0, maximum);
}

function objectRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, any>
    : {};
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

async function secretDigest(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function randomRecoveryToken(): string {
  return [...crypto.getRandomValues(new Uint8Array(8))]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

function terminalPuzzleAvailable(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  puzzleId: string,
): boolean {
  const flags = objectRecord(state.flags);
  if (flags.game_completed || flags.administratively_ended) return false;
  const puzzle = objectRecord(objectRecord(scenario.puzzles)[puzzleId]);
  const terminal = objectRecord(puzzle.terminal);
  const checkpointId = String(puzzle.checkpoint_id || "");
  const checkpoint = objectRecord(objectRecord(scenario.checkpoints)[checkpointId]);
  const checkpointState = objectRecord(objectRecord(state.checkpoint_states)[checkpointId]);
  if (!checkpointId || !Object.keys(checkpoint).length || String(terminal.mode || "phones") === "phones") return false;
  if (checkpointState.status === "solved") return false;
  if (checkpointState.status === "found") return true;
  if (checkpoint.requires_phase && String(state.phase || "") !== String(checkpoint.requires_phase)) return false;
  return (Array.isArray(checkpoint.requires) ? checkpoint.requires : []).every(
    (required) => objectRecord(objectRecord(state.checkpoint_states)[String(required)]).status === "solved",
  );
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
    if (url.pathname === "/internal/admin/overview" && request.method === "GET") {
      if (request.headers.get("X-EscapeBot-Internal-Admin") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      return this.adminOverview();
    }
    if (url.pathname === "/internal/admin/snapshot" && request.method === "GET") {
      if (request.headers.get("X-EscapeBot-Internal-Admin") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      return this.adminSessionSnapshot();
    }
    if (url.pathname === "/internal/admin/player-recovery" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Admin") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeDirectory(() => this.createPlayerRecovery(payload));
    }
    if (url.pathname === "/internal/admin/player-recovery/validate" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Admin") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.validatePlayerRecovery(payload);
    }
    if (url.pathname === "/internal/admin/terminal-reserve" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Admin") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeDirectory(() => this.reserveTerminal(payload));
    }
    if (url.pathname === "/internal/terminal/claim" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Terminal") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeDirectory(() => this.claimTerminal(payload));
    }
    if (url.pathname === "/internal/terminal/consume-route" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Terminal") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeDirectory(() => this.consumeTerminalRoute(payload));
    }
    if (url.pathname === "/internal/terminal/dispatch-route" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Terminal") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeDirectory(() => this.dispatchTerminalRoute(payload));
    }
    if (url.pathname === "/internal/terminal/released" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Terminal") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeDirectory(() => this.markTerminalReleased(payload));
    }
    if (url.pathname === "/internal/terminal/release" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Terminal") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      await this.serializeState(() => this.releaseTerminalById(
        cleanText(payload.terminal_id, 128),
        "Terminál byl znovu zaregistrován.",
        false,
      ));
      return json({ success: true });
    }
    if (url.pathname === "/internal/terminal/available" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Terminal") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      if (!this.snapshot.lobby.started || objectRecord(this.snapshot.gameState.flags).game_completed) {
        return json({ available: false });
      }
      const scenario = await this.loadScenario(this.snapshot.lobby.scenarioId);
      return json({ available: terminalPuzzleAvailable(scenario, this.snapshot.gameState, cleanText(payload.puzzle_id, 128)) });
    }
    if (url.pathname === "/internal/lobby/recover" && request.method === "POST") {
      if (request.headers.get("X-EscapeBot-Internal-Recovery") !== "1") {
        return json({ error: "not_found" }, 404);
      }
      const payload = await request.json<Record<string, unknown>>();
      return this.serializeState(() => this.recoverLobbyPlayer(payload));
    }
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

    let clientId = url.searchParams.get("client_id") ?? "";
    const bootstrap = request.headers.get("X-EscapeBot-Bootstrap") === "1";
    const sessionId = request.headers.get("X-EscapeBot-Session-Id") ?? "";
    const terminalId = cleanText(url.searchParams.get("terminal_id"), 128);
    const terminalToken = cleanText(url.searchParams.get("terminal_token"), 64).toUpperCase();
    let terminalRoute: Record<string, unknown> | null = null;
    if (!bootstrap && terminalId && terminalToken) {
      const response = await this.runtimeEnv.GAME_SESSIONS.getByName(DIRECTORY_OBJECT_NAME).fetch(
        "https://internal/internal/terminal/consume-route",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Terminal": "1" },
          body: JSON.stringify({ terminal_id: terminalId, session_id: sessionId, token: terminalToken }),
        },
      );
      terminalRoute = await response.json<Record<string, unknown>>();
      if (!response.ok) return json(terminalRoute, response.status);
      clientId = String(terminalRoute.controller_id || "");
    }
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
      role: terminalRoute ? "terminal" : bootstrap ? "bootstrap" : "session",
      ...(terminalRoute ? {
        terminalId,
        terminalLabel: String(terminalRoute.terminal_label || terminalId),
      } : {}),
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
    if (terminalRoute) {
      await this.attachTerminal(server, attachment, String(terminalRoute.puzzle_id || ""));
    }

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

    if (attachment.role === "terminal_waiting") {
      if (message.type === "terminal.register") {
        await this.registerTerminal(socket, attachment, message.payload ?? {});
      } else if (message.type === "terminal.status") {
        await this.sendTerminalStatus(socket, attachment);
      }
      return;
    }

    if (message.type === "qr.detected" && String(message.payload?.value || "").toLowerCase().startsWith("escapebot://terminal/")) {
      if (attachment.role !== "session") {
        this.send(socket, "terminal.attach_result", { success: false, reason: "Terminál může odemknout pouze hráč." });
        return;
      }
      await this.handleTerminalClaim(socket, attachment, message.payload ?? {});
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
    if (message.type === "terminal.register") {
      await this.serializeDirectory(() => this.registerTerminal(socket, attachment, message.payload ?? {}));
      return;
    }
    if (message.type === "terminal.status" && attachment.role === "terminal_waiting") {
      await this.sendTerminalStatus(socket, attachment);
      return;
    }
    if (message.type === "leaderboard.get") {
      this.send(socket, "leaderboard.update", { entries: [] });
      return;
    }
    if (!new Set(["lobby.solo", "lobby.create", "lobby.join", "lobby.recover"]).has(message.type)) {
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
        if (message.type === "lobby.recover") {
          await this.routeLobbyRecovery(socket, attachment.clientId, payload);
        } else if (message.type === "lobby.join") {
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

    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
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
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
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

  private async routeLobbyRecovery(
    socket: WebSocket,
    clientId: string,
    payload: Record<string, unknown>,
  ): Promise<void> {
    const token = cleanText(payload.recovery_token, 64)
      .toUpperCase()
      .replace("ESCAPEBOT://RECOVER/", "");
    if (!/^[A-F0-9]{16}$/.test(token)) {
      throw new Error("Návratový kód není platný, už byl použit nebo vypršel.");
    }
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const now = Date.now();
    for (const [digest, recovery] of Object.entries(directory.recoveryTokens)) {
      if (recovery.expiresAt <= now) delete directory.recoveryTokens[digest];
    }
    const digest = await secretDigest(token);
    const recovery = directory.recoveryTokens[digest];
    if (!recovery || recovery.expiresAt <= now) {
      await this.ctx.storage.put(DIRECTORY_KEY, directory);
      throw new Error("Návratový kód není platný, už byl použit nebo vypršel.");
    }
    const recovered = await this.runtimeEnv.GAME_SESSIONS.getByName(recovery.sessionId).fetch(
      "https://internal/internal/lobby/recover",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-EscapeBot-Internal-Recovery": "1",
        },
        body: JSON.stringify({
          old_client_id: recovery.playerId,
          new_client_id: clientId,
          recovery_id: digest,
        }),
      },
    );
    const result = await recovered.json<Record<string, any>>();
    if (!recovered.ok) throw new Error(String(result.error || "Identitu hráče se nepodařilo obnovit."));
    delete directory.recoveryTokens[digest];
    if (result.creator_transferred) {
      for (const [creatorKey, sessionId] of Object.entries(directory.creatorKeys)) {
        if (sessionId !== recovery.sessionId || !creatorKey.startsWith(`${recovery.playerId}\u0000`)) continue;
        const replacement = `${clientId}${creatorKey.slice(recovery.playerId.length)}`;
        directory.creatorKeys[replacement] = sessionId;
        delete directory.creatorKeys[creatorKey];
      }
    }
    await this.ctx.storage.put(DIRECTORY_KEY, directory);
    this.send(socket, "lobby.recovered", {
      player_name: String(result.player_name || ""),
      team_name: String(result.team_name || ""),
    });
    this.send(socket, "lobby.route", {
      session_id: recovery.sessionId,
      client_id: clientId,
      mode: String(result.mode || "team"),
      join_code: result.join_code ?? null,
    });
  }

  private async registerTerminal(
    socket: WebSocket,
    attachment: SocketAttachment,
    payload: Record<string, unknown>,
  ): Promise<void> {
    const terminalId = cleanText(payload.terminal_id, 128);
    const terminalLabel = cleanText(payload.terminal_label || `Terminál ${terminalId.slice(-4)}`, 64);
    if (!CLIENT_ID_PATTERN.test(terminalId)) {
      this.send(socket, "terminal.status", { reserved: false, reason: "Neplatné ID terminálu." });
      return;
    }
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const previous = directory.terminalDevices[terminalId];
    if (previous?.sessionId && SESSION_ID_PATTERN.test(previous.sessionId)) {
      await this.runtimeEnv.GAME_SESSIONS.getByName(previous.sessionId).fetch(
        "https://internal/internal/terminal/release",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Terminal": "1" },
          body: JSON.stringify({ terminal_id: terminalId }),
        },
      );
    }
    for (const candidate of this.ctx.getWebSockets()) {
      if (candidate === socket) continue;
      const existing = candidate.deserializeAttachment() as SocketAttachment | null;
      if (existing?.terminalId === terminalId) candidate.close(4003, "Terminal registered elsewhere");
    }
    for (const [digest, pairing] of Object.entries(directory.terminalPairings)) {
      if (pairing.terminalId === terminalId || pairing.expiresAt <= Date.now()) delete directory.terminalPairings[digest];
    }
    for (const [digest, route] of Object.entries(directory.terminalRoutes)) {
      if (route.terminalId === terminalId || route.expiresAt <= Date.now()) delete directory.terminalRoutes[digest];
    }
    const code = randomRecoveryToken();
    const expiresAt = Date.now() + 10 * 60_000;
    directory.terminalPairings[await secretDigest(code)] = { terminalId, expiresAt };
    directory.terminalDevices[terminalId] = {
      id: terminalId,
      label: terminalLabel,
      status: "free",
      puzzleId: previous?.puzzleId || "",
      sessionId: "",
      controllerId: "",
      online: true,
      updatedAt: new Date().toISOString(),
    };
    await this.ctx.storage.put(DIRECTORY_KEY, directory);
    const nextAttachment: SocketAttachment = {
      ...attachment,
      role: "terminal_waiting",
      terminalId,
      terminalLabel,
    };
    socket.serializeAttachment(nextAttachment);
    const status = await this.terminalStatus(directory, terminalId);
    this.send(socket, "terminal.ready", {
      code,
      value: `escapebot://terminal/${code}`,
      expires_in: 600,
      ...status,
    });
  }

  private async sendTerminalStatus(socket: WebSocket, attachment: SocketAttachment): Promise<void> {
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    this.send(socket, "terminal.status", await this.terminalStatus(directory, attachment.terminalId || ""));
  }

  private async terminalStatus(directory: DirectorySnapshot, terminalId: string): Promise<Record<string, unknown>> {
    const device = directory.terminalDevices[terminalId];
    const puzzleId = device?.puzzleId || "";
    let puzzleTitle = puzzleId;
    let eligibleTeamCount = 0;
    if (puzzleId) {
      const games = await this.loadRuntimeGames();
      for (const game of games) {
        const scenario = await this.loadScenario(game.id);
        const puzzle = objectRecord(objectRecord(scenario.puzzles)[puzzleId]);
        if (puzzle.title) puzzleTitle = String(puzzle.title);
      }
      const sessionIds = [...new Set([...Object.values(directory.teamKeys), ...Object.values(directory.creatorKeys)])];
      const availability = await Promise.all(sessionIds.filter((id) => SESSION_ID_PATTERN.test(id)).map(async (sessionId) => {
        try {
          const response = await this.runtimeEnv.GAME_SESSIONS.getByName(sessionId).fetch(
            "https://internal/internal/terminal/available",
            {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Terminal": "1" },
              body: JSON.stringify({ puzzle_id: puzzleId }),
            },
          );
          return response.ok && Boolean((await response.json<Record<string, unknown>>()).available);
        } catch {
          return false;
        }
      }));
      eligibleTeamCount = availability.filter(Boolean).length;
    }
    return { reserved: Boolean(puzzleId), puzzle_id: puzzleId, puzzle_title: puzzleTitle, eligible_team_count: eligibleTeamCount };
  }

  private async reserveTerminal(payload: Record<string, unknown>): Promise<Response> {
    const terminalId = cleanText(payload.terminal_id, 128);
    const puzzleId = cleanText(payload.puzzle_id, 128);
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const device = directory.terminalDevices[terminalId];
    if (!device) return json({ error: "terminal_not_found" }, 404);
    if (device.status !== "free") return json({ error: "terminal_attached" }, 409);
    const catalog = await this.terminalCatalog();
    if (puzzleId && !catalog.some((puzzle) => puzzle.id === puzzleId)) return json({ error: "invalid_puzzle_id" }, 400);
    device.puzzleId = puzzleId;
    device.updatedAt = new Date().toISOString();
    await this.ctx.storage.put(DIRECTORY_KEY, directory);
    for (const socket of this.ctx.getWebSockets()) {
      const attachment = socket.deserializeAttachment() as SocketAttachment | null;
      if (attachment?.role === "terminal_waiting" && attachment.terminalId === terminalId && socket.readyState === WebSocket.OPEN) {
        this.send(socket, "terminal.status", await this.terminalStatus(directory, terminalId));
      }
    }
    return json({ success: true, terminal_id: terminalId, puzzle_id: puzzleId });
  }

  private async terminalCatalog(): Promise<Array<{ id: string; title: string; play_mode: string }>> {
    const catalog = new Map<string, { id: string; title: string; play_mode: string }>();
    for (const game of await this.loadRuntimeGames()) {
      const scenario = await this.loadScenario(game.id);
      for (const [id, value] of Object.entries(objectRecord(scenario.puzzles))) {
        const puzzle = objectRecord(value);
        const terminal = objectRecord(puzzle.terminal);
        const mode = String(terminal.mode || "phones");
        if (mode === "phones") continue;
        catalog.set(id, { id, title: String(puzzle.title || id), play_mode: mode });
      }
    }
    return [...catalog.values()].sort((left, right) => left.title.localeCompare(right.title, "cs"));
  }

  private async claimTerminal(payload: Record<string, unknown>): Promise<Response> {
    const code = cleanText(payload.code, 64).toUpperCase();
    const sessionId = cleanText(payload.session_id, 128);
    const controllerId = cleanText(payload.controller_id, 128);
    const eligible = new Set(Array.isArray(payload.eligible_puzzle_ids) ? payload.eligible_puzzle_ids.map(String) : []);
    if (!TERMINAL_CODE_PATTERN.test(code) || !SESSION_ID_PATTERN.test(sessionId) || !CLIENT_ID_PATTERN.test(controllerId)) {
      return json({ error: "invalid_terminal_pairing" }, 400);
    }
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const now = Date.now();
    for (const [digest, pairing] of Object.entries(directory.terminalPairings)) {
      if (pairing.expiresAt <= now) delete directory.terminalPairings[digest];
    }
    const digest = await secretDigest(code);
    const pairing = directory.terminalPairings[digest];
    const device = pairing ? directory.terminalDevices[pairing.terminalId] : null;
    if (!pairing || !device || pairing.expiresAt <= now || device.status !== "free") {
      await this.ctx.storage.put(DIRECTORY_KEY, directory);
      return json({ error: "expired", reason: "Párovací QR terminálu už není platný. Na tabletu vytvořte nový." }, 410);
    }
    if (!device.puzzleId || !eligible.has(device.puzzleId)) {
      return json({ error: "puzzle_unavailable", reason: "Tento terminál je vyhrazen jiné hádance, než má váš tým právě dostupnou." }, 409);
    }
    const token = randomRecoveryToken();
    directory.terminalRoutes[await secretDigest(token)] = {
      terminalId: device.id,
      sessionId,
      controllerId,
      puzzleId: device.puzzleId,
      expiresAt: now + 60_000,
    };
    delete directory.terminalPairings[digest];
    device.status = "routing";
    device.online = true;
    device.sessionId = sessionId;
    device.controllerId = controllerId;
    device.updatedAt = new Date().toISOString();
    await this.ctx.storage.put(DIRECTORY_KEY, directory);
    return json({
      success: true,
      terminal_id: device.id,
      puzzle_id: device.puzzleId,
      terminal_label: device.label,
      attach_token: token,
    });
  }

  private async dispatchTerminalRoute(payload: Record<string, unknown>): Promise<Response> {
    const token = cleanText(payload.token, 64).toUpperCase();
    const sessionId = cleanText(payload.session_id, 128);
    if (!TERMINAL_CODE_PATTERN.test(token) || !SESSION_ID_PATTERN.test(sessionId)) {
      return json({ error: "invalid_terminal_route" }, 400);
    }
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const route = directory.terminalRoutes[await secretDigest(token)];
    const device = route ? directory.terminalDevices[route.terminalId] : null;
    if (!route || !device || route.expiresAt <= Date.now() || route.sessionId !== sessionId) {
      return json({ error: "invalid_terminal_route" }, 410);
    }
    const socket = this.ctx.getWebSockets().find((candidate) => {
      const attachment = candidate.deserializeAttachment() as SocketAttachment | null;
      return attachment?.role === "terminal_waiting" && attachment.terminalId === device.id && candidate.readyState === WebSocket.OPEN;
    });
    if (!socket) {
      delete directory.terminalRoutes[await secretDigest(token)];
      device.status = "free";
      device.sessionId = "";
      device.controllerId = "";
      device.online = false;
      await this.ctx.storage.put(DIRECTORY_KEY, directory);
      return json({ error: "terminal_offline" }, 410);
    }
    this.send(socket, "terminal.route", { session_id: sessionId, terminal_id: device.id, attach_token: token });
    return json({ success: true });
  }

  private async consumeTerminalRoute(payload: Record<string, unknown>): Promise<Response> {
    const terminalId = cleanText(payload.terminal_id, 128);
    const sessionId = cleanText(payload.session_id, 128);
    const token = cleanText(payload.token, 64).toUpperCase();
    if (!TERMINAL_CODE_PATTERN.test(token)) return json({ error: "invalid_terminal_route" }, 400);
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const digest = await secretDigest(token);
    const route = directory.terminalRoutes[digest];
    const device = directory.terminalDevices[terminalId];
    if (!route || !device || route.expiresAt <= Date.now() || route.terminalId !== terminalId || route.sessionId !== sessionId) {
      delete directory.terminalRoutes[digest];
      await this.ctx.storage.put(DIRECTORY_KEY, directory);
      return json({ error: "invalid_terminal_route" }, 410);
    }
    delete directory.terminalRoutes[digest];
    device.status = "attached";
    device.online = true;
    device.updatedAt = new Date().toISOString();
    await this.ctx.storage.put(DIRECTORY_KEY, directory);
    return json({
      controller_id: route.controllerId,
      puzzle_id: route.puzzleId,
      terminal_label: device.label,
    });
  }

  private async markTerminalReleased(payload: Record<string, unknown>): Promise<Response> {
    const terminalId = cleanText(payload.terminal_id, 128);
    const sessionId = cleanText(payload.session_id, 128);
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const device = directory.terminalDevices[terminalId];
    if (device && (!sessionId || device.sessionId === sessionId)) {
      device.status = "free";
      device.sessionId = "";
      device.controllerId = "";
      device.online = false;
      device.updatedAt = new Date().toISOString();
      await this.ctx.storage.put(DIRECTORY_KEY, directory);
    }
    return json({ success: true });
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

  private async createPlayerRecovery(payload: Record<string, unknown>): Promise<Response> {
    const sessionId = cleanText(payload.session_id, 128);
    const playerId = cleanText(payload.player_id, 128);
    if (!SESSION_ID_PATTERN.test(sessionId) || !CLIENT_ID_PATTERN.test(playerId)) {
      return json({ error: "invalid_player_recovery_request" }, 400);
    }
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const knownSessions = new Set([
      ...Object.values(directory.teamKeys),
      ...Object.values(directory.creatorKeys),
      ...Object.values(directory.joinCodes),
    ]);
    if (!knownSessions.has(sessionId)) return json({ error: "session_not_found" }, 404);
    const validation = await this.runtimeEnv.GAME_SESSIONS.getByName(sessionId).fetch(
      "https://internal/internal/admin/player-recovery/validate",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-EscapeBot-Internal-Admin": "1",
        },
        body: JSON.stringify({ player_id: playerId }),
      },
    );
    const player = await validation.json<Record<string, unknown>>();
    if (!validation.ok) return json(player, validation.status);

    const now = Date.now();
    for (const [digest, recovery] of Object.entries(directory.recoveryTokens)) {
      if (recovery.expiresAt <= now || (recovery.sessionId === sessionId && recovery.playerId === playerId)) {
        delete directory.recoveryTokens[digest];
      }
    }
    let token = randomRecoveryToken();
    let digest = await secretDigest(token);
    while (directory.recoveryTokens[digest]) {
      token = randomRecoveryToken();
      digest = await secretDigest(token);
    }
    directory.recoveryTokens[digest] = { sessionId, playerId, expiresAt: now + 600_000 };
    await this.ctx.storage.put(DIRECTORY_KEY, directory);
    return json({
      token,
      player_name: String(player.player_name || ""),
      team_name: String(player.team_name || ""),
      expires_in_seconds: 600,
    });
  }

  private validatePlayerRecovery(payload: Record<string, unknown>): Response {
    const playerId = cleanText(payload.player_id, 128);
    const player = this.snapshot.lobby.players[playerId];
    if (!player) return json({ error: "Hráč v této relaci neexistuje." }, 404);
    return json({ player_name: player.name, team_name: this.snapshot.lobby.teamName });
  }

  private async recoverLobbyPlayer(payload: Record<string, unknown>): Promise<Response> {
    const oldClientId = cleanText(payload.old_client_id, 128);
    const newClientId = cleanText(payload.new_client_id, 128);
    const recoveryId = cleanText(payload.recovery_id, 64).toLowerCase();
    if (!CLIENT_ID_PATTERN.test(oldClientId) || !CLIENT_ID_PATTERN.test(newClientId) || !/^[a-f0-9]{64}$/.test(recoveryId)) {
      return json({ error: "Chybí identifikátor nového zařízení." }, 400);
    }
    const previous = this.snapshot.identityRecoveryReceipts[recoveryId];
    if (previous) {
      if (previous.old_client_id !== oldClientId || previous.new_client_id !== newClientId) {
        return json({ error: "Návratový kód neodpovídá požadovanému přenosu." }, 409);
      }
      return json(previous);
    }
    const player = this.snapshot.lobby.players[oldClientId];
    if (!player) return json({ error: "Původní hráč v týmu neexistuje." }, 404);
    if (newClientId !== oldClientId && this.snapshot.lobby.players[newClientId]) {
      return json({ error: "Nové zařízení už v tomto týmu patří jinému hráči." }, 409);
    }
    const now = new Date().toISOString();
    const creatorTransferred = this.snapshot.lobby.creatorId === oldClientId;
    if (newClientId !== oldClientId) {
      delete this.snapshot.lobby.players[oldClientId];
      this.snapshot.lobby.players[newClientId] = {
        ...player,
        id: newClientId,
        recoveredAt: now,
      };
      if (creatorTransferred) this.snapshot.lobby.creatorId = newClientId;
      this.snapshot.gameState = transferPlayerIdentity(this.snapshot.gameState, oldClientId, newClientId);
      const receipts: Record<string, ProtocolMessage[]> = {};
      for (const [key, messages] of Object.entries(this.snapshot.operationReceipts)) {
        const targetKey = key.startsWith(`${oldClientId}:`)
          ? `${newClientId}:${key.slice(oldClientId.length + 1)}`
          : key;
        receipts[targetKey] = messages;
      }
      this.snapshot.operationReceipts = receipts;
    } else {
      player.recoveredAt = now;
    }
    const history = Array.isArray(this.snapshot.gameState.event_history)
      ? this.snapshot.gameState.event_history
      : [];
    history.push({
      at: now,
      type: "player.identity_transferred",
      details: { old_player_id: oldClientId, new_player_id: newClientId },
    });
    this.snapshot.gameState.event_history = history.slice(-500);
    this.snapshot.revision += 1;
    this.snapshot.updatedAt = now;
    const recoveryResult = {
      old_client_id: oldClientId,
      new_client_id: newClientId,
      player_name: player.name,
      team_name: this.snapshot.lobby.teamName,
      mode: this.snapshot.lobby.mode,
      join_code: this.snapshot.lobby.joinCode,
      creator_transferred: creatorTransferred,
      revision: this.snapshot.revision,
    };
    this.snapshot.identityRecoveryReceipts[recoveryId] = recoveryResult;
    while (Object.keys(this.snapshot.identityRecoveryReceipts).length > 20) {
      delete this.snapshot.identityRecoveryReceipts[Object.keys(this.snapshot.identityRecoveryReceipts)[0]];
    }
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);

    for (const candidate of this.ctx.getWebSockets()) {
      const attachment = candidate.deserializeAttachment() as SocketAttachment | null;
      if (attachment?.role !== "session" || attachment.clientId !== oldClientId) continue;
      this.send(candidate, "admin.session_removed", { message: "Identita hráče byla obnovena na novém zařízení." });
      candidate.close(4002, "Player identity transferred");
    }
    this.broadcastLobbyState();
    if (this.snapshot.lobby.started) await this.broadcastGameState();
    return json(recoveryResult);
  }

  private async adminOverview(): Promise<Response> {
    const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
    const sessionIds = [...new Set([
      ...Object.values(directory.teamKeys),
      ...Object.values(directory.creatorKeys),
      ...Object.values(directory.joinCodes),
    ])].filter((sessionId) => SESSION_ID_PATTERN.test(sessionId));
    const snapshots = await Promise.all(sessionIds.map(async (sessionId) => {
      try {
        const response = await this.runtimeEnv.GAME_SESSIONS.getByName(sessionId).fetch(
          "https://internal/internal/admin/snapshot",
          { headers: { "X-EscapeBot-Internal-Admin": "1" } },
        );
        return response.ok ? await response.json<Record<string, unknown>>() : null;
      } catch {
        return null;
      }
    }));
    const teams = snapshots
      .filter((snapshot): snapshot is Record<string, unknown> => snapshot !== null)
      .sort((left, right) => String(left.team_name || "").localeCompare(String(right.team_name || ""), "cs"));
    const terminalCatalog = await this.terminalCatalog();
    const terminals = Object.values(directory.terminalDevices)
      .filter((device) => device.online)
      .map((device) => ({
        id: device.id,
        label: device.label,
        status: device.status === "free" ? "free" : "attached",
        session_id: device.sessionId,
        team_name: teams.find((team) => team.session_id === device.sessionId)?.team_name || "",
        puzzle_id: device.puzzleId,
      }))
      .sort((left, right) => left.label.localeCompare(right.label, "cs"));
    return json({
      cloudflare_limited: true,
      teams,
      leaderboard: [],
      resolution_presets: {},
      scenario_catalog: [],
      scenario_errors: [],
      puzzle_catalog: terminalCatalog,
      terminals,
      display_status: { online: false, mode: "cloudflare", screen: "not_migrated", fullscreen: false, wake_lock: false },
    });
  }

  private adminSessionSnapshot(): Response {
    if (!this.snapshot.lobby.creatorId) return json({ error: "session_not_found" }, 404);
    const state = this.snapshot.gameState;
    const flags = objectRecord(state.flags);
    const connected = this.connectedClientIds();
    const players = Object.values(this.snapshot.lobby.players);
    const playerIds = players.map((player) => player.id);
    const exclusions = objectRecord(state.game_exclusions);
    const results = objectRecord(state.game_results);
    const lineGames = objectRecord(state.interactive_games);
    const triadGames = objectRecord(state.triad_games);
    const now = Date.now();
    const lastActivity = String(state.last_activity_at || this.snapshot.updatedAt || "");
    const lastActivityAt = Date.parse(lastActivity);
    const inactiveSeconds = Number.isFinite(lastActivityAt)
      ? Math.max(0, Math.floor((now - lastActivityAt) / 1000))
      : 0;
    const gameCompleted = Boolean(flags.game_completed);
    const administrativelyEnded = Boolean(flags.administratively_ended);
    const activityStatus = !this.snapshot.lobby.started || gameCompleted || administrativelyEnded
      ? "active"
      : inactiveSeconds >= 3600 ? "abandoned" : inactiveSeconds >= 1800 ? "suspicious" : "active";
    const progress = objectRecord(this.snapshot.scenarioProgress);
    const nodes = Array.isArray(progress.nodes) ? progress.nodes : [];
    const playerGameMetrics = (
      stores: Record<string, any>,
      gameType: "line" | "triad",
    ): Record<string, unknown>[] => Object.entries(stores).flatMap(([gameId, containerValue]) => {
      const container = objectRecord(containerValue);
      const storedPlayers = objectRecord(container.players);
      return playerIds.map((playerId, playerIndex) => {
        const game = objectRecord(Object.keys(storedPlayers).length
          ? storedPlayers[playerId]
          : playerIndex === 0 ? container : {});
        const common = {
          id: gameId,
          player_id: playerId,
          player_name: this.snapshot.lobby.players[playerId]?.name || "Hráč",
          connected: connected.has(playerId),
          excluded: Array.isArray(exclusions[gameId]) && exclusions[gameId].map(String).includes(playerId),
          status: String(game.status || "not_started"),
          result: objectRecord(results[gameId])[playerId] ?? null,
        };
        return gameType === "line"
          ? { ...common, swaps: Number(game.swaps || 0), progress: objectRecord(game.progress) }
          : {
            ...common,
            placements: Number(game.placements || 0),
            completed_orientations: Array.isArray(game.completed_orientations) ? game.completed_orientations : [],
          };
      });
    });
    const timeline = [
      ...(Array.isArray(state.event_history) ? state.event_history : []),
      ...Object.entries(objectRecord(state.checkpoint_states)).flatMap(([checkpointId, checkpointValue]) => {
        const checkpoint = objectRecord(checkpointValue);
        const events: Record<string, unknown>[] = [];
        if (checkpoint.first_scanned_at || checkpoint.found_at) {
          events.push({ at: checkpoint.first_scanned_at || checkpoint.found_at, type: "checkpoint_found", label: checkpointId });
        }
        if (checkpoint.solved_at) events.push({ at: checkpoint.solved_at, type: "checkpoint_solved", label: checkpointId });
        return events;
      }),
    ].sort((left, right) => String(objectRecord(right).at || "").localeCompare(String(objectRecord(left).at || "")));
    return json({
      ...this.lobbyPayload(""),
      score: Number(state.score || 0),
      phase: String(state.phase || "lobby"),
      completed_nodes: nodes.filter((node) => objectRecord(node).status === "complete").length,
      total_nodes: nodes.length,
      progress,
      admin_penalties: Array.isArray(flags.admin_penalties) ? flags.admin_penalties : [],
      admin_score_adjustments: Array.isArray(flags.admin_score_adjustments) ? flags.admin_score_adjustments : [],
      last_activity: lastActivity,
      inactive_seconds: inactiveSeconds,
      activity_status: activityStatus,
      game_completed: gameCompleted,
      administratively_ended: administrativelyEnded,
      out_of_competition: Boolean(flags.out_of_competition),
      end_reason: String(flags.administratively_ended_reason || (gameCompleted ? "completed" : "")),
      administratively_evaluated: Boolean(flags.administratively_evaluated),
      terminal_online: this.ctx.getWebSockets().some((socket) => {
        const attachment = socket.deserializeAttachment() as SocketAttachment | null;
        return attachment?.role === "terminal" && socket.readyState === WebSocket.OPEN;
      }),
      terminal_assignment: String(flags.terminal_assignment || ""),
      terminal_options: [],
      timeline,
      hints_used: objectRecord(state.hints_used),
      puzzle_attempts: objectRecord(state.puzzle_attempts),
      puzzle_telemetry: [],
      recent_messages: this.snapshot.chatHistory.slice(-8),
      support_chat: this.snapshot.chatHistory.filter((item) => item.channel === "support"),
      admin_support_joined: false,
      game_metrics: {
        line: playerGameMetrics(lineGames, "line"),
        karel: [],
        sokoban: [],
        triad: playerGameMetrics(triadGames, "triad"),
        archive: [],
      },
    });
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

  private async handleTerminalClaim(
    socket: WebSocket,
    attachment: SocketAttachment,
    payload: Record<string, unknown>,
  ): Promise<void> {
    await this.serializeState(async () => {
      if (!this.snapshot.lobby.started || !this.snapshot.lobby.players[attachment.clientId]) {
        this.send(socket, "terminal.attach_result", { success: false, reason: "Nejprve se připojte k rozehrané týmové relaci." });
        return;
      }
      const code = cleanText(payload.value, 128).toUpperCase().replace("ESCAPEBOT://TERMINAL/", "");
      if (!TERMINAL_CODE_PATTERN.test(code)) {
        this.send(socket, "terminal.attach_result", { success: false, reason: "Párovací QR terminálu není platný." });
        return;
      }
      const scenario = await this.loadScenario(this.snapshot.lobby.scenarioId);
      const previousGameState = structuredClone(this.snapshot.gameState);
      const eligiblePuzzleIds = Object.keys(objectRecord(scenario.puzzles)).filter(
        (puzzleId) => terminalPuzzleAvailable(scenario, this.snapshot.gameState, puzzleId),
      );
      const response = await this.runtimeEnv.GAME_SESSIONS.getByName(DIRECTORY_OBJECT_NAME).fetch(
        "https://internal/internal/terminal/claim",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Terminal": "1" },
          body: JSON.stringify({
            code,
            session_id: this.snapshot.sessionId,
            controller_id: attachment.clientId,
            eligible_puzzle_ids: eligiblePuzzleIds,
          }),
        },
      );
      const result = await response.json<Record<string, unknown>>();
      if (!response.ok) {
        this.send(socket, "terminal.attach_result", { success: false, reason: String(result.reason || "Terminál nelze odemknout.") });
        return;
      }
      const puzzleId = String(result.puzzle_id || "");
      const puzzle = objectRecord(objectRecord(scenario.puzzles)[puzzleId]);
      const checkpointId = String(puzzle.checkpoint_id || "");
      let activationMessages: Array<{ type: string; payload: Record<string, unknown> }> = [];
      if (!Object.hasOwn(objectRecord(this.snapshot.gameState.checkpoint_states), checkpointId)) {
        const checkpoint = objectRecord(objectRecord(scenario.checkpoints)[checkpointId]);
        const activation = applyScenarioCommand(
          scenario,
          this.snapshot.gameState,
          "qr.detected",
          { value: `escapebot://checkpoint/${String(checkpoint.token || "")}` },
          new Date().toISOString(),
          this.runtimeActor(attachment.clientId),
        );
        this.snapshot.gameState = activation.state;
        activationMessages = activation.messages;
      }
      this.snapshot.gameState.flags = { ...this.snapshot.gameState.flags, terminal_assignment: puzzleId };
      this.snapshot.scenarioProgress = buildScenarioProgress(scenario, this.snapshot.gameState);
      this.snapshot.revision += 1;
      this.snapshot.updatedAt = new Date().toISOString();
      await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
      const dispatched = await this.runtimeEnv.GAME_SESSIONS.getByName(DIRECTORY_OBJECT_NAME).fetch(
        "https://internal/internal/terminal/dispatch-route",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Terminal": "1" },
          body: JSON.stringify({ token: result.attach_token, session_id: this.snapshot.sessionId }),
        },
      );
      if (!dispatched.ok) {
        this.snapshot.gameState = previousGameState;
        this.snapshot.scenarioProgress = buildScenarioProgress(scenario, previousGameState);
        this.snapshot.revision += 1;
        this.snapshot.updatedAt = new Date().toISOString();
        await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
        this.send(socket, "terminal.attach_result", { success: false, reason: "Terminál už není připojený." });
        await this.broadcastGameState(scenario);
        return;
      }
      for (const message of activationMessages) this.broadcastProtocol(message);
      this.send(socket, "terminal.attach_result", {
        success: true,
        session_id: this.snapshot.sessionId,
        team_name: this.snapshot.lobby.teamName,
        controller_name: this.snapshot.lobby.players[attachment.clientId].name,
      });
      await this.broadcastGameState(scenario);
    });
  }

  private async attachTerminal(socket: WebSocket, attachment: SocketAttachment, puzzleId: string): Promise<void> {
    if (!this.snapshot.lobby.started || !this.snapshot.lobby.players[attachment.clientId]) {
      socket.close(4003, "Terminal controller is no longer a team member");
      return;
    }
    this.snapshot.gameState.flags = { ...this.snapshot.gameState.flags, terminal_assignment: puzzleId };
    this.snapshot.terminalReleaseAt = null;
    this.snapshot.revision += 1;
    this.snapshot.updatedAt = new Date().toISOString();
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    this.send(socket, "terminal.attached", {
      success: true,
      session_id: this.snapshot.sessionId,
      team_name: this.snapshot.lobby.teamName,
      controller_name: this.snapshot.lobby.players[attachment.clientId].name,
    });
    await this.sendAuthoritativeSnapshot(socket, false);
    await this.broadcastGameState();
  }

  private async releaseTerminalById(terminalId: string, reason: string, notifyDirectory = true): Promise<void> {
    const terminals = this.ctx.getWebSockets().filter((candidate) => {
      const attachment = candidate.deserializeAttachment() as SocketAttachment | null;
      return attachment?.role === "terminal" && (!terminalId || attachment.terminalId === terminalId);
    });
    if (!notifyDirectory) return;
    for (const terminal of terminals) {
      if (terminal.readyState === WebSocket.OPEN) this.send(terminal, "terminal.released", { reason });
      terminal.close(4003, "Terminal released");
    }
    const remaining = this.ctx.getWebSockets().some((candidate) => {
      if (terminals.includes(candidate)) return false;
      const attachment = candidate.deserializeAttachment() as SocketAttachment | null;
      return attachment?.role === "terminal" && candidate.readyState === WebSocket.OPEN;
    });
    if (!remaining && this.snapshot.gameState.flags.terminal_assignment) {
      const flags = { ...this.snapshot.gameState.flags };
      delete flags.terminal_assignment;
      this.snapshot.gameState = { ...this.snapshot.gameState, flags };
      this.snapshot.terminalReleaseAt = null;
      this.snapshot.revision += 1;
      this.snapshot.updatedAt = new Date().toISOString();
      await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
      await this.scheduleNextAlarm();
      await this.broadcastGameState();
    }
    for (const terminal of terminals) {
      const attachment = terminal.deserializeAttachment() as SocketAttachment | null;
      if (attachment?.terminalId) await this.notifyTerminalReleased(attachment.terminalId);
    }
  }

  private async notifyTerminalReleased(terminalId: string): Promise<void> {
    await this.runtimeEnv.GAME_SESSIONS.getByName(DIRECTORY_OBJECT_NAME).fetch(
      "https://internal/internal/terminal/released",
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Terminal": "1" },
        body: JSON.stringify({ terminal_id: terminalId, session_id: this.snapshot.sessionId }),
      },
    );
  }

  private async scheduleTerminalRelease(scenario: ScenarioDocument): Promise<void> {
    const puzzleId = String(this.snapshot.gameState.flags.terminal_assignment || "");
    if (!puzzleId || this.snapshot.terminalReleaseAt !== null) return;
    const puzzle = objectRecord(objectRecord(scenario.puzzles)[puzzleId]);
    const checkpoint = objectRecord(objectRecord(this.snapshot.gameState.checkpoint_states)[String(puzzle.checkpoint_id || "")]);
    if (checkpoint.status !== "solved") return;
    const delaySeconds = String(puzzle.type || "") === "finale" ? Number(puzzle.countdown_seconds || 10) + 8.5 : 3.5;
    this.snapshot.terminalReleaseAt = Date.now() + Math.round(delaySeconds * 1000);
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    await this.scheduleNextAlarm();
  }

  private async scheduleNextAlarm(): Promise<void> {
    const candidates = [this.snapshot.deadlineAt, this.snapshot.terminalReleaseAt]
      .filter((value): value is number => value !== null);
    if (candidates.length) await this.ctx.storage.setAlarm(Math.min(...candidates));
    else await this.ctx.storage.deleteAlarm();
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
            this.presentState(scenario, attachment, now),
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
      await this.scheduleTerminalRelease(scenario);

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
    const attachment = socket.deserializeAttachment() as SocketAttachment | null;
    if (attachment?.role === "terminal_waiting" && attachment.terminalId) {
      this.ctx.waitUntil(this.serializeDirectory(async () => {
        const directory = normalizeDirectory(await this.ctx.storage.get<DirectorySnapshot>(DIRECTORY_KEY));
        const device = directory.terminalDevices[attachment.terminalId || ""];
        const anotherWaiting = this.ctx.getWebSockets().some((candidate) => {
          if (candidate === socket) return false;
          const current = candidate.deserializeAttachment() as SocketAttachment | null;
          return current?.role === "terminal_waiting" && current.terminalId === attachment.terminalId && candidate.readyState === WebSocket.OPEN;
        });
        if (device && device.status === "free" && !anotherWaiting) device.online = false;
        for (const [digest, pairing] of Object.entries(directory.terminalPairings)) {
          if (pairing.terminalId === attachment.terminalId) delete directory.terminalPairings[digest];
        }
        await this.ctx.storage.put(DIRECTORY_KEY, directory);
      }));
    }
    if (attachment?.role === "terminal" && attachment.terminalId) {
      this.ctx.waitUntil(this.serializeState(async () => {
        await this.notifyTerminalReleased(attachment.terminalId || "");
        const hasAnother = this.ctx.getWebSockets().some((candidate) => {
          if (candidate === socket) return false;
          const current = candidate.deserializeAttachment() as SocketAttachment | null;
          return current?.role === "terminal" && candidate.readyState === WebSocket.OPEN;
        });
        if (!hasAnother && this.snapshot.gameState.flags.terminal_assignment) {
          const flags = { ...this.snapshot.gameState.flags };
          delete flags.terminal_assignment;
          this.snapshot.gameState = { ...this.snapshot.gameState, flags };
          this.snapshot.terminalReleaseAt = null;
          this.snapshot.revision += 1;
          this.snapshot.updatedAt = new Date().toISOString();
          await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
          await this.scheduleNextAlarm();
          await this.broadcastGameState();
        }
      }));
    }
    socket.close(code, reason);
  }

  async alarm(): Promise<void> {
    if (
      this.snapshot.terminalReleaseAt !== null &&
      (this.snapshot.deadlineAt === null || this.snapshot.terminalReleaseAt <= this.snapshot.deadlineAt)
    ) {
      this.snapshot.terminalReleaseAt = null;
      await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
      await this.releaseTerminalById("", "Hádanka byla dokončena. Terminál je znovu volný.");
      await this.scheduleNextAlarm();
      return;
    }
    if (this.snapshot.deadlineAt === null) return;
    if (this.snapshot.deadlineKind === "game") {
      const flags = { ...this.snapshot.gameState.flags };
      if (flags.game_completed || flags.deadline_reached_at || flags.out_of_competition) {
        this.snapshot = { ...this.snapshot, deadlineAt: null, deadlineKind: null };
        await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
        await this.scheduleNextAlarm();
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
      await this.scheduleNextAlarm();
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
    await this.scheduleNextAlarm();
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
    await this.scheduleNextAlarm();
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
      if (socket.readyState !== WebSocket.OPEN) continue;
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
    if (this.snapshot.lobby.started && (attachment?.role === "session" || attachment?.role === "terminal")) {
      const scenario = scenarioValue ?? await this.loadScenario(this.snapshot.lobby.scenarioId);
      gameState = this.presentState(scenario, attachment, new Date().toISOString());
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

  private presentState(
    scenario: ScenarioDocument,
    attachment: SocketAttachment,
    now: string,
  ): GameStateDocument {
    const state = presentGameState(scenario, this.snapshot.gameState, this.runtimeActor(attachment.clientId), now);
    const attached = this.ctx.getWebSockets().some((socket) => {
      const current = socket.deserializeAttachment() as SocketAttachment | null;
      return current?.role === "terminal" && socket.readyState === WebSocket.OPEN;
    });
    const assigned = String(this.snapshot.gameState.flags.terminal_assignment || "");
    if (Array.isArray(state.puzzles)) {
      state.puzzles = state.puzzles.map((value: unknown) => {
        const puzzle = objectRecord(value);
        const configured = objectRecord(puzzle.terminal);
        const mode = String(configured.mode || "phones");
        if (mode === "phones") {
          delete puzzle.terminal;
          return puzzle;
        }
        puzzle.terminal = {
          mode,
          label: String(configured.label || puzzle.title || "Herní terminál"),
          attached,
          device: attachment.role === "terminal",
          assigned: String(puzzle.id || "") === assigned,
        };
        return puzzle;
      });
    }
    return state;
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
      if (socket.readyState !== WebSocket.OPEN) continue;
      const attachment = socket.deserializeAttachment() as SocketAttachment | null;
      if (attachment?.role !== "session" && attachment?.role !== "terminal") continue;
      const state = scenario
        ? this.presentState(scenario, attachment, now)
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
      if (socket.readyState !== WebSocket.OPEN) continue;
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
    if (url.pathname === "/api/admin/overview" && request.method === "GET") {
      const unauthorized = await authorizeAdmin(request, env);
      if (unauthorized) return unauthorized;
      return env.GAME_SESSIONS.getByName(DIRECTORY_OBJECT_NAME).fetch(
        "https://internal/internal/admin/overview",
        { headers: { "X-EscapeBot-Internal-Admin": "1" } },
      );
    }
    const eventRoute = url.pathname.match(/^\/api\/admin\/events\/([^/]+)$/);
    if (eventRoute && new Set(["GET", "PUT"]).has(request.method)) {
      const unauthorized = await authorizeAdmin(request, env);
      if (unauthorized) return unauthorized;
      let eventId: string;
      try {
        eventId = decodeURIComponent(eventRoute[1]);
      } catch {
        return json({ error: "invalid_event_id" }, 400);
      }
      if (!EVENT_ID_PATTERN.test(eventId)) return json({ error: "invalid_event_id" }, 400);
      if (request.method === "GET") {
        return env.EVENTS.getByName(eventId).fetch("https://internal/internal/event", {
          headers: { "X-EscapeBot-Internal-Admin": "1" },
        });
      }
      let payload: Record<string, unknown>;
      try {
        payload = await request.json<Record<string, unknown>>();
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      return env.EVENTS.getByName(eventId).fetch("https://internal/internal/event", {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Admin": "1" },
        body: JSON.stringify({ ...payload, id: eventId }),
      });
    }
    if (url.pathname === "/api/admin/player-recovery" && request.method === "POST") {
      const unauthorized = await authorizeAdmin(request, env);
      if (unauthorized) return unauthorized;
      let payload: Record<string, unknown>;
      try {
        payload = await request.json<Record<string, unknown>>();
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      return env.GAME_SESSIONS.getByName(DIRECTORY_OBJECT_NAME).fetch(
        "https://internal/internal/admin/player-recovery",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-EscapeBot-Internal-Admin": "1",
          },
          body: JSON.stringify(payload),
        },
      );
    }
    if (url.pathname === "/api/admin/terminal-reserve" && request.method === "POST") {
      const unauthorized = await authorizeAdmin(request, env);
      if (unauthorized) return unauthorized;
      let payload: Record<string, unknown>;
      try {
        payload = await request.json<Record<string, unknown>>();
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      return env.GAME_SESSIONS.getByName(DIRECTORY_OBJECT_NAME).fetch(
        "https://internal/internal/admin/terminal-reserve",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Admin": "1" },
          body: JSON.stringify(payload),
        },
      );
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
