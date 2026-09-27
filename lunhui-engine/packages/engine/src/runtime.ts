import type {
  CommandEnvelope,
  Receipt,
  SeatId,
  VisibleSessionSnapshot,
  WaitingInput,
  WaitingKind,
} from '../../contracts/src/index.js';
import { choiceSchema, protagonistSeats } from '../../contracts/src/index.js';
import {
  actionMovementPlan,
  cultistForbids,
  legalActionTargets,
  moveDestination,
  placeAction,
  resolveActionCounters,
  resolveActionMovement,
} from './actions.js';
import { judgeScheduledIncident, recordIncident } from './incidents.js';
import { incidentProgram } from './native-incidents.js';
import { nativeForced, nativeOptional } from './native-rules.js';
import { abilityProgram } from './native-abilities.js';
import { catalogFingerprint, parseCheckpoint } from './checkpoint.js';
import type {
  ContentCatalog,
  ExecutionState,
  GameState,
  RuleSourceDefinition,
  ResolutionFrame,
  ResolutionLane,
  Timing,
} from './model.js';
import { createExecutionState } from './model.js';
import { checkStageVictory, evaluatePersistent } from './persistent.js';
import { matches, requiredTargetCount, selectCandidates } from './query.js';
import {
  buildIntents,
  commitBatch,
  inspectSegment,
  textMoveDestinations,
  movementFollowers,
} from './resolution.js';
import { rotateLeader, usageKey, validateNewGame } from './state.js';

type EngineSave = {
  engineVersion: '2.0.0';
  catalogFingerprint: string;
  sessionId: string;
  branchId: string;
  state: GameState;
  execution: ExecutionState;
};

const clone = <T>(value: T): T => structuredClone(value);

function fingerprint(command: CommandEnvelope): string {
  return JSON.stringify(command);
}

function bind<T>(value: T, bindings: Record<string, string>): T {
  const visit = (entry: unknown): unknown => {
    if (typeof entry === 'string') {
      if (bindings[entry] !== undefined) return bindings[entry];
      let result = entry;
      for (const key of Object.keys(bindings)
        .filter((key) => key.startsWith('$'))
        .sort((a, b) => b.length - a.length))
        result = result.split(key).join(bindings[key]!);
      return result;
    }
    if (Array.isArray(entry)) return entry.map(visit);
    if (entry && typeof entry === 'object')
      return Object.fromEntries(Object.entries(entry).map(([key, child]) => [key, visit(child)]));
    return entry;
  };
  return visit(value) as T;
}

function withScope<T>(value: T, owner: string, area: string): T {
  if (Array.isArray(value)) return value.map((child) => withScope(child, owner, area)) as T;
  if (typeof value === 'string') return (value === `$area:${owner}` ? area : value) as T;
  if (value && typeof value === 'object') {
    if ('sameAs' in value && value.sameAs === owner) return area as T;
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, withScope(child, owner, area)]),
    ) as T;
  }
  return value;
}

export class RulesEngine {
  private stateData: GameState;
  private execution: ExecutionState;

  constructor(
    state: GameState,
    private readonly catalog: ContentCatalog,
    private readonly sessionId = 'local',
    private readonly branchId = 'main',
  ) {
    if (state.schemaVersion !== 2) throw new Error('STATE_VERSION_MISMATCH');
    if (state.contentVersion !== catalog.version) throw new Error('CONTENT_VERSION_MISMATCH');
    this.stateData = clone(state);
    this.catalog = clone(catalog);
    this.execution = createExecutionState();
  }

  get state(): GameState {
    return clone(this.stateData);
  }

  get waiting(): WaitingInput | null {
    return clone(this.execution.waiting);
  }

  private id(prefix: string): string {
    return `${prefix}:${this.execution.nextId++}`;
  }

  private log(type: string, text: string): void {
    this.stateData.publicLog.push({ sequence: this.stateData.publicLog.length, type, text });
  }

  start(): void {
    if (this.stateData.status !== 'ready') throw new Error('GAME_ALREADY_STARTED');
    this.stateData.status = 'running';
    this.drive();
  }

  private sourceParts(instanceId: string): { sourceId: string; ownerCharacterId?: string } {
    const at = instanceId.indexOf('@');
    return at < 0
      ? { sourceId: instanceId }
      : { sourceId: instanceId.slice(0, at), ownerCharacterId: instanceId.slice(at + 1) };
  }

  private source(instanceId: string): RuleSourceDefinition {
    const { sourceId } = this.sourceParts(instanceId);
    const source = this.execution.generated[sourceId] ?? this.catalog.sources[sourceId];
    if (!source) throw new Error(`UNKNOWN_SOURCE:${sourceId}`);
    return source;
  }

  private sourceInstances(
    timing: Timing,
    context: Record<string, string | string[]> = {},
  ): string[] {
    const effective = evaluatePersistent(this.stateData, this.catalog, `timing:${timing}`);
    const result: string[] = [];
    for (const source of Object.values(this.catalog.sources)) {
      if (
        source.enabledBy &&
        source.enabledBy !== this.stateData.script.moduleId &&
        !this.stateData.script.ruleIds.includes(source.enabledBy)
      )
        continue;
      if (!source.timings.includes(timing)) continue;
      if (source.trigger?.sourceId && source.trigger.sourceId !== context.sourceId) continue;
      if (source.trigger?.characterId) {
        const ids = Array.isArray(context.characterIds)
          ? context.characterIds
          : [context.characterIds].filter(Boolean);
        if (!ids.includes(source.trigger.characterId)) continue;
      }
      if (source.trigger?.incidentId && source.trigger.incidentId !== context.incidentId) continue;
      if (source.instantiate) {
        for (const character of Object.values(this.stateData.characters).sort((a, b) =>
          a.id.localeCompare(b.id),
        )) {
          if (character.presence !== 'board') continue;
          const subjects = Array.isArray(context.characterIds) ? context.characterIds : [];
          if (
            [
              'character:died',
              'ability:completed',
              'incident:completed',
              'identity:revealed',
            ].includes(timing) &&
            !subjects.includes(character.id)
          )
            continue;
          const previousIdentity = Array.isArray(context.previousIdentities)
            ? context.previousIdentities
                .find((entry) => entry.startsWith(`${character.id}=`))
                ?.split('=')[1]
            : undefined;
          const abilities =
            timing === 'character:died' && Array.isArray(context.previousAbilities)
              ? context.previousAbilities
                  .filter((entry) => entry.startsWith(`${character.id}=`))
                  .map((entry) => entry.split('=')[1]!)
              : (effective.characters[character.id]?.abilities ?? []);
          const matchesTemplate =
            source.instantiate.kind === 'identity'
              ? (previousIdentity ?? effective.characters[character.id]?.identity) ===
                  source.instantiate.id || abilities.includes(source.instantiate.id)
              : character.definitionId === source.instantiate.id;
          if (
            !matchesTemplate ||
            (!source.instantiate.includeDead && !character.alive && timing !== 'character:died')
          )
            continue;
          const boundSource = bind(bind(source, { $owner: character.id }), {
            [`$area:${character.id}`]: character.area,
            [`$initial:${character.id}`]: character.initialArea,
          });
          const instanceId = `${source.id}@${character.id}`;
          if (this.exhausted(instanceId)) continue;
          if (
            this.abilityAreas(boundSource, character.id, this.stateData).some((area) =>
              matches(
                withScope(boundSource.condition, character.id, area),
                this.stateData,
                effective,
                this.catalog,
              ),
            )
          )
            result.push(instanceId);
        }
      } else if (
        !this.exhausted(source.id) &&
        matches(source.condition, this.stateData, effective, this.catalog)
      )
        result.push(source.id);
    }
    return result.sort((a, b) => {
      const pa = this.source(a).priority ?? 0;
      const pb = this.source(b).priority ?? 0;
      return pa - pb || a.localeCompare(b);
    });
  }

  private abilityAreas(source: RuleSourceDefinition, owner: string, state: GameState): string[] {
    const c = state.characters[owner]!;
    const areas = [c.area as string];
    if (source.kind === 'incident') return areas;
    if (c.definitionId === 'uploader')
      areas.push(
        ...Object.values(state.characters)
          .filter((card) => card.presence === 'board' && card.attachments.includes('uploader-ex'))
          .map((card) => card.area),
      );
    if (
      c.definitionId === 'big_shot' &&
      (source.kind !== 'goodwill' || state.clock.phase === 'mastermind_ability')
    ) {
      const territory = state.script.options[`territory:${owner}`];
      if (typeof territory === 'string') areas.push(territory);
    }
    return [...new Set(areas)];
  }

  private eventArea(owner: string, mode: string, state: GameState): import('./model.js').AreaId {
    const actual = state.characters[owner]!.area;
    if (mode === 'diagonal') return moveDestination(actual, ['move-diagonal']) ?? actual;
    if (mode === 'clockwise' && actual !== 'faraway') {
      const order = ['hospital', 'shrine', 'school', 'city'] as const;
      return order[(order.indexOf(actual) + 1) % order.length]!;
    }
    return actual;
  }

  private pushTiming(timing: Timing, context: Record<string, string | string[]> = {}): void {
    const sourceIds = this.sourceInstances(timing, context).filter(
      (id) => this.source(id).kind === 'forced',
    );
    for (const definition of nativeForced(timing, this.stateData, this.catalog, context)) {
      this.execution.generated[definition.id] = definition;
      if (!this.exhausted(definition.id)) sourceIds.push(definition.id);
    }
    const due = this.stateData.records.delayed.filter(
      (task) =>
        task.due === timing &&
        (task.loop === undefined || task.loop === this.stateData.clock.loop) &&
        (task.day === undefined || task.day === this.stateData.clock.day),
    );
    this.stateData.records.delayed = this.stateData.records.delayed.filter(
      (task) => !due.includes(task),
    );
    for (const task of due) {
      const id = `scheduled.${task.id}`;
      this.execution.generated[id] = {
        id,
        name: task.sourceId,
        reference: 'scheduled effect',
        kind: 'forced',
        timings: [],
        program: task.payload,
      };
      sourceIds.push(id);
    }
    if (sourceIds.length) this.pushGroup(sourceIds);
  }

