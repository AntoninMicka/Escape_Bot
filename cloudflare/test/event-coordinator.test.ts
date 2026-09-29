import { env, evictDurableObject, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

const authorization = { Authorization: "Bearer local-test-admin-token" };
type ProtocolMessage = { type: string; payload: Record<string, any> };

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

async function openBootstrap(clientId: string): Promise<WebSocket> {
  const response = await SELF.fetch(`https://example.test/ws?client_id=${clientId}`, {
    headers: { Upgrade: "websocket" },
  });
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

function eventConfiguration(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "Podzimní setkání",
    starts_at: "2026-10-10T09:00:00+02:00",
    ends_at: "2026-10-10T18:00:00+02:00",
    status: "ready",
    timezone: "Europe/Prague",
    primary_game_id: "hotel_kraskov",
    games: [
      {
        game_id: "hotel_kraskov",
        role: "primary",
        queue_enabled: true,
        leaderboard_enabled: true,
        weight: 1,
        start_interval_minutes: 15,
        max_active_teams: 4,
      },
      {
        game_id: "chronos_online",
        role: "side",
        queue_enabled: false,
        leaderboard_enabled: false,
      },
    ],
    branding_title: "Chronos 2026",
    branding_logo_url: "/assets/branding/mensa-cesko-logo.png",
    branding_accent_color: "#65F7FF",
    ...overrides,
  };
}

async function putEvent(eventId: string, payload: Record<string, unknown>): Promise<Response> {
  return SELF.fetch(`https://example.test/api/admin/events/${eventId}`, {
    method: "PUT",
    headers: { ...authorization, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

describe("EventCoordinator Durable Object", () => {
  it("persists an idempotent event update and rejects stale revisions", async () => {
    const unauthorized = await SELF.fetch("https://example.test/api/admin/events/autumn-2026");
    expect(unauthorized.status).toBe(401);
    expect(await unauthorized.json()).toEqual({ error: "unauthorized" });

    const missing = await SELF.fetch("https://example.test/api/admin/events/autumn-2026", {
      headers: authorization,
    });
    expect(missing.status).toBe(404);
    expect(await missing.json()).toEqual({ error: "event_not_found" });

    const created = await putEvent("autumn-2026", eventConfiguration({
      operation_id: "event-create-001",
      expected_revision: 0,
    }));
    expect(created.status).toBe(200);
    const createdPayload = await created.json<Record<string, any>>();
    expect(createdPayload).toMatchObject({
      changed: true,
      event: {
        schema_version: 2,
        id: "autumn-2026",
        revision: 1,
        name: "Podzimní setkání",
        status: "ready",
        timezone: "Europe/Prague",
        daily_windows: [{ date: "2026-10-10", enabled: true, opens_at: "08:00", closes_at: "20:00" }],
        primary_game_id: "hotel_kraskov",
        scenario_ids: ["hotel_kraskov", "chronos_online"],
        branding: { title: "Chronos 2026", accent_color: "#65f7ff" },
        leaderboard_finalized: false,
      },
    });
    expect(createdPayload.event).not.toHaveProperty("applied_operations");

    const duplicate = await putEvent("autumn-2026", eventConfiguration({
      name: "Tento název se nesmí uložit",
      operation_id: "event-create-001",
      expected_revision: 0,
    }));
    expect(await duplicate.json()).toMatchObject({
      changed: false,
      event: { revision: 1, name: "Podzimní setkání" },
    });

    const updated = await putEvent("autumn-2026", eventConfiguration({
      status: "open",
      operation_id: "event-open-002",
      expected_revision: 1,
    }));
    expect(await updated.json()).toMatchObject({
      changed: true,
      event: { revision: 2, status: "open" },
    });

    const stale = await putEvent("autumn-2026", eventConfiguration({
      operation_id: "event-stale-003",
      expected_revision: 1,
    }));
    expect(stale.status).toBe(409);
    expect(await stale.json()).toEqual({
      error: "revision_conflict",
      expected_revision: 1,
      current_revision: 2,
    });

    const concurrent = await Promise.all([
      putEvent("autumn-2026", eventConfiguration({
        status: "paused",
        operation_id: "event-concurrent-004",
        expected_revision: 2,
      })),
      putEvent("autumn-2026", eventConfiguration({
        status: "ended",
        operation_id: "event-concurrent-005",
        expected_revision: 2,
      })),
    ]);
    expect(concurrent.map((response) => response.status).sort()).toEqual([200, 409]);
    const concurrentPayloads = await Promise.all(concurrent.map((response) => response.json<Record<string, any>>()));
    expect(concurrentPayloads.find((payload) => payload.changed)?.event.revision).toBe(3);
    expect(concurrentPayloads.find((payload) => payload.error)?.current_revision).toBe(3);

    await evictDurableObject(env.EVENTS.getByName("autumn-2026"));
    const restored = await SELF.fetch("https://example.test/api/admin/events/autumn-2026", {
      headers: authorization,
    });
    expect(restored.status).toBe(200);
    expect(await restored.json()).toMatchObject({ id: "autumn-2026", revision: 3 });
  });

  it("keeps two event snapshots isolated", async () => {
    const first = await putEvent("event-alpha", eventConfiguration({
      name: "Event Alpha",
      operation_id: "alpha-create",
    }));
    const second = await putEvent("event-beta", eventConfiguration({
      name: "Event Beta",
      status: "paused",
      operation_id: "beta-create",
    }));
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);

    const [firstSnapshot, secondSnapshot] = await Promise.all([
      SELF.fetch("https://example.test/api/admin/events/event-alpha", { headers: authorization }),
      SELF.fetch("https://example.test/api/admin/events/event-beta", { headers: authorization }),
    ]);
    expect(await firstSnapshot.json()).toMatchObject({ id: "event-alpha", name: "Event Alpha", status: "ready" });
    expect(await secondSnapshot.json()).toMatchObject({ id: "event-beta", name: "Event Beta", status: "paused" });
  });

  it("rejects invalid event configuration before writing it", async () => {
    const invalid = await putEvent("invalid-event", eventConfiguration({
      operation_id: "invalid-create",
      games: [{ game_id: "missing_game", role: "primary" }],
      primary_game_id: "missing_game",
    }));
    expect(invalid.status).toBe(400);
    expect(await invalid.json()).toMatchObject({
      error: "invalid_event",
      message: "Event odkazuje na neznámou hru: missing_game.",
    });

    const missing = await SELF.fetch("https://example.test/api/admin/events/invalid-event", {
      headers: authorization,
    });
    expect(missing.status).toBe(404);
  });

  it("stores a daily schedule inside a multi-day event envelope", async () => {
    const dailyWindows = [
      { date: "2026-10-09", enabled: true, opens_at: "08:00", closes_at: "20:00" },
      { date: "2026-10-10", enabled: true, opens_at: "08:00", closes_at: "20:00" },
      { date: "2026-10-11", enabled: true, opens_at: "08:00", closes_at: "20:00" },
    ];
    const created = await putEvent("weekend-event", eventConfiguration({
      starts_at: "2026-10-09T15:00:00+02:00",
      ends_at: "2026-10-11T12:00:00+02:00",
      daily_windows: dailyWindows,
      operation_id: "weekend-create",
    }));
    expect(created.status).toBe(200);
    expect(await created.json()).toMatchObject({
      event: {
        schema_version: 2,
        starts_at: "2026-10-09T13:00:00.000Z",
        ends_at: "2026-10-11T10:00:00.000Z",
        daily_windows: dailyWindows,
      },
    });

    const missingDay = await putEvent("missing-day-event", eventConfiguration({
      starts_at: "2026-10-09T15:00:00+02:00",
      ends_at: "2026-10-11T12:00:00+02:00",
      daily_windows: dailyWindows.slice(0, 2),
      operation_id: "missing-day-create",
    }));
    expect(missingDay.status).toBe(400);
    expect(await missingDay.json()).toMatchObject({
      error: "invalid_event",
      message: "Chybí denní limit pro 2026-10-11.",
    });

    const invalidHours = await putEvent("invalid-hours-event", eventConfiguration({
      daily_windows: [{ date: "2026-10-10", enabled: true, opens_at: "20:00", closes_at: "08:00" }],
      operation_id: "invalid-hours-create",
    }));
    expect(invalidHours.status).toBe(400);
    expect(await invalidHours.json()).toMatchObject({
      error: "invalid_event",
      message: "Denní limit pro 2026-10-10 musí končit po svém začátku.",
    });
  });

  it("activates an event for bootstrap clients and restores the selection after eviction", async () => {
    const reset = await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    });
    expect(reset.status).toBe(200);
    await reset.json();
    const observer = await openBootstrap("event-observer");
    expect((await nextMessage(observer, "runtime.settings")).payload.event).toEqual({});

    const update = nextMessage(observer, "runtime.settings");
    const created = await putEvent("live-event", eventConfiguration({
      name: "Živý event",
      operation_id: "live-event-create",
    }));
    expect(created.status).toBe(200);
    await created.json();
    const settings = (await update).payload;
    expect(settings.event).toMatchObject({ id: "live-event", name: "Živý event", revision: 1 });
    expect(settings.games.map((game: Record<string, unknown>) => game.id)).toEqual([
      "hotel_kraskov",
      "chronos_online",
    ]);
    expect(settings.games[0]).toMatchObject({
      id: "hotel_kraskov",
      event_role: "primary",
      queue_enabled: true,
      leaderboard_enabled: true,
    });

    const active = await SELF.fetch("https://example.test/api/admin/events/active", {
      headers: authorization,
    });
    expect(await active.json()).toMatchObject({
      active_event_id: "live-event",
      event: { id: "live-event", revision: 1 },
    });

    await closeSocket(observer);
    await evictDurableObject(env.GAME_SESSIONS.getByName("__escape_bot_lobby_directory__"));
    const restoredObserver = await openBootstrap("restored-event-observer");
    expect((await nextMessage(restoredObserver, "runtime.settings")).payload.event).toMatchObject({
      id: "live-event",
      revision: 1,
    });

    const clearedSettings = nextMessage(restoredObserver, "runtime.settings");
    const cleared = await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    });
    expect(cleared.status).toBe(200);
    expect(await cleared.json()).toMatchObject({ changed: true, active_event_id: "", event: {} });
    const clearedPayload = (await clearedSettings).payload;
    expect(clearedPayload.event).toEqual({});
    expect(clearedPayload.games).toHaveLength(4);
    await closeSocket(restoredObserver);
  });
});
