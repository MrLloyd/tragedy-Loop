import { describe, it, expect } from 'vitest';
import {
  Engine,
  commitBatch,
  inspectSegment,
  evaluatePersistent,
  type EffectIntent,
} from '../packages/engine/src/index.js';
import { fixture, character, atNode, choose, source } from './fixtures.js';

const death = (id: string, targetId: string): EffectIntent => ({
  id,
  sourceInstanceId: id,
  effectId: id,
  targetId,
  operation: { kind: 'death' },
});

describe('流程图：统一批次和保护', () => {
  it('同一时点双杀人狂互杀，不因先执行者死亡取消效果', () => {
    const { state, catalog } = fixture();
    state.characters = { a: character('a', 'serial_killer'), b: character('b', 'serial_killer') };
    state.script.incidents = [];
    atNode(state, 'turn_end', 'turn_end.module');
    const engine = new Engine(state, catalog);
    engine.start();
    while (engine.waiting?.kind === 'targets') expect(choose(engine).status).toBe('accepted');
    expect(engine.state.characters.a!.alive).toBe(false);
    expect(engine.state.characters.b!.alive).toBe(false);
  });
  it('从者只保护大人物、大小姐或追加对象；替死和直接死亡各留一个请求', () => {
    const { state, catalog } = fixture();
    const servant = character('servant', 'civilian', { definitionId: 'servant' });
    servant.counters.guard = 1;
    state.characters = {
      noble: character('noble', 'civilian', { definitionId: 'big_shot' }),
      servant,
    };
    const result = commitBatch(state, catalog, [death('d1', 'noble'), death('d2', 'servant')]);
    expect(result.result.deathAttempts).toHaveLength(2);
    expect(result.state.characters.noble!.alive).toBe(true);
    expect(result.state.characters.servant!.alive).toBe(false);
    expect(result.state.characters.servant!.counters.guard).toBe(0);
    state.characters.noble!.definitionId = 'doctor';
    expect(commitBatch(state, catalog, [death('d1', 'noble')]).state.characters.noble!.alive).toBe(
      false,
    );
  });
  it('本批新获得主人公保护不会追溯抵挡同批死亡，反序相同', () => {
    const { state, catalog } = fixture();
    const effects: EffectIntent[] = [
      {
        ...death('protection', ''),
        operation: { kind: 'set-protagonist-protection', value: true },
      },
      { ...death('death', ''), operation: { kind: 'protagonists-die' } },
    ];
    expect(commitBatch(state, catalog, effects).state.records.protagonistsDead).toBe(true);
    expect(commitBatch(state, catalog, [...effects].reverse()).state.records.protagonistsDead).toBe(
      true,
    );
  });
  it('目标不足与零枚移除不同；尸体、移除卡不被普通角色选择', () => {
    const { state, catalog } = fixture();
    state.characters = { a: character('a'), b: character('b', 'civilian', { alive: false }) };
    const segment = {
      id: 'pair',
      effects: [
        {
          id: 'e',
          target: { kind: 'characters' as const, count: 2 },
          operation: { kind: 'counter' as const, counter: 'anxiety' as const, amount: -1 },
        },
      ],
    };
    expect(inspectSegment(segment, state, catalog, {})[0]!.status).toBe('no_target');
    segment.effects[0]!.target.count = 1;
    expect(inspectSegment(segment, state, catalog, {})[0]!.status).toBe('has_target');
    expect(state.characters.a!.counters.anxiety).toBe(0);
  });
  it('不死优先护卫，普通模组不登记LL死亡标志', () => {
    const { state, catalog } = fixture();
    const c = character('a', 'immortal');
    c.counters.guard = 1;
    state.characters = { a: c };
    expect(commitBatch(state, catalog, [death('d', 'a')]).state.characters.a!.counters.guard).toBe(
      1,
    );
    c.configuredIdentity = 'civilian';
    c.counters.guard = 0;
    const next = commitBatch(state, catalog, [death('d', 'a')]).state;
    expect(next.characters.a!.alive).toBe(false);
    expect(next.characters.a!.marks.died).toBe(false);
  });
});

describe('流程图：来源完成和中断', () => {
  it('医院事故同时杀死关键人物与主人公，愚者完成后清空不安', () => {
    const { state, catalog } = fixture();
    const fool = character('fool', 'fool');
    fool.counters.anxiety = 3;
    state.characters = { key: character('key', 'key_person'), fool };
    state.script.incidents = [
      {
        entryId: 'hospital-day1',
        day: 1,
        incidentId: 'hospital_accident',
        publicName: '公开名',
        culpritIds: ['fool'],
      },
    ];
    state.board.hospital.intrigue = 2;
    atNode(state, 'incident', 'incident.judge');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.records.previousLoop?.characters.fool!.counters.anxiety).toBe(0);
    expect(engine.state.records.previousLoop?.characters.key!.alive).toBe(false);
    expect(
      Object.values(engine.state.records.sourceOutcomes).find((o) =>
        o.sourceId.startsWith('incident.hospital_accident'),
      )?.completed,
    ).toBe(true);
  });
  it('首步骤导致结束的来源不执行随后，不冒领完成', () => {
    const { state, catalog } = fixture();
    catalog.sources.cut = source('cut', [
      {
        id: 'first',
        effects: [
          {
            id: 'end',
            target: { kind: 'none' },
            operation: { kind: 'fail-loop', reason: 'cut-test' },
          },
        ],
      },
      {
        id: 'second',
        effects: [
          {
            id: 'token',
            target: { kind: 'character', id: 'doctor' },
            operation: { kind: 'counter', counter: 'anxiety', amount: 9 },
          },
        ],
      },
    ]);
    atNode(state, 'turn_end', 'turn_end.module');
    const engine = new Engine(state, catalog);
    engine.start();
    const outcome = Object.values(engine.state.records.sourceOutcomes).find(
      (o) => o.sourceId === 'cut',
    );
    expect(outcome).toMatchObject({ truncated: true, completed: false });
    expect(engine.state.records.previousLoop!.characters.doctor!.counters.anxiety).toBe(0);
  });
  it('阶段入口特殊胜利先更新最终计划资格', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'last_liar';
    state.script.ruleIds = ['ll.y.final_plan', 'll.x.myth_collector'];
    state.traitors = ['protagonistA'];
    state.secretLetters = { protagonistA: 'B' };
    state.characters.doctor!.counters.hope = 1;
    expect(evaluatePersistent(state, catalog).traitors).toEqual([]);
  });
});