  private limitKey(instanceId: string, source = this.source(instanceId)): string {
    return usageKey(
      instanceId,
      source.usage?.scope ?? 'phase',
      this.stateData,
      source.usage?.sharedKey,
    );
  }

  private exhausted(instanceId: string): boolean {
    const source = this.source(instanceId);
    if (
      source.usage &&
      (this.stateData.records.usage[this.limitKey(instanceId)] ?? 0) >= source.usage.count
    )
      return true;
    if (
      source.additionalLimits?.some(
        (limit) =>
          (this.stateData.records.usage[
            usageKey(instanceId, limit.scope, this.stateData, limit.sharedKey)
          ] ?? 0) >= limit.count,
      )
    )
      return true;
    return (
      ['optional', 'goodwill'].includes(source.kind) &&
      (this.stateData.records.usage[usageKey(instanceId, 'phase', this.stateData)] ?? 0) >= 1
    );
  }

  private pushGroup(ids: string[], forcedGoodwill = false): void {
    const claimed = new Set<string>();
    const lanes: ResolutionLane[] = [];
    for (const instanceId of ids) {
      const { ownerCharacterId } = this.sourceParts(instanceId);
      const original = this.source(instanceId);
      const definition = bind(
        original,
        ownerCharacterId ? { $owner: ownerCharacterId, $culprit: ownerCharacterId } : {},
      );
      if (definition.native && ownerCharacterId)
        definition.program = abilityProgram(
          definition,
          ownerCharacterId,
          this.stateData,
          this.catalog,
        );
      if (forcedGoodwill && definition.goodwill) definition.goodwill.cannotRefuse = true;
      if (definition.kind === 'incident') {
        const incident = this.catalog.incidents[definition.id.replace(/^incident\./, '')]!;
        const entry = this.stateData.script.incidents.find(
          (entry) => entry.day === this.stateData.clock.day,
        );
        definition.program = bind(
          incidentProgram(
            incident,
            this.stateData,
            this.catalog,
            ownerCharacterId ?? '',
            entry?.entryId,
          ),
          { $culprit: ownerCharacterId ?? '' },
        );
        if (
          ownerCharacterId &&
          this.stateData.characters[ownerCharacterId]?.definitionId === 'black_cat'
        )
          definition.program = {
            segments: [
              {
                id: 'black-cat',
                effects: [
                  { id: 'no-phenomenon', target: { kind: 'none' }, operation: { kind: 'noop' } },
                ],
              },
            ],
          };
      }
      const claim = definition.usage?.sharedKey;
      if (this.exhausted(instanceId) || (claim && claimed.has(claim))) continue;
      if (claim) claimed.add(claim);
      lanes.push({
        id: this.id('source'),
        definition,
        ownerCharacterId,
        cursor: 0,
        choices: {},
        bindings: {},
        authorized: definition.kind !== 'goodwill',
        done: false,
        ...(definition.kind === 'incident'
          ? { incidentRecord: Number(this.execution.flowData['incident:record']) }
          : {}),
        outcome: {
          sourceId: instanceId,
          started: definition.kind === 'forced' || definition.kind === 'incident',
          completed: false,
          changed: false,
          rejected: false,
          truncated: false,
          targets: [],
        },
      });
    }
    if (!lanes.length) return;
    this.execution.frames.push({
      kind: 'resolution',
      id: this.id('resolution'),
      lanes,
      stage: 'prepare',
      readState: clone(this.stateData),
      prepared: [],
      prepareIndex: 0,
      cleanup: this.stateData.clock.phase === 'loop_end',
    });
  }

  private pushSource(instanceId: string): void {
    this.pushGroup([instanceId]);
  }

  private ask(
    key: string,
    actor: SeatId,
    kind: WaitingKind,
    prompt: string,
    options: Array<{ id: string; label: string; description?: string }>,
    minSelections = 1,
    maxSelections = 1,
    canPass = false,
    isPrivate = false,
  ): void {
    this.stateData.revision++;
    this.execution.waitingKey = key;
    this.execution.waiting = {
      id: this.id('input'),
      revision: this.stateData.revision,
      actor,
      kind,
      prompt,
      options,
      minSelections,
      maxSelections,
      canPass,
      private: isPrivate,
    };
    this.stateData.status = 'waiting';
  }

  private answer(key: string): string[] | undefined {
    const value = this.execution.answers[key];
    if (value) delete this.execution.answers[key];
    return value;
  }

  private resolveChooser(value: string | undefined, source: RuleSourceDefinition): SeatId {
    if (value === 'leader') return this.stateData.leader;
    if (source.native === 'ai' && value === 'mastermind') return this.stateData.leader;
    if (value && value !== 'source-owner') return value as SeatId;
    if (source.native === 'ai') return this.stateData.leader;
    if (source.kind === 'goodwill' && this.stateData.clock.phase === 'mastermind_ability')
      return 'mastermind';
    if (!value || value === 'source-owner')
      return source.owner ?? (source.kind === 'goodwill' ? this.stateData.leader : 'mastermind');
    return value as SeatId;
  }

  private stopped(frame?: ResolutionFrame): boolean {
    return Boolean(
      this.stateData.result || (!frame?.cleanup && this.stateData.records.endRequests.length),
    );
  }

