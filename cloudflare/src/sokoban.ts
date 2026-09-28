export type SokobanConfig = Record<string, any>;
export type SokobanState = Record<string, any>;

export interface SokobanExecutionResult {
  executed: number;
  requested: number;
  blocked: boolean;
  blocked_command: string | null;
  pushes: number;
  frames: Array<Record<string, unknown>>;
  level_complete: boolean;
  completed_level_id: string | null;
  score_delta: number;
  game_complete: boolean;
}

type Cell = [number, number];

const DIRECTIONS: Record<string, Cell> = {
  up: [-1, 0],
  down: [1, 0],
  left: [0, -1],
  right: [0, 1],
};

const COMMAND_NAMES: Record<string, string> = {
  NAHORU: "up",
  HORE: "up",
  N: "up",
  DOLU: "down",
  D: "down",
  J: "down",
  VLEVO: "left",
  LEVA: "left",
  L: "left",
  Z: "left",
  VPRAVO: "right",
  PRAVA: "right",
  P: "right",
  V: "right",
};

function clone<T>(value: T): T {
  return structuredClone(value);
}

function cell(value: unknown): Cell {
  if (!Array.isArray(value) || value.length !== 2) throw new Error("Neplatná souřadnice Sokobanu.");
  const result: Cell = [Number(value[0]), Number(value[1])];
  if (!result.every(Number.isInteger)) throw new Error("Neplatná souřadnice Sokobanu.");
  return result;
}

function cellKey(value: Cell): string {
  return `${value[0]}:${value[1]}`;
}

function compareCells(left: Cell, right: Cell): number {
  return left[0] - right[0] || left[1] - right[1];
}

function levels(config: SokobanConfig): Record<string, Record<string, any>> {
  const configured = Array.isArray(config.levels) ? config.levels : [];
  const result: Record<string, Record<string, any>> = {};
  for (const levelValue of configured) {
    const level = levelValue && typeof levelValue === "object" && !Array.isArray(levelValue)
      ? levelValue as Record<string, any>
      : {};
    const levelId = String(level.id ?? "");
    if (!levelId || Object.hasOwn(result, levelId)) {
      throw new Error("Every Sokoban level requires a unique id.");
    }
    result[levelId] = level;
  }
  return result;
}

function parseMap(rowsValue: unknown): Record<string, unknown> {
  const rows = Array.isArray(rowsValue) ? rowsValue.map(String) : [];
  if (!rows.length || new Set(rows.map((row) => row.length)).size !== 1) {
    throw new Error("Sokoban map must be a non-empty rectangle.");
  }
  const walls: Cell[] = [];
  const targets: Cell[] = [];
  const boxes: Cell[] = [];
  let player: Cell | null = null;
  rows.forEach((row, rowIndex) => {
    [...row].forEach((mapCell, columnIndex) => {
      const position: Cell = [rowIndex, columnIndex];
      if (mapCell === "#") walls.push(position);
      if (new Set([".", "+", "*"]).has(mapCell)) targets.push(position);
      if (new Set(["$", "*"]).has(mapCell)) boxes.push(position);
      if (new Set(["@", "+"]).has(mapCell)) {
        if (player) throw new Error("Sokoban map contains multiple players.");
        player = position;
      }
    });
  });
  if (!player || !boxes.length || boxes.length !== targets.length) {
    throw new Error("Sokoban map requires one player and the same number of boxes and targets.");
  }
  return { player, boxes, walls, targets, rows: rows.length, columns: rows[0].length };
}

function loadLevel(state: SokobanState, config: SokobanConfig, now: string): void {
  const levelId = String(state.active_level_ids[Number(state.level_index)]);
  const level = levels(config)[levelId];
  Object.assign(state, parseMap(level.map));
  state.level_id = levelId;
  state.level_label = String(level.label ?? levelId);
  state.moves = 0;
  state.pushes = 0;
  state.history = [];
  state.level_speakers = [];
  state.started_at = now;
  state.deadline_at = new Date(Date.parse(now) + Number(config.level_time_seconds ?? 120) * 1000).toISOString();
}

