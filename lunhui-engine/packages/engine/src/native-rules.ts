import type {
  ContentCatalog,
  EffectSpec,
  GameState,
  Operation,
  ResolutionProgram,
  RuleSourceDefinition,
  Selector,
  Timing,
} from './model.js';
import { evaluatePersistent } from './persistent.js';
import { readValue } from './query.js';
const none: Selector = { kind: 'none' };
const e = (id: string, target: Selector, operation: Operation): EffectSpec => ({
  id,
  target,
  operation,
});
const p = (...parts: EffectSpec[][]): ResolutionProgram => ({
  segments: parts.map((effects, i) => ({ id: String(i), effects })),
});

export function nativeForced(
  timing: Timing,
  state: GameState,
  catalog: ContentCatalog,
  context: Record<string, string | string[]>,
): RuleSourceDefinition[] {
  const result: RuleSourceDefinition[] = [];
  const effective = evaluatePersistent(state, catalog);
  const cards = Object.values(state.characters);
  const alive = cards.filter((c) => c.alive && c.presence === 'board');
  const onBoard = cards.filter((c) => c.presence === 'board');
  const identities = (id: string, dead = false) =>
    (dead ? onBoard : alive).filter((c) => effective.characters[c.id]!.identity === id);
  const add = (
    id: string,
    name: string,
    program: ResolutionProgram,
    extra: Partial<RuleSourceDefinition> = {},
  ) => {
    result.push({
      id: `native.${id}`,
      name,
      reference: `附录/${name}`,
      kind: 'forced',
      timings: [],
      program,
      ...extra,
    });
  };
  const token = (
    id: string,
    type: 'anxiety' | 'goodwill' | 'intrigue',
    amount: number,
    dead = false,
  ) =>
    e(
      `token:${id}`,
      { kind: 'character', id, allowDead: dead, allowRemoved: dead },
      { kind: 'counter', counter: type, amount },
    );
  const grant = (type: 'hope+1' | 'despair+1') =>
    type === 'despair+1'
      ? [e('despair', none, { kind: 'grant-card', seat: 'mastermind', cardKind: type })]
      : (['protagonistA', 'protagonistB', 'protagonistC'] as const).map((seat) =>
          e(seat, none, { kind: 'grant-card', seat, cardKind: type }),
        );
  const enabled = (name: string) =>
    state.script.ruleIds.some((id) => catalog.rules?.[id]?.name === name);
  const subjects = Array.isArray(context.characterIds) ? context.characterIds : [];
  const previousIds = Array.isArray(context.previousIdentities) ? context.previousIdentities : [];
  if (timing === 'phase:mastermind_ability:enter')
    for (const c of alive.filter(
      (c) =>
        c.definitionId === 'sacred_tree' &&
        effective.characters[c.id]!.traits.some((t) => t.includes('ignore-goodwill')),
    )) {
      add(
        `tree:mastermind:${c.id}`,
        '御神木特性',
        p([
          e(
            'token',
            { kind: 'character', id: c.id },
            {
              kind: 'move-counter',
              amount: 1,
              to: { kind: 'characters', filter: { area: c.area, not: [c.id] } },
              sacredTree: true,
            },
          ),
        ]),
        { usage: { scope: 'day', count: 1, consume: 'on_complete' } },
      );
    }

  if (timing === 'phase:loop_start:enter') {
    if (enabled('疯狂的真相') && state.ex >= 2) {
      const replacement = state.script.options.crazyTruthRuleY;
      if (
        typeof replacement !== 'string' ||
        !catalog.modules[state.script.moduleId]!.rules.includes(replacement) ||
        catalog.rules?.[replacement]?.kind !== 'y'
      )
        throw new Error('CRAZY_TRUTH_RULE_Y_REQUIRED');
      add(
        'crazy-truth',
        '疯狂的真相',
        p([
          e('replace', none, {
            kind: 'set-record',
            key: `failure-rule:${replacement}`,
            value: true,
          }),
        ]),
      );
    }
    for (const c of alive) {
      if (c.definitionId === 'black_cat')
        add(
          `black-cat:${c.id}`,
          '黑猫',
          p([
            e(
              'shrine',
              { kind: 'area', id: 'shrine' },
              { kind: 'counter', counter: 'intrigue', amount: 1 },
            ),
          ]),
        );
      if (c.definitionId === 'scholar')
        add(`scholar:${c.id}`, '学者', {
          segments: [
            {
              id: 'token',
              choices: [
                {
                  key: 'type',
                  prompt: '选择学者的指示物',
                  values: ['goodwill', 'anxiety', 'intrigue'],
                },
              ],
              effects: [
                e(
                  'grant',
                  { kind: 'character', id: c.id },
                  { kind: 'counter', counter: '$choice:type' as never, amount: 1 },
                ),
              ],
            },
          ],
        });
      if (
        effective.characters[c.id]!.identity === 'friend' &&
        state.records.revealedFacts.some((fact) => fact === `identity:${c.id}:friend`)
      )
        add(`friend-start:${c.id}`, '亲友', p([token(c.id, 'goodwill', 1)]));
    }
    const previous = state.records.previousLoop;
    if (previous) {
      if (enabled('因果线'))
        add(
          'causal-line',
          '因果线',
          p(
            Object.values(previous.characters)
              .filter((c) => c.counters.goodwill + c.counters.hope > 0)
              .map((c) => token(c.id, 'anxiety', 2, true)),
          ),
        );
      if (enabled('隔离病房惊魂记') && previous.ex <= 2)
        add('isolation', '隔离病房惊魂记', p([e('ex', none, { kind: 'ex', amount: 1 })]));
      for (const c of identities('causal_fragment')) {
        const old = previous.characters[c.id];
        if (!old) continue;
        if (!old.alive) add(`fragment:${c.id}`, '因果残片', p(grant('despair+1')));
        else if (old.counters.goodwill + old.counters.hope >= 2)
          add(`fragment:${c.id}`, '因果残片', p(grant('hope+1')));
      }
      if (identities('narrator').length && previous.ex >= 3)
        add('narrator', '叙述者', p(grant('hope+1')));
      if (enabled('因果之绊') || enabled('诸神之骰')) {
        const ids = Object.values(previous.characters)
          .filter((c) => !c.alive)
          .map((c) => c.id);
        add('ex-fate', '因果之绊／诸神之骰', {
          segments: [
            {
              id: 'ex',
              choices: [
                {
                  key: 'rule',
                  prompt: '选择放置EX牌的规则',
                  values: [
                    enabled('因果之绊') ? 'bond-ex' : '',
                    enabled('诸神之骰') ? 'dice-ex' : '',
                  ].filter(Boolean),
                },
              ],
              effects: [
                e(
                  'recipient',
                  { kind: 'characters', ids },
                  { kind: 'attachment', key: '$choice:rule' },
                ),
              ],
            },
          ],
        });
      }
    }
    if (enabled('超越世界线')) {
      if (state.clock.loop % 2 === 0)
        add('cross-world-despair', '超越世界线', p(grant('despair+1')));
      if (state.clock.loop === state.script.loops)
        add('cross-world-hope', '超越世界线', p(grant('hope+1')));
    }
    if (state.script.moduleId === 'another_horizon_revised') {
      add(
        'ahr-cards',
        'AHR轮回授牌',
        p([
          ...(['protagonistA', 'protagonistB', 'protagonistC'] as const).map((seat) =>
            e(seat, none, { kind: 'grant-card', seat, cardKind: 'anxiety+2' }),
          ),
          e('mastermind-goodwill', none, {
            kind: 'grant-card',
            seat: 'mastermind',
            cardKind: 'goodwill+1',
          }),
          ...(state.clock.loop === 1 ? grant('despair+1') : []),
        ]),
      );
    }
  }
  if (timing === 'character:died') {
    for (const [deadIdentity, livingIdentity] of [
      ['beloved', 'lover'],
      ['lover', 'beloved'],
    ]) {
      const deaths = previousIds.filter((v) => v.endsWith(`=${deadIdentity}`)).length;
      if (deaths)
        for (const c of identities(livingIdentity!))
          add(`grief:${c.id}`, '恋爱风景线', p([token(c.id, 'anxiety', 6 * deaths)]));
    }
  }
  if (['character:died', 'ability:completed'].includes(timing))
    for (const id of subjects) {
      const card = state.characters[id];
      if (!card) continue;
      if (timing === 'ability:completed' && (!card.alive || card.presence !== 'board')) continue;
      const identity =
        previousIds.find((v) => v.startsWith(`${id}=`))?.split('=')[1] ??
        effective.characters[id]!.identity;
      if (identity === 'influencer') {
        const recipients = alive.filter((c) => c.id !== id && c.initialArea === card.initialArea);
        add(
          `influencer:${timing}:${id}`,
          '网络名流',
          p(
            recipients.flatMap((c) => [
              token(c.id, 'anxiety', 1),
              ...(timing === 'ability:completed' ? [token(c.id, 'goodwill', 1)] : []),
            ]),
          ),
          timing === 'ability:completed'
            ? { usage: { scope: 'loop', count: 1, consume: 'on_complete' } }
            : {},
        );
      }
      if (identity === 'nursery_rhyme' && timing === 'ability:completed') {
        const targets = Array.isArray(context.targetIds) ? context.targetIds : [];
        add(
          `nursery-rhyme:${id}`,
          '童谣',
          p(
            targets
              .filter(
                (id) => state.characters[id]?.alive && state.characters[id]?.presence === 'board',
              )
              .map((id) => e(id, { kind: 'character', id }, { kind: 'death' })),
          ),
        );
      }
    }
  if (timing === 'identity:revealed' && state.clock.loop <= 2)
    for (const id of subjects) {
      if (effective.characters[id]?.identity !== 'key') continue;
      const day = Math.min(state.clock.day + 1, state.script.daysPerLoop);
      add(
        `key:${id}`,
        '密钥',
        p([
          ...(state.clock.day < state.script.daysPerLoop
            ? [
                e('limit', none, {
                  kind: 'set-record',
                  key: `key-limit:${state.clock.day + 1}`,
                  value: true,
                }),
              ]
            : []),
          e('death-due', none, {
            kind: 'schedule',
            task: {
              sourceId: 'key',
              due: 'phase:turn_end:enter',
              loop: state.clock.loop,
              day,
              expiresAtLoopEnd: true,
              payload: p([e('heroes', none, { kind: 'protagonists-die' })]),
            },
          }),
        ]),
      );
    }
  if (timing === 'ability:completed' && state.script.moduleId === 'another_horizon_revised') {
    const source =
      typeof context.sourceId === 'string' ? catalog.sources[context.sourceId] : undefined;
    if (source?.usage?.scope === 'loop')
      add('goodwill-world', '限次友好后的世界移动', p([e('world', none, { kind: 'world-move' })]));
  }
  if (timing === 'phase:incident:exit') {
    const starts = state.records.revealedFacts
      .filter((fact) => fact.startsWith('flag:tindalos:'))
      .map((fact) => Number(fact.split(':')[2]));
    if (
      starts.some((start) =>
        state.records.incidentHistory.some(
          (record) =>
            record.sequence > start &&
            record.loop === state.clock.loop &&
            record.day === state.clock.day,
        ),
      )
    )
      add('tindalos', '廷达罗斯之嗅', p([e('heroes', none, { kind: 'protagonists-die' })]));
  }
  if (timing === 'phase:turn_end:enter') {
    if (state.script.moduleId === 'weird_mythology' && state.ex >= 4)
      add('madness', '发狂', p([e('heroes', none, { kind: 'protagonists-die' })]));
    for (const c of alive.filter(
      (c) =>
        c.definitionId === 'temp_worker' &&
        Object.values(c.counters).reduce((a, b) => a + b, 0) >= 3,
    ))
      add(
        `temp-worker:${c.id}`,
        '临时工',
        p([e('death', { kind: 'character', id: c.id }, { kind: 'death' })]),
      );
    for (const c of identities('witness').filter(
      (c) => effective.characters[c.id]!.counts.anxiety >= 4,
    ))
      add(
        `witness:${c.id}`,
        '目击者',
        p([
          e('death', { kind: 'character', id: c.id }, { kind: 'death' }),
          e('ex', none, { kind: 'ex', amount: 1 }),
        ]),
      );
    for (const c of alive.filter(
      (c) => c.definitionId === 'uploader' && state.records.firstIncidentDay === state.clock.day,
    ))
      add(
        `uploader:${c.id}`,
        'UP主',
        p([
          e(
            'ex',
            {
              kind: 'union',
              selectors: [
                { kind: 'characters', filter: { attribute: '少年' } },
                { kind: 'characters', filter: { attribute: '少女' } },
              ],
            },
            { kind: 'attachment', key: 'uploader-ex' },
          ),
        ]),
      );
    if (
      identities('zombie', true).length ||
      (enabled('古墓活尸') && Object.values(state.board).some((a) => a.intrigue > 0))
    ) {
      const areas = Object.keys(state.board).filter((area) => {
        const zombies =
          onBoard.filter(
            (c) => c.area === area && effective.characters[c.id]!.identity === 'zombie',
          ).length +
          (enabled('古墓活尸') ? state.board[area as keyof typeof state.board].intrigue : 0);
        return (
          zombies >
            alive.filter(
              (c) => c.area === area && effective.characters[c.id]!.identity !== 'zombie',
            ).length && alive.some((c) => c.area === area)
        );
      });
      add(
        'zombies-kill',
        '丧尸',
        p([
          e(
            'victim',
            {
              kind: 'characters',
              ids: alive.filter((c) => areas.includes(c.area)).map((c) => c.id),
            },
            { kind: 'death' },
          ),
        ]),
        {
          usage: { scope: 'day', count: 1, consume: 'on_complete', sharedKey: 'all-zombies-kill' },
        },
      );
    }
  }
  if (timing === 'phase:loop_end:enter') {
    const a = (area: string) =>
      effective.areaIntrigue[area as keyof typeof effective.areaIntrigue] ?? 0;
    const intrigue = (id: string) => effective.characters[id]!.counts.intrigue;
    const corpses = readValue({ kind: 'corpses' }, state, effective, catalog);
    const occurred = (...names: string[]) =>
      state.records.incidentHistory.some(
        (r) =>
          r.loop === state.clock.loop &&
          names.includes(catalog.incidents[r.incidentId]?.name ?? ''),
      );
    const checks: Record<string, () => boolean> = {
      复仇的火种: () => identities('mastermind').some((c) => a(c.initialArea) >= 2),
      守护此地: () => a('school') >= 2,
      被封印的邪灵: () => a('shrine') >= 2,
      '和我签订契约吧！': () => identities('key_person', true).some((c) => intrigue(c.id) >= 2),
      叛逆的世界: () => identities('key_person', true).some((c) => intrigue(c.id) >= 2),
      改变未来: () => occurred('蝴蝶效应'),
      巨大定时炸弹X: () => identities('witch').some((c) => a(c.initialArea) >= 2),
      巨大定时炸弹Y: () => identities('witch').some((c) => a(c.initialArea) >= 2),
      巨大定时炸弹Z: () => identities('witch').some((c) => a(c.initialArea) >= 2),
      绝密报告: () =>
        state.records.revealedFacts.some(
          (f) =>
            f.startsWith(`identity-loop:${state.clock.loop}:`) &&
            ['mastermind', 'unstable_factor', 'magician'].some((id) => f.endsWith(`:${id}`)),
        ),
      男子汉的战争: () => identities('ninja', true).some((c) => intrigue(c.id) >= 2),
      死亡真人秀: () => alive.length <= 6,
      事件交织的罗网: () => state.ex >= 3,
      命悬一线的计划: () => state.ex <= 1,
      黑暗学园: () => a('school') >= state.clock.loop - 1,
      外神合唱曲: () => alive.filter((c) => intrigue(c.id) >= 1).length >= 5,
      达贡的福音书: () => a('shrine') >= state.ex,
      黄衣之王: () => state.records.exIncreasedThisLoop,
      染血的仪式: () => corpses >= state.ex,
      闭锁的未来: () => state.ex % 2 === 0,
      鹅妈妈神秘故事: () => corpses >= Math.min(3, state.clock.loop),
      次元融合计划: () => occurred('遗言', '遗失物'),
      虚幻世界: () =>
        onBoard.some(
          (c) =>
            c.configuredIdentity === 'obstinate' &&
            !c.reverseIdentity &&
            !['outsider', 'copycat'].includes(c.definitionId) &&
            intrigue(c.id) + state.ex >= 3,
        ),
      恶魔的剧本: () => occurred('遗言', '代行者'),
    };
    for (const ruleId of state.script.ruleIds) {
      const override = state.records.revealedFacts
        .find((fact) => fact.startsWith('flag:failure-rule:'))
        ?.slice('flag:failure-rule:'.length);
      const rule = catalog.rules?.[ruleId];
      const name = rule?.kind === 'y' && override ? catalog.rules?.[override]?.name : rule?.name;
      if (name && checks[name]?.())
        add(
          `failure:${ruleId}`,
          name,
          p([e('failure', none, { kind: 'fail-loop', reason: ruleId })]),
        );
    }
  }
  return result;
}

