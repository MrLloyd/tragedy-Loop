# 轮回规则引擎 · 流程重构版 v2

按全阶段图、事件阶段图与独立步骤稿重写的无界面规则引擎。保留 TypeScript strict、pnpm workspace、Zod、Vitest 框架。玩家仅提交选择，引擎自行推进阶段和结算后续。

当前已接入八个模组的规则、身份、事件和角色内容，并有各模组合法配置的整局测试；这不等于所有规则交叉组合已经逐条验收。具体证据和剩余边界见 [进度记录](docs/progress.md)。

## 运行

在本目录 PowerShell 中执行：

```powershell
.\run.ps1 check
.\run.ps1 demo
```

需要 Node.js 22 或更新版本。启动器优先选择本机 Codex 附带的 Node；已安装依赖时直接调用实际检查程序，不通过备用包管理器转发。首次安装可使用 `pnpm install --frozen-lockfile`。其他环境使用 `pnpm check` 和 `pnpm demo`。演示与测试不需要模型密钥或网络。

`check` 依次执行五份源文档指纹检查、格式检查、严格类型检查和测试。演示是 First Steps 自动选择走完一局，不是游戏界面，也不是智能玩家。

## 使用

```ts
import { Engine, createGame } from './packages/engine/src/index.js';
import { createCatalog, firstStepsScenario } from './packages/content/src/index.js';

const catalog = createCatalog();
const engine = new Engine(createGame(firstStepsScenario(), catalog), catalog);
engine.start(); // 无须宿主手动指定阶段或来源

const waiting = engine.waiting; // 仅供可信宿主，玩家用 view(seat).waiting
if (waiting) {
  const receipt = engine.submit(waiting.actor, {
    protocolVersion: 2,
    sessionId: 'local',
    branchId: 'main',
    commandId: 'example-command-1',
    expectedRevision: waiting.revision,
    waitingInputId: waiting.id,
    command: {
      kind: 'choose',
      optionIds: waiting.options.slice(0, waiting.minSelections).map((o) => o.id),
    },
  });
}

const saved = engine.serialize(); // 含秘密和执行栈，只能保存于宿主
const restored = Engine.restore(saved, catalog);
const playerView = restored.view('protagonistA');
```

公开视图只包含公开盘面、公开事件表、本席手牌、本席秘密字母及本席当前选择。实际事件名、当事人、未公开身份、内部来源和原始存档不能发给玩家。

## 实现入口

- `packages/contracts`：选择命令、席位视图和本机传输契约。
- `packages/engine`：自主阶段机、同时批次、常驻派生、死亡保护与替代、事件、延迟任务、轮回重置、最终决战、存档。
- `packages/content`：八模组内容表、身份和角色能力；`appendix-data.json` 从本地附录导入。
- `packages/transport`：由宿主绑定席位的本机适配器；不是远端认证服务。
- `tests`：动作、结算、能力、模组边界、完整流程和恢复测试。
- [流程映射](docs/flow-implementation.md)、[裁定及信任边界](docs/rulings.md)、[内容与测试映射](docs/rule-index.md)、[公开日志](docs/public-announcement-plan.md)。

v1 的 `start(sources)`、`beginLoopEnd`、`announcementsFor` 等接口不再适用。存档版本为 2；不承诺迁移旧模型存档。UI、网络服务器、数据库和模型玩家不属于本轮规则内核重构。
