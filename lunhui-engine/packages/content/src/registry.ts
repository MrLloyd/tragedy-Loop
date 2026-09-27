import appendix from './appendix-data.json' with { type: 'json' };
import type { ContentCatalog } from '../../engine/src/model.js';

const moduleIds = [
  'first_steps',
  'basic_tragedy_x',
  'midnight_zone',
  'mystery_circle',
  'haunted_stage_again',
  'weird_mythology',
  'another_horizon_revised',
  'last_liar',
];
const prefixes = ['fs', 'btx', 'mz', 'mc', 'hsa', 'wm', 'ahr', 'll'];
const aliases: Record<string, string> = {
  谋杀计划: 'murder_plan',
  复仇的火种: 'revenge',
  守护此地: 'protect_this_place',
  开膛者的魔影: 'shadow_of_the_ripper',
  流言四起: 'rumors',
  最黑暗的剧本: 'darkest_script',
  被封印的邪灵: 'sealed_evil',
  '和我签订契约吧！': 'contract',
  改变未来: 'change_future',
  巨大定时炸弹X: 'time_bomb',
  好友圈: 'friends',
  恋爱风景线: 'lovers',
  潜伏的杀人狂: 'hidden_killer',
  妄想扩大病毒: 'delusion_virus',
  因果线: 'causal_line',
  未知因子Χ: 'unknown_factor',
  因果之绊: 'bond_of_fate',
  心无灵犀: 'mutual_understanding',
  灭亡讴歌: 'doom_chant',
  士的宁毒液: 'strychnine_poison',
  古墓活尸: 'ancient_tomb',
  深渊之都的私语: 'whispers_of_the_deep',
  傀儡之线: 'puppet_strings',
  空想扩大病毒: 'fantasy_virus',
  最终计划: 'final_plan',
  封印的终末: 'sealed_end',
  真正的怪物: 'true_monster',
  神话收集者: 'myth_collector',
};

export function installRegistry(catalog: ContentCatalog): void {
  catalog.rules = {};
  const identityIds = Object.fromEntries(
    Object.values(catalog.identities).map((i) => [i.name, i.id]),
  );
  const incidentIds = Object.fromEntries(
    Object.values(catalog.incidents).map((i) => [i.name, i.id]),
  );
  appendix.modules.forEach((module, index) => {
    const id = moduleIds[index]!;
    const prefix = prefixes[index]!;
    const rules = module.rules.map((rule) => {
      if (rule.kind !== 'x' && rule.kind !== 'y') throw new Error(`UNKNOWN_RULE_KIND:${rule.kind}`);
      const ruleId = `${prefix}.${rule.kind}.${aliases[rule.name] ?? rule.name}`;
      catalog.rules![ruleId] = {
        id: ruleId,
        name: rule.name,
        kind: rule.kind,
        text: rule.text,
        roles: rule.roles.map((role) => {
          const identityId = identityIds[role.name];
          if (!identityId) throw new Error(`UNKNOWN_IMPORTED_IDENTITY:${role.name}`);
          return { identityId, count: role.count };
        }),
      };
      return ruleId;
    });
    catalog.modules[id] = {
      id,
      name: module.name,
      rules,
      ruleSelection: { y: 1, x: index === 0 ? 1 : 2 },
      finalShowdown: index !== 0,
      exReset: [3, 6].includes(index) ? 'zero' : index === 5 ? 'keep' : 'none',
      identities: ['civilian', ...module.identities.map((i) => identityIds[i.name]!)],
      identityLimits: Object.fromEntries(
        module.identities
          .filter((identity) => /^\d+$/.test(identity.max))
          .map((identity) => [identityIds[identity.name]!, Number(identity.max)]),
      ),
      incidents: module.incidents.map((incident) => incidentIds[incident.name] ?? incident.name),
    };
  });
}

export function contentCoverage(catalog: ContentCatalog) {
  return appendix.modules.flatMap((module, index) =>
    module.incidents.map((incident) => ({
      module: moduleIds[index]!,
      incident: incident.name,
      implemented: Object.values(catalog.incidents).some((entry) => entry.name === incident.name),
    })),
  );
}

export { appendix };
