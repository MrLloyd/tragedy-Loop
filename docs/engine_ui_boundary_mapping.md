# 惨剧轮回：Engine / UI 适配边界映射

本文件专门列出 **不是纯 engine 规则、也不是纯 UI 展示** 的中间层。

它的作用是避免这类问题被误判：

- engine 其实已经算对了，但 UI 没拿到
- UI 其实能显示，但适配层没转发
- `WaitForInput`、`VisibleGameState`、`UICallback` 这种对象到底归谁维护不清楚

配套文档：

- `docs/rules_to_engine_mapping.md`
- `docs/rules_to_ui_mapping.md`

---

## 1. 这层负责什么

适配边界层主要负责：

- 把 engine 的状态变化转成 UI 可消费的数据
- 把 UI 的输入转回 engine 的 `provide_input(...)`
- 在不改变规则本体的前提下，处理显示视角、日志整理、刷新时机

一句话：

- engine 决定 **规则结果**
- UI 决定 **如何显示**
- 适配层决定 **怎么把前者送到后者**

---

## 2. 核心边界对象

| 边界对象 | 主要代码 | 作用 |
|----------|----------|------|
| `UICallback` | `engine/game_controller.py` | engine 推送给 UI 的回调接口 |
| `WaitForInput` | `engine/phases/phase_base.py` | engine 声明“现在需要什么输入” |
| `VisibleGameState` | `engine/visibility.py` | engine 输出给某个视角的可见状态 |
| `GameSessionController` | `ui/controllers/game_session_controller.py` | 当前主要适配器，承接 engine 与 UI |
| `SessionViewState` | `ui/controllers/game_session_controller.py` | UI 页面消费的会话态 |
| `PlacementIntent` | `engine/models/cards.py` | UI 放牌输入回传给 engine 的标准结构 |

---

## 3. 数据流映射

### 3.1 Engine -> UI

主要链路：

1. `engine/game_controller.py`
2. `UICallback`
3. `ui/controllers/game_session_controller.py`
4. `SessionViewState`
5. `ui/screens/*.py`

关键回调：

| 回调 | 来源 | 去向 | 说明 |
|------|------|------|------|
| `on_phase_changed(...)` | `engine/game_controller.py` | `GameSessionController` | 阶段切换 |
| `on_state_changed(...)` | `engine/game_controller.py` | `GameSessionController` | 原子结算后的即时刷新 |
| `on_wait_for_input(...)` | `engine/game_controller.py` | `GameSessionController` | 当前等待输入 |
| `on_announcement(...)` | `engine/game_controller.py` | `GameSessionController` | 主人公侧公告 |
| `on_game_over(...)` | `engine/game_controller.py` | `GameSessionController` | 终局 |

### 3.2 UI -> Engine

主要链路：

1. `ui/screens/*.py`
2. `ui/controllers/game_session_controller.py`
3. `engine/game_controller.py`
4. `WaitForInput.callback`

关键输入：

| UI 输入 | 标准结构 | engine 接收点 |
|---------|----------|---------------|
| 非公开信息表提交 | `dict[str, object]` | `submit_script_setup()` |
| 放置行动牌 | `PlacementIntent` | `submit_place_action_card()` |
| 批量放牌 | `list[PlacementIntent]` | `submit_place_action_cards()` |
| 单项选择 | `Any` | `submit_input()` |
| Pass | `"pass"` | `submit_pass()` |
| 允许 / 拒绝 | `"allow"` / `"refuse"` | `submit_goodwill_response()` |

---

## 4. 按问题类型定位

### 4.1 这些问题优先查适配层

| 问题类型 | 优先文件 |
|----------|----------|
| engine 已结算，但界面没立刻刷新 | `engine/game_controller.py`, `ui/controllers/game_session_controller.py` |
| 提交失败后输入态丢失 | `ui/controllers/game_session_controller.py` |
| 主人公 / 剧作家视角数据串了 | `engine/visibility.py`, `ui/controllers/game_session_controller.py` |
| 某条日志应该能看到但没进公告栏 | `engine/game_controller.py`, `ui/controllers/game_session_controller.py` |
| 等待输入类型对了，但控件没拿到 | `ui/controllers/game_session_controller.py`, `ui/screens/game_screen.py` |
| 新增 engine 事件后 UI 没同步 | `engine/game_controller.py`, `ui/controllers/game_session_controller.py` |

### 4.2 这些问题不要只改适配层

| 问题类型 | 应回到哪层 |
|----------|------------|
| 本来就不该触发这个输入 | engine |
| 本来就不该公开这条信息 | engine |
| 输入选项集合本身不对 | engine |
| 规则结算结果不对 | engine |
| 布局丑或控件行为不顺手 | UI |

---

## 5. 当前文件职责

### 5.1 `engine/game_controller.py`

负责：

- 调度主循环
- 在合适时机调用 `UICallback`
- 把 engine 事件转发成 UI 可消费的状态更新

不负责：

- 具体控件布局
- 直接操作 Qt 组件

### 5.2 `ui/controllers/game_session_controller.py`

负责：

- 存 `SessionViewState`
- 接 `UICallback`
- 整理主人公 / 剧作家公告
- 把 UI 输入回传到 engine
- 在提交失败时恢复等待态

不负责：

- 规则裁定本身
- 直接定义哪些信息可见

### 5.3 `ui/screens/*.py`

负责：

- 把 `SessionViewState` 渲染成界面
- 收集用户点击 / 选择
- 调用 controller 提交输入

不负责：

- 规则是否合法
- 触发时机是否正确

---

## 6. 当前项目中的边界锚点

| 主题 | 文件 |
|------|------|
| `UICallback` 定义 | `engine/game_controller.py` |
| `WaitForInput` 定义 | `engine/phases/phase_base.py` |
| `VisibleGameState` 定义 | `engine/visibility.py` |
| 会话适配器 | `ui/controllers/game_session_controller.py` |
| 新游戏页输入适配 | `ui/controllers/new_game_controller.py` |
| 对局页输入渲染 | `ui/screens/game_screen.py` |

---

## 7. 使用顺序建议

以后遇到问题，优先这样判断：

1. 这是 **规则错了**，还是 **显示错了**？
2. 如果两边看起来都对，再查 **适配边界**

推荐顺序：

- 先看 `docs/rules_to_engine_mapping.md`
- 再看 `docs/rules_to_ui_mapping.md`
- 如果仍卡在中间，再看 `docs/engine_ui_boundary_mapping.md`

---

## 8. 文档维护规则

当出现以下变化时，更新本文件：

- `UICallback` 新增或改名
- `WaitForInput.input_type` 新增适配逻辑
- `SessionViewState` 字段结构变化
- engine -> UI 刷新机制变化
- 主人公 / 剧作家双视角适配逻辑变化
