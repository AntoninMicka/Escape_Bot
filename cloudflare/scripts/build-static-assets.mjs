import { createHash } from "node:crypto";
import {
  cp,
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const cloudflareDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryDir = resolve(cloudflareDir, "..");
const clientDir = join(repositoryDir, "client");
const outputDir = join(cloudflareDir, "dist");
const maximumAssetBytes = 25 * 1024 * 1024;

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function copyFile(source, destination) {
  await mkdir(dirname(destination), { recursive: true });
  await cp(source, destination);
}

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await listFiles(path)));
    if (entry.isFile()) files.push(path);
  }
  return files;
}

function relativeUrl(path) {
  return relative(outputDir, path).split(sep).join("/");
}

function supportedLobbyTypes(modes) {
  const values = new Set(modes);
  return [
    values.has("online_doom") || values.has("doom") || values.has("online")
      ? "online_doom"
      : null,
    values.has("on_site_qr") ||
    values.has("physical_indoor") ||
    values.has("physical_outdoor") ||
    values.has("hybrid")
      ? "on_site_qr"
      : null,
    values.has("geo") || values.has("osm") || values.has("gnss") || values.has("location")
      ? "geo"
      : null,
  ].filter(Boolean);
}

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });

const sourceWorker = await readFile(join(clientDir, "sw.js"), "utf8");
const cacheList = sourceWorker.match(/const ASSETS_TO_CACHE = \[([\s\S]*?)\];/);
if (!cacheList) throw new Error("V client/sw.js chybí ASSETS_TO_CACHE.");

const declaredAssets = [...cacheList[1].matchAll(/['\"]([^'\"]+)['\"]/g)].map(
  (match) => match[1],
);
const clientAssets = declaredAssets
  .filter((path) => path.startsWith("./assets/"))
  .map((path) => path.slice(2));

for (const path of ["display.html", "icon.svg", "manifest.json", ...clientAssets]) {
  await copyFile(join(clientDir, path), join(outputDir, path));
}

let indexHtml = await readFile(join(clientDir, "index.html"), "utf8");
const applicationScripts = ["operation-queue.js", "chronos3d.js"];
for (const sourceName of applicationScripts) {
  const contents = await readFile(join(clientDir, sourceName));
  const extensionIndex = sourceName.lastIndexOf(".");
  const outputName = `${sourceName.slice(0, extensionIndex)}-${digest(contents).slice(0, 12)}${sourceName.slice(extensionIndex)}`;
  const outputPath = `assets/app/${outputName}`;
  const replaced = indexHtml.replace(`src="${sourceName}"`, `src="${outputPath}"`);
  if (replaced === indexHtml) throw new Error(`V index.html chybí odkaz na ${sourceName}.`);
  indexHtml = replaced;
  await copyFile(join(clientDir, sourceName), join(outputDir, outputPath));
}
await writeFile(join(outputDir, "index.html"), indexHtml);

const webglSource = join(clientDir, "chronos-webgl", "dist");
const webglOutput = join(outputDir, "chronos-webgl", "dist");
await mkdir(dirname(webglOutput), { recursive: true });
await cp(webglSource, webglOutput, { recursive: true });
await copyFile(join(cloudflareDir, "static", "_headers"), join(outputDir, "_headers"));

const realizationDir = join(repositoryDir, "backend", "content", "realizations");
const runtimeGames = [];
for (const filename of (await readdir(realizationDir)).filter((name) => name.endsWith(".json")).sort()) {
  const realization = JSON.parse(await readFile(join(realizationDir, filename), "utf8"));
  const modes = Array.isArray(realization.modes) ? realization.modes.map(String) : [];
  runtimeGames.push({
    id: String(realization.id || ""),
    title: String(realization.title || realization.id || ""),
    template_id: String(realization.template?.id || ""),
    template_version: String(realization.template?.version || ""),
    realization_version: String(realization.version || ""),
    modes,
    lobby_types: supportedLobbyTypes(modes),
  });
}
if (runtimeGames.some((game) => !game.id || !game.lobby_types.length)) {
  throw new Error("Některá realizace nemá ID nebo podporovaný lobby režim.");
}
await writeFile(join(outputDir, "runtime-catalog.json"), `${JSON.stringify(runtimeGames, null, 2)}\n`);

const versionInputs = (await listFiles(outputDir)).filter(
  (path) => relativeUrl(path) !== "_headers",
);
const versionHash = createHash("sha256");
for (const path of versionInputs) {
  versionHash.update(relativeUrl(path));
  versionHash.update(await readFile(path));
}
const version = versionHash.digest("hex").slice(0, 12);

const localPrecache = versionInputs
  .map(relativeUrl)
  .filter((path) => path !== "index.html")
  .map((path) => `./${path}`);
const precache = [
  "./",
  "./index.html",
  ...localPrecache,
  ...declaredAssets.filter((path) => path.startsWith("https://")),
];
const generatedWorker = sourceWorker
  .replace(/const CACHE_NAME = ['\"][^'\"]+['\"];/, `const CACHE_NAME = 'escape-bot-${version}';`)
  .replace(
    /const ASSETS_TO_CACHE = \[[\s\S]*?\];/,
    `const ASSETS_TO_CACHE = ${JSON.stringify(precache, null, 4)};`,
  );
await writeFile(join(outputDir, "sw.js"), generatedWorker);

const outputFiles = await listFiles(outputDir);
for (const path of outputFiles) {
  const outputPath = relativeUrl(path);
  const segments = outputPath.split("/");
  if (segments.includes("node_modules") || segments.includes("src")) {
    throw new Error(`Build obsahuje zakázaný zdrojový adresář: ${outputPath}`);
  }
  const size = (await stat(path)).size;
  if (size > maximumAssetBytes) {
    throw new Error(`Asset ${outputPath} překračuje 25 MiB (${size} bajtů).`);
  }
}

console.log(`Static Assets build ${version}: ${outputFiles.length} souborů.`);
