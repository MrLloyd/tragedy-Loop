import type { SeatId } from '../../contracts/src/index.js';
import type {
  ActionCardState,
  ActionKind,
  ActionPlacement,
  AreaId,
  ContentCatalog,
  DomainEvent,
  EffectIntent,
  GameState,
  PlacementTarget,
} from './model.js';
import { evaluatePersistent } from './persistent.js';
import { commitBatch, legalMoveDestinations, movementFollowers } from './resolution.js';

const protagonistKinds = new Set<ActionKind>([
  'goodwill+1',
  'goodwill+2',
  'anxiety+1',
  'anxiety-1',
  'move-horizontal',
  'move-vertical',
  'forbid-intrigue',
  'forbid-movement',
  'hope+1',
  'anxiety+2',
]);

export function createBaseDeck(owner: SeatId): ActionCardState[] {
  const kinds: ActionKind[] =
    owner === 'mastermind'
      ? [
          'intrigue+2',
          'intrigue+1',
          'anxiety+1',
          'anxiety+1',
          'anxiety-1',
          'move-horizontal',
          'move-vertical',
          'move-diagonal',
          'forbid-goodwill',
          'forbid-anxiety',
        ]
      : [
          'goodwill+1',
          'goodwill+2',
          'anxiety+1',
          'anxiety-1',
          'move-horizontal',
          'move-vertical',
          'forbid-intrigue',
          'forbid-movement',
        ];
  return kinds.map((kind, index) => ({
    id: `${owner}:${kind}:${index + 1}`,
    kind,
    owner,
    oncePerLoop:
      ['intrigue+2', 'move-diagonal', 'goodwill+2', 'forbid-movement'].includes(kind) ||
      (kind === 'anxiety-1' && owner !== 'mastermind'),
    zone: 'hand',
  }));
}

export function legalActionTargets(
  state: GameState,
  catalog: ContentCatalog,
  owner: SeatId,
  card: ActionCardState,
): PlacementTarget[] {
  if (card.owner !== owner || card.zone !== 'hand') return [];
  if (owner !== 'mastermind' && !protagonistKinds.has(card.kind)) return [];
  const effective = evaluatePersistent(state, catalog, 'action:placement');
  const occupied = new Set(
    state.placements
      .filter((p) => (owner === 'mastermind') === (p.owner === 'mastermind'))
      .map((p) => `${p.target.kind}:${p.target.id}`),
  );
  const characters = Object.values(state.characters)
    .filter(
      (c) =>
        c.alive &&
        c.presence === 'board' &&
        c.definitionId !== 'fantasy' &&
        !effective.characters[c.id]?.placementBanned &&
        !effective.characters[c.id]?.placementBannedFor.includes(owner) &&
        !occupied.has(`character:${c.id}`),
    )
    .map((c) => ({ kind: 'character' as const, id: c.id }));
  const areas = Object.keys(state.board)
    .filter((id) => !occupied.has(`area:${id}`))
    .map((id) => ({ kind: 'area' as const, id }));
  return [...characters, ...areas];
}

export function placeAction(
  state: GameState,
  catalog: ContentCatalog,
  owner: SeatId,
  cardId: string,
  target: PlacementTarget,
): void {
  const card = state.cards[owner].find((c) => c.id === cardId);
  if (!card) throw new Error('UNKNOWN_ACTION_CARD');
  const legal = legalActionTargets(state, catalog, owner, card).some(
    (candidate) => candidate.kind === target.kind && candidate.id === target.id,
  );
  if (!legal) throw new Error('ILLEGAL_ACTION_TARGET');
  card.zone = 'placed';
  state.placements.push({
    id: `placement:${state.clock.loop}:${state.clock.day}:${state.placements.length + 1}`,
    cardId,
    owner,
    target,
    revealed: false,
    affectedCharacterIds: [],
    effective: true,
  });
  state.revision++;
}

function affected(state: GameState, placement: ActionPlacement): string[] {
  if (placement.target.kind === 'character') return [placement.target.id];
  return Object.values(state.characters)
    .filter(
      (c) =>
        c.alive &&
        c.presence === 'board' &&
        c.area === placement.target.id &&
        c.definitionId === 'fantasy',
    )
    .map((c) => c.id)
    .sort();
}

