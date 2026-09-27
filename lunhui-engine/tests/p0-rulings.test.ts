import { describe, expect, it } from 'vitest';
import { createCatalog, firstStepsScenario } from '../packages/content/src/index.js';
import {
  createGame,
  Engine,
  evaluatePersistent,
  selectCandidates,
  validateNewGame,
  type NewGameInput,
} from '../packages/engine/src/index.js';
import { nativeOptional } from '../packages/engine/src/native-rules.js';
import { incidentProgram } from '../packages/engine/src/native-incidents.js';
import { atNode, character, choose, fixture } from './fixtures.js';

function ahr(names: string[]) {
  const catalog = createCatalog();
  const module = catalog.modules.another_horizon_revised!;
  const rules = names.map(
    (name) =>
      Object.values(catalog.rules!).find((r) => module.rules.includes(r.id) && r.name === name)!,
  );
  const pairs: Array<[string, string | undefined]> = [];
  const counts = new Map<string, number>();
  for (const rule of rules) {
    const variable = rule.roles.filter((r) => ['表', '里'].includes(r.count));
    if (variable.length)
      pairs.push([
        variable.find((r) => r.count === '表')?.identityId ?? 'civilian',
        variable.find((r) => r.count === '里')?.identityId ?? 'civilian',
      ]);
    for (const role of rule.roles.filter((r) => !['表', '里'].includes(r.count)))
      counts.set(role.identityId, (counts.get(role.identityId) ?? 0) + Number(role.count));
  }
  for (const [identity, count] of counts)
    for (
      let i = 0;
      i <
      Math.min(
        count,
        module.identityLimits?.[identity] ?? catalog.identities[identity]?.max ?? Infinity,
      );
      i++
    )
      pairs.push([identity, undefined]);
  const definitions = [
    'doctor',
    'male_student',
    'female_student',
    'police',
    'shrine_maiden',
    'soldier',
    'teacher',
    'idol',
  ];
  const input: NewGameInput = {
    script: {
      id: 'ahr-faq',
      moduleId: module.id,
      ruleIds: rules.map((r) => r.id),
      loops: 3,
      daysPerLoop: 4,
      finalShowdown: true,
      incidents: [],
      options: {},
    },
    characters: pairs.map(([identity, reverseIdentity], index) => {
      const definition = catalog.characters[definitions[index]!]!;
      return character(`c${index}`, identity, {
        definitionId: definition.id,
        area: definition.initialAreas[0]!,
        initialArea: definition.initialAreas[0]!,
        reverseIdentity,
      });
    }),
  };
  return { catalog, input };
}

