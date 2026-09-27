import type { ContentCatalog, GameState, IncidentDefinition, IncidentRecord } from './model.js';
import { evaluatePersistent } from './persistent.js';

export interface IncidentJudgement {
  scheduled: boolean;
  occurs: boolean;
  entryId?: string;
  definition?: IncidentDefinition;
  culpritIds: string[];
  reason:
    | 'none-scheduled'
    | 'unknown-incident'
    | 'no-living-culprit'
    | 'banned'
    | 'forced'
    | 'threshold'
    | 'below-threshold'
    | 'crowd-threshold';
  count?: number;
  threshold?: number;
}

export function judgeScheduledIncident(
  state: GameState,
  catalog: ContentCatalog,
): IncidentJudgement {
  const scheduled = state.script.incidents.find((entry) => entry.day === state.clock.day);
  if (!scheduled)
    return { scheduled: false, occurs: false, culpritIds: [], reason: 'none-scheduled' };
  const definition = catalog.incidents[scheduled.incidentId];
  if (!definition) throw new Error(`UNKNOWN_INCIDENT:${scheduled.incidentId}`);
  if (definition.crowd) {
    const area = scheduled.crowdArea;
    const corpses = area
      ? Object.values(state.characters).filter(
          (c) => !c.alive && c.presence === 'board' && c.area === area,
        ).length +
        (state.script.moduleId === 'haunted_stage_again' ? state.board[area].intrigue : 0)
      : 0;
    return {
      scheduled: true,
      occurs: corpses >= definition.crowd.requiredCorpses,
      entryId: scheduled.entryId,
      definition,
      culpritIds: [],
      reason: 'crowd-threshold',
      count: corpses,
      threshold: definition.crowd.requiredCorpses,
    };
  }
  const effective = evaluatePersistent(state, catalog, 'incident:judgement');
  const configuredCulprits = [...scheduled.culpritIds];
  for (const id of scheduled.culpritIds)
    if (state.characters[id]?.definitionId === 'temp_worker') {
      const alternative = Object.values(state.characters).find(
        (c) => c.definitionId === 'temp_worker_alt',
      );
      if (alternative) configuredCulprits.push(alternative.id);
    }
  const culprits = [...new Set(configuredCulprits)].filter((id) => {
    const c = state.characters[id];
    return c?.alive && c.presence === 'board';
  });
  if (!culprits.length)
    return {
      scheduled: true,
      occurs: false,
      entryId: scheduled.entryId,
      definition,
      culpritIds: [],
      reason: 'no-living-culprit',
    };
  const unbanned = culprits.filter((id) => !effective.characters[id]!.incidentBanned);
  if (!unbanned.length)
    return {
      scheduled: true,
      occurs: false,
      entryId: scheduled.entryId,
      definition,
      culpritIds: culprits,
      reason: 'banned',
    };
  const forced = unbanned.filter(
    (id) => definition.alwaysOccurs || effective.characters[id]!.incidentForced,
  );
  const reverseWorld = state.script.moduleId === 'another_horizon_revised' && state.ex % 2 === 1;
  let best: { id: string; count: number; threshold: number } | null = null;
  const qualified = [...forced];
  for (const id of unbanned) {
    if (forced.includes(id)) continue;
    const c = state.characters[id]!;
    const def = catalog.characters[c.definitionId];
    const mode =
      definition.countMode ??
      effective.characters[id]!.incidentCountMode ??
      (reverseWorld ? 'goodwill' : 'anxiety');
    let count = effective.characters[id]!.counts[mode];
    if (mode === 'anxiety') {
      const tokenTypes = new Set<keyof typeof c.counters>(['anxiety', 'despair']);
      if (
        effective.characters[id]!.identity === 'sacrifice' ||
        (state.script.ruleIds.includes('mc.y.strychnine_poison') &&
          ['serial_murder', 'suicide'].includes(definition.id))
      )
        tokenTypes.add('intrigue');
      if (c.definitionId === 'ai')
        for (const type of Object.keys(c.counters) as Array<keyof typeof c.counters>)
          tokenTypes.add(type);
      count = [...tokenTypes].reduce((sum, type) => sum + c.counters[type], 0);
    }
    let threshold =
      typeof def?.anxietyLimit === 'number'
        ? def.anxietyLimit
        : Number(state.script.options[`hermitX:${id}`] ?? 0);
    let adjustment = definition.thresholdAdjustment ?? 0;
    if (effective.characters[id]!.traits.includes('cult-leader')) adjustment *= 2;
    threshold += adjustment + effective.characters[id]!.incidentThreshold;
    if (
      effective.characters[id]!.identity === 'civilian' &&
      state.script.ruleIds.includes('mz.x.doom_chant') &&
      Object.values(effective.characters).some(
        (other) =>
          other.identity === 'prophet' &&
          state.characters[other.id]!.alive &&
          state.characters[other.id]!.presence === 'board',
      )
    )
      threshold--;
    if (count >= threshold) qualified.push(id);
    if (!best || count - threshold > best.count - best.threshold) best = { id, count, threshold };
  }
  const occurs = qualified.length > 0;
  return {
    scheduled: true,
    occurs,
    entryId: scheduled.entryId,
    definition,
    culpritIds: qualified,
    reason: forced.length ? 'forced' : occurs ? 'threshold' : 'below-threshold',
    count: best?.count,
    threshold: best?.threshold,
  };
}

export function recordIncident(
  state: GameState,
  judgement: IncidentJudgement,
  calledByAi = false,
): IncidentRecord {
  if (!judgement.definition || !judgement.entryId) throw new Error('INCIDENT_NOT_RECORDABLE');
  const scheduled = state.script.incidents.find((entry) => entry.entryId === judgement.entryId)!;
  const record: IncidentRecord = {
    sequence: state.records.incidentHistory.length,
    entryId: judgement.entryId,
    incidentId: judgement.definition.id,
    publicName: scheduled.publicName,
    culpritIds: [...judgement.culpritIds],
    loop: state.clock.loop,
    day: state.clock.day,
    completed: false,
    changed: false,
    calledByAi,
  };
  if (!calledByAi) {
    state.records.incidentHistory.push(record);
    state.records.loopIncidentEntryIds.push(record.entryId);
    state.records.firstIncidentDay ??= state.clock.day;
  }
  return record;
}