function card(state: GameState, placement: ActionPlacement): ActionCardState {
  const found = state.cards[placement.owner].find((c) => c.id === placement.cardId);
  if (!found) throw new Error('PLACED_CARD_MISSING');
  return found;
}

export function moveDestination(area: AreaId, kinds: ActionKind[]): AreaId | null {
  if (area === 'faraway' || kinds.length === 0) return null;
  let horizontal = 0;
  let vertical = 0;
  for (const kind of new Set(kinds)) {
    if (kind === 'move-horizontal') horizontal ^= 1;
    if (kind === 'move-vertical') vertical ^= 1;
    if (kind === 'move-diagonal') {
      horizontal ^= 1;
      vertical ^= 1;
    }
  }
  if (!horizontal && !vertical) return null;
  const coordinates: Record<string, [number, number]> = {
    hospital: [0, 0],
    shrine: [1, 0],
    city: [0, 1],
    school: [1, 1],
  };
  const names: Record<string, AreaId> = {
    '0,0': 'hospital',
    '1,0': 'shrine',
    '0,1': 'city',
    '1,1': 'school',
  };
  const [x, y] = coordinates[area]!;
  return names[`${horizontal ? 1 - x : x},${vertical ? 1 - y : y}`] ?? null;
}

export interface ActionResolutionResult {
  state: GameState;
  events: DomainEvent[];
  batches: Array<{ stage: 'movement' | 'increase' | 'decrease'; changed: boolean }>;
}

export function actionMovementPlan(
  before: GameState,
  catalog: ContentCatalog,
): { intents: EffectIntent[]; followers: Record<string, string[]> } {
  let state = structuredClone(before);
  for (const placement of state.placements) {
    placement.revealed = true;
    placement.affectedCharacterIds = affected(state, placement);
  }
  const movementIntents: EffectIntent[] = [];
  for (const characterState of Object.values(state.characters)) {
    if (!characterState.alive || characterState.presence !== 'board') continue;
    const applicable = state.placements.filter((p) =>
      p.affectedCharacterIds.includes(characterState.id),
    );
    const kinds = applicable.map((p) => card(state, p).kind);
    const forbid =
      kinds.includes('forbid-movement') ||
      (state.script.ruleIds.includes('mz.x.mutual_understanding') &&
        kinds.includes('forbid-goodwill'));
    if (forbid) continue;
    const destination = moveDestination(
      characterState.area,
      kinds.filter((kind) => kind.startsWith('move-')),
    );
    if (
      destination &&
      destination !== characterState.area &&
      legalMoveDestinations(state, catalog, characterState.id).includes(destination)
    )
      movementIntents.push({
        id: `action:move:${characterState.id}`,
        sourceInstanceId: 'action-resolution',
        effectId: 'movement',
        targetId: characterState.id,
        operation: { kind: 'move-character', destination },
      });
  }
  const followers = movementFollowers(before, catalog, movementIntents);
  return { intents: movementIntents, followers };
}

export function resolveActionMovement(
  before: GameState,
  catalog: ContentCatalog,
  choices: Record<string, string> = {},
) {
  const plan = actionMovementPlan(before, catalog);
  const result = commitBatch(before, catalog, plan.intents, choices);
  for (const placement of result.state.placements) placement.revealed = true;
  return result;
}

export function cultistForbids(
  state: GameState,
  catalog: ContentCatalog,
): Record<string, string[]> {
  const effective = evaluatePersistent(state, catalog);
  return Object.fromEntries(
    Object.values(state.characters)
      .filter(
        (c) =>
          c.alive && c.presence === 'board' && effective.characters[c.id]!.identity === 'cultist',
      )
      .map((c) => [
        c.id,
        state.placements
          .filter(
            (p) =>
              card(state, p).kind === 'forbid-intrigue' &&
              (p.target.kind === 'area'
                ? p.target.id === c.area
                : state.characters[p.target.id]?.area === c.area),
          )
          .map((p) => p.id),
      ]),
  );
}

