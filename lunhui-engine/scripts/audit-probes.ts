/** Read-only P0 diagnostic fixtures. These expose current behavior, not acceptance tests. */
import { Engine, evaluatePersistent, selectCandidates } from '../packages/engine/src/index.js';
import { nativeOptional } from '../packages/engine/src/native-rules.js';
import { atNode, character, choose, fixture } from '../tests/fixtures.js';
import { writeFileSync } from 'node:fs';

const findings: unknown[] = [];
{
  const { state, catalog } = fixture();
  state.script.moduleId = 'haunted_stage_again';
  const rule = Object.values(catalog.rules!).find((r) => r.name === '怪物们的阴谋')!;
  state.script.ruleIds = [rule.id];
  state.characters = { tiger: character('tiger', 'paper_tiger') };
  state.characters.tiger!.counters.anxiety = 2;
  const effective = evaluatePersistent(state, catalog);
  const source = nativeOptional('mastermind_ability', state, catalog).find(
    (s) => s.name === rule.name,
  )!;
  const actual = selectCandidates(
    source.program.segments[0]!.effects[0]!.target,
    state,
    effective,
    catalog,
  );
  findings.push({
    id: 'P0-01',
    scenario: '纸老虎不安2，位于医院，启用怪物们的阴谋',
    expected: ['hospital'],
    actual,
    effectiveTraits: effective.characters.tiger!.traits,
  });
}
{
  const { state, catalog } = fixture();
  state.script.moduleId = 'haunted_stage_again';
  state.script.ruleIds = ['hsa.y.ancient_tomb'];
  state.characters = { living: character('living') };
  state.board.hospital.intrigue = 1;
  atNode(state, 'turn_end', 'turn_end.optional');
  const engine = new Engine(state, catalog);
  engine.start();
  findings.push({
    id: 'P0-02',
    scenario: '古墓活尸，医院只有密谋牺牲者丧尸，没有实体丧尸卡',
    expected: '可选择丧尸尸体移动',
    actual: engine.waiting?.options.map((o) => o.id),
  });
}
{
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
  const replies = [
    choose(engine, ['sister.goodwill1@sister']),
    choose(engine, ['appraiser.goodwill1@appraiser']),
  ];
  for (let i = 0; i < 10 && engine.waiting?.kind !== 'ability'; i++) replies.push(choose(engine));
  findings.push({
    id: 'P0-03',
    scenario: '妹妹调用鉴别员移动指示物，但同区只有妹妹和鉴别员，且无指示物',
    expected: '按用户确认裁定，成人能力无合法目标不阻止妹妹发动、登记沟通和完成',
    actual: {
      sisterCommunicated: engine.state.characters.sister!.marks.communicated,
      outcomes: Object.values(engine.state.records.sourceOutcomes).map((o) => ({
        sourceId: o.sourceId,
        started: o.started,
        completed: o.completed,
      })),
      replies,
    },
  });
}
const report = {
  date: '2026-09-26',
  note: '直接设置状态的诊断夹具，不代表合法完整剧本；P0处理意见的结果断言见tests/p0-rulings.test.ts。',
  findings,
};
writeFileSync(
  new URL('../docs/p0-probe-results.json', import.meta.url),
  JSON.stringify(report, null, 2) + '\n',
);
console.log(JSON.stringify(report, null, 2));
