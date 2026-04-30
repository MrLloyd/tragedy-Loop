# 惨剧轮回：规则文档 → UI 映射

本文件把规则文档中的“玩家应该看到什么、什么时候输入什么”映射到 `ui/` 代码，目的是把：

- **界面是否遵守规则文档**
- **某个显示或交互问题应该改哪里**

严格区分出来。

适用文档：

- `tragedy_loop_game_rules.md`
- `tragedy_loop_appendix.md`

不覆盖规则本体裁定；规则本体请看 `docs/rules_to_engine_mapping.md`。

当前核实说明：

- UI 下拉项的事实来源不是附录文本本身，而是 engine 返回的 `script_setup_context`
- 如果附录里有某条规则，但 `data/modules/*.json` 尚未录入，UI 不会凭空出现该项
- 因此“下拉项不全”必须先与 `docs/rules_to_engine_mapping.md` 中的实现覆盖范围一起判断
- 2026-04-22 起，`FS` / `BTX` 的规则数量已按附录补齐到 `data/modules/*.json`

---

## 1. 分层原则

下列问题归 `UI`：

- 非公开信息表该怎么录入
- 主人公界面和剧作家界面各显示什么
- 当前阶段如何显示给玩家
- 当前等待输入如何显示为按钮 / 下拉框 / 列表
- 公告栏如何呈现
- 测试期需要的双栏、调试快照如何摆放

下列文件是主要入口：

| 主题 | 主要代码 |
|------|----------|
| 应用入口 | `ui/app.py` |
| 主窗口与页面切换 | `ui/main_window.py` |
| 新游戏 / 非公开信息表 | `ui/screens/new_game_screen.py` |
| 对局画面 | `ui/screens/game_screen.py` |
| 标题 / 结果页 | `ui/screens/title_screen.py`, `ui/screens/result_screen.py` |
| UI ↔ engine 适配 | `ui/controllers/game_session_controller.py` |
| 非公开信息表 payload 装配 | `ui/controllers/new_game_controller.py` |

---

## 2. 规则文档主主题 → UI

| 规则主题 | UI 责任 | 主要代码 |
|----------|---------|----------|
| 非公开信息表 | 让剧作家录入模组、规则、角色、事件 | `ui/screens/new_game_screen.py` |
| 对局主界面 | 展示版图、角色、公开事件、等待输入 | `ui/screens/game_screen.py` |
| 页面流转 | 标题 → 新游戏 → 对局 → 结算 | `ui/main_window.py` |
| 输入回填 | 把 UI 选择提交给 engine | `ui/controllers/game_session_controller.py` |
| 公告显示 | 主人公告告栏、剧作家详细栏 | `ui/screens/game_screen.py`, `ui/controllers/game_session_controller.py` |
| 调试辅助 | 调试快照、测试期双栏并排 | `ui/screens/game_screen.py` |

---

## 3. 按玩家视角映射

### 3.1 主人公视角

规则文档中的主人公可见内容，在 UI 中主要落到：

| 规则主题 | 主要代码 | 说明 |
|----------|----------|------|
| 阶段文字 | `ui/screens/game_screen.py` | 顶部“阶段 / 轮回 / 天数 / 队长” |
| 公开事件 | `ui/screens/game_screen.py` | `public_info` 的展示 |
| 公开版图状态 | `ui/screens/game_screen.py` | 版图区域与角色当前状态 |
| 公告栏 | `ui/screens/game_screen.py` | 主人公侧公告栏 |
| 等待输入 | `ui/screens/game_screen.py` | 列表 + 目标选择 + 按钮 |

数据来源不是 UI 自己算，而是：

- `ui/controllers/game_session_controller.py`
- `engine/game_controller.py`
- `engine/visibility.py`

也就是说，主人公界面只负责显示，不负责定义什么能看。

### 3.2 剧作家视角

规则文档中的剧作家可见内容，在 UI 中主要落到：

| 规则主题 | 主要代码 | 说明 |
|----------|----------|------|
| 非公开信息表 | `ui/screens/new_game_screen.py` | 开局前配置 |
| 详细事件流 | `ui/controllers/game_session_controller.py` | 从事件总线日志整理 |
| 双栏详细公告 | `ui/screens/game_screen.py` | 测试期并排显示 |
| 目标列表 | `ui/screens/game_screen.py` | 放牌 / 能力目标优先用剧作家可见状态 |
| 调试快照 | `ui/screens/game_screen.py` | 当前测试辅助，不属于正式规则展示 |

---

## 4. 按交互规则映射

### 4.1 非公开信息表

| 规则主题 | 主要代码 | 说明 |
|----------|----------|------|
| 模组下拉 | `ui/screens/new_game_screen.py` | 模组选项 |
| 规则 Y / X 下拉 | `ui/screens/new_game_screen.py` | 规则选择 UI |
| 角色数量增减 | `ui/screens/new_game_screen.py` | 角色输入行增减 |
| 角色 / 身份选择 | `ui/screens/new_game_screen.py` | 每行的角色与身份 |
| 事件与当事人 | `ui/screens/new_game_screen.py` | 每天事件配置 |
| payload 生成 | `ui/controllers/new_game_controller.py` | 转为 engine 输入 |

适配边界：

- “有哪些可选项”来自 `engine.rules.module_loader.build_script_setup_context`
- “UI 怎么摆控件”属于 `ui/screens/new_game_screen.py`

排查顺序补充：

