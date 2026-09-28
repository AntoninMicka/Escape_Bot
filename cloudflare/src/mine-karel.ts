export type KarelConfig = Record<string, any>;
export type KarelState = Record<string, any>;

export interface KarelExecutionResult {
  success: true;
  frames: Array<Record<string, unknown>>;
  hit_mine: boolean;
  blocked: boolean;
  level_complete: boolean;
  completed_level_id: string | null;
  game_complete: boolean;
  score_delta: number;
}

type Cell = [number, number];

const DIRECTIONS: Record<string, Cell> = {
  up: [-1, 0],
  down: [1, 0],
  left: [0, -1],
  right: [0, 1],
};

function clone<T>(value: T): T {
  return structuredClone(value);
}

function cell(value: unknown): Cell {
  if (!Array.isArray(value) || value.length !== 2) throw new Error("Neplatná souřadnice mapy Karla.");
  const result: Cell = [Number(value[0]), Number(value[1])];
  if (!result.every(Number.isInteger)) throw new Error("Neplatná souřadnice mapy Karla.");
  return result;
}

function cellKey(value: Cell): string {
  return `${value[0]}:${value[1]}`;
}

function sameCell(left: unknown, right: unknown): boolean {
  const first = cell(left);
  const second = cell(right);
  return first[0] === second[0] && first[1] === second[1];
}

function levels(config: KarelConfig): Record<string, Record<string, any>> {
  return Object.fromEntries(
    (Array.isArray(config.levels) ? config.levels : []).map((level: Record<string, any>) => [String(level.id), level]),
  );
}

export function newKarelGame(config: KarelConfig, now: string): KarelState {
  const configuredLevels = levels(config);
  const active = Array.isArray(config.active_level_ids) ? config.active_level_ids.map(String) : [];
  if (!active.length || active.some((levelId) => !configuredLevels[levelId])) {
    throw new Error("Karel vyžaduje platné aktivní úrovně.");
  }
  Object.values(configuredLevels).forEach(validateKarelLevel);
  const state: KarelState = {
    active_level_ids: active,
    level_index: 0,
    completed_levels: [],
    awarded_points: 0,
    total_moves: 0,
    total_strikes: 0,
    restarts: 0,
    status: "playing",
  };
  loadLevel(state, config, now);
  return state;
}

export function publicKarelGame(config: KarelConfig, stateValue: KarelState, now: string): KarelState {
  const state = clone(stateValue);
  const remaining = Math.max(0, Math.floor((Date.parse(String(state.deadline_at)) - Date.parse(now)) / 1000));
  if (remaining === 0 && state.status === "playing") state.status = "expired";
  const mines = new Set((state.mines as unknown[]).map((item) => cellKey(cell(item))));
  const revealed = (state.revealed as unknown[]).map(cell);
  const result = Object.fromEntries(
    Object.entries(state).filter(([key]) => !new Set(["mines", "history"]).has(key)),
  ) as KarelState;
  result.clues = Object.fromEntries(
    revealed
      .filter((position) => !mines.has(cellKey(position)))
      .map((position) => [cellKey(position), adjacentMines(position, mines)]),
  );
  result.text_grid = Array.from({ length: Number(state.rows) }, (_, row) =>
    Array.from({ length: Number(state.columns) }, (_, column) => {
      const position: Cell = [row, column];
      const key = cellKey(position);
      if (sameCell(position, state.player)) return "E";
      if (sameCell(position, state.start)) return "S";
      if (sameCell(position, state.exit)) return "X";
      if ((state.triggered_mines as unknown[]).some((item) => sameCell(item, position))) return "!";
      if (Object.hasOwn(result.clues, key)) return String(result.clues[key]);
      return "?";
    }).join(" "),
  );
  result.remaining_seconds = remaining;
  result.total_levels = (state.active_level_ids as unknown[]).length;
  result.points_per_level = Number(config.points_per_level ?? 40);
  result.reserve_levels = Math.max(0, (Array.isArray(config.levels) ? config.levels.length : 0) - result.total_levels);
  return result;
}

