import { DurableObject } from "cloudflare:workers";

interface EventCoordinatorEnv {
  ASSETS: Fetcher;
}

type EventStatus = "draft" | "ready" | "open" | "paused" | "ended" | "archived";
type EventGameRole = "primary" | "competitive" | "side";

interface EventGameConfiguration {
  game_id: string;
  role: EventGameRole;
  queue_enabled: boolean;
  leaderboard_enabled: boolean;
  weight: number;
  start_interval_minutes: number;
  max_active_teams: number;
}

export interface EventSnapshot {
  schema_version: 1;
  id: string;
  revision: number;
  name: string;
  starts_at: string;
  ends_at: string;
  status: EventStatus;
  timezone: string;
  primary_game_id: string;
  games: EventGameConfiguration[];
  scenario_ids: string[];
  branding: {
    title: string;
    logo_url: string;
    accent_color: string;
  };
  leaderboard_finalized: boolean;
  leaderboard_finalized_at: string;
  created_at: string;
  updated_at: string;
}

interface StoredEventSnapshot extends EventSnapshot {
  applied_operations: string[];
}

const EVENT_SNAPSHOT_KEY = "event-snapshot";
export const EVENT_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const OPERATION_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const EVENT_STATUSES = new Set<EventStatus>(["draft", "ready", "open", "paused", "ended", "archived"]);
const EVENT_GAME_ROLES = new Set<EventGameRole>(["primary", "competitive", "side"]);

function json(data: unknown, status = 200): Response {
  const response = Response.json(data, { status });
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("X-Content-Type-Options", "nosniff");
  return response;
}

function cleanText(value: unknown, maximum: number): string {
  return String(value ?? "").trim().replace(/\s+/g, " ").slice(0, maximum);
}

function boundedNumber(value: unknown, fallback: number, minimum: number, maximum: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum ? parsed : fallback;
}

function boundedInteger(value: unknown, fallback: number, minimum: number, maximum: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : fallback;
}

function zonedTimestamp(value: unknown, label: string): string {
  const timestamp = cleanText(value, 64);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(timestamp) || !Number.isFinite(Date.parse(timestamp))) {
    throw new Error(`${label} musí být platný ISO čas s časovou zónou.`);
  }
  return new Date(timestamp).toISOString();
}

function validTimezone(value: unknown): string {
  const timezone = cleanText(value || "Europe/Prague", 64);
  try {
    new Intl.DateTimeFormat("cs-CZ", { timeZone: timezone }).format(new Date(0));
  } catch {
    throw new Error("Časová zóna eventu není platná.");
  }
  return timezone;
}

function publicSnapshot(snapshot: StoredEventSnapshot): EventSnapshot {
  const { applied_operations: _operations, ...event } = snapshot;
  return event;
}

export class EventCoordinator extends DurableObject<EventCoordinatorEnv> {
  private snapshot: StoredEventSnapshot | null = null;
  private updateQueue: Promise<void> = Promise.resolve();

