import type {
  ContentCatalog,
  Condition,
  EffectSpec,
  Operation,
  ResolutionProgram,
  RuleSourceDefinition,
  Selector,
} from '../../engine/src/model.js';
const self: Selector = { kind: 'character', id: '$owner' };
const same = (other = false): Selector => ({
  kind: 'characters',
  filter: { area: { sameAs: '$owner' }, ...(other ? { not: ['$owner'] } : {}) },
});
const e = (id: string, target: Selector, operation: Operation): EffectSpec => ({
  id,
  target,
  operation,
  chooser: 'source-owner',
});
const p = (...steps: EffectSpec[][]): ResolutionProgram => ({
  segments: steps.map((effects, i) => ({ id: `step${i}`, effects })),
});
const token = (target: Selector, counter: 'goodwill' | 'anxiety' | 'intrigue', amount: number) =>
  e('recipient', target, { kind: 'counter', counter, amount });
const loop2: Condition = { kind: 'compare', left: { kind: 'loop' }, op: '>=', right: 2 };
const empty = p([e('native', { kind: 'none' }, { kind: 'announce', text: '能力效果无现象' })]);

export function installCharacterSources(catalog: ContentCatalog): void {
  const add = (
    character: string,
    index: number,
    threshold: number,
    body: ResolutionProgram,
    once = false,
    extra: Partial<RuleSourceDefinition> = {},
  ) => {
    const id = `${character}.goodwill${index}`;
    catalog.characters[character]!.goodwillAbilities = catalog.characters[
      character
    ]!.goodwillAbilities.filter((a) => a.sourceId !== id);
    catalog.characters[character]!.goodwillAbilities.push({
      sourceId: id,
      threshold,
      oncePerLoop: once,
    });
    catalog.sources[id] = {
      id,
      name: `${catalog.characters[character]!.name}·友好能力${index}`,
      reference: `附录C/${catalog.characters[character]!.name}`,
      kind: 'goodwill',
      timings: ['phase:protagonist_ability:enter', 'phase:mastermind_ability:enter'],
      instantiate: { kind: 'character-definition', id: character },
      goodwill: { threshold },
      program: body,
      ...(once ? { usage: { scope: 'loop', count: 1, consume: 'on_complete' } as const } : {}),
      ...extra,
    };
  };
  add(
    'doctor',
    2,
    3,
    p([
      e(
        'patient',
        { kind: 'characters', filter: { definitionId: 'patient' }, count: 'all' },
        { kind: 'attachment', key: 'free-movement' },
      ),
    ]),
  );
  add('henchman', 1, 3, p([e('self', self, { kind: 'attachment', key: 'incident-ban' })]));
  add('little_girl', 1, 1, p([e('self', self, { kind: 'attachment', key: 'free-movement' })]));
  add('little_girl', 2, 3, p([e('self', self, { kind: 'move-character', adjacent: true })]), true);
  add('rich_girl', 1, 3, p([token(same(), 'goodwill', 1)]), false, {
    condition: { kind: 'area', target: '$owner', areas: ['school', 'city'] },
  });
  catalog.sources['shrine_maiden.goodwill1']!.condition = {
    kind: 'area',
    target: '$owner',
    areas: ['shrine'],
  };
  add('office_worker', 1, 3, p([e('reveal', self, { kind: 'reveal-identity' })]));
  add(
    'journalist',
    1,
    2,
    p([token({ kind: 'characters', filter: { not: ['$owner'] } }, 'anxiety', 1)]),
  );
  add(
    'journalist',
    2,
    2,
    p([
      token(
        { kind: 'union', selectors: [same(), { kind: 'area', id: '$area:$owner' as never }] },
        'intrigue',
        1,
      ),
    ]),
  );
  add(
    'spirit',
    2,
    5,
    p([
      token(
        { kind: 'union', selectors: [same(), { kind: 'area', id: '$area:$owner' as never }] },
        'intrigue',
        -1,
      ),
    ]),
  );
  add('outsider', 1, 3, p([e('reveal', self, { kind: 'reveal-identity' })]), false, {
    condition: loop2,
    goodwill: { threshold: 3, cannotRefuse: true },
  });
  add(
    'nurse',
    1,
    2,
    p([
      token(
        {
          kind: 'characters',
          filter: { area: { sameAs: '$owner' }, not: ['$owner'], atAnxietyLimit: true },
        },
        'anxiety',
        -1,
      ),
    ]),
    false,
    { goodwill: { threshold: 2, cannotRefuse: true } },
  );
  add(
    'cult_leader',
    1,
    3,
    p([
      token(
        { kind: 'characters', filter: { not: ['$owner'], atAnxietyLimit: true } },
        'goodwill',
        1,
      ),
    ]),
  );
  add(
    'cult_leader',
    2,
    4,
    p([
      e(
        'reveal',
        {
          kind: 'characters',
          filter: { area: { sameAs: '$owner' }, not: ['$owner'], atAnxietyLimit: true },
        },
        { kind: 'reveal-identity' },
      ),
    ]),
    true,
  );
  add('teacher', 1, 3, {
    segments: [
      {
        id: 'teach',
        choices: [
          {
            key: 'direction',
            prompt: '放置或移除不安',
            values: ['add', 'remove'],
            chooser: 'source-owner',
          },
        ],
        effects: [
          e(
            'student',
            { kind: 'characters', filter: { area: { sameAs: '$owner' }, attribute: '学生' } },
            {
              kind: 'counter',
              counter: 'anxiety',
              amount: 1,
              direction: '$choice:direction' as never,
            },
          ),
        ],
      },
    ],
  });
  add(
    'teacher',
    2,
    4,
    p([
      e(
        'student',
        { kind: 'characters', filter: { area: { sameAs: '$owner' }, attribute: '学生' } },
        { kind: 'reveal-identity' },
      ),
    ]),
  );
  add(
    'higher_being',
    1,
    3,
    {
      segments: [
        {
          id: 'gift',
          choices: [
            {
              key: 'type',
              prompt: '选择希望或绝望',
              values: ['hope', 'despair'],
              chooser: 'source-owner',
            },
          ],
          effects: [
            e('recipient', same(), {
              kind: 'counter',
              counter: '$choice:type' as never,
              amount: 1,
            }),
          ],
        },
      ],
    },
    true,
    { goodwill: { threshold: 3, mastermindThreshold: 1 } },
  );
  add('fantasy', 1, 3, p([e('character', same(), { kind: 'move-character' })]), true);
  add(
    'temp_worker_alt',
    1,
    3,
    p([e('reveal', self, { kind: 'reveal-identity' }), token(same(), 'goodwill', 2)]),
    true,
  );
  add(
    'transfer_student',
    1,
    2,
    p([
      e('recipient', same(true), {
        kind: 'replace-counter',
        from: 'intrigue',
        to: 'goodwill',
        amount: 1,
      }),
    ]),
  );
  add(
    'appraiser',
    2,
    5,
    p([e('corpse', { kind: 'characters', filter: { alive: false } }, { kind: 'reveal-identity' })]),
    true,
  );
  for (const [character, index, threshold, once, native] of [
    ['ai', 1, 3, true, 'ai'],
    ['servant', 1, 4, true, 'servant'],
    ['hermit', 1, 5, true, 'hermit'],
    ['scholar', 1, 3, false, 'scholar'],
    ['big_shot', 1, 5, true, 'big-shot'],
    ['copycat', 1, 3, false, 'copycat'],
    ['police', 1, 4, true, 'police'],
    ['spirit', 1, 3, true, 'spirit'],
    ['class_rep', 1, 2, false, 'class-rep'],
    ['informant', 1, 5, true, 'informant'],
    ['appraiser', 1, 2, true, 'transfer'],
    ['uploader', 1, 3, false, 'uploader'],
    ['sister', 1, 5, false, 'sister'],
  ] as const)
    add(character, index, threshold, empty, once, {
      native,
      ...(character === 'copycat'
        ? { condition: loop2, goodwill: { threshold, cannotRefuse: true } }
        : {}),
    });
}
