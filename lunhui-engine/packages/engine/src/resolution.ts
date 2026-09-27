import type {
  BatchResult,
  ContentCatalog,
  DeathAttempt,
  DomainEvent,
  EffectIntent,
  GameState,
  ResolutionSegment,
  TargetResult,
} from './model.js';
import { evaluatePersistent } from './persistent.js';
import {
  matches,
  readValue,
  requiredTargetCount,
  selectCandidates,
  virtualCorpse,
} from './query.js';

export function inspectSegment(
  segment: ResolutionSegment,
  state: GameState,
  catalog: ContentCatalog,
  choices: Record<string, string[]>,
): TargetResult[] {
  const effective = evaluatePersistent(state, catalog, `target:${segment.id}`);
  return segment.effects.map((effect) => {
    if (!matches(effect.condition, state, effective, catalog))
      return { effectId: effect.id, status: 'not_checked', candidates: [], selected: [] };
    if (effect.target.kind === 'none')
      return { effectId: effect.id, status: 'not_required', candidates: [], selected: [] };
    const candidates = selectCandidates(effect.target, state, effective, catalog);
    const required = requiredTargetCount(effect.target, candidates);
    if (required === 0 || candidates.length < required)
      return { effectId: effect.id, status: 'no_target', candidates, selected: [] };
    const fixed = effect.target.kind === 'character' && effect.target.id ? [effect.target.id] : [];
    const all =
      (effect.target.kind === 'characters' ||
        effect.target.kind === 'areas' ||
        effect.target.kind === 'union') &&
      effect.target.count === 'all'
        ? candidates
        : [];
    const oldSelection = choices[effect.id] ?? (fixed.length ? fixed : all);
    const selected = oldSelection.filter((id) => candidates.includes(id));
    return {
      effectId: effect.id,
      status: 'has_target',
      candidates,
      selected: selected.length === required ? selected : [],
    };
  });
}

export function buildIntents(
  sourceInstanceId: string,
  segment: ResolutionSegment,
  targets: TargetResult[],
): EffectIntent[] {
  const byId = new Map(targets.map((t) => [t.effectId, t]));
  const intents: EffectIntent[] = [];
  for (const effect of segment.effects) {
    const target = byId.get(effect.id)!;
    if (target.status === 'not_checked' || target.status === 'no_target') continue;
    if (target.status === 'not_required') {
      intents.push({
        id: `${sourceInstanceId}:${effect.id}:0`,
        sourceInstanceId,
        effectId: effect.id,
        operation: effect.operation,
      });
      continue;
    }
    target.selected.forEach((targetId, index) =>
      intents.push({
        id: `${sourceInstanceId}:${effect.id}:${index}`,
        sourceInstanceId,
        effectId: effect.id,
        targetId,
        operation: effect.operation,
      }),
    );
  }
  const expand = (intent: EffectIntent): EffectIntent[] =>
    intent.operation.kind === 'bundle'
      ? intent.operation.operations.flatMap((operation, index) =>
          expand({ ...intent, id: `${intent.id}:${index}`, operation }),
        )
      : [intent];
  return intents.flatMap(expand);
}

function servantFor(state: GameState, catalog: ContentCatalog, targetId: string): string | null {
  const target = state.characters[targetId];
  if (!target) return null;
  const effective = evaluatePersistent(state, catalog, 'death:replacement');
  const candidates = Object.values(state.characters)
    .filter(
      (c) =>
        c.id !== targetId &&
        c.alive &&
        c.presence === 'board' &&
        c.area === target.area &&
        c.definitionId === 'servant' &&
        (['big_shot', 'rich_girl'].includes(target.definitionId) ||
          c.attachments.includes(`serves:${targetId}`) ||
          target.attachments.includes(`served-by:${c.id}`)),
    )
    .map((c) => c.id)
    .sort();
  if (candidates.length > 1) throw new Error('AMBIGUOUS_SERVANT_REPLACEMENT');
  return candidates[0] ?? null;
}

