# 惨剧轮回：计划与代码映射（文档索引版）

本文件的目标不是复述架构，而是把“文档里的条目”尽量直接落到“仓库里的代码入口”。

维护原则：

- `PLAN.md` 继续作为阶段状态单一事实源。
- 规则语义优先看 `tragedy_loop_game_rules.md` 与 `tragedy_loop_appendix.md`。
- 规则到代码的具体落点，优先看 `docs/rules_to_engine_mapping.md`。
- UI 表现与输入回传，优先看 `docs/rules_to_ui_mapping.md` 和 `docs/engine_ui_boundary_mapping.md`。
- 本文件只做“导航索引”，不重复展开规则细节。

---

## 1. 文档入口总表

| 文档 | 主要用途 | 先看什么 |
|------|----------|---------|
| [`PLAN.md`](PLAN.md) | 项目阶段、DoD、开发顺序 | §2 开发阶段、§3 规则边界案例 |
| `tragedy_loop_game_rules.md` | 规则正文 | 规则名、时机、效果、边界描述 |
| `tragedy_loop_appendix.md` | 附录 / 模组条目事实源 | FS / BTX 的条目与数量 |
| [`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) | 规则语义 → `engine/` | 第 2 - 7 节 |
| [`docs/rules_to_ui_mapping.md`](docs/rules_to_ui_mapping.md) | 规则语义 → `ui/` | 第 2 - 8 节 |
| [`docs/engine_ui_boundary_mapping.md`](docs/engine_ui_boundary_mapping.md) | `engine/` ↔ `ui/` 中间层 | 第 2 - 7 节 |
| [`PHASE7_GAP_CHECKLIST.md`](PHASE7_GAP_CHECKLIST.md) | Phase 7 缺口清单 | FS / BTX 角色与规则缺口 |
| [`WORK_PROGRESS.md`](WORK_PROGRESS.md) | 当前断点 | 最近一次工作记录 |

---

## 2. 文档到代码的主索引

### 2.1 `PLAN.md` → 代码

#### §1 项目目录结构

| `PLAN.md` 条目 | 代码入口 |
|----------------|----------|
| `data/` 静态配置 | `data/board.json`、`data/cards.json`、`data/characters.json`、`data/modules/*.json` |
| `engine/` 核心引擎 | `engine/state_machine.py`、`engine/game_state.py`、`engine/game_controller.py` |
| `engine/models/` 领域模型 | `engine/models/enums.py`、`character.py`、`board.py`、`cards.py`、`script.py`、`incident.py`、`identity.py`、`ability.py`、`effects.py`、`selectors.py` |
| `engine/resolvers/` 结算层 | `atomic_resolver.py`、`ability_resolver.py`、`incident_resolver.py`、`death_resolver.py` |
| `engine/rules/` 数据装配 | `module_loader.py`、`script_validator.py`、`character_loader.py`、`identity_registry.py`、`incident_registry.py`、`runtime_traits.py`、`runtime_identities.py`、`persistent_effects.py` |
| `engine/phases/` 阶段层 | `phase_base.py` |
| `ui/` 前端 | `ui/app.py`、`ui/main_window.py`、`ui/screens/*.py`、`ui/controllers/*.py` |
| `tests/` 回归测试 | `tests/test_*.py` |

#### §2 开发阶段

| `PLAN.md` Phase | 代码入口 |
|-----------------|----------|
| Phase 0 数据与契约 | `data/*.json`、`engine/validation/*`、`tests/test_data_validation.py` |
| Phase 1 状态机与核心引擎 | `engine/state_machine.py`、`engine/game_controller.py`、`engine/game_state.py`、`engine/phases/phase_base.py`、`engine/resolvers/atomic_resolver.py`、`engine/resolvers/death_resolver.py`、`engine/event_bus.py`、`engine/visibility.py`、`tests/test_wait_for_input_loop.py`、`tests/test_incident_handler.py`、`tests/test_phase1_core.py` |
| Phase 2 模组加载与注册表 | `engine/rules/module_loader.py`、`engine/rules/script_validator.py`、`engine/rules/identity_registry.py`、`engine/rules/incident_registry.py`、`engine/rules/character_loader.py`、`tests/test_registry_loader.py`、`tests/test_module_apply.py`、`tests/test_validation_loader_integration.py` |
| Phase 3 行动牌系统 | `engine/models/cards.py`、`engine/phases/phase_base.py`、`engine/resolvers/atomic_resolver.py`、`tests/test_action_card_system.py` |
| Phase 4 身份 / 能力 / 事件 | `engine/models/identity.py`、`engine/models/incident.py`、`engine/models/ability.py`、`engine/models/effects.py`、`engine/resolvers/ability_resolver.py`、`engine/resolvers/incident_resolver.py`、`engine/rules/runtime_traits.py`、`engine/rules/runtime_identities.py`、`engine/rules/persistent_effects.py`、`tests/test_ability_resolver.py`、`tests/test_character_loader.py`、`tests/test_phase4_handlers.py`、`tests/test_phase4_p4_5_p4_6.py` |
| Phase 5 基础 UI | `ui/app.py`、`ui/main_window.py`、`ui/screens/title_screen.py`、`ui/screens/new_game_screen.py`、`ui/screens/game_screen.py`、`ui/screens/result_screen.py`、`ui/controllers/new_game_controller.py`、`ui/controllers/game_session_controller.py`、`tests/test_ui_new_game_controller.py`、`tests/test_ui_game_screen_model.py`、`tests/test_ui_main_window_flow.py`、`tests/test_ui_session_smoke.py` |
| Phase 6 端到端可玩 | `ui/` + `engine/` 闭环整体；优先看 `tests/test_first_steps_smoke_scenario.py`、`tests/test_test_mode_controller.py` |
| Phase 7 缺口收敛 | `PHASE7_GAP_CHECKLIST.md`、`docs/phase7_goodwill_structured_migration.md`、`tests/test_goodwill_structured_migration.py`、`tests/test_phase5_first_steps_abilities.py` |

#### §3 规则边界案例

| `PLAN.md` 条目 | 代码入口 |
|----------------|----------|
| 3.1 原子结算与同时裁定 | `engine/resolvers/atomic_resolver.py` |
| 3.2 医院事故多人死亡 | `engine/resolvers/atomic_resolver.py`、`engine/resolvers/incident_resolver.py` |
| 3.3 turn_end 能力顺序 | `engine/phases/phase_base.py`、`engine/resolvers/ability_resolver.py` |
| 3.4 / 3.5 杀人狂与护卫 | `engine/resolvers/death_resolver.py`、`engine/phases/phase_base.py` |
| 3.20 信息边界 | `engine/visibility.py` |

---

### 2.2 规则正文 / 附录 → 代码

#### `tragedy_loop_game_rules.md`

| 规则主题 | 主要代码 |
|----------|----------|
| 阶段顺序与时机 | `engine/state_machine.py`、`engine/phases/phase_base.py` |
| 行动牌合法性与结算 | `engine/models/cards.py`、`engine/phases/phase_base.py`、`engine/resolvers/atomic_resolver.py` |
| 能力时机、拒绝、目标 | `engine/resolvers/ability_resolver.py`、`engine/phases/phase_base.py` |
| 事件发生、公开结果 | `engine/resolvers/incident_resolver.py`、`engine/phases/phase_base.py`、`engine/visibility.py` |
| 死亡 / 失败 / 轮回结束 | `engine/resolvers/death_resolver.py`、`engine/game_controller.py`、`engine/event_bus.py` |
| 公开 / 非公开信息 | `engine/visibility.py` |

#### `tragedy_loop_appendix.md`

| 附录主题 | 主要代码 |
|----------|----------|
| FS / BTX 模组条目 | `data/modules/first_steps.json`、`data/modules/basic_tragedy_x.json` |
| 模组条目装配 | `engine/rules/module_loader.py` |
| 剧本合法性校验 | `engine/rules/script_validator.py` |
| 角色模板 | `data/characters.json`、`engine/rules/character_loader.py` |
| 身份 / 事件定义 | `engine/models/identity.py`、`engine/models/incident.py`、`engine/rules/identity_registry.py`、`engine/rules/incident_registry.py` |

---

### 2.3 规则文档映射文档 → 代码

#### [`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md)

| 文档章节 | 直接对应的代码 |
|----------|----------------|
| 第 1 节 分层原则 | `engine/state_machine.py`、`engine/game_controller.py`、`engine/phases/phase_base.py`、`engine/resolvers/*.py`、`engine/rules/*.py` |
| 第 2 节 规则主题 → Engine | `engine/game_state.py`、`engine/rules/module_loader.py`、`engine/rules/script_validator.py`、`engine/resolvers/ability_resolver.py`、`engine/resolvers/incident_resolver.py`、`engine/visibility.py` |
| 第 3 节 按规则对象映射 | `engine/models/script.py`、`engine/models/identity.py`、`engine/models/incident.py`、`engine/rules/runtime_identities.py` |
| 第 4 节 按流程规则映射 | `engine/game_controller.py`、`engine/phases/phase_base.py`、`engine/rules/module_loader.py` |
| 第 5 节 按“该改哪里”来查 | `engine/state_machine.py`、`engine/resolvers/*.py`、`engine/visibility.py`、`engine/rules/*.py` |

#### [`docs/rules_to_ui_mapping.md`](docs/rules_to_ui_mapping.md)

| 文档章节 | 直接对应的代码 |
|----------|----------------|
| 第 1 节 分层原则 | `ui/app.py`、`ui/main_window.py`、`ui/controllers/*.py`、`ui/screens/*.py` |
| 第 2 节 规则文档主主题 → UI | `ui/screens/new_game_screen.py`、`ui/screens/game_screen.py`、`ui/screens/title_screen.py`、`ui/screens/result_screen.py` |
| 第 3 节 按玩家视角映射 | `ui/screens/game_screen.py`、`ui/controllers/game_session_controller.py`、`engine/visibility.py` |
| 第 4 节 按交互规则映射 | `ui/screens/new_game_screen.py`、`ui/controllers/new_game_controller.py`、`ui/screens/game_screen.py` |
| 第 5 节 按显示规则映射 | `ui/screens/game_screen.py`、`ui/controllers/game_session_controller.py` |
| 第 6 节 按“该改哪里”来查 | `ui/screens/*.py`、`ui/controllers/*.py`、`ui/main_window.py` |

#### [`docs/engine_ui_boundary_mapping.md`](docs/engine_ui_boundary_mapping.md)

| 文档章节 | 直接对应的代码 |
|----------|----------------|
| 第 1 节 这层负责什么 | `engine/game_controller.py`、`ui/controllers/game_session_controller.py`、`ui/screens/*.py` |
| 第 2 节 核心边界对象 | `engine/game_controller.py`、`engine/phases/phase_base.py`、`engine/visibility.py`、`ui/controllers/game_session_controller.py` |
| 第 3 节 数据流映射 | `engine/game_controller.py`、`ui/controllers/game_session_controller.py`、`ui/screens/*.py` |
| 第 4 节 按问题类型定位 | `engine/game_controller.py`、`ui/controllers/game_session_controller.py`、`ui/screens/game_screen.py` |
| 第 5 节 当前文件职责 | `engine/game_controller.py`、`ui/controllers/game_session_controller.py`、`ui/screens/*.py` |

---

## 3. 代码到文档的反查索引

### 3.1 引擎入口

| 代码入口 | 反查文档 |
|----------|----------|
| `engine/state_machine.py` | [`PLAN.md`](PLAN.md) §2 Phase 1；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 4 节 |
| `engine/game_controller.py` | [`PLAN.md`](PLAN.md) §2 Phase 1 / §2 Phase 5；[`docs/engine_ui_boundary_mapping.md`](docs/engine_ui_boundary_mapping.md) 第 3 节 |
| `engine/game_state.py` | [`PLAN.md`](PLAN.md) §2 Phase 1 / Phase 2；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 2 节 |
| `engine/phases/phase_base.py` | [`PLAN.md`](PLAN.md) §2 Phase 1 / §3；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 4 节 |
| `engine/resolvers/atomic_resolver.py` | [`PLAN.md`](PLAN.md) §3.1；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 4 节 |
| `engine/resolvers/ability_resolver.py` | [`PLAN.md`](PLAN.md) Phase 4；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 4 节 |
| `engine/resolvers/incident_resolver.py` | [`PLAN.md`](PLAN.md) Phase 4 / §3.2；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 4 节 |
| `engine/resolvers/death_resolver.py` | [`PLAN.md`](PLAN.md) §3.4 / §3.5；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 4 节 |
| `engine/visibility.py` | [`PLAN.md`](PLAN.md) §3.20；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 2 节 |

### 3.2 规则与数据入口

| 代码入口 | 反查文档 |
|----------|----------|
| `engine/rules/module_loader.py` | [`PLAN.md`](PLAN.md) Phase 2；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 2 节 |
| `engine/rules/script_validator.py` | [`PLAN.md`](PLAN.md) Phase 4 P4-6；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 2 节 |
| `engine/rules/character_loader.py` | [`PLAN.md`](PLAN.md) Phase 4 P4-0 / P4-1；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 2 节 |
| `engine/rules/identity_registry.py` | [`PLAN.md`](PLAN.md) Phase 2 / Phase 4；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 3 节 |
| `engine/rules/incident_registry.py` | [`PLAN.md`](PLAN.md) Phase 2 / Phase 4；[`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md) 第 3 节 |
| `data/modules/*.json` | [`tragedy_loop_appendix.md`](tragedy_loop_appendix.md)；[`PLAN.md`](PLAN.md) Phase 2 |
| `data/characters.json` | [`tragedy_loop_appendix.md`](tragedy_loop_appendix.md)；[`PLAN.md`](PLAN.md) Phase 4 |

### 3.3 UI 入口

| 代码入口 | 反查文档 |
|----------|----------|
| `ui/app.py` | [`PLAN.md`](PLAN.md) Phase 5 / Phase 6；[`docs/rules_to_ui_mapping.md`](docs/rules_to_ui_mapping.md) 第 2 节 |
| `ui/main_window.py` | [`PLAN.md`](PLAN.md) Phase 5 / Phase 6；[`docs/rules_to_ui_mapping.md`](docs/rules_to_ui_mapping.md) 第 4 节 |
| `ui/screens/new_game_screen.py` | [`PLAN.md`](PLAN.md) Phase 5 / Phase 6；[`docs/rules_to_ui_mapping.md`](docs/rules_to_ui_mapping.md) 第 4 节 |
| `ui/screens/game_screen.py` | [`PLAN.md`](PLAN.md) Phase 5 / Phase 6；[`docs/rules_to_ui_mapping.md`](docs/rules_to_ui_mapping.md) 第 3 - 5 节 |
| `ui/controllers/game_session_controller.py` | [`docs/engine_ui_boundary_mapping.md`](docs/engine_ui_boundary_mapping.md) 第 2 - 5 节 |
| `ui/controllers/new_game_controller.py` | [`docs/rules_to_ui_mapping.md`](docs/rules_to_ui_mapping.md) 第 4 节；[`docs/engine_ui_boundary_mapping.md`](docs/engine_ui_boundary_mapping.md) 第 6 节 |

---

## 4. 当前仓库的“优先查找顺序”

当你准备把某条规则或某个界面需求落到代码时，建议按这个顺序走：

1. 先看 `tragedy_loop_game_rules.md` / `tragedy_loop_appendix.md`，确认规则原文和条目事实。
2. 再看 [`docs/rules_to_engine_mapping.md`](docs/rules_to_engine_mapping.md)，定位应该改哪层 `engine/`。
3. 如果是交互或展示问题，再看 [`docs/engine_ui_boundary_mapping.md`](docs/engine_ui_boundary_mapping.md)，确认是引擎、适配层还是 UI。
4. 最后看 [`docs/rules_to_ui_mapping.md`](docs/rules_to_ui_mapping.md)，定位应该改哪个 `ui/` 文件。
5. 如果要判断阶段进度和下一步工作，以 [`PLAN.md`](PLAN.md) 为准。

---

## 5. 维护规则

- 新增或重命名核心文件时，先更新本文件，再补其他映射文档。
- 如果某条规则已经从“规划”进入“实现”，优先把它从 `PLAN.md` 的阶段描述落到具体代码文件，而不是继续只写抽象阶段名。
- 如果文档里出现“未建 / 规划中”的路径，但仓库里已经有真实实现，优先把这里改成真实路径。
- 如果你以后要建立“文档条目 → 代码函数”的更细映射，建议直接在本文件下追加“章节 / 函数 / 测试”三列表，而不是再拆一份新的总索引。

---

## 6. 角色特性能力入口（`character_trait_ability`）

| 主题 | 代码入口 |
|------|----------|
| 角色数据声明（结构化） | `data/characters.json` 的 `character_trait_ability` |
| 角色模板解析 | `engine/rules/character_loader.py`（`CharacterDef.character_trait_abilities` / `CharacterState.character_trait_abilities`） |
| 静态数据校验 | `engine/validation/static_data.py`（`character_trait_ability` 数组校验） |
| 能力候选收集 | `engine/resolvers/ability_resolver.py`（`collect_character_trait_abilities`，`source_kind="character_trait_ability"`） |
| 阶段执行接线 | `engine/phases/phase_base.py`（`_candidate_owner_id` / 位置上下文） |
| 事件当事人覆写入口 | `engine/resolvers/incident_resolver.py`（`_incident_def_with_perpetrator_overrides`） |
| 回归测试 | `tests/test_character_loader.py`、`tests/test_ability_resolver.py`、`tests/test_phase4_handlers.py`、`tests/test_incident_handler.py` |

---

## 7. 从者跟随移动入口（`servant`）

| 主题 | 代码入口 |
|------|----------|
| 规则事实源 | `data/characters.json` 的 `servant.trait_rule` 与 `goodwill:servant:1` |
| 运行时追加目标预留 | `engine/game_state.py`（`trait_target_overrides`，按轮回清空） |
| 共享目标集合 | `engine/rules/servant_rules.py`（跟随与代死共用） |
| 跟随移动核心钩子 | `engine/resolvers/atomic_resolver.py`（`next_servant_follow_choice` / `_apply_servant_follow_rules`） |
| 顶层输入接线 | `engine/phases/phase_base.py`（`_resolve_effect_batch_with_servant_follow`，行动牌/能力/事件统一走这条链） |
| 事件接线 | `engine/resolvers/incident_resolver.py`（`next_servant_follow_choice` / `resolve_schedule(..., servant_follow_choices=...)`） |
| 当前覆盖范围 | 行动牌移动、身份/友好能力移动、事件移动（含 `sequential` / “随后”）、`servant` 代死 |
| 已实现 | `goodwill:servant:1` 写入 `trait_target_overrides["servant"]`，追加目标会自动进入现有跟随 / 代死链 |
| 回归测试 | `tests/test_action_card_system.py`、`tests/test_phase4_handlers.py`、`tests/test_incident_handler.py`、`tests/test_goodwill_structured_migration.py`、`tests/test_character_loader.py` |
