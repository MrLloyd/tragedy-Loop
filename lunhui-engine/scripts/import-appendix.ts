// Mechanical import only. Runtime semantics are implemented and tested separately.
import { readFileSync, writeFileSync } from 'node:fs';
const lines = readFileSync(new URL('../../tragedy_loop_appendix(3)(1).md', import.meta.url), 'utf8')
  .replace(/^\uFEFF/, '')
  .split(/\r?\n/);
type Rule = {
  name: string;
  kind: 'y' | 'x';
  roles: Array<{ name: string; count: string }>;
  text: string[];
};
type Module = {
  name: string;
  special: string[];
  rules: Rule[];
  identities: Array<{ name: string; max: string; traits: string; abilities: string[] }>;
  incidents: Array<{ name: string; text: string[] }>;
};
const modules: Module[] = [];
const characters: string[][] = [];
let module: Module | undefined;
let section = '';
let ruleKind: Rule['kind'] = 'y';
let characterSection = false;
for (const line of lines) {
  if (line.startsWith('## 附录C')) {
    characterSection = true;
    continue;
  }
  if (line.startsWith('### ') && !characterSection && !line.includes('希望／绝望')) {
    module = { name: line.slice(4).trim(), special: [], rules: [], identities: [], incidents: [] };
    modules.push(module);
    continue;
  }
  if (line.startsWith('#### ')) {
    section = line.slice(5).trim();
    continue;
  }
  if (!line.startsWith('|') || /^\|\s*-/.test(line)) continue;
  const cells = line
    .split('|')
    .slice(1, -1)
    .map((v) => v.trim());
  if (characterSection) {
    if (cells[0] !== '角色名') characters.push(cells);
    continue;
  }
  if (!module) continue;
  if (section === '特殊规则') {
    if (cells[0] !== '内容') module.special.push(cells[0]!);
  }
  if (section === '规则' && cells[0] !== '类型') {
    if (cells[0] === '规则Y') ruleKind = 'y';
    if (cells[0] === '规则X') ruleKind = 'x';
    if (cells[1]) module.rules.push({ name: cells[1], kind: ruleKind, roles: [], text: [] });
    const rule = module.rules.at(-1);
    if (!rule) throw new Error('RULE_WITHOUT_NAME');
    if (cells[2]) rule.roles.push({ name: cells[2], count: cells[3]! });
    if (cells[4]) rule.text.push(cells[4]);
  }
  if (section === '身份' && cells[0] !== '身份')
    module.identities.push({
      name: cells[0]!,
      max: cells[1]!,
      traits: cells[2]!,
      abilities: cells.slice(3).filter(Boolean),
    });
  if (section === '事件' && cells[0] !== '名称') {
    if (cells[0]) module.incidents.push({ name: cells[0], text: [] });
    module.incidents.at(-1)!.text.push(...cells.slice(1).filter(Boolean));
  }
}
if (modules.length !== 8 || characters.length !== 37)
  throw new Error(`IMPORT_COUNT:${modules.length}/${characters.length}`);
writeFileSync(
  new URL('../packages/content/src/appendix-data.json', import.meta.url),
  JSON.stringify({ modules, characters }, null, 2) + '\n',
);
console.log(`Imported ${modules.length} modules and ${characters.length} character cards.`);
