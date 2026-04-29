# Phase 7 测试与角色实现清单

日期：2026-04-28

范围：`First Steps` / `Basic Tragedy X`

目标：确认 `模组`、`规则`、`身份`、`事件` 已在测试界面完成收口，并把下一阶段切换到 `角色能力 / 特性结构化状态记录 -> 分批验证 -> 角色总测`。

---

## 一、当前结论

- [x] 模组测试界面验证完成
- [x] 规则测试界面验证完成
- [x] 身份测试界面验证完成
- [x] 事件测试界面验证完成
- [x] 剧本公开 / 非公开信息表边界已拆分并完成回归
- [x] “剧本制作时”类规则 / 角色约束改为正式版建局流程验证
- [ ] 角色实现完成
- [ ] 角色总测完成

---

## 二、模组测试

### 检查项

- [x] `first_steps` 可以正常加载
- [x] `basic_tragedy_x` 可以正常加载
- [x] 两个模组的基础配置进入运行时无误
- [x] 两个模组都能完成建局并进入测试流程

### 结论

- 模组测试已收口，后续仅保留角色实现后的回归冒烟。

---

## 三、规则测试

### `First Steps`

- [x] `fs_murder_plan`（谋杀计划）
- [x] `fs_revenge_kindling`（复仇的火种）
- [x] `fs_protect_this_place`（守护此地）
- [x] `fs_ripper_shadow`（开膛者的魔影）
- [x] `fs_rumors`（流言四起）
- [x] `fs_darkest_script`（最黑暗的剧本）
- [x] `First Steps` 规则测试完成

### `Basic Tragedy X`

- [x] `btx_murder_plan`（谋杀计划）
- [x] `btx_cursed_contract`（和我签订契约吧）
- [x] `btx_sealed_evil`（被封印的邪灵）
- [x] `btx_change_future`（改变未来）
- [x] `btx_giant_time_bomb_x`（巨大定时炸弹X）
- [x] `btx_friends_circle`（好友圈）
- [x] `btx_love_scenic_line`（恋爱风景线）
- [x] `btx_rumors`（流言四起）
- [x] `btx_latent_serial_killer`（潜伏的杀人狂）
- [x] `btx_causal_line`（因果线）
- [x] `btx_delusion_spread_virus`（妄想扩大病毒）
- [x] `btx_unknown_factor_chi`（未知因子Χ）
- [x] `Basic Tragedy X` 规则测试完成

### 说明

- 规则本体已按测试界面收口。
- 后续若出现“角色未实现导致的联动差异”，统一转入角色实现回归，不再把前四项重新打开。

---

## 四、身份测试

### `First Steps`

- [x] `key_person`（关键人物）
- [x] `killer`（杀手）
- [x] `mastermind`（主谋）
- [x] `cultist`（邪教徒）
- [x] `friend`（亲友）
- [x] `thug`（暴徒）
- [x] `rumormonger`（传谣人）
- [x] `serial_killer`（杀人狂）
- [x] `First Steps` 身份测试完成

### `Basic Tragedy X`

- [x] `key_person`（关键人物）
- [x] `killer`（杀手）
- [x] `mastermind`（主谋）
- [x] `cultist`（邪教徒）
- [x] `witch`（魔女）
- [x] `friend`（亲友）
- [x] `serial_killer`（杀人狂）
- [x] `rumormonger`（传谣人）
- [x] `time_traveler`（时间旅者）
- [x] `beloved`（心上人）
- [x] `lover`（求爱者）
- [x] `unstable_factor`（不安定因子）
- [x] `Basic Tragedy X` 身份测试完成

### 说明

- 身份阶段已收口；后续只做角色联动回归。

---

## 五、事件测试

### 检查项

- [x] `First Steps` 事件测试完成
- [x] `Basic Tragedy X` 事件测试完成
- [x] 关键事件已覆盖：`murder`
- [x] 关键事件已覆盖：`hospital_accident`
- [x] 关键事件已覆盖：`suicide`
- [x] 关键事件已覆盖：`spread`
- [x] 关键事件已覆盖：`disappearance`
- [x] 关键事件已覆盖：`long_range_murder`
- [x] 关键事件已覆盖：`butterfly_effect`
- [x] 关键事件已覆盖：`spiritual_contamination`

### 说明

- 事件阶段已收口；后续角色相关事件差异统一并入角色回归。

---

## 五点五、2026-04-28 补记：剧本信息边界与 AI / 情报商 / 鉴别员

### 剧本信息边界

