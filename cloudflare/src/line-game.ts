export type LineGameConfig = Record<string, any>;
export type LineGameState = Record<string, any>;

export interface LineGameSwapResult {
  scored: Record<string, number>;
  cascades: number;
  animation_frames: Array<Record<string, unknown>>;
  game_complete: boolean;
  completed_conditions: string[];
  score_delta: number;
}

type Cell = [number, number];
type Segment = { color: string; orientation: "horizontal" | "vertical"; cells: Cell[] };

function clone<T>(value: T): T {
  return structuredClone(value);
}

function secondsBetween(later: string, earlier: string): number {
  return Math.max(0, Math.floor((Date.parse(later) - Date.parse(earlier)) / 1000));
}

function deadline(startedAt: string, seconds: number): string {
  return new Date(Date.parse(startedAt) + seconds * 1000).toISOString();
}

export function newLineGame(config: LineGameConfig, now: string): LineGameState {
  const size = Number(config.size || 7);
  const colors = Array.isArray(config.colors) ? config.colors.map(String) : [];
  if (size < 5 || colors.length !== 5) {
    throw new Error("Swap game requires a board of at least 5×5 and exactly five colors.");
  }
  const state: LineGameState = {
    progress: Object.fromEntries(Object.keys(config.objectives || {}).map((length) => [length, 0])),
    status: "playing",
    started_at: now,
    deadline_at: deadline(now, Number(config.time_limit_seconds || 300)),
    swaps: 0,
    rng: Number(config.seed ?? 5312026) & 0x7fffffff,
    board: Array.from({ length: size }, () => Array.from({ length: size }, () => "")),
  };
  refill(state, config, true);
  return state;
}

export function publicLineGame(
  config: LineGameConfig,
  stateValue: LineGameState,
  now: string,
): LineGameState {
  const state = clone(stateValue);
  const remaining = Math.max(0, secondsBetween(state.deadline_at, now));
  if (remaining === 0 && state.status === "playing") state.status = "expired";
  return {
    ...state,
    size: Number(config.size || 7),
    colors: Array.isArray(config.colors) ? config.colors.map(String) : [],
    scoring_colors: Array.isArray(config.scoring_colors) ? config.scoring_colors.map(String) : [],
    objectives: Object.fromEntries(
      Object.entries(config.objectives || {}).map(([length, required]) => [length, Number(required)]),
    ),
    required_condition_count: Number(
      config.required_condition_count ?? Object.keys(config.objectives || {}).length,
    ),
    time_limit_seconds: Number(config.time_limit_seconds || 300),
    remaining_seconds: remaining,
  };
}

export function resetLineGame(
  config: LineGameConfig,
  state: LineGameState,
  now: string,
): void {
  const fresh = newLineGame(config, now);
  for (const key of Object.keys(state)) delete state[key];
  Object.assign(state, fresh);
}

export function completionTimeScore(
  config: LineGameConfig,
  state: LineGameState,
  now: string,
): number {
  const elapsed = secondsBetween(now, state.started_at);
  const neutral = Number(config.neutral_time_seconds || 180);
  const interval = Math.max(1, Number(config.score_interval_seconds || 10));
  const points = Math.max(0, Number(config.score_points_per_interval || 5));
  const difference = neutral - elapsed;
  if (difference === 0) return 0;
  const magnitude = Math.ceil(Math.abs(difference) / interval) * points;
  return difference > 0 ? magnitude : -magnitude;
}

export function swapLineGame(
  config: LineGameConfig,
  state: LineGameState,
  first: Cell,
  second: Cell,
  now: string,
): LineGameSwapResult {
  if (state.status !== "playing") throw new Error("Kalibrace není aktivní; spusťte nový pokus.");
  if (Date.parse(now) >= Date.parse(String(state.deadline_at))) {
    state.status = "expired";
    throw new Error("Časový limit vypršel.");
  }
  const size = Number(config.size || 7);
  for (const [row, column] of [first, second]) {
    if (!Number.isInteger(row) || !Number.isInteger(column) || row < 0 || column < 0 || row >= size || column >= size) {
      throw new Error("Pole leží mimo herní mřížku.");
    }
  }
  if (Math.abs(first[0] - second[0]) + Math.abs(first[1] - second[1]) !== 1) {
    throw new Error("Prohodit lze pouze dvě sousední barvy.");
  }

  const board = state.board as string[][];
  [board[first[0]][first[1]], board[second[0]][second[1]]] = [
    board[second[0]][second[1]],
    board[first[0]][first[1]],
  ];
  let runs = findLineGameRuns(board);
  if (!runs.length) {
    [board[first[0]][first[1]], board[second[0]][second[1]]] = [
      board[second[0]][second[1]],
      board[first[0]][first[1]],
    ];
    throw new Error("Tato výměna nevytvoří žádnou řadu.");
  }

  state.swaps = Number(state.swaps || 0) + 1;
  const animationFrames: Array<Record<string, unknown>> = [
    { phase: "swap", board: clone(board), first: [...first], second: [...second] },
  ];
  const scored: Record<string, number> = { "3": 0, "4": 0, "5": 0 };
  let cascades = 0;
  while (runs.length && cascades < 20) {
    cascades += 1;
    const clearCells = new Map<string, Cell>();
    for (const [color, cells] of runs) {
      for (const cell of cells) clearCells.set(cell.join(":"), cell);
      if ((config.scoring_colors || []).includes(color)) {
        const length = cells.length >= 5 ? "5" : String(cells.length);
        if (Object.hasOwn(state.progress, length)) {
          const required = Number(config.objectives[length]);
          if (Number(state.progress[length] || 0) < required) {
            state.progress[length] = Number(state.progress[length] || 0) + 1;
            scored[length] += 1;
          }
        }
      }
    }
    const sortedCells = [...clearCells.values()].sort(compareCells);
    for (const [row, column] of sortedCells) board[row][column] = "";
    animationFrames.push({
      phase: "clear",
      board: clone(board),
      cells: sortedCells.map((cell) => [...cell]),
      cascade: cascades,
    });
    collapse(board);
    animationFrames.push({ phase: "collapse", board: clone(board), cascade: cascades });
    refill(state, config);
    animationFrames.push({ phase: "refill", board: clone(board), cascade: cascades });
    runs = findLineGameRuns(board);
  }

  const completedConditions = Object.entries(config.objectives || {})
    .filter(([length, required]) => Number(state.progress[length] || 0) >= Number(required))
    .map(([length]) => length);
  const requiredCount = Number(config.required_condition_count ?? Object.keys(config.objectives || {}).length);
  const complete = completedConditions.length >= requiredCount;
  if (complete) state.status = "complete";
  return {
    scored,
    cascades,
    animation_frames: animationFrames,
    game_complete: complete,
    completed_conditions: completedConditions,
    score_delta: complete ? completionTimeScore(config, state, now) : 0,
  };
}

