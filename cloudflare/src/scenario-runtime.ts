import {
  newLineGame,
  publicLineGame,
  resetLineGame,
  swapLineGame,
  type LineGameState,
} from "./line-game";

export type ScenarioDocument = Record<string, any>;
export type GameStateDocument = Record<string, any>;

export interface RuntimeActor {
  clientId: string;
  participantIds: string[];
  participantNames: Record<string, string>;
  teamMode: "solo" | "team";
}

export interface RuntimeMessage {
  type: string;
  payload: Record<string, unknown>;
}

export interface ScenarioCommandResult {
  state: GameStateDocument;
  messages: RuntimeMessage[];
}

function record(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, any>)
    : {};
}

function phaseData(scenario: ScenarioDocument, phase: string): Record<string, any> {
  return record(record(scenario.phases)[phase]);
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function normalizedActor(actor?: RuntimeActor): RuntimeActor {
  if (actor) return actor;
  return {
    clientId: "player",
    participantIds: ["player"],
    participantNames: { player: "Hráč" },
    teamMode: "solo",
  };
}

function messageTemplate(
  value: unknown,
  replacement = "",
  placeholder = "{text}",
): Record<string, unknown> {
  const payload = clone(record(value));
  if (typeof payload.text === "string") payload.text = payload.text.replaceAll(placeholder, replacement);
  return payload;
}

function normalizePuzzleAnswer(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toUpperCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Z0-9]/g, "");
}

function appendUnique(target: unknown, values: unknown): string[] {
  const result = Array.isArray(target) ? target.map(String) : [];
  for (const value of Array.isArray(values) ? values : []) {
    const item = String(value);
    if (!result.includes(item)) result.push(item);
  }
  return result;
}

function applyRewards(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  rewardsValue: unknown,
): void {
  const rewards = record(rewardsValue);
  state.inventory = appendUnique(state.inventory, rewards.inventory);
  const knownTools = record(scenario.cipher_tools);
  const tools = (Array.isArray(rewards.cipher_tools) ? rewards.cipher_tools : [])
    .map(String)
    .filter((toolId: string) => Object.hasOwn(knownTools, toolId));
  state.unlocked_cipher_tools = appendUnique(state.unlocked_cipher_tools, tools);
  state.flags = record(state.flags);
  for (const flag of Array.isArray(rewards.flags) ? rewards.flags : []) {
    state.flags[String(flag)] = true;
  }
}

function puzzleUsesAnswerAdapter(scenario: ScenarioDocument, puzzle: Record<string, any>): boolean {
  const puzzleType = String(puzzle.type || "answer");
  const declarations = record(scenario.puzzle_components);
  const declaration = record(declarations[puzzleType]);
  if (Object.hasOwn(declarations, puzzleType)) {
    return String(declaration.adapter || puzzleType) === "answer";
  }
  return puzzle.answer !== undefined && puzzle.answer !== null;
}

function puzzleAdapter(scenario: ScenarioDocument, puzzle: Record<string, any>): string {
  const puzzleType = String(puzzle.type || "answer");
  return String(record(record(scenario.puzzle_components)[puzzleType]).adapter || puzzleType);
}

export function startScenario(
  scenario: ScenarioDocument,
  scoreAdjustment: number,
  now: string,
  actor?: RuntimeActor,
): ScenarioCommandResult {
  const initialPhase = String(record(scenario.phase_engine).initial_phase || "comms_offline");
  const unlockedCipherTools = Object.entries(record(scenario.cipher_tools))
    .filter(([, definition]) => Boolean(record(definition).default_unlocked))
    .map(([toolId]) => toolId);
  const state: GameStateDocument = {
    phase: initialPhase,
    unlocked_discoveries: [],
    inventory: [],
    flags: { operations_started_at: now },
    score: 1000 + scoreAdjustment,
    hints_used: {},
    checkpoint_states: {},
    unlocked_cipher_tools: unlockedCipherTools,
    paid_cipher_tools: [],
    puzzle_attempts: {},
    interactive_games: {},
    sokoban_games: {},
    karel_games: {},
    triad_games: {},
    archive_games: {},
    event_history: [],
    game_exclusions: {},
    game_results: {},
    last_activity_at: now,
  };
  const enterMessage = messageTemplate(phaseData(scenario, initialPhase).enter_message);
  return {
    state: presentGameState(scenario, state, actor, now),
    messages: Object.keys(enterMessage).length
      ? [{ type: "bot.message", payload: enterMessage }]
      : [],
  };
}

