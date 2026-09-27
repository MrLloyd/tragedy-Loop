import { describe, expect, it } from 'vitest';
import { Engine, placeAction } from '../packages/engine/src/index.js';
import { atNode, character, choose, fixture } from './fixtures.js';

describe('公开结果与秘密隔离', () => {
  it('医院事故等强制后续收尾后仅公告主人公死亡，不另公告同时失败', () => {
    const { state, catalog } = fixture();
    state.script.loops = 1;
    state.characters = { key: character('key', 'key_person'), fool: character('fool', 'fool') };
    state.characters.fool!.counters.anxiety = 3;
    state.board.hospital.intrigue = 2;
    state.script.incidents = [
      {
        entryId: 'event',
        day: 1,
        incidentId: 'hospital_accident',
        publicName: '公开事件',
        culpritIds: ['fool'],
      },
    ];
    atNode(state, 'incident', 'incident.judge');
    const engine = new Engine(state, catalog);
    engine.start();
    const log = engine.view('protagonistA').publicLog;
    expect(
      log
        .filter((entry) => ['loop-failed', 'protagonists-died'].includes(entry.type))
        .map((entry) => entry.text),
    ).toEqual(['主人公死亡']);
    const cleared = log.findIndex(
      (entry) => entry.type === 'counter-changed' && entry.text.includes('fool'),
    );
    expect(cleared).toBeGreaterThan(-1);
    expect(log.findIndex((entry) => entry.type === 'protagonists-died')).toBeGreaterThan(cleared);
    expect(JSON.stringify(log)).not.toContain('key_person');
  });

  it('未发生事件使用公开名称，不泄露实际事件或当事人', () => {
    const { state, catalog } = fixture();
    state.script.incidents = [
      {
        entryId: 'secret',
        day: 1,
        incidentId: 'suicide',
        publicName: '不明事件',
        culpritIds: ['doctor'],
      },
    ];
    atNode(state, 'incident', 'incident.judge');
    const engine = new Engine(state, catalog);
    engine.start();
    const log = engine.view('protagonistA').publicLog;
    expect(log).toContainEqual(
      expect.objectContaining({ type: 'incident-not-occurred', text: '预定事件未发生：不明事件' }),
    );
    expect(JSON.stringify(log)).not.toContain('suicide');
    expect(JSON.stringify(log)).not.toContain('doctor');
  });

  it('从者跟随等待前已经翻开所有牌，恢复选择不会重复公告', () => {
    const { state, catalog } = fixture();
    state.characters = {
      servant: character('servant', 'civilian', { definitionId: 'servant' }),
      big: character('big', 'civilian', { definitionId: 'big_shot' }),
      rich: character('rich', 'civilian', { definitionId: 'rich_girl' }),
    };
    placeAction(
      state,
      catalog,
      'mastermind',
      state.cards.mastermind.find((card) => card.kind === 'move-horizontal')!.id,
      { kind: 'character', id: 'big' },
    );
    placeAction(
      state,
      catalog,
      'protagonistA',
      state.cards.protagonistA.find((card) => card.kind === 'move-vertical')!.id,
      { kind: 'character', id: 'rich' },
    );
    atNode(state, 'action_resolution', 'action_resolution.run');
    const engine = new Engine(state, catalog);
    engine.start();
    expect(engine.waiting!.prompt).toContain('跟随');
    expect(engine.view('protagonistC').placements.every((placement) => placement.cardKind)).toBe(
      true,
    );
    expect(
      engine.view('protagonistC').publicLog.filter((entry) => entry.type === 'action-revealed'),
    ).toHaveLength(2);
    const restored = Engine.restore(engine.serialize(), catalog);
    expect(choose(restored, ['big']).status).toBe('accepted');
    expect(
      restored.view('protagonistC').publicLog.filter((entry) => entry.type === 'action-revealed'),
    ).toHaveLength(2);
  });

  it('EX牌只公开存在，不把所用因果规则编码泄露给主人公', () => {
    const { state, catalog } = fixture();
    state.characters.doctor!.attachments = ['bond-ex'];
    state.curses = [{ id: 'curse', kind: 'character', targetId: 'doctor' }];
    const view = new Engine(state, catalog).view('protagonistA');
    expect(view.characters.find((card) => card.id === 'doctor')!.exCard).toBe(true);
    expect(view.curses).toEqual(state.curses);
    expect(JSON.stringify(view)).not.toContain('bond-ex');
  });
});
