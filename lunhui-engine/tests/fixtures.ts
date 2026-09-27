import { createCatalog, firstStepsScenario } from '../packages/content/src/index.js';
import {
  createGame,
  Engine,
  blankCounters,
  type CharacterState,
  type ContentCatalog,
  type GameState,
  type RuleSourceDefinition,
} from '../packages/engine/src/index.js';
export function fixture(): { catalog: ContentCatalog; state: GameState } {
  const catalog = createCatalog();
  return { catalog, state: createGame(firstStepsScenario(), catalog) };
}
export function character(
  id: string,
  identity = 'civilian',
  changes: Partial<CharacterState> = {},
): CharacterState {
  return {
    id,
    definitionId: 'doctor',
    name: id,
    printedIdentity: identity,
    configuredIdentity: identity,
    temporaryIdentity: null,
    publicIdentity: null,
    initialArea: 'hospital',
    area: 'hospital',
    presence: 'board',
    alive: true,
    counters: blankCounters(),
    attachments: [],
    marks: { communicated: false, died: false },
    ...changes,
  };
}
export function atNode(state: GameState, phase: GameState['clock']['phase'], node: string): void {
  state.clock.phase = phase;
  state.clock.node = node;
}
export function choose(engine: Engine, ids?: string[], actor = engine.waiting!.actor) {
  const waiting = engine.waiting!;
  return engine.submit(actor, {
    protocolVersion: 2,
    sessionId: 'local',
    branchId: 'main',
    commandId: waiting.id,
    expectedRevision: waiting.revision,
    waitingInputId: waiting.id,
    command: {
      kind: 'choose',
      optionIds: ids ?? waiting.options.slice(0, waiting.minSelections).map((o) => o.id),
    },
  });
}
export function source(
  id: string,
  operations: RuleSourceDefinition['program']['segments'],
): RuleSourceDefinition {
  return {
    id,
    name: id,
    reference: 'test',
    kind: 'forced',
    timings: ['phase:turn_end:enter'],
    program: { segments: operations },
  };
}
