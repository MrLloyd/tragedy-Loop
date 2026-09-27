import type { SeatId, WaitingInput } from '../../contracts/src/index.js';

export const PHASES = [
  'setup',
  'loop_start',
  'turn_start',
  'mastermind_action',
  'protagonist_action',
  'action_resolution',
  'mastermind_ability',
  'protagonist_ability',
  'incident',
  'leader_rotation',
  'turn_end',
  'loop_end',
  'final_showdown',
] as const;
export type Phase = (typeof PHASES)[number];

export const AREAS = ['shrine', 'hospital', 'city', 'school', 'faraway'] as const;
export type AreaId = (typeof AREAS)[number];
export type BoardAreaId = Exclude<AreaId, 'faraway'>;
export type CounterType = 'goodwill' | 'anxiety' | 'intrigue' | 'hope' | 'despair' | 'guard';
export type PlacementTarget = { kind: 'character' | 'area'; id: string };

export interface Counters {
  goodwill: number;
  anxiety: number;
  intrigue: number;
  hope: number;
  despair: number;
  guard: number;
}

export interface CharacterState {
  id: string;
  definitionId: string;
  name: string;
  printedIdentity: string;
  configuredIdentity: string;
  reverseIdentity?: string;
  temporaryIdentity: string | null;
  publicIdentity: string | null;
  initialArea: AreaId;
  area: AreaId;
  presence: 'board' | 'removed' | 'not_entered';
  alive: boolean;
  counters: Counters;
  attachments: string[];
  marks: { communicated: boolean; died: boolean };
}

export type ActionKind =
  | 'intrigue+2'
  | 'intrigue+1'
  | 'anxiety+1'
  | 'anxiety-1'
  | 'goodwill+1'
  | 'goodwill+2'
  | 'move-horizontal'
  | 'move-vertical'
  | 'move-diagonal'
  | 'forbid-goodwill'
  | 'forbid-anxiety'
  | 'forbid-intrigue'
  | 'forbid-movement'
  | 'hope+1'
  | 'despair+1'
  | 'anxiety+2';

export interface ActionCardState {
  id: string;
  kind: ActionKind;
  owner: SeatId;
  oncePerLoop: boolean;
  zone: 'hand' | 'placed' | 'used' | 'excluded';
}

export interface ActionPlacement {
  id: string;
  cardId: string;
  owner: SeatId;
  target: PlacementTarget;
  revealed: boolean;
  affectedCharacterIds: string[];
  effective: boolean;
}

export interface ScheduledTask {
  id: string;
  sourceId: string;
  due: Timing;
  payload: ResolutionProgram;
  expiresAtLoopEnd: boolean;
  snapshot?: Record<string, unknown>;
  loop?: number;
  day?: number;
}

export interface IncidentRecord {
  sequence: number;
  entryId: string;
  incidentId: string;
  publicName: string;
  culpritIds: string[];
  loop: number;
  day: number;
  completed: boolean;
  changed: boolean;
  calledByAi: boolean;
}

export interface PreviousLoopSnapshot {
  loop: number;
  characters: Record<string, CharacterState>;
  board: Record<BoardAreaId, { intrigue: number }>;
  ex: number;
  loopIncidentEntryIds: string[];
}

export interface GameRecords {
  loopFailed: boolean;
  protagonistsDead: boolean;
  endRequests: string[];
  usage: Record<string, number>;
  revealedFacts: string[];
  incidentHistory: IncidentRecord[];
  loopIncidentEntryIds: string[];
  firstIncidentDay: number | null;
  worldMovedToday: boolean;
  worldMoveIncrementApplied: boolean;
  exIncreasedThisLoop: boolean;
  delayed: ScheduledTask[];
  previousLoop: PreviousLoopSnapshot | null;
  sourceOutcomes: Record<string, SourceOutcome>;
}

export interface ScriptState {
  id: string;
  moduleId: string;
  ruleIds: string[];
  loops: number;
  daysPerLoop: number;
  finalShowdown: boolean;
  discussionRestriction?: string;
  specialRules?: string[];
  incidents: Array<{
    entryId: string;
    day: number;
    incidentId: string;
    publicName: string;
    publicInfo?: string;
    privateInfo?: string;
    culpritIds: string[];
    crowdArea?: BoardAreaId;
  }>;
  options: Record<string, string | number | boolean | string[]>;
}