1. 先查附录实际应有几条规则
2. 再查 `data/modules/*.json` 当前已录入几条
3. 最后才判断 `ui/screens/new_game_screen.py` 是否漏显示 / 刷新错误

对当前仓库：

- `First Steps` 应显示 `规则Y=3`、`规则X=3`
- `Basic Tragedy X` 应显示 `规则Y=5`、`规则X=7`

### 4.2 对局等待输入

| 规则主题 | 主要代码 |
|----------|----------|
| 当前等待类型显示 | `ui/screens/game_screen.py` |
| 单选列表 | `ui/screens/game_screen.py` |
| 版图 / 角色目标下拉 | `ui/screens/game_screen.py` |
| 确认 / 提交 / pass / 允许 / 拒绝按钮 | `ui/screens/game_screen.py` |
| 输入提交与回填 | `ui/controllers/game_session_controller.py` |

当前主要输入类型映射：

| `WaitForInput.input_type` | UI 表现 |
|---------------------------|---------|
| `script_setup` | 新游戏页 |
| `place_action_card` | 卡牌列表 + 目标类型 + 目标下拉 |
| `choose_playwright_ability` | 列表单选 |
| `choose_goodwill_ability` | 列表单选 |
| `respond_goodwill_ability` | 允许 / 拒绝按钮 |
| `choose_ability_target` | 列表单选或目标选择 |

### 4.3 页面流转

| 规则节点 | 主要代码 |
|----------|----------|
| 标题页 | `ui/screens/title_screen.py` |
| 新游戏页 | `ui/screens/new_game_screen.py` |
| 对局页 | `ui/screens/game_screen.py` |
| 结果页 | `ui/screens/result_screen.py` |
| 总切换逻辑 | `ui/main_window.py` |

对应关系：

- 新游戏失败 / 校验失败仍停留新游戏页
- 剧本提交成功后进入对局页
- `Outcome` 出现后进入结果页

---

## 5. 按显示规则映射

### 5.1 阶段显示

| 规则主题 | 主要代码 | 说明 |
|----------|----------|------|
| 当前阶段名 | `ui/screens/game_screen.py` | 顶部状态区 |
| 阶段切换公告 | `ui/controllers/game_session_controller.py` | 当前已写入双公告栏 |

### 5.2 公告栏

| 规则主题 | 主要代码 | 说明 |
|----------|----------|------|
| 主人公告告 | `ui/controllers/game_session_controller.py` + `ui/screens/game_screen.py` | 展示公开公告 |
| 剧作家详细日志 | `ui/controllers/game_session_controller.py` + `ui/screens/game_screen.py` | 事件总线明细 |
| 双栏布局 | `ui/screens/game_screen.py` | 测试期同时显示 |

### 5.3 调试显示

| 规则主题 | 主要代码 |
|----------|----------|
| 调试快照按钮 | `ui/screens/game_screen.py` |
| 调试快照读取 | `ui/controllers/game_session_controller.py` |
| debug API | `engine/debug/api.py` |

注意：

- 调试快照不是规则文档要求的正式展示
- 它只是为了核对 engine 状态与 UI 状态是否一致

---

## 6. 按“该改哪里”来查

### 6.1 如果是这些问题，优先查 UI

| 问题类型 | 优先文件 |
|----------|----------|
| 下拉框没显示全 | `ui/screens/new_game_screen.py` |
| 角色数量不能加减 | `ui/screens/new_game_screen.py` |
| 提交失败后输入框消失 | `ui/controllers/game_session_controller.py`, `ui/screens/game_screen.py` |
| 公告栏排版不对 | `ui/screens/game_screen.py` |
| 阶段切换没显示 | `ui/controllers/game_session_controller.py`, `ui/screens/game_screen.py` |
| 双栏显示不合理 | `ui/screens/game_screen.py` |
| 页面没切换到结果页 | `ui/main_window.py` |

### 6.2 这些问题不要误判成 UI

下列问题通常不是 UI，而是 engine：

- 明明满足条件但能力没出现
- 事件发生日不对
- 行动牌结算结果不对
- 本不该公开的信息被公开
- 最终胜负判定错

这类问题请转看 `docs/rules_to_engine_mapping.md`。

---

## 7. UI 与 Engine 的边界

必须记住：

- UI 不决定规则，只消费规则结果
- UI 不决定哪些信息是公开，只消费 `VisibleGameState`
- UI 不决定等待什么输入，只消费 `WaitForInput`

因此可以按下面三句话判断：

- “该不该有这个控件” → 先看 UI
- “该不该出现这个输入类型” → 先看 engine
- “该不该显示这条信息” → 先看 `engine/visibility.py`

---

## 8. 当前适合继续维护的 UI 入口

后续如果继续补规则相关 UI，建议沿下面入口扩展：

1. `ui/main_window.py`
2. `ui/screens/new_game_screen.py`
3. `ui/screens/game_screen.py`
4. `ui/controllers/game_session_controller.py`
5. `ui/controllers/new_game_controller.py`

---

## 9. 文档维护规则

当出现以下变更时，必须同步更新本文件：

- 新增页面或切换逻辑
- 新增 `WaitForInput.input_type` 的 UI 表现
- 调整主人公 / 剧作家显示分栏
- 调整非公开信息表结构
- 新增正式展示区块

如果只是规则本体变化，不更新本文件，改更新 `docs/rules_to_engine_mapping.md`。
