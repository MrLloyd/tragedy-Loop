import type {
  ContentCatalog,
  EffectiveCharacter,
  EffectiveState,
  GameState,
  PersistentRuleDefinition,
} from './model.js';
import { matches } from './query.js';

export function orderPersistent(rules: PersistentRuleDefinition[]): PersistentRuleDefinition[] {
  const map = new Map(rules.map((r) => [r.id, r]));
  if (map.size !== rules.length) throw new Error('PERSISTENT_DUPLICATE');
  const result: PersistentRuleDefinition[] = [];
  const visiting = new Set<string>();
  const done = new Set<string>();
  const visit = (id: string): void => {
    if (done.has(id)) return;
    if (visiting.has(id)) throw new Error(`PERSISTENT_CYCLE:${id}`);
    const rule = map.get(id);
    if (!rule) throw new Error(`PERSISTENT_MISSING_DEPENDENCY:${id}`);
    visiting.add(id);
    for (const dependency of [...rule.dependsOn].sort()) visit(dependency);
    visiting.delete(id);
    done.add(id);
    result.push(rule);
  };
  for (const id of [...map.keys()].sort()) visit(id);
  return result;
}

function baseCharacter(state: GameState, catalog: ContentCatalog, id: string): EffectiveCharacter {
  const c = state.characters[id]!;
  let identityId =
    c.temporaryIdentity ??
    (state.script.moduleId === 'another_horizon_revised' && state.ex % 2 === 1
      ? (c.reverseIdentity ?? c.configuredIdentity)
      : c.configuredIdentity);
  const enabled = (id: string) => state.script.ruleIds.includes(id);
  const anxiety = c.counters.anxiety + c.counters.despair;
  if (c.definitionId === 'temp_worker') identityId = 'civilian';
  else if (enabled('mz.y.bond_of_fate') && c.attachments.includes('bond-ex'))
    identityId = 'key_person';
  else if (c.presence === 'board') {
    if (c.alive && enabled('btx.x.delusion_virus') && identityId === 'civilian' && anxiety >= 3)
      identityId = 'serial_killer';
    if (
      c.alive &&
      enabled('ahr.x.fantasy_virus') &&
      state.ex % 2 === 1 &&
      ['civilian', 'causal_fragment'].includes(identityId) &&
      Object.values(c.counters).filter((n) => n > 0).length >= 2
    )
      identityId = 'serial_killer';
    if (
      !c.alive &&
      enabled('hsa.y.ancient_tomb') &&
      ['civilian', 'coward', 'paper_tiger'].includes(identityId)
    )
      identityId = 'zombie';
  }
  const identity = catalog.identities[identityId];
  const definition = catalog.characters[c.definitionId];
  const traits = new Set([...(identity?.traits ?? []), ...(definition?.traits ?? [])]);
  if (c.counters.despair > 0) traits.add('must-ignore-goodwill');
  if (c.counters.hope > 0) {
    traits.delete('ignore-goodwill');
    traits.delete('must-ignore-goodwill');
    traits.delete('puppet-ignore-goodwill');
  }
  return {
    id,
    identity: identityId,
    traits: [...traits].sort(),
    abilities: [...(identity?.abilities ?? [])].sort(),
    counts: {
      goodwill: c.counters.goodwill + c.counters.hope,
      anxiety: c.counters.anxiety + c.counters.despair,
      intrigue: Math.max(0, c.counters.intrigue + c.counters.despair - c.counters.hope),
    },
    placementBanned: false,
    placementBannedFor: [],
    ignoredForbiddenAreas: false,
    incidentBanned: false,
    incidentForced: false,
    incidentThreshold: 0,
  };
}

