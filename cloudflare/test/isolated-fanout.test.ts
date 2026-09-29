import { describe, expect, it } from "vitest";
import { isolatedFanout } from "../src/isolated-fanout";

describe("isolated event fanout", () => {
  it("delivers to healthy targets without waiting forever for failed or stuck teams", async () => {
    const delivered: string[] = [];
    const startedAt = Date.now();
    const results = await isolatedFanout(
      ["healthy-a", "broken", "stuck", "healthy-b"],
      async (target) => {
        if (target === "broken") throw new Error("corrupt session");
        if (target === "stuck") await new Promise<never>(() => {});
        delivered.push(target);
      },
      20,
    );

    expect(delivered).toEqual(["healthy-a", "healthy-b"]);
    expect(results.map((result) => result.status)).toEqual([
      "fulfilled",
      "rejected",
      "rejected",
      "fulfilled",
    ]);
    expect(Date.now() - startedAt).toBeLessThan(500);
  });
});
