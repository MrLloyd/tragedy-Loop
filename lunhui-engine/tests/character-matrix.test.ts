import { describe, expect, it } from 'vitest';
import { createCatalog } from '../packages/content/src/index.js';
import { Engine } from '../packages/engine/src/index.js';
import { atNode, character, choose, fixture } from './fixtures.js';

const catalog = createCatalog();
describe('角色友好能力处理器矩阵（可执行性与恢复）', () => {
  for (const definition of Object.values(catalog.characters))
    for (const ability of definition.goodwillAbilities) {
      it(`${definition.name} / ${ability.sourceId}`, () => {
        const { state } = fixture();
        state.clock.loop = 2;
        state.ex = 2;
        const area = definition.initialAreas[0]!;
        state.characters = {
          owner: character('owner', 'civilian', {
            definitionId: definition.id,
            initialArea: area,
            area,
          }),
          adult: character('adult', 'civilian', { definitionId: 'doctor', area }),
          student: character('student', 'civilian', { definitionId: 'male_student', area }),
          patient: character('patient', 'civilian', { definitionId: 'patient', area }),
          corpse: character('corpse', 'civilian', { alive: false, area }),
        };
        for (const c of Object.values(state.characters))
          c.counters = { goodwill: 6, anxiety: 4, intrigue: 2, hope: 0, despair: 0, guard: 0 };
        state.script.options['hermitX:owner'] = 2;
        state.script.options['territory:owner'] = area;
        state.script.incidents = [
          {
            entryId: 'entry',
            incidentId: 'anxiety_spread',
            day: 1,
            publicName: '不安扩散',
            culpritIds: ['adult'],
          },
        ];
        state.records.incidentHistory = [
          {
            sequence: 0,
            entryId: 'entry',
            incidentId: 'anxiety_spread',
            publicName: '不安扩散',
            culpritIds: ['adult'],
            loop: 2,
            day: 1,
            completed: true,
            changed: true,
            calledByAi: false,
          },
        ];
        state.cards.protagonistA.find((card) => card.oncePerLoop)!.zone = 'used';
        atNode(state, 'protagonist_ability', 'protagonist_ability.optional');
        const engine = new Engine(state, catalog);
        engine.start();
        const id = `${ability.sourceId}@owner`;
        expect(engine.waiting?.options.map((option) => option.id)).toContain(id);
        expect(choose(engine, [id]).status).toBe('accepted');
        let choices = 0;
        while (engine.waiting && JSON.parse(engine.serialize()).execution.frames.length) {
          expect(++choices, engine.waiting.prompt).toBeLessThan(50);
          const w = engine.waiting;
          expect(w.options.length, w.prompt).toBeGreaterThanOrEqual(w.minSelections);
          const ids = w.options.slice(0, w.minSelections).map((option) => option.id);
          const restored = Engine.restore(engine.serialize(), catalog);
          expect(choose(engine, ids), w.prompt).toMatchObject({ status: 'accepted' });
          expect(choose(restored, ids), w.prompt).toMatchObject({ status: 'accepted' });
          expect(engine.serialize()).toBe(restored.serialize());
        }
        expect(engine.state.status).not.toBe('faulted');
        expect(
          Object.values(engine.state.records.sourceOutcomes).some(
            (outcome) => outcome.sourceId === id && outcome.completed,
          ),
        ).toBe(true);
      });
    }
});