describe('P0处理意见及LL/AHR纸本FAQ', () => {
  it('怪物们的阴谋读取最终有效特性：纸老虎和绝望有效，希望优先压制', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'haunted_stage_again';
    const rule = Object.values(catalog.rules!).find((r) => r.name === '怪物们的阴谋')!;
    state.script.ruleIds = [rule.id];
    state.characters = { tiger: character('tiger', 'paper_tiger') };
    const areas = () => {
      const source = nativeOptional('mastermind_ability', state, catalog).find(
        (s) => s.name === rule.name,
      )!;
      return selectCandidates(
        source.program.segments[0]!.effects[0]!.target,
        state,
        evaluatePersistent(state, catalog),
        catalog,
      );
    };
    expect(areas()).toEqual([]);
    state.characters.tiger!.counters.anxiety = 2;
    expect(areas()).toEqual(['hospital']);
    state.characters.tiger!.counters.hope = 1;
    expect(areas()).toEqual([]);
    state.characters.tiger!.counters.hope = 0;
    state.characters.tiger!.configuredIdentity = 'civilian';
    state.characters.tiger!.counters.despair = 1;
    expect(areas()).toEqual(['hospital']);
    state.characters.tiger!.counters.hope = 1;
    expect(areas()).toEqual([]);
  });

  it.each([false, true])(
    '仅牺牲者丧尸也有移动入口；与实体丧尸共享每日限次（实体=%s）',
    (hasCard) => {
      const { state, catalog } = fixture();
      state.script.moduleId = 'haunted_stage_again';
      state.script.ruleIds = ['hsa.y.ancient_tomb'];
      state.characters = hasCard
        ? { corpse: character('corpse', 'civilian', { alive: false }) }
        : {};
      state.board.hospital.intrigue = 1;
      state.board.shrine.intrigue = 3;
      atNode(state, 'turn_end', 'turn_end.optional');
      const engine = new Engine(state, catalog);
      engine.start();
      expect(
        engine.waiting?.options.filter((o) => o.id.startsWith('zombie.move-corpse')),
      ).toHaveLength(1);
      expect(choose(engine, ['zombie.move-corpse']).status).toBe('accepted');
      expect(choose(engine, ['victim:hospital:0']).status).toBe('accepted');
      const restored = Engine.restore(engine.serialize(), catalog);
      for (const current of [engine, restored]) {
        expect(choose(current, ['shrine']).status).toBe('accepted');
        expect(current.state.board.hospital.intrigue).toBe(0);
        expect(current.state.board.shrine.intrigue).toBe(3);
        expect(current.waiting?.options.some((o) => o.id.startsWith('zombie.move-corpse'))).toBe(
          false,
        );
      }
      expect(restored.serialize()).toBe(engine.serialize());
      const tomorrow = engine.state;
      tomorrow.status = 'ready';
      tomorrow.clock.day++;
      tomorrow.clock.phaseInstance++;
      atNode(tomorrow, 'turn_end', 'turn_end.optional');
      const nextDay = new Engine(tomorrow, catalog);
      nextDay.start();
      expect(nextDay.waiting?.options.some((o) => o.id === 'zombie.move-corpse')).toBe(true);
    },
  );

  it('普通牺牲者不是丧尸，不能出现丧尸移动入口', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'haunted_stage_again';
    state.script.ruleIds = [];
    state.board.hospital.intrigue = 1;
    atNode(state, 'turn_end', 'turn_end.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.waiting?.options.some((o) => o.id === 'zombie.move-corpse')).toBe(false);
  });

  it('成人能力无合法对象不阻止妹妹发动、沟通和完成', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'last_liar';
    state.script.ruleIds = [];
    state.characters = {
      sister: character('sister', 'civilian', { definitionId: 'sister' }),
      appraiser: character('appraiser', 'civilian', { definitionId: 'appraiser' }),
    };
    state.characters.sister!.counters.goodwill = 5;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['sister.goodwill1@sister']).status).toBe('accepted');
    expect(choose(engine, ['appraiser.goodwill1@appraiser']).status).toBe('accepted');
    for (let i = 0; i < 10 && engine.waiting?.kind !== 'ability'; i++) choose(engine);
    expect(engine.state.characters.sister!.marks.communicated).toBe(true);
    expect(engine.state.characters.appraiser!.marks.communicated).toBe(false);
    expect(Object.values(engine.state.records.sourceOutcomes)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          sourceId: 'sister.goodwill1@sister',
          started: true,
          completed: true,
        }),
      ]),
    );
  });

  it.each(['灭绝之火', '奇点'])('AI调用%s不触发首次发生条件，也不写发生记录', (name) => {
    const { state, catalog } = fixture();
    state.script.moduleId = name === '奇点' ? 'another_horizon_revised' : 'weird_mythology';
    state.script.ruleIds = [];
    state.characters = { ai: character('ai', 'civilian', { definitionId: 'ai', area: 'city' }) };
    state.characters.ai!.counters.goodwill = 3;
    const incident = Object.values(catalog.incidents).find((i) => i.name === name)!;
    state.script.incidents = [
      { entryId: 'future', day: 2, incidentId: incident.id, publicName: name, culpritIds: ['ai'] },
    ];
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['ai.goodwill1@ai']).status).toBe('accepted');
    expect(choose(engine, [incident.id]).status).toBe('accepted');
    expect(engine.state.characters.ai!.alive).toBe(true);
    expect(engine.state.records.protagonistsDead).toBe(false);
    expect(engine.state.records.incidentHistory).toEqual([]);
    expect(engine.state.records.worldMovedToday).toBe(name === '奇点');
    const next = engine.state;
    next.status = 'ready';
    next.clock.day = 2;
    next.script.loops = 1;
    next.clock.phaseInstance++;
    next.characters.ai!.counters.anxiety = 3;
    atNode(next, 'incident', 'incident.judge');
    const scheduled = new Engine(next, catalog);
    scheduled.start();
    expect(scheduled.state.records.incidentHistory).toHaveLength(1);
    expect(scheduled.state.records.protagonistsDead).toBe(true);
  });

  it('AI在事件真实发生之后调用灭绝之火仍不能满足首次发生', () => {
    const { state, catalog } = fixture();
    const definition = Object.values(catalog.incidents).find((i) => i.name === '灭绝之火')!;
    state.records.incidentHistory.push({
      sequence: 0,
      entryId: 'fire',
      incidentId: definition.id,
      publicName: definition.name,
      culpritIds: ['doctor'],
      loop: 1,
      day: 1,
      completed: true,
      changed: true,
      calledByAi: false,
    });
    expect(
      incidentProgram(definition, state, catalog, 'doctor', 'fire', true).segments.flatMap(
        (s) => s.effects,
      ),
    ).toEqual([]);
  });

  it('公开商议限制、特殊规则和事件公开说明，隐藏真实事件与非公开说明，存档后保留', () => {
    const { catalog } = fixture();
    const input = firstStepsScenario();
    input.script.id = 'private-title';
    input.script.discussionRestriction = '仅轮回开始时可商议';
    input.script.specialRules = ['公开特殊说明'];
    input.script.incidents[0]!.publicName = '伪装的公开事件';
    input.script.incidents[0]!.publicInfo = '公开事件备注';
    input.script.incidents[0]!.privateInfo = '仅剧作家可知的备注';
    const engine = new Engine(createGame(input, catalog), catalog);
    const publicScript = engine.view('protagonistA').publicScript;
    expect(publicScript).toMatchObject({
      discussionRestriction: '仅轮回开始时可商议',
      specialRules: ['公开特殊说明'],
    });
    expect(publicScript.incidents[0]).toEqual({
      day: 2,
      name: '伪装的公开事件',
      publicInfo: '公开事件备注',
    });
    expect(JSON.stringify(publicScript)).not.toContain('private-title');
    expect(JSON.stringify(publicScript)).not.toContain('仅剧作家可知');
    expect(publicScript.incidents[0]).not.toHaveProperty('incidentId');
    publicScript.specialRules.push('外部修改');
    const restored = Engine.restore(engine.serialize(), catalog);
    expect(restored.view('protagonistA').publicScript.specialRules).toEqual(['公开特殊说明']);
    expect(restored.state.script.incidents[0]!.privateInfo).toBe('仅剧作家可知的备注');
    const legacy = fixture();
    legacy.state.script.moduleId = 'last_liar';
    expect(
      Engine.restore(new Engine(legacy.state, legacy.catalog).serialize(), legacy.catalog).view(
        'protagonistA',
      ).publicScript.discussionRestriction,
    ).toBe('轮回中禁止商议');
  });

  it('AHR表里身份不占身份上限，模仿犯完整复制表里身份', () => {
    const { input, catalog } = ahr(['鹅妈妈神秘故事', '难以言喻的怪物', '超越世界线']);
    expect(input.characters.filter((c) => c.configuredIdentity === 'gossip')).toHaveLength(2);
    input.characters.push(
      character('copy', 'gossip', {
        definitionId: 'copycat',
        area: 'city',
        initialArea: 'city',
        reverseIdentity: 'obstinate',
      }),
    );
    expect(validateNewGame(input, catalog)).toEqual([]);
    input.characters.at(-1)!.reverseIdentity = 'mastermind';
    expect(validateNewGame(input, catalog)).toContain('COPYCAT_WITHOUT_ORIGINAL:copy');
  });

  it.each(['gossip', 'obstinate'])('局外人不能取得表里组任一侧已有的身份：%s', (identity) => {
    const { input, catalog } = ahr(['鹅妈妈神秘故事', '难以言喻的怪物', '超越世界线']);
    input.characters.push(
      character('outside', identity, {
        definitionId: 'outsider',
        area: 'school',
        initialArea: 'school',
      }),
    );
    expect(validateNewGame(input, catalog)).toContain('INVALID_OUTSIDER_IDENTITY:outside');
  });

  it('局外人不能取得表里组；可取得未出现的固定身份，并被模仿犯复制', () => {
    const { input, catalog } = ahr(['鹅妈妈神秘故事', '难以言喻的怪物', '超越世界线']);
    const outsider = character('outside', 'causal_fragment', {
      definitionId: 'outsider',
      area: 'school',
      initialArea: 'school',
    });
    input.characters.push(
      outsider,
      character('copy', 'causal_fragment', {
        definitionId: 'copycat',
        area: 'city',
        initialArea: 'city',
      }),
    );
    expect(validateNewGame(input, catalog)).toEqual([]);
    outsider.reverseIdentity = 'serial_killer';
    expect(validateNewGame(input, catalog)).toContain('INVALID_OUTSIDER_IDENTITY:outside');
  });

  it('AHR可给AI分配平民/杀人狂，给妹妹分配关键人物/主谋', () => {
    for (const [rule, definition] of [
      ['傀儡之线', 'ai'],
      ['化身博士', 'sister'],
    ]) {
      const { input, catalog } = ahr(['鹅妈妈神秘故事', rule!, '超越世界线']);
      const card = input.characters.find((c) => c.reverseIdentity)!;
      card.definitionId = definition!;
      card.initialArea = catalog.characters[definition!]!.initialAreas[0]!;
      card.area = card.initialArea;
      expect(validateNewGame(input, catalog)).toEqual([]);
    }
  });

  it('AHR不能把两个规则的表里身份拆散重组', () => {
    const { input, catalog } = ahr(['鹅妈妈神秘故事', '化身博士', '恶魔吹着笛子来']);
    expect(validateNewGame(input, catalog)).toEqual([]);
    const cards = input.characters.filter((c) => c.reverseIdentity);
    [cards[0]!.reverseIdentity, cards[1]!.reverseIdentity] = [
      cards[1]!.reverseIdentity,
      cards[0]!.reverseIdentity,
    ];
    expect(validateNewGame(input, catalog)).toContain('UNALLOCATED_VARIABLE_IDENTITY');
  });
  it('AHR模仿犯在里世界公开所有当前同身份角色，包括普通主谋', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'another_horizon_revised';
    state.script.ruleIds = [];
    state.clock.loop = 2;
    state.ex = 1;
    state.characters = {
      copy: character('copy', 'key_person', {
        definitionId: 'copycat',
        reverseIdentity: 'mastermind',
      }),
      original: character('original', 'key_person', { reverseIdentity: 'mastermind' }),
      ordinary: character('ordinary', 'mastermind', { definitionId: 'police' }),
    };
    state.characters.copy!.counters.anxiety = 3;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['copycat.goodwill1@copy']).status).toBe('accepted');
    const announcement = engine.state.publicLog.find((log) =>
      log.text.startsWith('与copy身份相同的角色：'),
    )!.text;
    expect(announcement).toContain('original');
    expect(announcement).toContain('ordinary');
  });
  it('LL局外人允许取得捏造的秘密条件追加身份，但不能取得规则自带身份', () => {
    const catalog = createCatalog();
    const module = catalog.modules.last_liar!;
    const input: NewGameInput = {
      script: {
        id: 'll-faq-q8',
        moduleId: module.id,
        ruleIds: ['巨大定时炸弹Z', '超越世界线', '捏造的秘密'].map(
          (name) =>
            Object.values(catalog.rules!).find(
              (rule) => module.rules.includes(rule.id) && rule.name === name,
            )!.id,
        ),
        loops: 3,
        daysPerLoop: 4,
        finalShowdown: true,
        incidents: [],
        options: { fabricatedSecretIdentity: 'killer' },
      },
      characters: [
        character('master', 'mastermind'),
        character('witch', 'witch', {
          definitionId: 'male_student',
          area: 'school',
          initialArea: 'school',
        }),
        character('gossip', 'gossip', {
          definitionId: 'female_student',
          area: 'school',
          initialArea: 'school',
        }),
        character('killer', 'killer', {
          definitionId: 'police',
          area: 'city',
          initialArea: 'city',
        }),
        character('outside', 'killer', {
          definitionId: 'outsider',
          area: 'school',
          initialArea: 'school',
        }),
      ],
    };
    expect(validateNewGame(input, catalog)).toEqual([]);
    input.characters.at(-1)!.configuredIdentity = 'mastermind';
    expect(validateNewGame(input, catalog)).toContain('INVALID_OUTSIDER_IDENTITY:outside');
  });
});