- [x] `Script` 已拆分为 `public_table` 与 `private_table`
- [x] 运行时真值统一从 `private_table` 读取，默认不再从公开信息表取规则 / 角色 / 事件真值
- [x] `public_table` 仅保留给主人公阅读的内容：
  - `module_id`
  - `loop_count`
  - `days_per_loop`
  - 公开事件名称与发生天数
  - 特殊规则
- [x] `private_table` 统一承载实际运行所需数据：
  - 模组
  - 规则 `Y / X`
  - 轮回数
  - 每轮回天数
  - 实际事件、发生天数、当事人
  - 登场角色
  - 特殊规则
- [x] 可见性与 UI 展示统一读取 `public_table`
- [x] `public_incident_refs` 支持“公开事件 -> 真实事件”映射；若未显式填写，则按私有事件同索引回退

### 角色专项补记

- [x] `goodwill:ai:1`
  - 从公开信息表选择事件
  - 实际效果映射到私有真实事件执行
  - 当事人视为 `AI`
  - 事件中的所有目标选择统一由队长完成
  - 仅处理事件效果，不标记事件已发生，不写公开结果，不发送 `INCIDENT_OCCURRED`
  - 不会触发 `改变未来` 中“蝴蝶效应已发生”的失败条件

- [x] `goodwill:informant:1`
  - 已按规则改为：主人公先声明 1 条所选规则 `X`，剧作家再从剧本已选规则 `X` 中公开另一条，且不得与主人公选择重复
  - `First Steps` 维持特判：剧作家直接公开规则 `X`
  - 已公开规则 `X` 状态改存于 `GameState.revealed_rule_x_ids`，并跨轮回保留

- [x] `goodwill:appraiser:1`
  - 已按裁定改为：先选同区域 2 名角色，再选择 1 枚指示物移动
  - 仅当 `A / B` 两名角色都没有指示物时，才允许“无效果”
  - 只要 `A` 或 `B` 任一角色上有可移动指示物，就必须选择其中一个合法移动

### 已完成回归

- [x] `tests/test_phase4_handlers.py`
  - `AI` 公开事件代结算
  - `informant` 规则 `X` 公开流程
  - `appraiser` 指示物移动边界
- [x] `tests/test_incident_handler.py`
  - `IncidentResolver.resolve_effect_only()` 只处理效果、不记事件发生
- [x] `tests/test_module_apply.py`
  - 运行时读取私有表、可见性读取公开表
  - 公开事件到私有事件的默认映射回退

---

## 六、角色能力与特性结构化状态

### 6.1 角色能力

#### 本轮执行顺序

1. 实现仅改变标记物的能力，按结构化能力直接接线；如果需要补充新的原语、选择器、条件或额外运行时机制，先请示后再继续。

#### 角色友好能力逐项状态

- [x] 在“带友好能力文本”的 `34` 个角色中，`33` 个已迁入 `goodwill_abilities`；当前仅 `hermit` 仍未迁入结构化字段
- [x] 下面按 `ability_id` 记录能力状态；后续逐个能力开发时，默认以本表为认领入口

##### 已实现并纳入当前完成统计

