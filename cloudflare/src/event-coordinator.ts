import { DurableObject } from "cloudflare:workers";

interface EventCoordinatorEnv {
  ASSETS: Fetcher;
}

type EventStatus = "draft" | "ready" | "open" | "paused" | "ended" | "archived";
type EventGameRole = "primary" | "competitive" | "side";
type EventLaunchMode = "free" | "managed";
type AnnouncementPriority = "emergency" | "high" | "normal" | "low";
type AnnouncementCategory = "organization" | "lost_found" | "refreshment" | "results" | "important";

interface EventGameConfiguration {
  game_id: string;
  role: EventGameRole;
  queue_enabled: boolean;
  leaderboard_enabled: boolean;
  weight: number;
  start_interval_minutes: number;
  max_active_teams: number;
}

export interface EventDailyWindow {
  date: string;
  enabled: boolean;
  opens_at: string;
  closes_at: string;
}

export interface EventAnnouncement {
  id: string;
  text: string;
  priority: AnnouncementPriority;
  category: AnnouncementCategory;
  published: boolean;
  starts_at: string;
  ends_at: string;
  link_url: string;
  link_label: string;
  override_minutes: number;
  override_until: string;
  fallback_priority: Exclude<AnnouncementPriority, "emergency">;
  event_id: string;
  game_id: string;
}

export interface EventRuntimeSettings {
  gameplay_enabled: boolean;
  launch_mode: EventLaunchMode;
  display_leaderboard: boolean;
  display_announcements: EventAnnouncement[];
}

export interface EventResult {
  entry_id: string;
  operation_id: string;
  session_id: string;
  scenario_id: string;
  name: string;
  players: string[];
  mode: "solo" | "team";
  score: number;
  duration_seconds: number | null;
  completed_at: string;
  finalized_at: string;
  administrative: boolean;
  out_of_competition: boolean;
  diploma_eligible: boolean;
}

export interface EventSnapshot {
  schema_version: 4;
  id: string;
  revision: number;
  name: string;
  starts_at: string;
  ends_at: string;
  status: EventStatus;
  timezone: string;
  daily_windows: EventDailyWindow[];
  primary_game_id: string;
  games: EventGameConfiguration[];
  scenario_ids: string[];
  branding: {
    title: string;
    logo_url: string;
    accent_color: string;
  };
  runtime: EventRuntimeSettings;
  leaderboard_finalized: boolean;
  leaderboard_finalized_at: string;
  results: Record<string, EventResult>;
  created_at: string;
  updated_at: string;
}

export interface EventStartAvailability {
  start_allowed: boolean;
  reason: string;
  operating_hours_applied: true;
  opening_at: string;
  closing_at: string;
  latest_start_at: string;
  game_duration_minutes: number;
}

interface StoredEventSnapshot extends EventSnapshot {
  applied_operations: string[];
}

const EVENT_SNAPSHOT_KEY = "event-snapshot";
export const EVENT_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const OPERATION_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const EVENT_STATUSES = new Set<EventStatus>(["draft", "ready", "open", "paused", "ended", "archived"]);
const EVENT_GAME_ROLES = new Set<EventGameRole>(["primary", "competitive", "side"]);
const ANNOUNCEMENT_PRIORITIES = new Set<AnnouncementPriority>(["emergency", "high", "normal", "low"]);
const ANNOUNCEMENT_CATEGORIES = new Set<AnnouncementCategory>(["organization", "lost_found", "refreshment", "results", "important"]);
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const MAX_EVENT_DAYS = 370;

function defaultRuntimeSettings(): EventRuntimeSettings {
  return {
    gameplay_enabled: true,
    launch_mode: "free",
    display_leaderboard: true,
    display_announcements: [],
  };
}

function optionalTimestamp(value: unknown, label: string, timezone: string): string {
  const timestamp = String(value ?? "").trim();
  if (!timestamp) return "";
  const local = timestamp.match(/^(\d{4}-\d{2}-\d{2})T((?:[01]\d|2[0-3]):[0-5]\d)$/);
  if (local) return new Date(zonedLocalTimestamp(local[1], local[2], timezone)).toISOString();
  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) throw new Error(`${label} musí být platný čas.`);
  return new Date(parsed).toISOString();
}

