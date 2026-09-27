import type {
  AreaId,
  CharacterFilter,
  Condition,
  ContentCatalog,
  EffectiveState,
  GameState,
  Selector,
  ValueExpr,
} from './model.js';

export function virtualCorpse(
  state: GameState,
  id: string,
): { area: import('./model.js').BoardAreaId; identity: string } | null {
  if (state.script.moduleId !== 'haunted_stage_again') return null;
  const match = /^victim:(hospital|shrine|city|school):(\d+)$/.exec(id);
  if (!match) return null;
  const area = match[1] as import('./model.js').BoardAreaId;
  if (Number(match[2]) >= state.board[area].intrigue) return null;
  return {
    area,
    identity: state.script.ruleIds.includes('hsa.y.ancient_tomb') ? 'zombie' : 'civilian',
  };
}

export function readValue(
  expr: ValueExpr,
  state: GameState,
  effective: EffectiveState,
  catalog?: ContentCatalog,
): number {
  if (typeof expr === 'number') return expr;
  switch (expr.kind) {
    case 'counter': {
      const c = state.characters[expr.target];
      if (!c) return 0;
      if (!expr.effective) return c.counters[expr.counter];
      const e = effective.characters[expr.target];
      if (!e) return 0;
      if (expr.counter === 'goodwill') return e.counts.goodwill;
      if (expr.counter === 'anxiety') return e.counts.anxiety;
      if (expr.counter === 'intrigue') return e.counts.intrigue;
      return c.counters[expr.counter];
    }
    case 'area-intrigue':
      return expr.effective === false
        ? (state.board[expr.area]?.intrigue ?? 0)
        : (effective.areaIntrigue[expr.area] ?? 0);
    case 'selection-count':
      return selectCandidates(expr.selector, state, effective, catalog).length;
    case 'ex':
      return state.ex;
    case 'loop':
      return state.clock.loop;
    case 'day':
      return state.clock.day;
    case 'days-per-loop':
      return state.script.daysPerLoop;
    case 'corpses': {
      let total = Object.values(state.characters).filter(
        (c) =>
          !c.alive &&
          c.presence === 'board' &&
          (!expr.area || c.area === expr.area) &&
          (!expr.identity || effective.characters[c.id]!.identity === expr.identity),
      ).length;
      if (
        state.script.moduleId === 'haunted_stage_again' &&
        (!expr.identity ||
          expr.identity ===
            (state.script.ruleIds.includes('hsa.y.ancient_tomb') ? 'zombie' : 'civilian'))
      )
        total += Object.entries(state.board)
          .filter(([id]) => !expr.area || id === expr.area)
          .reduce((sum, [, area]) => sum + area.intrigue, 0);
      return total;
    }
    case 'limit': {
      const c = state.characters[expr.target];
      if (!c || c.definitionId === 'hermit') return 0;
      return Number(catalog?.characters[c.definitionId]?.anxietyLimit ?? 0);
    }
    case 'token-total':
      return Object.values(state.characters[expr.target]?.counters ?? {}).reduce(
        (a, b) => a + b,
        0,
      );
    case 'token-kinds':
      return Object.values(state.characters[expr.target]?.counters ?? {}).filter((n) => n > 0)
        .length;
    case 'sum':
      return selectCandidates(expr.selector, state, effective, catalog).reduce(
        (sum, id) =>
          sum +
          readValue(
            { kind: 'counter', target: id, counter: expr.counter, effective: expr.effective },
            state,
            effective,
            catalog,
          ),
        0,
      );
    case 'alive-count':
      return Object.values(state.characters).filter((c) => c.alive && c.presence === 'board')
        .length;
    case 'mark-count':
      return Object.values(state.characters).filter((c) => c.marks[expr.mark]).length;
  }
}

export function matches(
  condition: Condition | undefined,
  state: GameState,
  effective: EffectiveState,
  catalog?: ContentCatalog,
): boolean {
  if (!condition || condition.kind === 'always') return true;
  switch (condition.kind) {
    case 'not':
      return !matches(condition.condition, state, effective, catalog);
    case 'all':
      return condition.conditions.every((c) => matches(c, state, effective, catalog));
    case 'any':
      return condition.conditions.some((c) => matches(c, state, effective, catalog));
    case 'compare': {
      const left = readValue(condition.left, state, effective, catalog);
      const right = readValue(condition.right, state, effective, catalog);
      if (condition.op === '>=') return left >= right;
      if (condition.op === '<=') return left <= right;
      if (condition.op === '>') return left > right;
      if (condition.op === '<') return left < right;
      return left === right;
    }
    case 'phase':
      return state.clock.phase === condition.phase;
    case 'final-day':
      return state.clock.day === state.script.daysPerLoop;
    case 'area':
      return condition.areas.includes(state.characters[condition.target]?.area as AreaId);
    case 'revealed':
      return state.records.revealedFacts.some((fact) =>
        fact.startsWith(`identity:${condition.target}:`),
      );
    case 'attachment':
      return state.characters[condition.target]?.attachments.includes(condition.key) ?? false;
    case 'alive':
      return state.characters[condition.characterId]?.alive === condition.value;
    case 'presence':
      return state.characters[condition.characterId]?.presence === condition.presence;
    case 'identity':
      return effective.characters[condition.characterId]?.identity === condition.identityId;
    case 'trait':
      return (
        effective.characters[condition.characterId]?.traits.includes(condition.traitId) ?? false
      );
    case 'flag':
      return (
        Boolean(state.records.revealedFacts.includes(`flag:${condition.key}`)) ===
        (condition.value ?? true)
      );
    case 'incident-occurred':
      return state.records.incidentHistory.some(
        (r) =>
          r.incidentId === condition.incidentId &&
          (!condition.thisLoop || r.loop === state.clock.loop) &&
          (!condition.today || (r.loop === state.clock.loop && r.day === state.clock.day)),
      );
  }
}

