import { DurableObject } from "cloudflare:workers";
import { diagnosticPage } from "./diagnostic";

interface Env {
  APP_ENV: string;
  GAME_SESSIONS: DurableObjectNamespace<GameSession>;
}

interface SocketAttachment {
  clientId: string;
  connectedAt: string;
}

interface ProtocolMessage {
  type: string;
  payload?: Record<string, unknown>;
}

interface SessionSnapshot {
  schemaVersion: 1;
  sessionId: string;
  revision: number;
  lobby: {
    teamName: string;
    started: boolean;
  };
  chatHistory: Array<Record<string, unknown>>;
  gameState: {
    phase: string;
    score: number;
    flags: Record<string, unknown>;
  };
  scenarioProgress: {
    completed: string[];
    available: string[];
  };
  deadlineAt: number | null;
  updatedAt: string;
}

const SNAPSHOT_KEY = "session-snapshot";
const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{8,128}$/;
const CLIENT_ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;

function json(data: unknown, status = 200): Response {
  return Response.json(data, { status });
}

function protocolMessage(type: string, payload: Record<string, unknown>): string {
  return JSON.stringify({ type, payload });
}

function defaultSnapshot(sessionId = ""): SessionSnapshot {
  return {
    schemaVersion: 1,
    sessionId,
    revision: 0,
    lobby: { teamName: "Cloudflare spike", started: false },
    chatHistory: [],
    gameState: { phase: "lobby", score: 0, flags: {} },
    scenarioProgress: { completed: [], available: [] },
    deadlineAt: null,
    updatedAt: new Date(0).toISOString(),
  };
}

export class GameSession extends DurableObject<Env> {
  private snapshot: SessionSnapshot = defaultSnapshot();

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      this.snapshot =
        (await ctx.storage.get<SessionSnapshot>(SNAPSHOT_KEY)) ?? defaultSnapshot();
    });
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket") {
      return json({ error: "websocket_upgrade_required" }, 426);
    }

    const url = new URL(request.url);
    const sessionId = request.headers.get("X-EscapeBot-Session-Id") ?? "";
    const clientId = url.searchParams.get("client_id") ?? "";
    if (!SESSION_ID_PATTERN.test(sessionId) || !CLIENT_ID_PATTERN.test(clientId)) {
      return json({ error: "invalid_session_or_client_id" }, 400);
    }
    if (this.snapshot.sessionId && this.snapshot.sessionId !== sessionId) {
      return json({ error: "session_routing_mismatch" }, 409);
    }
    if (!this.snapshot.sessionId) {
      this.snapshot = { ...this.snapshot, sessionId, updatedAt: new Date().toISOString() };
      await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    }

    const pair = new WebSocketPair();
    const client = pair[0];
    const server = pair[1];
    const attachment: SocketAttachment = {
      clientId,
      connectedAt: new Date().toISOString(),
    };
    server.serializeAttachment(attachment);
    this.ctx.acceptWebSocket(server);
    server.send(
      protocolMessage("session.connected", {
        session_id: sessionId,
        client_id: clientId,
        revision: this.snapshot.revision,
      }),
    );

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

    switch (message.type) {
      case "lobby.resume":
        this.sendAuthoritativeSnapshot(socket);
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
        this.send(socket, "error", { message: `Neznámý typ zprávy: ${message.type}` });
    }
  }

  webSocketClose(socket: WebSocket, code: number, reason: string): void {
    socket.close(code, reason);
  }

  async alarm(): Promise<void> {
    if (this.snapshot.deadlineAt === null) return;
    this.snapshot = {
      ...this.snapshot,
      revision: this.snapshot.revision + 1,
      deadlineAt: null,
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
    this.broadcastGameState();
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
    this.broadcastGameState();
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
      updatedAt: new Date().toISOString(),
    };
    await this.ctx.storage.put(SNAPSHOT_KEY, this.snapshot);
    await this.ctx.storage.setAlarm(deadlineAt);
    this.send(socket, "spike.deadline.scheduled", { deadline_at: deadlineAt });
  }

  private sendAuthoritativeSnapshot(socket: WebSocket): void {
    const players = this.ctx.getWebSockets().map((candidate) => {
      const attachment = candidate.deserializeAttachment() as SocketAttachment | null;
      return { client_id: attachment?.clientId ?? "unknown", online: true };
    });
    this.send(socket, "lobby.state", {
      session_id: this.snapshot.sessionId,
      revision: this.snapshot.revision,
      ...this.snapshot.lobby,
      players,
    });
    this.send(socket, "chat.history", { messages: this.snapshot.chatHistory });
    this.send(socket, "game.state", this.gameStatePayload());
    this.send(socket, "scenario.progress", this.snapshot.scenarioProgress);
  }

  private gameStatePayload(): Record<string, unknown> {
    return {
      session_id: this.snapshot.sessionId,
      revision: this.snapshot.revision,
      ...this.snapshot.gameState,
    };
  }

  private broadcastGameState(): void {
    this.broadcast("game.state", this.gameStatePayload());
  }

  private send(socket: WebSocket, type: string, payload: Record<string, unknown>): void {
    socket.send(protocolMessage(type, payload));
  }

  private broadcast(type: string, payload: Record<string, unknown>): void {
    const encoded = protocolMessage(type, payload);
    for (const socket of this.ctx.getWebSockets()) {
      try {
        socket.send(encoded);
      } catch {
        socket.close(1011, "Broadcast failed");
      }
    }
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/") return diagnosticPage();
    if (url.pathname === "/api/health") {
      return json({ status: "ok", runtime: "cloudflare", environment: env.APP_ENV });
    }
    if (url.pathname !== "/ws") return json({ error: "not_found" }, 404);
    if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket") {
      return json({ error: "websocket_upgrade_required" }, 426);
    }

    const sessionId = url.searchParams.get("session_id") ?? "";
    const clientId = url.searchParams.get("client_id") ?? "";
    if (!SESSION_ID_PATTERN.test(sessionId) || !CLIENT_ID_PATTERN.test(clientId)) {
      return json({ error: "invalid_session_or_client_id" }, 400);
    }

    const forwarded = new Request(request);
    forwarded.headers.set("X-EscapeBot-Session-Id", sessionId);
    return env.GAME_SESSIONS.getByName(sessionId).fetch(forwarded);
  },
} satisfies ExportedHandler<Env>;
