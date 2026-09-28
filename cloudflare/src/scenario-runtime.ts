export type ScenarioDocument = Record<string, any>;
export type GameStateDocument = Record<string, any>;

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

function messageTemplate(value: unknown, replacement = ""): Record<string, unknown> {
  const payload = clone(record(value));
  if (typeof payload.text === "string") payload.text = payload.text.replaceAll("{text}", replacement);
  return payload;
}

export function startScenario(
  scenario: ScenarioDocument,
  scoreAdjustment: number,
  now: string,
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
    state: presentGameState(scenario, state),
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
): ScenarioCommandResult {
  if (!new Set(["player.message", "phase.hint"]).has(type)) {
    return {
      state: presentGameState(scenario, currentState),
      messages: [{ type: "command.rejected", payload: { reason: `Příkaz ${type} ještě není v cloudovém enginu podporován.` } }],
    };
  }
  const state = clone(currentState);
  state.last_activity_at = now;
  const history = Array.isArray(state.event_history) ? state.event_history : [];
  history.push({ at: now, type, details: {} });
  state.event_history = history.slice(-500);

  if (type === "player.message") return applyPlayerMessage(scenario, state, payload);
  return applyPhaseHint(scenario, state, payload);
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
  if (!Number.isInteger(requested) || requested < 0 || requested >= hints.length || requested > unlocked) {
    return {
      state: presentGameState(scenario, state),
      messages: [{ type: "error", payload: { message: "Neplatný stupeň nápovědy." } }],
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

export function presentGameState(
  scenario: ScenarioDocument,
  stateValue: GameStateDocument,
): GameStateDocument {
  const state = clone(stateValue);
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
    return {
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
