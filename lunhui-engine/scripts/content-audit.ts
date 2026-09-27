/** P0 inventory generator. Routing below is an explicit review index, not semantic validation. */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createCatalog } from '../packages/content/src/index.js';
import { appendix } from '../packages/content/src/registry.js';

const root = new URL('../', import.meta.url);
const catalog = createCatalog();
const E = 'packages/engine/src/';
const C = 'packages/content/src/';
const sourceFile = '../tragedy_loop_appendix(3)(1).md';
const files = new Map<string, string[]>();
function lines(file: string): string[] {
  if (!files.has(file))
    files.set(
      file,
      readFileSync(new URL(file, root), 'utf8')
        .replace(/^\uFEFF/, '')
        .split(/\r?\n/),
    );
  return files.get(file)!;
}
type Ref = { file: string; line: number; note?: string };
function ref(file: string, needle = '', note?: string): Ref {
  const index = needle ? lines(file).findIndex((s) => s.includes(needle)) : 0;
  if (index < 0) throw new Error(`AUDIT_REFERENCE_NOT_FOUND:${file}:${needle}`);
  return { file, line: index + 1, ...(note ? { note } : {}) };
}
function refAfter(file: string, needle: string, after: string, note?: string): Ref {
  const start = lines(file).findIndex((s) => s.includes(after));
  const index = lines(file).findIndex((s, i) => i > start && s.includes(needle));
  if (start < 0 || index < 0)
    throw new Error(`AUDIT_REFERENCE_NOT_FOUND:${file}:${after}/${needle}`);
  return { file, line: index + 1, ...(note ? { note } : {}) };
}
const code = (name: string, needle = '') => ref(E + name + '.ts', needle);
const test = (name: string, needle = '', note = '相关测试入口；不代表本条所有条件已覆盖') =>
  ref('tests/' + name + '.test.ts', needle, note);
type Item = {
  id: string;
  category: string;
  module: string;
  subject: string;
  text: string;
  source: Ref;
  code: Ref[];
  tests: Ref[];
  status: string;
  review: string;
  issues: string[];
  constraints: {
    timing: string;
    chooser: string;
    targetsAndCounts: string;
    order: string;
    usage: string;
    visibility: string;
  };
};
const items: Item[] = [];
const staticStatus = '实现已定位，专项验收待补';
function add(
  category: string,
  module: string,
  subject: string,
  text: string,
  line: number,
  refs: Ref[],
  tests: Ref[] = [],
  review = '',
  source = sourceFile,
): Item {
  const ordinal = items.filter((i) => i.category === category).length + 1;
  const id = `${category}-${String(ordinal).padStart(3, '0')}`;
  const item: Item = {
    id,
    category,
    module,
    subject,
    text,
    source: { file: source, line },
    code: refs,
    tests,
    status: refs.length ? staticStatus : '待核对',
    review,
    issues: [],
    constraints: {
      timing:
        text.match(/【([^】]+)】/)?.[1] ??
        (category === '角色友好'
          ? '友好能力入口；剧作家使用需另检特许资格'
          : '原文所述时点；无指定时使用通用流程'),
      chooser: /队长选择|队长可以|由队长/.test(text)
        ? '队长（仅对应原文子句）'
        : category === '角色友好'
          ? '使用方；内部指定选择者按文本'
          : /制作|配置|初始区域/.test(text)
            ? '剧本配置或文本指定方'
            : '沿用来源选择方；明确例外见原文',
      targetsAndCounts: text,
      order: /随后|之后|然后|顺序/.test(text)
        ? '按原文顺序拆段；尚未开始的后段受结束要求截断'
        : '无明确先后时按同批处理；通用流程顺序另见流程清单',
      usage:
        text.match(/(?:每轮回|每轮|每日|每个回合)[^，。；】]{0,24}/)?.[0] ??
        '遵循阶段限次；明确共享、追加限次以原文或元数据为准',
      visibility: /公开|告知|宣称|秘密/.test(text)
        ? '逐字遵守原文公开对象；不外泄真实配置或幕后来源'
        : '公布可见结果，隐藏技能来源；见正文6.8',
    },
  };
  items.push(item);
  return item;
}
function splitAbilities(value: string): string[] {
  return value
    .split(/(?=【(?:强制|任意|失败|特殊胜利))/)
    .map((s) => s.replace(/^[；;\s]+|[；;\s]+$/g, ''))
    .filter(Boolean);
}
const stage = code('runtime', 'private stepFlow');
const batch = code('resolution', 'export function commitBatch');
const persistent = code('persistent', 'export function evaluatePersistent');
const native = code('native-rules', 'export function nativeForced');
const optional = code('native-rules', 'export function nativeOptional');
const validation = code('validation', 'export function validateConfiguration');
const sourceInstances = code('runtime', 'private sourceInstances');
const goodwill = code('runtime', 'private optionalInstances');
const prepare = code('runtime', 'private stepResolution');
const judge = code('incidents', 'export function judgeScheduledIncident');
const view = code('runtime', 'view(seat: SeatId)');