| 状态 | 能力 | 角色 / 友好能力 | 已接线语义 |
|------|------|-----------------|------------|
| [x] | `goodwill:idol:1` | `idol` 友好1 | 移除同区域另 1 名角色身上 1 枚不安 |
| [x] | `goodwill:idol:2` | `idol` 友好2 | 往同区域另 1 名角色身上放置 1 枚友好 |
| [x] | `goodwill:higher_being:1` | `higher_being` 友好1 | 往同区域任意 1 名角色身上放置 1 枚希望 / 绝望；带无视友好身份且友好达标时，剧作家阶段也可使用 |
| [x] | `goodwill:soldier:1` | `soldier` 友好1 | 往同区域任意 1 名角色身上放置 2 枚不安 |
| [x] | `goodwill:soldier:2` | `soldier` 友好2 | 本轮回中主人公不会死亡，走 `protagonist_protect` |
| [x] | `goodwill:detective:1` | `detective` 友好1 | 公开 1 个本轮已发生事件的当事人，统一公告文本 |
| [x] | `goodwill:detective:2` | `detective` 友好2 | 往同区域任意 1 名角色身上放置 1 枚护卫 |
| [x] | `goodwill:doctor:1` | `doctor` 友好1 | 放置 / 移除同区域另外 1 名角色身上 1 枚不安；带无视友好身份且友好达标时，剧作家阶段也可使用 |
| [x] | `goodwill:ojousama:1` | `ojousama` 友好1 | 位于学校 / 都市时，往同区域任意 1 名角色身上放置 1 枚友好 |
| [x] | `goodwill:female_student:1` | `female_student` 友好1 | 移除同区域另外 1 名角色身上 1 枚不安 |
| [x] | `goodwill:media_person:1` | `media_person` 友好1 | 往另外 1 名角色身上放置 1 枚不安 |
| [x] | `goodwill:media_person:2` | `media_person` 友好2 | 往同区域任意角色或版图放置 1 枚密谋 |
| [x] | `goodwill:little_girl:1` | `little_girl` 友好1 | 本轮回解除自身禁行区域 |
| [x] | `goodwill:little_girl:2` | `little_girl` 友好2 | 移动至相邻版图，最终走 `GameState.move_character()` |
| [x] | `goodwill:outsider:1` | `outsider` 友好1 | 第 2 轮后公开自身身份，且不可拒绝 |
| [x] | `goodwill:shrine_maiden:1` | `shrine_maiden` 友好1 | 位于神社时，移除神社 1 枚密谋 |
| [x] | `goodwill:shrine_maiden:2` | `shrine_maiden` 友好2 | 公开同区域任意 1 名角色身份 |
| [x] | `goodwill:phantom:1` | `phantom` 友好1 | 选择同区域角色并移动至任意版图，最终走 `GameState.move_character()` |
| [x] | `goodwill:alien:1` | `alien` 友好1 | 选择同区域其他活体角色，走 `DeathResolver.process_death()` |
| [x] | `goodwill:alien:2` | `alien` 友好2 | 选择同区域尸体并复活 |
| [x] | `goodwill:henchman:1` | `henchman` 友好1 | 成功发动后，本轮回中该角色为当事人的事件不会发生 |
| [x] | `goodwill:nurse:1` | `nurse` 友好1 | 移除同区域不安达限度的其他角色身上 1 枚不安，且不可拒绝 |
| [x] | `goodwill:cult_leader:1` | `cult_leader` 友好1 | 往不安达限度角色身上放置 1 枚友好 |
| [x] | `goodwill:cult_leader:2` | `cult_leader` 友好2 | 公开同区域不安达限度的其他角色身份 |
| [x] | `goodwill:class_rep:1` | `class_rep` 友好1 | 当前队长可回收自己已打出且已用的一轮回一次手牌 |
| [x] | `goodwill:teacher:1` | `teacher` 友好1 | 放置 / 移除同区域 1 名学生身上 1 枚不安 |
| [x] | `goodwill:teacher:2` | `teacher` 友好2 | 公开同区域 1 名学生身份 |
| [x] | `goodwill:male_student:1` | `male_student` 友好1 | 移除同区域另外 1 名角色身上 1 枚不安 |
| [x] | `goodwill:deity:1` | `deity` 友好1 | 公开 1 个事件的当事人，统一公告文本 |
| [x] | `goodwill:deity:2` | `deity` 友好2 | 移除同区域任意角色或版图上 1 枚密谋 |
| [x] | `goodwill:office_worker:1` | `office_worker` 友好1 | 公开自身身份 |
| [x] | `goodwill:temp_worker_alt:1` | `temp_worker_alt` 友好1 | 公开自身身份，并选择同区域角色放置 2 枚友好 |
| [x] | `goodwill:transfer_student:1` | `transfer_student` 友好1 | 将同区域其他角色身上 1 枚密谋替换为友好 |
| [x] | `goodwill:appraiser:2` | `appraiser` 友好2 | 选择 1 具尸体并公开身份 |

##### 已结构化接线，待后续专项复核

| 状态 | 能力 | 角色 / 友好能力 | 需要复核的点 |
|------|------|-----------------|--------------|
| [x] | `goodwill:doctor:2` | `doctor` 友好2 | `lift_forbidden_areas` 已接线；待专项回归确认住院患者禁行解除 |
| [x] | `goodwill:vip:1` | `vip` 友好1 | `reveal_identity` 已接线；待专项回归确认“领地中另外 1 名角色”范围 |
| [ ] | `goodwill:scholar:1` | `scholar` 友好1 | 已确认 FS / BTX 无 EX 槽分支；带 EX 槽模组的 +1 / -1 分支待后续专项回归 |
| [x] | `goodwill:phantom:2` | `phantom` 友好2 | `remove_character` 已接线；待专项回归确认离场状态与后续行动牌路由。后续统一采用三态入口：`ACTIVE / DEAD / REMOVED`，并由 `CharacterState.life_state()` 派生 `is_active()` / `is_dead()` |

##### 已结构化但仍有缺口

