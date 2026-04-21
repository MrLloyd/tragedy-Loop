# Phase 6 `GAME_PREPARE` / UI 接入草案

## 目标

在 **不提前修改 `engine/`** 的前提下，明确 Phase 6 后续接线方案，使：

- 非公开信息表在 `GAME_PREPARE` 中完成
- UI 层只使用 engine 已公开的 UI 交互入口
- 引擎负责剧本构建、合法性校验、落地到运行时状态
- UI 负责表单展示、编辑、提交、错误回显

---

## 已确认约束

- Phase 6 期间，如需修改 `engine/` 或新增 engine 接口，**先征求确认**
- UI 层只能通过 engine 提供的 UI 接口交互
- 规则文档约束：**设置非公开信息表属于 `GAME_PREPARE`**
- 不采用“UI 主动拉取剧本信息”的新 callback 设计
- 统一方向：`GAME_PREPARE` -> `WaitForInput("script_setup")` -> UI 填表 -> `provide_input(...)` 回传

---

## 当前 UI 侧已具备内容

- `ui/controllers/new_game_controller.py`
  - `default_phase5_draft()`
  - `build_character_setups()`
  - `build_incidents()`
  - `build_payload()`
- `ui/screens/new_game_screen.py`
  - `NewGameScreenModel`
  - 默认载入 Phase 5 非公开信息表
  - 可编辑基础字段并生成 payload
- `ui/controllers/game_session_controller.py`
  - 仅通过 `UICallback` 接收引擎状态
  - 仅通过 `GameController.provide_input(...)` 回传输入

这部分可以继续复用，不要求新增 UI ↔ engine 专用通道。

---

## 建议的最小闭环

### 1. `GAME_PREPARE` 首次进入时挂起

`GamePrepareHandler.execute(state)` 不再直接 `PhaseComplete()`，而是：

- 若当前对局尚未完成剧本设置
- 返回：

```python
WaitForInput(
    input_type="script_setup",
    prompt="请填写非公开信息表",
    options=[...可选元数据...],
    player="mastermind",
    callback=...
)
```

其中：

- `input_type="script_setup"` 作为 UI 路由标识
- `options` 不承载业务状态本体，只承载 UI 渲染所需元数据
- 提交后仍走现有 `provide_input(...)`

### 2. UI 根据 `input_type` 打开非公开信息表

UI 收到 `on_wait_for_input(wait)` 后：

- 若 `wait.input_type == "script_setup"`
- 打开/切换到新游戏非公开信息表
- 默认填充 Phase 5 草稿
- 允许用户修改后提交

### 3. UI 回传统一 payload

建议 `provide_input(...)` 回传结构沿用现有 `NewGameController.build_payload()` 形状：

```python
{
    "module_id": "first_steps",
    "loop_count": 3,
    "days_per_loop": 3,
    "rule_y_id": "fs_murder_plan",
    "rule_x_ids": ["fs_ripper_shadow"],
    "character_setups": list[CharacterSetup],
    "incidents": list[IncidentSchedule],
}
```

这样可直接复用现有 UI 草稿转换逻辑，避免再造一层字段映射。

### 4. 引擎在 callback 中完成装配与校验

`script_setup` 的 callback 内负责：

- 校验 payload 结构
- 基于 `module_id` 加载模组
- 将角色身份、事件日程、规则 Y/X、轮回配置写入运行时状态
- 触发 `GAME_PREPARE` 阶段的剧本合法性校验
- 成功后返回 `PhaseComplete()`
- 失败后返回新的 `WaitForInput("script_setup")`，并附带错误信息

---

## 建议的数据职责边界

### UI 负责

- 展示表单
- 维护编辑态
- 基础表单校验
  - 空值
  - 重复角色
  - 事件当事人必须在角色列表中
  - 天数范围合法
- 把草稿转换为 engine 输入 payload
- 接收并显示 engine 返回的错误

### engine 负责

- 模组装载
- 角色/身份/事件/规则对象化
- `GAME_PREPARE` 业务合法性校验
  - 模组内身份可用性
  - 规则 Y/X 组合合法性
  - 角色约束 / script constraints
  - 事件与身份/角色冲突校验
- 写入 `GameState`
- 成功后推进到 `LOOP_START`

---

## 建议的 `WaitForInput("script_setup")` 内容

为了让 UI 不自己读取 engine 内部数据，建议 `options` 或附带字段仅提供**渲染元数据**：

```python
{
    "default_draft": {...},
    "available_modules": [...],
    "available_rule_y_ids": [...],
    "available_rule_x_ids": [...],
    "available_identities": [...],
    "available_incidents": [...],
    "available_characters": [...],
    "errors": [...],
}
```

说明：

- `default_draft`：首次进入时给 UI 默认值；若校验失败则回传用户上次提交值
- `errors`：仅在校验失败时非空，供 UI 回显
- 其余列表用于表单下拉/校验提示

如果你希望更严格地保持 `WaitForInput` 简洁，也可以只保留：

- `input_type`
- `prompt`
- `callback`

然后默认值继续由 UI 固定使用当前 Phase 5 草稿。  
但这种做法会让 UI 与 engine 的可选项来源分离，后续扩模组时更容易漂移。

---

## 推荐方案

推荐采用 **“轻元数据 + 统一 submit payload”**：

- 引擎通过 `WaitForInput("script_setup")` 发起交互
- UI 不新增主动查询 callback
- UI 提交时继续只调用 `provide_input(...)`
- 引擎在 callback 内完成真正的剧本构建与校验
- 校验失败仍回到同一个 `script_setup` wait

这个方案的优点：

- 满足“非公开信息表属于 `GAME_PREPARE`”
- 满足“UI 层只用 engine 提供的 UI 接口”
- 不需要新增另一套双向接口
- 失败重试路径自然
- 现有 `NewGameController`/`NewGameScreenModel` 基本可复用

---

## 后续落地顺序建议

### Step A：engine 侧最小改动草案确认后实施

- `GamePrepareHandler` 增加 `script_setup` 挂起逻辑
- 在 callback 中接收并处理 payload
- 接通 `GAME_PREPARE` 校验失败后的错误回传

### Step B：UI 接 `script_setup`

- `GameSessionController` 识别 `input_type="script_setup"`
- 主窗口切换到非公开信息表页
- 表单提交后调用 `submit_input(payload)`

### Step C：P6-4 / P6-5

- 进入对局主界面
- 根据 `visible_state` 渲染当前可见信息
- 根据不同 `WaitForInput.input_type` 渲染对应交互
- 游戏结束后切到结算页

---

## 本草案不包含

- 本次不直接修改 `engine/`
- 本次不定义新的 `UICallback` 方法
- 本次不引入 UI 主动查询 engine 的额外接口
- 本次不扩展到完整 UI 视觉实现，只限定最小闭环

---

## 待你确认的 2 个点

1. `WaitForInput("script_setup")` 是否允许附带“可选项元数据 + 错误列表”
2. `provide_input(...)` 的 payload 是否直接沿用当前 `NewGameController.build_payload()` 输出形状

如果这两点确认，我下一步就可以按这份草案去细化实现清单。
