import {
  newLineGame,
  publicLineGame,
  resetLineGame,
  swapLineGame,
  type LineGameState,
} from "./line-game";
import {
  executeKarel,
  newKarelGame,
  publicKarelGame,
  resetKarelGame,
  type KarelState,
} from "./mine-karel";
import {
  newTriadGame,
  placeTriad,
  publicTriadGame,
  resetTriadGame,
  type TriadState,
} from "./triad-game";
import {
  executeSokoban,
  newSokobanGame,
  parseSokobanCommands,
  publicSokobanGame,
  resetSokobanLevel,
  undoSokoban,
  type SokobanState,
} from "./sokoban";
import {
  arrangeArchive,
  newArchiveGame,
  publicArchiveGame,
  validArchiveGame,
  type ArchiveState,
} from "./archive-vector";

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

export interface AdminGamePlayerResult extends ScenarioCommandResult {
  result: Record<string, unknown>;
}

export function transferPlayerIdentity(
  currentState: GameStateDocument,
  oldPlayerId: string,
  newPlayerId: string,
): GameStateDocument {
  const state = clone(currentState);
  for (const storeName of ["interactive_games", "triad_games"]) {
    const store = record(state[storeName]);
    for (const containerValue of Object.values(store)) {
      const players = record(record(containerValue).players);
      if (Object.hasOwn(players, oldPlayerId)) {
        players[newPlayerId] = players[oldPlayerId];
        delete players[oldPlayerId];
      }
    }
  }
  const exclusions = record(state.game_exclusions);
  for (const [puzzleId, excludedValue] of Object.entries(exclusions)) {
    if (!Array.isArray(excludedValue)) continue;
    exclusions[puzzleId] = [...new Set(excludedValue.map(String).map(
      (playerId) => playerId === oldPlayerId ? newPlayerId : playerId,
    ))];
  }
  for (const resultsValue of Object.values(record(state.game_results))) {
    const results = record(resultsValue);
    if (Object.hasOwn(results, oldPlayerId)) {
      results[newPlayerId] = results[oldPlayerId];
      delete results[oldPlayerId];
    }
  }
  for (const gameValue of Object.values(record(state.sokoban_games))) {
    const game = record(gameValue);
    if (Array.isArray(game.level_speakers)) {
      game.level_speakers = [...new Set(game.level_speakers.map(String).map(
        (playerId: string) => playerId === oldPlayerId ? newPlayerId : playerId,
      ))];
    }
  }
  return state;
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
  if (!new Set([
    "player.message",
    "phase.hint",
    "qr.detected",
    "puzzle.submit",
    "puzzle.hint",
    "line_game.move",
    "line_game.reset",
    "karel.command",
    "karel.reset",
    "sokoban.command",
    "sokoban.undo",
    "sokoban.reset",
    "archive.arrange",
    "finale.activate",
    "game.deadline_choice",
    "team_game.player.restore",
    "triad.place",
    "triad.reset",
  ]).has(type)) {
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

  if (type !== "game.deadline_choice" && record(state.flags).administratively_ended) {
    return {
      state: presentGameState(scenario, state, actor, now),
      messages: [{
        type: "error",
        payload: { message: "Hra je ukončena. Po vypršení limitu můžete zvolit dohrání mimo soutěž." },
      }],
    };
  }

  let result: ScenarioCommandResult;
  if (type === "player.message") result = applyPlayerMessage(scenario, state, payload, now, actor);
  else if (type === "phase.hint") result = applyPhaseHint(scenario, state, payload);
  else if (type === "qr.detected") result = applyQrDetected(scenario, state, payload, now, actor);
  else if (type === "puzzle.submit") result = applyPuzzleSubmit(scenario, state, payload, now);
  else if (type === "puzzle.hint") result = applyPuzzleHint(scenario, state, payload);
  else if (type === "line_game.move") result = applyLineGameMove(scenario, state, payload, now, actor);
  else if (type === "line_game.reset") result = applyLineGameReset(scenario, state, payload, now, actor);
  else if (type === "karel.command") result = applyKarelCommand(scenario, state, payload, now);
  else if (type === "karel.reset") result = applyKarelReset(scenario, state, payload, now);
  else if (type === "sokoban.command") result = applySokobanCommand(scenario, state, payload, now, actor);
  else if (type === "sokoban.undo") result = applySokobanUndo(scenario, state, payload, now);
  else if (type === "sokoban.reset") result = applySokobanReset(scenario, state, payload, now);
  else if (type === "archive.arrange") result = applyArchiveArrange(scenario, state, payload);
  else if (type === "finale.activate") result = applyFinaleActivate(scenario, state, payload, now);
  else if (type === "game.deadline_choice") result = applyDeadlineChoice(state, payload);
  else if (type === "team_game.player.restore") result = applyTeamPlayerRestore(scenario, state, payload, actor);
  else if (type === "triad.place") result = applyTriadPlace(scenario, state, payload, now, actor);
  else result = applyTriadReset(scenario, state, payload, now, actor);
  return { ...result, state: presentGameState(scenario, result.state, actor, now) };
}

export function applyAdminGamePlayerExclusion(
  scenario: ScenarioDocument,
  currentState: GameStateDocument,
  puzzleIdValue: string,
  playerIdValue: string,
  now: string,
  actorValue: RuntimeActor,
): AdminGamePlayerResult {
  const actor = normalizedActor(actorValue);
  const puzzleId = String(puzzleIdValue || "").trim();
  const playerId = String(playerIdValue || "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  const adapter = puzzleAdapter(scenario, puzzle);
  const checkpointId = String(puzzle.checkpoint_id || "");
  const checkpoint = record(record(currentState.checkpoint_states)[checkpointId]);
  if (actor.teamMode !== "team" || !actor.participantIds.includes(playerId)) {
    throw new Error("Hráč do tohoto týmu nepatří.");
  }
  if (!new Set(["line_game", "triad"]).has(adapter)) {
    throw new Error("Tato minihra nepodporuje individuální správu.");
  }
  const state = clone(currentState);
  state.game_exclusions = record(state.game_exclusions);
  const excluded = Array.isArray(state.game_exclusions[puzzleId])
    ? state.game_exclusions[puzzleId].map(String)
    : [];
  const changed = !excluded.includes(playerId);
  if (!changed) {
    const result = {
      success: true,
      action: "exclude",
      changed: false,
      puzzle_id: puzzleId,
      player_id: playerId,
      player_name: actor.participantNames[playerId] || "Hráč",
      team_complete: checkpoint.status === "solved",
      team_summary: null,
    };
    return {
      state: presentGameState(scenario, state, actor, now),
      messages: [{ type: "admin.game_player", payload: result }],
      result,
    };
  }
  if (checkpoint.status !== "found") {
    throw new Error("Spravovat lze pouze aktivní minihru.");
  }
  state.last_activity_at = now;
  if (changed) excluded.push(playerId);
  state.game_exclusions[puzzleId] = excluded;
  const progress = adapter === "line_game"
    ? lineGameTeamProgress(state, puzzleId, record(puzzle.game), actor)
    : triadTeamProgress(state, puzzleId, actor);
  const messages: RuntimeMessage[] = [];
  if (progress.team_complete) {
    const mutableCheckpoint = record(record(state.checkpoint_states)[checkpointId]);
    mutableCheckpoint.status = "solved";
    mutableCheckpoint.solved_at = now;
    applyRewards(scenario, state, record(record(scenario.checkpoints)[checkpointId]).rewards);
    const defaultBonus = adapter === "line_game" ? 40 : 60;
    const bonus = Number(record(puzzle.game).team_completion_bonus ?? defaultBonus);
    state.score = Number(state.score || 0) + bonus;
    messages.push(
      {
        type: "score.update",
        payload: {
          score: state.score,
          delta: bonus,
          bonus: Math.max(0, bonus),
          penalty: Math.max(0, -bonus),
          reason: adapter === "line_game" ? "line_game_team" : "triad",
        },
      },
      { type: "puzzle.result", payload: { correct: true, puzzle_id: puzzleId, team_summary: progress } },
      { type: "bot.message", payload: messageTemplate(puzzle.success_message) },
    );
    const navigation = record(record(scenario.checkpoints)[checkpointId]).navigation_message;
    if (navigation) messages.push({ type: "bot.message", payload: messageTemplate(navigation) });
  }
  const history = Array.isArray(state.event_history) ? state.event_history : [];
  history.push({ at: now, type: "admin.game_player", details: { action: "exclude", puzzle_id: puzzleId, player_id: playerId } });
  state.event_history = history.slice(-500);
  const result = {
    success: true,
    action: "exclude",
    changed,
    puzzle_id: puzzleId,
    player_id: playerId,
    player_name: actor.participantNames[playerId] || "Hráč",
    team_complete: Boolean(progress.team_complete),
    team_summary: progress.team_complete ? progress : null,
  };
  return {
    state: presentGameState(scenario, state, actor, now),
    messages: [{ type: "admin.game_player", payload: result }, ...messages],
    result,
  };
}

function applyPlayerMessage(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
  actor: RuntimeActor,
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

  if (String(payload.channel || "general") === "lost") {
    const activeSokobanId = Object.entries(record(scenario.puzzles)).find(([, puzzleValue]) => {
      const puzzle = record(puzzleValue);
      return puzzleAdapter(scenario, puzzle) === "sokoban" &&
        record(record(state.checkpoint_states)[String(puzzle.checkpoint_id || "")]).status === "found";
    })?.[0];
    if (activeSokobanId) {
      let commands: string[] | null;
      try {
        commands = parseSokobanCommands(text);
      } catch (error) {
        return {
          state,
          messages: [{
            type: "bot.message",
            payload: {
              text: error instanceof Error ? error.message : "Neplatná sekvence.",
              mood: "error",
              channel: "lost",
            },
          }],
        };
      }
      if (commands?.[0] === "undo" && commands.length === 1) {
        return applySokobanUndo(scenario, state, { puzzle_id: activeSokobanId }, now);
      }
      if (commands?.[0] === "reset" && commands.length === 1) {
        return applySokobanReset(scenario, state, { puzzle_id: activeSokobanId }, now);
      }
      if (commands) {
        return applySokobanCommand(
          scenario,
          state,
          { puzzle_id: activeSokobanId, commands },
          now,
          actor,
        );
      }
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
  if (puzzleId && puzzleAdapter(scenario, record(record(scenario.puzzles)[puzzleId])) === "mine_karel") {
    const puzzle = record(record(scenario.puzzles)[puzzleId]);
    ensureKarelGame(state, puzzleId, record(puzzle.game), now);
  }
  if (puzzleId && puzzleAdapter(scenario, record(record(scenario.puzzles)[puzzleId])) === "sokoban") {
    const puzzle = record(record(scenario.puzzles)[puzzleId]);
    ensureSokobanGame(state, puzzleId, record(puzzle.game), now);
  }
  if (puzzleId && puzzleAdapter(scenario, record(record(scenario.puzzles)[puzzleId])) === "archive_vector") {
    const puzzle = record(record(scenario.puzzles)[puzzleId]);
    ensureArchiveGame(state, puzzleId, record(puzzle.assembly));
  }
  if (puzzleId && puzzleAdapter(scenario, record(record(scenario.puzzles)[puzzleId])) === "triad") {
    const puzzle = record(record(scenario.puzzles)[puzzleId]);
    for (const participantId of actor.participantIds.length ? actor.participantIds : [actor.clientId]) {
      ensureTriadGame(state, puzzleId, record(puzzle.game), { ...actor, clientId: participantId }, now);
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
  const adapter = puzzleAdapter(scenario, puzzle);
  if (!puzzleUsesAnswerAdapter(scenario, puzzle) && adapter !== "archive_vector") {
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
  if (adapter === "archive_vector" && !ensureArchiveGame(state, puzzleId, record(puzzle.assembly)).assembled) {
    return {
      state: presentGameState(scenario, state),
      messages: [{
        type: "puzzle.result",
        payload: { correct: false, reason: "Nejprve správně sestavte obraz rekonstrukce." },
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

function applyDeadlineChoice(
  state: GameStateDocument,
  payload: Record<string, unknown>,
): ScenarioCommandResult {
  state.flags = record(state.flags);
  const choice = String(payload.choice || "");
  if (
    !state.flags.deadline_choice_pending ||
    state.flags.administratively_ended_reason !== "deadline" ||
    !new Set(["end", "continue"]).has(choice)
  ) {
    return {
      state,
      messages: [{ type: "error", payload: { message: "Volba po vypršení času už není dostupná." } }],
    };
  }
  state.flags.deadline_choice_pending = false;
  state.flags.deadline_choice = choice;
  if (choice === "continue") {
    state.flags.out_of_competition = true;
    state.flags.administratively_ended = false;
  }
  return { state, messages: [] };
}

function applyTeamPlayerRestore(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  actor: RuntimeActor,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id || "").trim();
  const playerId = String(payload.player_id || "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  const adapter = puzzleAdapter(scenario, puzzle);
  const checkpoint = record(record(state.checkpoint_states)[String(puzzle.checkpoint_id || "")]);
  if (actor.teamMode !== "team" || !new Set(["line_game", "triad"]).has(adapter) || checkpoint.status !== "found") {
    return {
      state,
      messages: [{
        type: "team_game.player.result",
        payload: { success: false, reason: "Spoluhráče lze obnovit pouze v aktivní týmové minihře." },
      }],
    };
  }
  if (!playerId || playerId === actor.clientId || !actor.participantIds.includes(playerId)) {
    return {
      state,
      messages: [{
        type: "team_game.player.result",
        payload: { success: false, reason: "Vybraný hráč není obnovitelný spoluhráč." },
      }],
    };
  }
  state.game_exclusions = record(state.game_exclusions);
  const excluded = Array.isArray(state.game_exclusions[puzzleId])
    ? state.game_exclusions[puzzleId].map(String)
    : [];
  const restored = excluded.includes(playerId);
  state.game_exclusions[puzzleId] = excluded.filter((candidate) => candidate !== playerId);
  return {
    state,
    messages: [{
      type: "team_game.player.result",
      payload: {
        success: true,
        restored,
        puzzle_id: puzzleId,
        player_id: playerId,
        player_name: actor.participantNames[playerId] || "Hráč",
      },
    }],
  };
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

function ensureKarelGame(
  state: GameStateDocument,
  puzzleId: string,
  config: Record<string, any>,
  now: string,
): KarelState {
  state.karel_games = record(state.karel_games);
  let game = state.karel_games[puzzleId];
  if (!game || typeof game !== "object" || Array.isArray(game) || !game.deadline_at) {
    game = newKarelGame(config, now);
    state.karel_games[puzzleId] = game;
  }
  return game as KarelState;
}

function applyKarelCommand(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  const checkpointId = String(puzzle.checkpoint_id || "");
  const checkpoint = record(record(state.checkpoint_states)[checkpointId]);
  if (puzzleAdapter(scenario, puzzle) !== "mine_karel" || checkpoint.status !== "found") {
    return {
      state,
      messages: [{ type: "karel.result", payload: { success: false, reason: "Navigační pole není aktivní." } }],
    };
  }

  let result;
  try {
    result = executeKarel(
      ensureKarelGame(state, puzzleId, record(puzzle.game), now),
      record(puzzle.game),
      payload.commands,
      now,
    );
  } catch (error) {
    return {
      state,
      messages: [{
        type: "karel.result",
        payload: { success: false, reason: error instanceof Error ? error.message : "Navigaci se nepodařilo provést." },
      }],
    };
  }

  if (result.score_delta) state.score = Number(state.score || 0) + result.score_delta;
  const commandNames: Record<string, string> = {
    up: "NAHORU",
    down: "DOLŮ",
    left: "VLEVO",
    right: "VPRAVO",
  };
  const commands = Array.isArray(payload.commands) ? payload.commands.map(String) : [];
  const understood = commands.map((command) => commandNames[command] || command.toUpperCase()).join(", ");
  const messages: RuntimeMessage[] = [
    {
      type: "bot.message",
      payload: {
        text: `Rozumím sekvenci: ${understood}. Provádím.`,
        mood: "focused",
        channel: "lost",
        suppress_unread: true,
      },
    },
    { type: "karel.result", payload: result as unknown as Record<string, unknown> },
  ];
  if (result.hit_mine) {
    messages.push({
      type: "bot.message",
      payload: {
        text: "Pozor! Narazila jsem na nestabilní pole a nouzový systém mě vrátil na začátek.",
        mood: "tense",
        channel: "lost",
        voice_id: "elara_anomaly_hit",
        suppress_unread: true,
      },
    });
  } else if (result.blocked) {
    messages.push({
      type: "bot.message",
      payload: {
        text: "Tudy cesta nevede. Poslední povel by mě vyvedl mimo stabilní oblast.",
        mood: "alert",
        channel: "lost",
        suppress_unread: true,
      },
    });
  } else if (result.frames.length) {
    const lastFrame = result.frames[result.frames.length - 1];
    const clue = Number(lastFrame.clue || 0);
    let text = "Okolí je čisté, sonda nehlásí žádnou anomálii.";
    if (lastFrame.revisited) text = `Toto pole už znám. Sonda stále hlásí ${clue} okolních anomálií.`;
    else if (clue >= 3) text = `Silné rušení. V osmi okolních polích jsou ${clue} anomálie.`;
    else if (clue) text = `Sonda hlásí ${clue} okolní anomálie. Postupuji opatrně.`;
    messages.push({
      type: "bot.message",
      payload: { text, mood: "focused", channel: "lost", suppress_unread: true },
    });
  }

  if (result.game_complete) {
    checkpoint.status = "solved";
    checkpoint.solved_at = now;
    applyRewards(scenario, state, record(record(scenario.checkpoints)[checkpointId]).rewards);
    messages.push(
      { type: "puzzle.result", payload: { correct: true, puzzle_id: puzzleId } },
      { type: "bot.message", payload: messageTemplate(puzzle.success_message) },
    );
    const navigation = record(record(scenario.checkpoints)[checkpointId]).navigation_message;
    if (navigation) messages.push({ type: "bot.message", payload: messageTemplate(navigation) });
  }
  if (result.score_delta) {
    messages.push({
      type: "score.update",
      payload: {
        score: state.score,
        delta: result.score_delta,
        bonus: Math.max(0, result.score_delta),
        penalty: Math.max(0, -result.score_delta),
        reason: "mine_karel",
      },
    });
  }
  return { state, messages };
}

function applyKarelReset(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  if (puzzleAdapter(scenario, puzzle) !== "mine_karel") {
    return { state, messages: [{ type: "karel.result", payload: { success: false, reason: "Neznámé pole." } }] };
  }
  const game = ensureKarelGame(state, puzzleId, record(puzzle.game), now);
  resetKarelGame(record(puzzle.game), game, now);
  return { state, messages: [{ type: "karel.result", payload: { success: true, reset: true } }] };
}

function validSokobanGame(value: unknown): value is SokobanState {
  const game = record(value);
  return Array.isArray(game.boxes) && Array.isArray(game.player) && Boolean(game.level_id) && Boolean(game.deadline_at);
}

function ensureSokobanGame(
  state: GameStateDocument,
  puzzleId: string,
  config: Record<string, any>,
  now: string,
): SokobanState {
  state.sokoban_games = record(state.sokoban_games);
  let game = state.sokoban_games[puzzleId];
  if (!validSokobanGame(game)) {
    game = newSokobanGame(config, now);
    state.sokoban_games[puzzleId] = game;
  }
  return game as SokobanState;
}

function activeSokoban(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  puzzleId: string,
  now: string,
): { puzzle: Record<string, any>; checkpoint: Record<string, any>; game: SokobanState } {
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  if (!Object.keys(puzzle).length || puzzleAdapter(scenario, puzzle) !== "sokoban") {
    throw new Error("Neznámá sokobanová úloha.");
  }
  const checkpoint = record(record(state.checkpoint_states)[String(puzzle.checkpoint_id || "")]);
  if (!Object.keys(checkpoint).length) throw new Error("Energetická mřížka zatím nebyla nalezena.");
  if (checkpoint.status === "solved") throw new Error("Energetická mřížka už byla stabilizovaná.");
  return { puzzle, checkpoint, game: ensureSokobanGame(state, puzzleId, record(puzzle.game), now) };
}

function applySokobanCommand(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
  actor: RuntimeActor,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const commands = Array.isArray(payload.commands) ? payload.commands.map(String) : null;
  if (!commands) {
    return { state, messages: [{ type: "sokoban.result", payload: { success: false, reason: "Neplatná sekvence." } }] };
  }
  let puzzle: Record<string, any>;
  let checkpoint: Record<string, any>;
  let game: SokobanState;
  let result;
  let speakerWarning = false;
  try {
    ({ puzzle, checkpoint, game } = activeSokoban(scenario, state, puzzleId, now));
    const speakers = Array.isArray(game.level_speakers) ? game.level_speakers.map(String) : [];
    speakerWarning = Boolean(actor.clientId && speakers.length && !speakers.includes(actor.clientId));
    if (actor.clientId && !speakers.includes(actor.clientId)) game.level_speakers.push(actor.clientId);
    result = executeSokoban(game, record(puzzle.game), commands, now);
  } catch (error) {
    return {
      state,
      messages: [{
        type: "sokoban.result",
        payload: { success: false, reason: error instanceof Error ? error.message : "Sekvenci se nepodařilo provést." },
      }],
    };
  }

  const messages: RuntimeMessage[] = [{
    type: "sokoban.result",
    payload: { success: true, speaker_warning: speakerWarning, ...result },
  }];
  if (speakerWarning) {
    messages.push({
      type: "bot.message",
      payload: {
        text: "Počkejte! Teď na mě mluví někdo jiný než před chvílí. V téhle tmě se podle překřikujících hlasů opravdu orientovat nedá — domluvte si jednoho navigátora!",
        mood: "tense",
        channel: "lost",
        suppress_unread: true,
      },
    });
  }
  let summary = result.blocked
    ? `Provedla jsem ${result.executed} z ${result.requested} kroků. Další pohyb blokuje stěna nebo energetický článek.`
    : `Sekvence potvrzena: ${result.executed} kroků, přesunuté články: ${result.pushes}.`;
  if (result.level_complete && !result.game_complete) {
    summary += " Úroveň je stabilní; přepínám na další servisní sektor.";
  }
  messages.push({
    type: "bot.message",
    payload: { text: summary, mood: "focused", channel: "lost", suppress_unread: true },
  });
  if (result.score_delta) {
    state.score = Number(state.score || 0) + result.score_delta;
    messages.push({
      type: "score.update",
      payload: {
        score: state.score,
        delta: result.score_delta,
        bonus: result.score_delta,
        penalty: 0,
        reason: "sokoban_level",
        level_id: result.completed_level_id,
      },
    });
  }
  if (result.game_complete) {
    checkpoint.status = "solved";
    checkpoint.solved_at = now;
    const checkpointId = String(puzzle.checkpoint_id || "");
    applyRewards(scenario, state, record(record(scenario.checkpoints)[checkpointId]).rewards);
    messages.push(
      { type: "puzzle.result", payload: { correct: true, puzzle_id: puzzleId } },
      { type: "bot.message", payload: messageTemplate(puzzle.success_message) },
    );
    const navigation = record(record(scenario.checkpoints)[checkpointId]).navigation_message;
    if (navigation) messages.push({ type: "bot.message", payload: messageTemplate(navigation) });
  }
  return { state, messages };
}

function applySokobanUndo(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  try {
    const { game } = activeSokoban(scenario, state, puzzleId, now);
    const changed = undoSokoban(game);
    const text = changed
      ? "Vrátila jsem poslední krok."
      : "Nemám žádný krok, ke kterému se mohu vrátit.";
    return {
      state,
      messages: [
        { type: "sokoban.result", payload: { success: changed, undo: changed, reason: changed ? "" : text } },
        { type: "bot.message", payload: { text, mood: "focused", channel: "lost" } },
      ],
    };
  } catch (error) {
    return {
      state,
      messages: [{
        type: "sokoban.result",
        payload: { success: false, reason: error instanceof Error ? error.message : "Krok nelze vrátit." },
      }],
    };
  }
}

function applySokobanReset(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  try {
    const { puzzle, game } = activeSokoban(scenario, state, puzzleId, now);
    resetSokobanLevel(record(puzzle.game), game, now);
    return {
      state,
      messages: [
        { type: "sokoban.result", payload: { success: true, reset: true } },
        {
          type: "bot.message",
          payload: {
            text: "Vracíme se k poslední stabilní časové kotvě. Mřížka je znovu v počáteční poloze.",
            mood: "alert",
            channel: "lost",
          },
        },
      ],
    };
  } catch (error) {
    return {
      state,
      messages: [{
        type: "sokoban.result",
        payload: { success: false, reason: error instanceof Error ? error.message : "Mřížku nelze obnovit." },
      }],
    };
  }
}

function ensureArchiveGame(
  state: GameStateDocument,
  puzzleId: string,
  config: Record<string, any>,
): ArchiveState {
  state.archive_games = record(state.archive_games);
  let game = state.archive_games[puzzleId];
  if (!validArchiveGame(game, config)) {
    game = newArchiveGame(config);
    state.archive_games[puzzleId] = game;
  }
  const rotations = record(game.rotations);
  for (const card of Array.isArray(config.cards) ? config.cards : []) {
    rotations[String(record(card).id || "")] ??= 0;
  }
  game.rotations = rotations;
  return game as ArchiveState;
}

function applyArchiveArrange(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  const checkpoint = record(record(state.checkpoint_states)[String(puzzle.checkpoint_id || "")]);
  if (
    !Object.keys(puzzle).length ||
    puzzleAdapter(scenario, puzzle) !== "archive_vector" ||
    checkpoint.status !== "found"
  ) {
    return {
      state,
      messages: [{
        type: "archive.result",
        payload: { success: false, reason: "Archivní skládačka nyní není aktivní." },
      }],
    };
  }
  try {
    const game = ensureArchiveGame(state, puzzleId, record(puzzle.assembly));
    const result = arrangeArchive(
      game,
      record(puzzle.assembly),
      payload.card_id,
      payload.action,
      payload.target_id,
    );
    return { state, messages: [{ type: "archive.result", payload: result }] };
  } catch (error) {
    return {
      state,
      messages: [{
        type: "archive.result",
        payload: { success: false, reason: error instanceof Error ? error.message : "Dílek nelze přesunout." },
      }],
    };
  }
}

function normalizeFinaleValue(value: unknown): string {
  return String(value ?? "").toUpperCase().replace(/\s+/g, "").replaceAll(":", "").replaceAll("-", "");
}

function finaleRating(puzzle: Record<string, any>, score: number): string {
  const thresholds = Object.entries(record(puzzle.rating_thresholds))
    .map(([minimum, label]) => [Number(minimum), String(label)] as const)
    .filter(([minimum]) => Number.isFinite(minimum))
    .sort(([left], [right]) => right - left);
  return thresholds.find(([minimum]) => score >= minimum)?.[1] ?? "STABILIZOVÁNO";
}

function applyFinaleActivate(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  if (!Object.keys(puzzle).length || puzzleAdapter(scenario, puzzle) !== "finale") {
    return {
      state,
      messages: [{ type: "finale.result", payload: { success: false, reason: "Neznámý finální terminál." } }],
    };
  }
  const checkpointId = String(puzzle.checkpoint_id || "");
  state.checkpoint_states = record(state.checkpoint_states);
  const checkpoint = record(state.checkpoint_states[checkpointId]);
  if (!Object.keys(checkpoint).length) {
    return {
      state,
      messages: [{
        type: "finale.result",
        payload: { success: false, reason: "Finální terminál zatím nebyl nalezen." },
      }],
    };
  }
  state.flags = record(state.flags);
  if (checkpoint.status === "solved" || state.flags.game_completed) {
    return {
      state,
      messages: [{
        type: "finale.result",
        payload: { success: true, already_complete: true, score: Number(state.score || 0) },
      }],
    };
  }

  const missingCheckpoints = (Array.isArray(puzzle.requires_checkpoints) ? puzzle.requires_checkpoints : [])
    .map(String)
    .filter((required) => record(state.checkpoint_states[required]).status !== "solved");
  const inventory = new Set(Array.isArray(state.inventory) ? state.inventory.map(String) : []);
  const missingInventory = (Array.isArray(puzzle.requires_inventory) ? puzzle.requires_inventory : [])
    .map(String)
    .filter((required) => !inventory.has(required));
  const missingFlags = (Array.isArray(puzzle.requires_flags) ? puzzle.requires_flags : [])
    .map(String)
    .filter((required) => !state.flags[required]);
  if (missingCheckpoints.length || missingInventory.length || missingFlags.length) {
    return {
      state,
      messages: [{
        type: "finale.result",
        payload: {
          success: false,
          reason: "Stroj není kompletní. Chybí povinné kotvy, součásti nebo archivní potvrzení.",
          missing_checkpoints: missingCheckpoints,
          missing_inventory: missingInventory,
          missing_flags: missingFlags,
        },
      }],
    };
  }

  const modules = Array.isArray(payload.modules) ? payload.modules.map(normalizeFinaleValue) : [];
  const expectedModules = (Array.isArray(puzzle.module_order) ? puzzle.module_order : []).map(normalizeFinaleValue);
  state.puzzle_attempts = record(state.puzzle_attempts);
  const attempts = Number(state.puzzle_attempts[puzzleId] || 0) + 1;
  state.puzzle_attempts[puzzleId] = attempts;
  const correct = normalizeFinaleValue(payload.year) === normalizeFinaleValue(puzzle.year) &&
    normalizeFinaleValue(payload.time) === normalizeFinaleValue(puzzle.time) &&
    modules.length === expectedModules.length &&
    modules.every((module, index) => module === expectedModules[index]);
  if (!correct) {
    return {
      state,
      messages: [
        {
          type: "finale.result",
          payload: {
            success: false,
            reason: "Časové souřadnice nebo pořadí modulů nesouhlasí.",
            attempts,
          },
        },
        { type: "bot.message", payload: messageTemplate(puzzle.failure_message) },
      ],
    };
  }

  checkpoint.status = "solved";
  checkpoint.solved_at = now;
  state.checkpoint_states[checkpointId] = checkpoint;
  applyRewards(scenario, state, record(record(scenario.checkpoints)[checkpointId]).rewards);
  state.phase = String(puzzle.completion_phase || record(scenario.phase_engine).completion_phase || "portal_open");
  state.flags.game_completed = true;
  state.flags.completed_at = now;
  const score = Number(state.score || 0);
  const rating = finaleRating(puzzle, score);
  state.flags.final_rating = rating;
  const countdownSeconds = Number(puzzle.countdown_seconds ?? 10);
  const messages: RuntimeMessage[] = [{
    type: "finale.result",
    payload: { success: true, score, rating, countdown_seconds: countdownSeconds },
  }];
  for (const template of Array.isArray(puzzle.success_messages) ? puzzle.success_messages : []) {
    messages.push({ type: "bot.message", payload: messageTemplate(template) });
  }
  messages.push(
    {
      type: "effect.trigger",
      payload: { effect: "finale", intensity: 1, duration_ms: countdownSeconds * 1000 },
    },
    { type: "game.complete", payload: { score, rating, completed_at: now } },
  );
  return { state, messages };
}

function ensureTriadGame(
  state: GameStateDocument,
  puzzleId: string,
  config: Record<string, any>,
  actorValue: RuntimeActor,
  now: string,
): TriadState {
  const actor = normalizedActor(actorValue);
  state.triad_games = record(state.triad_games);
  let container = state.triad_games[puzzleId];
  const validGame = (value: unknown): value is TriadState => {
    const game = record(value);
    return Array.isArray(game.board) && Boolean(game.deadline_at) && Number(game.size) === Number(config.size ?? 5);
  };
  if (actor.teamMode === "solo" && actor.participantIds.length === 1) {
    if (record(container).players) container = record(record(container).players)[actor.clientId];
    if (!validGame(container)) container = newTriadGame(config, now);
    state.triad_games[puzzleId] = container;
    return container as TriadState;
  }
  if (validGame(container)) container = { players: { [actor.clientId]: container } };
  if (!container || typeof container !== "object" || Array.isArray(container) || !record(container).players) {
    container = { players: {} };
  }
  state.triad_games[puzzleId] = container;
  const players = record(container.players);
  if (!validGame(players[actor.clientId])) players[actor.clientId] = newTriadGame(config, now);
  container.players = players;
  return players[actor.clientId] as TriadState;
}

function triadPlayers(state: GameStateDocument, puzzleId: string, actor: RuntimeActor): Record<string, any> {
  const container = record(record(state.triad_games)[puzzleId]);
  if (actor.teamMode === "solo" && actor.participantIds.length === 1 && Array.isArray(container.board)) {
    return { [actor.clientId]: container };
  }
  return record(container.players);
}

function triadTeamProgress(
  state: GameStateDocument,
  puzzleId: string,
  actorValue: RuntimeActor,
): Record<string, unknown> {
  const actor = normalizedActor(actorValue);
  const players = triadPlayers(state, puzzleId, actor);
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
    const conditions = Array.isArray(game.completed_orientations)
      ? [...new Set(game.completed_orientations.map(String))].sort()
      : [];
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
  const allConditions = ["diagonal", "horizontal", "vertical"];
  const missing = allConditions.filter((condition) => !covered.has(condition));
  return {
    players: summaries,
    covered_conditions: [...covered].sort(),
    missing_conditions: missing,
    recommendation: missing.length === 1 ? missing[0] : null,
    team_complete: teamComplete,
  };
}

function applyTriadPlace(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
  actor: RuntimeActor,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const excluded = Array.isArray(record(state.game_exclusions)[puzzleId])
    ? record(state.game_exclusions)[puzzleId].map(String)
    : [];
  if (excluded.includes(actor.clientId)) {
    return {
      state,
      messages: [{ type: "triad.result", payload: { success: false, reason: "Game Master vás z této týmové minihry dočasně vyřadil." } }],
    };
  }
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  const checkpointId = String(puzzle.checkpoint_id || "");
  const checkpoint = record(record(state.checkpoint_states)[checkpointId]);
  if (puzzleAdapter(scenario, puzzle) !== "triad" || checkpoint.status !== "found") {
    return { state, messages: [{ type: "triad.result", payload: { success: false, reason: "Pole není aktivní." } }] };
  }

  const game = ensureTriadGame(state, puzzleId, record(puzzle.game), actor, now);
  let result;
  try {
    result = placeTriad(
      game,
      record(puzzle.game),
      Number(payload.row ?? -1),
      Number(payload.column ?? -1),
      String(payload.symbol ?? ""),
      now,
    );
  } catch (error) {
    return {
      state,
      messages: [{
        type: "triad.result",
        payload: { success: false, reason: error instanceof Error ? error.message : "Tah se nepodařilo provést." },
      }],
    };
  }

  let teamProgress = triadTeamProgress(state, puzzleId, actor);
  const resultPayload: Record<string, unknown> = {
    ...result,
    team_complete: Boolean(teamProgress.team_complete),
  };
  const messages: RuntimeMessage[] = [{ type: "triad.result", payload: resultPayload }];
  if (result.game_complete) {
    state.game_results = record(state.game_results);
    const results = record(state.game_results[puzzleId]);
    state.game_results[puzzleId] = results;
    if (!Object.hasOwn(results, actor.clientId)) {
      const scoreDelta = Number(record(puzzle.game).individual_completion_bonus ?? 20);
      results[actor.clientId] = {
        elapsed_seconds: Math.max(0, Math.floor((Date.parse(now) - Date.parse(String(game.started_at))) / 1000)),
        score_delta: scoreDelta,
        conditions: [...new Set((game.completed_orientations as unknown[]).map(String))].sort(),
      };
      state.score = Number(state.score || 0) + scoreDelta;
      messages.push({
        type: "score.update",
        payload: { score: state.score, delta: scoreDelta, bonus: scoreDelta, penalty: 0, reason: "triad_individual" },
      });
    }
    teamProgress = triadTeamProgress(state, puzzleId, actor);
    resultPayload.team_complete = Boolean(teamProgress.team_complete);
  }
  if (teamProgress.team_complete) {
    checkpoint.status = "solved";
    checkpoint.solved_at = now;
    applyRewards(scenario, state, record(record(scenario.checkpoints)[checkpointId]).rewards);
    const bonus = actor.teamMode === "team" ? Number(record(puzzle.game).team_completion_bonus ?? 60) : 0;
    state.score = Number(state.score || 0) + bonus;
    resultPayload.team_summary = teamProgress;
    messages.push(
      { type: "score.update", payload: { score: state.score, delta: bonus, bonus, penalty: 0, reason: "triad" } },
      { type: "puzzle.result", payload: { correct: true, puzzle_id: puzzleId } },
      { type: "bot.message", payload: messageTemplate(puzzle.success_message) },
    );
    const navigation = record(record(scenario.checkpoints)[checkpointId]).navigation_message;
    if (navigation) messages.push({ type: "bot.message", payload: messageTemplate(navigation) });
  }
  return { state, messages };
}

function applyTriadReset(
  scenario: ScenarioDocument,
  state: GameStateDocument,
  payload: Record<string, unknown>,
  now: string,
  actor: RuntimeActor,
): ScenarioCommandResult {
  const puzzleId = String(payload.puzzle_id ?? "").trim();
  const puzzle = record(record(scenario.puzzles)[puzzleId]);
  if (puzzleAdapter(scenario, puzzle) !== "triad") {
    return { state, messages: [{ type: "triad.result", payload: { success: false, reason: "Neznámé pole." } }] };
  }
  resetTriadGame(
    record(puzzle.game),
    ensureTriadGame(state, puzzleId, record(puzzle.game), actor, now),
    now,
  );
  return { state, messages: [{ type: "triad.result", payload: { success: true, reset: true } }] };
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
    const terminal = record(puzzle.terminal);
    if (new Set(["exclusive", "mirror"]).has(String(terminal.mode || "off"))) {
      presented.terminal = {
        mode: String(terminal.mode),
        label: String(terminal.label || puzzle.title || "Herní terminál").slice(0, 80),
      };
    }
    if (checkpointState.status === "found" || checkpointState.status === "solved") {
      presented.instructions = String(puzzle.instructions || "");
      presented.image = puzzle.image ?? null;
      presented.categories = clone(record(puzzle.categories));
      presented.clues = Array.isArray(puzzle.clues) ? clone(puzzle.clues) : [];
      presented.ciphertext = String(puzzle.ciphertext || "");
    }
    if (
      actorValue &&
      puzzleAdapter(scenario, puzzle) === "line_game" &&
      (checkpointState.status === "found" || checkpointState.status === "solved")
    ) {
      const game = ensureLineGame(state, puzzleId, record(puzzle.game), actor, now);
      presented.game = publicLineGame(record(puzzle.game), game, now);
      presented.team_progress = lineGameTeamProgress(state, puzzleId, record(puzzle.game), actor);
    }
    if (
      puzzleAdapter(scenario, puzzle) === "mine_karel" &&
      (checkpointState.status === "found" || checkpointState.status === "solved")
    ) {
      const game = ensureKarelGame(state, puzzleId, record(puzzle.game), now);
      presented.game = publicKarelGame(record(puzzle.game), game, now);
    }
    if (
      puzzleAdapter(scenario, puzzle) === "sokoban" &&
      (checkpointState.status === "found" || checkpointState.status === "solved")
    ) {
      const game = ensureSokobanGame(state, puzzleId, record(puzzle.game), now);
      presented.game = publicSokobanGame(record(puzzle.game), game, now);
    }
    if (
      puzzleAdapter(scenario, puzzle) === "archive_vector" &&
      (checkpointState.status === "found" || checkpointState.status === "solved")
    ) {
      const game = ensureArchiveGame(state, puzzleId, record(puzzle.assembly));
      presented.archive_game = publicArchiveGame(record(puzzle.assembly), game);
    }
    if (
      puzzleAdapter(scenario, puzzle) === "finale" &&
      (checkpointState.status === "found" || checkpointState.status === "solved")
    ) {
      presented.finale = {
        module_labels: Array.isArray(puzzle.module_labels) ? puzzle.module_labels.map(String) : [],
        countdown_seconds: Number(puzzle.countdown_seconds ?? 10),
      };
    }
    if (
      actorValue &&
      puzzleAdapter(scenario, puzzle) === "triad" &&
      (checkpointState.status === "found" || checkpointState.status === "solved")
    ) {
      const game = ensureTriadGame(state, puzzleId, record(puzzle.game), actor, now);
      presented.game = publicTriadGame(record(puzzle.game), game, now);
      presented.team_progress = triadTeamProgress(state, puzzleId, actor);
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