function isComplete(state: SokobanState): boolean {
  const boxes = new Set((state.boxes as unknown[]).map((position) => cellKey(cell(position))));
  const targets = new Set((state.targets as unknown[]).map((position) => cellKey(cell(position))));
  return boxes.size === targets.size && [...boxes].every((position) => targets.has(position));
}

function move(state: SokobanState, command: string): [boolean, boolean] {
  const [rowDelta, columnDelta] = DIRECTIONS[command];
  const player = cell(state.player);
  const destination: Cell = [player[0] + rowDelta, player[1] + columnDelta];
  const walls = new Set((state.walls as unknown[]).map((position) => cellKey(cell(position))));
  const boxes = new Map(
    (state.boxes as unknown[]).map((position) => {
      const parsed = cell(position);
      return [cellKey(parsed), parsed];
    }),
  );
  if (walls.has(cellKey(destination))) return [false, false];
  const pushed = boxes.has(cellKey(destination));
  if (pushed) {
    const boxDestination: Cell = [destination[0] + rowDelta, destination[1] + columnDelta];
    if (walls.has(cellKey(boxDestination)) || boxes.has(cellKey(boxDestination))) return [false, false];
    boxes.delete(cellKey(destination));
    boxes.set(cellKey(boxDestination), boxDestination);
    state.boxes = [...boxes.values()].sort(compareCells);
  }
  state.player = destination;
  return [true, pushed];
}

export function newSokobanGame(config: SokobanConfig, now: string): SokobanState {
  const configuredLevels = levels(config);
  const active = Array.isArray(config.active_level_ids) ? config.active_level_ids.map(String) : [];
  if (!active.length || active.some((levelId) => !configuredLevels[levelId])) {
    throw new Error("Sokoban requires valid active_level_ids.");
  }
  const state: SokobanState = {
    active_level_ids: active,
    level_index: 0,
    completed_levels: [],
    awarded_points: 0,
    moves: 0,
    pushes: 0,
    total_moves: 0,
    total_pushes: 0,
    restarts: 0,
    status: "playing",
    command_history: [],
  };
  loadLevel(state, config, now);
  return state;
}

export function publicSokobanGame(
  config: SokobanConfig,
  stateValue: SokobanState,
  now: string,
): SokobanState {
  const remaining = Math.max(0, Math.floor((Date.parse(String(stateValue.deadline_at)) - Date.parse(now)) / 1000));
  if (remaining === 0 && stateValue.status === "playing") stateValue.status = "expired";
  const result = clone(stateValue);
  delete result.history;
  result.remaining_seconds = remaining;
  result.level_time_seconds = Number(config.level_time_seconds ?? 120);
  result.points_per_level = Number(config.points_per_level ?? 30);
  result.total_levels = (stateValue.active_level_ids as unknown[]).length;
  result.reserve_levels = Math.max(
    0,
    (Array.isArray(config.levels) ? config.levels.length : 0) - result.total_levels,
  );
  return result;
}

