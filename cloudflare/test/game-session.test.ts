import { env } from "cloudflare:workers";
import { evictDurableObject, runDurableObjectAlarm } from "cloudflare:test";
import { describe, expect, it } from "vitest";

type Message = { type: string; payload: Record<string, unknown> };

async function connect(sessionId: string, clientId: string) {
  const stub = env.GAME_SESSIONS.getByName(sessionId);
  const response = await stub.fetch(
    `https://example.test/ws?session_id=${sessionId}&client_id=${clientId}`,
    {
      headers: {
        Upgrade: "websocket",
        "X-EscapeBot-Session-Id": sessionId,
      },
    },
  );
  expect(response.status).toBe(101);
  const socket = response.webSocket;
  if (!socket) throw new Error("WebSocket response is missing a socket");
  socket.accept();
  await nextMessage(socket, "session.connected");
  return { socket, stub };
}

function nextMessage(socket: WebSocket, expectedType: string): Promise<Message> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${expectedType}`)), 2000);
    const listener = (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as Message;
      if (message.type !== expectedType) return;
      clearTimeout(timeout);
      socket.removeEventListener("message", listener);
      resolve(message);
    };
    socket.addEventListener("message", listener);
  });
}

function send(socket: WebSocket, type: string, payload: Record<string, unknown> = {}) {
  socket.send(JSON.stringify({ type, payload }));
}

describe("GameSession Durable Object spike", () => {
  it("broadcasts one message to three clients in the same session", async () => {
    const sessionId = "broadcast-session";
    const clients = await Promise.all([
      connect(sessionId, "alice"),
      connect(sessionId, "bob"),
      connect(sessionId, "carol"),
    ]);
    const received = clients.map(({ socket }) => nextMessage(socket, "spike.broadcast"));

    send(clients[0].socket, "spike.broadcast", { text: "hello team" });

    for (const message of await Promise.all(received)) {
      expect(message.payload).toEqual({ client_id: "alice", text: "hello team" });
    }
    for (const { socket } of clients) socket.close(1000, "done");
  });

  it("restores authoritative state and socket metadata after eviction", async () => {
    const { socket, stub } = await connect("resume-session", "iphone");
    const stateUpdate = nextMessage(socket, "game.state");
    send(socket, "spike.state.patch", { phase: "operations", score: 425 });
    expect((await stateUpdate).payload.score).toBe(425);

    await evictDurableObject(stub);

    const lobby = nextMessage(socket, "lobby.state");
    const history = nextMessage(socket, "chat.history");
    const game = nextMessage(socket, "game.state");
    const progress = nextMessage(socket, "scenario.progress");
    send(socket, "lobby.resume");

    expect((await lobby).payload.players).toEqual([{ client_id: "iphone", online: true }]);
    expect((await history).payload.messages).toEqual([]);
    expect((await game).payload).toMatchObject({ phase: "operations", score: 425, revision: 1 });
    expect((await progress).payload).toEqual({ completed: [], available: [] });
    socket.close(1000, "done");
  });

  it("keeps authoritative snapshots isolated by session id", async () => {
    const first = await connect("isolated-session-a", "player-a");
    const second = await connect("isolated-session-b", "player-b");
    const firstUpdate = nextMessage(first.socket, "game.state");
    send(first.socket, "spike.state.patch", { score: 900 });
    expect((await firstUpdate).payload.score).toBe(900);

    const secondState = nextMessage(second.socket, "game.state");
    send(second.socket, "lobby.resume");
    expect((await secondState).payload.score).toBe(0);
    first.socket.close(1000, "done");
    second.socket.close(1000, "done");
  });

  it("persists and broadcasts a deadline alarm", async () => {
    const { socket, stub } = await connect("deadline-session", "captain");
    const scheduled = nextMessage(socket, "spike.deadline.scheduled");
    send(socket, "spike.deadline.schedule", { deadline_at: Date.now() + 60_000 });
    await scheduled;

    const deadline = nextMessage(socket, "game.deadline");
    const state = nextMessage(socket, "game.state");
    expect(await runDurableObjectAlarm(stub)).toBe(true);

    expect((await deadline).payload.session_id).toBe("deadline-session");
    expect((await state).payload.flags).toEqual({ deadline_reached: true });
    socket.close(1000, "done");
  });
});