| 状态 | 能力 | 角色 / 友好能力 | 当前缺口 |
|------|------|-----------------|----------|
| [x] | `goodwill:ai:1` | `ai` 友好1 | 已接线专用交互；从公开信息表选事件并映射到私有真实事件，仅执行效果，不标记事件已发生 |
| [ ] | `goodwill:streamer:1` | `streamer` 友好1 | 仍为空 `effects`；需放置友好、移除不安，并处理 Ex 牌转移 |
|[x]| `goodwill:servant:1` | `servant` 友好1 | 仍为空 `effects`；需本轮追加特性适用对象 |
|[x] | `goodwill:sister:1` | `sister` 友好1 | 仍为空 `effects`；需让同区域成人无视友好数量使用 1 个友好能力，且不可拒绝 |
| [x] | `goodwill:informant:1` | `informant` 友好1 | 已接线专用交互并通过规则流程回归；后续只需继续观察正式 UI 展示 |
| [ ] | `goodwill:copycat:1` | `copycat` 友好1 | 仍为空 `effects`；需公开场上与自身身份相同的全部角色名 |
| [x] | `goodwill:appraiser:1` | `appraiser` 友好1 | 已接线专用交互并通过边界回归；仅当两名目标都无指示物时才无效果，否则必须移动 1 枚合法指示物 |

#### 未结构化

- [ ] `hermit`
  - 原因：友好能力仍停留在旧三字段
  - 缺口：需要同时表达“移动至任意版图或远方 -> 复活同区域尸体 -> 按剧本 X 值放置友好”的多步联动
  - 备注：还牵涉动态 `X` 值与事件判定位置替代；本轮按当前要求继续暂缓

### 6.2 角色特性

#### 已结构化实现

- [x] 通用 trait 运行时层已接线：`base_traits`、身份 trait、`derived_traits`、`suppressed_traits`
- [x] `ai`
  - 剧本制作时“不能为平民”已纳入校验
  - 事件判定时“所有指示物都视作不安指示物”已有专门分支
- [x] `sister`
  - 剧本制作时“不能配置为带无视友好特性的身份”已纳入校验
- [x] `henchman`
  - 每轮初始区域选择已通过 `initial_area_mode = mastermind_each_loop` 接线
- [x] `servant`、`hermit`
  - 剧本指定初始区域已通过 `initial_area_mode = script_choice` 与 `initial_area_candidates` 接线

#### 未结构化

- [ ] 脚本制作时的跨角色身份 / 当事人绑定
  - `temp_worker_alt`：需要与 `temp_worker` 同步身份与事件当事人配置，当前缺少跨角色脚本绑定入口
  - [x]`outsider`：需要分配“当前模组存在、且剧本未带有”的身份，当前缺少角色定制身份分配器
  - [x]`copycat`：需要复制另一名角色身份并突破身份上限，当前缺少“复制并追加身份”机制

- [ ] 生命周期 / 延迟登场
  - `temp_worker`：需要同时处理“身份强制为平民”“总指示物 ≥ 3 死亡”“死亡后使 `temp_worker_alt` 在都市上场”，当前缺少跨角色生命周期链
  - [x] `deity`：`entry_loop` 仅有预留字段，尚未接线到轮回准备 / 登场流程
  - [x]`transfer_student`：`entry_day` 仅有预留字段，尚未接线到回合开始登场流程

- [ ] 事件覆写 / 事件重放 / 事件判定替代
  - [x]`black_cat`：需要在轮回开始时自动往神社放置密谋，并把其为当事人的事件改为“无现象”，当前缺少角色级事件覆写
  - [x]`cult_leader`：需要把其为当事人的事件按文字结算 `2` 次，当前缺少事件重放 / 二次结算链
  - [x]`hermit`：需要把其为当事人的事件判定位置视作顺时针相邻版图，当前缺少事件判定位置替代

- [ ] 行动牌 / 区域投影 / 跟随与代死
  - `streamer`：需要处理 `Ex` 牌设置，以及“将放置有 `Ex` 牌角色所在区域视为自身所在区域”，当前缺少 `Ex` 牌生命周期与区域投影
  - [x] `phantom`：行动牌路由已接入；`NO_ACTION_CARDS` 直接禁止在该角色身上放牌，版图牌按移动批次与非移动批次分别投影到当前所在角色
  - [x]`servant`：跟随 `vip / ojousama` 移动已接入，支持同批次多目标由主人公选择、忽略自身同阶段移动、并覆盖 `sequential`/“随后”；`trait_target_overrides` 已预留给友好能力扩展。仍缺代替死亡链

