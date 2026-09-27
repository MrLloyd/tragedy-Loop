import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createCatalog, firstStepsScenario } from '../packages/content/src/index.js';
import { validateNewGame } from '../packages/engine/src/state.js';

const manifest = JSON.parse(
  readFileSync(new URL('../docs/rule-baseline.json', import.meta.url), 'utf8'),
) as { files: { path: string; sha256: string }[] };
for (const file of manifest.files) {
  const path = fileURLToPath(new URL(`../../${file.path}`, import.meta.url));
  const text = readFileSync(path, 'utf8')
    .replace(/^\uFEFF/, '')
    .replace(/\r\n/g, '\n');
  const hash = createHash('sha256').update(text, 'utf8').digest('hex');
  if (hash !== file.sha256) throw new Error(`规则基线已变化，请复核并更新映射：${file.path}`);
}
const errors = validateNewGame(firstStepsScenario(), createCatalog());
if (errors.length) throw new Error(errors.join(','));
console.log(`规则基线校验通过：${manifest.files.length} 份规则文件；流程引擎样例配置有效。`);