  private stepResolution(frame: ResolutionFrame): void {
    if (frame.stage === 'prepare') {
      const batchSnapshot = frame.readState!;
      while (frame.prepareIndex < frame.lanes.length) {
        let snapshot = batchSnapshot;
        const lane = frame.lanes[frame.prepareIndex]!;
        if (lane.done) {
          frame.prepareIndex++;
          continue;
        }
        const source = lane.definition;
        if (
          source.kind === 'incident' &&
          lane.ownerCharacterId &&
          !lane.bindings['incident-compiled']
        ) {
          const owner = snapshot.characters[lane.ownerCharacterId]!;
          const identity = evaluatePersistent(snapshot, this.catalog).characters[owner.id]!
            .identity;
          let mode = identity === 'twins' ? 'diagonal' : 'actual';
          if (owner.definitionId === 'hermit' && owner.area !== 'faraway' && identity !== 'twins') {
            const key = `${lane.id}:incident-area`;
            const answer = this.answer(key);
            if (!answer) {
              this.ask(key, 'mastermind', 'option', '选择仙人事件效果所用位置', [
                { id: 'actual', label: '实际所在区域' },
                { id: 'clockwise', label: '顺时针相邻版图' },
              ]);
              return;
            }
            mode = answer[0]!;
          }
          lane.bindings['event-mode'] = mode;
          lane.bindings['incident-compiled'] = 'yes';
          const incident = this.catalog.incidents[source.id.replace(/^incident\./, '')]!;
          const entry = snapshot.script.incidents.find((entry) => entry.day === snapshot.clock.day);
          if (owner.definitionId !== 'black_cat') {
            source.program = bind(
              incidentProgram(
                incident,
                snapshot,
                this.catalog,
                owner.id,
                entry?.entryId,
                false,
                this.eventArea(owner.id, mode, snapshot),
              ),
              { $culprit: owner.id },
            );
            if (
              evaluatePersistent(snapshot, this.catalog).characters[owner.id]!.traits.includes(
                'cult-leader',
              )
            ) {
              const repeated = clone(source.program.segments);
              const replacements: Record<string, string> = {};
              for (const segment of repeated)
                for (const choice of segment.choices ?? [])
                  replacements[`$choice:${choice.key}`] = `$choice:repeat:${choice.key}`;
              for (const segment of repeated) {
                for (const choice of segment.choices ?? []) choice.key = `repeat:${choice.key}`;
                segment.id += ':repeat';
              }
              source.program.segments.push(...bind(repeated, replacements));
            }
          }
        }
        if (lane.ownerCharacterId && source.kind !== 'incident' && !lane.bindings['scope']) {
          const owner = lane.ownerCharacterId;
          const candidates = this.abilityAreas(source, owner, snapshot).filter((area) =>
            matches(
              withScope(source.condition, owner, area),
              snapshot,
              evaluatePersistent(snapshot, this.catalog),
              this.catalog,
            ),
          );
          if (candidates.length > 1) {
            const key = `${lane.id}:scope`;
            const answer = this.answer(key);
            if (!answer) {
              this.ask(
                key,
                this.resolveChooser(undefined, source),
                'option',
                '选择本次能力所用的所在区域（范围不合并）',
                candidates.map((id) => ({ id, label: id })),
              );
              return;
            }
            lane.bindings.scope =
              answer[0] === snapshot.characters[owner]!.area ? '$actual' : answer[0]!;
          } else
            lane.bindings.scope =
              !candidates[0] || candidates[0] === snapshot.characters[owner]!.area
                ? '$actual'
                : candidates[0];
        }
        const eventChoices = source.program.segments[lane.cursor]!.eventChoice;
        if (eventChoices) {
          const viable = [...new Set(eventChoices)].filter(
            (id) => Boolean(this.catalog.incidents[id]) || id.startsWith('no-effect:'),
          );
          const key = `${lane.id}:event-choice:${lane.cursor}`;
          const answer = this.answer(key);
          if (!viable.length) {
            lane.done = true;
            frame.prepareIndex++;
            continue;
          }
          if (!answer) {
            this.ask(
              key,
              this.resolveChooser(undefined, source),
              'option',
              '选择事件效果',
              viable.map((id) => ({
                id,
                label:
                  this.catalog.incidents[id]?.name ??
                  snapshot.script.incidents.find((entry) => `no-effect:${entry.entryId}` === id)
                    ?.publicName ??
                  id,
              })),
            );
            return;
          }
          const selected = this.catalog.incidents[answer[0]!];
          if (
            lane.ownerCharacterId &&
            evaluatePersistent(snapshot, this.catalog).characters[lane.ownerCharacterId]!
              .identity === 'twins'
          )
            lane.bindings['event-mode'] = 'diagonal';
          const nested = selected
            ? incidentProgram(
                selected,
                snapshot,
                this.catalog,
                lane.ownerCharacterId ?? '',
                undefined,
                source.kind === 'goodwill',
                lane.ownerCharacterId
                  ? this.eventArea(
                      lane.ownerCharacterId,
                      lane.bindings['event-mode'] ?? 'actual',
                      snapshot,
                    )
                  : undefined,
              )
            : {
                segments: [
                  {
                    id: 'no-effect',
                    effects: [
                      {
                        id: 'notice',
                        target: { kind: 'none' as const },
                        operation: {
                          kind: 'announce' as const,
                          text: '所选公开事件没有对应的事件效果',
                        },
                      },
                    ],
                  },
                ],
              };
          if ('endLoopOnComplete' in nested && nested.endLoopOnComplete)
            source.program.endLoopOnComplete = nested.endLoopOnComplete;
          source.program.segments.splice(
            lane.cursor,
            1,
            ...bind(nested.segments, { $culprit: lane.ownerCharacterId ?? '' }),
          );
          if (source.program.segments[lane.cursor]!.eventChoice) return;
        }
        let choiceUnavailable = false;
        for (const choice of bind(source.program.segments[lane.cursor]!, lane.bindings).choices ??
          []) {
          if (lane.bindings[`$choice:${choice.key}`]) continue;
          const values = choice.values.filter((id) => id !== choice.exclude);
          if (!values.length) {
            choiceUnavailable = true;
            break;
          }
          const key = `${lane.id}:choice:${lane.cursor}:${choice.key}`;
          const answer = this.answer(key);
          if (!answer) {
            this.ask(
              key,
              this.resolveChooser(choice.chooser, source),
              'option',
              choice.prompt,
              values.map((id) => ({ id, label: this.catalog.rules?.[id]?.name ?? id })),
            );
            return;
          }
          lane.bindings[`$choice:${choice.key}`] = answer[0]!;
        }
        if (
          lane.ownerCharacterId &&
          lane.bindings['event-mode'] &&
          lane.bindings['event-mode'] !== 'actual'
        ) {
          snapshot = clone(batchSnapshot);
          snapshot.characters[lane.ownerCharacterId]!.area = this.eventArea(
            lane.ownerCharacterId,
            lane.bindings['event-mode'],
            batchSnapshot,
          );
        }
        const locations = Object.fromEntries(
          Object.values(snapshot.characters).flatMap((c) => [
            [`$area:${c.id}`, c.area],
            [`$initial:${c.id}`, c.initialArea],
          ]),
        );
        const scoped =
          lane.ownerCharacterId && lane.bindings.scope && lane.bindings.scope !== '$actual'
            ? withScope(
                source.program.segments[lane.cursor]!,
                lane.ownerCharacterId,
                lane.bindings.scope,
              )
            : source.program.segments[lane.cursor]!;
        const segment = bind(scoped, { ...lane.bindings, ...locations });
        // An impossible required choice has no effect; never create an empty,
        // unanswerable prompt or publish an unresolved placeholder.
        if (choiceUnavailable) segment.effects = [];
        if (segment.abilityChoice && !lane.bindings['called-ability']) {
          const owners = selectCandidates(
            segment.abilityChoice,
            snapshot,
            evaluatePersistent(snapshot, this.catalog),
            this.catalog,
          );
          const choices = this.sourceInstances(`phase:${snapshot.clock.phase}:enter`).filter(
            (id) =>
              this.source(id).kind === 'goodwill' &&
              owners.includes(this.sourceParts(id).ownerCharacterId ?? ''),
          );
          if (!choices.length) {
            lane.done = true;
            frame.prepareIndex++;
            continue;
          }
          const key = `${lane.id}:adult`;
          const answer = this.answer(key);
          if (!answer) {
            this.ask(
              key,
              this.resolveChooser(undefined, source),
              'ability',
              '选择成人的友好能力（无视友好阈值，但仍受限次约束）',
              choices.map((id) => ({ id, label: this.source(id).name })),
            );
            return;
          }
          lane.bindings['called-ability'] = answer[0]!;
        }
        if (segment.alternatives) {
          const legal = segment.alternatives.filter((option) =>
            inspectSegment(
              { id: option.id, effects: option.effects },
              snapshot,
              this.catalog,
              {},
            ).some((t) => ['has_target', 'not_required'].includes(t.status)),
          );
          if (legal.length) {
            const key = `${lane.id}:alternative:${lane.cursor}`;
            let selected = lane.bindings[`alternative:${lane.cursor}`];
            if (!selected) {
              const answer = this.answer(key);
              if (!answer) {
                this.ask(
                  key,
                  this.resolveChooser(segment.chooser, source),
                  'option',
                  `${source.name}：选择效果`,
                  legal.map((o) => ({ id: o.id, label: o.label })),
                );
                return;
              }
              selected = answer[0]!;
              lane.bindings[`alternative:${lane.cursor}`] = selected;
            }
            segment.effects = legal.find((o) => o.id === selected)!.effects;
          }
        }
        if (segment.optional && !lane.optionalAccepted) {
          const key = `${lane.id}:optional:${lane.cursor}`;
          const answer = this.answer(key);
          if (!answer) {
            this.ask(
              key,
              this.resolveChooser(segment.chooser, source),
              'yes_no',
              `是否执行：${source.name}`,
              [
                { id: 'yes', label: '执行' },
                { id: 'no', label: '跳过' },
              ],
            );
            return;
          }
          if (answer[0] === 'no') {
            frame.prepareIndex++;
            continue;
          }
          lane.optionalAccepted = true;
        }
        const targets = inspectSegment(segment, snapshot, this.catalog, lane.choices);
        for (const effect of segment.effects) {
          const target = targets.find((t) => t.effectId === effect.id)!;
          if (target.status !== 'has_target' || target.selected.length) continue;
          const key = `${lane.id}:target:${lane.cursor}:${effect.id}`;
          const answer = this.answer(key);
          if (!answer) {
            const count = requiredTargetCount(effect.target, target.candidates);
            this.ask(
              key,
              this.resolveChooser(effect.chooser, source),
              'targets',
              `${source.name}：选择目标`,
              target.candidates.map((id) => ({ id, label: snapshot.characters[id]?.name ?? id })),
              count,
              count,
            );
            return;
          }
          lane.choices[effect.id] = answer;
          target.selected = answer;
        }
        for (const target of targets)
          if (target.selected[0]) lane.bindings[`$target:${target.effectId}`] = target.selected[0];
        for (const effect of segment.effects)
          if (effect.operation.kind === 'reveal-identity') {
            const targetsToReveal = targets.find(
              (target) => target.effectId === effect.id,
            )!.selected;
            for (const id of targetsToReveal)
              if (
                snapshot.characters[id]?.alive &&
                evaluatePersistent(snapshot, this.catalog).characters[id]?.identity === 'ninja'
              ) {
                const key = `${lane.id}:ninja:${lane.cursor}:${effect.id}:${id}`;
                if (!lane.bindings[key]) {
                  const answer = this.answer(key);
                  if (!answer) {
                    const roles = [
                      ...new Set(
                        Object.values(snapshot.characters).flatMap((c) => [
                          c.configuredIdentity,
                          c.reverseIdentity ?? 'civilian',
                        ]),
                      ),
                    ].filter((id) => id !== 'civilian');
                    this.ask(
                      key,
                      'mastermind',
                      'option',
                      '忍者公开身份：选择宣称的非平民身份',
                      roles.map((id) => ({ id, label: this.catalog.identities[id]!.name })),
                      1,
                      1,
                      false,
                      true,
                    );
                    return;
                  }
                  lane.bindings[key] = answer[0]!;
                }
              }
          }
        for (const effect of segment.effects) {
          if (effect.operation.kind === 'move-counter') {
            const target = targets.find((t) => t.effectId === effect.id)!;
            const donor = snapshot.characters[target.selected[0] ?? ''];
            if (!donor) continue;
            const recipients = selectCandidates(
              effect.operation.to,
              snapshot,
              evaluatePersistent(snapshot, this.catalog),
              this.catalog,
            ).filter((id) => id !== donor.id);
            const types = Object.entries(donor.counters)
              .filter(([, amount]) => amount > 0)
              .map(([type]) => type);
            if (!recipients.length || !types.length) {
              target.status = 'no_target';
              continue;
            }
            for (const [field, values, prompt] of [
              ['recipient', recipients, '选择接收指示物的角色'],
              ['counter', types, '选择要移动的指示物'],
            ] as const) {
              const key = `${lane.id}:transfer:${lane.cursor}:${effect.id}:${field}`;
              if (!lane.bindings[key]) {
                const answer = this.answer(key);
                if (!answer) {
                  this.ask(
                    key,
                    this.resolveChooser(effect.chooser, source),
                    'option',
                    prompt,
                    values.map((id) => ({ id, label: snapshot.characters[id]?.name ?? id })),
                  );
                  return;
                }
                lane.bindings[key] = answer[0]!;
              }
              if (field === 'recipient')
                effect.operation.to = { kind: 'character', id: lane.bindings[key]! };
              else
                effect.operation.counter = lane.bindings[key] as import('./model.js').CounterType;
            }
          }
          if (effect.operation.kind !== 'move-character' || effect.operation.destination) continue;
          const target = targets.find((target) => target.effectId === effect.id)!;
          if (!target.selected.length) continue;
          const candidates = textMoveDestinations(
            snapshot,
            target.selected[0]!,
            effect.operation.adjacent,
            effect.operation.anyArea,
          );
          if (!candidates.length) {
            target.status = 'no_target';
            continue;
          }
          const key = `${lane.id}:destination:${lane.cursor}:${effect.id}`;
          let destination = lane.bindings[key];
          if (!destination) {
            const answer = this.answer(key);
            if (!answer) {
              this.ask(
                key,
                this.resolveChooser(effect.chooser, source),
                'option',
                '选择移动目的地',
                candidates.map((id) => ({ id, label: id })),
              );
              return;
            }
            destination = answer[0]!;
            lane.bindings[key] = destination;
          }
          effect.operation.destination = destination as import('./model.js').AreaId;
        }
        if (
          ['optional', 'goodwill'].includes(source.kind) &&
          lane.cursor === 0 &&
          !lane.outcome.started &&
          !targets.some((t) => ['has_target', 'not_required'].includes(t.status))
        ) {
          lane.done = true;
          frame.prepareIndex++;
          continue;
        }
        if (!lane.authorized) {
          const owner = lane.ownerCharacterId ?? source.characterId;
          if (!owner) throw new Error('GOODWILL_OWNER_REQUIRED');
          const e = evaluatePersistent(this.stateData, this.catalog).characters[owner]!;
          const mastermind = this.stateData.clock.phase === 'mastermind_ability';
          const cannotRefuse = source.goodwill?.cannotRefuse;
          let refused = false;
          if (!mastermind && !cannotRefuse) {
            if (e.traits.includes('must-ignore-goodwill')) refused = true;
            else if (
              e.traits.some((t) => ['ignore-goodwill', 'puppet-ignore-goodwill'].includes(t))
            ) {
              const key = `${lane.id}:refuse`;
              const answer = this.answer(key);
              if (!answer) {
                this.ask(
                  key,
                  'mastermind',
                  'yes_no',
                  `是否拒绝 ${source.name}？`,
                  [
                    { id: 'allow', label: '允许' },
                    { id: 'refuse', label: '拒绝' },
                  ],
                  1,
                  1,
                  false,
                  true,
                );
                return;
              }
              refused = answer[0] === 'refuse';
            }
          }
          lane.authorized = true;
          if (refused) {
            lane.outcome.rejected = true;
            lane.done = true;
            this.log('goodwill-refused', '友好能力被拒绝');
            if (this.stateData.script.moduleId === 'weird_mythology') {
              const beforeEx = this.stateData.ex;
              this.stateData.ex++;
              this.stateData.records.exIncreasedThisLoop = true;
              this.publishBatch([
                { type: 'ex-changed', before: beforeEx, after: this.stateData.ex },
              ]);
              this.pushTiming('ex:changed');
            }
            this.stateData.records.sourceOutcomes[lane.id] = clone(lane.outcome);
            frame.prepareIndex++;
            return;
          }
          if (this.stateData.script.moduleId === 'last_liar') {
            this.stateData.characters[owner]!.marks.communicated = true;
            this.stateData.revision++;
            this.stateData.result = checkStageVictory(this.stateData, this.catalog);
            if (this.stateData.result) {
              lane.done = true;
              this.stateData.records.sourceOutcomes[lane.id] = clone(lane.outcome);
              frame.prepareIndex++;
              return;
            }
          }
        }
        lane.outcome.started = true;
        lane.outcome.targets.push(...targets);
        if (source.usage?.consume === 'on_start' && lane.cursor === 0) {
          const key = this.limitKey(lane.outcome.sourceId, source);
          this.stateData.records.usage[key] = (this.stateData.records.usage[key] ?? 0) + 1;
        }
        for (const limit of source.additionalLimits ?? [])
          if (limit.consume === 'on_start' && lane.cursor === 0) {
            const key = usageKey(
              lane.outcome.sourceId,
              limit.scope,
              this.stateData,
              limit.sharedKey,
            );
            this.stateData.records.usage[key] = (this.stateData.records.usage[key] ?? 0) + 1;
          }
        frame.prepared.push(
          ...buildIntents(lane.id, segment, targets).map((intent) => {
            const identity =
              lane.bindings[
                `${lane.id}:ninja:${lane.cursor}:${intent.effectId}:${intent.targetId}`
              ];
            return identity && intent.operation.kind === 'reveal-identity'
              ? { ...intent, operation: { ...intent.operation, declaredIdentity: identity } }
              : intent;
          }),
        );
        frame.prepareIndex++;
      }
      const before = this.stateData;
      const followerChoices: Record<string, string> = {};
      for (const [servant, candidates] of Object.entries(
        movementFollowers(before, this.catalog, frame.prepared),
      )) {
        const key = `${frame.id}:follow:${servant}:${batchSnapshot.revision}`;
        if (candidates.length === 1) followerChoices[servant] = candidates[0]!;
        else {
          const answer = this.answer(key);
          if (!answer) {
            this.ask(
              key,
              before.leader,
              'targets',
              `${before.characters[servant]!.name}跟随哪名角色？`,
              candidates.map((id) => ({ id, label: before.characters[id]!.name })),
            );
            return;
          }
          followerChoices[servant] = answer[0]!;
        }
      }
      const result = commitBatch(before, this.catalog, frame.prepared, followerChoices);
      this.stateData = result.state;
      frame.stage = 'aftermath';
      this.execution.trace.push({
        id: this.id('batch'),
        type: 'batch',
        data: clone(result.result),
      });
      for (const lane of frame.lanes)
        if (!lane.done && frame.prepared.some((i) => i.sourceInstanceId === lane.id))
          lane.outcome.changed ||= result.result.changedSourceIds.includes(lane.id);
      this.stateData.result = checkStageVictory(this.stateData, this.catalog);
      // Each new timing is a child of the committed batch. Death sources are collected using
      // the saved owner information; completion eligibility is evaluated after these children.
      if (result.result.events.some((e) => e.type === 'ex-changed')) this.pushTiming('ex:changed');
      const revealed = result.result.events.flatMap((e) =>
        e.type === 'identity-revealed' ? [e.targetId] : [],
      );
      if (revealed.length) this.pushTiming('identity:revealed', { characterIds: revealed });
      if (result.result.deaths.length)
        this.pushTiming('character:died', {
          characterIds: result.result.deaths,
          previousIdentities: result.result.deaths.map(
            (id) => `${id}=${evaluatePersistent(before, this.catalog).characters[id]!.identity}`,
          ),
          previousAbilities: result.result.deaths.flatMap((id) =>
            evaluatePersistent(before, this.catalog).characters[id]!.abilities.map(
              (ability) => `${id}=${ability}`,
            ),
          ),
        });
      this.publishBatch(result.result.events);
      for (const lane of frame.lanes)
        if (
          !lane.done &&
          lane.bindings['called-ability'] &&
          !lane.bindings['called-ability-started']
        ) {
          lane.bindings['called-ability-started'] = 'yes';
          this.pushGroup([lane.bindings['called-ability']!], true);
        }
      return;
    }
    if (frame.stage === 'aftermath') {
      frame.stage = 'complete';
      const completed: ResolutionLane[] = [];
      for (const lane of frame.lanes) {
        if (lane.done || lane.cursor !== lane.definition.program.segments.length - 1) continue;
        lane.done = true;
        lane.outcome.completed = true;
        if (
          lane.definition.program.endLoopOnComplete &&
          !this.stateData.records.endRequests.includes(lane.definition.program.endLoopOnComplete)
        )
          this.stateData.records.endRequests.push(lane.definition.program.endLoopOnComplete);
        this.stateData.records.sourceOutcomes[lane.id] = clone(lane.outcome);
        const source = lane.definition;
        const key = this.limitKey(lane.outcome.sourceId, source);
        if (source.usage && source.usage.consume !== 'on_start')
          this.stateData.records.usage[key] = (this.stateData.records.usage[key] ?? 0) + 1;
        for (const limit of source.additionalLimits ?? [])
          if (limit.consume === 'on_complete') {
            const key = usageKey(
              lane.outcome.sourceId,
              limit.scope,
              this.stateData,
              limit.sharedKey,
            );
            this.stateData.records.usage[key] = (this.stateData.records.usage[key] ?? 0) + 1;
          }
        if (['optional', 'goodwill'].includes(source.kind))
          this.stateData.records.usage[usageKey(lane.outcome.sourceId, 'phase', this.stateData)] =
            1;
        completed.push(lane);
        this.execution.trace.push({
          id: this.id('completed'),
          type: 'completed',
          data: clone(lane.outcome),
        });
      }
      // Reverse push keeps source-completion timing distinct and deterministic.
      for (const lane of completed.reverse()) {
        if (lane.definition.kind === 'goodwill')
          this.pushTiming('ability:completed', {
            sourceId: lane.definition.id,
            characterIds: lane.ownerCharacterId ? [lane.ownerCharacterId] : [],
            targetIds: [...new Set(lane.outcome.targets.flatMap((target) => target.selected))],
          });
        if (lane.definition.kind === 'incident')
          this.pushTiming('incident:completed', {
            incidentId: lane.definition.id.replace(/^incident\./, ''),
            characterIds: lane.ownerCharacterId ? [lane.ownerCharacterId] : [],
          });
      }
      return;
    }
    if (frame.stage === 'complete') {
      for (const lane of frame.lanes) {
        if (lane.done) continue;
        if (this.stopped(frame)) {
          lane.done = true;
          lane.outcome.truncated = true;
          this.stateData.records.sourceOutcomes[lane.id] = clone(lane.outcome);
        } else {
          lane.cursor++;
          lane.choices = {};
          lane.optionalAccepted = undefined;
        }
      }
      for (const recordId of new Set(
        frame.lanes.map((lane) => lane.incidentRecord).filter((id) => id !== undefined),
      )) {
        const record = this.stateData.records.incidentHistory[recordId!];
        if (!record) continue;
        const lanes = frame.lanes.filter((lane) => lane.incidentRecord === recordId);
        record.completed = lanes.every((lane) => lane.outcome.completed);
        record.changed ||= lanes.some((lane) => lane.outcome.changed);
      }
      if (frame.lanes.every((lane) => lane.done)) {
        this.execution.frames.pop();
        if (!this.execution.frames.length) this.publishSettledResult();
        return;
      }
      frame.stage = 'prepare';
      frame.readState = clone(this.stateData);
      frame.prepareIndex = 0;
      frame.prepared = [];
    }
  }