function normalizeAnnouncements(value: unknown, event: EventSnapshot): EventAnnouncement[] {
  if (!Array.isArray(value)) throw new Error("Oznámení musí být seznam položek.");
  if (value.length > 20) throw new Error("Lze uložit nejvýše 20 oznámení.");
  return value.map((rawValue) => {
    const raw = rawValue && typeof rawValue === "object" && !Array.isArray(rawValue)
      ? rawValue as Record<string, unknown>
      : {};
    const text = String(raw.text ?? "").trim().slice(0, 501);
    if (!text || text.length > 500) throw new Error("Každé oznámení musí obsahovat nejvýše 500 znaků.");
    const priority = cleanText(raw.priority || "normal", 16) as AnnouncementPriority;
    if (!ANNOUNCEMENT_PRIORITIES.has(priority)) throw new Error("Oznámení má neplatnou prioritu.");
    const category = cleanText(raw.category || "organization", 32) as AnnouncementCategory;
    if (!ANNOUNCEMENT_CATEGORIES.has(category)) throw new Error("Oznámení má neplatnou kategorii.");
    const fallback = cleanText(raw.fallback_priority || "high", 16) as Exclude<AnnouncementPriority, "emergency">;
    if (!new Set(["high", "normal", "low"]).has(fallback)) throw new Error("Náhradní priorita oznámení není platná.");
    const eventId = cleanText(raw.event_id, 64);
    const gameId = cleanText(raw.game_id, 64);
    if (gameId && !eventId) throw new Error("Oznámení konkrétní hry musí patřit eventu.");
    if (eventId && eventId !== event.id) throw new Error("Oznámení odkazuje na jiný než aktivní event.");
    if (gameId && !event.scenario_ids.includes(gameId)) throw new Error("Oznámení odkazuje na hru mimo aktivní event.");
    const linkUrl = String(raw.link_url ?? "").trim().slice(0, 501);
    if (linkUrl.length > 500 || (linkUrl && !/^(?:https?:\/\/|\/)/i.test(linkUrl))) {
      throw new Error("Odkaz oznámení musí být bezpečná HTTP(S) nebo lokální adresa.");
    }
    const linkLabel = String(raw.link_label || "Více informací").trim().slice(0, 81);
    if (linkLabel.length > 80) throw new Error("Text odkazu oznámení je příliš dlouhý.");
    const overrideMinutes = boundedNumber(raw.override_minutes, 0, 0, 1440);
    let overrideUntil = optionalTimestamp(raw.override_until, "Konec nouzového překrytí", event.timezone);
    if (priority === "emergency" && overrideMinutes && !overrideUntil) {
      overrideUntil = new Date(Date.now() + overrideMinutes * 60_000).toISOString();
    }
    if (priority !== "emergency") overrideUntil = "";
    const startsAt = optionalTimestamp(raw.starts_at, "Začátek oznámení", event.timezone);
    const endsAt = optionalTimestamp(raw.ends_at, "Konec oznámení", event.timezone);
    if (startsAt && endsAt && Date.parse(startsAt) >= Date.parse(endsAt)) {
      throw new Error("Konec oznámení musí následovat po jeho začátku.");
    }
    return {
      id: cleanText(raw.id, 64) || crypto.randomUUID(),
      text,
      priority,
      category,
      published: raw.published !== false,
      starts_at: startsAt,
      ends_at: endsAt,
      link_url: linkUrl,
      link_label: linkLabel || "Více informací",
      override_minutes: overrideMinutes,
      override_until: overrideUntil,
      fallback_priority: fallback,
      event_id: eventId,
      game_id: gameId,
    };
  });
}

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

function dateInTimezone(timestamp: string, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(timestamp));
  const values = new Map(parts.map((part) => [part.type, part.value]));
  return `${values.get("year")}-${values.get("month")}-${values.get("day")}`;
}

function localParts(timestamp: string, timezone: string): Record<string, string> {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(timestamp));
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