const identityExtra: Record<string, Ref[]> = {
  邪教徒: [code('actions', 'cultist')],
  时间旅者: [code('actions', 'time_traveler')],
  次元旅者: [code('actions', 'dimension_traveler')],
  亲友: [code('native-rules', "identity === 'friend'")],
  心上人: [code('native-rules', "['beloved', 'lover']")],
  求爱者: [code('native-rules', "['lover', 'beloved']")],
  不安定因子: [code('persistent', "c.identity === 'unstable_factor'")],
  无面者: [code('persistent', "c.identity === 'faceless'")],
  怪杰: [code('persistent', "c.identity === 'eccentric'")],
  纸老虎: [code('persistent', "c.identity === 'paper_tiger'")],
  预言家: [code('persistent', "['prophet', 'werewolf']"), judge],
  狼人: [code('persistent', "['prophet', 'werewolf']")],
  强迫症: [code('persistent', "c.identity === 'obstinate'"), validation],
  侦探: [code('persistent', "other.identity === 'detective'"), validation],
  监视者: [code('persistent', "other.identity === 'watcher'")],
  双胞胎: [code('runtime', "identity === 'twins'"), validation],
  忍者: [code('resolution', "actualIdentity === 'ninja'"), prepare],
  祭品: [judge, validation],
  丧尸: [
    code('native-rules', "identities('zombie', true)"),
    code('query', 'export function virtualCorpse'),
  ],
  目击者: [code('native-rules', "identities('witness')")],
  因果残片: [code('native-rules', "identities('causal_fragment')")],
  叙述者: [code('native-rules', "identities('narrator')")],
  童谣: [code('native-rules', "identity === 'nursery_rhyme'")],
  网络名流: [code('native-rules', "identity === 'influencer'")],
  密钥: [code('native-rules', "timing === 'identity:revealed'")],
};
const identityTests: Record<string, Ref[]> = {
  关键人物: [test('resolution', '医院事故同时'), test('regressions', '死亡触发保留')],
  亲友: [test('module-flow')],
  杀人狂: [test('resolution', '双杀人狂')],
  不安定因子: [test('persistent', '怪杰、不安定因子'), test('regressions', '死亡触发保留')],
  怪杰: [test('persistent', '怪杰、不安定因子')],
  无面者: [test('persistent', '怪杰、不安定因子')],
  纸老虎: [test('persistent', '纸老虎追加')],
  忍者: [test('regressions', '活忍者'), test('regressions', '忍者尸体')],
  愚者: [test('resolution', '医院事故同时'), test('regressions', '医院无密谋')],
  心理医生: [test('module-boundaries', '御神木和心理医生')],
  双胞胎: [test('regressions', '双胞胎按')],
  时间旅者: [test('module-boundaries', '时间旅者仅')],
  巫师: [test('regressions', 'AI巫师')],
  心上人: [test('regressions', '多个被爱者')],
  求爱者: [test('regressions', '多个被爱者')],
};
function identityRefs(name: string, text: string): Ref[] {
  const definition = Object.values(catalog.identities).find((i) => i.name === name);
  if (!definition) throw new Error(`AUDIT_IDENTITY_MISSING:${name}`);
  if (/剧本制|剧本创/.test(text)) return [validation];
  const refs = Object.values(catalog.sources)
    .filter((s) => s.instantiate?.kind === 'identity' && s.instantiate.id === definition.id)
    .map((s) => {
      const identityLines = lines(C + 'identity-sources.ts');
      const bodyStart = identityLines.findIndex((line) => line.includes('const mastermindArea'));
      const file = identityLines.some(
        (line, i) => i > bodyStart && line.includes(`'${definition.id}'`),
      )
        ? 'identity-sources.ts'
        : 'index.ts';
      return file === 'index.ts'
        ? refAfter(C + file, `'${definition.id}'`, '  identitySource(', `来源 ${s.id}`)
        : refAfter(C + file, `'${definition.id}'`, 'const mastermindArea', `来源 ${s.id}`);
    });
  return [...refs, ...(identityExtra[name] ?? []), sourceInstances];
}
const characterTraits: Record<string, Ref[]> = {
  AI: [validation, judge],
  UP主: [
    code('native-rules', "c.definitionId === 'uploader'"),
    code('runtime', 'private abilityAreas'),
  ],
  '临时工？': [
    code('state', 'TEMP_WORKER_ALT_CANNOT_BE_CONFIGURED'),
    code('runtime', "'temp_worker_alt'"),
  ],
  临时工: [
    code('persistent', "c.definitionId === 'temp_worker'"),
    code('native-rules', "c.definitionId === 'temp_worker'"),
    stage,
    judge,
  ],
  从者: [code('resolution', 'export function movementFollowers'), code('resolution', 'served-by:')],
  仙人: [
    validation,
    code('query', "c.definitionId === 'hermit'"),
    code('runtime', "owner.definitionId === 'hermit'"),
  ],
  黑猫: [
    code('native-rules', "c.definitionId === 'black_cat'"),
    code('runtime', "definitionId === 'black_cat'"),
  ],
  大人物: [validation, code('runtime', 'private abilityAreas')],
  妹妹: [validation],
  学者: [code('native-rules', "c.definitionId === 'scholar'")],
  局外人: [code('validation', "c.definitionId === 'outsider'")],
  幻想: [code('actions', 'fantasy')],
  手下: [code('runtime', 'henchman')],
  教主: [judge, code('runtime', "'cult-leader'")],
  模仿犯: [code('validation', "c.definitionId === 'copycat'")],
  神灵: [code('runtime', 'const spiritLoop'), validation],
  转校生: [code('runtime', "character.definitionId === 'transfer_student'"), validation],
  御神木: [
    code('native-rules', "c.definitionId === 'sacred_tree'"),
    optional,
    code('resolution', 'operation.sacredTree'),
  ],
};
function relevantTests(name: string): Ref[] {
  const result: Ref[] = [];
  for (const file of [
    'abilities',
    'regressions',
    'persistent',
    'module-boundaries',
    'resolution',
    'announcements',
  ]) {
    const path = `tests/${file}.test.ts`;
    lines(path).forEach((line, index) => {
      if (line.includes('it(') && line.includes(name))
        result.push({ file: path, line: index + 1, note: '相关专项，仅覆盖用例标题所述场景' });
    });
  }
  return result;
}
function ruleRefs(name: string, text: string): Ref[] {
  if (/剧本制|剧本创/.test(text)) return [validation];
  if (/失败条件/.test(text)) return [code('native-rules', name)];
  if (/特殊胜利条件[AB]/.test(text))
    return [
      code('persistent', 'export function checkStageVictory'),
      code('runtime', 'checkStageVictory(this.stateData'),
    ];
  if (/特殊胜利条件C/.test(text)) return [code('runtime', "'final_showdown'")];
  const table: Record<string, Ref[]> = {
    流言四起: [ref(C + 'index.ts', "for (const id of ['fs.x.rumors'"), optional],
    妄想扩大病毒: [code('persistent', "enabled('btx.x.delusion_virus')")],
    因果线: [code('native-rules', "enabled('因果线')")],
    因果之绊: [
      code('native-rules', "enabled('因果之绊')"),
      code('persistent', "enabled('mz.y.bond_of_fate')"),
    ],
    诸神之骰: [code('native-rules', "enabled('诸神之骰')")],
    X异因子: [code('native-rules', "rule.name === 'X异因子'")],
    心无灵犀: [code('actions', 'mutual_understanding')],
    灭亡讴歌: [judge],
    士的宁毒液: [judge],
    隔离病房惊魂记: [code('native-rules', "enabled('隔离病房惊魂记')")],
    古墓活尸: [
      code('persistent', "enabled('hsa.y.ancient_tomb')"),
      code('query', 'export function virtualCorpse'),
    ],
    被诅咒的土地: [optional, code('runtime', 'curse-no-target')],
    魔女遗咒: [optional],
    怪物们的阴谋: [code('native-rules', "rule.name === '怪物们的阴谋'")],
    深渊之都的私语: [code('persistent', 'wm.x.whispers_of_the_deep')],
    疯狂的真相: [code('native-rules', "enabled('疯狂的真相')")],
    傀儡之线: [code('persistent', 'ahr.x.puppet_strings')],
    超越世界线: [code('native-rules', "enabled('超越世界线')")],
    难以言喻的怪物: [optional],
    空想扩大病毒: [code('persistent', "enabled('ahr.x.fantasy_virus')")],
    最终计划: [code('persistent', 'll.y.final_plan'), code('runtime', "'showdown:participants'")],
    封印的终末: [code('persistent', 'll.y.sealed_end'), optional],
    恶魔的剧本: [optional],
    捏造的秘密: [validation, code('persistent', '捏造的秘密')],
  };
  return table[name] ?? [];
}