export function nativeOptional(
  phase: GameState['clock']['phase'],
  state: GameState,
  catalog: ContentCatalog,
): RuleSourceDefinition[] {
  const result: RuleSourceDefinition[] = [];
  const effective = evaluatePersistent(state, catalog);
  const alive = Object.values(state.characters).filter((c) => c.alive && c.presence === 'board');
  const areasOf = (ids: string[]): Selector => ({
    kind: 'union',
    selectors: [...new Set(ids.map((id) => state.characters[id]!.area))]
      .filter((area) => area !== 'faraway')
      .map((id) => ({ kind: 'area', id: id as never })),
  });
  const byIdentity = (identity: string) =>
    alive.filter((c) => effective.characters[c.id]!.identity === identity).map((c) => c.id);
  const add = (
    id: string,
    name: string,
    program: ResolutionProgram,
    extra: Partial<RuleSourceDefinition> = {},
  ) =>
    result.push({
      id: `native.optional:${id}`,
      name,
      reference: `附录B/${name}`,
      kind: 'optional',
      timings: [],
      owner: 'mastermind',
      program,
      ...extra,
    });
  const loop = { scope: 'loop', count: 1, consume: 'on_complete' } as const;
  if (phase === 'protagonist_ability')
    for (const c of alive.filter((c) => c.definitionId === 'sacred_tree'))
      add(
        `tree:protagonists:${c.id}`,
        '御神木特性',
        p([
          e(
            'token',
            { kind: 'character', id: c.id },
            {
              kind: 'move-counter',
              amount: 1,
              to: { kind: 'characters', filter: { area: c.area, not: [c.id] } },
              sacredTree: true,
            },
          ),
        ]),
        { owner: state.leader, usage: { scope: 'day', count: 1, consume: 'on_complete' } },
      );
  for (const id of state.script.ruleIds) {
    const rule = catalog.rules?.[id];
    if (!rule) continue;
    if (phase === 'mastermind_ability') {
      if (rule.name === '流言四起' && !catalog.sources[id])
        add(
          id,
          rule.name,
          p([e('area', { kind: 'areas' }, { kind: 'counter', counter: 'intrigue', amount: 1 })]),
          { usage: loop },
        );
      if (rule.name === 'X异因子')
        add(
          id,
          rule.name,
          p([
            e('area', areasOf(byIdentity('unstable_factor')), {
              kind: 'counter',
              counter: 'intrigue',
              amount: 1,
            }),
          ]),
          { usage: loop },
        );
      if (rule.name === '怪物们的阴谋') {
        const ids = alive
          .filter((c) =>
            effective.characters[c.id]!.traits.some((t) => t.includes('ignore-goodwill')),
          )
          .map((c) => c.id);
        add(
          id,
          rule.name,
          p([e('area', areasOf(ids), { kind: 'counter', counter: 'intrigue', amount: 1 })]),
          { usage: { ...loop, count: 2 }, additionalLimits: [{ ...loop, scope: 'day' }] },
        );
      }
    }
    if (phase === 'loop_start' && ['被诅咒的土地', '魔女遗咒'].includes(rule.name)) {
      const ids = byIdentity(rule.name === '被诅咒的土地' ? 'ghost' : 'witch');
      const selector: Selector = {
        kind: 'union',
        selectors: [...new Set(ids.map((id) => state.characters[id]!.initialArea))]
          .filter((area) => area !== 'faraway')
          .map((id) => ({ kind: 'area', id: id as never })),
      };
      add(id, rule.name, p([e('curse', selector, { kind: 'curse', action: 'create' })]));
    }
    if (phase === 'turn_end') {
      const permitted =
        (rule.name === '难以言喻的怪物' && state.ex >= 3) ||
        (rule.name === '封印的终末' && effective.areaIntrigue.shrine >= 2) ||
        (rule.name === '被诅咒的土地' &&
          state.records.revealedFacts.some((fact) =>
            fact.startsWith(`flag:curse-no-target:${state.clock.day}:`),
          )) ||
        (rule.name === '恶魔的剧本' &&
          state.clock.day === state.script.daysPerLoop &&
          byIdentity('watcher').some(
            (id) => Object.values(state.characters[id]!.counters).reduce((a, b) => a + b, 0) <= 1,
          ));
      if (permitted) add(id, rule.name, p([e('heroes', none, { kind: 'protagonists-die' })]));
    }
  }
  if (state.script.moduleId === 'weird_mythology') {
    if (phase === 'turn_start' && state.clock.day === 1 && state.ex >= 1)
      add(
        'sensing',
        '感应咒文',
        p([
          e(
            'goodwill',
            { kind: 'characters' },
            { kind: 'counter', counter: 'goodwill', amount: 2 },
          ),
        ]),
        { owner: state.leader },
      );
    if (phase === 'loop_end' && state.ex >= 2) {
      const x = state.script.ruleIds.find((id) => catalog.rules?.[id]?.kind === 'x');
      if (x)
        add(
          'ancestral-memory',
          '先祖记忆',
          p([
            e('reveal', none, {
              kind: 'announce',
              text: `规则X1：${catalog.rules![x]!.name}`,
              fact: `rule:${x}`,
            }),
          ]),
          { owner: state.leader },
        );
    }
  }
  return result;
}
