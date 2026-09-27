import { describe, expect, it } from 'vitest';
import { Engine, commitBatch } from '../packages/engine/src/index.js';
import { nativeForced } from '../packages/engine/src/native-rules.js';
import { atNode, character, choose, fixture, source } from './fixtures.js';

describe('流程重构回归', () => {
  it('轮回开始强制后续要求结束时，不开始第1天或询问可选能力', () => {
    const { state, catalog } = fixture();
    state.script.loops = 1;
    state.records.delayed.push({
      id: 'due',
      sourceId: 'due',
      due: 'phase:loop_start:enter',
      loop: 1,
      day: 1,
      expiresAtLoopEnd: false,
      payload: {
        segments: [
          {
            id: 'end',
            effects: [
              {
                id: 'end',
                target: { kind: 'none' },
                operation: { kind: 'end-loop', reason: 'test-due' },
              },
            ],
          },
        ],
      },
    });
    atNode(state, 'loop_start', 'loop_start.reset');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.status).toBe('finished');
    expect(engine.state.result?.reason).toBe('protagonists-won-loop');
    expect(
      engine.state.publicLog.some(
        (entry) => entry.type === 'phase' && entry.text.startsWith('turn_start'),
      ),
    ).toBe(false);
  });

  it('AI巫师调用疯狂杀人令自身死亡后，不再发动普通友好完成触发', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'weird_mythology';
    state.characters = { ai: character('ai', 'wizard', { definitionId: 'ai', area: 'city' }) };
    state.characters.ai!.counters.goodwill = 3;
    state.script.incidents = [
      {
        entryId: 'murder',
        day: 2,
        incidentId: '疯狂杀人',
        publicName: '疯狂杀人',
        culpritIds: ['ai'],
      },
    ];
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['ai.goodwill1@ai']).status).toBe('accepted');
    expect(choose(engine, ['疯狂杀人']).status).toBe('accepted');
    expect(choose(engine, ['ai']).status).toBe('accepted');
    expect(engine.state.characters.ai).toMatchObject({ alive: false, publicIdentity: null });
    expect(engine.state.ex).toBe(0);
  });

  it('死亡触发保留死亡前获得的关键人物能力，不受同批城市密谋移除影响', () => {
    const { state, catalog } = fixture();
    state.script.loops = 1;
    state.characters = { unstable: character('unstable', 'unstable_factor') };
    state.board.city.intrigue = 2;
    catalog.sources.kill = source('kill', [
      {
        id: 'both',
        effects: [
          {
            id: 'death',
            target: { kind: 'character', id: 'unstable' },
            operation: { kind: 'death' },
          },
          {
            id: 'city',
            target: { kind: 'area', id: 'city' },
            operation: { kind: 'counter', counter: 'intrigue', amount: -2 },
          },
        ],
      },
    ]);
    atNode(state, 'turn_end', 'turn_end.module');
    const engine = new Engine(state, catalog);
    engine.start();
    if (engine.waiting?.options.some((option) => option.id === 'city'))
      expect(choose(engine, ['city']).status).toBe('accepted');
    expect(engine.state.records.loopFailed).toBe(true);
    expect(engine.state.records.endRequests).toContain('key-person-died');
  });

  it('能力可选择文本允许的禁行目的地，实际移动失败但仍正常完成与限次', () => {
    const { state, catalog } = fixture();
    state.characters = {
      girl: character('girl', 'civilian', { definitionId: 'little_girl', area: 'school' }),
    };
    state.characters.girl!.counters.goodwill = 3;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['little_girl.goodwill2@girl']).status).toBe('accepted');
    expect(engine.waiting?.options.map((option) => option.id)).toContain('city');
    expect(choose(engine, ['city']).status).toBe('accepted');
    expect(engine.state.characters.girl!.area).toBe('school');
    expect(
      engine.waiting?.options.some((option) => option.id === 'little_girl.goodwill2@girl'),
    ).toBe(false);
  });

  it('能力同时移动多个对象时，从者跟随选择可以暂停恢复；不继承对象的延迟禁行', () => {
    const { state, catalog } = fixture();
    state.characters = {
      servant: character('servant', 'civilian', { definitionId: 'servant' }),
      big: character('big', 'civilian', { definitionId: 'big_shot' }),
      rich: character('rich', 'civilian', { definitionId: 'rich_girl' }),
    };
    state.script.options['territory:big'] = 'city';
    catalog.sources.moves = source('moves', [
      {
        id: 'move',
        effects: [
          {
            id: 'big',
            target: { kind: 'character', id: 'big' },
            operation: { kind: 'move-character', destination: 'city', lockNextDay: true },
          },
          {
            id: 'rich',
            target: { kind: 'character', id: 'rich' },
            operation: { kind: 'move-character', destination: 'school' },
          },
          {
            id: 'servant',
            target: { kind: 'character', id: 'servant' },
            operation: { kind: 'move-character', destination: 'shrine' },
          },
        ],
      },
    ]);
    atNode(state, 'turn_end', 'turn_end.module');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.waiting?.prompt).toContain('跟随');
    const restored = Engine.restore(engine.serialize(), catalog);
    expect(choose(engine, ['big']).status).toBe('accepted');
    expect(choose(restored, ['big']).status).toBe('accepted');
    expect(engine.serialize()).toBe(restored.serialize());
    expect(engine.state.characters.servant!.area).toBe('city');
    expect(engine.state.characters.servant!.attachments).not.toContain('movement-lock:2');
    expect(engine.state.characters.big!.attachments).toContain('movement-lock:2');
  });

  it('医院无密谋时事故仍完成，愚者的完成后能力依然清除不安', () => {
    const { state, catalog } = fixture();
    state.characters = { fool: character('fool', 'fool') };
    state.characters.fool!.counters.anxiety = 3;
    state.script.incidents = [
      {
        entryId: 'empty',
        day: 1,
        incidentId: 'hospital_accident',
        publicName: '医院事故',
        culpritIds: ['fool'],
      },
    ];
    atNode(state, 'incident', 'incident.judge');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.records.incidentHistory[0]).toMatchObject({
      completed: true,
      changed: false,
    });
    expect(engine.state.characters.fool!.counters.anxiety).toBe(0);
    expect(engine.state.publicLog.some((entry) => entry.type === 'incident-no-effect')).toBe(true);
  });

  it('手下在复原前选择本轮初始区域，上一轮快照不被改写', () => {
    const { state, catalog } = fixture();
    state.characters = {
      hench: character('hench', 'civilian', {
        definitionId: 'henchman',
        area: 'city',
        alive: false,
      }),
    };
    state.records.previousLoop = {
      loop: 1,
      ex: 0,
      characters: structuredClone(state.characters),
      board: structuredClone(state.board),
      loopIncidentEntryIds: [],
    };
    state.clock.loop = 2;
    atNode(state, 'loop_start', 'loop_start.henchman');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['school']).status).toBe('accepted');
    expect(engine.state.characters.hench).toMatchObject({
      alive: true,
      area: 'school',
      initialArea: 'school',
    });
    expect(engine.state.records.previousLoop!.characters.hench).toMatchObject({
      alive: false,
      area: 'city',
      initialArea: 'hospital',
    });
  });

  it('疯狂的真相仅替换本轮Y失败条件，不替换已配置身份或规则X', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'weird_mythology';
    state.script.ruleIds = ['wm.y.巨大定时炸弹Y', 'wm.x.疯狂的真相', 'wm.x.rumors'];
    state.script.options.crazyTruthRuleY = 'wm.y.染血的仪式';
    state.ex = 2;
    state.characters = {
      witch: character('witch', 'witch'),
      dead1: character('dead1', 'civilian', { alive: false }),
      dead2: character('dead2', 'civilian', { alive: false }),
    };
    const start = nativeForced('phase:loop_start:enter', state, catalog, {});
    expect(start.some((entry) => entry.name === '疯狂的真相')).toBe(true);
    state.records.revealedFacts.push('flag:failure-rule:wm.y.染血的仪式');
    const end = nativeForced('phase:loop_end:enter', state, catalog, {});
    expect(end.some((entry) => entry.name === '染血的仪式')).toBe(true);
    expect(end.some((entry) => entry.name === '巨大定时炸弹Y')).toBe(false);
    expect(state.characters.witch!.configuredIdentity).toBe('witch');
    expect(state.script.ruleIds).toContain('wm.x.rumors');
  });

  it('同轮希望牌已被除外后，另一授牌来源也不能再授第二张', () => {
    const { state, catalog } = fixture();
    const intent = {
      id: 'grant',
      sourceInstanceId: 'grant',
      effectId: 'card',
      operation: {
        kind: 'grant-card' as const,
        seat: 'protagonistA' as const,
        cardKind: 'hope+1' as const,
      },
    };
    let next = commitBatch(state, catalog, [intent]).state;
    next.cards.protagonistA.find((card) => card.kind === 'hope+1')!.zone = 'excluded';
    next = commitBatch(next, catalog, [intent]).state;
    expect(next.cards.protagonistA.filter((card) => card.kind === 'hope+1')).toHaveLength(1);
    next.clock.loop++;
    next = commitBatch(next, catalog, [intent]).state;
    expect(
      next.cards.protagonistA.filter((card) => card.kind === 'hope+1' && card.zone === 'hand'),
    ).toHaveLength(1);
  });

  it('AHR首轮授予绝望牌会发布公告', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'another_horizon_revised';
    atNode(state, 'loop_start', 'loop_start.reset');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(
      engine.state.publicLog
        .filter((entry) => entry.type === 'card-granted')
        .map((entry) => entry.text),
    ).toEqual(['剧作家获得绝望+1行动牌']);
  });

  it('双胞胎按对角医院结算事故，死亡后尸体仍留在学校', () => {
    const { state, catalog } = fixture();
    state.characters = {
      twins: character('twins', 'twins', { area: 'school' }),
      patient: character('patient'),
      other: character('other', 'civilian', { area: 'city' }),
    };
    state.characters.twins!.counters.anxiety = 3;
    state.board.hospital.intrigue = 1;
    state.script.incidents = [
      {
        entryId: 'accident',
        day: 1,
        incidentId: 'hospital_accident',
        publicName: '医院事故',
        culpritIds: ['twins'],
      },
    ];
    atNode(state, 'incident', 'incident.judge');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.characters.twins).toMatchObject({ alive: false, area: 'school' });
    expect(engine.state.characters.patient!.alive).toBe(false);
    expect(engine.state.characters.other!.alive).toBe(true);
    expect(engine.state.records.incidentHistory[0]!.completed).toBe(true);
  });

  it('仙人选择顺时针医院后参与医院事故，实际位置不移动', () => {
    const { state, catalog } = fixture();
    state.characters = {
      hermit: character('hermit', 'civilian', { definitionId: 'hermit', area: 'city' }),
    };
    state.script.options['hermitX:hermit'] = 0;
    state.board.hospital.intrigue = 1;
    state.script.incidents = [
      {
        entryId: 'accident',
        day: 1,
        incidentId: 'hospital_accident',
        publicName: '医院事故',
        culpritIds: ['hermit'],
      },
    ];
    atNode(state, 'incident', 'incident.judge');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['clockwise']).status).toBe('accepted');
    expect(engine.state.characters.hermit).toMatchObject({ alive: false, area: 'city' });
  });

  it('活忍者可宣称本局主谋身份，绝密报告使用公开名称而非实际身份', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'midnight_zone';
    state.script.ruleIds = ['mz.y.绝密报告'];
    state.characters = {
      ninja: character('ninja', 'ninja'),
      master: character('master', 'mastermind'),
    };
    catalog.sources.reveal = source('reveal', [
      {
        id: 'reveal',
        effects: [
          {
            id: 'identity',
            target: { kind: 'character', id: 'ninja' },
            operation: { kind: 'reveal-identity' },
          },
        ],
      },
    ]);
    atNode(state, 'turn_end', 'turn_end.module');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.waiting).toMatchObject({ actor: 'mastermind', private: true });
    expect(choose(engine, ['mastermind']).status).toBe('accepted');
    expect(engine.state.characters.ninja).toMatchObject({
      configuredIdentity: 'ninja',
      publicIdentity: 'mastermind',
    });
    const failure = nativeForced('phase:loop_end:enter', engine.state, catalog, {});
    expect(failure.some((entry) => entry.name === '绝密报告')).toBe(true);
  });

  it('忍者尸体不能通过直接效果绕过常驻失效条件', () => {
    const { state, catalog } = fixture();
    state.characters = { ninja: character('ninja', 'ninja', { alive: false }) };
    const next = commitBatch(state, catalog, [
      {
        id: 'reveal',
        sourceInstanceId: 'reveal',
        effectId: 'identity',
        targetId: 'ninja',
        operation: { kind: 'reveal-identity', declaredIdentity: 'mastermind' },
      },
    ]).state;
    expect(next.characters.ninja!.publicIdentity).toBe('ninja');
  });

  it('情报商在FS声明唯一真实X后，不产生空的强制选择或未绑定公告', () => {
    const { state, catalog } = fixture();
    state.characters = {
      info: character('info', 'civilian', { definitionId: 'informant', area: 'city' }),
    };
    state.characters.info!.counters.goodwill = 5;
    atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(choose(engine, ['informant.goodwill1@info']).status).toBe('accepted');
    expect(choose(engine, ['fs.x.shadow_of_the_ripper']).status).toBe('accepted');
    expect(engine.waiting?.options.some((option) => option.id === 'finish')).toBe(true);
    expect(engine.state.publicLog.some((entry) => entry.text.includes('$choice'))).toBe(false);
  });

  it('多个被爱者同批死亡时，为每名被爱者分别累计恋人不安', () => {
    const { state, catalog } = fixture();
    state.characters = {
      lover: character('lover', 'lover'),
      first: character('first', 'beloved'),
      second: character('second', 'beloved'),
    };
    catalog.sources.kill = source('kill', [
      {
        id: 'kill',
        effects: [
          {
            id: 'victims',
            target: { kind: 'characters', ids: ['first', 'second'], count: 'all' },
            operation: { kind: 'death' },
          },
        ],
      },
    ]);
    atNode(state, 'turn_end', 'turn_end.module');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.state.characters.lover!.counters.anxiety).toBe(12);
  });

  it('公开事件表只显示伪装名称，秘密字母仅对所属主人公可见', () => {
    const { state, catalog } = fixture();
    state.script.moduleId = 'last_liar';
    state.script.options.privateTest = 'hidden';
    state.secretLetters = { protagonistA: 'C', protagonistB: 'A', protagonistC: 'B' };
    state.script.incidents = [
      {
        entryId: 'secret-entry',
        day: 1,
        incidentId: 'suicide',
        publicName: '神秘事件',
        culpritIds: ['doctor'],
      },
    ];
    const engine = new Engine(state, catalog);
    const view = engine.view('protagonistA');
    expect(view.publicScript.incidents).toEqual([{ day: 1, name: '神秘事件' }]);
    expect(view.secretLetter).toBe('C');
    expect(engine.view('mastermind').secretLetter).toBeUndefined();
    expect(JSON.stringify(view)).not.toContain('secret-entry');
    expect(JSON.stringify(view)).not.toContain('hidden');
    expect(JSON.stringify(view)).not.toContain('suicide');
  });
});