let moduleName = '通用';
let section = '';
let ruleName = '';
let ruleKind = '';
let incidentName = '';
let part = '';
const continuationLines = new Set<number>();
const tableHeaders = new Set(['类别', '内容', '类型', '身份', '名称', '角色名']);
const appendixLines = lines(sourceFile);
appendixLines.forEach((line, index) => {
  const n = index + 1;
  if (line.startsWith('## 附录A')) part = 'A';
  if (line.startsWith('## 附录B')) part = 'B';
  if (line.startsWith('## 附录C')) {
    part = 'C';
    moduleName = '通用';
  }
  if (part === 'B' && line.startsWith('### ')) moduleName = line.slice(4).trim();
  if (line.startsWith('#### ')) section = line.slice(5).trim();
  if (part === 'A' && /^- /.test(line))
    add(
      '指示物通则',
      '通用',
      '希望／绝望',
      line.slice(2),
      n,
      [persistent],
      [test('persistent', '固定种子')],
    );
  if (part === 'A' && line.startsWith('特殊：'))
    add(
      '行动规则',
      '通用',
      '移动方向合成',
      line,
      n,
      [code('actions', 'export function')],
      [test('actions')],
    );
  if (!line.startsWith('|') || /^\|\s*[-:]/.test(line)) return;
  const cells = line
    .split('|')
    .slice(1, -1)
    .map((s) => s.trim());
  if (tableHeaders.has(cells[0]!)) return;
  if (part === 'A') {
    add(
      '行动牌',
      cells[0]!,
      cells[1]!,
      `${cells[2]}；数量=${cells[3]}；每轮限次=${cells[4]}`,
      n,
      [
        code('actions', 'export function createBaseDeck'),
        code('actions', 'export function legalActionTargets'),
        batch,
      ],
      [test('actions'), test('module-boundaries', '时间旅者仅')],
      '基础牌张与限次可定位；额外牌的授予与除外另读对应模组，尚无逐牌完整结果矩阵。',
    );
  } else if (part === 'C') {
    const name = cells[0]!;
    const definition = Object.values(catalog.characters).find((c) => c.name === name)!;
    if (!definition) throw new Error(`AUDIT_CHARACTER_MISSING:${name}`);
    const metadata = add(
      '角色配置',
      '通用',
      name,
      `属性=${cells.slice(2, 4).filter(Boolean).join('、')}；初始区域=${cells[4]}；禁行=${cells[5]}；不安限度=${cells[10]}`,
      n,
      [ref(C + 'index.ts', `'${definition.id}'`), validation],
      [test('content-consistency', '37张角色')],
      '现有一致性测试核对这些静态字段；不代表动态特性已验收。',
    );
    metadata.status = '静态数据专项覆盖';
    if (cells[1]) {
      const clauses = cells[1].split(/(?<=[。；])/).filter((s) => s.trim());
      clauses.forEach((clause, i) =>
        add(
          '角色特性',
          '通用',
          `${name}·${i + 1}`,
          clause,
          n,
          characterTraits[name] ?? [],
          relevantTests(name),
          '按该角色独立特性拆句；同卡后续句仍依赖前句范围，需连同整格原文阅读。',
        ),
      );
    }
    cells.slice(6, 10).forEach((text, i) => {
      if (!text) return;
      const id = `${definition.id}.goodwill${i + 1}`;
      const source = catalog.sources[id];
      if (!source) throw new Error(`AUDIT_ABILITY_MISSING:${id}`);
      const finalOverride =
        !['male_student', 'female_student', 'soldier', 'idol', 'alien'].includes(definition.id) &&
        !(definition.id === 'doctor' && i === 0) &&
        !(definition.id === 'shrine_maiden' && i === 1) &&
        !(definition.id === 'police' && i === 1) &&
        !(definition.id === 'fantasy' && i === 1);
      const file = finalOverride ? 'character-sources.ts' : 'index.ts';
      const pointer =
        file === 'index.ts'
          ? refAfter(C + file, `'${definition.id}'`, 'const goodwill', `最终目录来源 ${id}`)
          : ref(
              C + file,
              definition.id === 'shrine_maiden' && i === 0
                ? "'shrine_maiden.goodwill1'"
                : `'${definition.id}'`,
              `最终目录来源 ${id}`,
            );
      const refs = [pointer, goodwill];
      if (source.native) refs.push(code('native-abilities', `case '${source.native}'`));
      const row = add(
        '角色友好',
        '通用',
        `${name}·能力${i + 1}`,
        `${text}；需求=${cells[11 + i]}；每轮一次=${cells[15 + i] || '否'}`,
        n,
        refs,
        [
          test('character-matrix', '角色友好能力处理器矩阵', '执行与恢复矩阵，未逐条断言所有效果'),
          ...relevantTests(name),
        ],
        `来源=${id}；${source.native ? '动态程序已接入，初始无现象模板会被编译替换。' : '已使用统一结算程序。'} 须补本条目标、限次和实际结果的专项验收。`,
      );
      row.constraints.usage = `阶段至多一次；每轮一次=${cells[15 + i] || '否'}；双方每轮限次共享`;
    });
  } else if (section === '特殊规则') {
    cells[0]!
      .split(/(?=EX[1-4]\+)|(?<=。)/)
      .filter(Boolean)
      .forEach((clause, i) =>
        add(
          '模组特殊',
          moduleName,
          `${moduleName}·${i + 1}`,
          clause,
          n,
          [ref(C + 'registry.ts', 'catalog.modules[id]'), stage, native, optional, persistent],
          [test('module-flow')],
          '已核对相应分支；同一原文格的后句继承前句对象和适用范围。整局测试仅覆盖选定配置，复合条款仍需逐条件验收。',
        ),
      );
  } else if (section === '规则') {
    if (cells[0]) ruleKind = cells[0];
    if (cells[1]) ruleName = cells[1];
    if (cells[2])
      add(
        '规则配置',
        moduleName,
        `${ruleKind}·${ruleName}`,
        `追加身份=${cells[2]}；配置=${cells[3]}`,
        n,
        [ref(C + 'registry.ts', 'roles: rule.roles.map'), validation],
        [test('content-consistency', '八模组'), test('module-flow')],
        '已登记数量与身份；模组引用检查不等于所有Y/X组合、表里例外均通过。',
      );
    else if (cells[1])
      add(
        '规则配置',
        moduleName,
        `${ruleKind}·${ruleName}`,
        '本规则不追加固定身份；效果另列。',
        n,
        [ref(C + 'registry.ts', 'catalog.rules![ruleId]'), validation],
        [test('content-consistency', '八模组')],
      );
    splitAbilities(cells[4] ?? '').forEach((text, i) =>
      add(
        '规则效果',
        moduleName,
        `${ruleName}·${i + 1}`,
        text,
        n,
        ruleRefs(ruleName, text),
        relevantTests(ruleName),
        '配置身份与追加效果分别盘点；空效果格表示只追加身份，不视为缺少技能。',
      ),
    );
  } else if (section === '身份') {
    const name = cells[0]!;
    const definition = Object.values(catalog.identities).find((i) => i.name === name)!;
    const row = add(
      '身份配置',
      moduleName,
      name,
      `人数上限=${cells[1] || '未另设'}；基础特性=${cells[2] || '无'}；能力=${cells.slice(3).filter(Boolean).length ? '另列' : '无文本能力'}`,
      n,
      [
        ref(C + 'index.ts', `'${definition.id}'`),
        ref(C + 'registry.ts', 'identityLimits:'),
        validation,
        persistent,
      ],
      [test('content-consistency', '八模组')],
      '不同模组分别登记；魔女、永生者等仅有特性不等于漏实现主动技能。',
    );
    if (!row.code.length) throw new Error('MISSING_IDENTITY_METADATA');
    cells
      .slice(3)
      .flatMap(splitAbilities)
      .forEach((text, i) =>
        add(
          '身份能力',
          moduleName,
          `${name}·${i + 1}`,
          text,
          n,
          identityRefs(name, text),
          identityTests[name] ?? [],
          '检查来源实例化以及取得其他身份能力的路径；相关测试不覆盖所有门槛、尸体和限次组合。',
        ),
      );
  } else if (section === '事件') {
    if (!cells[0]) {
      const previous = items.at(-1)!;
      if (previous.category !== '事件') throw new Error('EVENT_CONTINUATION_WITHOUT_EVENT');
      previous.text += '；' + cells.slice(1).filter(Boolean).join('；');
      previous.constraints.targetsAndCounts = previous.text;
      previous.review += ` 附录第${n}行续文已合并。`;
      continuationLines.add(n);
      return;
    }
    if (cells[0]) incidentName = cells[0];
    const definition = Object.values(catalog.incidents).find((i) => i.name === incidentName)!;
    if (!definition) throw new Error(`AUDIT_EVENT_MISSING:${incidentName}`);
    const pointer = definition.native
      ? code('native-incidents', `case '${incidentName}'`)
      : ref(C + 'index.ts', `'${definition.id}'`);
    add(
      '事件',
      moduleName,
      incidentName,
      cells.slice(1).filter(Boolean).join('；'),
      n,
      [pointer, judge, prepare],
      [
        test('incident-matrix', 'it(', '执行与恢复矩阵；不证明每个效果和特殊分支正确'),
        ...relevantTests(incidentName),
      ],
      `来源=${definition.id}；同名事件按模组保留独立行；“随后”仍属于同一来源的多个步骤。`,
    );
  }
});

