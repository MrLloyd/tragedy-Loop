import { protagonistSeats, type SeatId } from '../../contracts/src/index.js';
import { randomInt } from 'node:crypto';
import { createBaseDeck } from './actions.js';
import { validateConfiguration } from './validation.js';
import type {
  BoardAreaId,
  CharacterState,
  ContentCatalog,
  GameState,
  ScriptState,
} from './model.js';

export interface NewGameInput {
  script: ScriptState;
  characters: CharacterState[];
  contentVersion?: string;
  secretLetters?: Partial<Record<SeatId, 'A' | 'B' | 'C'>>;
}

export function validateNewGame(input: NewGameInput, catalog: ContentCatalog): string[] {
  const errors: string[] = [];
  const module = catalog.modules[input.script.moduleId];
  if (!module) return [`UNKNOWN_MODULE:${input.script.moduleId}`];
  errors.push(...validateConfiguration(input, catalog));
  if (input.script.loops < 1) errors.push('LOOPS_MUST_BE_POSITIVE');
  if (input.script.daysPerLoop < 1) errors.push('DAYS_MUST_BE_POSITIVE');
  const ids = input.characters.map((c) => c.id);
  if (new Set(ids).size !== ids.length) errors.push('DUPLICATE_CHARACTER');
  const rules = input.script.ruleIds.map((id) => ({ id, type: id.includes('.y.') ? 'y' : 'x' }));
  if (rules.filter((r) => r.type === 'y').length !== module.ruleSelection.y)
    errors.push('WRONG_RULE_Y_COUNT');
  if (rules.filter((r) => r.type === 'x').length !== module.ruleSelection.x)
    errors.push('WRONG_RULE_X_COUNT');
  for (const rule of rules)
    if (!module.rules.includes(rule.id)) errors.push(`RULE_NOT_IN_MODULE:${rule.id}`);
  const days = input.script.incidents.map((i) => i.day);
  if (new Set(days).size !== days.length) errors.push('MORE_THAN_ONE_INCIDENT_PER_DAY');
  for (const incident of input.script.incidents) {
    if (incident.day < 1 || incident.day > input.script.daysPerLoop)
      errors.push(`INCIDENT_DAY_OUT_OF_RANGE:${incident.entryId}`);
    if (!module.incidents.includes(incident.incidentId))
      errors.push(`INCIDENT_NOT_IN_MODULE:${incident.incidentId}`);
    if (!incident.crowdArea && incident.culpritIds.some((id) => !ids.includes(id)))
      errors.push(`UNKNOWN_INCIDENT_CULPRIT:${incident.entryId}`);
  }
  const identityCounts = new Map<string, number>();
  for (const character of input.characters) {
    if (!catalog.characters[character.definitionId])
      errors.push(`UNKNOWN_CHARACTER:${character.definitionId}`);
    const identity = catalog.identities[character.configuredIdentity];
    if (!identity) errors.push(`UNKNOWN_IDENTITY:${character.configuredIdentity}`);
    if (!['outsider', 'copycat'].includes(character.definitionId) && !character.reverseIdentity)
      identityCounts.set(
        character.configuredIdentity,
        (identityCounts.get(character.configuredIdentity) ?? 0) + 1,
      );
    if (character.definitionId === 'temp_worker_alt')
      errors.push('TEMP_WORKER_ALT_CANNOT_BE_CONFIGURED');
  }
  for (const [identityId, count] of identityCounts) {
    const max = module.identityLimits?.[identityId] ?? catalog.identities[identityId]?.max;
    if (max !== undefined && count > max) errors.push(`IDENTITY_LIMIT:${identityId}`);
  }
  if (input.script.moduleId === 'last_liar' && protagonistSeats.length !== 3)
    errors.push('LAST_LIAR_REQUIRES_FOUR_PLAYERS');
  return [...new Set(errors)].sort();
}

export function createGame(input: NewGameInput, catalog: ContentCatalog): GameState {
  const errors = validateNewGame(input, catalog);
  if (errors.length) throw new Error(`INVALID_SCRIPT:${errors.join(',')}`);
  const board = Object.fromEntries(
    (['shrine', 'hospital', 'city', 'school'] as BoardAreaId[]).map((id) => [id, { intrigue: 0 }]),
  ) as GameState['board'];
  const cards = {
    mastermind: createBaseDeck('mastermind'),
    protagonistA: createBaseDeck('protagonistA'),
    protagonistB: createBaseDeck('protagonistB'),
    protagonistC: createBaseDeck('protagonistC'),
  };
  const letters = ['A', 'B', 'C'] as const;
  const shuffled = [...letters];
  if (input.script.moduleId === 'last_liar' && !input.secretLetters) {
    for (let index = shuffled.length - 1; index > 0; index--) {
      const other = randomInt(index + 1);
      [shuffled[index], shuffled[other]] = [shuffled[other]!, shuffled[index]!];
    }
  }
  const secretLetters =
    input.script.moduleId === 'last_liar'
      ? (input.secretLetters ??
        Object.fromEntries(protagonistSeats.map((seat, i) => [seat, shuffled[i]!])))
      : {};
  if (
    input.script.moduleId === 'last_liar' &&
    (secretLetters.mastermind ||
      new Set(protagonistSeats.map((seat) => secretLetters[seat])).size !== 3 ||
      protagonistSeats.some((seat) => !letters.includes(secretLetters[seat]!)))
  )
    throw new Error('INVALID_SECRET_LETTERS');
  const traitorLetters = new Set(
    input.script.ruleIds
      .map((id) => catalog.rules?.[id]?.name)
      .flatMap((name) =>
        name === '真正的怪物'
          ? ['A']
          : name === '神话收集者'
            ? ['B']
            : name === '我才是名侦探'
              ? ['C']
              : [],
      ),
  );
  return {
    schemaVersion: 2,
    revision: 0,
    contentVersion: input.contentVersion ?? catalog.version,
    status: 'ready',
    script: structuredClone(input.script),
    clock: { loop: 1, day: 1, phase: 'setup', node: 'setup.validate', phaseInstance: 0 },
    leader: 'protagonistA',
    board,
    characters: Object.fromEntries(input.characters.map((c) => [c.id, structuredClone(c)])),
    cards,
    placements: [],
    curses: [],
    ex: 0,
    protagonistProtection: false,
    traitors: protagonistSeats.filter((seat) => traitorLetters.has(secretLetters[seat] ?? '')),
    secretLetters,
    records: {
      loopFailed: false,
      protagonistsDead: false,
      endRequests: [],
      usage: {},
      revealedFacts: [],
      incidentHistory: [],
      loopIncidentEntryIds: [],
      firstIncidentDay: null,
      worldMovedToday: false,
      worldMoveIncrementApplied: false,
      exIncreasedThisLoop: false,
      delayed: [],
      previousLoop: null,
      sourceOutcomes: {},
    },
    result: null,
    publicLog: [],
  };
}

export function usageKey(
  sourceId: string,
  scope: 'phase' | 'day' | 'loop' | 'game',
  state: GameState,
  sharedKey?: string,
): string {
  const id = sharedKey ?? sourceId;
  if (scope === 'game') return `game:${id}`;
  if (scope === 'loop') return `loop:${state.clock.loop}:${id}`;
  if (scope === 'day') return `day:${state.clock.loop}:${state.clock.day}:${id}`;
  return `phase:${state.clock.phaseInstance}:${id}`;
}

export function rotateLeader(leader: SeatId): SeatId {
  const index = protagonistSeats.indexOf(leader as (typeof protagonistSeats)[number]);
  return protagonistSeats[(index + 1) % protagonistSeats.length]!;
}