export function applyScenarioCommand(
  scenario: ScenarioDocument,
  currentState: GameStateDocument,
  type: string,
  payload: Record<string, unknown>,
  now: string,
  actorValue?: RuntimeActor,
): ScenarioCommandResult {
  const actor = normalizedActor(actorValue);
  if (!new Set(["player.message", "phase.hint", "qr.detected", "puzzle.submit", "puzzle.hint", "line_game.move", "line_game.reset"]).has(type)) {
    return {
      state: presentGameState(scenario, currentState, actor, now),
      messages: [{ type: "command.rejected", payload: { reason: `Příkaz ${type} ještě není v cloudovém enginu podporován.` } }],
    };
  }
  const state = clone(currentState);
  state.last_activity_at = now;
  const history = Array.isArray(state.event_history) ? state.event_history : [];
  history.push({ at: now, type, details: {} });
  state.event_history = history.slice(-500);

  let result: ScenarioCommandResult;
  if (type === "player.message") result = applyPlayerMessage(scenario, state, payload);
  else if (type === "phase.hint") result = applyPhaseHint(scenario, state, payload);
  else if (type === "qr.detected") result = applyQrDetected(scenario, state, payload, now, actor);
  else if (type === "puzzle.submit") result = applyPuzzleSubmit(scenario, state, payload, now);
  else if (type === "puzzle.hint") result = applyPuzzleHint(scenario, state, payload);
  else if (type === "line_game.move") result = applyLineGameMove(scenario, state, payload, now, actor);
  else result = applyLineGameReset(scenario, state, payload, now, actor);
  return { ...result, state: presentGameState(scenario, result.state, actor, now) };
}

function applyPlayerMessage(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
): ScenarioCommandResult {
  const text = String(payload.text ?? "").trim();
  if (!text) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Text zprávy je prázdný." } }],
    };
  }

  const phase = String(state.phase || "boot");
  const transition = record(record(record(scenario.phase_engine).transitions)[phase]);
  if (transition.event === undefined || transition.event === "player.message") {
    const match = String(transition.match || "any");
    const expected = String(transition.value ?? phaseData(scenario, phase).success_keyword ?? "");
    const accepted =
      Object.keys(transition).length > 0 &&
      (match === "any" || (match === "contains" && text.includes(expected)) || (match === "equals" && text === expected));
    if (accepted) {
      const nextPhase = String(transition.next_phase || phase);
      state.phase = nextPhase;
      for (const [flag, value] of Object.entries(record(transition.set_flags))) {
        state.flags[flag] = value;
      }
      let configured = transition.success_messages ?? phaseData(scenario, phase).success_messages;
      let templates = Array.isArray(configured) ? configured : configured ? [configured] : [];
      if (!templates.length) {
        configured = phaseData(scenario, nextPhase).enter_message;
        templates = configured ? [configured] : [];
      }
      return {
        state: presentGameState(scenario, state),
        messages: templates.map((template) => ({
          type: "bot.message",
          payload: messageTemplate(template, text),
        })),
      };
    }
    if (Object.keys(transition).length > 0) {
      const failure = transition.fail_message || phaseData(scenario, phase).fail_message;
      return {
        state: presentGameState(scenario, state),
        messages: [{ type: "bot.message", payload: messageTemplate(failure, text) }],
      };
    }
  }

  return {
    state: presentGameState(scenario, state),
    messages: [{
      type: "bot.message",
      payload: messageTemplate(phaseData(scenario, String(state.phase)).default_message, text),
    }],
  };
}

