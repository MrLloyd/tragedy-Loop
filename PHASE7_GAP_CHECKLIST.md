# Phase 7 缺口清单

日期：2026-04-23

范围：检查 `First Steps` / `Basic Tragedy X` 的身份、规则、事件，以及角色层友好能力与特性，区分当前哪些已经结构化、哪些仍是半结构化或未结构化数据。

目标：Phase 7 优先完成 FS / BTX 模组与角色数据的结构化收敛，让规则、身份、事件、友好能力、特性都能被引擎稳定读取、校验和测试，避免继续依赖描述文本或临时 fallback。

---

## 一、整体结论

- `data/modules/first_steps.json` 与 `data/modules/basic_tragedy_x.json` 中的规则、身份、事件主数据已经基本结构化。
- 规则层仍存在少量 `description` 字段承担规则语义说明，属于半结构化状态。
- 身份层大部分能力已结构化，`unstable_factor` 的动态派生能力已迁移为身份数据中的 `derived_identities`。
- 事件层已统一使用 `incidents[].effects` 表达，但 `any_board`、`choose_token_type` 等值仍依赖 resolver 特判。
- 角色层仍是 Phase 7 最大缺口：`trait_rule` 与 `goodwill_ability_*` 旧三字段仍大量存在，尚未完全迁移为结构化能力与特性。

---

## 二、已结构化的数据

### 1. FS / BTX 模组基础信息

- `module_id`、`name`、`special_rules`、`rule_x_count`、`has_final_guess`、`has_ex_gauge` 等模组元信息已结构化。
- `First Steps` 已表达：
  - 只使用 1 条规则 X。
  - 没有最终猜测。
  - 没有 EX Gauge。
- `Basic Tragedy X` 已表达：
  - 标准基础模组。
  - 使用 2 条规则 X。
  - 有最终猜测。
  - 没有 EX Gauge。

### 2. FS / BTX 规则基础结构

- `rules_y` / `rules_x` 均使用结构化条目表达：
  - `rule_id`
  - `name`
  - `rule_type`
  - `module`
  - `identity_slots`
  - `identity_slot_ranges`
  - `abilities`
- 只负责身份组成的规则已可通过 `identity_slots` / `identity_slot_ranges` 表达。
- 含失败条件或剧作家能力的规则，大多已通过 `abilities[].condition` 与 `abilities[].effects` 表达。

### 3. FS / BTX 身份能力

- 多数关键身份已结构化为：
  - `identity_id`
  - `name`
  - `module`
  - `traits`
  - `max_count`
  - `abilities`
- 已结构化的典型身份包括：
  - `key_person`
  - `killer`
  - `mastermind`
  - `cultist`
  - `friend`
  - `rumormonger`
  - `serial_killer`
  - `time_traveler`
  - `beloved`
  - `lover`
- 常见能力结构已覆盖：
  - 死亡触发。
  - 剧作家能力。
  - 轮回开始能力。
  - 轮回结束失败条件。
  - 行动牌结算干预。
  - 回合结束强制或任意能力。

### 4. FS / BTX 事件效果

- `incidents` 已统一结构化为：
  - `incident_id`
  - `name`
  - `module`
  - `sequential`
  - `effects`
- 已结构化事件包括：
  - `unease_spread`
  - `murder`
  - `hospital_accident`
  - `suicide`
  - `spread`
  - `disappearance`
  - `long_range_murder`
  - `spiritual_contamination`
  - `butterfly_effect`
- 事件效果已能表达：
  - 放置指示物。
  - 移除指示物。
  - 杀死角色。
  - 移动角色。
  - 主人公死亡。
  - 条件式效果。

---

## 三、半结构化的数据

### 1. 仍带 `description` 的规则

- `fs_revenge_kindling`
  - 已有 `loop_end` 失败条件能力。
  - `description` 仍重复承载规则说明。
- `fs_protect_this_place`
  - 已有 `loop_end` 失败条件能力。
  - `description` 仍重复承载规则说明。
- `fs_darkest_script`
  - 已有 `identity_slot_ranges.thug.min/max`。
  - `description` 仍说明“暴徒人数可以为 0-2 人”。
- `btx_giant_time_bomb_x`
  - 已有魔女初始区域密谋失败条件能力。
  - `description` 仍重复承载规则说明。
- `btx_causal_line`
  - 已有 `loop_start` 规则能力。
  - 使用受控约定字符串 `last_loop_goodwill_characters` 表达“上轮轮回结束时所有带有友好的角色”。
- `btx_delusion_spread_virus`
  - 已有常驻能力结构。
  - `description` 仍重复说明身份变化逻辑。

### 2. 受控约定字符串