- [ ] 回合开始自动处理 / 强制使用语义
  - [x] `scholar`：需要在每轮轮回开始时选择并放置 `友好 / 不安 / 密谋` 之一，当前缺少 `loop_start` 选择链
  - [x] `sacred_tree`：需要在主人公能力阶段把自身 `1` 枚指示物移给同区域其他角色，并在无视友好时改由剧作家强制使用，当前缺少“无视友好 -> 剧作家强制声明”语义

- [ ] 其余说明
  - 未在此列出的角色，当前没有额外未拆解的 `trait_rule`，或其角色侧行为已完全落入现有通用入口

---

## 七、角色总测（角色实现完成后）

### 测试范围

- [ ] 角色能力测试
- [ ] 角色特性测试
- [ ] 初始区域 / 延迟登场测试
- [ ] 信息边界测试
- [ ] 关键角色交互测试

### 输出要求

- 角色总测结果单独记录，不与前四项混合统计。

---

## 八、完成标准

- [x] 模组测试完成
- [x] 规则测试完成
- [x] 身份测试完成
- [x] 事件测试完成
- [ ] 角色实现完成
- [ ] 角色总测完成
- [x] `PHASE7_GAP_CHECKLIST.md` 已同步更新
- [x] `PLAN.md` 的 Phase 7 已同步更新
- [x] `WORK_PROGRESS.md` 已按当前阶段同步更新



  已统一

  - 规则、身份、事件定义里的能力/效果在加载时都会解析成 Ability / Effect：engine/rules/module_loader.py:320 engine/rules/module_loader.py:336
    engine/rules/module_loader.py:361 engine/rules/module_loader.py:373
  - 身份能力、规则能力收集后，最终都下发到 AtomicResolver.resolve() 执行：engine/resolvers/ability_resolver.py:119 engine/resolvers/
    ability_resolver.py:171 engine/phases/phase_base.py:335
  - 事件的“实际效果”统一走 IncidentResolver -> AtomicResolver：engine/resolvers/incident_resolver.py:68
  - AtomicResolver 已统一承接具体 effect 执行，包括 kill_character、revive_character、change_identity、suppress_incident 等：engine/resolvers/
    atomic_resolver.py:178 engine/resolvers/atomic_resolver.py:474

  未统一

  - 规则的身份配额/范围约束不是 Effect，而是剧本校验逻辑：engine/models/script.py:16 engine/rules/script_validator.py:205
  - 模组级规则开关如 has_final_guess / has_ex_gauge / rule_x_count / special_rules 不是 Effect，而是流程/配置：engine/models/script.py:40 engine/
    game_state.py:219 engine/state_machine.py:126
  - 规则里的 ALWAYS + change_identity 常驻能力没有走 AtomicResolver，而是在常驻同步里直接 apply_identity_change()：engine/rules/
    persistent_effects.py:12 engine/rules/runtime_identities.py:19
  - 身份的 trait 系统 不走 Effect；IMMORTAL、NO_ACTION_CARDS、IGNORE_GOODWILL 等都是直接运行时判定：engine/models/identity.py:26 engine/rules/
    runtime_traits.py:10 engine/resolvers/death_resolver.py:43 engine/phases/phase_base.py:99 engine/resolvers/ability_resolver.py:497
  - 身份的 max_count 不是 Effect，走脚本校验：engine/models/identity.py:30 engine/rules/script_validator.py:255
  - 身份的 derived_identities 也不是 Effect；它只是决定“派生身份能力是否出现”，派生出来的 ability 才走 effect：engine/models/identity.py:13 engine/
    resolvers/ability_resolver.py:213
  - 事件的触发判定（已发生、被压制、当事人存活、不安阈值、extra_condition）不走 Effect：engine/resolvers/incident_resolver.py:130
  - 事件的发生标记、公开结果记录、公开事件广播不走 Effect：engine/resolvers/incident_resolver.py:178 engine/resolvers/incident_resolver.py:192
  - 事件字段 modifies_paranoia_limit 是直接改触发阈值，不是 Effect：engine/models/incident.py:41 engine/resolvers/incident_resolver.py:165
  - 事件字段 is_crowd_event / required_corpse_count / no_ex_gauge_increment / ex_gauge_increment / perpetrator_area 目前只在模型声明，repo 内未看到
    运行时消费：engine/models/incident.py:39 engine/models/incident.py:56
  - 规则字段 special_victory 目前也只在模型声明，repo 内未看到运行时使用：engine/models/script.py:31

  一句话总结

  - “效果本体”大体统一了，Effect 链已经是主干。
  - “条件、约束、trait、常驻同步、事件发生流程”还没有统一进 Effect。

  如果你要，我下一步可以把这些再整理成一份“哪些属于可迁移进 Effect 的待办清单”。