export function executeSokoban(
  state: SokobanState,
  config: SokobanConfig,
  commandsValue: unknown,
  now: string,
  maximumCommands = 30,
): SokobanExecutionResult {
  if (state.status === "expired") throw new Error("Čas této úrovně vypršel. Obnovte ji povelem RESET.");
  if (state.status !== "playing") throw new Error("Energetická mřížka už je stabilizovaná.");
  if (Date.parse(now) >= Date.parse(String(state.deadline_at))) {
    state.status = "expired";
    throw new Error("Čas této úrovně vypršel. Obnovte ji povelem RESET.");
  }
  const commands = Array.isArray(commandsValue) ? commandsValue.map(String) : [];
  if (!commands.length || commands.length > maximumCommands) {
    throw new Error(`Sekvence musí obsahovat 1 až ${maximumCommands} pohybů.`);
  }
  if (commands.some((command) => !DIRECTIONS[command])) {
    throw new Error("Sekvence obsahuje neznámý pohyb.");
  }

  let executed = 0;
  let blocked = false;
  let blockedCommand: string | null = null;
  let pushed = 0;
  const frames: Array<Record<string, unknown>> = [];
  for (const command of commands) {
    const snapshot = {
      player: clone(state.player),
      boxes: clone(state.boxes),
      moves: Number(state.moves),
      pushes: Number(state.pushes),
      total_moves: Number(state.total_moves),
      total_pushes: Number(state.total_pushes),
    };
    const [moved, didPush] = move(state, command);
    if (!moved) {
      blocked = true;
      blockedCommand = command;
      break;
    }
    state.history.push(snapshot);
    state.history = state.history.slice(-200);
    state.moves = Number(state.moves) + 1;
    state.pushes = Number(state.pushes) + Number(didPush);
    state.total_moves = Number(state.total_moves) + 1;
    state.total_pushes = Number(state.total_pushes) + Number(didPush);
    executed += 1;
    pushed += Number(didPush);
    frames.push({
      command,
      player: clone(state.player),
      boxes: clone(state.boxes),
      moves: state.moves,
      pushes: state.pushes,
      did_push: didPush,
    });
    if (isComplete(state)) break;
  }

  const levelComplete = isComplete(state);
  let gameComplete = false;
  let scoreDelta = 0;
  let completedLevelId: string | null = null;
  if (levelComplete) {
    completedLevelId = String(state.level_id);
    if (!(state.completed_levels as string[]).includes(completedLevelId)) {
      state.completed_levels.push(completedLevelId);
      scoreDelta = Number(config.points_per_level ?? 30);
      state.awarded_points = Number(state.awarded_points) + scoreDelta;
    }
    if (Number(state.level_index) + 1 >= (state.active_level_ids as unknown[]).length) {
      state.status = "complete";
      gameComplete = true;
    } else {
      state.level_index = Number(state.level_index) + 1;
      loadLevel(state, config, now);
    }
  }
  state.command_history.push({ commands: clone(commands), executed, blocked });
  state.command_history = state.command_history.slice(-100);
  return {
    executed,
    requested: commands.length,
    blocked,
    blocked_command: blockedCommand,
    pushes: pushed,
    frames,
    level_complete: levelComplete,
    completed_level_id: completedLevelId,
    score_delta: scoreDelta,
    game_complete: gameComplete,
  };
}

export function undoSokoban(state: SokobanState): boolean {
  if (state.status !== "playing" || !Array.isArray(state.history) || !state.history.length) return false;
  const snapshot = state.history.pop();
  state.player = snapshot.player;
  state.boxes = snapshot.boxes;
  state.moves = snapshot.moves;
  state.pushes = snapshot.pushes;
  state.total_moves = snapshot.total_moves;
  state.total_pushes = snapshot.total_pushes;
  return true;
}

export function resetSokobanLevel(config: SokobanConfig, state: SokobanState, now: string): void {
  if (state.status === "complete") throw new Error("Všechny úrovně už byly dokončeny.");
  state.status = "playing";
  state.restarts = Number(state.restarts ?? 0) + 1;
  loadLevel(state, config, now);
}

export function parseSokobanCommands(text: string, maximumCommands = 30): string[] | null {
  const normalized = text
    .trim()
    .toUpperCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ");
  if (new Set(["ZPET", "UNDO", "KROK ZPET"]).has(normalized)) return ["undo"];
  if (new Set(["RESET", "RESTART", "ZNOVU", "OBNOVIT"]).has(normalized)) return ["reset"];
  const parts = normalized.split(/[,;]+/).map((part) => part.trim()).filter(Boolean);
  if (!parts.length) return null;
  const commands: string[] = [];
  for (const part of parts) {
    const match = part.match(/^(?:(\d+)\s*[X×]?\s*)?([A-Z]+)(?:\s+(\d+)\s*[X×]?)?$/);
    if (!match) return null;
    const command = COMMAND_NAMES[match[2]];
    if (!command) return null;
    const count = Number(match[1] || match[3] || 1);
    if (count < 1 || commands.length + count > maximumCommands) {
      throw new Error(`Sekvence může obsahovat nejvýše ${maximumCommands} pohybů.`);
    }
    commands.push(...Array.from({ length: count }, () => command));
  }
  return commands;
}