- 这类数据已经具备结构化外壳，但其中少量 `target` / `value` 仍使用受控约定字符串，由 resolver 统一解释。
- Phase 7 当前不建议继续拆分成更多字段，避免数据模型过度膨胀。
- Phase 7 需要做的是：
  - 保留这些约定字符串。
  - 明确其合法值范围与语义。
  - 确保 resolver 对同一取值的解释唯一且稳定。
  - 为每个约定值补回归测试。
- 当前已识别的典型值包括：
  - `disappearance`
    - `move_character.value = "any_board"`：表示“由剧作家选择目标版图”。
  - `butterfly_effect`
    - `value = "choose_token_type"`：表示“选择指示物类型”。
  - `long_range_murder`
    - `target = "any_character"` 与条件里的 `target = "other"`：表示“从拥有 2 枚或以上密谋的角色中选择目标”。

### 3. 结构化空能力身份

- `thug`
  - 只有 `ignore_goodwill` 特性，无主动能力，当前可视为合理空能力身份。
- `witch`
  - 只有 `must_ignore_goodwill` 特性，无主动能力。
  - 需要显式测试确认“必定无视友好”由 trait 正确生效。
- `unstable_factor`
  - 已有 `ignore_goodwill` 特性。
  - 已通过 `derived_identities` 显式声明动态获得 `rumormonger` / `key_person` 能力的条件。

---

## 四、未结构化的数据

### 1. 角色特性仍是纯文本

- `data/characters.json` 中大量角色仍使用 `trait_rule` 文本描述角色特性。
- `trait_rule` 当前无法被静态校验稳定理解，也不适合直接驱动引擎行为。
- 示例类型包括：
  - 剧本制作限制。
  - 回合开始配置上场。
  - 回合结束死亡。
  - 事件当事人特殊处理。
  - 初始区域变化。
  - EX 牌相关特性。
  - 移动/死亡代替特性。

### 2. 角色友好能力仍保留旧三字段

- `data/characters.json` 当前仍大量使用：
  - `goodwill_ability_texts`
  - `goodwill_ability_goodwill_requirements`
  - `goodwill_ability_once_per_loop`
- 这些字段目前依靠加载器转换成 `goodwill_abilities`，属于兼容迁移状态，不是最终结构化数据形态。
- 当前仍存在兼容逻辑：
  - `engine/rules/character_loader.py`
  - `engine/resolvers/ability_resolver.py`
  - `engine/validation/static_data.py`
- Phase 7 应迁移为显式 `goodwill_abilities`，并删除旧字段与 fallback。

### 3. 测试仍覆盖旧字段路径

- 现有测试仍直接构造或断言旧字段：
  - `goodwill_ability_texts`
  - `goodwill_ability_goodwill_requirements`
  - `goodwill_ability_once_per_loop`
- 这些测试应随结构化迁移改为断言：
  - `goodwill_abilities`
  - 结构化 `Ability` 字段。
  - 具体友好能力行为。
  - 不再依赖文本 fallback。

---

## 五、FS 具体检查结果

### 1. FS 规则

- `fs_murder_plan`
  - 已结构化：身份槽 `key_person`、`killer`、`mastermind`。
  - 无行为能力，属于纯身份槽规则。
- `fs_revenge_kindling`
  - 已结构化：主谋身份槽与轮回结束失败条件。
  - 半结构化：仍带 `description`。
- `fs_protect_this_place`
  - 已结构化：关键人物、邪教徒身份槽与学校密谋失败条件。
  - 半结构化：`effect.value` 命名仍沿用 `mastermind_initial_area_intrigue_2`，建议核对语义命名。
- `fs_ripper_shadow`
  - 已结构化：传谣人、杀人狂身份槽与学校密谋失败条件。
- `fs_rumors`
  - 已结构化：传谣人身份槽与剧作家每轮一次放置密谋能力。
- `fs_darkest_script`
  - 已结构化：传谣人、亲友身份槽与暴徒数量范围。
  - 半结构化：仍带 `description`。

### 2. FS 身份

- `key_person`
  - 已结构化：死亡时主人公失败并强制结束轮回。
- `killer`
  - 已结构化：杀死关键人物、密谋 4+ 导致主人公死亡。
- `mastermind`
  - 已结构化：放置密谋到同区域角色或版图。
- `cultist`
  - 已结构化：必定无视友好，并可无效化禁止密谋。
- `friend`
  - 已结构化：死亡轮回结束时公开身份并失败，公开后轮回开始加友好。
  - 待验证：主人公侧快照是否真的可见公开身份。
- `thug`
  - 已结构化：无视友好，无主动能力。
- `rumormonger`
  - 已结构化：剧作家能力放置不安。
