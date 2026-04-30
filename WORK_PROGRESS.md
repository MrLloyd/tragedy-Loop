# 工作进度断点

日期：2026-04-28

## 当前状态

- Phase 7 前四项仍保持收口状态：
  - `模组`、`规则`、`身份`、`事件` 已完成测试界面验证。
  - “剧本制作时”类规则与角色约束继续转由正式版建局流程回归。
- 本轮新增的核心收口是 `剧本公开 / 非公开信息表边界`：
  - `Script` 已拆成 `public_table` 与 `private_table`。
  - 运行时真值统一读取 `private_table`；`public_table` 只用于主人公阅读与少数明确例外。
  - `UI / Visibility` 统一展示 `public_table`，调试快照同步区分公开 / 非公开脚本。
  - 公开事件到真实事件新增 `public_incident_refs`；未显式填写时按私有事件同索引回退。
- 本轮已完成并回归的角色专项：
  - `ai` 友好1：从公开信息表选事件，映射到私有真实事件执行，仅处理效果，不记为事件已发生。
  - `informant` 友好1：主人公先选已选规则 `X`，剧作家公开另一条；`First Steps` 维持直接公开特判。
  - `appraiser` 友好1：先选同区域两名角色，再在两者之间移动一枚指示物；只有两者都无指示物时才无效果。
- 已完成的公开身份 / 公开当事人 / 移动 / 死亡 / 复活能力都优先沿用统一 `effect` 入口，不再单角色分叉。
- 角色阶段判断口径继续保持：
  - “友好能力结构化迁移完成” 不等于 “角色整体完成”。
  - 仍需单独考虑 `trait_rule`、延迟登场、禁行区域、Ex 牌、事件覆写与更大范围信息边界回归。
- 本轮已补齐的测试覆盖：
  - `tests/test_phase4_handlers.py`：`AI / informant / appraiser`
  - `tests/test_incident_handler.py`：`resolve_effect_only()`
  - `tests/test_module_apply.py`：公开 / 非公开剧本表读取边界

## 下一步建议

1. `hermit` 仍未迁，当前继续暂缓。
2. 下一步若继续补角色语义，优先处理：
   - `streamer`
   - `servant`
   - `sister`
   - `copycat`
   - `scholar`
3. 继续做“迁一批，测一批”：
   - 角色能力优先补到专门回归文件
   - 调试面板只做辅助确认，不再作为唯一验收依据
   - 运行时默认继续遵守“除非另有说明，一切剧本真值从非公开信息表读取”
4. 等语义补齐覆盖率足够后，再统一删除 legacy goodwill fallback

## 关键文件

- `PLAN.md`：Phase 7 已改为“前四项测试收口 + 角色实现”。
- `PHASE7_GAP_CHECKLIST.md`：前四项测试已记为完成，角色部分改为分批实现清单。
- `docs/phase7_goodwill_structured_migration.md`：本轮角色友好能力结构化迁移记录。
- `data/characters.json`：角色数据基表，当前共 `37` 个角色。
- `engine/models/script.py`：公开 / 非公开剧本表拆分与映射回退入口。
- `engine/resolvers/ability_resolver.py`：角色能力候选收集、条件求值与新 selector 解析入口。
- `engine/phases/phase_base.py`：角色能力声明 / 目标选择 / mode、token 输入链入口。
- `engine/resolvers/incident_resolver.py`：事件 effect-only 执行入口。
- `engine/rules/script_validator.py`：剧本制作时约束统一入口。
