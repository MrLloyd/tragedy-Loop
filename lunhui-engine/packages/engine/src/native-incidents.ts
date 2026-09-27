import type {
  AreaId,
  ContentCatalog,
  EffectSpec,
  GameState,
  IncidentDefinition,
  Operation,
  ResolutionProgram,
  Selector,
} from './model.js';
import { evaluatePersistent } from './persistent.js';
import { readValue } from './query.js';

export const NATIVE_INCIDENTS = [
  '阴谋活动',
  '暴乱',
  '破局',
  '伪装自杀',
  '伪造事件',
  '可疑信件',
  '封锁',
  '亵渎杀人',
  '言灵诅咒',
  '孤守',
  '疯狂之夜',
  '诅咒活化',
  '污秽溢出',
  '死者默示录',
  '疯狂杀人',
  '集体自杀',
  '灭绝之火',
  '廷达罗斯之嗅',
  '次元歪曲',
  '次元断层',
  '遗失物',
  '空想事件',
  '遗言',
  '奇点',
  '代行者',
  '骤变',
];
const areas = ['hospital', 'shrine', 'city', 'school'];
const none: Selector = { kind: 'none' };
const any: Selector = { kind: 'characters' };
const e = (
  id: string,
  target: Selector,
  operation: Operation,
  extra: Partial<EffectSpec> = {},
): EffectSpec => ({ id, target, operation, ...extra });
const p = (...effects: EffectSpec[][]): ResolutionProgram => ({
  segments: effects.map((effects, index) => ({ id: `step${index}`, effects })),
});
const token = (
  id: string,
  target: Selector,
  counter: 'intrigue' | 'anxiety' | 'goodwill',
  amount: number,
) => e(id, target, { kind: 'counter', counter, amount });
const heroDeath = () => e('hero-death', none, { kind: 'protagonists-die' });
const world = () => e('world', none, { kind: 'world-move' });