export function executeKarel(
  state: KarelState,
  config: KarelConfig,
  commandsValue: unknown,
  now: string,
): KarelExecutionResult {
  if (state.status !== "playing" || Date.parse(now) >= Date.parse(String(state.deadline_at))) {
    state.status = "expired";
    throw new Error("Čas navigace vypršel. Obnovte pole povelem RESET.");
  }
  const commands = Array.isArray(commandsValue) ? commandsValue.map(String) : [];
  if (!commands.length || commands.length > 30 || commands.some((command) => !DIRECTIONS[command])) {
    throw new Error("Neplatná navigační sekvence.");
  }
  const mines = new Set((state.mines as unknown[]).map((item) => cellKey(cell(item))));
  const frames: Array<Record<string, unknown>> = [];
  let scoreDelta = 0;
  let hitMine = false;
  let blocked = false;
  for (const command of commands) {
    const origin = cell(state.player);
    const [rowDelta, columnDelta] = DIRECTIONS[command];
    const target: Cell = [origin[0] + rowDelta, origin[1] + columnDelta];
    if (target[0] < 0 || target[1] < 0 || target[0] >= Number(state.rows) || target[1] >= Number(state.columns)) {
      blocked = true;
      break;
    }
    const revisited = (state.revealed as unknown[]).some((item) => sameCell(item, target));
    state.history.push([...origin]);
    state.moves = Number(state.moves) + 1;
    state.total_moves = Number(state.total_moves) + 1;
    hitMine = mines.has(cellKey(target));
    if (hitMine) {
      state.strikes = Number(state.strikes) + 1;
      state.total_strikes = Number(state.total_strikes) + 1;
      state.triggered_mines.push([...target]);
      state.player = clone(state.start);
      scoreDelta -= Number(config.mine_penalty ?? 20);
    } else {
      state.player = [...target];
      if (!revisited) state.revealed.push([...target]);
    }
    frames.push({
      command,
      from: origin,
      entered: [...target],
      player: clone(state.player),
      clue: hitMine ? null : adjacentMines(target, mines),
      hit_mine: hitMine,
      revisited,
    });
    if (hitMine || sameCell(state.player, state.exit)) break;
  }

  const levelComplete = sameCell(state.player, state.exit);
  let gameComplete = false;
  let completedLevelId: string | null = null;
  if (levelComplete) {
    completedLevelId = String(state.level_id);
    if (!(state.completed_levels as string[]).includes(completedLevelId)) {
      state.completed_levels.push(completedLevelId);
      const points = Number(config.points_per_level ?? 40);
      scoreDelta += points;
      state.awarded_points = Number(state.awarded_points) + points;
    }
    if (Number(state.level_index) + 1 >= (state.active_level_ids as unknown[]).length) {
      state.status = "complete";
      gameComplete = true;
    } else {
      state.level_index = Number(state.level_index) + 1;
      loadLevel(state, config, now);
    }
  }
  return {
    success: true,
    frames,
    hit_mine: hitMine,
    blocked,
    level_complete: levelComplete,
    completed_level_id: completedLevelId,
    game_complete: gameComplete,
    score_delta: scoreDelta,
  };
}

export function resetKarelGame(config: KarelConfig, state: KarelState, now: string): void {
  state.restarts = Number(state.restarts) + 1;
  loadLevel(state, config, now);
}

export function safeKarelPath(level: Record<string, any>): Cell[] {
  const rows = Number(level.rows);
  const columns = Number(level.columns);
  const start = cell(level.start);
  const exit = cell(level.exit);
  const mines = new Set((Array.isArray(level.mines) ? level.mines : []).map((item) => cellKey(cell(item))));
  const queue: Cell[] = [start];
  const previous = new Map<string, Cell | null>([[cellKey(start), null]]);
  const positions = new Map<string, Cell>([[cellKey(start), start]]);
  while (queue.length) {
    const current = queue.shift() as Cell;
    if (cellKey(current) === cellKey(exit)) break;
    for (const [rowDelta, columnDelta] of Object.values(DIRECTIONS)) {
      const neighbor: Cell = [current[0] + rowDelta, current[1] + columnDelta];
      const key = cellKey(neighbor);
      if (
        neighbor[0] >= 0 && neighbor[1] >= 0 && neighbor[0] < rows && neighbor[1] < columns &&
        !mines.has(key) && !previous.has(key)
      ) {
        previous.set(key, current);
        positions.set(key, neighbor);
        queue.push(neighbor);
      }
    }
  }
  if (!previous.has(cellKey(exit))) return [];
  const path: Cell[] = [];
  let current: Cell | null = positions.get(cellKey(exit)) as Cell;
  while (current) {
    path.push(current);
    current = previous.get(cellKey(current)) ?? null;
  }
  return path.reverse();
}

export function validateKarelLevel(level: Record<string, any>): void {
  const rows = Number(level.rows || 0);
  const columns = Number(level.columns || 0);
  if (!Number.isInteger(rows) || !Number.isInteger(columns) || rows < 2 || columns < 2) {
    throw new Error("Karel vyžaduje mřížku alespoň 2×2.");
  }
  const start = cell(level.start);
  const exit = cell(level.exit);
  const mines = (Array.isArray(level.mines) ? level.mines : []).map(cell);
  const occupied = [start, exit, ...mines];
  if (sameCell(start, exit) || mines.some((mine) => sameCell(mine, start) || sameCell(mine, exit))) {
    throw new Error("Start, cíl a miny Karla se nesmí překrývat.");
  }
  if (occupied.some(([row, column]) => row < 0 || column < 0 || row >= rows || column >= columns)) {
    throw new Error("Souřadnice mapy Karla leží mimo mřížku.");
  }
  if (!safeKarelPath(level).length) throw new Error(`Pole ${String(level.id || "")} nemá bezpečnou trasu.`);
}

function loadLevel(state: KarelState, config: KarelConfig, now: string): void {
  const levelId = String(state.active_level_ids[Number(state.level_index)]);
  const level = levels(config)[levelId];
  Object.assign(state, {
    level_id: level.id,
    level_label: level.label || level.id,
    rows: Number(level.rows),
    columns: Number(level.columns),
    mines: clone(level.mines),
    start: clone(level.start),
    exit: clone(level.exit),
    player: clone(level.start),
    revealed: [...clone(level.revealed || []), clone(level.start), clone(level.exit)],
    triggered_mines: [],
    moves: 0,
    strikes: 0,
    history: [],
    status: "playing",
    started_at: now,
    deadline_at: new Date(Date.parse(now) + Number(config.level_time_seconds ?? 180) * 1000).toISOString(),
  });
}

function adjacentMines([row, column]: Cell, mines: Set<string>): number {
  let count = 0;
  for (let rowDelta = -1; rowDelta <= 1; rowDelta += 1) {
    for (let columnDelta = -1; columnDelta <= 1; columnDelta += 1) {
      if ((rowDelta || columnDelta) && mines.has(cellKey([row + rowDelta, column + columnDelta]))) count += 1;
    }
  }
  return count;
}