function applyPhaseHint(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
): ScenarioCommandResult {
  const phase = String(state.phase || "");
  state.hints_used = record(state.hints_used);
  if (String(payload.phase_id || "") !== phase) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Tato fáze už není aktivní." } }],
    };
  }
  const hints = Array.isArray(phaseData(scenario, phase).hints)
    ? phaseData(scenario, phase).hints
    : [];
  if (!hints.length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "bot.message",
        payload: {
          text: "Systém: Pro tuto situaci nemám v databázi žádné další nápovědy.",
          mood: "error",
          channel: "general",
        },
      }],
    };
  }
  const unlocked = Number(record(state.hints_used)[phase] || 0);
  const requested = Number(payload.hint_index ?? unlocked);
  if (!Number.isInteger(requested) || requested < 0 || requested >= hints.length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Neplatný stupeň nápovědy." } }],
    };
  }
  if (requested > unlocked) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Nejprve odemkněte předchozí nápovědu." } }],
    };
  }
  const hint = record(hints[requested]);
  const isNew = requested === unlocked;
  const cost = isNew ? Number(hint.penalty || 10) : 0;
  if (isNew) {
    state.score = Number(state.score || 0) - cost;
    state.hints_used[phase] = unlocked + 1;
  }
  const messages: RuntimeMessage[] = [];
  if (isNew) messages.push({ type: "score.update", payload: { score: state.score, penalty: cost } });
  messages.push({
    type: "bot.message",
    payload: { text: `NÁPOVĚDA SYSTÉMU: ${String(hint.text || "")}`, mood: "info", channel: "general" },
  });
  return { state: presentGameState(scenario, state), messages };
}

function applyQrDetected(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
  actor: RuntimeActor,
): ScenarioCommandResult {
  const value = String(payload.value ?? "").trim();
  const prefix = "escapebot://checkpoint/";
  if (!value.startsWith(prefix) || value.length === prefix.length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "qr.result", payload: { accepted: false, reason: "Neznámý formát QR kódu." } }],
    };
  }

  const token = value.slice(prefix.length);
  const checkpointEntry = Object.entries(record(scenario.checkpoints)).find(
    ([, definition]) => String(record(definition).token || "") === token,
  );
  if (!checkpointEntry) {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "qr.result",
        payload: { accepted: false, reason: "Tato časová kotva nepatří do aktuálního scénáře." },
      }],
    };
  }

  const [checkpointId, checkpointValue] = checkpointEntry;
  const checkpoint = record(checkpointValue);
  state.checkpoint_states = record(state.checkpoint_states);
  if (Object.hasOwn(state.checkpoint_states, checkpointId)) {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "qr.result",
        payload: { accepted: true, duplicate: true, checkpoint_id: checkpointId },
      }],
    };
  }

  const requiredPhase = String(checkpoint.requires_phase || "");
  if (requiredPhase && String(state.phase || "") !== requiredPhase) {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "qr.result",
        payload: {
          accepted: false,
          reason: "Časová kotva zatím nereaguje. Pokračujte nejprve v hlavním příběhu.",
          required_phase: requiredPhase,
        },
      }],
    };
  }

  const missing = (Array.isArray(checkpoint.requires) ? checkpoint.requires : [])
    .map(String)
    .filter((required: string) => record(state.checkpoint_states[required]).status !== "solved");
  if (missing.length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "qr.result",
        payload: {
          accepted: false,
          reason: "Časová kotva je mimo sekvenci. Nejprve dokončete předchozí stanoviště.",
          missing,
        },
      }],
    };
  }

  const puzzleId = checkpoint.puzzle_id ? String(checkpoint.puzzle_id) : null;
  const status = puzzleId ? "found" : "solved";
  state.checkpoint_states[checkpointId] = {
    status,
    first_scanned_at: now,
    ...(status === "solved" ? { solved_at: now } : {}),
  };
  state.unlocked_discoveries = appendUnique(state.unlocked_discoveries, [checkpointId]);
  applyRewards(scenario, state, checkpoint.found_rewards);
  if (status === "solved") applyRewards(scenario, state, checkpoint.rewards);
  if (puzzleId && puzzleAdapter(scenario, record(record(scenario.puzzles)[puzzleId])) === "line_game") {
    const puzzle = record(record(scenario.puzzles)[puzzleId]);
    for (const participantId of actor.participantIds.length ? actor.participantIds : [actor.clientId]) {
      ensureLineGame(state, puzzleId, record(puzzle.game), { ...actor, clientId: participantId }, now);
    }
  }

  const configuredMessage = checkpoint.message ?? record(scenario.global_events).qr_detected;
  const messages: RuntimeMessage[] = [
    {
      type: "qr.result",
      payload: {
        accepted: true,
        duplicate: false,
        checkpoint_id: checkpointId,
        puzzle_id: puzzleId,
        status,
      },
    },
    { type: "bot.message", payload: messageTemplate(configuredMessage, checkpointId, "{checkpoint_id}") },
  ];
  const warning = record(checkpoint.warning_if_missing_flag);
  if (warning.flag && !record(state.flags)[String(warning.flag)]) {
    messages.push({ type: "bot.message", payload: messageTemplate(warning.message) });
  }
  messages.push({ type: "effect.trigger", payload: { effect: "glitch", intensity: 0.35, duration_ms: 900 } });
  return { state: presentGameState(scenario, state), messages };
}

