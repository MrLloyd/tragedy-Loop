import { describe, expect, it } from 'vitest';
import { createCatalog } from '../packages/content/src/index.js';
import { Engine } from '../packages/engine/src/index.js';
import { atNode, character, choose, fixture } from './fixtures.js';

const catalog = createCatalog();
describe('附录事件处理器矩阵（定点结算夹具，不是剧本校验）', () => {
  for (const module of Object.values(catalog.modules))
    for (const incidentId of module.incidents) {
      const incident = catalog.incidents[incidentId]!;
      it(`${module.name} / ${incident.name} 能完成或按结束要求截断，且无空选项`, () => {
        const { state } = fixture();
        state.script.moduleId = module.id;
        state.script.ruleIds = [];
        state.script.loops = 1;
        state.script.finalShowdown = module.finalShowdown;
        state.characters = {
          culprit: character('culprit', 'civilian'),
          neighbour: character('neighbour', 'civilian', { definitionId: 'nurse' }),
          distant: character('distant', 'civilian', { definitionId: 'teacher', area: 'school' }),
          corpse1: character('corpse1', 'civilian', { alive: false }),
          corpse2: character('corpse2', 'civilian', { alive: false }),
        };
        state.characters.culprit!.counters = {
          anxiety: 10,
          intrigue: 3,
          goodwill: 3,
          despair: 0,
          hope: 0,
          guard: 0,
        };
        state.board.hospital.intrigue = 2;
        state.script.incidents = [
          {
            entryId: 'entry',
            day: 1,
            incidentId,
            publicName: incident.name,
            culpritIds: incident.crowd ? [] : ['culprit'],
            ...(incident.crowd ? { crowdArea: 'hospital' as const } : {}),
          },
        ];
        atNode(state, 'incident', 'incident.judge');
        let engine = new Engine(state, catalog);
        engine.start();
        let count = 0;
        while (engine.waiting && engine.state.clock.phase === 'incident') {
          expect(++count).toBeLessThan(100);
          const w = engine.waiting;
          expect(w.options.length, w.prompt).toBeGreaterThanOrEqual(w.minSelections);
          const ids = w.options.slice(0, w.minSelections).map((option) => option.id);
          const restored = Engine.restore(engine.serialize(), catalog);
          expect(choose(engine, ids), w.prompt).toMatchObject({ status: 'accepted' });
          expect(choose(restored, ids), w.prompt).toMatchObject({ status: 'accepted' });
          expect(restored.serialize()).toBe(engine.serialize());
          engine = restored;
        }
        expect(engine.state.status).not.toBe('faulted');
        expect(engine.state.records.incidentHistory).toHaveLength(1);
        const record = engine.state.records.incidentHistory[0]!;
        const outcomes = Object.values(engine.state.records.sourceOutcomes).filter((outcome) =>
          outcome.sourceId.startsWith('incident.'),
        );
        expect(record.completed || outcomes.some((outcome) => outcome.truncated)).toBe(true);
      });
    }
});