  private publishSettledResult(): void {
    const state = this.stateData;
    const kind = state.records.protagonistsDead
      ? 'protagonists-died'
      : state.records.loopFailed
        ? 'loop-failed'
        : null;
    if (!kind) return;
    const key = `result-announced:${state.clock.loop}:${kind}`;
    if (!this.execution.flowData[key]) {
      this.log(kind, kind === 'protagonists-died' ? '主人公死亡' : '主人公失败');
      this.execution.flowData[key] = true;
    }
  }

  private publishBatch(events: import('./model.js').DomainEvent[]): void {
    for (const event of events) {
      if (event.type === 'counter-changed')
        this.log(
          event.type,
          `${this.stateData.characters[event.targetId]?.name ?? event.targetId} ${event.counter}：${event.before} → ${event.after}`,
        );
      if (event.type === 'character-died')
        this.log(event.type, `${this.stateData.characters[event.targetId]!.name}死亡`);
      if (event.type === 'character-resurrected')
        this.log(event.type, `${this.stateData.characters[event.targetId]!.name}复活`);
      if (event.type === 'character-removed')
        this.log(event.type, `${this.stateData.characters[event.targetId]!.name}从版图移除`);
      if (event.type === 'ex-changed') this.log(event.type, `EX：${event.before} → ${event.after}`);
      if (event.type === 'world-moved') this.log(event.type, '发生世界移动');
      if (event.type === 'card-granted' && event.cardKind === 'despair+1')
        this.log(event.type, '剧作家获得绝望+1行动牌');
      if (event.type === 'character-moved')
        this.log(event.type, `${this.stateData.characters[event.targetId]!.name}移动至${event.to}`);
      if (event.type === 'identity-revealed')
        this.log(
          event.type,
          `${this.stateData.characters[event.targetId]!.name}的身份：${this.catalog.identities[event.identityId]?.name ?? event.identityId}`,
        );
    }
  }