function applyPuzzleSubmit(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  if (!Object.keys(puzzle).length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "puzzle.result", payload: { correct: false, reason: "Neznámá hádanka." } }],
    };
  }
  if (!puzzleUsesAnswerAdapter(scenario, puzzle)) {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "puzzle.result",
        payload: { correct: false, reason: "Tato úloha se řeší přímo na herní mřížce." },
      }],
    };
  }

  const checkpointId = String(puzzle.checkpoint_id || "");
  state.checkpoint_states = record(state.checkpoint_states);
  const checkpointState = record(state.checkpoint_states[checkpointId]);
  if (!Object.keys(checkpointState).length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "puzzle.result",
        payload: { correct: false, reason: "Hádanka zatím nebyla nalezena." },
      }],
    };
  }
  if (checkpointState.status === "solved") {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "puzzle.result",
        payload: { correct: true, puzzle_id: puzzleId, already_solved: true },
      }],
    };
  }

  state.puzzle_attempts = record(state.puzzle_attempts);
  const attempts = Number(state.puzzle_attempts[puzzleId] || 0) + 1;
  state.puzzle_attempts[puzzleId] = attempts;
  const acceptedAnswers = Array.isArray(puzzle.answers) ? puzzle.answers : [puzzle.answer ?? ""];
  const answer = normalizePuzzleAnswer(payload.answer);
  const accepted = acceptedAnswers.some((candidate: unknown) => normalizePuzzleAnswer(candidate) === answer);
  if (!accepted) {
    return {
      state: presentGameState(scenario, state),
      messages: [
        { type: "puzzle.result", payload: { correct: false, puzzle_id: puzzleId, attempts } },
        { type: "bot.message", payload: messageTemplate(puzzle.failure_message) },
      ],
    };
  }

  checkpointState.status = "solved";
  checkpointState.solved_at = now;
  state.checkpoint_states[checkpointId] = checkpointState;
  const checkpoint = record(record(scenario.checkpoints)[checkpointId]);
  applyRewards(scenario, state, checkpoint.rewards);
  const messages: RuntimeMessage[] = [
    { type: "puzzle.result", payload: { correct: true, puzzle_id: puzzleId, attempts } },
    { type: "bot.message", payload: messageTemplate(puzzle.success_message) },
  ];
  if (checkpoint.navigation_message) {
    messages.push({ type: "bot.message", payload: messageTemplate(checkpoint.navigation_message) });
  }
  return { state: presentGameState(scenario, state), messages };
}

