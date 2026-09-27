import type {
  ContentCatalog,
  Condition,
  EffectSpec,
  Operation,
  ResolutionProgram,
  RuleSourceDefinition,
  Selector,
  Timing,
  ValueExpr,
} from '../../engine/src/model.js';

const none: Selector = { kind: 'none' };
const self: Selector = { kind: 'character', id: '$owner', allowDead: true };
const neighbours = (other = false): Selector => ({
  kind: 'characters',
  filter: { area: { sameAs: '$owner' }, ...(other ? { not: ['$owner'] } : {}) },
});
const effect = (
  id: string,
  target: Selector,
  operation: Operation,
  condition?: Condition,
): EffectSpec => ({ id, target, operation, condition });
const program = (...steps: EffectSpec[][]): ResolutionProgram => ({
  segments: steps.map((effects, i) => ({ id: `step${i}`, effects })),
});
const compare = (left: ValueExpr, op: '>=' | '<=' | '=', right: ValueExpr): Condition => ({
  kind: 'compare',
  left,
  op,
  right,
});
const counter = (type: 'anxiety' | 'intrigue' | 'goodwill', n: number) =>
  compare({ kind: 'counter', target: '$owner', counter: type, effective: true }, '>=', n);
const ex = (n: number) => compare({ kind: 'ex' }, '>=', n);
const heroes = () => effect('heroes', none, { kind: 'protagonists-die' });
const dead = { kind: 'alive', characterId: '$owner', value: false } as const;
const token = (
  id: string,
  target: Selector,
  type: 'anxiety' | 'intrigue' | 'goodwill' | 'hope' | 'despair',
  amount: number,
) => effect(id, target, { kind: 'counter', counter: type, amount });
const loop = { scope: 'loop', count: 1, consume: 'on_complete' } as const;