function zonedLocalTimestamp(date: string, time: string, timezone: string): number {
  const desired = Date.parse(`${date}T${time}:00Z`);
  let candidate = desired;
  for (let iteration = 0; iteration < 4; iteration += 1) {
    const parts = localParts(new Date(candidate).toISOString(), timezone);
    const represented = Date.UTC(
      Number(parts.year),
      Number(parts.month) - 1,
      Number(parts.day),
      Number(parts.hour),
      Number(parts.minute),
      Number(parts.second),
    );
    const adjustment = desired - represented;
    candidate += adjustment;
    if (adjustment === 0) break;
  }
  const verified = localParts(new Date(candidate).toISOString(), timezone);
  if (`${verified.year}-${verified.month}-${verified.day}` !== date || `${verified.hour}:${verified.minute}` !== time) {
    throw new Error(`Čas ${date} ${time} v zóně ${timezone} neexistuje.`);
  }
  return candidate;
}

export function eventStartAvailability(
  event: EventSnapshot,
  nowValue: string | number | Date,
  gameDurationMinutes: number,
): EventStartAvailability {
  const now = new Date(nowValue).valueOf();
  const duration = Math.max(0, Math.round(gameDurationMinutes));
  const fallbackTime = Number.isFinite(now) ? new Date(now).toISOString() : event.starts_at;
  const fallback: EventStartAvailability = {
    start_allowed: false,
    reason: "Čas eventu nelze vyhodnotit.",
    operating_hours_applied: true,
    opening_at: fallbackTime,
    closing_at: fallbackTime,
    latest_start_at: fallbackTime,
    game_duration_minutes: duration,
  };
  if (!Number.isFinite(now)) return fallback;
  const eventStart = Date.parse(event.starts_at);
  const eventEnd = Date.parse(event.ends_at);
  if (!event.runtime.gameplay_enabled) {
    return { ...fallback, start_allowed: false, reason: "Herní provoz je zastaven správcem." };
  }
  if (event.status !== "open") {
    return { ...fallback, start_allowed: false, reason: `Event není otevřený (stav: ${event.status}).` };
  }
  if (now < eventStart) return { ...fallback, start_allowed: false, reason: "Event ještě nezačal." };
  if (now >= eventEnd) return { ...fallback, start_allowed: false, reason: "Event už skončil." };
  const localDate = dateInTimezone(new Date(now).toISOString(), event.timezone);
  const window = event.daily_windows.find((item) => item.date === localDate);
  if (!window) {
    return { ...fallback, reason: "Pro dnešní den není nastavené provozní okno." };
  }
  let dailyOpen: number;
  let dailyClose: number;
  try {
    dailyOpen = zonedLocalTimestamp(window.date, window.opens_at, event.timezone);
    dailyClose = zonedLocalTimestamp(window.date, window.closes_at, event.timezone);
  } catch (error) {
    return { ...fallback, reason: error instanceof Error ? error.message : fallback.reason };
  }
  const opening = Math.max(eventStart, dailyOpen);
  const closing = Math.min(eventEnd, dailyClose);
  const latestStart = Math.max(opening, closing - duration * 60_000);
  const base = {
    operating_hours_applied: true as const,
    opening_at: new Date(opening).toISOString(),
    closing_at: new Date(closing).toISOString(),
    latest_start_at: new Date(latestStart).toISOString(),
    game_duration_minutes: duration,
  };
  if (!window.enabled) return { ...base, start_allowed: false, reason: "Hra je pro dnešní den vypnutá." };
  if (now < opening) return { ...base, start_allowed: false, reason: "Dnešní provozní doba ještě nezačala." };
  if (now >= closing) return { ...base, start_allowed: false, reason: "Dnešní provozní doba už skončila." };
  if (now + duration * 60_000 > closing) {
    return { ...base, start_allowed: false, reason: "Na dokončení hry před koncem provozu už nezbývá dost času." };
  }
  return { ...base, start_allowed: true, reason: "Start je v provozním okně eventu povolen." };
}

function eventDates(startsAt: string, endsAt: string, timezone: string): string[] {
  const firstDate = dateInTimezone(startsAt, timezone);
  const lastDate = dateInTimezone(new Date(Date.parse(endsAt) - 1).toISOString(), timezone);
  const current = new Date(`${firstDate}T00:00:00Z`);
  const last = new Date(`${lastDate}T00:00:00Z`);
  if (!DATE_PATTERN.test(firstDate) || !DATE_PATTERN.test(lastDate) || current > last) {
    throw new Error("Kalendářní rozsah eventu není platný.");
  }
  const dates: string[] = [];
  while (current <= last) {
    if (dates.length >= MAX_EVENT_DAYS) {
      throw new Error(`Event může pokrývat nejvýše ${MAX_EVENT_DAYS} kalendářních dnů.`);
    }
    dates.push(current.toISOString().slice(0, 10));
    current.setUTCDate(current.getUTCDate() + 1);
  }
  return dates;
}

