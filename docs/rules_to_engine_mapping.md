# 惨剧轮回：规则文档 → Engine 映射

本文件把规则文档中的“规则含义”映射到 `engine/` 代码，目的是把：

- **规则是否实现正确**
- **应该改哪一层 engine**
- **某条规则现在是否已有代码落点**

严格区分出来。

适用文档：

- `tragedy_loop_game_rules.md`
- `tragedy_loop_appendix.md`

不覆盖 UI 展示细节；UI 相关请看 `docs/rules_to_ui_mapping.md`。

当前核实说明：

- `tragedy_loop_appendix.md` 是模组规则数量与条目名称的事实源
- 当前仓库中的 `data/modules/*.json` 仅实现了附录中的**部分** `FS` / `BTX` 规则
- 因此出现“附录里有，但当前下拉里没有”时，必须先区分：
  1. `engine/data` 尚未录入
  2. UI 没把已录入项显示出来

---

## 1. 分层原则

下列问题归 `engine`：

- 阶段顺序是否正确
- 行动牌是否合法、如何结算
- 能力何时触发、何时可拒绝
- 事件何时发生、效果如何裁定
- 死亡 / 失败 / 强制轮回结束的优先级
- 模组规则、规则 Y / X、身份槽位是否合法
- 哪些信息本质上是公开 / 非公开

下列文件是主要入口：

| 主题 | 主要代码 |
|------|----------|
| 阶段流转 | `engine/state_machine.py` |
| 调度总入口 | `engine/game_controller.py` |
| 阶段业务 | `engine/phases/phase_base.py` |
| 原子结算 | `engine/resolvers/atomic_resolver.py` |
| 能力筛选 / 目标选择 | `engine/resolvers/ability_resolver.py` |
| 事件结算 | `engine/resolvers/incident_resolver.py` |
| 死亡链 | `engine/resolvers/death_resolver.py` |
| 信息边界源定义 | `engine/visibility.py` |
| 模组 / 规则 / 身份 / 事件装配 | `engine/rules/module_loader.py` |
| 剧本合法性校验 | `engine/rules/script_validator.py` |
| 角色模板加载 | `engine/rules/character_loader.py` |
| 事件通知 | `engine/event_bus.py` |

---

## 2. 规则文档主主题 → Engine

| 规则主题 | 规则文档含义 | 主要代码 | 备注 |
|----------|--------------|----------|------|
| 模组定义 | FS / BTX 的规则 Y、规则 X、身份、事件、特殊规则 | `data/modules/*.json`, `engine/rules/module_loader.py` | 规则原始数据入口 |
| 角色资料 | 初始区域、特性、属性、不安限度、友好能力来源 | `data/characters.json`, `engine/rules/character_loader.py` | 属于规则数据，不是 UI 配置 |
| 剧本制作约束 | 规则 Y/X 对身份槽位、角色限制、事件限制 | `engine/rules/script_validator.py` | 负责“这份剧本能否成立” |
| 游戏状态 | 当前轮、当前天、角色、版图、已放牌、失败标记 | `engine/game_state.py` | 是所有规则的运行时容器 |
| 阶段顺序 | 15 阶段线性流转与分支 | `engine/state_machine.py` | 负责“什么时候到哪个阶段” |
| 阶段执行 | 每阶段执行什么、何时等待输入 | `engine/phases/phase_base.py` | 负责“这个阶段做什么” |
| 裁定顺序 | 原子效果、同时裁定、触发链 | `engine/resolvers/atomic_resolver.py` | 负责“效果怎么落地” |
| 死亡与失败 | 死亡链、失败条件、轮回结束 | `engine/resolvers/death_resolver.py`, `engine/phases/phase_base.py` | 多阶段联动 |
| 能力系统 | 强制 / 任意 / 失败条件 / 可拒绝 | `engine/resolvers/ability_resolver.py`, `engine/phases/phase_base.py` | 触发窗口在 phase，候选筛选在 resolver |
| 事件系统 | 事件日程、发生条件、公开结果 | `engine/resolvers/incident_resolver.py`, `engine/phases/phase_base.py` | `INCIDENT` 阶段落地 |
| 信息边界 | 主人公 / 剧作家可见信息 | `engine/visibility.py` | 这是 UI 展示的源，不是 UI 自己定义 |