- `serial_killer`
  - 已结构化：同区域恰好一名其他角色时杀人。

### 3. FS 事件

- `unease_spread`
  - 已结构化：放置 2 不安与 1 密谋。
- `murder`
  - 已结构化：杀死同区域其他角色。
- `hospital_accident`
  - 已结构化：医院密谋 1+ 杀死医院全员，医院密谋 2+ 主人公死亡。
- `suicide`
  - 已结构化：当事人死亡。
- `spread`
  - 已结构化：移除 2 友好，再放置 2 友好。
- `disappearance`
  - 半结构化：移动到 `any_board` 后在同区域版图放置 1 密谋，需要测试剧作家选择目标区域。
- `long_range_murder`
  - 已结构化：从拥有 2 枚或以上密谋的角色中选择目标并杀死。
  - 使用受控约定字符串：`target = "any_character"` 搭配 `condition.params.target = "other"` 过滤候选目标。

---

## 六、BTX 具体检查结果

### 1. BTX 规则

- `btx_murder_plan`
  - 已结构化：身份槽 `key_person`、`killer`、`mastermind`。
  - 无行为能力，属于纯身份槽规则。
- `btx_cursed_contract`
  - 已结构化：关键人物身份槽与关键人物 2+ 密谋失败条件。
- `btx_sealed_evil`
  - 已结构化：主谋、邪教徒身份槽与神社 2+ 密谋失败条件。
- `btx_change_future`
  - 已结构化：邪教徒、时间旅者身份槽与蝴蝶效应发生后的失败条件。
- `btx_giant_time_bomb_x`
  - 已结构化：魔女身份槽与魔女初始区域 2+ 密谋失败条件。
  - 半结构化：仍带 `description`。
- `btx_friends_circle`
  - 已结构化：亲友 2、传谣人 1。
  - 无行为能力，属于纯身份槽规则。
- `btx_love_scenic_line`
  - 已结构化：心上人 1、求爱者 1。
  - 无行为能力，能力在身份上表达。
- `btx_rumors`
  - 已结构化：传谣人身份槽与剧作家每轮一次放置密谋能力。
- `btx_latent_serial_killer`
  - 已结构化：杀人狂 1、亲友 1。
  - 无行为能力，属于纯身份槽规则。
- `btx_causal_line`
  - 已结构化：规则能力在 `loop_start` 时为上轮结束时带友好的角色放置 2 枚不安。
  - 使用受控约定字符串：`target = "last_loop_goodwill_characters"`。
- `btx_delusion_spread_virus`
  - 已结构化：常驻身份变化能力。
  - 半结构化：仍带 `description`，且需确认 persistent effect 与模组能力表达是否重复。
- `btx_unknown_factor_chi`
  - 已结构化：不安定因子身份槽。
  - 动态能力已在 `unstable_factor.derived_identities` 中显式声明。

### 2. BTX 身份

- `key_person`
  - 已结构化：死亡时主人公失败并强制结束轮回。
- `killer`
  - 已结构化：杀死关键人物、密谋 4+ 导致主人公死亡。
- `mastermind`
  - 已结构化：放置密谋到同区域角色或版图。
- `cultist`
  - 已结构化：必定无视友好，并可无效化禁止密谋。
- `witch`
  - 半结构化：只有 `must_ignore_goodwill` 特性，无主动能力。
- `friend`
  - 已结构化：死亡轮回结束时公开身份并失败，公开后轮回开始加友好。
- `serial_killer`
  - 已结构化：同区域恰好一名其他角色时杀人。
- `rumormonger`
  - 已结构化：剧作家能力放置不安。
- `time_traveler`
  - 已结构化：无效化禁止友好、最终日友好不足失败。
- `beloved`
  - 已结构化：求爱者死亡时自身获得 6 不安。
- `lover`
  - 已结构化：心上人死亡时自身获得 6 不安，且满足密谋/不安条件时主人公死亡。
- `unstable_factor`
  - 已结构化：通过 `derived_identities` 显式声明学校 2+ 密谋时获得传谣人能力、都市 2+ 密谋时获得关键人物能力。

### 3. BTX 事件

- `unease_spread`
  - 已结构化：放置 2 不安与 1 密谋。
- `murder`
  - 已结构化：杀死同区域其他角色。
- `spiritual_contamination`
  - 已结构化：神社放置 2 密谋。
- `hospital_accident`
  - 已结构化：医院密谋 1+ 杀死医院全员，医院密谋 2+ 主人公死亡。
- `suicide`
  - 已结构化：当事人死亡。
- `spread`
  - 已结构化：移除 2 友好，再放置 2 友好。