function processDeaths(
  state: GameState,
  catalog: ContentCatalog,
  intents: EffectIntent[],
): { attempts: DeathAttempt[]; deaths: string[]; guardSpend: Record<string, number> } {
  const effective = evaluatePersistent(state, catalog, 'death:batch');
  const guards = Object.fromEntries(
    Object.values(state.characters).map((c) => [c.id, c.counters.guard]),
  );
  const guardSpend: Record<string, number> = {};
  const attempts: DeathAttempt[] = [];
  const deaths = new Set<string>();
  for (const intent of intents.filter((i) => i.operation.kind === 'death')) {
    const original = intent.targetId!;
    if (!state.characters[original]?.alive) continue;
    let finalTarget = original;
    let replaced = false;
    const blocker = (id: string): DeathAttempt['blockedBy'] => {
      if (effective.characters[id]?.traits.includes('immortal')) return 'immortal';
      if ((guards[id] ?? 0) > 0) {
        guards[id]!--;
        guardSpend[id] = (guardSpend[id] ?? 0) + 1;
        return 'guard';
      }
      return null;
    };
    let blockedBy = blocker(finalTarget);
    if (!blockedBy) {
      const servant = servantFor(state, catalog, original);
      if (servant) {
        finalTarget = servant;
        replaced = true;
        blockedBy = blocker(finalTarget);
      }
    }
    attempts.push({ id: intent.id, originalTarget: original, finalTarget, blockedBy, replaced });
    if (!blockedBy) deaths.add(finalTarget);
  }
  return { attempts, deaths: [...deaths].sort(), guardSpend };
}

export function adjacent(from: string, to: string): boolean {
  const coordinates: Record<string, [number, number]> = {
    hospital: [0, 0],
    shrine: [1, 0],
    city: [0, 1],
    school: [1, 1],
  };
  const a = coordinates[from];
  const b = coordinates[to];
  return Boolean(a && b && Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) === 1);
}

export function textMoveDestinations(
  state: GameState,
  id: string,
  onlyAdjacent = false,
  faraway = false,
): import('./model.js').AreaId[] {
  const from = state.characters[id]?.area ?? virtualCorpse(state, id)?.area;
  if (!from) return [];
  return (
    [
      'hospital',
      'shrine',
      'city',
      'school',
      ...(faraway ? ['faraway'] : []),
    ] as import('./model.js').AreaId[]
  ).filter((area) => !onlyAdjacent || adjacent(from, area));
}

export function legalMoveDestinations(
  state: GameState,
  catalog: ContentCatalog,
  id: string,
  onlyAdjacent = false,
  faraway = false,
): import('./model.js').AreaId[] {
  const victim = virtualCorpse(state, id);
  if (victim)
    return (['hospital', 'shrine', 'city', 'school'] as const).filter(
      (area) => !onlyAdjacent || adjacent(victim.area, area),
    );
  const character = state.characters[id];
  if (!character) return [];
  const effective = evaluatePersistent(state, catalog).characters[id]!;
  if (character.attachments.includes(`movement-lock:${state.clock.day}`)) return [character.area];
  const blocked = new Set(
    state.records.revealedFacts.flatMap((fact) => {
      const match = /^flag:blockade:(hospital|shrine|city|school):(\d+)$/.exec(fact);
      return match && state.clock.day <= Number(match[2]) ? [match[1]] : [];
    }),
  );
  return textMoveDestinations(state, id, onlyAdjacent, faraway).filter(
    (area) =>
      (area === character.area || (!blocked.has(character.area) && !blocked.has(area))) &&
      (effective.ignoredForbiddenAreas ||
        !catalog.characters[character.definitionId]!.forbiddenAreas.includes(area)),
  );
}

