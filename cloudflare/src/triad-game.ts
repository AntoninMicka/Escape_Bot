export type TriadConfig = Record<string, any>;
export type TriadState = Record<string, any>;

export interface TriadPlaceResult {
  success: true;
  row: number;
  column: number;
  symbol: string;
  new_lines: Array<Record<string, unknown>>;
  opponent_move: Record<string, unknown> | null;
  game_complete: boolean;
}

type Cell = [number, number];
type Orientation = "horizontal" | "vertical" | "diagonal" | "anti_diagonal";

const VECTORS: Record<Orientation, Cell> = {
  horizontal: [0, 1],
  vertical: [1, 0],
  diagonal: [1, 1],
  anti_diagonal: [1, -1],
};

function clone<T>(value: T): T {
  return structuredClone(value);
}

function sameCell(left: unknown, right: Cell): boolean {
  return Array.isArray(left) && Number(left[0]) === right[0] && Number(left[1]) === right[1];
}

function normalizedOrientation(orientation: Orientation): string {
  return orientation === "anti_diagonal" ? "diagonal" : orientation;
}

function lines(size: number): Array<[Orientation, Cell[]]> {
  const result: Array<[Orientation, Cell[]]> = [];
  for (const [orientation, [rowDelta, columnDelta]] of Object.entries(VECTORS) as Array<[Orientation, Cell]>) {
    for (let startRow = 0; startRow < size; startRow += 1) {
      for (let startColumn = 0; startColumn < size; startColumn += 1) {
        const cells = Array.from({ length: 3 }, (_, index) => [
          startRow + index * rowDelta,
          startColumn + index * columnDelta,
        ] as Cell);
        if (cells.every(([row, column]) => row >= 0 && column >= 0 && row < size && column < size)) {
          result.push([orientation, cells]);
        }
      }
    }
  }
  return result;
}

export function newTriadGame(config: TriadConfig, now: string): TriadState {
  const size = Number(config.size ?? 5);
  return {
    size,
    board: Array.from({ length: size }, () => Array.from({ length: size }, () => null)),
    blocked: clone(Array.isArray(config.blocked) ? config.blocked : []),
    completed_orientations: [],
    scored_lines: [],
    placements: 0,
    opponent_moves: 0,
    restarts: 0,
    status: "playing",
    started_at: now,
    deadline_at: new Date(Date.parse(now) + Number(config.time_limit_seconds ?? 180) * 1000).toISOString(),
  };
}

export function publicTriadGame(config: TriadConfig, stateValue: TriadState, now: string): TriadState {
  const state = clone(stateValue);
  const remaining = Math.max(0, Math.floor((Date.parse(String(state.deadline_at)) - Date.parse(now)) / 1000));
  if (remaining === 0 && state.status === "playing") state.status = "expired";
  state.blocked = clone(Array.isArray(config.blocked) ? config.blocked : []);
  return {
    ...state,
    remaining_seconds: remaining,
    symbols: Array.isArray(config.symbols) ? config.symbols.map(String) : ["cyan", "amber"],
    required_orientations: ["horizontal", "vertical", "diagonal"],
    required_orientation_count: Number(config.required_orientation_count ?? 3),
  };
}

