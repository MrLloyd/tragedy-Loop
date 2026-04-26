# Phase 7 角色友好能力结构化迁移记录

日期：2026-04-26

范围：`data/characters.json` 中角色友好能力从旧三字段

- `goodwill_ability_texts`
- `goodwill_ability_goodwill_requirements`
- `goodwill_ability_once_per_loop`

迁移到正式结构化入口 `goodwill_abilities`。

---

## 一、这轮实际完成了什么

### 1. 通用原语 / 选择器补齐

- 新增 selector：
  - `any_other_character`
  - `same_area_any_or_board`
  - `same_area_attribute:<attr>`
  - `same_area_limit_reached_other`
  - `any_character_limit_reached`
  - `any_dead_character`
  - `same_area_dead_character`
  - `identity:<identity_id>`
- 新增 effect：
  - `protagonist_protect`
  - `lift_forbidden_areas`
- 已接通现有效果：
  - `revive_character`

### 2. 友好能力补充输入类型

- `choose_token_type`
  - 现已可限制到指定 options，支持 `hope / despair` 这类子集选择。
- `choose_place_or_remove`
  - 现已可把同一条结构化能力收束为“放置 / 移除”二选一。

### 3. 候选能力可用性过滤

- 可选能力在没有合法目标时，不再出现在可声明列表里。
- 这轮重点覆盖了“达限角色”“尸体”“角色/版图二选一”这几类目标。

### 4. 交互链根因修复

- 修复了一个结构化结算链问题：
  - 当某个 effect 的第一步选择只有唯一答案时，系统会自动套用；
  - 但此前会错误跳过该 effect 后续仍需输入的 `mode` / `token` 选择。
- 本轮已修复为：
  - 自动锁定唯一目标后，仍会继续追问同一 effect 的后续选择。

---

## 二、已完成结构化迁移的角色

当前已有 `33` 个角色把友好能力迁入 `goodwill_abilities`，当前仅 `hermit` 仍未迁。

### 1. 已结构化且已接线的角色

- `higher_being`
- `temp_worker_alt`
- `idol`
- `soldier`
- `detective`
- `doctor`
- `vip`
- `ojousama`
- `female_student`
- `media_person`
- `scholar`
- `little_girl`
- `outsider`
- `shrine_maiden`
- `phantom`
- `alien`
- `henchman`
- `nurse`
- `cult_leader`
- `teacher`
- `class_rep`
- `male_student`
- `deity`
- `office_worker`
- `appraiser`（友好2：公开尸体身份）
- `transfer_student`
- `sacred_tree`

### 2. 本轮新增的 data-only 结构化迁移

以下 `6` 个角色本轮**不新增引擎功能**，仅把旧三字段中的文本 / goodwill 门槛 / 次数限制迁入 `goodwill_abilities`；运行时仍保持 legacy 期间的空 `effects` 语义：

- `ai`
- `streamer`
- `servant`
- `sister`
- `informant`
- `copycat`

说明：

- 这里指的是“友好能力结构化迁移完成”。
- **不等于**“该角色全部 trait / 生命周期 /剧本制作时约束 / 特殊事件交互 已完全收口”。

---

## 三、当前仍未完成的点

### 1. 唯一仍未迁入结构化字段的角色

- `hermit`

### 2. 已结构化但仍缺语义接线的代表角色

- `ai`
- `streamer`
- `servant`
- `informant`
- `copycat`
- `appraiser`（友好1 待 `MOVE_TOKEN`；友好2 已接线）

典型缺口：

- 事件代打 / 事件不视作已发生
- 复合目标绑定
- 两目标之间移动 token
- 回收已使用行动牌 / 转移 Ex 牌
- 公开“同身份全部角色名”
- 将角色追加到 trait 适用对象

---

## 四、当前边界

- 旧三字段仍保留在 `data/characters.json` 的部分角色中，作为迁移期兼容数据。
- `character_loader` 与 `ability_resolver` 的 legacy fallback **暂未删除**。
- 原因不是没法删，而是：
  - 仍有大量角色未迁完；
  - 现在删除会把未迁移角色直接打挂。

因此当前状态是：

- **结构化入口已开始成为主入口**
- **兼容入口仍保留，等待角色批量迁完后统一下线**

---

## 五、这轮验证结果

已通过：

- `pytest -q tests/test_goodwill_structured_migration.py tests/test_character_loader.py tests/test_ability_resolver.py tests/test_phase5_first_steps_abilities.py`
- `pytest -q tests/test_phase4_handlers.py tests/test_debug_api.py tests/test_test_mode_controller.py`
- `python3 -m engine.validation`

### 公开身份友好能力验收（2026-04-26）

验收口径：

- 可选目标类能力：必须先通过 selector 产出合法目标列表，再完成一次实际选择
- 所有能力：至少执行到 `reveal_identity` effect

专项回归已通过：

- `pytest -q tests/test_goodwill_structured_migration.py -k 'office_worker_structured_goodwill_reveals_self or temp_worker_alt_structured_goodwill_reveals_self_and_places_two_goodwill or outsider_structured_goodwill_requires_loop_two_and_is_not_refusable or shrine_maiden_structured_goodwill_reveals_selected_same_area_character or cult_leader_structured_goodwill_reveals_selected_limit_reached_other_character or teacher_structured_goodwill_reveals_selected_student or appraiser_structured_goodwill_reveals_selected_corpse'`

已验收通过的公开身份友好能力：

- `office_worker` 友好1：固定 `self`，直接公开自身身份
- `temp_worker_alt` 友好1：先公开 `self`，再通过 selector 选择同区域角色放置 `2` 枚友好
- `outsider` 友好1：固定 `self`，第 `2` 轮轮回或之后可用，且不可拒绝
- `shrine_maiden` 友好2：通过 selector 选择同一区域角色公开身份
- `cult_leader` 友好2：通过 selector 选择同一区域“不安达限度”的其他角色公开身份
- `teacher` 友好2：通过 selector 选择同一区域学生公开身份
- `appraiser` 友好2：通过 `dead_character` selector 选择尸体公开身份

专项回归覆盖点：

- 新 selector 解析
- 角色/版图混合目标
- 尸体目标与复活
- 达限目标筛选
- `choose_place_or_remove`
- `choose_token_type`
- `protagonist_protect`

---

## 六、下一步建议

优先顺序建议保持为：

1. `hermit` 的结构化迁移（当前按用户要求暂缓）
2. 在允许新增引擎功能后，优先补齐：
   - `streamer`
   - `appraiser`
   - `ai`
   - `servant`
   - `informant`
   - `copycat`
3. 等语义补齐覆盖率足够后，再统一删除 legacy goodwill fallback
