import { describe, expect, it } from 'vitest';
import { Engine, commitBatch, evaluatePersistent } from '../packages/engine/src/index.js';
import { atNode, character, choose, fixture } from './fixtures.js';
import { judgeScheduledIncident } from '../packages/engine/src/incidents.js';
import { legalMoveDestinations } from '../packages/engine/src/resolution.js';

describe('附录能力接入统一来源生命周期', () => {
  it('学者清空所有实际指示物，不使用人为上限，也不清除LL标志', () => {
    const { state, catalog } = fixture();
    state.characters = { scholar: character('scholar', 'civilian', { definitionId: 'scholar' }) };
    state.characters.scholar!.counters = {
      goodwill: 3,
      anxiety: 2000000,
      intrigue: 2,
      hope: 1,
      despair: 2,
      guard: 1,
    };
    state.characters.scholar!.marks.communicated = true;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['scholar.goodwill1@scholar']).status).toBe('accepted');
    expect(Object.values(engine.state.characters.scholar!.counters)).toEqual([0, 0, 0, 0, 0, 0]);
    expect(engine.state.characters.scholar!.marks.communicated).toBe(true);
  });
  it('巫女的神社能力与大小姐的学校/都市能力检查使用地点', () => {
    const { state, catalog } = fixture();
    state.characters = {
      maiden: character('maiden', 'civilian', { definitionId: 'shrine_maiden' }),
      rich: character('rich', 'civilian', { definitionId: 'rich_girl' }),
    };
    for (const c of Object.values(state.characters)) c.counters.goodwill = 3;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.waiting!.options.map((o) => o.id)).toEqual(['finish']);
  });
  it('AI调用自杀效果，不登记发生、不增加MC的EX', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'mystery_circle';
    state.characters = {
      ai: character('ai', 'mastermind', { definitionId: 'ai', area: 'city', initialArea: 'city' }),
    };
    state.characters.ai!.counters.goodwill = 3;
    state.characters.ai!.counters.hope = 1;
    state.script.incidents = [
      { entryId: 'event', day: 1, incidentId: 'suicide', publicName: '自杀', culpritIds: ['ai'] },
    ];
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['ai.goodwill1@ai']).status).toBe('accepted');
    expect(choose(engine, ['suicide']).status).toBe('accepted');
    expect(engine.state.characters.ai!.alive).toBe(false);
    expect(engine.state.records.incidentHistory).toEqual([]);
    expect(engine.state.ex).toBe(0);
    expect(
      Object.values(engine.state.records.sourceOutcomes).some(
        (o) => o.sourceId === 'ai.goodwill1@ai' && o.completed,
      ),
    ).toBe(true);
  });
  it('妹妹调用成人能力无视阈值和无视友好，但仍走子来源', () => {
    const { state, catalog } = fixture();
    state.characters = {
      sister: character('sister', 'civilian', { definitionId: 'sister' }),
      doctor: character('doctor', 'cultist'),
    };
    state.characters.sister!.counters.goodwill = 5;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['sister.goodwill1@sister']).status).toBe('accepted');
    expect(choose(engine, ['doctor.goodwill1@doctor']).status).toBe('accepted');
    expect(choose(engine, ['add']).status).toBe('accepted');
    expect(choose(engine, ['sister']).status).toBe('accepted');
    expect(engine.state.characters.sister!.counters.anxiety).toBe(1);
    const outcomes = Object.values(engine.state.records.sourceOutcomes);
    expect(outcomes.filter((o) => o.completed).map((o) => o.sourceId)).toEqual(
      expect.arrayContaining(['sister.goodwill1@sister', 'doctor.goodwill1@doctor']),
    );
  });
  it('死亡状态的临时工在次日带出替代卡；事件保留配置并汇总双方', () => {
    const { state, catalog } = fixture();
    state.characters = {
      worker: character('worker', 'obstinate', {
        definitionId: 'temp_worker',
        alive: false,
        area: 'city',
        initialArea: 'city',
      }),
    };
    state.script.incidents = [
      {
        entryId: 'event',
        day: 1,
        incidentId: 'suicide',
        publicName: '自杀',
        culpritIds: ['worker'],
      },
    ];
    atNode(state, 'turn_start', 'turn_start.reset');
    const engine = new Engine(state, catalog);
    engine.start();
    const next = engine.state;
    expect(next.characters['worker-replacement']!.configuredIdentity).toBe('obstinate');
    expect(judgeScheduledIncident(next, catalog).culpritIds).toEqual(['worker-replacement']);
    next.characters.worker!.alive = true;
    next.characters.worker!.counters.anxiety = 1;
    expect(judgeScheduledIncident(next, catalog).culpritIds.sort()).toEqual([
      'worker',
      'worker-replacement',
    ]);
    expect(evaluatePersistent(next, catalog).characters.worker!.identity).toBe('civilian');
  });
  it('HSA日末：原地缚灵只附身，原附身尝试死亡后才落地', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'haunted_stage_again';
    state.characters = { a: character('a'), b: character('b', 'immortal', { area: 'city' }) };
    state.curses = [
      { id: 'attach', kind: 'area', targetId: 'hospital' },
      { id: 'drop', kind: 'character', targetId: 'b' },
    ];
    atNode(state, 'turn_end', 'turn_end.module');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['a']).status).toBe('accepted');
    expect(engine.state.characters.a!.alive).toBe(true);
    expect(engine.state.characters.b!.alive).toBe(true);
    expect(engine.state.curses).toEqual([
      { id: 'attach', kind: 'character', targetId: 'a' },
      { id: 'drop', kind: 'area', targetId: 'city' },
    ]);
  });
  it('封锁包含发生当天，三天后自动失效', () => {
    const { state, catalog } = fixture();
    state.records.revealedFacts.push('flag:blockade:hospital:3');
    expect(legalMoveDestinations(state, catalog, 'doctor')).toEqual(['hospital']);
    state.clock.day = 4;
    expect(legalMoveDestinations(state, catalog, 'doctor')).toHaveLength(4);
  });
  it('可疑信件仅在实际移动后施加本轮次日禁行', () => {
    const { state, catalog } = fixture();
    const intent = {
      id: 'letter',
      sourceInstanceId: 'letter',
      effectId: 'letter',
      targetId: 'doctor',
      operation: { kind: 'move-character', destination: 'city', lockNextDay: true },
    } as const;
    const moved = commitBatch(state, catalog, [intent]).state;
    moved.clock.day = 2;
    expect(legalMoveDestinations(moved, catalog, 'doctor')).toEqual(['city']);
    moved.clock.day = 3;
    expect(legalMoveDestinations(moved, catalog, 'doctor')).toHaveLength(4);
  });
});