---

## 3. 按规则对象映射

### 3.1 模组、规则 Y、规则 X

| 规则对象 | 主要代码 | 说明 |
|----------|----------|------|
| 模组元数据 | `engine/models/script.py` 中 `ModuleDef` | 规则 X 数量、是否有最终决战、特殊规则等 |
| 规则 Y / X 定义 | `engine/models/script.py` 中 `RuleDef` | 身份槽位、附加能力、特殊胜利条件 |
| 模组加载 | `engine/rules/module_loader.py` | 从 JSON 装配为运行时结构 |
| 规则合法性 | `engine/rules/script_validator.py` | 校验所选规则与剧本是否匹配 |

相关入口：

- `engine/rules/module_loader.py:107`
- `engine/rules/module_loader.py:190`
- `engine/rules/script_validator.py:53`
- `engine/rules/script_validator.py:204`

附录与当前实现覆盖（2026-04-22 更新）：

| 模组 | 附录条目数 | 当前 `data/modules/*.json` |
|------|------------|----------------------------|
| `First Steps` | `规则Y=3`，`规则X=3` | 已录入 `规则Y=3`，`规则X=3` |
| `Basic Tragedy X` | `规则Y=5`，`规则X=7` | 已录入 `规则Y=5`，`规则X=7` |

这意味着：

- `FS` / `BTX` 的规则数量现在已与附录条目数对齐
- 如果 UI 仍显示不全，优先怀疑 UI / 适配层
- 但个别复杂规则当前可能仅录入了条目与说明，未必已完全结构化实现

### 3.2 角色、身份、事件

| 规则对象 | 主要代码 | 说明 |
|----------|----------|------|
| 角色模板 | `engine/rules/character_loader.py` | 从 `data/characters.json` 读入 |
| 运行时角色 | `engine/models/character.py` | 血条、区域、标记物、公开状态等 |
| 身份定义 | `engine/models/identity.py` | 身份能力、特性、数量限制 |
| 事件定义 | `engine/models/incident.py` | 事件效果、额外条件、公开结果 |
| 动态身份同步 | `engine/rules/runtime_identities.py` | 动态身份变化与回填 |

---

## 4. 按流程规则映射

### 4.1 开局与剧本准备

| 规则主题 | 主要代码 | 说明 |
|----------|----------|------|
| 开局装配模组 | `engine/game_controller.py`, `engine/rules/module_loader.py` | 由模组创建 `GameState` |
| 非公开信息表提交 | `engine/phases/phase_base.py` | `GAME_PREPARE` 阶段产生 `script_setup` 输入 |
| 剧本 payload 回填 | `engine/rules/module_loader.py` | `apply_script_setup_payload()` |
| 剧本校验 | `engine/rules/script_validator.py` | 提交时执行校验 |

关键点：

- “能不能开局”是 engine 规则问题，不是 UI 问题
- UI 只是提交 payload，真正的合法性判断在 engine

### 4.2 阶段流转

| 规则主题 | 主要代码 |
|----------|----------|
| 阶段定义 | `engine/models/enums.py` |
| 阶段推进 | `engine/state_machine.py` |
| 阶段执行 | `engine/phases/phase_base.py` |
| 总调度 | `engine/game_controller.py` |

典型对应：

- `TURN_START -> MASTERMIND_ACTION -> PROTAGONIST_ACTION -> ACTION_RESOLVE`
- `PLAYWRIGHT_ABILITY -> PROTAGONIST_ABILITY -> INCIDENT -> TURN_END`
- `LOOP_END` 末尾分支 -> `NEXT_LOOP` / `FINAL_GUESS` / `GAME_END`

### 4.3 行动牌规则

| 规则主题 | 主要代码 | 说明 |
|----------|----------|------|
| 放牌输入 | `engine/phases/phase_base.py` | `WaitForInput(input_type="place_action_card")` |
| 目标合法性 | `engine/phases/phase_base.py` | `_validate_action_target`, `_validate_action_slot` |
| 翻牌与行动结算 | `engine/phases/phase_base.py` | `ActionResolveHandler` |
| 行动牌数据 | `engine/models/cards.py` | 卡牌类型、是否移动、是否 once_per_loop |

关键规则落点：

- 同目标冲突
- `FORBID_*` 预处理
- 移动牌先结算
- 指示物牌后结算

