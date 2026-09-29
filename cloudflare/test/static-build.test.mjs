import assert from "node:assert/strict";
import { readFile, readdir, stat } from "node:fs/promises";
import { dirname, join, relative, resolve, sep } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const cloudflareDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputDir = join(cloudflareDir, "dist");

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await listFiles(path)));
    if (entry.isFile()) files.push(path);
  }
  return files;
}

test("Static Assets build is minimal, fingerprinted and internally complete", async () => {
  const files = await listFiles(outputDir);
  const relativeFiles = files.map((path) => relative(outputDir, path).split(sep).join("/"));
  assert.ok(relativeFiles.includes("index.html"));
  assert.ok(relativeFiles.includes("display.html"));
  assert.ok(relativeFiles.includes("sw.js"));
  assert.ok(relativeFiles.includes("runtime-catalog.json"));
  assert.ok(relativeFiles.includes("scenarios/chronos_online.json"));
  assert.ok(relativeFiles.includes("chronos-webgl/dist/index.html"));
  assert.ok(relativeFiles.some((path) => /^assets\/app\/operation-queue-[a-f0-9]{12}\.js$/.test(path)));
  assert.ok(relativeFiles.some((path) => /^assets\/app\/chronos3d-[a-f0-9]{12}\.js$/.test(path)));
  assert.ok(relativeFiles.some((path) => /^chronos-webgl\/dist\/assets\/chronos-[A-Za-z0-9_-]+\.js$/.test(path)));
  assert.ok(relativeFiles.every((path) => !path.split("/").includes("node_modules")));
  assert.ok(relativeFiles.every((path) => !path.split("/").includes("src")));

  const index = await readFile(join(outputDir, "index.html"), "utf8");
  assert.doesNotMatch(index, /src="(?:operation-queue|chronos3d)\.js"/);
  assert.match(index, /fetch\('\/api\/admin\/overview'/);
  assert.match(index, /fetch\('\/api\/admin\/player-recovery'/);
  assert.match(index, /fetch\('\/api\/admin\/terminal-reserve'/);
  assert.match(index, /fetch\(`\/api\/admin\/events\/\$\{encodeURIComponent\(eventId\)\}`/);
  assert.match(index, /fetch\('\/api\/admin\/events\/active'/);
  assert.match(index, /fetch\('\/api\/admin\/events\/active\/runtime'/);
  assert.match(index, /fetch\('\/api\/admin\/events\/active\/start'/);
  assert.match(index, /\/api\/admin\/events\/active\/leaderboard\/finalize/);
  assert.match(index, /\/api\/admin\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\/finalize/);
  assert.match(index, /channel=event&event_id=/);
  assert.match(index, /launchMode = msg\.payload\.launch_mode === 'managed'/);
  assert.match(index, /onclick="toggleDisplayLeaderboard\(\)"/);
  assert.match(index, /\/api\/admin\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\/support/);
  assert.match(index, /runCloudflareAdminAction\(sessionId,'extend',\{minutes\}\)/);
  assert.match(index, /runCloudflareAdminAction\(sessionId,'end',\{reason\}\)/);
  assert.match(index, /runCloudflareAdminAction\(sessionId,'score-adjustment',\{delta,reason\}\)/);
  assert.match(index, /runCloudflareAdminAction\(sessionId,'checkpoint',\{checkpoint_id:checkpointId,status,penalty_preset:presetId\}\)/);
  assert.match(index, /runCloudflareAdminAction\(sessionId,'game-reset',\{puzzle_id:puzzleId\}\)/);
  assert.match(index, /fetch\('\/api\/admin\/scenario-play-modes'/);
  assert.match(index, /operation_id:crypto\.randomUUID\?\.\(\).*game-player-/);
  assert.match(index, /adminCapabilityValues\('checkpoint_states'\)/);
  assert.match(index, /adminCapabilityValues\('game_reset_adapters'\)/);
  assert.match(index, /adminCapabilityValues\('game_player_actions'\)/);
  assert.match(index, /adminCapabilityValues\('actions'\)/);
  assert.match(index, /adminCapabilityValues\('http_actions'\)/);
  assert.match(index, /\/api\/admin\/terminal-catalog/);
  assert.doesNotMatch(index, /cloudflare_limited/);
  assert.match(index, /!team\.game_completed && !team\.administratively_ended/);
  assert.match(index, /\/api\/admin\/sessions\/\$\{encodeURIComponent\(adminSpectatingSession\)\}\/spectate\?player_id=/);
  assert.match(index, /ZOBRAZIT HRÁČE/);
  assert.match(index, /const spectatorView = adminModeRequested && Boolean\(adminSpectatingSession\)/);
  assert.match(index, /if \(!spectatorView\) \{\s*sessionId = payload\.session_id;/);
  assert.match(index, /id="event-daily-windows"/);
  assert.match(index, /daily_windows:eventDailyWindowDraft/);
  assert.match(index, /if\(Array\.isArray\(msg\.payload\.start_queue\)\)runtimeStartQueue = msg\.payload\.start_queue/);
  assert.match(index, /msg\.type === 'queue\.auto_started'/);
  assert.match(index, /Authorization:`Bearer \$\{token\}`/);
  assert.match(index, /type:'lobby\.leave'/);
  assert.match(index, /msg\.type === 'lobby\.left'/);
  assert.match(index, /TRVALE OPUSTIT HRU/);
  const display = await readFile(join(outputDir, "display.html"), "utf8");
  const extractFunction = (name) => {
    const match = display.match(new RegExp(`function ${name}\\(\\)\\{[^\\n]+\\}`));
    assert.ok(match, `Veřejná nástěnka neobsahuje funkci ${name}.`);
    return match[0];
  };
  const filterLeaderboard = new Function(
    "leaderboard",
    "event",
    "selectedGameId",
    `${extractFunction("visibleLeaderboard")};return visibleLeaderboard();`,
  );
  const leaderboardFixture = [
    { id: "matching", event_id: "event-a", scenario_id: "game-a", leaderboard_enabled: true, competition_role: "primary" },
    { id: "other-game", event_id: "event-a", scenario_id: "game-b", leaderboard_enabled: true, competition_role: "competitive" },
    { id: "other-event", event_id: "event-b", scenario_id: "game-a", leaderboard_enabled: true, competition_role: "primary" },
    { id: "disabled", event_id: "event-a", scenario_id: "game-a", leaderboard_enabled: false, competition_role: "primary" },
    { id: "side", event_id: "event-a", scenario_id: "game-a", leaderboard_enabled: true, competition_role: "side" },
  ];
  assert.deepEqual(
    filterLeaderboard(leaderboardFixture, { id: "event-a" }, "game-a").map((entry) => entry.id),
    ["matching"],
  );
  assert.deepEqual(
    filterLeaderboard(leaderboardFixture, { id: "event-a" }, "game-b").map((entry) => entry.id),
    ["other-game"],
  );

  const filterAnnouncements = new Function(
    "announcements",
    "event",
    "selectedGameId",
    `${extractFunction("activeAnnouncements")};return activeAnnouncements();`,
  );
  const announcements = filterAnnouncements([
    { text: "Pro všechny", published: true },
    { text: "Správný event a hra", published: true, event_id: "event-a", game_id: "game-a" },
    { text: "Jiný event", published: true, event_id: "event-b", game_id: "game-a" },
    { text: "Jiná hra", published: true, event_id: "event-a", game_id: "game-b" },
    { text: "Koncept", published: false, event_id: "event-a", game_id: "game-a" },
  ], { id: "event-a" }, "game-a");
  assert.deepEqual(announcements.map((item) => item.text), ["Pro všechny", "Správný event a hra"]);
  const serviceWorker = await readFile(join(outputDir, "sw.js"), "utf8");
  assert.match(serviceWorker, /const CACHE_NAME = 'escape-bot-[a-f0-9]{12}';/);
  for (const match of serviceWorker.matchAll(/"\.\/([^"?]+)"/g)) {
    if (match[1] === "") continue;
    assert.ok(relativeFiles.includes(match[1]), `Precache odkaz ${match[1]} neexistuje.`);
  }

  const runtimeCatalog = JSON.parse(
    await readFile(join(outputDir, "runtime-catalog.json"), "utf8"),
  );
  assert.ok(runtimeCatalog.some((game) => game.id === "chronos_online"));
  assert.ok(
    runtimeCatalog.find((game) => game.id === "chronos_online").lobby_types.includes("online_doom"),
  );
  const chronosScenario = JSON.parse(
    await readFile(join(outputDir, "scenarios", "chronos_online.json"), "utf8"),
  );
  assert.equal(chronosScenario.id, "chronos_online_rescue");
  assert.match(chronosScenario.phases.searching_lost.enter_message.text, /Výzkumného ústavu CHRONOS/);

  for (const path of files) assert.ok((await stat(path)).size <= 25 * 1024 * 1024);
});
