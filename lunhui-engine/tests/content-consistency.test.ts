import { describe, expect, it } from 'vitest';
import { createCatalog } from '../packages/content/src/index.js';
import { appendix } from '../packages/content/src/registry.js';

const catalog = createCatalog();
const areaNames: Record<string, string> = {
  医院: 'hospital',
  神社: 'shrine',
  都市: 'city',
  学校: 'school',
  远方: 'faraway',
};

describe('附录与执行内容数据一致性', () => {
  it('37张角色属性、阈值、限次和能力数逐行一致', () => {
    expect(Object.keys(catalog.characters)).toHaveLength(appendix.characters.length);
    for (const row of appendix.characters) {
      const card = Object.values(catalog.characters).find((card) => card.name === row[0])!;
      expect(card, row[0]).toBeDefined();
      expect(card.attributes, card.name).toEqual(row.slice(2, 4).filter(Boolean));
      expect(card.anxietyLimit, card.name).toBe(row[10] === 'X' ? 'X' : Number(row[10]));
      if (row[4] !== '见特性') {
        const initial = row[4]!
          .replace(/（.*?）/g, '')
          .split(/[，、,]/)
          .map((name) => areaNames[name]);
        expect(card.initialAreas, card.name).toEqual(initial);
      }
      const forbidden =
        row[5] === '否' ? [] : row[5]!.split(/[，、,]/).map((name) => areaNames[name]);
      expect([...card.forbiddenAreas].sort(), card.name).toEqual(forbidden.sort());
      expect(card.goodwillAbilities, card.name).toHaveLength(
        row.slice(6, 10).filter(Boolean).length,
      );
      for (let index = 0; index < 4; index++)
        if (row[6 + index]) {
          const ability = card.goodwillAbilities.find(
            (ability) => ability.sourceId === `${card.id}.goodwill${index + 1}`,
          )!;
          expect(ability.threshold, card.name).toBe(Number(row[11 + index]));
          expect(Boolean(ability.oncePerLoop), `${card.name}:${index}`).toBe(
            row[15 + index] === '是',
          );
          expect(catalog.sources[ability.sourceId]?.goodwill?.threshold).toBe(ability.threshold);
        }
    }
  });

  it('八模组的规则和事件没有未登记的引用', () => {
    expect(Object.keys(catalog.modules)).toHaveLength(8);
    for (const module of Object.values(catalog.modules)) {
      const data = appendix.modules.find((data) => data.name === module.name)!;
      expect(module.rules).toHaveLength(data.rules.length);
      expect(module.incidents).toHaveLength(data.incidents.length);
      for (const id of module.rules) expect(catalog.rules![id]).toBeDefined();
      for (const id of module.identities) expect(catalog.identities[id]).toBeDefined();
      for (const id of module.incidents) expect(catalog.incidents[id]).toBeDefined();
    }
  });
});
