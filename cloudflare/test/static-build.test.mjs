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
  assert.match(index, /Authorization:`Bearer \$\{token\}`/);
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