export interface GameState {
  schemaVersion: 2;
  revision: number;
  contentVersion: string;
  status: 'ready' | 'running' | 'waiting' | 'finished' | 'faulted';
  script: ScriptState;
  clock: {
    loop: number;
    day: number;
    phase: Phase;
    node: string;
    phaseInstance: number;
  };
  leader: SeatId;
  board: Record<BoardAreaId, { intrigue: number }>;
  characters: Record<string, CharacterState>;
  cards: Record<SeatId, ActionCardState[]>;
  placements: ActionPlacement[];
  curses: Array<{ id: string; kind: 'area' | 'character'; targetId: string }>;
  ex: number;
  protagonistProtection: boolean;
  traitors: SeatId[];
  secretLetters: Partial<Record<SeatId, 'A' | 'B' | 'C'>>;
  records: GameRecords;
  result: null | { winners: SeatId[]; reason: string };
  publicLog: Array<{ sequence: number; type: string; text: string }>;
}

export type Timing =
  | `phase:${Phase}:enter`
  | `phase:${Phase}:exit`
  | 'character:died'
  | 'identity:revealed'
  | 'ability:completed'
  | 'incident:completed'
  | 'ex:changed'
  | 'batch:committed';

export type ValueExpr =
  | number
  | { kind: 'counter'; target: string; counter: CounterType; effective?: boolean }
  | { kind: 'area-intrigue'; area: BoardAreaId; effective?: boolean }
  | { kind: 'ex' }
  | { kind: 'loop' }
  | { kind: 'day' }
  | { kind: 'selection-count'; selector: Selector }
  | { kind: 'token-total' | 'token-kinds'; target: string }
  | { kind: 'sum'; selector: Selector; counter: CounterType; effective?: boolean }
  | { kind: 'limit'; target: string }
  | { kind: 'days-per-loop' }
  | { kind: 'corpses'; area?: AreaId; identity?: string }
  | { kind: 'alive-count' }
  | { kind: 'mark-count'; mark: 'communicated' | 'died' };

export type Condition =
  | { kind: 'always' }
  | { kind: 'not'; condition: Condition }
  | { kind: 'all' | 'any'; conditions: Condition[] }
  | { kind: 'compare'; left: ValueExpr; op: '>=' | '<=' | '>' | '<' | '='; right: ValueExpr }
  | { kind: 'phase'; phase: Phase }
  | { kind: 'alive'; characterId: string; value: boolean }
  | { kind: 'presence'; characterId: string; presence: CharacterState['presence'] }
  | { kind: 'identity'; characterId: string; identityId: string }
  | { kind: 'trait'; characterId: string; traitId: string }
  | { kind: 'flag'; key: string; value?: boolean }
  | { kind: 'area'; target: string; areas: AreaId[] }
  | { kind: 'final-day' }
  | { kind: 'revealed'; target: string }
  | { kind: 'attachment'; target: string; key: string }
  | { kind: 'incident-occurred'; incidentId: string; thisLoop?: boolean; today?: boolean };

export type Selector =
  | { kind: 'union'; selectors: Selector[]; count?: number | 'all' }
  | { kind: 'none' }
  | { kind: 'character'; id: string; allowDead?: boolean; allowRemoved?: boolean }
  | { kind: 'characters'; ids?: string[]; filter?: CharacterFilter; count?: number | 'all' }
  | { kind: 'area'; id?: BoardAreaId }
  | { kind: 'areas'; count?: number | 'all' }
  | { kind: 'protagonists' };

export interface CharacterFilter {
  definitionId?: string;
  alive?: boolean;
  presence?: CharacterState['presence'];
  area?: AreaId | { sameAs: string };
  not?: string[];
  identity?: string;
  trait?: string;
  attribute?: string;
  counter?: { type: CounterType; atLeast: number; effective?: boolean };
  atAnxietyLimit?: boolean;
}

export type Operation =
  | { kind: 'noop' }
  | { kind: 'bundle'; operations: Operation[] }
  | { kind: 'attachment'; key: string; remove?: boolean }
  | { kind: 'curse'; curseId?: string; action: 'create' | 'attach' | 'drop' }
  | { kind: 'counter'; counter: CounterType; amount: ValueExpr; direction?: 'add' | 'remove' }
  | { kind: 'clear-counters'; counters?: CounterType[] }
  | { kind: 'announce'; text: string; fact?: string }
  | { kind: 'return-card'; seat: SeatId; cardId: string }
  | {
      kind: 'move-counter';
      counter?: CounterType;
      amount: number;
      to: Selector;
      sacredTree?: boolean;
    }
  | { kind: 'attachment-transfer'; from: string; key: string }
  | { kind: 'replace-counter'; from: CounterType; to: CounterType; amount: number }
  | {
      kind: 'move-character';
      destination?: AreaId;
      adjacent?: boolean;
      anyArea?: boolean;
      lockNextDay?: boolean;
    }
  | { kind: 'death' }
  | { kind: 'protagonists-die' }
  | { kind: 'fail-loop'; reason: string }
  | { kind: 'end-loop'; reason: string }
  | { kind: 'resurrect' }
  | { kind: 'remove-character' }
  | { kind: 'reveal-identity'; declaredIdentity?: string }
  | { kind: 'set-temporary-identity'; identityId: string | null }
  | { kind: 'ex'; amount: number }
  | { kind: 'set-protagonist-protection'; value: boolean }
  | { kind: 'set-record'; key: string; value: boolean }
  | { kind: 'grant-card'; cardKind: ActionKind; seat: SeatId }
  | { kind: 'schedule'; task: Omit<ScheduledTask, 'id'> }
  | { kind: 'world-move' };