  private enterPhase(
    phase: GameState['clock']['phase'],
    afterNode: string,
    runEntryTiming = true,
  ): void {
    this.stateData.clock.phase = phase;
    this.stateData.clock.phaseInstance++;
    this.stateData.clock.node = afterNode;
    this.stateData.revision++;
    this.log(
      'phase',
      `${phase}（第${this.stateData.clock.loop}轮第${this.stateData.clock.day}日）`,
    );
    const special = checkStageVictory(this.stateData, this.catalog);
    if (special) {
      this.stateData.result = special;
      return;
    }
    if (runEntryTiming) this.pushTiming(`phase:${phase}:enter`);
  }

  private resetLoop(): void {
    this.stateData.records.loopFailed = false;
    this.stateData.records.protagonistsDead = false;
    this.stateData.records.endRequests = [];
    this.stateData.records.loopIncidentEntryIds = [];
    this.stateData.records.firstIncidentDay = null;
    this.stateData.records.worldMovedToday = false;
    this.stateData.records.worldMoveIncrementApplied = false;
    this.stateData.records.exIncreasedThisLoop = false;
    this.stateData.records.revealedFacts = this.stateData.records.revealedFacts.filter(
      (fact) => !fact.startsWith('flag:'),
    );
    this.stateData.records.delayed = this.stateData.records.delayed.filter(
      (task) =>
        !task.expiresAtLoopEnd &&
        (task.loop === undefined || task.loop >= this.stateData.clock.loop),
    );
    this.stateData.protagonistProtection = false;
    this.stateData.placements = [];
    this.stateData.curses = [];
    const module = this.catalog.modules[this.stateData.script.moduleId]!;
    if (module.exReset === 'zero') this.stateData.ex = 0;
    for (const area of Object.values(this.stateData.board)) area.intrigue = 0;
    for (const character of Object.values(this.stateData.characters)) {
      character.counters = { goodwill: 0, anxiety: 0, intrigue: 0, hope: 0, despair: 0, guard: 0 };
      character.temporaryIdentity = null;
      character.attachments = [];
      const definition = this.catalog.characters[character.definitionId];
      const spiritLoop = Number(this.stateData.script.options[`spiritLoop:${character.id}`] ?? 1);
      if (character.definitionId === 'spirit' && this.stateData.clock.loop < spiritLoop) {
        character.presence = 'not_entered';
        character.alive = true;
      } else if (['transfer_student', 'temp_worker_alt'].includes(character.definitionId)) {
        character.presence = 'not_entered';
        character.alive = true;
      } else {
        character.presence = 'board';
        character.alive = true;
        character.area = character.initialArea;
      }
      if (character.definitionId === 'temp_worker') character.temporaryIdentity = 'civilian';
      if (
        character.presence === 'board' &&
        !this.stateData.records.revealedFacts.includes(`appeared:${character.id}`)
      )
        this.stateData.records.revealedFacts.push(`appeared:${character.id}`);
      if (!definition) throw new Error(`UNKNOWN_CHARACTER:${character.definitionId}`);
    }
    for (const deck of Object.values(this.stateData.cards))
      for (const card of deck) if (card.zone !== 'excluded') card.zone = 'hand';
    this.stateData.clock.day = 1;
    this.stateData.revision++;
  }

  private resetDay(): void {
    this.stateData.records.worldMovedToday = false;
    this.stateData.records.worldMoveIncrementApplied = false;
    this.stateData.revision++;
  }

  private optionalInstances(phase: GameState['clock']['phase']): string[] {
    const native = nativeOptional(phase, this.stateData, this.catalog);
    for (const source of native) this.execution.generated[source.id] = source;
    return [
      ...this.sourceInstances(`phase:${phase}:enter`),
      ...native.map((source) => source.id),
    ].filter((id) => {
      const source = this.source(id);
      if (!['optional', 'goodwill'].includes(source.kind)) return false;
      if (this.exhausted(id)) return false;
      if (source.kind === 'goodwill') {
        const owner = this.sourceParts(id).ownerCharacterId ?? source.characterId;
        if (!owner || !this.stateData.characters[owner]?.alive) return false;
        const e = evaluatePersistent(this.stateData, this.catalog).characters[owner]!;
        const reverse =
          this.stateData.script.moduleId === 'another_horizon_revised' &&
          this.stateData.ex % 2 === 1;
        const worldCount = reverse ? e.counts.anxiety : e.counts.goodwill;
        if (phase === 'mastermind_ability') {
          if (
            !e.traits.some((t) =>
              ['ignore-goodwill', 'must-ignore-goodwill', 'puppet-ignore-goodwill'].includes(t),
            )
          )
            return false;
          const puppetPermission =
            e.traits.includes('puppet-ignore-goodwill') &&
            worldCount >= (source.goodwill?.threshold ?? Infinity);
          const characterPermission =
            e.counts.goodwill >= (source.goodwill?.mastermindThreshold ?? Infinity);
          if (!puppetPermission && !characterPermission) return false;
        } else if (worldCount < (source.goodwill?.threshold ?? Infinity)) return false;
      }
      return true;
    });
  }

  private optionalMenu(node: string, next: () => void): void {
    const key = `${node}:pick`;
    const answer = this.answer(key);
    const options = this.optionalInstances(this.stateData.clock.phase);
    if (!answer && options.length === 0 && this.stateData.clock.phase === 'loop_end') {
      next();
      return;
    }
    if (!answer) {
      this.ask(
        key,
        options.length
          ? this.resolveChooser(undefined, this.source(options[0]!))
          : this.stateData.clock.phase === 'mastermind_ability' ||
              this.stateData.clock.phase === 'turn_end'
            ? 'mastermind'
            : this.stateData.leader,
        'ability',
        '选择要使用的能力，或结束本阶段',
        [
          ...options.map((id) => ({ id, label: this.source(id).name })),
          { id: 'finish', label: '结束阶段' },
        ],
      );
      return;
    }
    if (answer[0] === 'finish') next();
    else this.pushSource(answer[0]!);
  }