export function movementFollowers(
  before: GameState,
  catalog: ContentCatalog,
  intents: EffectIntent[],
): Record<string, string[]> {
  const moving = intents.filter((intent) => {
    const card = before.characters[intent.targetId ?? ''];
    const op = intent.operation;
    return (
      card?.alive &&
      card.presence === 'board' &&
      op.kind === 'move-character' &&
      op.destination &&
      op.destination !== card.area &&
      legalMoveDestinations(before, catalog, card.id, op.adjacent, true).includes(op.destination)
    );
  });
  return Object.fromEntries(
    Object.values(before.characters)
      .filter((c) => c.definitionId === 'servant' && c.alive && c.presence === 'board')
      .flatMap((servant) => {
        const candidates = [
          ...new Set(
            moving
              .filter((intent) => {
                const card = before.characters[intent.targetId!]!;
                return (
                  card.id !== servant.id &&
                  card.area === servant.area &&
                  (['big_shot', 'rich_girl'].includes(card.definitionId) ||
                    servant.attachments.includes(`serves:${card.id}`) ||
                    card.attachments.includes(`served-by:${servant.id}`))
                );
              })
              .map((intent) => intent.targetId!),
          ),
        ];
        return candidates.length ? [[servant.id, candidates]] : [];
      }),
  );
}

