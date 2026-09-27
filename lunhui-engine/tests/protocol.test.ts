import { describe, expect, it } from 'vitest';
import { Engine, createGame } from '../packages/engine/src/index.js';
import { firstStepsScenario } from '../packages/content/src/index.js';
import { LocalTransport } from '../packages/transport/src/index.js';
import { fixture } from './fixtures.js';

function command(engine: Engine) {
  const w = engine.waiting!;
  return {
    protocolVersion: 2 as const,
    sessionId: 'local',
    branchId: 'main',
    commandId: 'receipt-1',
    expectedRevision: w.revision,
    waitingInputId: w.id,
    command: { kind: 'choose' as const, optionIds: [w.options[0]!.id] },
  };
}

describe('协议、恢复与宿主事务', () => {
  it('同命令重试不重复执行；不同载荷或席位不得复用回执', () => {
    const { state, catalog } = fixture();
    const engine = new Engine(state, catalog);
    engine.start();
    const input = command(engine);
    const actor = engine.waiting!.actor;
    const accepted = engine.submit(actor, input);
    const snapshot = engine.serialize();
    expect(engine.submit(actor, input)).toEqual(accepted);
    expect(engine.serialize()).toBe(snapshot);
    expect(engine.submit('mastermind', input)).toMatchObject({
      status: 'rejected',
      code: 'ID_REUSED',
    });
    expect(
      engine.submit(actor, { ...input, command: { kind: 'choose', optionIds: ['protagonistC'] } }),
    ).toMatchObject({ status: 'rejected', code: 'ID_REUSED' });
    const restored = Engine.restore(snapshot, catalog);
    expect(restored.submit(actor, input)).toEqual(accepted);
    expect(restored.serialize()).toBe(snapshot);
  });

  it('非法、过期、跨会话、重复和越界选择均不修改状态', () => {
    const { state, catalog } = fixture();
    const engine = new Engine(state, catalog);
    engine.start();
    const input = command(engine);
    const actor = engine.waiting!.actor;
    const before = engine.serialize();
    for (const malformed of [
      { ...input, protocolVersion: 1 },
      { ...input, injected: true },
      { ...input, expectedRevision: input.expectedRevision - 1 },
      { ...input, sessionId: 'other' },
      { ...input, branchId: 'other' },
      { ...input, command: { kind: 'choose', optionIds: [] } },
      { ...input, command: { kind: 'choose', optionIds: ['invalid'] } },
      {
        ...input,
        command: {
          kind: 'choose',
          optionIds: [input.command.optionIds[0], input.command.optionIds[0]],
        },
      },
    ]) {
      expect(engine.submit(actor, malformed).status).toBe('rejected');
      expect(engine.serialize()).toBe(before);
    }
  });

  it('返回的视图与状态副本不能修改内部状态', () => {
    const { state, catalog } = fixture();
    const engine = new Engine(state, catalog);
    engine.start();
    const before = engine.serialize();
    engine.state.characters.doctor!.alive = false;
    engine.view('protagonistA').characters[0]!.counters.goodwill = 999;
    engine.waiting!.options.length = 0;
    expect(engine.serialize()).toBe(before);
  });

  it('本机传输串行处理重复提交，观察者异常不回滚已接受选择', async () => {
    const { state, catalog } = fixture();
    const engine = new Engine(state, catalog);
    engine.start();
    const transport = new LocalTransport(engine, engine.waiting!.actor);
    transport.subscribe(() => {
      throw new Error('observer failed');
    });
    const input = command(engine);
    const [a, b] = await Promise.all([transport.submit(input), transport.submit(input)]);
    expect(a.status).toBe('accepted');
    expect(b).toEqual(a);
    expect((await transport.getSnapshot()).revision).toBe(a.revision);
  });

  it.each([17, 29, 43, 61, 83, 101, 127, 149])('固定种子%s下合法随机选择能走完整局', (seed) => {
    const { catalog } = fixture();
    const engine = new Engine(createGame(firstStepsScenario(), catalog), catalog);
    engine.start();
    let random = seed;
    let decisions = 0;
    const next = () => {
      random = (Math.imul(random, 1664525) + 1013904223) >>> 0;
      return random / 4294967296;
    };
    while (engine.waiting) {
      expect(++decisions).toBeLessThan(2000);
      const w = engine.waiting;
      const options = [...w.options];
      const ids: string[] = [];
      for (let i = 0; i < w.minSelections; i++) {
        const at = Math.floor(next() * options.length);
        ids.push(options.splice(at, 1)[0]!.id);
      }
      expect(
        engine.submit(w.actor, {
          ...command(engine),
          commandId: `random:${decisions}`,
          command: { kind: 'choose', optionIds: ids },
        }),
        w.prompt,
      ).toMatchObject({ status: 'accepted' });
    }
    expect(engine.state.status).toBe('finished');
  });
});
