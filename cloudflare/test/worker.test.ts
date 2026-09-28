import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

describe("Cloudflare spike router", () => {
  it("reports health without touching a game session", async () => {
    const response = await SELF.fetch("https://example.test/api/health");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      status: "ok",
      runtime: "cloudflare",
      environment: "local",
    });
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
      payload: { session_id: "router-session", client_id: "phone", revision: 0 },
    });
    socket.close(1000, "done");
  });
});
