import { describe, it, expect } from 'vitest';
import { Engine } from '../packages/engine/src/index.js';
import { fixture, choose } from './fixtures.js';

describe('自主阶段机及等待恢复', () => {
  it('玩家只提交选择，完整走过九阶段并结束一局', () => {
    const { state, catalog } = fixture();
    state.script.daysPerLoop = 1;
    state.script.incidents = [];
    const engine = new Engine(state, catalog);
    engine.start();
    let commands = 0;
    while (engine.waiting) {
      expect(++commands).toBeLessThan(100);
      const w = engine.waiting;
      const answer = w.options.find((o) => o.id === 'finish')?.id ?? w.options[0]!.id;
      expect(choose(engine, [answer]).status).toBe('accepted');
    }
    expect(engine.state.status).toBe('finished');
    expect(
      engine.state.publicLog.filter((l) => l.type === 'phase').map((l) => l.text.split('（')[0]),
    ).toEqual([
      'loop_start',
      'turn_start',
      'mastermind_action',
      'protagonist_action',
      'action_resolution',
      'mastermind_ability',
      'protagonist_ability',
      'incident',
      'leader_rotation',
      'turn_end',
      'loop_end',
    ]);
    expect(engine.state.leader).toBe('protagonistB');
  });
  it('等待中的快照恢复相同；外席和过期命令不改变盘面', () => {
    const { state, catalog } = fixture();
    const engine = new Engine(state, catalog);
    engine.start();
    const restored = Engine.restore(engine.serialize(), catalog);
    const before = engine.serialize();
    expect(choose(engine, ['protagonistA'], 'mastermind')).toMatchObject({ status: 'rejected' });
    expect(engine.serialize()).toBe(before);
    expect(choose(engine, ['protagonistA']).status).toBe('accepted');
    expect(choose(restored, ['protagonistA']).status).toBe('accepted');
    expect(restored.serialize()).toBe(engine.serialize());
    expect(engine.view('protagonistA').characters.every((c) => c.identity === undefined)).toBe(
      true,
    );
  });
});