export function evaluatePersistent(
  state: GameState,
  catalog: ContentCatalog,
  context = state.clock.node,
): EffectiveState {
  const effective: EffectiveState = {
    revision: state.revision,
    context,
    characters: Object.fromEntries(
      Object.keys(state.characters).map((id) => [id, baseCharacter(state, catalog, id)]),
    ),
    traitors: [...state.traitors],
    areaIntrigue: Object.fromEntries(
      Object.entries(state.board).map(([id, area]) => [id, area.intrigue]),
    ) as EffectiveState['areaIntrigue'],
    evidence: {},
  };
  if (state.script.ruleIds.includes('ll.y.sealed_end')) {
    for (const area of Object.keys(state.board) as Array<keyof typeof state.board>)
      effective.areaIntrigue[area] = Math.max(
        0,
        state.board[area].intrigue +
          Object.values(state.characters)
            .filter((c) => c.alive && c.presence === 'board' && c.area === area)
            .reduce((sum, c) => sum + c.counters.despair - c.counters.hope, 0),
      );
  }
  const writers = new Map<string, { rule: PersistentRuleDefinition; value: string | number }>();
  const depends = (rule: PersistentRuleDefinition, id: string): boolean =>
    rule.dependsOn.some(
      (key) => key === id || (catalog.persistent[key] && depends(catalog.persistent[key]!, id)),
    );
  for (const rule of orderPersistent(Object.values(catalog.persistent))) {
    if (
      rule.enabledBy &&
      rule.enabledBy !== state.script.moduleId &&
      !state.script.ruleIds.includes(rule.enabledBy)
    )
      continue;
    if (!matches(rule.condition, state, effective, catalog)) continue;
    for (const contribution of rule.contributions) {
      const key =
        contribution.kind === 'identity'
          ? `identity:${contribution.characterId}`
          : ['trait-add', 'trait-remove'].includes(contribution.kind)
            ? `trait:${contribution.characterId}:${contribution.value}`
            : null;
      if (key) {
        const value = contribution.kind === 'identity' ? contribution.value : contribution.kind;
        const prior = writers.get(key);
        if (prior && prior.value !== value && !depends(rule, prior.rule.id))
          throw new Error(`PERSISTENT_CONFLICT:${prior.rule.id}:${rule.id}`);
        writers.set(key, { rule, value });
      }
      const c = contribution.characterId
        ? effective.characters[contribution.characterId]
        : undefined;
      const evidenceKey = `${contribution.kind}:${contribution.characterId ?? 'global'}:${String(contribution.value)}`;
      (effective.evidence[evidenceKey] ??= []).push(rule.id);
      switch (contribution.kind) {
        case 'identity':
          if (!c) throw new Error(`PERSISTENT_UNKNOWN_CHARACTER:${rule.id}`);
          c.identity = String(contribution.value);
          c.traits = [
            ...(catalog.characters[state.characters[c.id]!.definitionId]?.traits ?? []),
            ...(catalog.identities[c.identity]?.traits ?? []),
          ];
          c.abilities = [...(catalog.identities[c.identity]?.abilities ?? [])];
          break;
        case 'trait-add':
          if (!c) throw new Error(`PERSISTENT_UNKNOWN_CHARACTER:${rule.id}`);
          c.traits.push(String(contribution.value));
          break;
        case 'trait-remove':
          if (!c) throw new Error(`PERSISTENT_UNKNOWN_CHARACTER:${rule.id}`);
          c.traits = c.traits.filter((v) => v !== contribution.value);
          break;
        case 'ability-add':
          if (!c) throw new Error(`PERSISTENT_UNKNOWN_CHARACTER:${rule.id}`);
          c.abilities.push(String(contribution.value));
          break;
        case 'traitor-add':
          effective.traitors.push(contribution.value as never);
          break;
        case 'traitor-remove':
          effective.traitors = effective.traitors.filter((s) => s !== contribution.value);
          break;
        case 'placement-ban':
          if (c) c.placementBanned = true;
          break;
        case 'movement-ban-remove':
          if (c) c.ignoredForbiddenAreas = true;
          break;
        case 'incident-ban':
          if (c) c.incidentBanned = true;
          break;
        case 'incident-force':
          if (c) c.incidentForced = true;
          break;
        case 'count-area-extra':
          for (const area of Object.keys(state.board) as Array<keyof typeof state.board>) {
            const cards = Object.values(state.characters).filter(
              (card) => card.presence === 'board' && card.alive && card.area === area,
            );
            effective.areaIntrigue[area] = Math.max(
              0,
              state.board[area].intrigue +
                cards.reduce((sum, card) => sum + card.counters.despair - card.counters.hope, 0),
            );
          }
          break;
        case 'incident-count-mode':
          if (c && ['anxiety', 'goodwill', 'intrigue'].includes(String(contribution.value)))
            c.incidentCountMode = contribution.value as 'anxiety' | 'goodwill' | 'intrigue';
          break;
        case 'incident-threshold':
          if (c) c.incidentThreshold += Number(contribution.value);
          break;
      }
    }
  }
  for (const c of Object.values(effective.characters)) {
    const card = state.characters[c.id]!;
    const living = card.presence === 'board' && card.alive;
    if (c.identity === 'unstable_factor') {
      if (effective.areaIntrigue.school >= 2) c.abilities.push('gossip');
      if (effective.areaIntrigue.city >= 2) c.abilities.push('key_person');
    }
    if (c.identity === 'faceless') c.abilities.push(state.ex <= 1 ? 'gossip' : 'deep_one');
    if (c.identity === 'eccentric' && state.clock.day % 3 === 0)
      c.abilities.push('gossip', 'mastermind', 'serial_killer');
    if (c.identity === 'paranoid' && state.script.ruleIds.includes('wm.x.whispers_of_the_deep'))
      c.abilities.push('key_person');
    if (
      c.identity === 'key' &&
      state.script.ruleIds.some((id) => catalog.rules?.[id]?.name === '捏造的秘密')
    )
      c.traits.push('ignore-goodwill');
    if (c.identity === 'paper_tiger' && c.counts.anxiety >= 2) {
      c.traits = c.traits.filter((t) => t !== 'immortal');
      c.traits.push('must-ignore-goodwill');
    }
    if (card.counters.despair > 0) c.traits.push('must-ignore-goodwill');
    if (
      state.script.ruleIds.includes('ahr.x.puppet_strings') &&
      c.traits.some((t) => t.includes('ignore-goodwill'))
    ) {
      c.traits = c.traits.filter((t) => !t.includes('ignore-goodwill'));
      c.traits.push('puppet-ignore-goodwill');
    }
    if (living && ['prophet', 'werewolf'].includes(c.identity))
      c.placementBannedFor.push('mastermind');
    if (card.attachments.includes('fake-suicide'))
      c.placementBannedFor.push('protagonistA', 'protagonistB', 'protagonistC');
    c.incidentBanned ||= card.attachments.includes('incident-ban');
    c.ignoredForbiddenAreas ||= card.attachments.includes('free-movement');
    if (living) {
      const neighbours = Object.values(effective.characters).filter(
        (other) =>
          state.characters[other.id]!.alive &&
          state.characters[other.id]!.presence === 'board' &&
          state.characters[other.id]!.area === card.area,
      );
      c.incidentBanned ||= neighbours.some(
        (other) => other.id !== c.id && other.identity === 'prophet',
      );
      c.incidentForced ||=
        c.identity === 'obstinate' ||
        (state.ex === 0 && neighbours.some((other) => other.identity === 'detective')) ||
        (card.counters.despair > 0 && neighbours.some((other) => other.identity === 'watcher'));
    }
    c.traits = [...new Set(c.traits)].sort();
    c.abilities = [...new Set(c.abilities)].sort();
    if (state.characters[c.id]!.counters.hope > 0)
      c.traits = c.traits.filter(
        (t) => !['ignore-goodwill', 'must-ignore-goodwill', 'puppet-ignore-goodwill'].includes(t),
      );
  }
  effective.traitors = [...new Set(effective.traitors)].sort();
  if (
    state.script.ruleIds.includes('ll.y.final_plan') &&
    Object.values(effective.characters).some(
      (c) =>
        c.identity === 'key_person' &&
        state.characters[c.id]!.presence === 'board' &&
        state.characters[c.id]!.counters.hope > 0,
    )
  )
    effective.traitors = [];
  if (state.script.ruleIds.includes('ll.y.sealed_end')) {
    for (const area of Object.keys(state.board) as Array<keyof typeof state.board>) {
      effective.areaIntrigue[area] = Math.max(
        0,
        state.board[area].intrigue +
          Object.values(state.characters)
            .filter((c) => c.alive && c.presence === 'board' && c.area === area)
            .reduce((sum, c) => sum + c.counters.despair - c.counters.hope, 0),
      );
    }
  }
  return effective;
}

export function checkStageVictory(state: GameState, catalog: ContentCatalog): GameState['result'] {
  if (state.result || state.script.moduleId !== 'last_liar') return state.result;
  const effective = evaluatePersistent(state, catalog, `victory:${state.clock.phase}`);
  const seatFor = (letter: 'A' | 'B') =>
    Object.entries(state.secretLetters).find(([, value]) => value === letter)?.[0] as
      | GameState['leader']
      | undefined;
  const b = seatFor('B');
  const a = seatFor('A');
  if (
    state.clock.phase === 'protagonist_ability' &&
    state.script.ruleIds.includes('ll.x.myth_collector') &&
    b &&
    effective.traitors.includes(b) &&
    Object.values(state.characters).filter((c) => c.marks.communicated).length >= 6
  )
    return { winners: [b], reason: 'll.special-victory-b' };
  if (
    state.clock.phase === 'turn_end' &&
    state.script.ruleIds.includes('ll.x.true_monster') &&
    a &&
    effective.traitors.includes(a) &&
    Object.values(state.characters).filter((c) => c.marks.died).length >= 5
  )
    return { winners: [a], reason: 'll.special-victory-a' };
  return null;
}
