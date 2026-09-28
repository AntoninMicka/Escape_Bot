import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

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
      payload: { session_id: "router-session", client_id: "phone", revision: 0 },
    });
    socket.close(1000, "done");
  });
});