function applyPuzzleHint(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  if (!Object.keys(puzzle).length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Neznámá hádanka." } }],
    };
  }
  const checkpointId = String(puzzle.checkpoint_id || "");
  if (record(record(state.checkpoint_states)[checkpointId]).status !== "found") {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Pro tuto hádanku nyní nelze použít nápovědu." } }],
    };
  }
  const hints = Array.isArray(puzzle.hints) ? puzzle.hints : [];
  if (!hints.length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Nejsou dostupné žádné nápovědy." } }],
    };
  }
  const key = `puzzle.${puzzleId}`;
  state.hints_used = record(state.hints_used);
  const unlocked = Number(record(state.hints_used)[key] || 0);
  const requested = Number(payload.hint_index ?? unlocked);
  if (!Number.isInteger(requested) || requested < 0 || requested >= hints.length) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Neplatný stupeň nápovědy." } }],
    };
  }
  if (requested > unlocked) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Nejprve odemkněte předchozí nápovědu." } }],
    };
  }
  const hint = record(hints[requested]);
  const isNew = requested === unlocked;
  const cost = isNew ? Number(hint.penalty || 10) : 0;
  if (isNew) {
    state.score = Number(state.score || 0) - cost;
    state.hints_used[key] = unlocked + 1;
  }
  const messages: RuntimeMessage[] = [];
  if (isNew) messages.push({ type: "score.update", payload: { score: state.score, penalty: cost } });
  messages.push({
    type: "bot.message",
    payload: { text: `NÁPOVĚDA SYSTÉMU: ${String(hint.text || "")}`, mood: "info", channel: "general" },
  });
  return { state: presentGameState(scenario, state), messages };
}

function ensureLineGame(
  state: GameStateDocument,
  puzzleId: string,
  config: Record<string, any>,
  actorValue: RuntimeActor,
  now: string,
): LineGameState {
  const actor = normalizedActor(actorValue);
  state.interactive_games = record(state.interactive_games);
  let container = state.interactive_games[puzzleId];
  if (actor.teamMode === "solo" && actor.participantIds.length === 1) {
    if (record(container).players) container = record(record(container).players)[actor.clientId];
    if (!validLineGame(container)) container = newLineGame(config, now);
    state.interactive_games[puzzleId] = container;
    return container as LineGameState;
  }
  if (validLineGame(container)) container = { players: { [actor.clientId]: container } };
  if (!container || typeof container !== "object" || Array.isArray(container) || !record(container).players) {
    container = { players: {} };
  }
  state.interactive_games[puzzleId] = container;
  const players = record(container.players);
  if (!validLineGame(players[actor.clientId])) players[actor.clientId] = newLineGame(config, now);
  container.players = players;
  return players[actor.clientId] as LineGameState;
}

function validLineGame(value: unknown): value is LineGameState {
  const game = record(value);
  return Array.isArray(game.board) && Boolean(game.deadline_at) && typeof game.progress === "object";
}

function lineGameConditions(config: Record<string, any>, game: Record<string, any>): string[] {
  return Object.entries(record(config.objectives))
    .filter(([length, required]) => Number(record(game.progress)[length] || 0) >= Number(required))
    .map(([length]) => length)
    .sort();
}

function lineGamePlayers(state: GameStateDocument, puzzleId: string, actor: RuntimeActor): Record<string, any> {
  const container = record(record(state.interactive_games)[puzzleId]);
  if (actor.teamMode === "solo" && actor.participantIds.length === 1 && validLineGame(container)) {
    return { [actor.clientId]: container };
  }
  return record(container.players);
}

