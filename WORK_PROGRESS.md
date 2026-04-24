# 工作进度断点

日期：2026-04-24

## 当前状态

- 已固定一条不要轻易修改的死亡触发结算语义：
  - 同一批次死亡必须完整触发全部死亡效果。
  - 同一批次死亡角色在触发死亡效果时，状态仍按“已死亡”处理，不额外回滚到活体视角。
  - 先后死亡严格按批次分开；先死者不会被后死者当作普通活体目标，除非规则明确写尸体目标。
  - 触发能力仍保留 `sequential` / 非 `sequential` 的原语义。
- 已重新核对 `FS / BTX` 模组层实际状态：
  - 规则、身份、事件条目都已录入，当前没有确认未实现的 FS / BTX 规则或身份条目。
  - `witch`、`unstable_factor`、`friend`、`beloved / lover`、`disappearance`、`butterfly_effect`、`long_range_murder` 均已有实现与回归。
  - 主缺口已从模组层转移到角色层结构化。
- 已重写 `PHASE7_GAP_CHECKLIST.md`，改为反映当前真实状态：
  - 模组层基本完成。
  - 角色层旧字段与文本特性仍未完成结构化。
- 已删除模块数据中纯重复说明的顶层 `description`：
  - `fs_revenge_kindling`
  - `fs_protect_this_place`
  - `fs_darkest_script`
  - `btx_giant_time_bomb_x`
  - `btx_causal_line`
  - `btx_delusion_spread_virus`
- 角色层当前仍保留的兼容路径：
  - `data/characters.json` 仍主要使用 `trait_rule` 与 `goodwill_ability_*` 旧字段。
  - `engine/rules/character_loader.py` 仍会把旧字段转换为 `goodwill_abilities`。
  - `engine/resolvers/ability_resolver.py` 仍保留旧字段 fallback。
  - `engine/validation/static_data.py` 仍允许并校验旧字段。
  - `collect_character_abilities()` 仍是兼容别名，公开统一入口已是 `collect_abilities()`。

## 今日关键验证

- `python3 -m engine.validation`
- `pytest -q tests/test_phase1_core.py tests/test_ability_resolver.py tests/test_phase4_handlers.py tests/test_phase4_p4_5_p4_6.py tests/test_incident_handler.py`
- 结果：全部通过。

## 明天继续建议

1. 继续 Phase 7 的角色层结构化：
   - 把 `goodwill_ability_*` 旧三字段迁移到 `goodwill_abilities`。
   - 让测试逐步改为直接覆盖结构化友好能力。
2. 拆分 `trait_rule`：
   - 优先抽出 `script_constraints`。
   - 再抽 `character_abilities` / `loop_start_effects` / `turn_end_effects` / `incident_modifiers`。
3. 清理兼容层：
   - 删除 loader / resolver / validation 的旧字段 fallback。
   - 最后下线 `collect_character_abilities()`。
4. 如需继续补强测试，再补“每条规则一条显式专测”的对表矩阵；这已不是阻塞项。

## 关键文件

- `PLAN.md`：Phase 7 执行顺序已调整。
- `PHASE7_GAP_CHECKLIST.md`：已改为当前真实缺口清单。
- `data/modules/first_steps.json`：已删除冗余规则顶层 `description`。
- `data/modules/basic_tragedy_x.json`：已删除冗余规则顶层 `description`。
- `engine/rules/character_loader.py`：角色旧字段迁移入口。
- `engine/resolvers/ability_resolver.py`：统一能力入口与旧字段兼容路径。
- `engine/validation/static_data.py`：角色旧字段仍在此处校验。