export function commitBatch(
  before: GameState,
  catalog: ContentCatalog,
  intents: EffectIntent[],
  followerChoices: Record<string, string> = {},
): { state: GameState; result: BatchResult } {
  const originalIntents = intents;
  for (const [servant, candidates] of Object.entries(
    movementFollowers(before, catalog, originalIntents),
  )) {
    const chosen =
      followerChoices[servant] ?? (candidates.length === 1 ? candidates[0]! : undefined);
    if (!chosen || !candidates.includes(chosen))
      throw new Error(`SERVANT_FOLLOW_CHOICE_REQUIRED:${servant}`);
    const leaderMove = originalIntents.find(
      (intent) => intent.targetId === chosen && intent.operation.kind === 'move-character',
    )!;
    if (leaderMove.operation.kind !== 'move-character') throw new Error('INVALID_FOLLOW_MOVEMENT');
    intents = intents.filter(
      (intent) => intent.targetId !== servant || intent.operation.kind !== 'move-character',
    );
    intents.push({
      ...leaderMove,
      id: `follow:${servant}:${leaderMove.id}`,
      targetId: servant,
      operation: { kind: 'move-character', destination: leaderMove.operation.destination },
    });
  }
  for (const id of new Set(
    intents.flatMap((intent) =>
      intent.operation.kind === 'move-character' && intent.targetId ? [intent.targetId] : [],
    ),
  )) {
    const destinations = new Set(
      intents
        .filter((intent) => intent.targetId === id && intent.operation.kind === 'move-character')
        .map((intent) =>
          intent.operation.kind === 'move-character' ? intent.operation.destination : undefined,
        ),
    );
    if (destinations.size > 1) throw new Error(`CONFLICTING_MOVEMENTS:${id}`);
  }
  const state = structuredClone(before);
  const events: DomainEvent[] = [];
  const counterDeltas = new Map<string, number[]>();
  const delta = (id: string, counter: string, amount: number) => {
    const key = `${id}|${counter}`;
    counterDeltas.set(key, [...(counterDeltas.get(key) ?? []), amount]);
  };
  const death = processDeaths(before, catalog, intents);
  const consumedVictims = new Set<string>();
  let protagonistsDie = false;
  let exDelta = 0;
  const transfers = new Map<string, number>();
  for (const intent of intents) {
    const operation = intent.operation;
    const targetId = intent.targetId;
    switch (operation.kind) {
      case 'noop':
        break;
      case 'bundle':
        throw new Error('UNEXPANDED_BUNDLE');
      case 'announce':
        if (operation.fact && !state.records.revealedFacts.includes(operation.fact))
          state.records.revealedFacts.push(operation.fact);
        state.publicLog.push({
          sequence: state.publicLog.length,
          type: 'information',
          text: operation.text,
        });
        break;
      case 'return-card': {
        const card = state.cards[operation.seat].find(
          (c) => c.id === operation.cardId && c.oncePerLoop && c.zone === 'used',
        );
        if (!card) throw new Error('CARD_NOT_RETURNABLE');
        card.zone = 'hand';
        break;
      }
      case 'attachment': {
        if (!targetId || !state.characters[targetId]) throw new Error('ATTACHMENT_TARGET_REQUIRED');
        const c = state.characters[targetId];
        c.attachments = c.attachments.filter((key) => key !== operation.key);
        if (!operation.remove) c.attachments.push(operation.key);
        break;
      }
      case 'attachment-transfer': {
        const donor = state.characters[operation.from];
        const recipient = targetId ? state.characters[targetId] : undefined;
        if (donor && recipient && donor.attachments.includes(operation.key)) {
          donor.attachments = donor.attachments.filter((key) => key !== operation.key);
          if (!recipient.attachments.includes(operation.key))
            recipient.attachments.push(operation.key);
        }
        break;
      }
      case 'curse': {
        if (operation.action === 'create') {
          if (!targetId) throw new Error('CURSE_TARGET_REQUIRED');
          state.curses.push({
            id: `curse:${before.revision}:${intent.id}`,
            kind: targetId in state.characters ? 'character' : 'area',
            targetId,
          });
        } else {
          const curse = state.curses.find((entry) => entry.id === operation.curseId);
          if (!curse) throw new Error('UNKNOWN_CURSE');
          if (operation.action === 'attach') {
            curse.kind = 'character';
            curse.targetId = targetId!;
          } else {
            curse.kind = 'area';
            curse.targetId = state.characters[curse.targetId]!.area;
          }
        }
        break;
      }
      case 'counter': {
        if (!targetId) throw new Error('TARGET_REQUIRED');
        const key = `${targetId}|${operation.counter}`;
        const values = counterDeltas.get(key) ?? [];
        const amount = readValue(
          operation.amount,
          before,
          evaluatePersistent(before, catalog),
          catalog,
        );
        values.push(operation.direction === 'remove' ? -Math.abs(amount) : amount);
        counterDeltas.set(key, values);
        break;
      }
      case 'clear-counters': {
        if (!targetId || !before.characters[targetId]) throw new Error('TARGET_REQUIRED');
        const counters = before.characters[targetId]!.counters;
        for (const type of operation.counters ??
          (Object.keys(counters) as Array<keyof typeof counters>))
          delta(targetId, type, -counters[type]);
        break;
      }
      case 'move-counter': {
        if (!targetId || !operation.counter || operation.to.kind !== 'character')
          throw new Error('TRANSFER_SELECTION_REQUIRED');
        const destination = operation.to.id;
        const donor = before.characters[targetId];
        if (!donor || !before.characters[destination]) throw new Error('INVALID_TRANSFER');
        let available = donor.counters[operation.counter];
        if (operation.sacredTree)
          available -= intents
            .filter(
              (other) =>
                other.targetId === targetId &&
                other.operation.kind === 'counter' &&
                other.operation.counter === operation.counter,
            )
            .reduce((sum, other) => {
              if (other.operation.kind !== 'counter') return sum;
              const amount = readValue(
                other.operation.amount,
                before,
                evaluatePersistent(before, catalog),
                catalog,
              );
              return sum + Math.max(0, other.operation.direction === 'remove' ? amount : -amount);
            }, 0);
        const amount = Math.min(operation.amount, Math.max(0, available));
        const resource = `${targetId}:${operation.counter}`;
        transfers.set(resource, (transfers.get(resource) ?? 0) + amount);
        if (transfers.get(resource)! > donor.counters[operation.counter])
          throw new Error(`CONFLICTING_TOKEN_TRANSFERS:${resource}`);
        delta(targetId, operation.counter, -amount);
        delta(destination, operation.counter, amount);
        break;
      }
      case 'replace-counter': {
        if (!targetId || !state.characters[targetId]) throw new Error('TARGET_REQUIRED');
        const c = before.characters[targetId]!;
        const moved = Math.min(operation.amount, c.counters[operation.from]);
        if (moved) {
          delta(targetId, operation.from, -moved);
          delta(targetId, operation.to, moved);
        }
        break;
      }
      case 'move-character': {
        const victim = targetId ? virtualCorpse(before, targetId) : null;
        if (victim && targetId) {
          const destination = operation.destination;
          if (
            destination &&
            destination !== 'faraway' &&
            destination !== victim.area &&
            legalMoveDestinations(before, catalog, targetId, operation.adjacent).includes(
              destination,
            ) &&
            !consumedVictims.has(targetId)
          ) {
            consumedVictims.add(targetId);
            delta(victim.area, 'intrigue', -1);
            delta(destination, 'intrigue', 1);
          }
          break;
        }
        if (!targetId || !state.characters[targetId]) throw new Error('TARGET_REQUIRED');
        const c = state.characters[targetId];
        const destination = operation.destination;
        if (!destination) throw new Error('DESTINATION_REQUIRED');
        const definition = catalog.characters[c.definitionId];
        const effective = evaluatePersistent(before, catalog, 'movement');
        const forbidden = !legalMoveDestinations(before, catalog, targetId, false, true).includes(
          destination,
        );
        const legalDistance = !operation.adjacent || adjacent(c.area, destination);
        if (c.area !== destination && !forbidden && legalDistance) {
          const from = c.area;
          c.area = destination;
          events.push({ type: 'character-moved', targetId, from, to: destination });
          if (operation.lockNextDay && before.clock.day < before.script.daysPerLoop)
            c.attachments.push(`movement-lock:${before.clock.day + 1}`);
        }
        break;
      }
      case 'death':
        break;
      case 'protagonists-die':
        protagonistsDie = true;
        break;
      case 'fail-loop':
        state.records.loopFailed = true;
        if (!state.records.endRequests.includes(operation.reason))
          state.records.endRequests.push(operation.reason);
        events.push({ type: 'loop-failed', reason: operation.reason });
        events.push({ type: 'loop-end-requested', reason: operation.reason });
        break;
      case 'end-loop':
        if (!state.records.endRequests.includes(operation.reason))
          state.records.endRequests.push(operation.reason);
        events.push({ type: 'loop-end-requested', reason: operation.reason });
        break;
      case 'resurrect': {
        const victim = targetId ? virtualCorpse(before, targetId) : null;
        if (victim && targetId) {
          if (!consumedVictims.has(targetId)) {
            consumedVictims.add(targetId);
            delta(victim.area, 'intrigue', -1);
          }
          break;
        }
        if (!targetId || !state.characters[targetId]) throw new Error('TARGET_REQUIRED');
        const c = state.characters[targetId];
        if (!c.alive && c.presence === 'board') {
          c.alive = true;
          events.push({ type: 'character-resurrected', targetId });
        }
        break;
      }
      case 'remove-character':
        if (
          targetId &&
          state.characters[targetId] &&
          state.characters[targetId].presence !== 'removed'
        ) {
          state.characters[targetId].presence = 'removed';
          events.push({ type: 'character-removed', targetId });
        }
        break;
      case 'reveal-identity': {
        const victim = targetId ? virtualCorpse(before, targetId) : null;
        if (victim) {
          state.publicLog.push({
            sequence: state.publicLog.length,
            type: 'information',
            text: `${victim.area}牺牲者的身份：${catalog.identities[victim.identity]!.name}`,
          });
          break;
        }
        if (!targetId || !state.characters[targetId]) throw new Error('TARGET_REQUIRED');
        const c = state.characters[targetId];
        const actualIdentity = evaluatePersistent(before, catalog, 'reveal').characters[targetId]!
          .identity;
        const identityId =
          actualIdentity === 'ninja' && before.characters[targetId]!.alive
            ? (operation.declaredIdentity ?? actualIdentity)
            : actualIdentity;
        c.publicIdentity = identityId;
        const fact = `identity:${targetId}:${identityId}`;
        if (!state.records.revealedFacts.includes(fact)) state.records.revealedFacts.push(fact);
        const loopFact = `identity-loop:${state.clock.loop}:${targetId}:${identityId}`;
        if (!state.records.revealedFacts.includes(loopFact))
          state.records.revealedFacts.push(loopFact);
        events.push({ type: 'identity-revealed', targetId, identityId });
        break;
      }
      case 'set-temporary-identity':
        if (targetId && state.characters[targetId])
          state.characters[targetId].temporaryIdentity = operation.identityId;
        break;
      case 'ex': {
        exDelta += operation.amount;
        break;
      }
      case 'set-protagonist-protection':
        state.protagonistProtection = operation.value;
        break;
      case 'set-record': {
        const fact = `flag:${operation.key}`;
        state.records.revealedFacts = state.records.revealedFacts.filter((v) => v !== fact);
        if (operation.value) state.records.revealedFacts.push(fact);
        events.push({ type: 'record-changed', key: operation.key, value: operation.value });
        break;
      }
      case 'grant-card': {
        const deck = state.cards[operation.seat];
        const key = `loop:${state.clock.loop}:grant:${operation.seat}:${operation.cardKind}`;
        if (operation.cardKind === 'hope+1' && state.records.usage[key]) break;
        if (!deck.some((c) => c.kind === operation.cardKind && c.zone !== 'excluded')) {
          deck.push({
            id: `${operation.seat}:${operation.cardKind}:${deck.length + 1}`,
            kind: operation.cardKind,
            owner: operation.seat,
            oncePerLoop: true,
            zone: 'hand',
          });
          events.push({ type: 'card-granted', seat: operation.seat, cardKind: operation.cardKind });
        }
        state.records.usage[key] = 1;
        break;
      }
      case 'schedule':
        state.records.delayed.push({
          ...operation.task,
          id: `task:${state.revision}:${state.records.delayed.length}`,
        });
        break;
      case 'world-move':
        state.records.worldMovedToday = true;
        events.push({ type: 'world-moved' });
        break;
    }
  }
  if (exDelta) {
    state.ex = Math.max(0, before.ex + exDelta);
    if (state.ex > before.ex) state.records.exIncreasedThisLoop = true;
    if (state.ex !== before.ex)
      events.push({ type: 'ex-changed', before: before.ex, after: state.ex });
  }
  for (const [key, values] of counterDeltas) {
    const [targetId, counter] = key.split('|') as [
      string,
      keyof (typeof state.characters)[string]['counters'],
    ];
    if (values.some((v) => v > 0) && values.some((v) => v < 0))
      throw new Error(`UNRESOLVED_COUNTER_CONFLICT:${key}`);
    const character = state.characters[targetId];
    if (character) {
      const old = character.counters[counter];
      const cap = counter === 'guard' ? 1 : Number.POSITIVE_INFINITY;
      character.counters[counter] = Math.min(
        cap,
        Math.max(0, old + values.reduce((a, b) => a + b, 0)),
      );
      if (old !== character.counters[counter])
        events.push({
          type: 'counter-changed',
          targetId,
          counter,
          before: old,
          after: character.counters[counter],
        });
    } else if (counter === 'intrigue' && targetId in state.board) {
      const area = state.board[targetId as keyof typeof state.board];
      const old = area.intrigue;
      area.intrigue = Math.min(3, Math.max(0, old + values.reduce((a, b) => a + b, 0)));
      if (old !== area.intrigue)
        events.push({
          type: 'counter-changed',
          targetId,
          counter,
          before: old,
          after: area.intrigue,
        });
    }
  }
  for (const [id, spent] of Object.entries(death.guardSpend)) {
    const old = state.characters[id]!.counters.guard;
    state.characters[id]!.counters.guard = Math.max(0, old - spent);
    if (old !== state.characters[id]!.counters.guard)
      events.push({
        type: 'counter-changed',
        targetId: id,
        counter: 'guard',
        before: old,
        after: state.characters[id]!.counters.guard,
      });
  }
  for (const id of death.deaths) {
    const c = state.characters[id]!;
    if (!c.alive) continue;
    c.alive = false;
    if (state.script.moduleId === 'last_liar') c.marks.died = true;
    events.push({ type: 'character-died', targetId: id, fromArea: c.area });
  }
  if (protagonistsDie && !before.protagonistProtection) {
    state.records.protagonistsDead = true;
    if (!state.records.endRequests.includes('protagonists-died'))
      state.records.endRequests.push('protagonists-died');
    events.push({ type: 'protagonists-died' });
    events.push({ type: 'loop-end-requested', reason: 'protagonists-died' });
  }
  state.revision++;
  if (Object.values(state.characters).reduce((sum, c) => sum + c.counters.guard, 0) > 1)
    throw new Error('GLOBAL_GUARD_LIMIT');
  const changed = (a: unknown, b: unknown) => JSON.stringify(a) !== JSON.stringify(b);
  const didChange = (intent: EffectIntent): boolean => {
    const operation = intent.operation;
    const id = intent.targetId ?? '';
    const oldCard = before.characters[id];
    const newCard = state.characters[id];
    switch (operation.kind) {
      case 'noop':
        return false;
      case 'bundle':
        throw new Error('UNEXPANDED_BUNDLE');
      case 'counter':
        return (
          readValue(operation.amount, before, evaluatePersistent(before, catalog), catalog) !== 0 &&
          changed(
            oldCard?.counters[operation.counter] ??
              before.board[id as keyof typeof before.board]?.intrigue,
            newCard?.counters[operation.counter] ??
              state.board[id as keyof typeof state.board]?.intrigue,
          )
        );
      case 'clear-counters':
        return changed(oldCard?.counters, newCard?.counters);
      case 'replace-counter':
        return operation.amount > 0 && changed(oldCard?.counters, newCard?.counters);
      case 'move-counter':
        return operation.amount > 0 && changed(oldCard?.counters, newCard?.counters);
      case 'move-character':
        return changed(oldCard?.area, newCard?.area) || consumedVictims.has(id);
      case 'death': {
        const attempt = death.attempts.find((attempt) => attempt.id === intent.id);
        return Boolean(
          attempt &&
            (attempt.blockedBy === 'guard' ||
              (!attempt.blockedBy && death.deaths.includes(attempt.finalTarget))),
        );
      }
      case 'protagonists-die':
        return before.records.protagonistsDead !== state.records.protagonistsDead;
      case 'fail-loop':
        return before.records.loopFailed !== state.records.loopFailed;
      case 'end-loop':
        return false;
      case 'resurrect':
        return oldCard?.alive !== newCard?.alive || consumedVictims.has(id);
      case 'remove-character':
        return oldCard?.presence !== newCard?.presence;
      case 'reveal-identity':
        return (
          oldCard?.publicIdentity !== newCard?.publicIdentity || Boolean(virtualCorpse(before, id))
        );
      case 'set-temporary-identity':
        return oldCard?.temporaryIdentity !== newCard?.temporaryIdentity;
      case 'ex':
        return operation.amount !== 0 && before.ex !== state.ex;
      case 'set-protagonist-protection':
        return before.protagonistProtection !== state.protagonistProtection;
      case 'attachment':
        return changed(oldCard?.attachments, newCard?.attachments);
      case 'attachment-transfer':
        return changed(
          before.characters[operation.from]?.attachments,
          state.characters[operation.from]?.attachments,
        );
      case 'curse':
        return changed(before.curses, state.curses);
      case 'grant-card':
        return changed(before.cards[operation.seat], state.cards[operation.seat]);
      case 'return-card':
        return changed(before.cards[operation.seat], state.cards[operation.seat]);
      case 'world-move':
        return !before.records.worldMovedToday && state.records.worldMovedToday;
      case 'set-record':
      case 'schedule':
        return false;
      case 'announce':
        return Boolean(operation.fact && !before.records.revealedFacts.includes(operation.fact));
    }
  };
  const changedSourceIds = [
    ...new Set(intents.filter(didChange).map((intent) => intent.sourceInstanceId)),
  ];
  return {
    state,
    result: {
      changed: changedSourceIds.length > 0,
      changedSourceIds,
      deaths: death.deaths,
      deathAttempts: death.attempts,
      events,
    },
  };
}
