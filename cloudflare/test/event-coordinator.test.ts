import { env, evictDurableObject, runDurableObjectAlarm, runInDurableObject, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { eventStartAvailability, type EventSnapshot } from "../src/event-coordinator";

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

async function openSession(sessionId: string, clientId: string): Promise<WebSocket> {
  const response = await env.GAME_SESSIONS.getByName(sessionId).fetch(
    `https://example.test/ws?session_id=${sessionId}&client_id=${clientId}`,
    { headers: { Upgrade: "websocket", "X-EscapeBot-Session-Id": sessionId } },
  );
  expect(response.status).toBe(101);
  const socket = response.webSocket;
  if (!socket) throw new Error("WebSocket response is missing a socket");
  socket.accept();
  await nextMessage(socket, "session.connected");
  return socket;
}

async function openEventChannel(eventId: string): Promise<WebSocket> {
  const response = await SELF.fetch(`https://example.test/ws?channel=event&event_id=${encodeURIComponent(eventId)}`, {
    headers: { Upgrade: "websocket" },
  });
  expect(response.status).toBe(101);
  const socket = response.webSocket;
  if (!socket) throw new Error("Event WebSocket response is missing a socket");
  socket.accept();
  return socket;
}

function closeSocket(socket: WebSocket): Promise<void> {
  if (socket.readyState === WebSocket.CLOSED) return Promise.resolve();
  return new Promise((resolve) => {
    const timeout = setTimeout(resolve, 250);
    socket.addEventListener("close", () => {
      clearTimeout(timeout);
      resolve();
    }, { once: true });
    socket.close(1000, "done");
  });
}

function dateInZone(value: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const values = new Map(parts.map((part) => [part.type, part.value]));
  return `${values.get("year")}-${values.get("month")}-${values.get("day")}`;
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

async function patchActiveRuntime(payload: Record<string, unknown>): Promise<Response> {
  return SELF.fetch("https://example.test/api/admin/events/active/runtime", {
    method: "PATCH",
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
        schema_version: 4,
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
        runtime: {
          gameplay_enabled: true,
          launch_mode: "free",
          display_leaderboard: true,
          display_announcements: [],
        },
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

  it("upgrades a stored schema v2 event with safe runtime defaults", async () => {
    const eventId = "legacy-runtime-event";
    const created = await putEvent(eventId, eventConfiguration({ operation_id: "legacy-runtime-create", activate: false }));
    expect(created.status).toBe(200);
    await created.json();
    const stub = env.EVENTS.getByName(eventId);
    await runInDurableObject(stub, async (_instance, state) => {
      const stored = await state.storage.get<Record<string, any>>("event-snapshot");
      expect(stored).toBeDefined();
      delete stored!.runtime;
      stored!.schema_version = 3;
      await state.storage.put("event-snapshot", stored);
    });
    await evictDurableObject(stub);
    const restored = await SELF.fetch(`https://example.test/api/admin/events/${eventId}`, { headers: authorization });
    expect(restored.status).toBe(200);
    expect(await restored.json()).toMatchObject({
      schema_version: 4,
      runtime: {
        gameplay_enabled: true,
        launch_mode: "free",
        display_leaderboard: true,
        display_announcements: [],
      },
    });
  });

  it("persists event runtime controls and broadcasts validated announcements", async () => {
    await (await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    })).json();
    const observer = await openBootstrap("runtime-controls-observer");
    await nextMessage(observer, "runtime.settings");
    const activated = nextMessage(observer, "runtime.settings");
    const created = await putEvent("runtime-controls-event", eventConfiguration({
      operation_id: "runtime-controls-create",
    }));
    expect(created.status).toBe(200);
    await created.json();
    await activated;

    const update = nextMessage(observer, "runtime.settings");
    const patched = await patchActiveRuntime({
      operation_id: "runtime-controls-patch",
      expected_revision: 1,
      runtime: {
        launch_mode: "managed",
        display_leaderboard: false,
        display_announcements: [{
          text: "Registrace týmů končí v 17:30.",
          priority: "high",
          category: "organization",
          published: true,
          event_id: "runtime-controls-event",
          starts_at: "2026-10-10T12:00",
          ends_at: "2026-10-10T13:00",
          link_url: "/pravidla",
          link_label: "Pravidla",
        }],
      },
    });
    expect(patched.status).toBe(200);
    const patchedPayload = await patched.json<Record<string, any>>();
    expect(patchedPayload).toMatchObject({
      changed: true,
      event: {
        revision: 2,
        runtime: {
          gameplay_enabled: true,
          launch_mode: "managed",
          display_leaderboard: false,
          display_announcements: [expect.objectContaining({
            text: "Registrace týmů končí v 17:30.",
            priority: "high",
            event_id: "runtime-controls-event",
            starts_at: "2026-10-10T10:00:00.000Z",
            ends_at: "2026-10-10T11:00:00.000Z",
            link_url: "/pravidla",
          })],
        },
      },
    });
    expect((await update).payload).toMatchObject({
      gameplay_enabled: true,
      launch_mode: "managed",
      display_leaderboard: false,
      display_announcements: [expect.objectContaining({ text: "Registrace týmů končí v 17:30." })],
    });

    const invalid = await patchActiveRuntime({
      operation_id: "runtime-controls-invalid-link",
      expected_revision: 2,
      runtime: { display_announcements: [{ text: "Nebezpečný odkaz", link_url: "javascript:alert(1)" }] },
    });
    expect(invalid.status).toBe(400);
    expect(await invalid.json()).toMatchObject({ error: "invalid_runtime_settings" });

    const invalidBoolean = await patchActiveRuntime({
      operation_id: "runtime-controls-invalid-boolean",
      expected_revision: 2,
      runtime: { display_leaderboard: "false" },
    });
    expect(invalidBoolean.status).toBe(400);
    expect(await invalidBoolean.json()).toMatchObject({ error: "invalid_runtime_settings" });

    await closeSocket(observer);
    await evictDurableObject(env.EVENTS.getByName("runtime-controls-event"));
    await evictDurableObject(env.GAME_SESSIONS.getByName("__escape_bot_lobby_directory__"));
    const restored = await openBootstrap("runtime-controls-restored");
    expect((await nextMessage(restored, "runtime.settings")).payload).toMatchObject({
      launch_mode: "managed",
      display_leaderboard: false,
      display_announcements: [expect.objectContaining({ text: "Registrace týmů končí v 17:30." })],
    });
    await closeSocket(restored);
    await (await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    })).json();
  });

  it("finalizes each session result once and broadcasts it on the event channel", async () => {
    const created = await putEvent("result-event", eventConfiguration({
      operation_id: "result-event-create",
    }));
    expect(created.status).toBe(200);
    await created.json();
    const channel = await openEventChannel("result-event");
    expect((await nextMessage(channel, "runtime.settings")).payload.event.id).toBe("result-event");
    expect((await nextMessage(channel, "leaderboard.update")).payload.entries).toEqual([]);

    const update = nextMessage(channel, "leaderboard.update");
    const resultStub = env.EVENTS.getByName("result-event");
    const payload = {
      operation_id: "session-result:resultsession01",
      session_id: "resultsession01",
      scenario_id: "hotel_kraskov",
      name: "Výsledkový tým",
      players: ["Alice", "Bob"],
      mode: "team",
      score: 1234,
      started_at: "2026-10-10T10:00:00.000Z",
      completed_at: "2026-10-10T10:42:00.000Z",
      out_of_competition: true,
    };
    const finalized = await resultStub.fetch("https://internal/internal/event/result", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Admin": "1" },
      body: JSON.stringify(payload),
    });
    expect(finalized.status).toBe(200);
    expect(await finalized.json()).toMatchObject({
      changed: true,
      result: { score: 1234, duration_seconds: 2520, out_of_competition: true },
    });
    expect((await update).payload.entries).toEqual([
      expect.objectContaining({ session_id: "resultsession01", score: 1234, event_id: "result-event" }),
    ]);

    const duplicate = await resultStub.fetch("https://internal/internal/event/result", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Admin": "1" },
      body: JSON.stringify({ ...payload, score: 9999 }),
    });
    expect(await duplicate.json()).toMatchObject({ changed: false, result: { score: 1234 } });
    const conflicting = await resultStub.fetch("https://internal/internal/event/result", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Admin": "1" },
      body: JSON.stringify({ ...payload, operation_id: "different-result-operation" }),
    });
    expect(conflicting.status).toBe(409);
    expect(await conflicting.json()).toMatchObject({ error: "result_already_finalized" });

    await closeSocket(channel);
    await evictDurableObject(resultStub);
    const restoredLeaderboard = await resultStub.fetch("https://internal/internal/event/leaderboard", {
      headers: { "X-EscapeBot-Internal-Admin": "1" },
    });
    expect(await restoredLeaderboard.json()).toMatchObject({
      entries: [expect.objectContaining({ session_id: "resultsession01", score: 1234 })],
    });

    const closed = await SELF.fetch("https://example.test/api/admin/events/active/leaderboard/finalize", {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: "result-event-close" }),
    });
    expect(closed.status).toBe(200);
    expect(await closed.json()).toMatchObject({ changed: true, event: { leaderboard_finalized: true } });
    const lateResult = await resultStub.fetch("https://internal/internal/event/result", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-EscapeBot-Internal-Admin": "1" },
      body: JSON.stringify({ ...payload, operation_id: "late-result", session_id: "resultsession02" }),
    });
    expect(lateResult.status).toBe(409);
    expect(await lateResult.json()).toMatchObject({ error: "leaderboard_finalized" });
    await (await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    })).json();
  });

  it("automatically publishes a completed game with the one-time completion bonus", async () => {
    const now = new Date();
    const offset = 12 - now.getUTCHours();
    const timezone = offset === 0 ? "UTC" : `Etc/GMT${offset > 0 ? `-${offset}` : `+${Math.abs(offset)}`}`;
    const date = dateInZone(now, timezone);
    const created = await putEvent("automatic-result-event", eventConfiguration({
      starts_at: new Date(now.valueOf() - 60 * 60_000).toISOString(),
      ends_at: new Date(now.valueOf() + 6 * 60 * 60_000).toISOString(),
      status: "open",
      timezone,
      daily_windows: [{ date, enabled: true, opens_at: "00:00", closes_at: "23:59" }],
      operation_id: "automatic-result-create",
    }));
    expect(created.status).toBe(200);
    await created.json();

    const bootstrap = await openBootstrap("automatic-result-player");
    const route = nextMessage(bootstrap, "lobby.route");
    bootstrap.send(JSON.stringify({
      type: "lobby.create",
      payload: {
        client_id: "automatic-result-player",
        name: "Alice",
        team_name: "Automatický výsledek",
        lobby_type: "on_site_qr",
        scenario_id: "hotel_kraskov",
      },
    }));
    const sessionId = String((await route).payload.session_id);
    const session = await openSession(sessionId, "automatic-result-player");
    const started = nextMessage(session, "lobby.state");
    session.send(JSON.stringify({ type: "lobby.start", payload: {} }));
    expect((await started).payload.started).toBe(true);

    const scenarioResponse = await env.ASSETS.fetch("https://assets.local/scenarios/hotel_kraskov.json");
    const scenario = await scenarioResponse.json<Record<string, any>>();
    await runInDurableObject(env.GAME_SESSIONS.getByName(sessionId), async (instance, state) => {
      const target = instance as unknown as { snapshot: { gameState: Record<string, any> } };
      const finale = scenario.puzzles.time_machine_finale;
      for (const checkpointId of finale.requires_checkpoints) {
        target.snapshot.gameState.checkpoint_states[checkpointId] = {
          ...target.snapshot.gameState.checkpoint_states[checkpointId],
          status: "solved",
        };
      }
      target.snapshot.gameState.checkpoint_states.time_machine_console = { status: "found" };
      target.snapshot.gameState.inventory = [...finale.requires_inventory];
      target.snapshot.gameState.flags.room_108_unlocked = true;
      await state.storage.put("session-snapshot", target.snapshot);
    });

    const eventChannel = await openEventChannel("automatic-result-event");
    await nextMessage(eventChannel, "runtime.settings");
    await nextMessage(eventChannel, "leaderboard.update");
    const leaderboardUpdate = nextMessage(eventChannel, "leaderboard.update");
    const completion = nextMessage(session, "game.complete");
    session.send(JSON.stringify({
      type: "finale.activate",
      operation_id: "automatic-result-finale",
      payload: {
        puzzle_id: "time_machine_finale",
        year: "2037",
        time: "21:40",
        modules: ["TEMPORÁLNÍ MOTOR", "FÁZOVÝ STABILIZÁTOR", "KRYSTAL ČASOVÉ KOTVY"],
      },
    }));
    const completed = await completion;
    expect(completed.payload).toMatchObject({ score_frozen: false });
    expect(Number(completed.payload.leaderboard_score)).toBe(Number(completed.payload.score));
    expect((await leaderboardUpdate).payload.entries).toEqual([
      expect.objectContaining({
        session_id: sessionId,
        score: completed.payload.leaderboard_score,
        administrative: false,
      }),
    ]);

    await Promise.all([closeSocket(bootstrap), closeSocket(session), closeSocket(eventChannel)]);
    await (await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    })).json();
  });

  const managedAdminScenario = async () => {
    const now = new Date();
    const offset = 12 - now.getUTCHours();
    const timezone = offset === 0 ? "UTC" : `Etc/GMT${offset > 0 ? `-${offset}` : `+${Math.abs(offset)}`}`;
    const date = dateInZone(now, timezone);
    const created = await putEvent("managed-runtime-event", eventConfiguration({
      starts_at: new Date(now.valueOf() - 60 * 60_000).toISOString(),
      ends_at: new Date(now.valueOf() + 6 * 60 * 60_000).toISOString(),
      status: "open",
      timezone,
      daily_windows: [{ date, enabled: true, opens_at: "00:00", closes_at: "23:59" }],
      games: [{
        game_id: "hotel_kraskov",
        role: "primary",
        queue_enabled: true,
        leaderboard_enabled: true,
        weight: 1,
        start_interval_minutes: 30,
        max_active_teams: 4,
      }],
      operation_id: "managed-runtime-create",
    }));
    expect(created.status).toBe(200);
    await created.json();

    const bootstrap = await openBootstrap("managed-runtime-captain");
    const route = nextMessage(bootstrap, "lobby.route");
    bootstrap.send(JSON.stringify({
      type: "lobby.create",
      payload: {
        client_id: "managed-runtime-captain",
        name: "Alice",
        team_name: "Řízený tým",
        lobby_type: "on_site_qr",
        scenario_id: "hotel_kraskov",
      },
    }));
    const sessionId = String((await route).payload.session_id);
    const session = await openSession(sessionId, "managed-runtime-captain");
    await closeSocket(bootstrap);

    const managedSettings = nextMessage(session, "runtime.settings");
    const managed = await patchActiveRuntime({
      operation_id: "managed-runtime-enable",
      expected_revision: 1,
      runtime: { launch_mode: "managed" },
    });
    expect(managed.status).toBe(200);
    expect((await managedSettings).payload.launch_mode).toBe("managed");

    const rejected = nextMessage(session, "lobby.error");
    session.send(JSON.stringify({ type: "lobby.start", payload: {} }));
    expect(String((await rejected).payload.message)).toContain("řízeném režimu");

    const startedState = nextMessage(session, "lobby.state");
    const startedSettings = nextMessage(session, "runtime.settings");
    const adminStart = await SELF.fetch("https://example.test/api/admin/events/active/start", {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: "managed-runtime-start", session_id: sessionId }),
    });
    expect(adminStart.status).toBe(200);
    expect(await adminStart.json()).toMatchObject({ changed: true, started: true, session_id: sessionId });
    expect((await startedState).payload.started).toBe(true);
    expect((await startedSettings).payload).toMatchObject({ gameplay_enabled: true, launch_mode: "managed" });

    const managedCreated = await SELF.fetch("https://example.test/api/admin/teams", {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({
        operation_id: "managed-team-create",
        team_name: "Tým založený správcem",
        scenario_id: "hotel_kraskov",
        lobby_type: "on_site_qr",
      }),
    });
    expect(managedCreated.status).toBe(201);
    const managedTeam = await managedCreated.json<Record<string, any>>();
    expect(managedTeam).toMatchObject({ changed: true, team_name: "Tým založený správcem" });
    expect(managedTeam.join_code).toMatch(/^[A-F0-9]{8}$/);
    const duplicateCreate = await SELF.fetch("https://example.test/api/admin/teams", {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: "managed-team-create", team_name: "jiný název" }),
    });
    expect(await duplicateCreate.json()).toMatchObject({ changed: false, session_id: managedTeam.session_id });

    const managedBootstrap = await openBootstrap("managed-created-player");
    const managedRoute = nextMessage(managedBootstrap, "lobby.route");
    managedBootstrap.send(JSON.stringify({
      type: "lobby.join",
      payload: {
        client_id: "managed-created-player",
        name: "Bob",
        join_code: managedTeam.join_code,
      },
    }));
    expect((await managedRoute).payload.session_id).toBe(managedTeam.session_id);
    const managedSession = await openSession(managedTeam.session_id, "managed-created-player");
    await closeSocket(managedBootstrap);
    const managedLobby = nextMessage(managedSession, "lobby.state");
    managedSession.send(JSON.stringify({ type: "lobby.resume", payload: { session_id: managedTeam.session_id } }));
    expect((await managedLobby).payload).toMatchObject({ registered_players: 1, is_creator: true });

    const intervalRejected = await SELF.fetch("https://example.test/api/admin/events/active/start", {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: "managed-team-normal-start", session_id: managedTeam.session_id }),
    });
    expect(intervalRejected.status).toBe(409);
    expect(String((await intervalRejected.json<Record<string, any>>()).reason)).toContain("minimální rozestup");

    const managedStarted = nextMessage(managedSession, "lobby.state");
    const overrideStart = await SELF.fetch("https://example.test/api/admin/events/active/start", {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({
        operation_id: "managed-team-override-start",
        session_id: managedTeam.session_id,
        override_soft: true,
      }),
    });
    expect(overrideStart.status).toBe(200);
    expect(await overrideStart.json()).toMatchObject({ changed: true, override_soft: true });
    expect((await managedStarted).payload.started).toBe(true);
    const duplicateOverride = await SELF.fetch("https://example.test/api/admin/events/active/start", {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({
        operation_id: "managed-team-override-start",
        session_id: managedTeam.session_id,
        override_soft: true,
      }),
    });
    expect(await duplicateOverride.json()).toMatchObject({ changed: false, override_soft: true });

    const removedNotice = nextMessage(managedSession, "admin.session_removed");
    const deleted = await SELF.fetch(`https://example.test/api/admin/sessions/${managedTeam.session_id}`, {
      method: "DELETE",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: "managed-team-delete" }),
    });
    expect(deleted.status).toBe(200);
    expect(await deleted.json()).toMatchObject({ changed: true, session_id: managedTeam.session_id });
    await removedNotice;
    const duplicateDelete = await SELF.fetch(`https://example.test/api/admin/sessions/${managedTeam.session_id}`, {
      method: "DELETE",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: "managed-team-delete" }),
    });
    expect(await duplicateDelete.json()).toMatchObject({ changed: false, session_id: managedTeam.session_id });

    const staleBootstrap = await openBootstrap("managed-stale-player");
    const staleJoin = nextMessage(staleBootstrap, "lobby.error");
    staleBootstrap.send(JSON.stringify({
      type: "lobby.join",
      payload: { client_id: "managed-stale-player", name: "Cyril", join_code: managedTeam.join_code },
    }));
    expect(String((await staleJoin).payload.message)).toContain("neexistuje");
    await Promise.all([closeSocket(managedSession), closeSocket(staleBootstrap)]);

    const stoppedNotice = nextMessage(session, "operations.stopped");
    const stoppedSettings = nextMessage(session, "runtime.settings");
    const stopped = await patchActiveRuntime({
      operation_id: "managed-runtime-stop",
      expected_revision: 2,
      runtime: { gameplay_enabled: false },
    });
    expect(stopped.status).toBe(200);
    expect((await stoppedNotice).payload.message).toContain("ukončen Game Masterem");
    expect((await stoppedSettings).payload.gameplay_enabled).toBe(false);
    const snapshot = await env.GAME_SESSIONS.getByName(sessionId).fetch(
      "https://internal/internal/admin/snapshot",
      { headers: { "X-EscapeBot-Internal-Admin": "1" } },
    );
    const stoppedSnapshot = await snapshot.json<Record<string, any>>();
    expect(stoppedSnapshot).toMatchObject({ administratively_ended: true, end_reason: "manual" });
    await runInDurableObject(env.GAME_SESSIONS.getByName(sessionId), async (_instance, state) => {
      expect(await state.storage.getAlarm()).toBeNull();
    });

    const evaluated = await SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/finalize`,
      {
        method: "POST",
        headers: { ...authorization, "Content-Type": "application/json" },
        body: JSON.stringify({ operation_id: "managed-runtime-evaluate" }),
      },
    );
    expect(evaluated.status).toBe(200);
    expect(await evaluated.json()).toMatchObject({ changed: true, session_id: sessionId, score: stoppedSnapshot.score });
    const leaderboard = await env.EVENTS.getByName("managed-runtime-event").fetch(
      "https://internal/internal/event/leaderboard",
      { headers: { "X-EscapeBot-Internal-Admin": "1" } },
    );
    expect(await leaderboard.json()).toMatchObject({
      entries: [expect.objectContaining({ session_id: sessionId, score: stoppedSnapshot.score, administrative: true })],
    });
    const evaluatedAgain = await SELF.fetch(
      `https://example.test/api/admin/sessions/${sessionId}/finalize`,
      {
        method: "POST",
        headers: { ...authorization, "Content-Type": "application/json" },
        body: JSON.stringify({ operation_id: "managed-runtime-evaluate-again" }),
      },
    );
    expect(await evaluatedAgain.json()).toMatchObject({ changed: false, score: stoppedSnapshot.score });

    const blockedBootstrap = await openBootstrap("managed-runtime-new-player");
    const blocked = nextMessage(blockedBootstrap, "lobby.error");
    blockedBootstrap.send(JSON.stringify({
      type: "lobby.solo",
      payload: {
        client_id: "managed-runtime-new-player",
        name: "Bob",
        team_name: "Pozdní tým",
        lobby_type: "on_site_qr",
        scenario_id: "hotel_kraskov",
      },
    }));
    expect(String((await blocked).payload.message)).toContain("zastaven správcem");
    await closeSocket(blockedBootstrap);

    const deletedStoppedSession = await SELF.fetch(`https://example.test/api/admin/sessions/${sessionId}`, {
      method: "DELETE",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: "managed-runtime-delete-stopped" }),
    });
    expect(deletedStoppedSession.status).toBe(200);
    expect(await deletedStoppedSession.json()).toMatchObject({ changed: true, session_id: sessionId });

    await closeSocket(session);
    await (await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    })).json();
  };

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
      status: "open",
      daily_windows: dailyWindows,
      operation_id: "weekend-create",
    }));
    expect(created.status).toBe(200);
    const createdPayload = await created.json<Record<string, any>>();
    expect(createdPayload).toMatchObject({
      event: {
        schema_version: 4,
        starts_at: "2026-10-09T13:00:00.000Z",
        ends_at: "2026-10-11T10:00:00.000Z",
        daily_windows: dailyWindows,
      },
    });
    const event = createdPayload.event as EventSnapshot;
    expect(eventStartAvailability(event, "2026-10-09T12:59:00Z", 165)).toMatchObject({
      start_allowed: false,
      reason: "Event ještě nezačal.",
    });
    expect(eventStartAvailability(event, "2026-10-10T15:15:00Z", 165)).toMatchObject({
      start_allowed: true,
      latest_start_at: "2026-10-10T15:15:00.000Z",
      closing_at: "2026-10-10T18:00:00.000Z",
    });
    expect(eventStartAvailability(event, "2026-10-10T15:16:00Z", 165)).toMatchObject({
      start_allowed: false,
      reason: "Na dokončení hry před koncem provozu už nezbývá dost času.",
    });
    expect(eventStartAvailability(event, "2026-10-11T07:16:00Z", 165)).toMatchObject({
      start_allowed: false,
      latest_start_at: "2026-10-11T07:15:00.000Z",
      closing_at: "2026-10-11T10:00:00.000Z",
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

  it("rejects a direct team start outside the active event window", async () => {
    const created = await putEvent("paused-event", eventConfiguration({
      status: "paused",
      operation_id: "paused-event-create",
    }));
    expect(created.status).toBe(200);
    await created.json();

    const sessionId = "event-window-team-session";
    const initialized = await env.GAME_SESSIONS.getByName(sessionId).fetch(
      "https://internal/internal/lobby/initialize",
      {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          mode: "team",
          creator_id: "event-captain",
          team_name: "Čekající tým",
          join_code: "ABCD1234",
          lobby_type: "on_site_qr",
          scenario_id: "hotel_kraskov",
          player_name: "Alice",
        }),
      },
    );
    expect(initialized.status).toBe(200);

    const socket = await openSession(sessionId, "event-captain");
    const rejected = nextMessage(socket, "lobby.error");
    socket.send(JSON.stringify({ type: "lobby.start", payload: {} }));
    expect((await rejected).payload).toEqual({ message: "Event není otevřený (stav: paused)." });

    const snapshot = await env.GAME_SESSIONS.getByName(sessionId).fetch(
      "https://internal/internal/admin/snapshot",
      { headers: { "X-EscapeBot-Internal-Admin": "1" } },
    );
    expect(await snapshot.json()).toMatchObject({ started: false });
    await closeSocket(socket);
    const cleared = await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    });
    await cleared.json();
  });

  it("atomically enforces per-game capacity and start interval", async () => {
    const now = new Date();
    const utcHour = now.getUTCHours();
    const offset = 12 - utcHour;
    const timezone = offset === 0 ? "UTC" : `Etc/GMT${offset > 0 ? `-${offset}` : `+${Math.abs(offset)}`}`;
    const date = dateInZone(now, timezone);
    const eventWindow = {
      starts_at: new Date(now.valueOf() - 60 * 60_000).toISOString(),
      ends_at: new Date(now.valueOf() + 6 * 60 * 60_000).toISOString(),
      status: "open",
      timezone,
      daily_windows: [{ date, enabled: true, opens_at: "00:00", closes_at: "23:59" }],
    };
    const gameConfiguration = {
      game_id: "hotel_kraskov",
      role: "primary",
      queue_enabled: true,
      leaderboard_enabled: true,
      weight: 1,
      start_interval_minutes: 30,
      max_active_teams: 1,
    };
    const created = await putEvent("capacity-event", eventConfiguration({
      ...eventWindow,
      games: [{
        ...gameConfiguration,
      }],
      operation_id: "capacity-event-create",
    }));
    expect(created.status).toBe(200);
    await created.json();

    const createTeam = async (clientId: string, teamName: string): Promise<{ bootstrap: WebSocket; session: WebSocket }> => {
      const bootstrap = await openBootstrap(clientId);
      const route = nextMessage(bootstrap, "lobby.route");
      bootstrap.send(JSON.stringify({
        type: "lobby.create",
        payload: {
          client_id: clientId,
          name: clientId,
          team_name: teamName,
          lobby_type: "on_site_qr",
          scenario_id: "hotel_kraskov",
        },
      }));
      const routed = await route;
      const session = await openSession(String(routed.payload.session_id), clientId);
      return { bootstrap, session };
    };
    const first = await createTeam("capacity-one", "Kapacita jedna");
    const second = await createTeam("capacity-two", "Kapacita dva");

    const started = nextMessage(first.session, "lobby.state");
    first.session.send(JSON.stringify({ type: "lobby.start", payload: {} }));
    expect((await started).payload).toMatchObject({ started: true });

    const rejected = nextMessage(second.session, "lobby.error");
    second.session.send(JSON.stringify({ type: "lobby.start", payload: {} }));
    expect(String((await rejected).payload.message)).toContain("Kapacita současně hrajících týmů je naplněna.");

    const expanded = await putEvent("capacity-event", eventConfiguration({
      ...eventWindow,
      games: [{ ...gameConfiguration, max_active_teams: 4 }],
      operation_id: "capacity-event-expand",
      expected_revision: 1,
    }));
    expect(expanded.status).toBe(200);
    await expanded.json();
    const intervalRejected = nextMessage(second.session, "lobby.error");
    second.session.send(JSON.stringify({ type: "lobby.start", payload: {} }));
    expect(String((await intervalRejected).payload.message)).toContain("Ještě neuplynul minimální rozestup mezi starty.");

    await Promise.all([
      closeSocket(first.bootstrap),
      closeSocket(first.session),
      closeSocket(second.bootstrap),
      closeSocket(second.session),
    ]);
    const cleared = await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    });
    await cleared.json();
  });

  it("persists a queued team and starts it from the directory alarm", async () => {
    const now = new Date();
    const offset = 12 - now.getUTCHours();
    const timezone = offset === 0 ? "UTC" : `Etc/GMT${offset > 0 ? `-${offset}` : `+${Math.abs(offset)}`}`;
    const date = dateInZone(now, timezone);
    const created = await putEvent("queue-event", eventConfiguration({
      starts_at: new Date(now.valueOf() - 60 * 60_000).toISOString(),
      ends_at: new Date(now.valueOf() + 6 * 60 * 60_000).toISOString(),
      status: "open",
      timezone,
      daily_windows: [{ date, enabled: true, opens_at: "00:00", closes_at: "23:59" }],
      games: [{
        game_id: "hotel_kraskov",
        role: "primary",
        queue_enabled: true,
        leaderboard_enabled: true,
        weight: 1,
        start_interval_minutes: 0,
        max_active_teams: 4,
      }],
      operation_id: "queue-event-create",
    }));
    expect(created.status).toBe(200);
    await created.json();

    const bootstrap = await openBootstrap("queued-captain");
    const route = nextMessage(bootstrap, "lobby.route");
    bootstrap.send(JSON.stringify({
      type: "lobby.create",
      payload: {
        client_id: "queued-captain",
        name: "Alice",
        team_name: "Tým ve frontě",
        lobby_type: "on_site_qr",
        scenario_id: "hotel_kraskov",
      },
    }));
    const sessionId = String((await route).payload.session_id);
    const session = await openSession(sessionId, "queued-captain");
    await closeSocket(bootstrap);
    const queuedSettings = nextMessage(session, "runtime.settings");
    session.send(JSON.stringify({ type: "lobby.queue", payload: {} }));
    expect((await queuedSettings).payload.start_queue).toEqual([
      expect.objectContaining({ session_id: sessionId, team_name: "Tým ve frontě", position: 1 }),
    ]);
    const dequeuedSettings = nextMessage(session, "runtime.settings");
    session.send(JSON.stringify({ type: "lobby.dequeue", payload: {} }));
    expect((await dequeuedSettings).payload.start_queue).toEqual([]);
    const requeuedSettings = nextMessage(session, "runtime.settings");
    session.send(JSON.stringify({ type: "lobby.queue", payload: {} }));
    expect((await requeuedSettings).payload.start_queue).toEqual([
      expect.objectContaining({ session_id: sessionId, position: 1 }),
    ]);

    await evictDurableObject(env.GAME_SESSIONS.getByName("__escape_bot_lobby_directory__"));
    const started = nextMessage(session, "lobby.state");
    expect(await runDurableObjectAlarm(env.GAME_SESSIONS.getByName("__escape_bot_lobby_directory__"))).toBe(true);
    expect((await started).payload).toMatchObject({ session_id: sessionId, started: true });

    const snapshot = await env.GAME_SESSIONS.getByName(sessionId).fetch(
      "https://internal/internal/admin/snapshot",
      { headers: { "X-EscapeBot-Internal-Admin": "1" } },
    );
    expect(await snapshot.json()).toMatchObject({ started: true, team_name: "Tým ve frontě" });

    await closeSocket(session);
    const cleared = await SELF.fetch("https://example.test/api/admin/events/active", {
      method: "DELETE",
      headers: authorization,
    });
    await cleared.json();
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

  it("blocks player starts in managed mode, allows admin team operations, and globally stops active games", managedAdminScenario);
});
