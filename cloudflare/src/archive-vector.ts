export type ArchiveConfig = Record<string, any>;
export type ArchiveState = Record<string, any>;

export interface ArchiveArrangeResult extends Record<string, unknown> {
  success: true;
  assembled: boolean;
}

function configuredCards(config: ArchiveConfig): Array<Record<string, any>> {
  return Array.isArray(config.cards)
    ? config.cards.filter((card): card is Record<string, any> => Boolean(card) && typeof card === "object" && !Array.isArray(card))
    : [];
}

function cardIds(config: ArchiveConfig): string[] {
  return configuredCards(config).map((card) => String(card.id ?? ""));
}

function sameCardSet(left: unknown, right: string[]): boolean {
  if (!Array.isArray(left) || left.length !== right.length) return false;
  return new Set(left.map(String)).size === right.length && right.every((cardId) => left.map(String).includes(cardId));
}

export function newArchiveGame(config: ArchiveConfig): ArchiveState {
  const ids = cardIds(config);
  if (!ids.length || ids.some((cardId) => !cardId) || new Set(ids).size !== ids.length) {
    throw new Error("Archivní skládačka vyžaduje unikátní karty.");
  }
  const initialOrder = Array.isArray(config.initial_order) ? config.initial_order.map(String) : [...ids];
  if (!sameCardSet(initialOrder, ids)) throw new Error("Počáteční pořadí archivních karet není platné.");
  const rotations = Object.fromEntries(
    Object.entries(config.initial_rotations && typeof config.initial_rotations === "object"
      ? config.initial_rotations as Record<string, unknown>
      : {}).map(([cardId, rotation]) => [cardId, normalizedRotation(rotation)]),
  );
  for (const cardId of ids) rotations[cardId] ??= 0;
  return { order: initialOrder, rotations, moves: 0, assembled: false };
}

export function validArchiveGame(value: unknown, config: ArchiveConfig): value is ArchiveState {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return sameCardSet((value as ArchiveState).order, cardIds(config));
}

export function publicArchiveGame(config: ArchiveConfig, state: ArchiveState): Record<string, unknown> {
  const cards = Object.fromEntries(configuredCards(config).map((card) => {
    const id = String(card.id);
    return [id, {
      id,
      label: String(card.label ?? id),
      color: String(card.color ?? "cyan"),
      icon: String(card.icon ?? "◇"),
      source_index: Number(card.source_index ?? 0),
    }];
  }));
  const assembled = Boolean(state.assembled);
  return {
    order: [...state.order],
    rotations: { ...state.rotations },
    moves: Number(state.moves ?? 0),
    assembled,
    cards,
    mode: String(config.mode ?? "cards"),
    image: String(config.image ?? ""),
    grid_size: Number(config.grid_size ?? 3),
    revealed_key: assembled ? String(config.revealed_key ?? "") : "",
    module_order: assembled && Array.isArray(config.module_order) ? config.module_order.map(String) : [],
  };
}

export function arrangeArchive(
  state: ArchiveState,
  config: ArchiveConfig,
  cardIdValue: unknown,
  actionValue: unknown,
  targetIdValue?: unknown,
): ArchiveArrangeResult {
  const cardId = String(cardIdValue ?? "");
  const action = String(actionValue ?? "");
  const order = state.order as string[];
  if (!order.includes(cardId)) throw new Error("Neznámá archivní karta.");
  const index = order.indexOf(cardId);
  if (action === "left" && index > 0) {
    [order[index - 1], order[index]] = [order[index], order[index - 1]];
  } else if (action === "right" && index < order.length - 1) {
    [order[index + 1], order[index]] = [order[index], order[index + 1]];
  } else if (action === "rotate") {
    state.rotations[cardId] = (normalizedRotation(state.rotations[cardId]) + 90) % 360;
  } else if (action === "swap") {
    const targetId = String(targetIdValue ?? "");
    if (!order.includes(targetId) || targetId === cardId) throw new Error("Vyberte dva různé dílky.");
    const targetIndex = order.indexOf(targetId);
    [order[index], order[targetIndex]] = [order[targetIndex], order[index]];
  } else {
    throw new Error("Kartu tímto směrem nelze posunout.");
  }
  state.moves = Number(state.moves ?? 0) + 1;
  const correctOrder = Array.isArray(config.correct_order) ? config.correct_order.map(String) : [];
  const correctRotations = Object.fromEntries(
    Object.entries(config.correct_rotations && typeof config.correct_rotations === "object"
      ? config.correct_rotations as Record<string, unknown>
      : {}).map(([configuredCardId, rotation]) => [configuredCardId, normalizedRotation(rotation)]),
  );
  state.assembled = order.length === correctOrder.length &&
    order.every((item, orderIndex) => item === correctOrder[orderIndex]) &&
    Object.entries(correctRotations).every(
      ([configuredCardId, rotation]) => normalizedRotation(state.rotations[configuredCardId]) === rotation,
    );
  return { success: true, assembled: Boolean(state.assembled) };
}

function normalizedRotation(value: unknown): number {
  const rotation = Math.trunc(Number(value) || 0) % 360;
  return rotation < 0 ? rotation + 360 : rotation;
}