function lineGameTeamProgress(
  state: GameStateDocument,
  puzzleId: string,
  config: Record<string, any>,
  actorValue: RuntimeActor,
): Record<string, unknown> {
  const actor = normalizedActor(actorValue);
  const players = lineGamePlayers(state, puzzleId, actor);
  const excluded = new Set(
    Array.isArray(record(state.game_exclusions)[puzzleId])
      ? record(state.game_exclusions)[puzzleId].map(String)
      : [],
  );
  const covered = new Set<string>();
  const results = record(record(state.game_results)[puzzleId]);
  const participantIds = actor.participantIds.length ? actor.participantIds : [actor.clientId];
  const summaries = participantIds.map((playerId) => {
    const game = record(players[playerId]);
    const conditions = lineGameConditions(config, game);
    if (!excluded.has(playerId)) conditions.forEach((condition) => covered.add(condition));
    return {
      id: playerId,
      name: actor.participantNames[playerId] || "Hráč",
      status: excluded.has(playerId) ? "excluded" : game.status === "complete" ? "complete" : "playing",
      conditions,
      result: results[playerId],
    };
  });
  const requiredPlayers = participantIds.filter((playerId) => !excluded.has(playerId));
  const everyoneComplete = requiredPlayers.length > 0 && requiredPlayers.every(
    (playerId) => record(players[playerId]).status === "complete",
  );
  const teamComplete = everyoneComplete && (
    actor.teamMode === "solo" || covered.size >= 3 || excluded.size > 0
  );
  const allConditions = Object.keys(record(config.objectives)).sort();
  const missing = allConditions.filter((condition) => !covered.has(condition));
  return {
    players: summaries,
    covered_conditions: [...covered].sort(),
    missing_conditions: missing,
    recommendation: missing.length === 1 ? missing[0] : null,
    team_complete: teamComplete,
  };
}

function activeLineGame(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  puzzleId: string,
  actor: RuntimeActor,
  now: string,
): { puzzle: Record<string, any>; checkpoint: Record<string, any>; game: LineGameState } {
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  if (!Object.keys(puzzle).length || puzzleAdapter(scenario, puzzle) !== "line_game") {
    throw new Error("Neznámá interaktivní úloha.");
  }
  const checkpointId = String(puzzle.checkpoint_id || "");
  const checkpoint = record(record(state.checkpoint_states)[checkpointId]);
  if (!Object.keys(checkpoint).length) throw new Error("Interaktivní úloha zatím nebyla nalezena.");
  if (checkpoint.status === "solved") throw new Error("Interaktivní úloha už byla dokončena.");
  return { puzzle, checkpoint, game: ensureLineGame(state, puzzleId, record(puzzle.game), actor, now) };
}

function applyLineGameMove(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
  actor: RuntimeActor,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  if ((Array.isArray(record(state.game_exclusions)[puzzleId])
    ? record(state.game_exclusions)[puzzleId].map(String)
    : []).includes(actor.clientId)) {
    return {
      state,
      messages: [{ type: "line_game.result", payload: { success: false, reason: "Game Master vás z této týmové minihry dočasně vyřadil." } }],
    };
  }
  try {
    const { puzzle, checkpoint, game } = activeLineGame(scenario, state, puzzleId, actor, now);
    const first = payload.first;
    const second = payload.second;
    if (!Array.isArray(first) || !Array.isArray(second) || first.length !== 2 || second.length !== 2) {
      throw new Error("Tah musí obsahovat dvě souřadnice.");
    }
    const coordinates = [...first, ...second].map(Number);
    if (!coordinates.every(Number.isInteger)) throw new Error("Tah musí obsahovat dvě souřadnice.");
    const result = swapLineGame(
      record(puzzle.game),
      game,
      [coordinates[0], coordinates[1]],
      [coordinates[2], coordinates[3]],
      now,
    );
    let teamProgress = lineGameTeamProgress(state, puzzleId, record(puzzle.game), actor);
    const resultPayload: Record<string, unknown> = {
      success: true,
      ...result,
      team_complete: Boolean(teamProgress.team_complete),
    };
    const messages: RuntimeMessage[] = [{ type: "line_game.result", payload: resultPayload }];
    if (result.game_complete) {
      state.game_results = record(state.game_results);
      const results = record(state.game_results[puzzleId]);
      state.game_results[puzzleId] = results;
      if (!Object.hasOwn(results, actor.clientId)) {
        const elapsed = Math.max(0, Math.floor((Date.parse(now) - Date.parse(String(game.started_at))) / 1000));
        results[actor.clientId] = {
          elapsed_seconds: elapsed,
          score_delta: result.score_delta,
          conditions: lineGameConditions(record(puzzle.game), game),
        };
        state.score = Number(state.score || 0) + result.score_delta;
        messages.push({
          type: "score.update",
          payload: {
            score: state.score,
            delta: result.score_delta,
            bonus: Math.max(0, result.score_delta),
            penalty: Math.max(0, -result.score_delta),
            reason: "line_game_individual",
          },
        });
      }
      teamProgress = lineGameTeamProgress(state, puzzleId, record(puzzle.game), actor);
      resultPayload.team_complete = Boolean(teamProgress.team_complete);
    }
    if (teamProgress.team_complete) {
      checkpoint.status = "solved";
      checkpoint.solved_at = now;
      applyRewards(scenario, state, record(record(scenario.checkpoints)[String(puzzle.checkpoint_id || "")]).rewards);
      const scoreDelta = actor.teamMode === "team" ? Number(record(puzzle.game).team_completion_bonus ?? 40) : 0;
      state.score = Number(state.score || 0) + scoreDelta;
      messages.push({
        type: "score.update",
        payload: {
          score: state.score,
          delta: scoreDelta,
          bonus: Math.max(0, scoreDelta),
          penalty: Math.max(0, -scoreDelta),
          reason: "line_game_team",
        },
      });
      resultPayload.team_summary = teamProgress;
      messages.push(
        { type: "puzzle.result", payload: { correct: true, puzzle_id: puzzleId } },
        { type: "bot.message", payload: messageTemplate(puzzle.success_message) },
      );
      const navigation = record(record(scenario.checkpoints)[String(puzzle.checkpoint_id || "")]).navigation_message;
      if (navigation) messages.push({ type: "bot.message", payload: messageTemplate(navigation) });
    }
    return { state, messages };
  } catch (error) {
    return {
      state,
      messages: [{
        type: "line_game.result",
        payload: { success: false, reason: error instanceof Error ? error.message : "Tah se nepodařilo provést." },
      }],
    };
  }
}