export interface EffectSpec {
  id: string;
  condition?: Condition;
  target: Selector;
  operation: Operation;
  chooser?: SeatId | 'leader' | 'source-owner';
}

export interface ResolutionSegment {
  id: string;
  effects: EffectSpec[];
  optional?: boolean;
  chooser?: SeatId | 'leader' | 'source-owner';
  choices?: Array<{
    key: string;
    prompt: string;
    values: string[];
    chooser?: SeatId | 'leader' | 'source-owner';
    exclude?: string;
  }>;
  alternatives?: Array<{ id: string; label: string; effects: EffectSpec[] }>;
  eventChoice?: string[];
  abilityChoice?: Selector;
}

export interface ResolutionProgram {
  segments: ResolutionSegment[];
  endLoopOnComplete?: string;
}

export interface UsageLimit {
  scope: 'phase' | 'day' | 'loop' | 'game';
  count: number;
  sharedKey?: string;
  consume: 'on_start' | 'on_complete';
}

export interface RuleSourceDefinition {
  id: string;
  name: string;
  reference: string;
  kind: 'forced' | 'optional' | 'goodwill' | 'incident' | 'rule';
  timings: Timing[];
  owner?: SeatId;
  characterId?: string;
  instantiate?: {
    kind: 'identity' | 'character-definition';
    id: string;
    includeDead?: boolean;
  };
  condition?: Condition;
  program: ResolutionProgram;
  usage?: UsageLimit;
  additionalLimits?: UsageLimit[];
  allowDeadOwner?: boolean;
  priority?: number;
  trigger?: { sourceId?: string; characterId?: string; incidentId?: string };
  enabledBy?: string;
  goodwill?: { threshold: number; cannotRefuse?: boolean; mastermindThreshold?: number };
  native?: string;
}

export interface PersistentContribution {
  kind:
    | 'identity'
    | 'trait-add'
    | 'trait-remove'
    | 'ability-add'
    | 'traitor-add'
    | 'traitor-remove'
    | 'placement-ban'
    | 'movement-ban-remove'
    | 'incident-ban'
    | 'incident-force'
    | 'incident-count-mode'
    | 'incident-threshold'
    | 'count-area-extra';
  characterId?: string;
  value: string | number;
  priority?: number;
}

export interface PersistentRuleDefinition {
  id: string;
  reference: string;
  dependsOn: string[];
  condition: Condition;
  contributions: PersistentContribution[];
  enabledBy?: string;
}

export interface IdentityDefinition {
  id: string;
  name: string;
  traits: string[];
  abilities: string[];
  max?: number;
}

export interface CharacterDefinition {
  id: string;
  name: string;
  attributes: string[];
  initialAreas: AreaId[];
  forbiddenAreas: AreaId[];
  anxietyLimit: number | 'X';
  goodwillAbilities: Array<{ sourceId: string; threshold: number; oncePerLoop?: boolean }>;
  traits: string[];
}

export interface IncidentDefinition {
  id: string;
  name: string;
  crowd?: { requiredCorpses: number };
  program: ResolutionProgram;
  thresholdAdjustment?: number;
  endsLoopOnComplete?: boolean;
  countMode?: 'anxiety' | 'goodwill' | 'intrigue';
  alwaysOccurs?: boolean;
  native?: boolean;
}

export interface ModuleDefinition {
  id: string;
  name: string;
  ruleSelection: { y: number; x: number };
  finalShowdown: boolean;
  exReset: 'zero' | 'keep' | 'none';
  rules: string[];
  identities: string[];
  identityLimits?: Record<string, number>;
  incidents: string[];
}

export interface ContentCatalog {
  version: string;
  modules: Record<string, ModuleDefinition>;
  identities: Record<string, IdentityDefinition>;
  characters: Record<string, CharacterDefinition>;
  incidents: Record<string, IncidentDefinition>;
  sources: Record<string, RuleSourceDefinition>;
  persistent: Record<string, PersistentRuleDefinition>;
  rules?: Record<
    string,
    {
      id: string;
      name: string;
      kind: 'y' | 'x';
      roles: Array<{ identityId: string; count: string }>;
      text: string[];
    }
  >;
}

