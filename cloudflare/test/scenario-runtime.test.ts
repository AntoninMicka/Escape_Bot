import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import {
  applyScenarioCommand,
  buildScenarioProgress,
  startScenario,
  type ScenarioDocument,
} from "../src/scenario-runtime";

async function chronosScenario(): Promise<ScenarioDocument> {
  const response = await env.ASSETS.fetch("https://example.test/scenarios/chronos_online.json");
  expect(response.status).toBe(200);
  return response.json<ScenarioDocument>();
}

describe("deterministic Cloudflare scenario runtime", () => {
  it("starts the compiled scenario with its real phase, message and progress", async () => {
    const scenario = await chronosScenario();
    const started = startScenario(scenario, 20, "2026-09-28T12:00:00.000Z");
    expect(started.state).toMatchObject({ phase: "comms_offline", score: 1020 });
    expect(started.state.phase_hints).toMatchObject({ count: 1, unlocked: 0, costs: [5] });
    expect(started.messages[0].payload.text).toContain("Tady Kapitánka");
    expect(buildScenarioProgress(scenario, started.state)).toMatchObject({
      scenario_id: "chronos_online_rescue",
      current_phase: "comms_offline",
      score: 1020,
    });
  });

  it("advances the opening narrative and applies progressive hints", async () => {
    const scenario = await chronosScenario();
    const started = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z");
    const confirmed = applyScenarioCommand(
      scenario,
      started.state,
      "player.message",
      { text: "Slyšíme se" },
      "2026-09-28T12:00:01.000Z",
    );
    expect(confirmed.state.phase).toBe("searching_lost");
    expect(confirmed.messages[0].payload.text).toContain("nouzový záznam");

    const hinted = applyScenarioCommand(
      scenario,
      confirmed.state,
      "phase.hint",
      { phase_id: "searching_lost", hint_index: 0 },
      "2026-09-28T12:00:02.000Z",
    );
    expect(hinted.state.score).toBe(990);
    expect(hinted.state.phase_hints).toMatchObject({ unlocked: 1 });
    expect(hinted.messages.map((message) => message.type)).toEqual(["score.update", "bot.message"]);

    const connected = applyScenarioCommand(
      scenario,
      hinted.state,
      "player.message",
      { text: "Frekvence je 734" },
      "2026-09-28T12:00:03.000Z",
    );
    expect(connected.state.phase).toBe("navigating");
    expect(connected.state.flags.chronomap_unlocked).toBe(true);
    expect(connected.messages).toHaveLength(3);
  });

  it("rejects an unsupported command without changing gameplay state", async () => {
    const scenario = await chronosScenario();
    const started = startScenario(scenario, 0, "2026-09-28T12:00:00.000Z");
    const rejected = applyScenarioCommand(
      scenario,
      started.state,
      "puzzle.submit",
      { puzzle_id: "missing" },
      "2026-09-28T12:00:01.000Z",
    );

    expect(rejected.messages[0].type).toBe("command.rejected");
    expect(rejected.state).toEqual(started.state);
  });
});