function applyLineGameReset(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
  actor: RuntimeActor,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  try {
    const { puzzle, game } = activeLineGame(scenario, state, puzzleId, actor, now);
    resetLineGame(record(puzzle.game), game, now);
    return { state, messages: [{ type: "line_game.result", payload: { success: true, reset: true } }] };
  } catch (error) {
    return {
      state,
      messages: [{
        type: "line_game.result",
        payload: { success: false, reason: error instanceof Error ? error.message : "Hru se nepodařilo obnovit." },
      }],
    };
  }
}

export function presentGameState(
  scenario: ScenarioDocument,
  stateValue: GameStateDocument,
  actorValue?: RuntimeActor,
  now = new Date().toISOString(),
): GameStateDocument {
  const state = clone(stateValue);
  const actor = normalizedActor(actorValue);
  const currentPhase = String(state.phase || "boot");
  const hints = Array.isArray(phaseData(scenario, currentPhase).hints)
    ? phaseData(scenario, currentPhase).hints
    : [];
  state.phase_hints = {
    phase_id: currentPhase,
    count: hints.length,
    unlocked: Math.min(Number(record(state.hints_used)[currentPhase] || 0), hints.length),
    costs: hints.map((hint: unknown) => Number(record(hint).penalty || 10)),
  };
  const allToolsAvailable = scenario.cipher_tools_access === "all";
  const unlockedTools = new Set(Array.isArray(state.unlocked_cipher_tools) ? state.unlocked_cipher_tools : []);
  state.cipher_tools = Object.entries(record(scenario.cipher_tools)).map(([toolId, definition]) => ({
    id: toolId,
    label: String(record(definition).label || toolId),
    status: allToolsAvailable || unlockedTools.has(toolId) ? "unlocked" : "available_for_points",
    unlock_cost: Number(record(definition).unlock_cost || 0),
  }));
  state.puzzles = Object.entries(record(scenario.puzzles)).map(([puzzleId, definition]) => {
    const puzzle = record(definition);
    const checkpointState = record(record(state.checkpoint_states)[String(puzzle.checkpoint_id || "")]);
    const puzzleHints = Array.isArray(puzzle.hints) ? puzzle.hints : [];
    const presented: Record<string, unknown> = {
      id: puzzleId,
      title: String(puzzle.title || puzzleId),
      type: String(puzzle.type || "text"),
      status: String(checkpointState.status || "locked"),
      attempts: Number(record(state.puzzle_attempts)[puzzleId] || 0),
      has_hints: puzzleHints.length > 0,
      hint_count: puzzleHints.length,
      hints_unlocked: Math.min(Number(record(state.hints_used)[`puzzle.${puzzleId}`] || 0), puzzleHints.length),
      hint_costs: puzzleHints.map((hint: unknown) => Number(record(hint).penalty || 10)),
    };
    if (
      actorValue &&
      puzzleAdapter(scenario, puzzle) === "line_game" &&
      (checkpointState.status === "found" || checkpointState.status === "solved")
    ) {
      const game = ensureLineGame(state, puzzleId, record(puzzle.game), actor, now);
      presented.game = publicLineGame(record(puzzle.game), game, now);
      presented.team_progress = lineGameTeamProgress(state, puzzleId, record(puzzle.game), actor);
    }
    return presented;
  });
  return state;
}