function defaultDailyWindows(startsAt: string, endsAt: string, timezone: string): EventDailyWindow[] {
  return eventDates(startsAt, endsAt, timezone).map((date) => ({
    date,
    enabled: true,
    opens_at: "08:00",
    closes_at: "20:00",
  }));
}

function normalizeDailyWindows(
  value: unknown,
  startsAt: string,
  endsAt: string,
  timezone: string,
): EventDailyWindow[] {
  const dates = eventDates(startsAt, endsAt, timezone);
  if (value === undefined) return defaultDailyWindows(startsAt, endsAt, timezone);
  if (!Array.isArray(value)) throw new Error("Denní limity eventu musí být seznam.");
  const expectedDates = new Set(dates);
  const supplied = new Map<string, EventDailyWindow>();
  for (const rawValue of value) {
    const raw = rawValue && typeof rawValue === "object" && !Array.isArray(rawValue)
      ? rawValue as Record<string, unknown>
      : {};
    const date = cleanText(raw.date, 10);
    const opensAt = cleanText(raw.opens_at, 5);
    const closesAt = cleanText(raw.closes_at, 5);
    if (!DATE_PATTERN.test(date) || !expectedDates.has(date)) {
      throw new Error(`Denní limit ${date || "bez data"} neleží v obálce eventu.`);
    }
    if (supplied.has(date)) throw new Error(`Denní limit pro ${date} je uveden vícekrát.`);
    if (!TIME_PATTERN.test(opensAt) || !TIME_PATTERN.test(closesAt)) {
      throw new Error(`Denní limit pro ${date} musí obsahovat platné časy HH:MM.`);
    }
    if (opensAt >= closesAt) throw new Error(`Denní limit pro ${date} musí končit po svém začátku.`);
    supplied.set(date, { date, enabled: raw.enabled !== false, opens_at: opensAt, closes_at: closesAt });
  }
  const missingDate = dates.find((date) => !supplied.has(date));
  if (missingDate) throw new Error(`Chybí denní limit pro ${missingDate}.`);
  return dates.map((date) => supplied.get(date)!);
}

function publicSnapshot(snapshot: StoredEventSnapshot): EventSnapshot {
  const { applied_operations: _operations, ...event } = snapshot;
  return event;
}

function leaderboardEntries(snapshot: StoredEventSnapshot): Array<Record<string, unknown>> {
  const configurations = new Map(snapshot.games.map((game) => [game.game_id, game]));
  return Object.values(snapshot.results)
    .map((result) => {
      const configuration = configurations.get(result.scenario_id);
      const { operation_id: _operationId, ...publicResult } = result;
      return {
        ...publicResult,
        event_id: snapshot.id,
        event_name: snapshot.name,
        game_title: result.scenario_id,
        competition_role: configuration?.role ?? "competitive",
        leaderboard_enabled: configuration?.leaderboard_enabled ?? true,
        competition_weight: configuration?.weight ?? 1,
      };
    })
    .sort((left, right) => Number(right.score) - Number(left.score) || String(left.completed_at).localeCompare(String(right.completed_at)));
}

export class EventCoordinator extends DurableObject<EventCoordinatorEnv> {
  private snapshot: StoredEventSnapshot | null = null;
  private updateQueue: Promise<void> = Promise.resolve();

