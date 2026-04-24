# Phase 7 缺口清单

日期：2026-04-24

范围：基于当前仓库实际代码、数据与测试，重新核对 `First Steps` / `Basic Tragedy X` 的规则、身份、事件，以及角色层友好能力与特性结构化状态。

---

## 一、当前结论

- `FS / BTX` 的规则、身份、事件条目已经全部录入 `data/modules/*.json`，不再是“只录了部分条目”的状态。
- `FS / BTX` 的规则能力、身份能力、事件效果已接入引擎当前通用机制，主缺口已经不在模组层，而在角色层。
- `witch`、`unstable_factor`、`friend`、`beloved / lover`、`disappearance`、`butterfly_effect`、`long_range_murder` 等此前标记为风险点的条目，现在都已有实现与回归。
- 规则层原先仅重复说明结构化语义的顶层 `description` 已可删除；本次已删除这些冗余字段。
- 当前真正仍未结构化、仍依赖兼容 fallback 的部分，集中在 `data/characters.json` 与角色加载/友好能力路径。

---

## 二、FS / BTX 规则层现状

### 1. 已实现且已结构化

- `FS` 规则：
  - `fs_murder_plan`
  - `fs_revenge_kindling`
  - `fs_protect_this_place`
  - `fs_ripper_shadow`
  - `fs_rumors`
  - `fs_darkest_script`
- `BTX` 规则：
  - `btx_murder_plan`
  - `btx_cursed_contract`
  - `btx_sealed_evil`
  - `btx_change_future`
  - `btx_giant_time_bomb_x`
  - `btx_friends_circle`
  - `btx_love_scenic_line`
  - `btx_rumors`
  - `btx_latent_serial_killer`
  - `btx_causal_line`
  - `btx_delusion_spread_virus`
  - `btx_unknown_factor_chi`

### 2. 说明

- 纯身份槽 / 身份范围规则已由 `identity_slots`、`identity_slot_ranges` 与 `script_validator` 支撑。
- 失败条件规则已由 `loop_end` 能力与通用条件求值支撑。
- 剧作家能力规则已由 `playwright_ability` + `phase_base.py` 目标选择流程支撑。
- `btx_causal_line` 已不再是阶段硬编码，而是规则能力。
- `btx_delusion_spread_virus` 已由常驻能力 + persistent effect 机制实现，不再是说明性占位数据。
- 本次已删除以下规则顶层冗余 `description`：
  - `fs_revenge_kindling`
  - `fs_protect_this_place`
  - `fs_darkest_script`
  - `btx_giant_time_bomb_x`
  - `btx_causal_line`
  - `btx_delusion_spread_virus`

### 3. 当前未实现规则

- 就 `FS / BTX` 模组规则本身而言，当前**没有确认未实现的规则条目**。

---

## 三、FS / BTX 身份层现状

### 1. 已实现且已结构化

- `FS` 身份：
  - `key_person`
  - `killer`
  - `mastermind`
  - `cultist`
  - `friend`
  - `thug`
  - `rumormonger`
  - `serial_killer`
- `BTX` 身份：
  - `key_person`
  - `killer`
  - `mastermind`
  - `cultist`
  - `witch`
  - `friend`
  - `serial_killer`
  - `rumormonger`
  - `time_traveler`
  - `beloved`
  - `lover`
  - `unstable_factor`

### 2. 已核对的关键风险点

- `witch`
  - `must_ignore_goodwill` 已通过独立 trait 派生层与能力收集逻辑生效，并有显式测试。
- `unstable_factor`
  - 已通过 `derived_identities` 显式声明动态获得 `rumormonger` / `key_person` 能力，不再依赖临时硬编码。
- `friend`
  - 死亡失败、公开身份、跨轮回友好追加，以及主人公视角可见性已有回归。
- `beloved / lover`
  - 顺序死亡会触发后继死亡效果。
  - 同时死亡遵循当前固定规则：先一起变尸体，再统一触发死亡效果；同批次角色按已死亡处理，因此不会互相追加 `+6` 不安。
- `time_traveler`
  - 终日失败条件与当前身份 trait 行为已有回归。

### 3. 当前未实现身份

- 就 `FS / BTX` 身份本身而言，当前**没有确认未实现的身份条目**。

---

## 四、FS / BTX 事件层现状

### 1. 已实现且已结构化

- `FS` 事件：
  - `unease_spread`
  - `murder`
  - `hospital_accident`
  - `suicide`
  - `spread`
  - `disappearance`
  - `long_range_murder`
- `BTX` 事件：
  - `unease_spread`
  - `murder`
  - `spiritual_contamination`
  - `hospital_accident`
  - `suicide`
  - `spread`
  - `butterfly_effect`
  - `disappearance`
  - `long_range_murder`

### 2. 受控约定值现状

- 下列值仍是“受控约定字符串”，但已经有唯一解释与测试，不再视为当前阻塞缺口：
  - `any_board`
  - `choose_token_type`
  - `last_loop_goodwill_characters`
  - `any_character` + 条件内 `target = "other"`
- 这些值目前属于“结构化外壳 + 受控语义”的稳定实现，而不是未实现状态。

### 3. 当前未实现事件

- 就 `FS / BTX` 事件本身而言，当前**没有确认未实现的事件条目**。

---

## 五、当前真正未结构化的部分

### 1. 角色特性仍以 `trait_rule` 文本承载

- `data/characters.json` 中大量角色仍使用自然语言 `trait_rule`。
- 当前引擎只能对其中极少数模式做文本 fallback，例如：
  - `cannot_be_commoner`
  - `cannot_ignore_goodwill_identity`
- 其余特性仍不能被静态校验或稳定驱动运行时逻辑。

### 2. 角色友好能力仍主要依赖旧三字段

- 现状仍保留：
  - `goodwill_ability_texts`
  - `goodwill_ability_goodwill_requirements`
  - `goodwill_ability_once_per_loop`
- `character_loader` 会把旧字段临时转换成 `goodwill_abilities`。
- `ability_resolver` 仍保留旧字段 fallback。
- `validation/static_data.py` 仍在验证旧字段格式。

### 3. 测试仍大量覆盖旧字段路径

- 若要真正完成角色层结构化，需要把测试从旧三字段逐步迁移到显式 `goodwill_abilities`。

### 4. 兼容接口仍未完全下线

- `collect_character_abilities()` 目前仍作为兼容别名存在。
- 公开统一入口已经是 `collect_abilities()`，但旧接口尚未彻底移除。

---

## 六、下一步最值得做的事

1. 将 `data/characters.json` 的友好能力迁移为显式 `goodwill_abilities`。
2. 为角色 `trait_rule` 拆出结构化字段，至少先覆盖：
   - `script_constraints`
   - `base_traits`
   - `character_abilities`
   - `loop_start_effects`
   - `turn_end_effects`
   - `incident_modifiers`
3. 删除 `character_loader` / `ability_resolver` / `validation` 中对旧三字段的 fallback。
4. 等角色层迁移完成后，再下线 `collect_character_abilities()` 兼容入口。

---

## 七、当前优先级

1. 角色友好能力结构化迁移。
2. 角色 `trait_rule` 结构化拆分。
3. 删除旧字段与运行时 fallback。
4. 视需要补“每条规则一个显式专测”的测试矩阵，但这已不是实现阻塞项。