function matchesFilter(
  id: string,
  filter: CharacterFilter | undefined,
  state: GameState,
  effective: EffectiveState,
  catalog?: ContentCatalog,
): boolean {
  const victim = virtualCorpse(state, id);
  if (victim) {
    const area =
      typeof filter?.area === 'string'
        ? filter.area
        : filter?.area
          ? state.characters[filter.area.sameAs]?.area
          : undefined;
    return (
      filter?.alive === false &&
      (!filter.presence || filter.presence === 'board') &&
      (!area || area === victim.area) &&
      (!filter.identity || filter.identity === victim.identity) &&
      !filter.attribute &&
      !filter.definitionId &&
      !filter.trait &&
      !filter.not?.includes(id) &&
      !filter.counter
    );
  }
  const c = state.characters[id];
  const e = effective.characters[id];
  if (!c || !e) return false;
  if (c.presence !== (filter?.presence ?? 'board')) return false;
  if (c.alive !== (filter?.alive ?? true)) return false;
  if (!filter) return true;
  if (filter.definitionId && c.definitionId !== filter.definitionId) return false;
  if (filter.alive !== undefined && c.alive !== filter.alive) return false;
  if (filter.presence && c.presence !== filter.presence) return false;
  if (filter.not?.includes(id)) return false;
  if (filter.identity && e.identity !== filter.identity) return false;
  if (filter.trait && !e.traits.includes(filter.trait)) return false;
  if (
    filter.attribute &&
    !catalog?.characters[c.definitionId]?.attributes.includes(filter.attribute)
  )
    return false;
  if (filter.area) {
    const area: AreaId | undefined =
      typeof filter.area === 'string' ? filter.area : state.characters[filter.area.sameAs]?.area;
    if (!area || c.area !== area) return false;
  }
  if (filter.counter) {
    const value = filter.counter.effective
      ? filter.counter.type === 'goodwill'
        ? e.counts.goodwill
        : filter.counter.type === 'anxiety'
          ? e.counts.anxiety
          : filter.counter.type === 'intrigue'
            ? e.counts.intrigue
            : c.counters[filter.counter.type]
      : c.counters[filter.counter.type];
    if (value < filter.counter.atLeast) return false;
  }
  if (
    filter.atAnxietyLimit &&
    e.counts.anxiety < readValue({ kind: 'limit', target: id }, state, effective, catalog)
  )
    return false;
  return true;
}

export function selectCandidates(
  selector: Selector,
  state: GameState,
  effective: EffectiveState,
  catalog?: ContentCatalog,
): string[] {
  switch (selector.kind) {
    case 'union':
      return [
        ...new Set(
          selector.selectors.flatMap((s) => selectCandidates(s, state, effective, catalog)),
        ),
      ];
    case 'none':
      return [];
    case 'character': {
      const c = state.characters[selector.id];
      if (!c) return [];
      if (!selector.allowRemoved && c.presence !== 'board') return [];
      if (!selector.allowDead && !c.alive) return [];
      return [c.id];
    }
    case 'characters':
      return (
        selector.ids ?? [
          ...Object.keys(state.characters),
          ...(selector.filter?.alive === false && state.script.moduleId === 'haunted_stage_again'
            ? Object.entries(state.board).flatMap(([area, value]) =>
                Array.from({ length: value.intrigue }, (_, index) => `victim:${area}:${index}`),
              )
            : []),
        ]
      )
        .filter((id) => matchesFilter(id, selector.filter, state, effective, catalog))
        .sort();
    case 'area':
      return selector.id ? [selector.id] : ['shrine', 'hospital', 'city', 'school'];
    case 'areas':
      return ['shrine', 'hospital', 'city', 'school'];
    case 'protagonists':
      return ['protagonists'];
  }
}

export function requiredTargetCount(selector: Selector, candidates: string[]): number {
  if (selector.kind === 'none') return 0;
  if (selector.kind === 'character') return candidates.length ? 1 : 0;
  if (selector.kind === 'characters' || selector.kind === 'areas' || selector.kind === 'union') {
    if (selector.count === 'all') return candidates.length;
    return selector.count ?? 1;
  }
  return 1;
}
