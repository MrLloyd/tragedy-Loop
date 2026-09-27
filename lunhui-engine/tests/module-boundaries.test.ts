import { describe, expect, it } from 'vitest';
import {
  Engine,
  commitBatch,
  placeAction,
  resolveActions,
  selectCandidates,
  evaluatePersistent,
  type EffectIntent,
} from '../packages/engine/src/index.js';
import { firstStepsScenario } from '../packages/content/src/index.js';
import { validateNewGame } from '../packages/engine/src/state.js';
import { atNode, character, choose, fixture, source } from './fixtures.js';

describe('跨模组边界', () => {
  it('御神木和心理医生涉及同一枚不安：该枚消失，交换枚举顺序不复制', () => {
    const { state, catalog } = fixture();
    state.characters = {
      tree: character('tree', 'cultist', { definitionId: 'sacred_tree' }),
      other: character('other'),
    };
    state.characters.tree!.counters.anxiety = 1;
    const intents: EffectIntent[] = [
      {
        id: 'tree',
        sourceInstanceId: 'tree',
        effectId: 'move',
        targetId: 'tree',
        operation: {
          kind: 'move-counter',
          counter: 'anxiety',
          amount: 1,
          to: { kind: 'character', id: 'other' },
          sacredTree: true,
        },
      },
      {
        id: 'calm',
        sourceInstanceId: 'psychologist',
        effectId: 'remove',
        targetId: 'tree',
        operation: { kind: 'counter', counter: 'anxiety', amount: -1 },
      },
    ];
    for (const batch of [intents, [...intents].reverse()]) {
      const next = commitBatch(state, catalog, batch).state;
      expect(next.characters.tree!.counters.anxiety).toBe(0);
      expect(next.characters.other!.counters.anxiety).toBe(0);
    }
  });
  it('HSA牺牲者可被异界人复活：移除密谋但不创造角色卡', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'haunted_stage_again';
    state.characters = {
      alien: character('alien', 'civilian', { definitionId: 'alien', area: 'shrine' }),
    };
    state.characters.alien!.counters.goodwill = 5;
    state.board.shrine.intrigue = 2;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['alien.goodwill2@alien']).status).toBe('accepted');
    expect(choose(engine, ['victim:shrine:0']).status).toBe('accepted');
    expect(engine.state.board.shrine.intrigue).toBe(1);
    expect(Object.keys(engine.state.characters)).toEqual(['alien']);
  });
  it('普通角色查询不纳入牺牲者，古墓尸体查询纳入丧尸牺牲者', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'haunted_stage_again';
    state.script.ruleIds = ['hsa.y.ancient_tomb'];
    state.board.city.intrigue = 2;
    const effective = evaluatePersistent(state, catalog);
    expect(
      selectCandidates({ kind: 'characters' }, state, effective, catalog).some((id) =>
        id.startsWith('victim:'),
      ),
    ).toBe(false);
    expect(
      selectCandidates(
        { kind: 'characters', filter: { alive: false, identity: 'zombie' } },
        state,
        effective,
        catalog,
      ),
    ).toEqual(['victim:city:0', 'victim:city:1']);
  });
  it('仙人移动后的复活范围读取新区域，不固定为能力开始位置', () => {
    const { state, catalog } = fixture();
    state.characters = {
      hermit: character('hermit', 'civilian', { definitionId: 'hermit' }),
      corpse: character('corpse', 'civilian', { area: 'city', alive: false }),
    };
    state.characters.hermit!.counters.goodwill = 5;
    state.script.options['hermitX:hermit'] = 4;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['hermit.goodwill1@hermit']).status).toBe('accepted');
    expect(choose(engine, ['city']).status).toBe('accepted');
    expect(choose(engine, ['corpse']).status).toBe('accepted');
    expect(engine.state.characters.corpse!.alive).toBe(true);
    expect(engine.state.characters.corpse!.counters.goodwill).toBe(4);
  });
  it('银色子弹在教主两次文本均完成后结束，MC不增加EX', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'mystery_circle';
    state.characters = { cult: character('cult', 'civilian', { definitionId: 'cult_leader' }) };
    state.characters.cult!.counters.anxiety = 3;
    state.script.incidents = [
      {
        entryId: 'silver',
        day: 1,
        incidentId: 'silver_bullet',
        publicName: '银色子弹',
        culpritIds: ['cult'],
      },
    ];
    atNode(state, 'incident', 'incident.judge');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.records.incidentHistory[0]!.completed).toBe(true);
    expect(
      engine.state.records.sourceOutcomes[Object.keys(engine.state.records.sourceOutcomes)[0]!]!
        .completed,
    ).toBe(true);
    expect(engine.state.ex).toBe(0);
    expect(engine.state.result?.reason).toBe('protagonists-won-loop');
  });
  it('黑猫替换事件仍完成，并触发愚者；银色子弹不再结束轮回', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'mystery_circle';
    state.characters = { cat: character('cat', 'fool', { definitionId: 'black_cat' }) };
    state.characters.cat!.counters.anxiety = 3;
    state.script.incidents = [
      {
        entryId: 'silver',
        day: 1,
        incidentId: 'silver_bullet',
        publicName: '银色子弹',
        culpritIds: ['cat'],
      },
    ];
    atNode(state, 'incident', 'incident.judge');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.records.incidentHistory[0]!.completed).toBe(true);
    expect(engine.state.characters.cat!.counters.anxiety).toBe(0);
    expect(engine.state.ex).toBe(1);
    expect(engine.state.records.endRequests).toEqual([]);
  });
  it('LL特殊胜利成立后仍允许必须后续等待选择，结算完才公开结果', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'last_liar';
    state.script.ruleIds = ['ll.x.true_monster'];
    state.traitors = ['protagonistC'];
    state.secretLetters = { protagonistC: 'A' };
    state.characters = {
      preacher: character('preacher', 'preacher'),
      recipient: character('recipient'),
    };
    for (let i = 0; i < 4; i++)
      state.characters[`old${i}`] = character(`old${i}`, 'civilian', {
        presence: 'removed',
        marks: { died: true, communicated: false },
      });
    catalog.sources.kill = source('kill', [
      {
        id: 'death',
        effects: [
          {
            id: 'victim',
            target: { kind: 'character', id: 'preacher' },
            operation: { kind: 'death' },
          },
        ],
      },
    ]);
    atNode(state, 'turn_end', 'turn_end.module');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.result?.reason).toBe('ll.special-victory-a');
    expect(engine.state.status).toBe('waiting');
    expect(engine.view('protagonistC').result).toBeNull();
    expect(choose(engine, ['recipient']).status).toBe('accepted');
    expect(engine.state.status).toBe('finished');
    expect(engine.view('protagonistC').result?.winners).toEqual(['protagonistC']);
    expect(engine.state.characters.recipient!.counters.despair).toBe(1);
  });
  it('AHR最终决战必须回答表里两套身份', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'another_horizon_revised';
    state.characters = { a: character('a', 'key_person', { reverseIdentity: 'mastermind' }) };
    atNode(state, 'final_showdown', 'final_showdown.prepare');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['a']).status).toBe('accepted');
    expect(choose(engine, ['key_person']).status).toBe('accepted');
    expect(engine.state.result).toBeNull();
    expect(choose(engine, ['mastermind']).status).toBe('accepted');
    expect(engine.state.result?.reason).toBe('final-showdown-cleared');
  });
  it('剧作家可以在First Steps剧本中开放最终决战', () => {
    const { state, catalog } = fixture();
    const input = firstStepsScenario();
    input.script.finalShowdown = true;
    expect(validateNewGame(input, catalog)).toEqual([]);

    state.script.finalShowdown = true;
    state.clock.loop = state.script.loops;
    state.records.loopFailed = true;
    atNode(state, 'loop_end', 'loop_end.evaluate');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.clock.phase).toBe('final_showdown');
    expect(engine.waiting?.kind).toBe('targets');
  });
  it('剧作家关闭最终决战时，最终轮回失败后直接获胜', () => {
    const { state, catalog } = fixture();
    state.script.finalShowdown = false;
    state.clock.loop = state.script.loops;
    state.records.loopFailed = true;
    atNode(state, 'loop_end', 'loop_end.evaluate');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.result).toEqual({ winners: ['mastermind'], reason: 'all-loops-failed' });
  });
  it('关闭最终决战时，怪异神话EX跳转也不进入决战', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'weird_mythology';
    state.script.finalShowdown = false;
    state.ex = 4;
    state.records.loopFailed = true;
    atNode(state, 'loop_end', 'loop_end.evaluate');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.result).toEqual({ winners: ['mastermind'], reason: 'all-loops-failed' });
  });
  it('从者跟随明确选择的同时移动对象，忽略自己的移动牌', () => {
    const { state, catalog } = fixture();
    state.characters = {
      servant: character('servant', 'civilian', { definitionId: 'servant' }),
      big: character('big', 'civilian', { definitionId: 'big_shot' }),
      rich: character('rich', 'civilian', { definitionId: 'rich_girl' }),
    };
    const add = (seat: 'mastermind' | 'protagonistA' | 'protagonistB', kind: string, id: string) =>
      placeAction(state, catalog, seat, state.cards[seat].find((c) => c.kind === kind)!.id, {
        kind: 'character',
        id,
      });
    add('mastermind', 'move-diagonal', 'servant');
    add('protagonistA', 'move-horizontal', 'big');
    add('protagonistB', 'move-vertical', 'rich');
    const next = resolveActions(state, catalog, { followers: { servant: 'rich' } }).state;
    expect(next.characters.servant!.area).toBe('city');
    expect(next.characters.big!.area).toBe('shrine');
  });
  it('时间旅者仅无视自身禁止友好，不把版图牌扩散给同区普通角色', () => {
    const { state, catalog } = fixture();
    state.characters.doctor!.configuredIdentity = 'time_traveler';
    placeAction(
      state,
      catalog,
      'mastermind',
      state.cards.mastermind.find((c) => c.kind === 'forbid-goodwill')!.id,
      { kind: 'character', id: 'doctor' },
    );
    placeAction(
      state,
      catalog,
      'protagonistA',
      state.cards.protagonistA.find((c) => c.kind === 'goodwill+1')!.id,
      { kind: 'character', id: 'doctor' },
    );
    expect(resolveActions(state, catalog).state.characters.doctor!.counters.goodwill).toBe(1);
  });
  it('存档恢复拒绝计数损坏和内容指纹变化', () => {
    const { state, catalog } = fixture();
    const engine = new Engine(state, catalog);
    engine.start();
    const save = JSON.parse(engine.serialize());
    save.state.characters.doctor.counters.anxiety = -1;
    expect(() => Engine.restore(JSON.stringify(save), catalog)).toThrow('INVALID_CHECKPOINT');
    const original = engine.serialize();
    catalog.sources['killer.kill-key']!.name = 'changed';
    expect(() => Engine.restore(original, catalog)).toThrow('CONTENT_FINGERPRINT_MISMATCH');
    expect(engine.serialize()).toBe(original);
  });
  it('剧本不能利用通用豁免跳过身份分配；局外人不能复制所选规则身份', () => {
    const { catalog } = fixture();
    const input = firstStepsScenario();
    input.script.options.identityLimitException = true;
    expect(validateNewGame(input, catalog)).toContain('BLANKET_IDENTITY_LIMIT_EXCEPTION_FORBIDDEN');
    delete input.script.options.identityLimitException;
    input.characters.push(
      character('outsider', 'killer', {
        definitionId: 'outsider',
        area: 'school',
        initialArea: 'school',
      }),
    );
    expect(validateNewGame(input, catalog)).toContain('INVALID_OUTSIDER_IDENTITY:outsider');
  });
});