export function buildScenarioProgress(
  scenario: ScenarioDocument,
  state: GameStateDocument,
): Record<string, unknown> {
  const flow = Array.isArray(scenario.scenario_flow) ? scenario.scenario_flow : [];
  const currentPhase = String(state.phase || "boot");
  const phaseIds = flow
    .filter((node: unknown) => record(node).kind === "phase")
    .map((node: unknown) => String(record(node).id));
  const phaseIndex = phaseIds.indexOf(currentPhase);
  const resolved = new Set<string>();
  phaseIds.slice(0, phaseIndex + 1).forEach((id: string) => resolved.add(id));
  for (const [checkpointId, checkpointState] of Object.entries(record(state.checkpoint_states))) {
    if (record(checkpointState).status === "solved") resolved.add(checkpointId);
  }
  for (const nodeValue of flow) {
    const node = record(nodeValue);
    if (node.completion_flag && record(state.flags)[String(node.completion_flag)]) {
      resolved.add(String(node.id));
    }
  }

  const puzzles = record(scenario.puzzles);
  const checkpoints = record(scenario.checkpoints);
  const nodes = flow.map((nodeValue: unknown) => {
    const node = record(nodeValue);
    const id = String(node.id || "");
    const kind = String(node.kind || "checkpoint");
    const requires = Array.isArray(node.requires) ? node.requires.map(String) : [];
    let status = "locked";
    if (kind === "phase") {
      const index = phaseIds.indexOf(id);
      status = id === currentPhase ? "active" : phaseIndex >= 0 && index < phaseIndex ? "complete" : "locked";
    } else if (resolved.has(id)) status = "complete";
    else if (record(record(state.checkpoint_states)[id]).status === "found") status = "active";
    else if (requires.every((required: string) => resolved.has(required))) status = "available";
    const puzzleEntry = Object.entries(puzzles).find(
      ([puzzleId, puzzle]) => puzzleId === id || String(record(puzzle).checkpoint_id || "") === id,
    );
    return {
      id,
      label: String(node.label || id),
      kind,
      status,
      requires,
      puzzle_id: puzzleEntry?.[0] ?? null,
      puzzle_type: puzzleEntry ? String(record(puzzleEntry[1]).type || "") : null,
      activation_value: kind === "checkpoint"
        ? `escapebot://checkpoint/${String(record(checkpoints[id]).token || "")}`
        : "",
    };
  });
  return {
    scenario_id: String(scenario.id || "default"),
    title: String(scenario.title || "Escape Bot"),
    current_phase: currentPhase,
    phase: currentPhase,
    score: Number(state.score || 0),
    inventory: Array.isArray(state.inventory) ? state.inventory : [],
    unlocked_cipher_tools: Array.isArray(state.unlocked_cipher_tools) ? state.unlocked_cipher_tools : [],
    nodes,
    completed_nodes: nodes.filter((node: Record<string, unknown>) => node.status === "complete").length,
    total_nodes: nodes.length,
    world: record(scenario.world),
  };
}
