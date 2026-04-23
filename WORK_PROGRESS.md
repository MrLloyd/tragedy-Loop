# 工作进度断点

日期：2026-04-23

## 当前状态

- 游戏主流程已基本跑通，Phase 7 已改为优先收敛 `First Steps` / `Basic Tragedy X` 的模组规则能力与身份能力。
- 已重写 `PHASE7_GAP_CHECKLIST.md`，按“已结构化 / 半结构化 / 未结构化”重新整理 FS / BTX 的规则、身份、事件与角色层缺口。
- 已调整 `PLAN.md` 的 Phase 7 顺序：
  1. 先完成 FS / BTX 模组规则能力。
  2. 再完成 FS / BTX 模组身份能力。
  3. 然后补事件解释回归。
  4. 最后处理角色友好能力与角色特性结构化。
- 已修正 `long_range_murder`：
  - 远距离杀人现在只能从拥有 2 枚或以上密谋的角色中选择死亡目标。
  - `token_check` 已支持 `target = "other"` 指向当前候选角色。
- 已将 `btx_causal_line` 从阶段硬编码迁移为规则能力：
  - `loop_start` 时通过规则能力给上轮结束时带友好的角色放置 2 枚不安。
  - 使用受控约定字符串 `last_loop_goodwill_characters`。
- 已将 `unstable_factor` 的动态能力迁移为身份数据：
  - `derived_identities` 显式声明学校 2+ 密谋获得传谣人能力。
  - `derived_identities` 显式声明都市 2+ 密谋获得关键人物能力。

## 今日关键验证

- `python3 -m engine.validation`
- `pytest -q tests/test_incident_handler.py`
- `pytest -q tests/test_ability_resolver.py tests/test_phase4_handlers.py tests/test_phase4_p4_5_p4_6.py tests/test_incident_handler.py`
- 结果：全部通过，最后一组为 `62 passed`。

## 明天继续建议

1. 继续 Phase 7 的模组身份能力回归：
   - `witch`：补“必定无视友好”显式测试。
   - `friend`：确认公开身份后的主人公可见快照已覆盖足够。
   - `beloved` / `lover`：补同时死亡与先后死亡触发链回归。
2. 补 FS / BTX 规则对表测试：
   - 纯身份槽规则：合法 / 非法剧本校验。
   - 失败条件规则：`loop_end` 触发回归。
   - 剧作家能力规则：目标、时机、限次回归。
3. 继续事件解释回归：
   - `disappearance`：剧作家选择目标版图。
   - `butterfly_effect`：选择指示物类型并触发 `btx_change_future`。
   - `long_range_murder`：已补目标过滤，后续可补 UI/WaitForInput 层验证。
4. 模组规则/身份完成后，再处理角色层：
   - `goodwill_ability_*` 旧三字段迁移到 `goodwill_abilities`。
   - `trait_rule` 拆成结构化特性、能力或剧本制作约束。

## 关键文件

- `PLAN.md`：Phase 7 执行顺序已调整。
- `PHASE7_GAP_CHECKLIST.md`：Phase 7 新缺口清单与优先级。
- `data/modules/basic_tragedy_x.json`：`btx_causal_line` 规则能力与 `unstable_factor.derived_identities`。
- `engine/models/identity.py`：新增 `DerivedIdentityRule`。
- `engine/rules/module_loader.py`：加载 `derived_identities`。
- `engine/resolvers/ability_resolver.py`：派生身份能力改为读取数据，并修正 `token_check other`。
- `engine/resolvers/atomic_resolver.py`：支持 `last_loop_goodwill_characters` 目标。
- `engine/phases/phase_base.py`：移除 `btx_causal_line` 阶段硬编码。
- `engine/validation/modules.py`：校验 `derived_identities`。
- `tests/test_ability_resolver.py`：新增结构化数据回归。
- `tests/test_incident_handler.py`：新增远距离杀人目标过滤回归。