### 4.4 能力规则

| 规则主题 | 主要代码 | 说明 |
|----------|----------|------|
| 能力定义 | `engine/models/ability.py` | 统一能力模型 |
| 候选能力收集 | `engine/resolvers/ability_resolver.py` | 按时机 / 类型 / 条件筛选 |
| 剧作家能力阶段 | `engine/phases/phase_base.py` | `PlaywrightAbilityHandler` |
| 主人公能力阶段 | `engine/phases/phase_base.py` | `ProtagonistAbilityHandler` |
| 能力目标选择 | `engine/phases/phase_base.py` | `choose_ability_target` 等输入 |
| 能力原子结算 | `engine/resolvers/atomic_resolver.py` | 效果真正生效 |

补充：

- “能力在什么时候出现”主要是 phase 规则
- “能力是否满足条件、有哪些合法目标”主要是 resolver 规则

### 4.5 事件规则

| 规则主题 | 主要代码 |
|----------|----------|
| 事件定义 | `engine/models/incident.py` |
| 事件日程 | `engine/models/script.py` |
| 事件阶段 | `engine/phases/phase_base.py` 中 `IncidentHandler` |
| 事件结算 | `engine/resolvers/incident_resolver.py` |
| 公开结果 | `engine/visibility.py`, `engine/models/incident.py` |

### 4.6 死亡 / 失败 / 强制轮回结束

| 规则主题 | 主要代码 |
|----------|----------|
| 死亡处理链 | `engine/resolvers/death_resolver.py` |
| 主人公死亡 / 失败事件 | `engine/resolvers/atomic_resolver.py` |
| 强制轮回结束信号 | `engine/phases/phase_base.py` |
| 最终胜负判定 | `engine/game_controller.py` |

---

## 5. 按“该改哪里”来查

### 5.1 如果是这些问题，优先查 engine

| 问题类型 | 优先文件 |
|----------|----------|
| 阶段跳错了 | `engine/state_machine.py`, `engine/phases/phase_base.py` |
| 规则 Y / X 效果不对 | `data/modules/*.json`, `engine/rules/module_loader.py`, `engine/rules/script_validator.py` |
| 能力没触发 / 多触发 | `engine/resolvers/ability_resolver.py`, `engine/phases/phase_base.py` |
| 事件发生条件不对 | `engine/resolvers/incident_resolver.py`, `engine/phases/phase_base.py` |
| 同时裁定不对 | `engine/resolvers/atomic_resolver.py` |
| 死亡链或失败优先级错 | `engine/resolvers/death_resolver.py`, `engine/resolvers/atomic_resolver.py` |
| 某信息不该公开却公开了 | `engine/visibility.py` |

### 5.2 这些问题不要误判成 engine

下列问题通常不是规则错误，而是 UI 或适配层问题：

- 下拉框没显示全
- 输入框没刷新
- 公告栏没显示阶段切换
- 剧作家栏没把详细日志展开
- 提交失败后输入态丢失

这类问题请转看 `docs/rules_to_ui_mapping.md`。

---

## 6. 与 UI 的边界

必须记住：

- **公开 / 非公开信息的定义** 在 `engine/visibility.py`
- **具体怎么显示** 在 `ui/`
- **等待什么输入** 在 `engine/phases/phase_base.py`
- **输入控件长什么样** 在 `ui/screens/*.py`

也就是说：

- “该不该看到”是 engine 规则
- “怎么看到”是 UI 实现

---

## 7. 当前适合继续维护的规则入口

后续如果继续补规则，建议优先沿下面入口扩展：

1. `data/modules/*.json`
2. `engine/rules/module_loader.py`
3. `engine/rules/script_validator.py`
4. `engine/resolvers/ability_resolver.py`
5. `engine/resolvers/incident_resolver.py`
6. `engine/resolvers/atomic_resolver.py`
7. `engine/visibility.py`

---

## 8. 文档维护规则

当出现以下变更时，必须同步更新本文件：

- 新增模组规则字段
- 新增能力时机 / 效果类型 / 目标选择器
- 新增事件公开结果规则
- 调整阶段流转
- 调整信息边界

如果只是控件布局、日志展示、交互控件变化，不更新本文件，改更新 `docs/rules_to_ui_mapping.md`。