export function incidentProgram(
  definition: IncidentDefinition,
  state: GameState,
  catalog: ContentCatalog,
  culprit: string,
  entryId?: string,
  calledByAi = false,
  effectArea?: AreaId,
): ResolutionProgram {
  if (!definition.native) return structuredClone(definition.program);
  const card = state.characters[culprit];
  const scheduled = state.script.incidents.find((entry) => entry.entryId === entryId);
  const area = effectArea ?? card?.area ?? scheduled?.crowdArea ?? 'city';
  const initial = card?.initialArea ?? area;
  const self: Selector = { kind: 'character', id: culprit };
  const board: Selector = { kind: 'area', id: area as never };
  const neighbours: Selector = { kind: 'characters', filter: { area: { sameAs: culprit } } };
  const others: Selector = {
    kind: 'characters',
    filter: { area: { sameAs: culprit }, not: [culprit] },
  };
  const corpseCondition = (n: number) => ({
    kind: 'compare' as const,
    left: { kind: 'corpses' as const, area },
    op: '>=' as const,
    right: n,
  });
  const prior = state.records.incidentHistory.filter(
    (record) =>
      record.entryId === entryId &&
      record.sequence < state.records.incidentHistory.length - (calledByAi ? 0 : 1),
  );
  switch (definition.name) {
    case '阴谋活动':
      return {
        segments: [
          { id: 'choose-event', effects: [], eventChoice: ['serial_murder', 'disappearance'] },
        ],
      };
    case '空想事件':
      return {
        segments: [
          {
            id: 'choose-event',
            effects: [],
            eventChoice: ['impulsive_murder', '次元歪曲', '遗失物'],
          },
        ],
      };
    case '暴乱':
      return p(
        ['city', 'school'].map((id) =>
          e(
            id,
            { kind: 'characters', filter: { area: id as AreaId }, count: 'all' },
            { kind: 'death' },
            {
              condition: {
                kind: 'compare',
                left: { kind: 'area-intrigue', area: id as never },
                op: '>=',
                right: 1,
              },
            },
          ),
        ),
      );
    case '破局':
      return p([
        e(
          'remove',
          { kind: 'union', selectors: [any, { kind: 'areas' }] },
          { kind: 'counter', counter: 'intrigue', amount: -2 },
          { chooser: 'leader' },
        ),
      ]);
    case '伪装自杀':
      return p([e('ex', self, { kind: 'attachment', key: 'fake-suicide' })]);
    case '伪造事件':
      return p([
        {
          ...heroDeath(),
          condition: {
            kind: 'compare',
            left: { kind: 'area-intrigue', area: initial as never },
            op: '>=',
            right: 2,
          },
        },
      ]);
    case '言灵诅咒':
      return p([e('curse', self, { kind: 'curse', action: 'create' })]);
    case '诅咒活化':
      return p([e('curse', board, { kind: 'curse', action: 'create' })]);
    case '亵渎杀人':
      return {
        segments: [
          {
            id: 'choice',
            effects: [],
            alternatives: [
              {
                id: 'kill',
                label: '同区域另一名角色死亡',
                effects: [e('victim', others, { kind: 'death' })],
              },
              {
                id: 'intrigue',
                label: '当事人版图密谋+1',
                effects: [token('intrigue', board, 'intrigue', 1)],
              },
            ],
          },
        ],
      };
    case '污秽溢出':
      return p(
        [token('anxiety', any, 'anxiety', 2)],
        [token('intrigue', { kind: 'areas' }, 'intrigue', 1)],
      );
    case '死者默示录':
      return p(
        [e('kill', { kind: 'characters', filter: { area }, count: 'all' }, { kind: 'death' })],
        [{ ...heroDeath(), condition: corpseCondition(5) }],
      );
    case '疯狂杀人':
      return p([e('victim', neighbours, { kind: 'death' })]);
    case '集体自杀':
      return p([
        e(
          'victims',
          { kind: 'characters', filter: { area: { sameAs: culprit } }, count: 'all' },
          { kind: 'death' },
          {
            condition: {
              kind: 'compare',
              left: { kind: 'counter', target: culprit, counter: 'intrigue', effective: true },
              op: '>=',
              right: 1,
            },
          },
        ),
      ]);
    case '灭绝之火':
      return calledByAi || prior.length
        ? p([])
        : p([e('all-die', { kind: 'characters', count: 'all' }, { kind: 'death' }), heroDeath()]);
    case '廷达罗斯之嗅':
      return p([
        e('activate', none, {
          kind: 'set-record',
          key: `tindalos:${state.records.incidentHistory.length - 1}`,
          value: true,
        }),
      ]);
    case '疯狂之夜': {
      const zombies = readValue(
        { kind: 'corpses', identity: 'zombie' },
        state,
        evaluatePersistent(state, catalog),
        catalog,
      );
      return zombies < 6
        ? p([])
        : p([
            e('schedule', none, {
              kind: 'schedule',
              task: {
                sourceId: 'mad-night',
                due: 'phase:turn_end:enter',
                loop: state.clock.loop,
                day: state.clock.day,
                expiresAtLoopEnd: true,
                payload: p([heroDeath()]),
              },
            }),
          ]);
    }
    case '遗言':
      return p([
        e('death', self, { kind: 'death' }),
        e('next-loop', none, {
          kind: 'schedule',
          task: {
            sourceId: 'last-words',
            due: 'phase:loop_start:enter',
            loop: state.clock.loop + 1,
            day: 1,
            expiresAtLoopEnd: false,
            payload: p(
              ['protagonistA', 'protagonistB', 'protagonistC'].map((seat) =>
                e(`hope:${seat}`, none, {
                  kind: 'grant-card',
                  cardKind: 'hope+1',
                  seat: seat as never,
                }),
              ),
            ),
          },
        }),
      ]);
    case '次元歪曲':
      return {
        segments: [
          { id: 'optional-world', optional: true, effects: [world()] },
          ...p(
            [token('first', any, 'anxiety', 2)],
            [
              token(
                'second',
                { kind: 'characters', filter: { not: ['$target:first'] } },
                'goodwill',
                2,
              ),
            ],
          ).segments,
        ],
      };
    case '次元断层':
      return {
        segments: [
          { id: 'optional-world', optional: true, effects: [world()] },
          {
            id: 'death',
            effects: [
              {
                ...heroDeath(),
                condition: {
                  kind: 'compare',
                  left: { kind: 'token-kinds', target: culprit },
                  op: '>=',
                  right: 3,
                },
              },
            ],
          },
        ],
      };
    case '遗失物':
      return {
        segments: [
          { id: 'intrigue', effects: [token('token', neighbours, 'intrigue', 1)] },
          {
            id: 'move',
            choices: [{ key: 'destination', prompt: '选择移动目的地', values: areas }],
            effects: [
              e('move', self, {
                kind: 'move-character',
                destination: '$choice:destination' as never,
              }),
            ],
          },
        ],
      };
    case '奇点': {
      if (state.ex % 2 === 0) return calledByAi || prior.length ? p([world()]) : p([heroDeath()]);
      return p([
        {
          ...heroDeath(),
          condition: {
            kind: 'compare',
            left: { kind: 'area-intrigue', area: initial as never },
            op: '>=',
            right: 1,
          },
        },
      ]);
    }
    case '代行者':
      return {
        segments: [
          {
            id: 'proxy',
            choices: [
              {
                key: 'seat',
                prompt: '选择主人公',
                values: ['protagonistA', 'protagonistB', 'protagonistC'],
              },
            ],
            effects: [e('victim', any, { kind: 'death' }, { chooser: '$choice:seat' as never })],
          },
        ],
      };
    case '骤变':
      return p([
        {
          ...heroDeath(),
          condition: {
            kind: 'compare',
            left: { kind: 'area-intrigue', area: initial as never },
            op: '>=',
            right: 2,
          },
        },
        {
          ...token('add', { kind: 'area', id: initial as never }, 'intrigue', 2),
          condition: {
            kind: 'compare',
            left: { kind: 'area-intrigue', area: initial as never },
            op: '<=',
            right: 1,
          },
        },
      ]);
    case '封锁':
      return p([
        e('blockade', none, {
          kind: 'set-record',
          key: `blockade:${area}:${state.clock.day + 2}`,
          value: true,
        }),
      ]);
    case '可疑信件':
      return {
        segments: [
          {
            id: 'move',
            effects: [e('letter', neighbours, { kind: 'move-character', lockNextDay: true })],
          },
        ],
      };
    case '孤守': {
      const targets = Object.values(state.characters).filter(
        (c) => c.id !== culprit && c.alive && c.presence === 'board' && c.area === area,
      );
      return {
        segments: [
          {
            id: 'all-move',
            choices: targets.map((c) => ({
              key: `destination-${c.id}`,
              prompt: `选择${c.name}的目的地`,
              values: areas.filter((a) => a !== area),
            })),
            effects: targets.map((c) =>
              e(
                c.id,
                { kind: 'character', id: c.id },
                { kind: 'move-character', destination: `$choice:destination-${c.id}` as never },
              ),
            ),
          },
        ],
      };
    }
    default:
      throw new Error(`INCIDENT_HANDLER_MISSING:${definition.name}`);
  }
}