// The complete source text remains in the inventory; the index does not reinterpret prose.
function route(text: string, heading: string): { refs: Ref[]; tests: Ref[] } {
  const all = heading + ' ' + text;
  if (/制作|开局|校验|公开表/.test(all))
    return {
      refs: [validation, code('state', 'validateNewGame'), view],
      tests: [test('content-consistency'), test('module-boundaries', '剧本不能')],
    };
  if (/常驻|有效友好|有效不安|有效密谋|希望.*绝望|背叛者资格/.test(all))
    return {
      refs: [persistent, code('persistent', 'checkStageVictory')],
      tests: [test('persistent'), test('resolution', '阶段入口')],
    };
  if (/行动牌|行动结算|行动阶段|回收|合成|旧印/.test(all))
    return {
      refs: [code('actions', 'createBaseDeck'), stage, batch],
      tests: [test('actions'), test('announcements')],
    };
  if (/事件|当事人|AI/.test(all))
    return {
      refs: [judge, code('native-incidents', 'incidentProgram'), prepare],
      tests: [test('incident-matrix'), test('module-boundaries')],
    };
  if (/身份|友好能力|技能|限次|御神木|能力阶段/.test(all))
    return {
      refs: [sourceInstances, goodwill, prepare],
      tests: [test('abilities'), test('character-matrix')],
    };
  if (/死亡|护卫|不死|复活|替代|从者/.test(all))
    return { refs: [batch, native, prepare], tests: [test('resolution'), test('regressions')] };
  if (/公开|秘密|信息|公告/.test(all))
    return {
      refs: [view, code('runtime', 'private publishBatch')],
      tests: [test('announcements'), test('protocol')],
    };
  if (/指示物|目标|对象|数量|区域|版图/.test(all))
    return {
      refs: [code('query', 'selectCandidates'), batch, prepare],
      tests: [test('resolution'), test('persistent')],
    };
  return { refs: [stage, prepare, native], tests: [test('flow'), test('module-flow')] };
}
const general: Item[] = [];
for (const filename of [
  '../tragedy_loop_game_rules(3)(1).md',
  '../全阶段逻辑样例.md',
  '../事件阶段逻辑样例.md',
  '../步骤结算流程（独立稿）.md',
]) {
  let heading = '';
  let inMermaid = false;
  let glossary = false;
  const isRules = filename.includes('game_rules');
  lines(filename).forEach((line, index) => {
    const trimmed = line.trim();
    if (/^#{1,6} /.test(trimmed)) {
      heading = trimmed.replace(/^#+\s*/, '');
      if (heading.includes('术语表')) glossary = true;
      return;
    }
    if (trimmed.startsWith('```')) {
      inMermaid = !inMermaid;
      return;
    }
    if (!trimmed || /^(---|flowchart |end$|subgraph )/.test(trimmed)) return;
    if (
      !heading ||
      heading === '目录' ||
      /依据/.test(heading) ||
      trimmed.startsWith('>') ||
      trimmed.startsWith('[返回')
    )
      return;
    if (/^\|\s*[-:]/.test(trimmed)) return;
    if (/^\| (序号|对象|原编号|术语|关键词|情况|状态或记录|当前结果|本稿部分) \|/.test(trimmed))
      return;
    if (trimmed.startsWith('依据：') || trimmed.startsWith('FAQ：')) return;
    const category = inMermaid
      ? '流程节点与连线'
      : glossary && isRules
        ? '术语对照'
        : isRules
          ? '正文条款'
          : '流程执行注';
    const routed = route(trimmed, heading);
    const row = add(
      category,
      isRules ? '正文' : filename.replace('../', '').replace('.md', ''),
      heading,
      trimmed,
      index + 1,
      routed.refs,
      routed.tests,
      '已建立来源到执行层的索引；本条全部路径和边界未逐项动态验证。',
      filename,
    );
    // These rows are a requirements index, not a claim that the whole graph was proven correct.
    row.status = '流程已定位，逐路径验收待补';
    general.push(row);
  });
}

// Explicit review exceptions; these override broad routing statuses.
for (const row of items) {
  if (
    (row.subject.includes('怪物们的阴谋') && row.category === '规则效果') ||
    (row.subject.startsWith('纸老虎') && row.category === '身份能力')
  )
    row.issues.push('P0-01');
  if (
    (row.subject.startsWith('丧尸') && /移动/.test(row.text)) ||
    (row.subject.startsWith('古墓活尸') && row.category === '规则效果')
  )
    row.issues.push('P0-02');
  if (
    (row.subject.startsWith('妹妹') && row.category === '角色友好') ||
    (row.category.startsWith('流程') && /妹妹|合法.*沟通/.test(row.text))
  )
    row.issues.push('P0-03');
  if (
    row.category === '正文条款' &&
    /剧本名称不公开|是否允许商议|剧本特殊规则|公开特殊信息/.test(row.text)
  )
    row.issues.push('P0-04');
  if (row.issues.length) {
    row.status = '处理意见专项覆盖';
    row.tests.push(ref('tests/p0-rulings.test.ts'));
    row.review += ' 对应P0处理意见已落实并补专项断言；仅验收该问题范围，不代表本条全部交互已验收。';
  }
  if (row.subject.startsWith('纸老虎') && row.issues.includes('P0-01'))
    row.review += ' 怪物们的阴谋已读取最终有效特性，纸老虎条件变化及希望优先压制已覆盖。';
  if (row.subject.startsWith('古墓活尸') && row.issues.includes('P0-02'))
    row.review += ' 仅牺牲者丧尸的移动入口、共享每日限次、版图密谋上限及恢复已覆盖。';
  if (row.issues.includes('P0-03'))
    row.review += ' 依用户裁定：成人能力无合法对象不阻止妹妹自身发动、沟通与完成；原缺陷判定撤回。';
  if (row.subject.startsWith('因果线') || /因果线/.test(row.text))
    row.review += ' 因果线按有效友好判定，只有希望也计入。';
  if (row.category === '正文条款' && /没有角色卡，也不能复活/.test(row.text))
    row.review += ' 资料冲突：全阶段图明确可用复活移除牺牲者密谋；实现采用流程图。';
  if (row.subject.startsWith('御神木') || /御神木.*时机任意/.test(row.text))
    row.review += ' 裁定：全阶段图要求剧作家阶段并入强制批次，双方每日分别限次。';
  if (row.subject === '灭绝之火')
    row.review += ' 已覆盖AI调用不满足首次发生、也不占用后续真实事件首次记录。';
  if (row.subject === '奇点')
    row.review += ' 待验证：表/里、首次/再次、AI入口分别断言；不借执行矩阵宣告正确。';
  if (row.category === '模组特殊' && /主题|基础游戏模组/.test(row.text)) {
    row.status = '说明性条目';
    row.review = '题材或目录说明，无独立发动效果；涉及EX牌的实际规则另列。';
  }
}

const content = items.filter((item) => !general.includes(item));
const count = (values: Item[], field: 'category' | 'status' | 'module') =>
  Object.fromEntries(
    [...new Set(values.map((i) => i[field]))].map((key) => [
      key,
      values.filter((i) => i[field] === key).length,
    ]),
  );
const inputFiles = [
  sourceFile,
  '../tragedy_loop_game_rules(3)(1).md',
  '../全阶段逻辑样例.md',
  '../事件阶段逻辑样例.md',
  '../步骤结算流程（独立稿）.md',
];
const payload = {
  date: '2026-09-26',
  stage: 'P0 inventory and static review; not full semantic acceptance',
  sourceHashes: Object.fromEntries(
    inputFiles.map((file) => [
      file,
      createHash('sha256').update(lines(file).join('\n')).digest('hex'),
    ]),
  ),
  counts: {
    content: count(content, 'category'),
    contentStatus: count(content, 'status'),
    requirements: count(general, 'category'),
  },
  entries: items,
};

// Each concrete appendix table row must appear, including zero-active-ability identities.
const coveredLines = new Set(content.map((item) => item.source.line));
for (let i = 0; i < appendixLines.length; i++) {
  const line = appendixLines[i]!;
  if (!line.startsWith('|') || /^\|\s*[-:]/.test(line)) continue;
  const first = line.split('|')[1]!.trim();
  if (tableHeaders.has(first)) continue;
  if (!coveredLines.has(i + 1) && !continuationLines.has(i + 1))
    throw new Error(`UNCOVERED_APPENDIX_ROW:${i + 1}`);
}
if (
  content.filter((i) => i.category === '角色配置').length !== 37 ||
  content.filter((i) => i.category === '角色友好').length !== 46 ||
  new Set(content.filter((i) => i.category === '事件').map((i) => i.module + ':' + i.subject))
    .size !== appendix.modules.reduce((sum, m) => sum + m.incidents.length, 0)
)
  throw new Error(`AUDIT_COUNT_MISMATCH:${JSON.stringify(payload.counts)}`);
const escape = (s: string) =>
  s.replace(/\|/g, '｜').replace(/\r?\n/g, ' ').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function link(r: Ref, label?: string): string {
  const target = fileURLToPath(new URL(r.file, root)).replace(/\\/g, '/');
  return `[${label ?? r.file.split('/').at(-1)}:${r.line}](<${target}:${r.line}>)`;
}
function table(rows: Item[]): string {
  return (
    '| 编号 / 条目 | 原文与约束 | 实现入口 | 测试证据 | 状态 / 复核备注 |\n| --- | --- | --- | --- | --- |\n' +
    rows
      .map(
        (row) =>
          `| ${row.id} ${escape(row.subject)} | ${link(row.source, '原文')} ${escape(row.text)} | ${
            row.code
              .map((r) => link(r))
              .filter((v, i, a) => a.indexOf(v) === i)
              .join('；') || '尚未定位'
          } | ${row.tests.map((r) => link(r) + (r.note?.startsWith('执行') ? '（执行矩阵）' : '')).join('；') || '无已定位的条目专项'} | ${row.status}${row.issues.length ? '：' + row.issues.join('、') : ''}。${escape(row.review)} |`,
      )
      .join('\n') +
    '\n'
  );
}
// Keep the reviewed overview and user rulings; regenerate only the source inventory.
const reviewedAudit = readFileSync(new URL('docs/content-audit.md', root), 'utf8');
const inventoryMarker = '## 附录逐项清单';
if (!reviewedAudit.includes(inventoryMarker)) throw new Error('AUDIT_OVERVIEW_MISSING');
let md = reviewedAudit.slice(0, reviewedAudit.indexOf(inventoryMarker)).trimEnd();
md += '\n\n' + inventoryMarker + '\n';
for (const category of [...new Set(content.map((i) => i.category))]) {
  md += `\n### ${category}\n\n`;
  const rows = content.filter((i) => i.category === category);
  for (const module of [...new Set(rows.map((i) => i.module))])
    md += `\n#### ${module}\n\n${table(rows.filter((i) => i.module === module))}`;
}
let flowMd =
  '# P0 正文与流程来源索引\n\n与 [主盘点](content-audit.md) 配套。每个正文非空条款、术语行、流程声明/连线和执行注保留来源位置与原文，排除目录、格式行和纯引用。相同规则的重复表述不合并，以便查漏；连线不是额外技能。代码为人工选定的执行层路由，测试为相关入口，不表示逐路径验收完成。\n\n';
for (const module of [...new Set(general.map((i) => i.module))]) {
  flowMd += `\n## ${module}\n`;
  const rows = general.filter((i) => i.module === module);
  for (const heading of [...new Set(rows.map((i) => i.subject))])
    flowMd += `\n### ${heading}\n\n${table(rows.filter((i) => i.subject === heading))}`;
}
writeFileSync(new URL('docs/content-audit.json', root), JSON.stringify(payload, null, 2) + '\n');
writeFileSync(new URL('docs/content-audit.md', root), md);
writeFileSync(new URL('docs/content-audit-flow.md', root), flowMd);
console.log(
  JSON.stringify(
    {
      ...payload.counts,
      total: items.length,
      unlocatedContent: content.filter((i) => !i.code.length).map((i) => i.id + ':' + i.subject),
    },
    null,
    2,
  ),
);
