# 工作进度断点

日期：2026-04-26

## 当前状态

- Phase 7 前四项已在测试界面完成收口：
  - `模组`、`规则`、`身份`、`事件` 已完成测试界面验证。
  - “剧本制作时”类规则与角色约束不再阻塞测试界面，转到正式版建局流程验证。
- 当前主瓶颈已切换为 `角色实现`：
  - `data/characters.json` 共 `37` 个角色。
  - 当前已有 `33` 个角色完成 `goodwill_abilities` 结构化迁移，当前仅 `hermit` 仍未迁。
  - 本轮新增 `6` 个 **data-only** 结构化迁移角色：
    - `ai`、`streamer`、`servant`、`sister`
    - `informant`、`copycat`
  - 上述 `6` 个角色本轮**不新增引擎功能**，仅把旧文本 / 门槛 / 次数限制迁入结构化字段，运行时仍保持 legacy 期间的空 `effects` 语义。
  - `appraiser` 已从 data-only 移出：
    - 友好2（公开尸体身份）已接线并通过验收
    - 友好1 仍待 `MOVE_TOKEN`
  - 旧三字段与运行时 fallback 仍保留，后续语义补齐前不会被这轮改动打断。
- 本轮角色侧新增 / 补齐的通用能力基础：
  - selector：`same_area_any_or_board`、`same_area_attribute:*`、`same_area_limit_reached_other`、`same_area_dead_character`、`any_other_character`、`any_character_limit_reached`、`any_dead_character`、`identity:*`
  - effect：`protagonist_protect`、`lift_forbidden_areas`、`revive_character`
  - 选择输入：`choose_token_type`、`choose_place_or_remove`
  - 可选能力无合法目标时会自动隐藏
  - 修复了“唯一目标自动选定后，后续 mode/token 选择被跳过”的结算链问题
- 今天已额外完成并回归的角色能力：
  - `phantom` 友好1、`little_girl` 友好2：移动能力统一走 `GameState.move_character()`
  - `detective` 友好1、`deity` 友好1：公开当事人统一输出 `XXX事件的当事人是XXX`，并已接入 UI 弹框
  - `alien` 友好1、友好2：已验证分别走统一死亡链 `DeathResolver.process_death()` 与复活 effect，且能实际改写角色存亡状态
- 角色阶段的判断口径已进一步明确：
  - “友好能力结构化迁移完成” ≠ “角色整体完成”
  - 仍需单独考虑 `trait_rule`、延迟登场、禁行区域、事件代打、信息边界
  - 详细清单见 `docs/phase7_goodwill_structured_migration.md`

## 下一步建议

1. `hermit` 仍未迁，当前按你的要求继续暂缓。
2. 下一步若允许补引擎语义，优先处理：
   - `streamer`
   - `appraiser`
   - `ai`
   - `servant`
   - `informant`
   - `copycat`
3. 保持“迁一批，测一批”：
   - 角色能力优先补到专门回归文件
   - 调试面板只做辅助确认，不再作为唯一验收依据
   - 已完成的公开身份 / 公开当事人 / 移动 / 死亡 / 复活能力都优先沿用统一 effect 入口，不再单角色分叉
4. 等语义补齐覆盖率足够后，再统一删除 legacy goodwill fallback

## 关键文件

- `PLAN.md`：Phase 7 已改为“前四项测试收口 + 角色实现”。
- `PHASE7_GAP_CHECKLIST.md`：前四项测试已记为完成，角色部分改为分批实现清单。
- `docs/phase7_goodwill_structured_migration.md`：本轮角色友好能力结构化迁移记录。
- `data/characters.json`：角色数据基表，当前共 `37` 个角色。
- `engine/resolvers/ability_resolver.py`：角色能力候选收集、条件求值与新 selector 解析入口。
- `engine/phases/phase_base.py`：角色能力声明 / 目标选择 / mode、token 输入链入口。
- `engine/rules/script_validator.py`：剧本制作时约束统一入口。