export function installIdentitySources(catalog: ContentCatalog): void {
  const add = (
    identity: string,
    suffix: string,
    timing: Timing,
    kind: 'forced' | 'optional',
    body: ResolutionProgram,
    condition?: Condition,
    extra: Partial<RuleSourceDefinition> = {},
  ) => {
    const id = `${identity}.${suffix}`;
    catalog.sources[id] = {
      id,
      name: `${catalog.identities[identity]!.name}·${suffix}`,
      reference: `附录B/身份/${catalog.identities[identity]!.name}`,
      kind,
      owner: 'mastermind',
      timings: [timing],
      instantiate: {
        kind: 'identity',
        id: identity,
        includeDead:
          ['ghost', 'zombie'].includes(identity) ||
          (['friend', 'wizard', 'alice'].includes(identity) && timing === 'phase:loop_end:enter') ||
          (identity === 'fool' && timing === 'incident:completed'),
      },
      program: body,
      condition,
      ...extra,
    };
  };
  const mastermindArea: Selector = {
    kind: 'union',
    selectors: [neighbours(), { kind: 'area', id: '$area:$owner' as never }],
  };
  for (const role of ['mastermind', 'deep_one'])
    add(
      role,
      'intrigue',
      'phase:mastermind_ability:enter',
      'optional',
      program([token('target', mastermindArea, 'intrigue', 1)]),
    );
  add(
    'fool',
    'event-completed',
    'incident:completed',
    'forced',
    program([effect('clear', self, { kind: 'clear-counters', counters: ['anxiety'] })]),
  );
  add(
    'magician',
    'death',
    'character:died',
    'forced',
    program([effect('clear', self, { kind: 'clear-counters', counters: ['anxiety'] })]),
  );
  for (const role of ['wizard', 'alice'])
    add(
      role,
      'loop-failure',
      'phase:loop_end:enter',
      'forced',
      program([effect('failure', none, { kind: 'fail-loop', reason: `${role}-dead` })]),
      dead,
    );
  add(
    'deep_one',
    'death',
    'character:died',
    'forced',
    program([
      effect('reveal', self, { kind: 'reveal-identity' }),
      effect('ex', none, { kind: 'ex', amount: 1 }),
    ]),
  );
  add('wizard', 'goodwill', 'ability:completed', 'forced', {
    segments: [
      { id: 'reveal', effects: [effect('reveal', self, { kind: 'reveal-identity' })] },
      {
        id: 'ex',
        optional: true,
        chooser: 'leader',
        effects: [effect('ex', none, { kind: 'ex', amount: 1 })],
      },
    ],
  });
  for (const timing of ['character:died', 'ability:completed'] as const)
    add(
      'key',
      timing,
      timing,
      'forced',
      program([effect('reveal', self, { kind: 'reveal-identity' })]),
    );
  add(
    'puppet',
    'goodwill',
    'ability:completed',
    'forced',
    program([
      effect('death', self, { kind: 'death' }),
      effect('world', none, { kind: 'world-move' }),
    ]),
    compare({ kind: 'token-kinds', target: '$owner' }, '>=', 2),
  );
  add(
    'alice',
    'goodwill',
    'ability:completed',
    'forced',
    program([
      token(
        'hope',
        {
          kind: 'characters',
          filter: { area: { sameAs: '$owner' }, not: ['$owner'] },
          count: 'all',
        },
        'hope',
        1,
      ),
    ]),
    ex(1),
    { usage: loop },
  );
  add('preacher', 'death', 'character:died', 'forced', {
    segments: [
      { id: 'despair', effects: [token('recipient', neighbours(), 'despair', 1)] },
      { id: 'world', optional: true, effects: [effect('world', none, { kind: 'world-move' })] },
    ],
  });
  add(
    'preacher',
    'goodwill',
    'phase:mastermind_ability:enter',
    'optional',
    program([token('recipient', neighbours(), 'goodwill', 1)]),
  );
  add(
    'narrator',
    'transfer',
    'phase:mastermind_ability:enter',
    'optional',
    program([
      effect('donor', neighbours(true), { kind: 'move-counter', amount: 1, to: neighbours(true) }),
    ]),
    ex(1),
  );
  add('paranoid', 'token', 'phase:mastermind_ability:enter', 'optional', {
    segments: [
      {
        id: 'token',
        choices: [{ key: 'counter', prompt: '选择密谋或不安', values: ['intrigue', 'anxiety'] }],
        effects: [
          effect('self', self, { kind: 'counter', counter: '$choice:counter' as never, amount: 1 }),
        ],
      },
    ],
  });
  add(
    'nursery_rhyme',
    'token',
    'phase:mastermind_ability:enter',
    'optional',
    {
      segments: [
        {
          id: 'token',
          choices: [{ key: 'counter', prompt: '选择不安或友好', values: ['anxiety', 'goodwill'] }],
          effects: [
            effect('recipient', neighbours(), {
              kind: 'counter',
              counter: '$choice:counter' as never,
              amount: 1,
            }),
          ],
        },
      ],
    },
    undefined,
    { usage: loop },
  );
  add(
    'nursery_rhyme',
    'heroes',
    'phase:turn_end:enter',
    'optional',
    program([heroes()]),
    compare({ kind: 'token-kinds', target: '$owner' }, '>=', 4),
  );
  add('lover', 'heroes', 'phase:turn_end:enter', 'optional', program([heroes()]), {
    kind: 'all',
    conditions: [counter('intrigue', 1), counter('anxiety', 3)],
  });
  add(
    'ninja',
    'kill',
    'phase:turn_end:enter',
    'optional',
    program([
      effect(
        'victim',
        {
          kind: 'characters',
          filter: {
            area: { sameAs: '$owner' },
            counter: { type: 'intrigue', atLeast: 2, effective: true },
          },
        },
        { kind: 'death' },
      ),
    ]),
  );
  for (const role of ['poisoner', 'piper'])
    add(
      role,
      'kill',
      'phase:turn_end:enter',
      'forced',
      program([effect('victim', neighbours(), { kind: 'death' })]),
      ex(2),
      { usage: loop },
    );
  add('poisoner', 'heroes', 'phase:turn_end:enter', 'forced', program([heroes()]), ex(4));
  add(
    'vampire',
    'kill-key',
    'phase:turn_end:enter',
    'optional',
    program([
      effect(
        'victim',
        {
          kind: 'characters',
          filter: {
            area: { sameAs: '$owner' },
            identity: 'key_person',
            counter: { type: 'intrigue', atLeast: 2, effective: true },
          },
        },
        { kind: 'death' },
      ),
    ]),
  );
  add(
    'vampire',
    'heroes',
    'phase:turn_end:enter',
    'optional',
    program([heroes()]),
    compare({ kind: 'corpses', area: '$initial:$owner' as never }, '>=', 2),
  );
  add('werewolf', 'heroes', 'phase:turn_end:enter', 'optional', program([heroes()]), {
    kind: 'incident-occurred',
    incidentId: '疯狂之夜',
    today: true,
  });
  add(
    'nightmare',
    'kill',
    'phase:turn_end:enter',
    'optional',
    program([effect('victim', neighbours(), { kind: 'death' })]),
  );
  const corpseIntrigue = compare(
    {
      kind: 'sum',
      selector: { kind: 'characters', filter: { alive: false }, count: 'all' },
      counter: 'intrigue',
      effective: true,
    },
    '>=',
    3,
  );
  add(
    'nightmare',
    'heroes',
    'phase:turn_end:enter',
    'optional',
    program([heroes()]),
    corpseIntrigue,
  );
  add(
    'piper',
    'corpse',
    'phase:turn_end:enter',
    'optional',
    program(
      [
        token(
          'corpse',
          { kind: 'characters', filter: { alive: false, area: { sameAs: '$owner' } } },
          'intrigue',
          1,
        ),
      ],
      [effect('heroes', none, { kind: 'protagonists-die' }, corpseIntrigue)],
    ),
  );
  for (const role of ['time_traveler', 'dimension_traveler'])
    add(
      role,
      'final-day',
      'phase:turn_end:enter',
      'optional',
      program([
        effect(
          'end',
          none,
          role === 'time_traveler'
            ? { kind: 'fail-loop', reason: 'time-traveler' }
            : { kind: 'protagonists-die' },
        ),
      ]),
      {
        kind: 'all',
        conditions: [
          { kind: 'final-day' },
          compare(
            role === 'time_traveler'
              ? { kind: 'counter', target: '$owner', counter: 'goodwill', effective: true }
              : { kind: 'token-kinds', target: '$owner' },
            '<=',
            2,
          ),
        ],
      },
    );
  add(
    'sacrifice',
    'sacrifice',
    'phase:turn_end:enter',
    'optional',
    program([effect('all', { kind: 'characters', count: 'all' }, { kind: 'death' }), heroes()]),
    { kind: 'all', conditions: [counter('intrigue', 2), counter('anxiety', 2)] },
  );
  add(
    'ghost',
    'anxiety',
    'phase:mastermind_ability:enter',
    'forced',
    program([
      token(
        'recipient',
        {
          kind: 'union',
          selectors: [
            neighbours(),
            { kind: 'characters', filter: { area: '$initial:$owner' as never } },
          ],
        },
        'anxiety',
        1,
      ),
    ]),
    dead,
  );
  add(
    'coward',
    'flee',
    'phase:mastermind_ability:enter',
    'forced',
    {
      segments: [
        { id: 'move', effects: [effect('self', self, { kind: 'move-character', adjacent: true })] },
      ],
    },
    counter('anxiety', 2),
  );
  add(
    'magician',
    'move',
    'phase:mastermind_ability:enter',
    'optional',
    program([
      effect(
        'recipient',
        {
          kind: 'characters',
          filter: {
            area: { sameAs: '$owner' },
            counter: { type: 'anxiety', atLeast: 1, effective: true },
          },
        },
        { kind: 'move-character', adjacent: true },
      ),
    ]),
    undefined,
    { usage: { ...loop, sharedKey: 'all-magicians' } },
  );
  add(
    'zombie',
    'move-corpse',
    'phase:turn_end:enter',
    'optional',
    program([
      effect(
        'corpse',
        { kind: 'characters', filter: { alive: false, identity: 'zombie' } },
        { kind: 'move-character', adjacent: true },
      ),
    ]),
    compare({ kind: 'corpses', identity: 'zombie' }, '>=', 1),
    {
      // All zombie corpses share this ability, including HSA's intrigue-token victims.
      instantiate: undefined,
      enabledBy: 'haunted_stage_again',
      usage: { scope: 'day', count: 1, consume: 'on_complete', sharedKey: 'all-zombies-move' },
    },
  );
}
