import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import {
  Engine,
  evaluatePersistent,
  orderPersistent,
  type PersistentRuleDefinition,
} from '../packages/engine/src/index.js';
import { atNode, character, fixture } from './fixtures.js';

describe('一般常驻纯派生与资格优先级', () => {
  it('固定种子检验实际与有效计数，重复求值不改写状态', () => {
    const { state, catalog } = fixture();
    state.characters = { a: character('a', 'cultist') };
    fc.assert(
      fc.property(
        fc.tuple(...Array.from({ length: 5 }, () => fc.integer({ min: 0, max: 10000 }))),
        ([goodwill, anxiety, intrigue, hope, despair]) => {
          state.characters.a!.counters = {
            goodwill: goodwill!,
            anxiety: anxiety!,
            intrigue: intrigue!,
            hope: hope!,
            despair: despair!,
            guard: 0,
          };
          const snapshot = JSON.stringify(state);
          const effective = evaluatePersistent(state, catalog);
          expect(effective.characters.a!.counts).toEqual({
            goodwill: goodwill! + hope!,
            anxiety: anxiety! + despair!,
            intrigue: Math.max(0, intrigue! + despair! - hope!),
          });
          expect(evaluatePersistent(state, catalog)).toEqual(effective);
          expect(JSON.stringify(state)).toBe(snapshot);
          expect(
            effective.characters.a!.traits.some((trait) => trait.includes('ignore-goodwill')),
          ).toBe(hope === 0);
        },
      ),
      { seed: 20260925, numRuns: 100 },
    );
  });

  it('BTX病毒随有效不安跨阈值生效并撤销，不永久改写配置身份', () => {
    const { state, catalog } = fixture();
    state.script.ruleIds = ['btx.x.delusion_virus'];
    state.characters = { a: character('a') };
    state.characters.a!.counters.anxiety = 2;
    state.characters.a!.counters.despair = 1;
    expect(evaluatePersistent(state, catalog).characters.a!.identity).toBe('serial_killer');
    state.characters.a!.counters.despair = 0;
    expect(evaluatePersistent(state, catalog).characters.a!.identity).toBe('civilian');
    expect(state.characters.a!.configuredIdentity).toBe('civilian');
  });

  it('AHR世界、表里身份及病毒依实际种类数重新派生', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'another_horizon_revised';
    state.script.ruleIds = ['ahr.x.fantasy_virus'];
    state.characters = { a: character('a', 'gossip', { reverseIdentity: 'civilian' }) };
    state.characters.a!.counters.hope = 1;
    state.ex = 1;
    expect(evaluatePersistent(state, catalog).characters.a!.identity).toBe('civilian');
    state.characters.a!.counters.anxiety = 1;
    expect(evaluatePersistent(state, catalog).characters.a!.identity).toBe('serial_killer');
    state.ex = 2;
    expect(evaluatePersistent(state, catalog).characters.a!.identity).toBe('gossip');
  });

  it('纸老虎追加无视、傀儡转换与希望压制按依赖顺序处理', () => {
    const { state, catalog } = fixture();
    state.script.ruleIds = ['ahr.x.puppet_strings'];
    state.characters = { a: character('a', 'paper_tiger') };
    state.characters.a!.counters.despair = 2;
    expect(evaluatePersistent(state, catalog).characters.a!.traits).toEqual([
      'puppet-ignore-goodwill',
    ]);
    state.characters.a!.counters.hope = 1;
    expect(evaluatePersistent(state, catalog).characters.a!.traits).toEqual([]);
    state.characters.a!.counters.despair = 0;
    expect(evaluatePersistent(state, catalog).characters.a!.traits).toContain('immortal');
  });

  it('怪杰、不安定因子及无面者的获得能力随日期与盘面撤销', () => {
    const { state, catalog } = fixture();
    state.characters = {
      eccentric: character('eccentric', 'eccentric'),
      unstable: character('unstable', 'unstable_factor'),
      faceless: character('faceless', 'faceless'),
    };
    state.clock.day = 3;
    state.board.city.intrigue = 2;
    state.board.school.intrigue = 2;
    state.ex = 2;
    let e = evaluatePersistent(state, catalog);
    expect(e.characters.eccentric!.abilities).toEqual(['gossip', 'mastermind', 'serial_killer']);
    expect(e.characters.unstable!.abilities).toEqual(['gossip', 'key_person']);
    expect(e.characters.faceless!.abilities).toEqual(['deep_one']);
    state.clock.day = 4;
    state.board.city.intrigue = 0;
    state.board.school.intrigue = 0;
    state.ex = 0;
    e = evaluatePersistent(state, catalog);
    expect(e.characters.eccentric!.abilities).toEqual([]);
    expect(e.characters.unstable!.abilities).toEqual([]);
    expect(e.characters.faceless!.abilities).toEqual(['gossip']);
  });

  it('医生特许读取有效友好，不随AHR里世界改读不安；与傀儡资格取并集', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'another_horizon_revised';
    state.ex = 1;
    state.characters = { doctor: character('doctor', 'puppet'), recipient: character('recipient') };
    state.characters.doctor!.counters.goodwill = 2;
    atNode(state, 'mastermind_ability', 'mastermind_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.waiting!.options.map((option) => option.id)).toContain('doctor.goodwill1@doctor');
  });

  it('上位存在剧作家特许在里世界仍只要求一有效友好', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'another_horizon_revised';
    state.ex = 1;
    state.characters = {
      higher: character('higher', 'mastermind', { definitionId: 'higher_being' }),
    };
    state.characters.higher!.counters.goodwill = 1;
    atNode(state, 'mastermind_ability', 'mastermind_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.waiting!.options.map((option) => option.id)).toContain(
      'higher_being.goodwill1@higher',
    );
  });

  it('自定义常驻必须显式声明依赖，拒绝循环和未声明的覆盖', () => {
    const { state, catalog } = fixture();
    const first: PersistentRuleDefinition = {
      id: 'first',
      reference: 'test',
      dependsOn: [],
      condition: { kind: 'always' },
      contributions: [{ kind: 'identity', characterId: 'doctor', value: 'killer' }],
    };
    const second: PersistentRuleDefinition = {
      ...first,
      id: 'second',
      contributions: [{ kind: 'identity', characterId: 'doctor', value: 'civilian' }],
    };
    catalog.persistent = { first, second };
    expect(() => evaluatePersistent(state, catalog)).toThrow('PERSISTENT_CONFLICT');
    second.dependsOn = ['first'];
    expect(evaluatePersistent(state, catalog).characters.doctor!.identity).toBe('civilian');
    first.dependsOn = ['second'];
    expect(() => orderPersistent([first, second])).toThrow('PERSISTENT_CYCLE');
    first.dependsOn = ['missing'];
    expect(() => orderPersistent([first])).toThrow('PERSISTENT_MISSING_DEPENDENCY');
  });
});