  private actionPlacement(mastermind: boolean): void {
    const state = this.stateData;
    const keyPrefix = mastermind ? 'mastermind_action' : 'protagonist_action';
    const required = mastermind
      ? state.records.revealedFacts.includes(`flag:key-limit:${state.clock.day}`)
        ? 1
        : 3
      : 3;
    const index = Number(this.execution.flowData[`${keyPrefix}:index`] ?? 0);
    if (index >= required) {
      delete this.execution.flowData[`${keyPrefix}:index`];
      if (mastermind) this.enterPhase('protagonist_action', 'protagonist_action.place');
      else this.enterPhase('action_resolution', 'action_resolution.run');
      return;
    }
    const actor = mastermind
      ? 'mastermind'
      : protagonistSeats[(protagonistSeats.indexOf(state.leader as never) + index) % 3]!;
    const selectedKey = `${keyPrefix}:selected-card`;
    const selected = this.execution.flowData[selectedKey] as string | undefined;
    if (!selected) {
      const key = `${keyPrefix}:card:${index}`;
      const answer = this.answer(key);
      if (!answer) {
        const usable = state.cards[actor].filter((card) => card.zone === 'hand');
        this.ask(
          key,
          actor,
          'action_card',
          '选择行动牌',
          usable.map((card) => ({ id: card.id, label: card.kind })),
          1,
          1,
          false,
          true,
        );
        return;
      }
      this.execution.flowData[selectedKey] = answer[0]!;
      return;
    }
    const card = state.cards[actor].find((candidate) => candidate.id === selected)!;
    const targets = legalActionTargets(state, this.catalog, actor, card);
    const key = `${keyPrefix}:target:${index}`;
    const answer = this.answer(key);
    if (!answer) {
      this.ask(
        key,
        actor,
        'action_target',
        '选择行动牌放置位置',
        targets.map((target) => ({
          id: `${target.kind}:${target.id}`,
          label: state.characters[target.id]?.name ?? target.id,
        })),
        1,
        1,
        false,
        true,
      );
      return;
    }
    const [kind, id] = answer[0]!.split(':', 2) as ['character' | 'area', string];
    placeAction(state, this.catalog, actor, selected, { kind, id });
    delete this.execution.flowData[selectedKey];
    this.execution.flowData[`${keyPrefix}:index`] = index + 1;
  }

  private savePreviousLoop(): void {
    this.stateData.records.previousLoop = {
      loop: this.stateData.clock.loop,
      characters: clone(this.stateData.characters),
      board: clone(this.stateData.board),
      ex: this.stateData.ex,
      loopIncidentEntryIds: [...this.stateData.records.loopIncidentEntryIds],
    };
  }

  private normalWinners(): SeatId[] {
    const traitors = new Set(
      evaluatePersistent(this.stateData, this.catalog, 'normal-victory').traitors,
    );
    return protagonistSeats.filter((seat) => !traitors.has(seat));
  }

