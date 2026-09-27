import type {
  CharacterDefinition,
  ContentCatalog,
  Condition,
  EffectSpec,
  ResolutionProgram,
  RuleSourceDefinition,
  Selector,
  CounterType,
  Operation,
} from '../../engine/src/model.js';
import { blankCounters } from '../../engine/src/model.js';
import type { NewGameInput } from '../../engine/src/state.js';
import { installRegistry } from './registry.js';
import { NATIVE_INCIDENTS } from '../../engine/src/native-incidents.js';
import { installIdentitySources } from './identity-sources.js';
import { installCharacterSources } from './character-sources.js';
export { contentCoverage } from './registry.js';

const all: Selector = { kind: 'characters', count: 'all' };
const any: Selector = { kind: 'characters' };
const self: Selector = { kind: 'character', id: '$owner' };
const same = (owner = '$owner', other = false): Selector => ({
  kind: 'characters',
  filter: { area: { sameAs: owner }, ...(other ? { not: [owner] } : {}) },
});
const effect = (
  id: string,
  target: Selector,
  operation: Operation,
  condition?: Condition,
  chooser?: EffectSpec['chooser'],
): EffectSpec => ({ id, target, operation, condition, chooser });
const counter = (
  id: string,
  target: Selector,
  type: CounterType,
  amount: number,
  chooser?: EffectSpec['chooser'],
) => effect(id, target, { kind: 'counter', counter: type, amount }, undefined, chooser);
const program = (...effects: EffectSpec[][]): ResolutionProgram => ({
  segments: effects.map((entries, index) => ({ id: `step${index}`, effects: entries })),
});
const count = (target: string, type: CounterType, amount: number): Condition => ({
  kind: 'compare',
  left: { kind: 'counter', target, counter: type, effective: true },
  op: '>=',
  right: amount,
});
const areaCount = (area: 'hospital' | 'shrine' | 'city' | 'school', amount: number): Condition => ({
  kind: 'compare',
  left: { kind: 'area-intrigue', area },
  op: '>=',
  right: amount,
});