  constructor(ctx: DurableObjectState, env: EventCoordinatorEnv) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      this.snapshot = await ctx.storage.get<StoredEventSnapshot>(EVENT_SNAPSHOT_KEY) ?? null;
    });
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("X-EscapeBot-Internal-Admin") !== "1") {
      return json({ error: "not_found" }, 404);
    }
    const url = new URL(request.url);
    if (url.pathname === "/internal/event" && request.method === "GET") {
      return this.snapshot
        ? json(publicSnapshot(this.snapshot))
        : json({ error: "event_not_found" }, 404);
    }
    if (url.pathname === "/internal/event" && request.method === "PUT") {
      let payload: Record<string, unknown>;
      try {
        payload = await request.json<Record<string, unknown>>();
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      return this.serializeUpdate(() => this.updateEvent(payload));
    }
    return json({ error: "not_found" }, 404);
  }

  private async serializeUpdate<T>(operation: () => Promise<T>): Promise<T> {
    const previous = this.updateQueue;
    let release: () => void = () => {};
    this.updateQueue = new Promise<void>((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      return await operation();
    } finally {
      release();
    }
  }

  private async updateEvent(payload: Record<string, unknown>): Promise<Response> {
    const eventId = cleanText(payload.id, 64);
    const operationId = cleanText(payload.operation_id, 128);
    if (!EVENT_ID_PATTERN.test(eventId)) return json({ error: "invalid_event_id" }, 400);
    if (!OPERATION_ID_PATTERN.test(operationId)) return json({ error: "invalid_operation_id" }, 400);
    if (this.snapshot && this.snapshot.id !== eventId) {
      return json({ error: "event_routing_mismatch" }, 409);
    }
    if (this.snapshot?.applied_operations.includes(operationId)) {
      return json({ changed: false, event: publicSnapshot(this.snapshot) });
    }
    const expectedRevision = payload.expected_revision;
    if (
      expectedRevision !== undefined &&
      (!Number.isInteger(expectedRevision) || Number(expectedRevision) !== (this.snapshot?.revision ?? 0))
    ) {
      return json({
        error: "revision_conflict",
        expected_revision: expectedRevision,
        current_revision: this.snapshot?.revision ?? 0,
      }, 409);
    }

    let normalized: Omit<EventSnapshot, "schema_version" | "revision" | "created_at" | "updated_at">;
    try {
      normalized = await this.normalizeEvent(eventId, payload);
    } catch (error) {
      return json({ error: "invalid_event", message: error instanceof Error ? error.message : "Event není platný." }, 400);
    }
    const now = new Date().toISOString();
    this.snapshot = {
      schema_version: 1,
      revision: (this.snapshot?.revision ?? 0) + 1,
      created_at: this.snapshot?.created_at ?? now,
      updated_at: now,
      ...normalized,
      applied_operations: [...(this.snapshot?.applied_operations ?? []), operationId].slice(-500),
    };
    await this.ctx.storage.put(EVENT_SNAPSHOT_KEY, this.snapshot);
    return json({ changed: true, event: publicSnapshot(this.snapshot) });
  }

  private async normalizeEvent(
    eventId: string,
    payload: Record<string, unknown>,
  ): Promise<Omit<EventSnapshot, "schema_version" | "revision" | "created_at" | "updated_at">> {
    const startsAt = zonedTimestamp(payload.starts_at, "Začátek eventu");
    const endsAt = zonedTimestamp(payload.ends_at, "Konec eventu");
    if (Date.parse(startsAt) >= Date.parse(endsAt)) {
      throw new Error("Konec eventu musí následovat po jeho začátku.");
    }
    const status = cleanText(payload.status || "draft", 16) as EventStatus;
    if (!EVENT_STATUSES.has(status)) throw new Error("Neznámý stav eventu.");
    const rawGames = payload.games;
    if (!Array.isArray(rawGames)) throw new Error("Konfigurace her eventu musí být seznam.");

    const catalogResponse = await this.env.ASSETS.fetch("https://assets.local/runtime-catalog.json");
    if (!catalogResponse.ok) throw new Error("Katalog her není dostupný.");
    const catalog = await catalogResponse.json<Array<{ id?: unknown }>>();
    const knownGames = new Set(catalog.map((item) => cleanText(item.id, 64)).filter(Boolean));
    const seen = new Set<string>();
    const games: EventGameConfiguration[] = [];
    for (const rawValue of rawGames) {
      const raw = rawValue && typeof rawValue === "object" && !Array.isArray(rawValue)
        ? rawValue as Record<string, unknown>
        : {};
      const gameId = cleanText(raw.game_id, 64);
      if (!gameId || seen.has(gameId)) continue;
      if (!knownGames.has(gameId)) throw new Error(`Event odkazuje na neznámou hru: ${gameId}.`);
      const role = cleanText(raw.role || "competitive", 16) as EventGameRole;
      if (!EVENT_GAME_ROLES.has(role)) throw new Error(`Neznámá role hry ${gameId}.`);
      games.push({
        game_id: gameId,
        role,
        queue_enabled: raw.queue_enabled === undefined ? role !== "side" : Boolean(raw.queue_enabled),
        leaderboard_enabled: raw.leaderboard_enabled === undefined ? role !== "side" : Boolean(raw.leaderboard_enabled),
        weight: boundedNumber(raw.weight, 1, 0, 1000),
        start_interval_minutes: boundedInteger(raw.start_interval_minutes, 0, 0, 1440),
        max_active_teams: boundedInteger(raw.max_active_teams, 0, 0, 10000),
      });
      seen.add(gameId);
    }
    if (!games.length) throw new Error("Event musí obsahovat alespoň jednu hru.");
    const primaryGames = games.filter((game) => game.role === "primary");
    if (primaryGames.length !== 1) throw new Error("Event musí mít právě jednu hlavní hru.");
    const requestedPrimary = cleanText(payload.primary_game_id, 64);
    if (requestedPrimary && requestedPrimary !== primaryGames[0].game_id) {
      throw new Error("Hlavní hra neodpovídá konfiguraci rolí.");
    }
    const accentColor = cleanText(payload.branding_accent_color || "#65f7ff", 16);
    if (!/^#[0-9a-f]{6}$/i.test(accentColor)) throw new Error("Barva eventu musí být ve formátu #RRGGBB.");
    const sameEvent = this.snapshot?.id === eventId;
    return {
      id: eventId,
      name: cleanText(payload.name, 120) || eventId,
      starts_at: startsAt,
      ends_at: endsAt,
      status,
      timezone: validTimezone(payload.timezone),
      primary_game_id: primaryGames[0].game_id,
      games,
      scenario_ids: games.map((game) => game.game_id),
      branding: {
        title: cleanText(payload.branding_title, 120),
        logo_url: cleanText(payload.branding_logo_url, 500),
        accent_color: accentColor.toLowerCase(),
      },
      leaderboard_finalized: sameEvent ? Boolean(this.snapshot?.leaderboard_finalized) : false,
      leaderboard_finalized_at: sameEvent ? String(this.snapshot?.leaderboard_finalized_at || "") : "",
    };
  }
}