  private stepFlow(): void {
    const state = this.stateData;
    const node = state.clock.node;
    if (state.result) {
      state.status = 'finished';
      return;
    }
    const beforeLoopReset =
      state.clock.phase === 'loop_start' &&
      [
        'loop_start.skip',
        'loop_start.confirm-skip',
        'loop_start.henchman',
        'loop_start.reset',
      ].includes(node);
    if (
      state.records.endRequests.length &&
      !beforeLoopReset &&
      !['loop_end', 'final_showdown'].includes(state.clock.phase)
    ) {
      this.enterPhase('loop_end', 'loop_end.after_forced');
      return;
    }
    switch (node) {
      case 'setup.validate': {
        const errors = validateNewGame(
          { script: state.script, characters: Object.values(state.characters) },
          this.catalog,
        );
        if (errors.length) throw new Error(`INVALID_SCRIPT:${errors.join(',')}`);
        state.clock.node = 'setup.leader';
        return;
      }
      case 'setup.leader': {
        const key = 'setup:leader';
        const answer = this.answer(key);
        if (!answer) {
          this.ask(
            key,
            'protagonistA',
            'leader',
            '选择初始队长',
            protagonistSeats.map((id) => ({ id, label: id })),
          );
          return;
        }
        state.leader = answer[0] as SeatId;
        this.enterPhase('loop_start', 'loop_start.skip', false);
        return;
      }
      case 'loop_start.skip': {
        if (!state.script.finalShowdown) {
          state.clock.node = 'loop_start.henchman';
          return;
        }
        const key = `loop:${state.clock.loop}:skip`;
        const answer = this.answer(key);
        if (!answer) {
          this.ask(key, state.leader, 'yes_no', '主人公是否一致同意放弃剩余轮回并进入最终决战？', [
            { id: 'yes', label: '进入最终决战' },
            { id: 'no', label: '继续轮回' },
          ]);
          return;
        }
        if (answer[0] === 'yes') state.clock.node = 'loop_start.confirm-skip';
        else state.clock.node = 'loop_start.henchman';
        return;
      }
      case 'loop_start.confirm-skip': {
        const others = protagonistSeats.filter((seat) => seat !== state.leader);
        const index = Number(this.execution.flowData['skip:index'] ?? 0);
        if (index >= others.length) {
          delete this.execution.flowData['skip:index'];
          this.enterPhase('final_showdown', 'final_showdown.prepare');
          return;
        }
        const key = `skip:${state.clock.loop}:${index}`;
        const answer = this.answer(key);
        if (!answer) {
          this.ask(key, others[index]!, 'yes_no', '是否同意放弃全部剩余轮回，进入最终决战？', [
            { id: 'yes', label: '同意' },
            { id: 'no', label: '不同意' },
          ]);
          return;
        }
        if (answer[0] === 'no') {
          delete this.execution.flowData['skip:index'];
          state.clock.node = 'loop_start.henchman';
        } else this.execution.flowData['skip:index'] = index + 1;
        return;
      }
      case 'loop_start.henchman': {
        for (const c of Object.values(state.characters).filter(
          (c) => c.definitionId === 'henchman',
        )) {
          const key = `henchman:${state.clock.loop}:${c.id}`;
          if (this.execution.flowData[key]) continue;
          const answer = this.answer(key);
          if (!answer) {
            this.ask(
              key,
              'mastermind',
              'option',
              '选择手下本轮的初始区域',
              Object.keys(state.board).map((id) => ({ id, label: id })),
            );
            return;
          }
          c.initialArea = answer[0] as import('./model.js').BoardAreaId;
          this.execution.flowData[key] = true;
        }
        state.clock.node = 'loop_start.reset';
        return;
      }
      case 'loop_start.reset':
        this.resetLoop();
        state.clock.node = 'loop_start.optional';
        this.pushTiming('phase:loop_start:enter');
        return;
      case 'loop_start.optional':
        this.optionalMenu(node, () => this.enterPhase('turn_start', 'turn_start.reset', false));
        return;
      case 'turn_start.reset': {
        this.resetDay();
        const worker = Object.values(state.characters).find(
          (c) => c.definitionId === 'temp_worker',
        );
        if (
          worker &&
          !worker.alive &&
          !Object.values(state.characters).some(
            (c) => c.definitionId === 'temp_worker_alt' && c.presence === 'board',
          )
        ) {
          const id = `${worker.id}-replacement`;
          const existing = state.characters[id];
          state.characters[id] = existing
            ? { ...existing, alive: true, presence: 'board', area: 'city' }
            : {
                ...clone(worker),
                id,
                definitionId: 'temp_worker_alt',
                name: '临时工？',
                temporaryIdentity: null,
                publicIdentity: null,
                initialArea: 'city',
                area: 'city',
                presence: 'board',
                alive: true,
                counters: { goodwill: 0, anxiety: 0, intrigue: 0, hope: 0, despair: 0, guard: 0 },
                attachments: [],
                marks: { died: false, communicated: false },
              };
          this.log('character-entered', '临时工？登场');
          if (!state.records.revealedFacts.includes(`appeared:${id}`))
            state.records.revealedFacts.push(`appeared:${id}`);
        }
        for (const character of Object.values(state.characters)) {
          if (character.definitionId === 'transfer_student') {
            const day = Number(state.script.options[`transferDay:${character.id}`] ?? 0);
            if (day === state.clock.day) {
              character.presence = 'board';
              character.area = character.initialArea;
              if (!state.records.revealedFacts.includes(`appeared:${character.id}`))
                state.records.revealedFacts.push(`appeared:${character.id}`);
            }
          }
        }
        state.clock.node = 'turn_start.optional';
        this.pushTiming('phase:turn_start:enter');
        return;
      }
      case 'turn_start.optional':
        this.optionalMenu(node, () =>
          this.enterPhase('mastermind_action', 'mastermind_action.place'),
        );
        return;
      case 'mastermind_action.place':
        this.actionPlacement(true);
        return;
      case 'protagonist_action.place':
        this.actionPlacement(false);
        return;
      case 'action_resolution.run': {
        const revealKey = `actions-revealed:${state.clock.loop}:${state.clock.day}`;
        if (!this.execution.flowData[revealKey]) {
          for (const placement of state.placements) {
            placement.revealed = true;
            const action = state.cards[placement.owner].find(
              (card) => card.id === placement.cardId,
            )!;
            this.log(
              'action-revealed',
              `${placement.owner}：${state.characters[placement.target.id]?.name ?? placement.target.id}／${action.kind}`,
            );
          }
          this.execution.flowData[revealKey] = true;
        }
        const plan = actionMovementPlan(state, this.catalog);
        const follow: Record<string, string> = {};
        for (const [servant, candidates] of Object.entries(plan.followers)) {
          const key = `action:follow:${state.clock.loop}:${state.clock.day}:${servant}`;
          if (candidates.length > 1 && !this.execution.flowData[key]) {
            const answer = this.answer(key);
            if (!answer) {
              this.ask(
                key,
                state.leader,
                'targets',
                `${state.characters[servant]!.name}跟随哪名角色？`,
                candidates.map((id) => ({ id, label: state.characters[id]!.name })),
              );
              return;
            }
            this.execution.flowData[key] = answer[0]!;
          }
          follow[servant] = (this.execution.flowData[key] as string) ?? candidates[0]!;
        }
        const result = resolveActionMovement(state, this.catalog, follow);
        this.stateData = result.state;
        this.publishBatch(result.result.events);
        this.stateData.clock.node = 'action_resolution.cultists';
        return;
      }
      case 'action_resolution.cultists': {
        const ignored: string[] = [];
        for (const [cultist, placements] of Object.entries(cultistForbids(state, this.catalog))) {
          if (!placements.length) continue;
          const key = `action:cultist:${state.clock.loop}:${state.clock.day}:${cultist}`;
          if (!this.execution.flowData[key]) {
            const answer = this.answer(key);
            if (!answer) {
              this.ask(
                key,
                'mastermind',
                'targets',
                '选择邪教徒要无效化的禁止密谋（可不选）',
                placements.map((id) => {
                  const target = state.placements.find((p) => p.id === id)!.target;
                  return { id, label: state.characters[target.id]?.name ?? target.id };
                }),
                0,
                placements.length,
                true,
                true,
              );
              return;
            }
            this.execution.flowData[key] = answer;
          }
          ignored.push(...(this.execution.flowData[key] as string[]));
        }
        const result = resolveActionCounters(state, this.catalog, ignored);
        this.stateData = result.state;
        this.publishBatch(result.events);
        this.enterPhase('mastermind_ability', 'mastermind_ability.optional');
        return;
      }
      case 'mastermind_ability.optional':
        this.optionalMenu(node, () =>
          this.enterPhase('protagonist_ability', 'protagonist_ability.optional'),
        );
        return;
      case 'protagonist_ability.optional':
        this.optionalMenu(node, () => this.enterPhase('incident', 'incident.judge'));
        return;
      case 'incident.judge': {
        const judgement = judgeScheduledIncident(state, this.catalog);
        if (!judgement.occurs || !judgement.definition) {
          if (judgement.scheduled) {
            const entry = state.script.incidents.find((entry) => entry.day === state.clock.day)!;
            this.log('incident-not-occurred', `预定事件未发生：${entry.publicName}`);
          }
          state.clock.node = 'incident.exit';
          return;
        }
        const record = recordIncident(state, judgement);
        this.log('incident', `事件发生：${record.publicName}`);
        const blackCat = judgement.culpritIds.some(
          (id) => state.characters[id]?.definitionId === 'black_cat',
        );
        const beforeEx = state.ex;
        if (blackCat) {
          if (state.script.moduleId === 'mystery_circle') {
            state.ex++;
            state.records.exIncreasedThisLoop = true;
          }
        }
        if (
          !blackCat &&
          state.script.moduleId === 'mystery_circle' &&
          judgement.definition.id !== 'silver_bullet'
        ) {
          state.ex += judgement.definition.id === 'gruesome_murder' ? 2 : 1;
          state.records.exIncreasedThisLoop = true;
        }
        const dynamicId = `incident.${judgement.definition.id}`;
        this.execution.generated[dynamicId] = {
          id: dynamicId,
          name: judgement.definition.name,
          reference: 'appendix incident',
          kind: 'incident',
          timings: [],
          program: judgement.definition.program,
        };
        state.clock.node = 'incident.after';
        this.execution.flowData['incident:record'] = record.sequence;
        this.pushGroup(
          judgement.culpritIds.length
            ? judgement.culpritIds.map((id) => `${dynamicId}@${id}`)
            : [dynamicId],
        );
        if (state.ex !== beforeEx) {
          this.publishBatch([{ type: 'ex-changed', before: beforeEx, after: state.ex }]);
          this.pushTiming('ex:changed');
        }
        return;
      }
      case 'incident.after': {
        const sequence = Number(this.execution.flowData['incident:record']);
        const record = state.records.incidentHistory[sequence];
        if (record?.completed && !record.changed) this.log('incident-no-effect', '事件效果无现象');
        state.clock.node = 'incident.exit';
        return;
      }
      case 'incident.exit':
        this.pushTiming('phase:incident:exit');
        state.clock.node = 'leader_rotation.rotate';
        return;
      case 'leader_rotation.rotate':
        this.enterPhase('leader_rotation', 'leader_rotation.apply', false);
        return;
      case 'leader_rotation.apply':
        state.leader = rotateLeader(state.leader);
        this.enterPhase('turn_end', 'turn_end.module', false);
        return;
      case 'turn_end.module':
        if (state.script.moduleId === 'haunted_stage_again' && state.curses.length) {
          const id = `native.curses:${state.clock.loop}:${state.clock.day}`;
          const attached = state.curses.filter((curse) => curse.kind === 'character');
          this.execution.generated[id] = {
            id,
            name: '诅咒牌前置处理',
            reference: '附录B/HSA',
            kind: 'forced',
            timings: [],
            program: {
              segments: [
                {
                  id: 'attach-and-kill',
                  effects: state.curses.map((curse) =>
                    curse.kind === 'character'
                      ? {
                          id: curse.id,
                          target: { kind: 'character', id: curse.targetId, allowDead: true },
                          operation: { kind: 'death' },
                        }
                      : {
                          id: curse.id,
                          target: { kind: 'characters', filter: { area: curse.targetId as never } },
                          operation: { kind: 'curse', action: 'attach', curseId: curse.id },
                        },
                  ),
                },
                {
                  id: 'drop',
                  effects: attached.map((curse) => ({
                    id: curse.id,
                    target: { kind: 'none' },
                    operation: { kind: 'curse', action: 'drop', curseId: curse.id },
                  })),
                },
              ],
            },
          };
          for (const curse of state.curses.filter((curse) => curse.kind === 'area')) {
            if (
              !Object.values(state.characters).some(
                (c) => c.presence === 'board' && c.alive && c.area === curse.targetId,
              )
            )
              state.records.revealedFacts.push(
                `flag:curse-no-target:${state.clock.day}:${curse.targetId}`,
              );
          }
          state.clock.node = 'turn_end.forced';
          this.pushGroup([id]);
          return;
        }
        if (
          state.script.moduleId === 'another_horizon_revised' &&
          state.records.worldMovedToday &&
          !state.records.worldMoveIncrementApplied
        ) {
          state.ex++;
          state.records.exIncreasedThisLoop = true;
          state.records.worldMoveIncrementApplied = true;
          state.revision++;
          this.publishBatch([{ type: 'ex-changed', before: state.ex - 1, after: state.ex }]);
          this.pushTiming('ex:changed');
        }
        state.clock.node = 'turn_end.forced';
        return;
      case 'turn_end.forced':
        state.clock.node = 'turn_end.optional';
        this.pushTiming('phase:turn_end:enter');
        return;
      case 'turn_end.optional':
        this.optionalMenu(node, () => {
          if (state.clock.day >= state.script.daysPerLoop)
            this.enterPhase('loop_end', 'loop_end.after_forced');
          else {
            state.clock.day++;
            this.enterPhase('turn_start', 'turn_start.reset', false);
          }
        });
        return;
      case 'loop_end.after_forced':
        this.optionalMenu(node, () => {
          state.clock.node = 'loop_end.evaluate';
        });
        return;
      case 'loop_end.evaluate':
        this.savePreviousLoop();
        if (!state.records.loopFailed && !state.records.protagonistsDead) {
          state.result = { winners: this.normalWinners(), reason: 'protagonists-won-loop' };
          return;
        }
        if (state.script.moduleId === 'weird_mythology' && state.ex >= 4) {
          if (state.script.finalShowdown)
            this.enterPhase('final_showdown', 'final_showdown.prepare');
          else state.result = { winners: ['mastermind'], reason: 'all-loops-failed' };
          return;
        }
        if (state.clock.loop < state.script.loops) {
          state.clock.loop++;
          this.enterPhase('loop_start', 'loop_start.skip', false);
          return;
        }
        if (state.script.finalShowdown) this.enterPhase('final_showdown', 'final_showdown.prepare');
        else state.result = { winners: ['mastermind'], reason: 'all-loops-failed' };
        return;
      case 'final_showdown.prepare': {
        const traitors =
          state.script.moduleId === 'last_liar' && state.clock.loop !== state.script.loops
            ? state.traitors
            : evaluatePersistent(state, this.catalog).traitors;
        this.execution.flowData['showdown:participants'] = protagonistSeats.filter(
          (seat) => !traitors.includes(seat),
        );
        const c = protagonistSeats.find(
          (seat) => state.secretLetters[seat] === 'C' && traitors.includes(seat),
        );
        if (
          c &&
          state.script.ruleIds.some((id) => this.catalog.rules?.[id]?.name === '我才是名侦探')
        ) {
          this.execution.flowData['showdown:c'] = c;
          this.execution.flowData['showdown:c-index'] = 0;
          state.clock.node = 'final_showdown.c';
        } else state.clock.node = 'final_showdown.reset';
        return;
      }
      case 'final_showdown.c': {
        const index = Number(this.execution.flowData['showdown:c-index']);
        const actor = this.execution.flowData['showdown:c'] as SeatId;
        const incident = state.script.incidents[index];
        if (!incident) {
          state.result = { winners: [actor], reason: 'll.special-victory-c' };
          return;
        }
        const key = `showdown:c:${index}`;
        const answer = this.answer(key);
        if (!answer) {
          this.ask(
            key,
            actor,
            'incident_culprit_guess',
            `推理第${incident.day}天${incident.publicName}的当事人`,
            Object.values(state.characters)
              .filter((c) => c.definitionId !== 'temp_worker_alt')
              .map((c) => ({ id: c.id, label: c.name })),
          );
          return;
        }
        if (answer[0] !== incident.culpritIds[0]) state.clock.node = 'final_showdown.reset';
        else this.execution.flowData['showdown:c-index'] = index + 1;
        return;
      }
      case 'final_showdown.reset':
        for (const area of Object.values(state.board)) area.intrigue = 0;
        state.ex = 0;
        for (const character of Object.values(state.characters)) {
          if (
            character.presence === 'not_entered' &&
            !state.records.revealedFacts.includes(`appeared:${character.id}`)
          )
            continue;
          character.presence = 'board';
          character.alive = true;
          character.area = character.initialArea;
          character.counters = {
            goodwill: 0,
            anxiety: 0,
            intrigue: 0,
            hope: 0,
            despair: 0,
            guard: 0,
          };
        }
        this.execution.flowData['showdown:answered'] = [];
        state.clock.node = 'final_showdown.pick';
        return;
      case 'final_showdown.pick': {
        const participants = this.execution.flowData['showdown:participants'] as SeatId[];
        if (!participants.length) {
          state.result = { winners: ['mastermind'], reason: 'no-eligible-protagonist' };
          return;
        }
        const answered = this.execution.flowData['showdown:answered'] as string[];
        const remaining = Object.values(state.characters).filter(
          (c) => c.presence === 'board' && !answered.includes(c.id),
        );
        if (!remaining.length) {
          state.result = { winners: participants, reason: 'final-showdown-cleared' };
          return;
        }
        const key = `showdown:pick:${answered.length}`;
        const answer = this.answer(key);
        if (!answer) {
          this.ask(
            key,
            participants.includes(state.leader) ? state.leader : participants[0]!,
            'targets',
            '选择尚未回答的角色',
            remaining.map((c) => ({ id: c.id, label: c.name })),
          );
          return;
        }
        this.execution.flowData['showdown:character'] = answer[0]!;
        this.execution.flowData['showdown:reverse'] = false;
        state.clock.node = 'final_showdown.guess';
        return;
      }
      case 'final_showdown.guess': {
        const participants = this.execution.flowData['showdown:participants'] as SeatId[];
        const character =
          state.characters[this.execution.flowData['showdown:character'] as string]!;
        const reverse = this.execution.flowData['showdown:reverse'] === true;
        const key = `showdown:${character.id}:${reverse}`;
        const answer = this.answer(key);
        if (!answer) {
          this.ask(
            key,
            participants[0] ?? state.leader,
            'identity_guess',
            `推理 ${character.name} 的${reverse ? '里世界' : '表面'}身份`,
            Object.values(this.catalog.identities).map((identity) => ({
              id: identity.id,
              label: identity.name,
            })),
          );
          return;
        }
        if (answer[0] !== (reverse ? character.reverseIdentity : character.configuredIdentity)) {
          state.result = { winners: ['mastermind'], reason: 'final-showdown-wrong-answer' };
          return;
        }
        if (character.reverseIdentity && !reverse)
          this.execution.flowData['showdown:reverse'] = true;
        else {
          (this.execution.flowData['showdown:answered'] as string[]).push(character.id);
          state.clock.node = 'final_showdown.pick';
        }
        return;
      }
      default:
        throw new Error(`UNKNOWN_FLOW_NODE:${node}`);
    }
  }

