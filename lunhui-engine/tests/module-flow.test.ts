import { describe, expect, it } from 'vitest';
import { createCatalog } from '../packages/content/src/index.js';
import {
  createGame,
  Engine,
  validateNewGame,
  type NewGameInput,
} from '../packages/engine/src/index.js';
import { character, choose } from './fixtures.js';

const configurations: Array<[string, string[]]> = [
  ['first_steps', ['谋杀计划', '开膛者的魔影']],
  ['basic_tragedy_x', ['谋杀计划', '好友圈', '流言四起']],
  ['midnight_zone', ['因果之绊', '死亡真人秀', '心无灵犀']],
  ['mystery_circle', ['命悬一线的计划', '火药的味道', '我是名侦探']],
  ['haunted_stage_again', ['古墓活尸', '恋爱风景线', '不听劝的人']],
  ['weird_mythology', ['巨大定时炸弹Y', '流言四起', '无貌之神']],
  ['another_horizon_revised', ['童话里的杀人鬼', '化身博士', '恶魔吹着笛子来']],
  ['last_liar', ['巨大定时炸弹Z', '真正的怪物', '超越世界线']],
];

function scenario(moduleId: string, names: string[]) {
  const catalog = createCatalog();
  const module = catalog.modules[moduleId]!;
  const rules = names.map(
    (name) =>
      Object.values(catalog.rules!).find(
        (rule) => rule.name === name && module.rules.includes(rule.id),
      )!,
  );
  const counts = new Map<string, number>();
  const pairs: Array<[string, string | undefined]> = [];
  for (const rule of rules) {
    expect(rule).toBeDefined();
    const variable = rule.roles.filter((role) => ['表', '里'].includes(role.count));
    if (variable.length)
      pairs.push([
        variable.find((role) => role.count === '表')?.identityId ?? 'civilian',
        variable.find((role) => role.count === '里')?.identityId ?? 'civilian',
      ]);
    for (const role of rule.roles.filter((role) => !['表', '里'].includes(role.count)))
      counts.set(
        role.identityId,
        (counts.get(role.identityId) ?? 0) + Number(role.count.split('-')[0]),
      );
  }
  for (const [id, count] of counts)
    for (
      let i = 0;
      i < Math.min(count, module.identityLimits?.[id] ?? catalog.identities[id]?.max ?? Infinity);
      i++
    )
      pairs.push([id, undefined]);
  const definitions = [
    'doctor',
    'male_student',
    'female_student',
    'police',
    'shrine_maiden',
    'soldier',
    'office_worker',
    'teacher',
    'idol',
    'cult_leader',
    'journalist',
  ];
  const characters = pairs.map(([identity, reverseIdentity], i) => {
    const definition = catalog.characters[definitions[i]!]!;
    const area = definition.initialAreas[0]!;
    return character(`actor${i}`, identity, {
      definitionId: definition.id,
      area,
      initialArea: area,
      ...(reverseIdentity ? { reverseIdentity } : {}),
    });
  });
  const incident = module.incidents
    .map((id) => catalog.incidents[id]!)
    .find((entry) => !entry.crowd)!;
  const input: NewGameInput = {
    script: {
      id: `smoke-${moduleId}`,
      moduleId,
      ruleIds: rules.map((rule) => rule.id),
      loops: 2,
      daysPerLoop: 3,
      finalShowdown: module.finalShowdown,
      options: {},
      incidents: characters
        .filter((c) =>
          ['obstinate', 'fool', 'twins', 'sacrifice', 'eccentric'].includes(c.configuredIdentity),
        )
        .map((c, index) => ({
          entryId: `incident${index}`,
          day: index + 1,
          incidentId: incident.id,
          publicName: incident.name,
          culpritIds: [c.id],
        })),
    },
    characters,
    ...(moduleId === 'last_liar'
      ? {
          secretLetters: {
            protagonistA: 'B' as const,
            protagonistB: 'C' as const,
            protagonistC: 'A' as const,
          },
        }
      : {}),
  };
  return { catalog, input };
}

describe('八模组实际配置整局验收', () => {
  it('剧作家可以关闭默认开放最终决战的模组', () => {
    const { catalog, input } = scenario('basic_tragedy_x', ['谋杀计划', '好友圈', '流言四起']);
    input.script.finalShowdown = false;
    expect(validateNewGame(input, catalog)).toEqual([]);
    expect(createGame(input, catalog).script.finalShowdown).toBe(false);
  });
  for (const [moduleId, rules] of configurations) {
    it(`${moduleId}：开局、自动阶段、选择与中途恢复均可到达最终结果`, () => {
      const { catalog, input } = scenario(moduleId, rules);
      expect(validateNewGame(input, catalog)).toEqual([]);
      let engine = new Engine(createGame(input, catalog), catalog);
      engine.start();
      let count = 0;
      while (engine.waiting) {
        expect(++count, engine.waiting.prompt).toBeLessThan(1500);
        const waiting = engine.waiting;
        expect(waiting.options.length, waiting.prompt).toBeGreaterThanOrEqual(
          waiting.minSelections,
        );
        const preferred =
          waiting.options.find((option) => option.id === 'finish') ??
          waiting.options.find((option) => option.id === 'no');
        const ids = preferred
          ? [preferred.id]
          : waiting.options.slice(0, waiting.minSelections).map((option) => option.id);
        if (count % 11 === 0) {
          const restored = Engine.restore(engine.serialize(), catalog);
          expect(choose(restored, ids), `${moduleId}: ${waiting.prompt}`).toMatchObject({
            status: 'accepted',
          });
          expect(choose(engine, ids), `${moduleId}: ${waiting.prompt}`).toMatchObject({
            status: 'accepted',
          });
          expect(restored.serialize()).toBe(engine.serialize());
          engine = restored;
        } else
          expect(choose(engine, ids), `${moduleId}: ${waiting.prompt}`).toMatchObject({
            status: 'accepted',
          });
      }
      expect(engine.state.status).toBe('finished');
      expect(engine.state.result?.winners.length).toBeGreaterThan(0);
      expect(
        engine.state.publicLog.some(
          (entry) => entry.type === 'phase' && entry.text.startsWith('loop_end'),
        ),
      ).toBe(true);
    });
  }
});