- `butterfly_effect`
  - 半结构化：`choose_token_type` 需要 resolver 解释。
- `disappearance`
  - 半结构化：`any_board` 需要 resolver 解释。
- `long_range_murder`
  - 已结构化：从拥有 2 枚或以上密谋的角色中选择目标并杀死。
  - 使用受控约定字符串：`target = "any_character"` 搭配 `condition.params.target = "other"` 过滤候选目标。

---

## 七、Phase 7 下一步执行清单

### 1. 先完成 FS / BTX 模组规则能力

- 为 FS / BTX 每条规则 Y / X 建立对表清单。
- 纯身份槽规则先补 `script_validator` 合法 / 非法剧本测试：
  - `fs_murder_plan`
  - `btx_murder_plan`
  - `btx_friends_circle`
  - `btx_love_scenic_line`
  - `btx_latent_serial_killer`
  - `btx_unknown_factor_chi`
- 含失败条件规则测试 `loop_end` 触发：
  - `fs_revenge_kindling`
  - `fs_protect_this_place`
  - `fs_ripper_shadow`
  - `btx_cursed_contract`
  - `btx_sealed_evil`
  - `btx_change_future`
  - `btx_giant_time_bomb_x`
- 含剧作家能力规则测试时机、目标与限次：
  - `fs_rumors`
  - `btx_rumors`
- 含常驻 / 跨轮回规则明确实现归属并补回归：
  - `btx_causal_line`
  - `btx_delusion_spread_virus`

### 2. 再完成 FS / BTX 模组身份能力

- 为关键身份补行为回归：
  - `key_person`
  - `killer`
  - `mastermind`
  - `cultist`
  - `friend`
  - `rumormonger`
  - `serial_killer`
  - `witch`
  - `time_traveler`
  - `beloved`
  - `lover`
  - `unstable_factor`
- 为 `unstable_factor` 明确动态能力来源并补测试：
  - 学校 2+ 密谋 → 获得传谣人能力。
  - 都市 2+ 密谋 → 获得关键人物能力。
- 为 `witch` 补显式特性回归，确认 `must_ignore_goodwill` 被能力收集与友好能力判定正确使用。
- 为 `friend` 补信息边界回归，确认公开身份后主人公快照可见。

### 3. 然后收敛半结构化规则

- 对仍带 `description` 的规则逐条判断：
  - 如果只是重复说明，保留为纯展示字段或移到 `flavor_text` / `rules_text`。
  - 如果仍承载实际行为，补成 `abilities` / `conditions` / `effects`。
- 优先处理：
  - `btx_causal_line`
  - `btx_unknown_factor_chi`
  - `fs_darkest_script`
  - `btx_delusion_spread_virus`

### 4. 补事件解释回归

- `suicide`
  - 验证事件成功时当事人死亡。
- `disappearance`
  - 验证剧作家选择目标版图后，角色移动并在目标版图放置密谋。
- `butterfly_effect`
  - 验证可选择指示物类型，并能触发 `btx_change_future` 的轮回结束失败条件。
- `long_range_murder`
  - 验证只能从拥有 2 枚或以上密谋的角色中选择死亡目标。

### 5. 最后处理角色层未结构化数据

- 将 `data/characters.json` 的 `goodwill_ability_*` 三字段迁移为显式 `goodwill_abilities`。
- 为 `trait_rule` 增加结构化表达字段，例如：
  - `base_traits`
  - `character_abilities`
  - `setup_constraints`
  - `incident_modifiers`
  - `loop_start_effects`
  - `turn_end_effects`
- 删除旧三字段的加载 fallback。
- 删除旧三字段的运行时 fallback。
- 修改静态校验，让旧字段变成禁止项或 deprecated issue。

### 6. 建立 FS / BTX 对表测试矩阵

- 每条规则 Y / X 至少一条最小回归。
- 纯身份槽规则测试 `script_validator` 合法 / 非法剧本。
- 含失败条件规则测试失败条件触发。
- 含常驻规则测试状态变化。
- 含剧作家能力规则测试时机、目标与限次。
- 事件测试覆盖“输入 → 原子结算 → 触发链 → 可见结果”。

---

## 八、当前优先级

1. FS / BTX 每条规则建立对表测试。
2. 纯身份槽规则补 `script_validator` 合法 / 非法剧本测试。
3. 含失败条件、常驻能力、剧作家能力的规则补行为回归。
4. `unstable_factor`、`witch`、`friend` 等关键身份能力补显式回归。
5. `disappearance`、`butterfly_effect`、`long_range_murder` 事件解释回归。
6. 角色友好能力旧三字段迁移到 `goodwill_abilities`。
7. 角色 `trait_rule` 拆成结构化特性与能力。