  private drive(): void {
    if (this.stateData.status === 'finished' || this.stateData.status === 'faulted') return;
    this.stateData.status = 'running';
    let safety = 0;
    try {
      while (
        !this.execution.waiting &&
        (this.execution.frames.length > 0 || !this.stateData.result)
      ) {
        if (++safety > 20_000) throw new Error('FLOW_LOOP_GUARD');
        const frame = this.execution.frames.at(-1);
        if (frame) this.stepResolution(frame);
        else this.stepFlow();
      }
      if (this.stateData.result && !this.execution.waiting && !this.execution.frames.length)
        this.stateData.status = 'finished';
      else if (this.execution.waiting) this.stateData.status = 'waiting';
    } catch (error) {
      this.execution.fault = error instanceof Error ? error.message : String(error);
      this.stateData.status = 'faulted';
      throw error;
    }
  }

  submit(actor: SeatId, input: unknown): Receipt {
    const parsed = choiceSchema.safeParse(input);
    if (!parsed.success)
      return { status: 'rejected', revision: this.stateData.revision, code: 'INVALID_INPUT' };
    const command = parsed.data;
    const existing = this.execution.receipts[command.commandId];
    if (existing)
      return existing.actor === actor && existing.fingerprint === fingerprint(command)
        ? { status: 'accepted', revision: existing.revision }
        : { status: 'rejected', revision: this.stateData.revision, code: 'ID_REUSED' };
    if (command.sessionId !== this.sessionId || command.branchId !== this.branchId)
      return { status: 'rejected', revision: this.stateData.revision, code: 'WRONG_SESSION' };
    const waiting = this.execution.waiting;
    if (!waiting || waiting.id !== command.waitingInputId || actor !== waiting.actor)
      return { status: 'rejected', revision: this.stateData.revision, code: 'NOT_ALLOWED' };
    if (command.expectedRevision !== this.stateData.revision)
      return { status: 'rejected', revision: this.stateData.revision, code: 'STALE' };
    const selected = command.command.optionIds;
    const allowed = new Set(waiting.options.map((option) => option.id));
    if (
      selected.length < waiting.minSelections ||
      selected.length > waiting.maxSelections ||
      new Set(selected).size !== selected.length ||
      selected.some((id) => !allowed.has(id))
    )
      return { status: 'rejected', revision: this.stateData.revision, code: 'INVALID_OPTION' };
    const backupState = clone(this.stateData);
    const backupExecution = clone(this.execution);
    try {
      this.execution.answers[this.execution.waitingKey!] = [...selected];
      this.execution.waiting = null;
      this.execution.waitingKey = null;
      this.stateData.revision++;
      this.drive();
      this.execution.receipts[command.commandId] = {
        fingerprint: fingerprint(command),
        actor,
        revision: this.stateData.revision,
      };
      return { status: 'accepted', revision: this.stateData.revision };
    } catch {
      this.stateData = backupState;
      this.execution = backupExecution;
      return { status: 'rejected', revision: this.stateData.revision, code: 'ENGINE_ERROR' };
    }
  }

  view(seat: SeatId): VisibleSessionSnapshot {
    const mastermind = seat === 'mastermind';
    return {
      sessionId: this.sessionId,
      branchId: this.branchId,
      revision: this.stateData.revision,
      status: this.stateData.status,
      phase: this.stateData.clock.phase,
      node: this.stateData.clock.node,
      loop: this.stateData.clock.loop,
      day: this.stateData.clock.day,
      leader: this.stateData.leader,
      publicScript: {
        moduleId: this.stateData.script.moduleId,
        loops: this.stateData.script.loops,
        daysPerLoop: this.stateData.script.daysPerLoop,
        finalShowdown: this.stateData.script.finalShowdown,
        discussionRestriction:
          this.stateData.script.discussionRestriction ??
          (this.stateData.script.moduleId === 'last_liar' ? '轮回中禁止商议' : '允许商议'),
        specialRules: [...(this.stateData.script.specialRules ?? [])],
        incidents: this.stateData.script.incidents.map((entry) => ({
          day: entry.day,
          name: entry.publicName,
          ...(entry.publicInfo !== undefined ? { publicInfo: entry.publicInfo } : {}),
        })),
      },
      characters: Object.values(this.stateData.characters).map((c) => ({
        id: c.id,
        definitionId: c.definitionId,
        name: c.name,
        area: c.area,
        alive: c.alive,
        presence: c.presence,
        counters: { ...c.counters },
        ...(mastermind
          ? {
              identity: evaluatePersistent(this.stateData, this.catalog).characters[c.id]!.identity,
            }
          : {}),
        ...(c.publicIdentity ? { publicIdentity: c.publicIdentity } : {}),
        marks: [c.marks.communicated ? 'communicated' : '', c.marks.died ? 'died' : ''].filter(
          Boolean,
        ),
        exCard: c.attachments.some((key) =>
          ['bond-ex', 'dice-ex', 'uploader-ex', 'fake-suicide'].includes(key),
        ),
      })),
      board: clone(this.stateData.board),
      ex: this.stateData.ex,
      curses: clone(this.stateData.curses),
      territories: Object.values(this.stateData.characters)
        .filter((c) => c.definitionId === 'big_shot')
        .flatMap((c) => {
          const area = this.stateData.script.options[`territory:${c.id}`];
          return typeof area === 'string' ? [{ characterId: c.id, area }] : [];
        }),
      ...(this.stateData.secretLetters[seat]
        ? { secretLetter: this.stateData.secretLetters[seat] }
        : {}),
      hand: this.stateData.cards[seat].map((card) => ({
        id: card.id,
        kind: card.kind,
        zone: card.zone,
      })),
      placements: this.stateData.placements.map((p) => ({
        id: p.id,
        owner: p.owner,
        target: clone(p.target),
        ...(p.revealed || p.owner === seat
          ? { cardKind: this.stateData.cards[p.owner].find((c) => c.id === p.cardId)!.kind }
          : {}),
      })),
      waiting: this.execution.waiting?.actor === seat ? clone(this.execution.waiting) : null,
      result: this.stateData.status === 'finished' ? clone(this.stateData.result) : null,
      publicLog: clone(this.stateData.publicLog),
    };
  }

  serialize(): string {
    const save: EngineSave = {
      engineVersion: '2.0.0',
      catalogFingerprint: catalogFingerprint(this.catalog),
      sessionId: this.sessionId,
      branchId: this.branchId,
      state: this.stateData,
      execution: this.execution,
    };
    return JSON.stringify(save);
  }

  static restore(serialized: string, catalog: ContentCatalog): RulesEngine {
    const save = parseCheckpoint(serialized) as EngineSave;
    if (save.engineVersion !== '2.0.0') throw new Error('ENGINE_VERSION_MISMATCH');
    if (save.catalogFingerprint !== catalogFingerprint(catalog))
      throw new Error('CONTENT_FINGERPRINT_MISMATCH');
    const engine = new RulesEngine(save.state, catalog, save.sessionId, save.branchId);
    engine.execution = clone(save.execution);
    return engine;
  }
}

export { RulesEngine as Engine };