export interface EffectiveCharacter {
  id: string;
  identity: string;
  traits: string[];
  abilities: string[];
  counts: { goodwill: number; anxiety: number; intrigue: number };
  placementBanned: boolean;
  placementBannedFor: SeatId[];
  ignoredForbiddenAreas: boolean;
  incidentBanned: boolean;
  incidentForced: boolean;
  incidentCountMode?: 'anxiety' | 'goodwill' | 'intrigue';
  incidentThreshold: number;
}

export interface EffectiveState {
  revision: number;
  context: string;
  characters: Record<string, EffectiveCharacter>;
  traitors: SeatId[];
  areaIntrigue: Record<BoardAreaId, number>;
  evidence: Record<string, string[]>;
}

export interface TargetResult {
  effectId: string;
  status: 'has_target' | 'no_target' | 'not_required' | 'not_checked';
  candidates: string[];
  selected: string[];
}

export interface SourceOutcome {
  sourceId: string;
  started: boolean;
  completed: boolean;
  changed: boolean;
  rejected: boolean;
  truncated: boolean;
  targets: TargetResult[];
}

export interface EffectIntent {
  id: string;
  sourceInstanceId: string;
  effectId: string;
  targetId?: string;
  operation: Operation;
}

export interface DeathAttempt {
  id: string;
  originalTarget: string;
  finalTarget: string;
  blockedBy: 'immortal' | 'guard' | null;
  replaced: boolean;
}

export interface BatchResult {
  changed: boolean;
  changedSourceIds: string[];
  deaths: string[];
  deathAttempts: DeathAttempt[];
  events: DomainEvent[];
}

export type DomainEvent =
  | {
      type: 'counter-changed';
      targetId: string;
      counter: CounterType;
      before: number;
      after: number;
    }
  | { type: 'character-moved'; targetId: string; from: AreaId; to: AreaId }
  | { type: 'character-died'; targetId: string; fromArea: AreaId }
  | { type: 'character-resurrected'; targetId: string }
  | { type: 'character-removed'; targetId: string }
  | { type: 'card-granted'; seat: SeatId; cardKind: ActionKind }
  | { type: 'identity-revealed'; targetId: string; identityId: string }
  | { type: 'ex-changed'; before: number; after: number }
  | { type: 'loop-failed'; reason: string }
  | { type: 'loop-end-requested'; reason: string }
  | { type: 'protagonists-died' }
  | { type: 'world-moved' }
  | { type: 'record-changed'; key: string; value: boolean };

export interface SourceFrame {
  kind: 'source';
  id: string;
  sourceId: string;
  ownerCharacterId?: string;
  segment: number;
  stage: 'targeting' | 'commit' | 'aftermath' | 'advance';
  choices: Record<string, string[]>;
  outcome: SourceOutcome;
}

export interface ResolutionLane {
  id: string;
  definition: RuleSourceDefinition;
  ownerCharacterId?: string;
  cursor: number;
  choices: Record<string, string[]>;
  bindings: Record<string, string>;
  optionalAccepted?: boolean;
  authorized: boolean;
  done: boolean;
  outcome: SourceOutcome;
  incidentRecord?: number;
}

export interface ResolutionFrame {
  kind: 'resolution';
  id: string;
  lanes: ResolutionLane[];
  stage: 'prepare' | 'aftermath' | 'complete' | 'advance';
  readState?: GameState;
  prepared: EffectIntent[];
  prepareIndex: number;
  cleanup: boolean;
}

export interface TimingFrame {
  kind: 'timing';
  id: string;
  timing: Timing;
  sourceIds: string[];
  cursor: number;
  context: Record<string, string | string[]>;
}

export type ExecutionFrame = ResolutionFrame;

export interface ExecutionState {
  frames: ExecutionFrame[];
  waiting: WaitingInput | null;
  waitingKey: string | null;
  answers: Record<string, string[]>;
  firedTriggerInstances: string[];
  nextId: number;
  receipts: Record<string, { fingerprint: string; revision: number; actor: SeatId }>;
  fault: string | null;
  flowData: Record<string, string | number | boolean | string[]>;
  generated: Record<string, RuleSourceDefinition>;
  trace: Array<{ id: string; type: string; data: unknown }>;
}

export const blankCounters = (): Counters => ({
  goodwill: 0,
  anxiety: 0,
  intrigue: 0,
  hope: 0,
  despair: 0,
  guard: 0,
});

export const emptyCards = (): Record<SeatId, ActionCardState[]> => ({
  mastermind: [],
  protagonistA: [],
  protagonistB: [],
  protagonistC: [],
});

export function createExecutionState(): ExecutionState {
  return {
    frames: [],
    waiting: null,
    waitingKey: null,
    answers: {},
    firedTriggerInstances: [],
    nextId: 1,
    receipts: {},
    fault: null,
    flowData: {},
    generated: {},
    trace: [],
  };
}