export function createCatalog(): ContentCatalog {
  const catalog: ContentCatalog = {
    version: 'flow-v2.2026-09-23',
    modules: {},
    identities: {},
    characters: {},
    incidents: {},
    sources: {},
    persistent: {},
  };
  const identities: Array<[string, string, string[], number?]> = [
    ['civilian', '平民', []],
    ['key_person', '关键人物', []],
    ['killer', '杀手', ['ignore-goodwill']],
    ['mastermind', '主谋', ['ignore-goodwill']],
    ['cultist', '邪教徒', ['must-ignore-goodwill']],
    ['friend', '亲友', [], 2],
    ['mob', '暴徒', ['ignore-goodwill']],
    ['serial_killer', '杀人狂', []],
    ['gossip', '传谣人', [], 1],
    ['witch', '魔女', ['must-ignore-goodwill']],
    ['time_traveler', '时间旅者', ['immortal']],
    ['beloved', '心上人', []],
    ['lover', '求爱者', []],
    ['unstable_factor', '不安定因子', ['ignore-goodwill']],
    ['ninja', '忍者', ['ignore-goodwill']],
    ['obstinate', '强迫症', ['must-ignore-goodwill']],
    ['magician', '魔术师', []],
    ['immortal', '永生者', ['immortal']],
    ['prophet', '预言家', []],
    ['poisoner', '投毒者', ['ignore-goodwill']],
    ['fool', '愚者', [], 1],
    ['paranoid', '偏执狂', ['must-ignore-goodwill']],
    ['psychologist', '心理医生', []],
    ['detective', '侦探', ['immortal']],
    ['twins', '双胞胎', []],
    ['vampire', '吸血鬼', ['ignore-goodwill', 'immortal']],
    ['werewolf', '狼人', ['ignore-goodwill']],
    ['nightmare', '梦魇', ['ignore-goodwill', 'immortal']],
    ['ghost', '鬼魂', [], 1],
    ['paper_tiger', '纸老虎', ['immortal']],
    ['coward', '胆小鬼', []],
    ['zombie', '丧尸', []],
    ['sacrifice', '祭品', ['immortal']],
    ['deep_one', '深潜者', ['ignore-goodwill'], 1],
    ['wizard', '巫师', [], 1],
    ['witness', '目击者', []],
    ['faceless', '无面者', ['immortal', 'ignore-goodwill']],
    ['puppet', '提线木偶', ['puppet-ignore-goodwill']],
    ['narrator', '叙述者', ['immortal']],
    ['nursery_rhyme', '童谣', ['puppet-ignore-goodwill']],
    ['dimension_traveler', '次元旅者', ['immortal']],
    ['causal_fragment', '因果残片', []],
    ['piper', '魔笛手', ['ignore-goodwill']],
    ['preacher', '布道者', [], 1],
    ['alice', '爱丽丝', []],
    ['watcher', '监视者', ['immortal'], 1],
    ['influencer', '网络名流', []],
    ['key', '密钥', []],
    ['eccentric', '怪杰', ['immortal', 'must-ignore-goodwill'], 1],
  ];
  for (const [id, name, traits, max] of identities)
    catalog.identities[id] = { id, name, traits, max, abilities: [] };
  const definitions: Array<
    [
      string,
      string,
      string[],
      CharacterDefinition['initialAreas'],
      CharacterDefinition['forbiddenAreas'],
      number | 'X',
      string[]?,
    ]
  > = [
    ['ai', 'AI', ['造物'], ['city'], ['shrine', 'hospital', 'school'], 4],
    ['uploader', 'UP主', ['男性', '学生'], ['faraway'], [], 2],
    ['higher_being', '上位存在', ['少女'], ['shrine'], [], 2],
    ['temp_worker_alt', '临时工？', ['少女'], ['city'], [], 3],
    ['temp_worker', '临时工', ['成人', '男性'], ['city'], [], 1],
    ['servant', '从者', ['成人', '女性'], ['school', 'city'], [], 3],
    ['hermit', '仙人', ['成人', '男性'], ['shrine', 'hospital'], [], 'X'],
    ['black_cat', '黑猫', ['动物'], ['shrine'], [], 0],
    ['idol', '偶像', ['学生', '少女'], ['city'], [], 2],
    ['soldier', '军人', ['男性', '成人'], ['hospital'], [], 3],
    ['police', '刑警', ['成人', '男性'], ['city'], [], 3],
    ['doctor', '医生', ['成人', '男性'], ['hospital'], [], 2],
    ['big_shot', '大人物', ['成人', '男性'], ['city'], [], 4],
    ['rich_girl', '大小姐', ['学生', '少女'], ['school'], [], 1],
    ['female_student', '女子学生', ['学生', '少女'], ['school'], [], 3],
    ['sister', '妹妹', ['少女', '妹妹'], ['shrine'], [], 3],
    ['journalist', '媒体人', ['成人', '男性'], ['city'], [], 2],
    ['scholar', '学者', ['男性', '成人'], ['hospital'], [], 2],
    ['little_girl', '小女孩', ['学生', '少女'], ['school'], ['shrine', 'city', 'hospital'], 1],
    ['outsider', '局外人', ['学生', '少年'], ['school'], [], 3],
    ['shrine_maiden', '巫女', ['学生', '少女'], ['shrine'], ['city'], 2],
    ['fantasy', '幻想', ['虚构', '女性'], ['shrine'], [], 3],
    ['alien', '异界人', ['学生', '少女'], ['shrine'], ['hospital'], 2],
    ['informant', '情报商', ['女性', '成人'], ['city'], [], 3],
    ['henchman', '手下', ['成人', '男性'], ['hospital', 'shrine', 'city', 'school'], [], 1],
    ['nurse', '护士', ['成人', '女性'], ['hospital'], [], 3],
    ['cult_leader', '教主', ['成人', '女性'], ['shrine'], [], 3, ['cult-leader']],
    ['teacher', '教师', ['成人', '女性'], ['school'], [], 2],
    ['copycat', '模仿犯', ['少年', '学生'], ['city'], [], 2],
    ['class_rep', '班长', ['学生', '少女'], ['school'], [], 2],
    ['male_student', '男子学生', ['学生', '少年'], ['school'], [], 2],
    ['spirit', '神灵', ['男性', '女性'], ['shrine'], [], 3],
    ['office_worker', '职员', ['成人', '男性'], ['city'], ['school'], 2],
    ['transfer_student', '转校生', ['学生', '少女'], ['school'], [], 2],
    ['sacred_tree', '御神木', ['植物'], ['shrine'], ['school', 'city', 'hospital'], 4],
    ['patient', '住院患者', ['少年'], ['hospital'], ['shrine', 'school', 'city'], 2],
    ['appraiser', '鉴别员', ['成人', '男性'], ['city'], [], 3],
  ];
  for (const [
    id,
    name,
    attributes,
    initialAreas,
    forbiddenAreas,
    anxietyLimit,
    traits = [],
  ] of definitions)
    catalog.characters[id] = {
      id,
      name,
      attributes,
      initialAreas,
      forbiddenAreas,
      anxietyLimit,
      traits,
      goodwillAbilities: [],
    };

  const incident = (id: string, name: string, p: ResolutionProgram, extra = {}) => {
    catalog.incidents[id] = { id, name, program: p, ...extra };
  };
  const murder = program([effect('victim', same('$culprit', true), { kind: 'death' })]);
  const spread = program(
    [counter('first', any, 'anxiety', 2)],
    [counter('second', { kind: 'characters', filter: { not: ['$target:first'] } }, 'intrigue', 1)],
  );
  incident('murder', '谋杀', murder);
  incident('serial_murder', '连续杀人', murder);
  incident(
    'suicide',
    '自杀',
    program([effect('suicide', { kind: 'character', id: '$culprit' }, { kind: 'death' })]),
  );
  incident('anxiety_spread', '不安扩散', spread);
  incident(
    'evil_contamination',
    '邪气污染',
    program([counter('shrine', { kind: 'area', id: 'shrine' }, 'intrigue', 2)]),
  );
  incident(
    'hospital_accident',
    '医院事故',
    program([
      effect(
        'patients',
        { kind: 'characters', filter: { area: 'hospital' }, count: 'all' },
        { kind: 'death' },
        areaCount('hospital', 1),
      ),
      effect(
        'protagonists',
        { kind: 'none' },
        { kind: 'protagonists-die' },
        areaCount('hospital', 2),
      ),
    ]),
  );
  incident(
    'terrorism',
    '恐怖袭击',
    program([
      effect(
        'victims',
        { kind: 'characters', filter: { area: 'city' }, count: 'all' },
        { kind: 'death' },
        areaCount('city', 1),
      ),
      effect('protagonists', { kind: 'none' }, { kind: 'protagonists-die' }, areaCount('city', 2)),
    ]),
  );
  incident(
    'spreading',
    '散播',
    program(
      [counter('first', any, 'goodwill', -2)],
      [
        counter(
          'second',
          { kind: 'characters', filter: { not: ['$target:first'] } },
          'goodwill',
          2,
        ),
      ],
    ),
  );
  incident('disappearance', '失踪', {
    segments: [
      {
        id: 'move',
        choices: [
          {
            key: 'destination',
            prompt: '选择目的版图',
            values: ['hospital', 'shrine', 'city', 'school'],
          },
        ],
        effects: [
          effect(
            'move',
            { kind: 'character', id: '$culprit' },
            { kind: 'move-character', destination: '$choice:destination' as never },
          ),
        ],
      },
      {
        id: 'intrigue',
        effects: [
          counter('intrigue', { kind: 'area', id: '$area:$culprit' as never }, 'intrigue', 1),
        ],
      },
    ],
  });
  incident(
    'long_distance_murder',
    '远距离杀人',
    program([
      effect(
        'victim',
        {
          kind: 'characters',
          filter: { counter: { type: 'intrigue', atLeast: 2, effective: true } },
        },
        { kind: 'death' },
      ),
    ]),
  );
  incident('butterfly_effect', '蝴蝶效应', {
    segments: [
      {
        id: 'tokens',
        choices: [
          { key: 'counter', prompt: '选择指示物', values: ['goodwill', 'anxiety', 'intrigue'] },
        ],
        effects: [counter('token', same('$culprit'), '$choice:counter' as CounterType, 1)],
      },
    ],
  });
  incident(
    'confession',
    '自白',
    program([effect('reveal', { kind: 'character', id: '$culprit' }, { kind: 'reveal-identity' })]),
  );
  incident('omen', '前兆', program([counter('anxiety', same('$culprit'), 'anxiety', 1)]), {
    thresholdAdjustment: -1,
  });
  incident('impulsive_murder', '冲动杀人', murder, { thresholdAdjustment: -1 });
  incident(
    'funeral',
    '送葬',
    program([effect('victim', any, { kind: 'death' }, undefined, 'leader')]),
    { thresholdAdjustment: -1 },
  );
  incident(
    'gruesome_murder',
    '猎奇杀人',
    {
      segments: [...murder.segments, ...spread.segments].map((s, i) => ({ ...s, id: `step${i}` })),
    },
    { thresholdAdjustment: 1 },
  );
  incident(
    'silver_bullet',
    '银色子弹',
    {
      ...program([effect('text', { kind: 'none' }, { kind: 'noop' })]),
      endLoopOnComplete: 'silver-bullet',
    },
    { endsLoopOnComplete: true },
  );
  incident('despair_dark', '绝望之暗', program([counter('despair', any, 'despair', 1)]));
  incident('hope_light', '希望之光', program([counter('hope', any, 'hope', 1, 'leader')]), {
    countMode: 'goodwill',
  });
  incident('sunlight', '隙间的阳光', program([counter('hope', any, 'hope', 1, 'leader')]));
  incident(
    'discovery',
    '发现',
    program([effect('ex', { kind: 'none' }, { kind: 'ex', amount: 1 })]),
  );
  incident(
    'dimension_change',
    '次元转换',
    program([effect('world', { kind: 'none' }, { kind: 'world-move' })]),
    { alwaysOccurs: true },
  );

  const add = (source: RuleSourceDefinition) => {
    catalog.sources[source.id] = source;
  };
  const identitySource = (
    identity: string,
    suffix: string,
    phase: string,
    kind: 'forced' | 'optional',
    p: ResolutionProgram,
    condition?: Condition,
    extra: Partial<RuleSourceDefinition> = {},
  ) => {
    add({
      id: `${identity}.${suffix}`,
      name: `${catalog.identities[identity]!.name}·${suffix}`,
      reference: '附录B/身份',
      kind,
      timings: [phase as never],
      instantiate: {
        kind: 'identity',
        id: identity,
        includeDead: ['friend', 'fool', 'wizard', 'alice'].includes(identity),
      },
      program: p,
      condition,
      owner: 'mastermind',
      ...extra,
    });
  };
  identitySource(
    'key_person',
    'death',
    'character:died',
    'forced',
    program([
      effect('failure', { kind: 'none' }, { kind: 'fail-loop', reason: 'key-person-died' }),
    ]),
  );
  identitySource(
    'serial_killer',
    'kill',
    'phase:turn_end:enter',
    'forced',
    program([effect('victim', same('$owner', true), { kind: 'death' })]),
    {
      kind: 'compare',
      left: { kind: 'selection-count', selector: same('$owner', true) },
      op: '=',
      right: 1,
    },
  );
  identitySource(
    'gossip',
    'anxiety',
    'phase:mastermind_ability:enter',
    'optional',
    program([counter('target', same(), 'anxiety', 1)]),
  );
  identitySource(
    'mastermind',
    'intrigue',
    'phase:mastermind_ability:enter',
    'optional',
    program([counter('target', same(), 'intrigue', 1)]),
  );
  identitySource(
    'killer',
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
  identitySource(
    'killer',
    'kill-protagonists',
    'phase:turn_end:enter',
    'optional',
    program([effect('death', { kind: 'none' }, { kind: 'protagonists-die' })]),
    count('$owner', 'intrigue', 4),
  );
  identitySource(
    'friend',
    'loop-failure',
    'phase:loop_end:enter',
    'forced',
    program([
      effect(
        'reveal',
        { kind: 'character', id: '$owner', allowDead: true },
        { kind: 'reveal-identity' },
      ),
      effect('failure', { kind: 'none' }, { kind: 'fail-loop', reason: 'friend-dead' }),
    ]),
    { kind: 'alive', characterId: '$owner', value: false },
  );
  identitySource(
    'fool',
    'event-completed',
    'incident:completed',
    'forced',
    program([
      counter('remove', { kind: 'character', id: '$owner', allowDead: true }, 'anxiety', -1000000),
    ]),
  );
  identitySource(
    'psychologist',
    'calm',
    'phase:mastermind_ability:enter',
    'forced',
    program([counter('patient', same('$owner', true), 'anxiety', -1)]),
    { kind: 'compare', left: { kind: 'ex' }, op: '>=', right: 1 },
  );

  const goodwill = (
    characterId: string,
    index: number,
    threshold: number,
    p: ResolutionProgram,
    once = false,
    extra: Partial<RuleSourceDefinition> = {},
  ) => {
    for (const segment of p.segments)
      for (const effect of segment.effects)
        if (effect.chooser === 'leader') effect.chooser = 'source-owner';
    const id = `${characterId}.goodwill${index}`;
    catalog.characters[characterId]!.goodwillAbilities.push({
      sourceId: id,
      threshold,
      oncePerLoop: once,
    });
    add({
      id,
      name: `${catalog.characters[characterId]!.name}·友好能力${index}`,
      reference: '附录C/角色友好能力',
      kind: 'goodwill',
      timings: ['phase:protagonist_ability:enter', 'phase:mastermind_ability:enter'],
      instantiate: { kind: 'character-definition', id: characterId },
      goodwill: { threshold },
      program: p,
      ...(once ? { usage: { scope: 'loop', count: 1, consume: 'on_complete' } as const } : {}),
      ...extra,
    });
  };
  for (const id of ['male_student', 'female_student'])
    goodwill(
      id,
      1,
      2,
      program([
        counter(
          'student',
          {
            kind: 'characters',
            filter: { area: { sameAs: '$owner' }, not: ['$owner'], attribute: '学生' },
          },
          'anxiety',
          -1,
          'leader',
        ),
      ]),
    );
  goodwill(
    'doctor',
    1,
    2,
    {
      segments: [
        {
          id: 'treat',
          choices: [
            {
              key: 'direction',
              prompt: '放置或移除不安',
              values: ['add', 'remove'],
              chooser: 'source-owner',
            },
          ],
          effects: [
            effect(
              'patient',
              same('$owner', true),
              {
                kind: 'counter',
                counter: 'anxiety',
                amount: 1,
                direction: '$choice:direction' as never,
              },
              undefined,
              'source-owner',
            ),
          ],
        },
      ],
    },
    false,
    { goodwill: { threshold: 2, mastermindThreshold: 2 } },
  );
  goodwill(
    'shrine_maiden',
    1,
    3,
    program([counter('shrine', { kind: 'area', id: 'shrine' }, 'intrigue', -1, 'leader')]),
  );
  goodwill(
    'shrine_maiden',
    2,
    5,
    program([effect('reveal', same(), { kind: 'reveal-identity' }, undefined, 'leader')]),
    true,
  );
  goodwill('soldier', 1, 2, program([counter('anxiety', same(), 'anxiety', 2, 'leader')]), true);
  goodwill(
    'soldier',
    2,
    5,
    program([
      effect('protect', { kind: 'none' }, { kind: 'set-protagonist-protection', value: true }),
    ]),
    true,
  );
  goodwill('police', 2, 5, program([counter('guard', same(), 'guard', 1, 'leader')]), true);
  goodwill('idol', 1, 3, program([counter('calm', same('$owner', true), 'anxiety', -1, 'leader')]));
  goodwill(
    'idol',
    2,
    4,
    program([counter('friend', same('$owner', true), 'goodwill', 1, 'leader')]),
  );
  goodwill('office_worker', 1, 2, program([effect('reveal', self, { kind: 'reveal-identity' })]));
  goodwill(
    'alien',
    1,
    4,
    program([effect('death', same('$owner', true), { kind: 'death' }, undefined, 'leader')]),
    true,
  );
  goodwill(
    'alien',
    2,
    5,
    program([
      effect(
        'revive',
        { kind: 'characters', filter: { area: { sameAs: '$owner' }, alive: false } },
        { kind: 'resurrect' },
        undefined,
        'leader',
      ),
    ]),
    true,
  );
  goodwill('fantasy', 2, 4, program([effect('remove', self, { kind: 'remove-character' })]));

  const baseIncidents = [
    'anxiety_spread',
    'murder',
    'hospital_accident',
    'suicide',
    'spreading',
    'disappearance',
    'long_distance_murder',
  ];
  catalog.modules.first_steps = {
    id: 'first_steps',
    name: 'First Steps',
    ruleSelection: { y: 1, x: 1 },
    finalShowdown: false,
    exReset: 'none',
    rules: [
      'fs.y.murder_plan',
      'fs.y.revenge',
      'fs.y.protect_this_place',
      'fs.x.shadow_of_the_ripper',
      'fs.x.rumors',
      'fs.x.darkest_script',
    ],
    identities: [
      'civilian',
      'key_person',
      'killer',
      'mastermind',
      'cultist',
      'friend',
      'mob',
      'serial_killer',
      'gossip',
    ],
    incidents: baseIncidents,
  };
  catalog.modules.basic_tragedy_x = {
    id: 'basic_tragedy_x',
    name: 'Basic Tragedy X',
    ruleSelection: { y: 1, x: 2 },
    finalShowdown: true,
    exReset: 'none',
    rules: [
      'btx.y.murder_plan',
      'btx.y.sealed_evil',
      'btx.y.contract',
      'btx.y.change_future',
      'btx.y.time_bomb',
      'btx.x.friends',
      'btx.x.lovers',
      'btx.x.hidden_killer',
      'btx.x.rumors',
      'btx.x.delusion_virus',
      'btx.x.causal_line',
      'btx.x.unknown_factor',
    ],
    identities: identities.slice(0, 14).map(([id]) => id),
    incidents: [...baseIncidents, 'evil_contamination', 'butterfly_effect'],
  };
  for (const id of ['fs.x.rumors', 'btx.x.rumors'])
    add({
      id,
      name: '流言四起',
      reference: '附录B/规则X',
      enabledBy: id,
      kind: 'optional',
      timings: ['phase:mastermind_ability:enter'],
      program: program([counter('area', { kind: 'areas' }, 'intrigue', 1)]),
      usage: { scope: 'loop', count: 1, consume: 'on_complete' },
    });
  for (const name of NATIVE_INCIDENTS)
    catalog.incidents[name] = {
      id: name,
      name,
      native: true,
      program: { segments: [] },
      ...(['阴谋活动', '空想事件', '廷达罗斯之嗅'].includes(name)
        ? { countMode: 'intrigue' as const }
        : {}),
      ...(['疯狂之夜', '诅咒活化', '污秽溢出', '死者默示录'].includes(name)
        ? { crowd: { requiredCorpses: name === '疯狂之夜' ? 0 : name === '诅咒活化' ? 1 : 2 } }
        : {}),
    };
  installRegistry(catalog);
  installIdentitySources(catalog);
  installCharacterSources(catalog);
  return catalog;
}

export function firstStepsScenario(): NewGameInput {
  const catalog = createCatalog();
  const cast = [
    ['doctor', 'key_person'],
    ['male_student', 'killer'],
    ['female_student', 'mastermind'],
    ['shrine_maiden', 'gossip'],
    ['police', 'serial_killer'],
  ] as const;
  return {
    script: {
      id: 'fs.training.01',
      moduleId: 'first_steps',
      ruleIds: ['fs.y.murder_plan', 'fs.x.shadow_of_the_ripper'],
      loops: 3,
      daysPerLoop: 4,
      finalShowdown: false,
      incidents: [
        {
          entryId: 'day2',
          day: 2,
          incidentId: 'hospital_accident',
          publicName: '医院事故',
          culpritIds: ['doctor'],
        },
        {
          entryId: 'day4',
          day: 4,
          incidentId: 'suicide',
          publicName: '自杀',
          culpritIds: ['police'],
        },
      ],
      options: {},
    },
    characters: cast.map(([id, identity]) => ({
      id,
      definitionId: id,
      name: catalog.characters[id]!.name,
      printedIdentity: identity,
      configuredIdentity: identity,
      temporaryIdentity: null,
      publicIdentity: null,
      initialArea: catalog.characters[id]!.initialAreas[0]!,
      area: catalog.characters[id]!.initialAreas[0]!,
      presence: 'board',
      alive: true,
      counters: blankCounters(),
      attachments: [],
      marks: { communicated: false, died: false },
    })),
  };
}