export function findLineGameRuns(board: string[][]): Array<[string, Cell[]]> {
  const size = board.length;
  const segments: Segment[] = [];
  for (let row = 0; row < size; row += 1) {
    scanLine(Array.from({ length: size }, (_, column) => [row, column] as Cell), board, segments, "horizontal");
  }
  for (let column = 0; column < size; column += 1) {
    scanLine(Array.from({ length: size }, (_, row) => [row, column] as Cell), board, segments, "vertical");
  }

  const intersections = segments.map(() => new Set<number>());
  for (let left = 0; left < segments.length; left += 1) {
    const leftCells = new Set(segments[left].cells.map(cellKey));
    for (let right = left + 1; right < segments.length; right += 1) {
      if (
        segments[left].color === segments[right].color &&
        segments[left].orientation !== segments[right].orientation &&
        segments[right].cells.some((cell) => leftCells.has(cellKey(cell)))
      ) {
        intersections[left].add(right);
        intersections[right].add(left);
      }
    }
  }

  const runs: Array<[string, Cell[]]> = [];
  const merged = new Set<number>();
  const visited = new Set<number>();
  for (let index = 0; index < segments.length; index += 1) {
    if (visited.has(index)) continue;
    const component = new Set<number>();
    const pending = [index];
    while (pending.length) {
      const current = pending.pop() as number;
      if (component.has(current)) continue;
      component.add(current);
      for (const neighbor of intersections[current]) {
        if (!component.has(neighbor)) pending.push(neighbor);
      }
    }
    for (const item of component) visited.add(item);
    if (component.size < 2 || ![...component].some((item) => segments[item].cells.length >= 3)) continue;
    const cells = new Map<string, Cell>();
    for (const item of component) {
      for (const cell of segments[item].cells) cells.set(cellKey(cell), cell);
      merged.add(item);
    }
    runs.push([segments[index].color, [...cells.values()].sort(compareCells)]);
  }
  segments.forEach((segment, index) => {
    if (!merged.has(index) && segment.cells.length >= 3) runs.push([segment.color, segment.cells]);
  });
  return runs;
}

function scanLine(
  coordinates: Cell[],
  board: string[][],
  segments: Segment[],
  orientation: Segment["orientation"],
): void {
  let start = 0;
  while (start < coordinates.length) {
    const [startRow, startColumn] = coordinates[start];
    const color = board[startRow][startColumn];
    let end = start + 1;
    while (end < coordinates.length) {
      const [row, column] = coordinates[end];
      if (board[row][column] !== color) break;
      end += 1;
    }
    if (color && end - start >= 2) {
      segments.push({ color, orientation, cells: coordinates.slice(start, end) });
    }
    start = end;
  }
}

function refill(state: LineGameState, config: LineGameConfig, avoidInitialMatches = false): void {
  const board = state.board as string[][];
  const colors = (config.colors || []).map(String);
  for (let row = 0; row < board.length; row += 1) {
    for (let column = 0; column < board.length; column += 1) {
      if (board[row][column]) continue;
      const candidates = avoidInitialMatches
        ? colors.filter((color: string) => !candidateCreatesRun(board, row, column, color))
        : [...colors];
      if (!candidates.length) throw new Error("Initial board cannot be generated without a matching line.");
      state.rng = (Math.imul(1103515245, Number(state.rng)) + 12345) & 0x7fffffff;
      board[row][column] = candidates[Number(state.rng) % candidates.length];
    }
  }
}

function candidateCreatesRun(board: string[][], row: number, column: number, color: string): boolean {
  board[row][column] = color;
  try {
    return findLineGameRuns(board).some(([, cells]) => cells.some(([r, c]) => r === row && c === column));
  } finally {
    board[row][column] = "";
  }
}

function collapse(board: string[][]): void {
  const size = board.length;
  for (let column = 0; column < size; column += 1) {
    const values = board.map((row) => row[column]).filter(Boolean);
    const empty = size - values.length;
    for (let row = 0; row < size; row += 1) {
      board[row][column] = row < empty ? "" : values[row - empty];
    }
  }
}

function cellKey([row, column]: Cell): string {
  return `${row}:${column}`;
}

function compareCells(left: Cell, right: Cell): number {
  return left[0] - right[0] || left[1] - right[1];
}