export function resolveActionCounters(
  before: GameState,
  catalog: ContentCatalog,
  ignoredForbids: string[] = [],
): ActionResolutionResult {
  let state = structuredClone(before);
  for (const placement of state.placements)
    placement.affectedCharacterIds = affected(state, placement);

  const doubleIntrigueBan =
    state.placements.filter((p) => card(state, p).kind === 'forbid-intrigue').length >= 2;
  const doubleHope = state.placements.filter((p) => card(state, p).kind === 'hope+1').length >= 2;
  const oldSeal = state.script.moduleId === 'weird_mythology' && state.ex >= 3;
  const increaseIntents: EffectIntent[] = [];
  const decreaseIntents: EffectIntent[] = [];
  for (const placement of state.placements) {
    const action = card(state, placement);
    const targetIds = placement.affectedCharacterIds;
    const peerKinds = state.placements
      .filter(
        (p) =>
          p.target.kind === placement.target.kind &&
          p.target.id === placement.target.id &&
          !ignoredForbids.includes(p.id),
      )
      .map((p) => card(state, p).kind);
    let counter: 'goodwill' | 'anxiety' | 'intrigue' | 'hope' | 'despair' | null = null;
    let amount = 0;
    if (action.kind === 'goodwill+1') [counter, amount] = ['goodwill', 1];
    if (action.kind === 'goodwill+2') [counter, amount] = ['goodwill', 2];
    if (action.kind === 'anxiety+1') [counter, amount] = ['anxiety', 1];
    if (action.kind === 'anxiety+2') [counter, amount] = ['anxiety', 2];
    if (action.kind === 'intrigue+1') [counter, amount] = ['intrigue', 1];
    if (action.kind === 'intrigue+2') [counter, amount] = ['intrigue', 2];
    if (action.kind === 'hope+1') [counter, amount] = doubleHope ? ['goodwill', 1] : ['hope', 1];
    if (action.kind === 'despair+1') [counter, amount] = ['despair', 1];
    if (action.kind === 'anxiety-1') [counter, amount] = ['anxiety', -1];
    if (!counter) continue;
    const identity =
      placement.target.kind === 'character'
        ? evaluatePersistent(state, catalog).characters[placement.target.id]?.identity
        : undefined;
    const ignoresGoodwillBan = identity === 'time_traveler' || identity === 'dimension_traveler';
    const blocked =
      (counter === 'goodwill' && peerKinds.includes('forbid-goodwill') && !ignoresGoodwillBan) ||
      (counter === 'anxiety' && peerKinds.includes('forbid-anxiety')) ||
      (counter === 'intrigue' &&
        peerKinds.includes('forbid-intrigue') &&
        !(doubleIntrigueBan && !oldSeal));
    if (blocked && !['hope', 'despair'].includes(counter)) continue;
    const destinations =
      placement.target.kind === 'area' && counter === 'intrigue'
        ? [placement.target.id, ...targetIds]
        : targetIds;
    for (const targetId of destinations) {
      const intent: EffectIntent = {
        id: `action:${placement.id}:${targetId}`,
        sourceInstanceId: 'action-resolution',
        effectId: placement.id,
        targetId,
        operation: { kind: 'counter', counter, amount },
      };
      (amount >= 0 ? increaseIntents : decreaseIntents).push(intent);
    }
  }
  const increase = commitBatch(state, catalog, increaseIntents);
  state = increase.state;
  const decrease = commitBatch(state, catalog, decreaseIntents);
  state = decrease.state;
  for (const placement of state.placements) {
    const action = card(state, placement);
    if (action.kind === 'hope+1' && doubleHope) action.zone = 'hand';
    else if (action.kind === 'hope+1') {
      for (const deck of Object.values(state.cards))
        for (const c of deck) if (c.kind === 'hope+1') c.zone = 'excluded';
    } else action.zone = action.oncePerLoop ? 'used' : 'hand';
  }
  state.placements = [];
  state.revision++;
  return {
    state,
    events: [...increase.result.events, ...decrease.result.events],
    batches: [
      { stage: 'increase', changed: increase.result.changed },
      { stage: 'decrease', changed: decrease.result.changed },
    ],
  };
}

export function resolveActions(
  before: GameState,
  catalog: ContentCatalog,
  choices: { followers?: Record<string, string>; ignoredForbids?: string[] } = {},
): ActionResolutionResult {
  const movement = resolveActionMovement(before, catalog, choices.followers);
  const counters = resolveActionCounters(movement.state, catalog, choices.ignoredForbids);
  return {
    state: counters.state,
    events: [...movement.result.events, ...counters.events],
    batches: [{ stage: 'movement', changed: movement.result.changed }, ...counters.batches],
  };
}