export function placeTriad(
  state: TriadState,
  config: TriadConfig,
  row: number,
  column: number,
  symbol: string,
  now: string,
): TriadPlaceResult {
  if (state.status !== "playing" || Date.parse(now) >= Date.parse(String(state.deadline_at))) {
    state.status = "expired";
    throw new Error("Čas stabilizace vypršel. Spusťte nové pole.");
  }
  const symbols = Array.isArray(config.symbols) ? config.symbols.map(String) : ["cyan", "amber"];
  if (!symbols.includes(symbol)) throw new Error("Neplatný typ uzlu.");
  if (!Number.isInteger(row) || !Number.isInteger(column) || row < 0 || column < 0 || row >= Number(state.size) || column >= Number(state.size)) {
    throw new Error("Pole leží mimo mřížku.");
  }
  if ((state.blocked as unknown[]).some((item) => sameCell(item, [row, column])) || state.board[row][column] !== null) {
    throw new Error("Toto pole nelze obsadit.");
  }

  state.board[row][column] = symbol;
  state.placements = Number(state.placements) + 1;
  const newLines: Array<Record<string, unknown>> = [];
  for (const [orientation, cells] of lines(Number(state.size))) {
    const key = cells.map(([lineRow, lineColumn]) => `${lineRow}:${lineColumn}`);
    if ((state.scored_lines as string[][]).some((existing) => existing.length === key.length && existing.every((item, index) => item === key[index]))) {
      continue;
    }
    if (cells.every(([lineRow, lineColumn]) => state.board[lineRow][lineColumn] === symbol)) {
      state.scored_lines.push(key);
      newLines.push({ orientation, cells: key, symbol });
      const normalized = normalizedOrientation(orientation);
      if (!(state.completed_orientations as string[]).includes(normalized)) state.completed_orientations.push(normalized);
    }
  }
  const requiredCount = Number(config.required_orientation_count ?? 3);
  const completed = new Set(
    (state.completed_orientations as string[]).filter((orientation) => ["horizontal", "vertical", "diagonal"].includes(orientation)),
  );
  const complete = completed.size >= requiredCount;
  if (complete) state.status = "complete";
  const opponentMove = complete ? null : opponentTriadMove(state, config);
  return {
    success: true,
    row,
    column,
    symbol,
    new_lines: newLines,
    opponent_move: opponentMove,
    game_complete: complete,
  };
}

export function resetTriadGame(config: TriadConfig, state: TriadState, now: string): void {
  const restarts = Number(state.restarts || 0) + 1;
  const fresh = newTriadGame(config, now);
  for (const key of Object.keys(state)) delete state[key];
  Object.assign(state, fresh, { restarts });
}

function opponentTriadMove(state: TriadState, config: TriadConfig): Record<string, unknown> | null {
  const symbols = new Set(Array.isArray(config.symbols) ? config.symbols.map(String) : ["cyan", "amber"]);
  const completed = new Set(state.completed_orientations as string[]);
  const candidates = new Map<string, number>();
  for (const [orientation, cells] of lines(Number(state.size))) {
    const normalized = normalizedOrientation(orientation);
    const values = cells.map(([row, column]) => state.board[row][column]);
    const empty = cells.filter(([row, column], index) =>
      values[index] === null && !(state.blocked as unknown[]).some((item) => sameCell(item, [row, column])),
    );
    const playerValues = values.filter((value: unknown) => symbols.has(String(value)));
    if (!empty.length || values.includes("opponent")) continue;
    const samePair = playerValues.length === 2 && playerValues[0] === playerValues[1];
    for (const position of empty) {
      let score = samePair && !completed.has(normalized) ? 1000 : 0;
      score += playerValues.length * 20;
      score += completed.has(normalized) ? 1 : 8;
      const key = `${position[0]}:${position[1]}`;
      candidates.set(key, Number(candidates.get(key) || 0) + score);
    }
  }

  const available: Cell[] = [];
  for (let row = 0; row < Number(state.size); row += 1) {
    for (let column = 0; column < Number(state.size); column += 1) {
      if (
        state.board[row][column] === null &&
        !(state.blocked as unknown[]).some((item) => sameCell(item, [row, column]))
      ) available.push([row, column]);
    }
  }
  if (!available.length) return null;
  const center = (Number(state.size) - 1) / 2;
  available.sort((left, right) => {
    const scoreDifference = Number(candidates.get(`${right[0]}:${right[1]}`) || 0) - Number(candidates.get(`${left[0]}:${left[1]}`) || 0);
    if (scoreDifference) return scoreDifference;
    const leftDistance = Math.abs(left[0] - center) + Math.abs(left[1] - center);
    const rightDistance = Math.abs(right[0] - center) + Math.abs(right[1] - center);
    return leftDistance - rightDistance || left[0] - right[0] || left[1] - right[1];
  });
  const [row, column] = available[0];
  state.board[row][column] = "opponent";
  state.opponent_moves = Number(state.opponent_moves || 0) + 1;
  return { row, column, symbol: "opponent" };
}