  constructor(ctx: DurableObjectState, env: EventCoordinatorEnv) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      const stored = await ctx.storage.get<StoredEventSnapshot>(EVENT_SNAPSHOT_KEY);
      if (!stored) {
        this.snapshot = null;
        return;
      }
      let dailyWindows = stored.daily_windows;
      if (!Array.isArray(dailyWindows)) {
        try {
          dailyWindows = defaultDailyWindows(stored.starts_at, stored.ends_at, validTimezone(stored.timezone));
        } catch {
          dailyWindows = [];
        }
      }
      this.snapshot = {
        ...stored,
        schema_version: 4,
        daily_windows: dailyWindows,
        runtime: { ...defaultRuntimeSettings(), ...(stored.runtime ?? {}) },
        results: stored.results && typeof stored.results === "object" ? stored.results : {},
      };
    });
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("X-EscapeBot-Internal-Admin") !== "1") {
      return json({ error: "not_found" }, 404);
    }
    const url = new URL(request.url);
    if (url.pathname === "/internal/event/connect" && request.headers.get("Upgrade")?.toLowerCase() === "websocket") {
      if (!this.snapshot) return json({ error: "event_not_found" }, 404);
      const pair = new WebSocketPair();
      pair[1].serializeAttachment({ role: "event" });
      this.ctx.acceptWebSocket(pair[1]);
      this.sendEventSnapshot(pair[1]);
      return new Response(null, { status: 101, webSocket: pair[0] });
    }
    if (url.pathname === "/internal/event" && request.method === "GET") {
      return this.snapshot
        ? json(publicSnapshot(this.snapshot))
        : json({ error: "event_not_found" }, 404);
    }
    if (url.pathname === "/internal/event/leaderboard" && request.method === "GET") {
      return this.snapshot
        ? json({ entries: leaderboardEntries(this.snapshot), finalized: this.snapshot.leaderboard_finalized })
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
    if (url.pathname === "/internal/event/runtime" && request.method === "PATCH") {
      let payload: Record<string, unknown>;
      try {
        payload = await request.json<Record<string, unknown>>();
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      return this.serializeUpdate(() => this.updateRuntime(payload));
    }
    if (url.pathname === "/internal/event/result" && request.method === "POST") {
      let payload: Record<string, unknown>;
      try {
        payload = await request.json<Record<string, unknown>>();
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      return this.serializeUpdate(() => this.finalizeResult(payload));
    }
    if (url.pathname === "/internal/event/leaderboard-finalize" && request.method === "POST") {
      let payload: Record<string, unknown>;
      try {
        payload = await request.json<Record<string, unknown>>();
      } catch {
        return json({ error: "invalid_json" }, 400);
      }
      return this.serializeUpdate(() => this.finalizeLeaderboard(payload));
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
      schema_version: 4,
      revision: (this.snapshot?.revision ?? 0) + 1,
      created_at: this.snapshot?.created_at ?? now,
      updated_at: now,
      ...normalized,
      applied_operations: [...(this.snapshot?.applied_operations ?? []), operationId].slice(-500),
    };
    await this.ctx.storage.put(EVENT_SNAPSHOT_KEY, this.snapshot);
    this.broadcastEvent("runtime.settings", this.eventRuntimePayload());
    return json({ changed: true, event: publicSnapshot(this.snapshot) });
  }

  private async updateRuntime(payload: Record<string, unknown>): Promise<Response> {
    if (!this.snapshot) return json({ error: "event_not_found" }, 404);
    const operationId = cleanText(payload.operation_id, 128);
    if (!OPERATION_ID_PATTERN.test(operationId)) return json({ error: "invalid_operation_id" }, 400);
    if (this.snapshot.applied_operations.includes(operationId)) {
      return json({ changed: false, event: publicSnapshot(this.snapshot) });
    }
    const expectedRevision = payload.expected_revision;
    if (
      expectedRevision !== undefined &&
      (!Number.isInteger(expectedRevision) || Number(expectedRevision) !== this.snapshot.revision)
    ) {
      return json({
        error: "revision_conflict",
        expected_revision: expectedRevision,
        current_revision: this.snapshot.revision,
      }, 409);
    }
    const supplied = payload.runtime && typeof payload.runtime === "object" && !Array.isArray(payload.runtime)
      ? payload.runtime as Record<string, unknown>
      : payload;
    const runtime = { ...this.snapshot.runtime };
    try {
      if (Object.hasOwn(supplied, "gameplay_enabled")) {
        if (typeof supplied.gameplay_enabled !== "boolean") throw new Error("Stav herního provozu musí být ano/ne.");
        runtime.gameplay_enabled = supplied.gameplay_enabled;
      }
      if (Object.hasOwn(supplied, "display_leaderboard")) {
        if (typeof supplied.display_leaderboard !== "boolean") throw new Error("Viditelnost žebříčku musí být ano/ne.");
        runtime.display_leaderboard = supplied.display_leaderboard;
      }
      if (Object.hasOwn(supplied, "launch_mode")) {
        const launchMode = cleanText(supplied.launch_mode, 16) as EventLaunchMode;
        if (!new Set<EventLaunchMode>(["free", "managed"]).has(launchMode)) {
          throw new Error("Neznámý režim spouštění.");
        }
        runtime.launch_mode = launchMode;
      }
      if (Object.hasOwn(supplied, "display_announcements")) {
        runtime.display_announcements = normalizeAnnouncements(supplied.display_announcements, this.snapshot);
      }
    } catch (error) {
      return json({ error: "invalid_runtime_settings", message: error instanceof Error ? error.message : "Runtime nastavení není platné." }, 400);
    }
    const changed = JSON.stringify(runtime) !== JSON.stringify(this.snapshot.runtime);
    this.snapshot = {
      ...this.snapshot,
      revision: changed ? this.snapshot.revision + 1 : this.snapshot.revision,
      updated_at: changed ? new Date().toISOString() : this.snapshot.updated_at,
      runtime,
      applied_operations: [...this.snapshot.applied_operations, operationId].slice(-500),
    };
    await this.ctx.storage.put(EVENT_SNAPSHOT_KEY, this.snapshot);
    this.broadcastEvent("runtime.settings", this.eventRuntimePayload());
    return json({ changed, event: publicSnapshot(this.snapshot) });
  }

  private eventRuntimePayload(): Record<string, unknown> {
    if (!this.snapshot) return {};
    const { results: _results, ...event } = publicSnapshot(this.snapshot);
    return {
      ...this.snapshot.runtime,
      event,
      leaderboard_finalized: this.snapshot.leaderboard_finalized,
    };
  }

  private sendEventSnapshot(socket: WebSocket): void {
    if (!this.snapshot) return;
    socket.send(JSON.stringify({ type: "runtime.settings", payload: this.eventRuntimePayload() }));
    socket.send(JSON.stringify({ type: "leaderboard.update", payload: { entries: leaderboardEntries(this.snapshot) } }));
  }

  private broadcastEvent(type: string, payload: Record<string, unknown>): void {
    const encoded = JSON.stringify({ type, payload });
    for (const socket of this.ctx.getWebSockets()) {
      if (socket.readyState !== WebSocket.OPEN) continue;
      try {
        socket.send(encoded);
      } catch {
        socket.close(1011, "Event broadcast failed");
      }
    }
  }

  private async finalizeResult(payload: Record<string, unknown>): Promise<Response> {
    if (!this.snapshot) return json({ error: "event_not_found" }, 404);
    const operationId = cleanText(payload.operation_id, 128);
    const sessionId = cleanText(payload.session_id, 128);
    const scenarioId = cleanText(payload.scenario_id, 64);
    if (!OPERATION_ID_PATTERN.test(operationId)) return json({ error: "invalid_operation_id" }, 400);
    if (!/^[A-Za-z0-9_-]{8,128}$/.test(sessionId)) return json({ error: "invalid_session_id" }, 400);
    const operationResult = Object.values(this.snapshot.results).find((result) => result.operation_id === operationId);
    if (operationResult) {
      return operationResult.session_id === sessionId
        ? json({ changed: false, result: operationResult, leaderboard: leaderboardEntries(this.snapshot) })
        : json({ error: "operation_id_conflict" }, 409);
    }
    if (!this.snapshot.games.some((game) => game.game_id === scenarioId)) {
      return json({ error: "game_not_in_event" }, 409);
    }
    const existing = this.snapshot.results[sessionId];
    if (existing) {
      return existing.operation_id === operationId
        ? json({ changed: false, result: existing, leaderboard: leaderboardEntries(this.snapshot) })
        : json({ error: "result_already_finalized", result: existing }, 409);
    }
    if (this.snapshot.leaderboard_finalized) return json({ error: "leaderboard_finalized" }, 409);
    const score = Number(payload.score);
    if (!Number.isFinite(score)) return json({ error: "invalid_score" }, 400);
    let completedAt: string;
    try {
      completedAt = optionalTimestamp(payload.completed_at, "Čas dokončení", this.snapshot.timezone)
        || new Date().toISOString();
    } catch (error) {
      return json({ error: "invalid_result", message: error instanceof Error ? error.message : "Výsledek není platný." }, 400);
    }
    const finalizedAt = new Date().toISOString();
    const startedAtValue = String(payload.started_at || "").trim();
    const startedAt = startedAtValue ? Date.parse(startedAtValue) : Number.NaN;
    const completedAtMs = Date.parse(completedAt);
    const result: EventResult = {
      entry_id: `result-${sessionId}`,
      operation_id: operationId,
      session_id: sessionId,
      scenario_id: scenarioId,
      name: cleanText(payload.name, 64) || sessionId,
      players: Array.isArray(payload.players)
        ? payload.players.map((name) => cleanText(name, 64)).filter(Boolean).slice(0, 32)
        : [],
      mode: payload.mode === "solo" ? "solo" : "team",
      score: Math.round(score),
      duration_seconds: Number.isFinite(startedAt) && completedAtMs >= startedAt
        ? Math.round((completedAtMs - startedAt) / 1000)
        : null,
      completed_at: completedAt,
      finalized_at: finalizedAt,
      administrative: payload.administrative === true,
      out_of_competition: payload.out_of_competition === true,
      diploma_eligible: payload.diploma_eligible !== false,
    };
    this.snapshot = {
      ...this.snapshot,
      revision: this.snapshot.revision + 1,
      updated_at: finalizedAt,
      results: { ...this.snapshot.results, [sessionId]: result },
      applied_operations: [...this.snapshot.applied_operations, operationId].slice(-500),
    };
    await this.ctx.storage.put(EVENT_SNAPSHOT_KEY, this.snapshot);
    const leaderboard = leaderboardEntries(this.snapshot);
    this.broadcastEvent("leaderboard.update", { entries: leaderboard });
    return json({ changed: true, result, leaderboard });
  }

  private async finalizeLeaderboard(payload: Record<string, unknown>): Promise<Response> {
    if (!this.snapshot) return json({ error: "event_not_found" }, 404);
    const operationId = cleanText(payload.operation_id, 128);
    if (!OPERATION_ID_PATTERN.test(operationId)) return json({ error: "invalid_operation_id" }, 400);
    if (this.snapshot.applied_operations.includes(operationId) || this.snapshot.leaderboard_finalized) {
      return json({ changed: false, event: publicSnapshot(this.snapshot), leaderboard: leaderboardEntries(this.snapshot) });
    }
    const now = new Date().toISOString();
    this.snapshot = {
      ...this.snapshot,
      revision: this.snapshot.revision + 1,
      updated_at: now,
      leaderboard_finalized: true,
      leaderboard_finalized_at: now,
      applied_operations: [...this.snapshot.applied_operations, operationId].slice(-500),
    };
    await this.ctx.storage.put(EVENT_SNAPSHOT_KEY, this.snapshot);
    this.broadcastEvent("runtime.settings", this.eventRuntimePayload());
    return json({ changed: true, event: publicSnapshot(this.snapshot), leaderboard: leaderboardEntries(this.snapshot) });
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
    const timezone = validTimezone(payload.timezone);
    const dailyWindows = normalizeDailyWindows(payload.daily_windows, startsAt, endsAt, timezone);
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
      timezone,
      daily_windows: dailyWindows,
      primary_game_id: primaryGames[0].game_id,
      games,
      scenario_ids: games.map((game) => game.game_id),
      branding: {
        title: cleanText(payload.branding_title, 120),
        logo_url: cleanText(payload.branding_logo_url, 500),
        accent_color: accentColor.toLowerCase(),
      },
      runtime: sameEvent ? this.snapshot!.runtime : defaultRuntimeSettings(),
      leaderboard_finalized: sameEvent ? Boolean(this.snapshot?.leaderboard_finalized) : false,
      leaderboard_finalized_at: sameEvent ? String(this.snapshot?.leaderboard_finalized_at || "") : "",
      results: sameEvent ? { ...(this.snapshot?.results ?? {}) } : {},
    };
  }
}
