# 工作进度断点

日期：2026-04-21

## 当前状态

- 已按最新规则文档调整：手牌落点冲突由引擎拒绝，UI 不做复杂预判。
- 剧作家行动改为逐张放置 3 次；剧作家自己的 3 张牌不能放到同一目标。
- 主人公行动保持 3 名主人公各放 1 张；主人公之间不能放到同一目标，但可以和剧作家放到同一目标。
- 剧本校验已覆盖：规则 X 不重复、每天最多 1 个事件、跨天事件当事人不重复。
- 新游戏 UI 已改为下拉选择规则、身份、事件；事件按每天配置，支持“无事件”。
- 对局 UI 已改为四个版图显示，角色状态、标记物、生死状态在版图内展示。
- 对局信息已显示可公开事件信息：事件名称和天数。
- 为规避 Wayland 最大化尺寸协议错误，对局页使用滚动容器承载内容。

## 验证结果

- `python3 -m pytest`
- 结果：`112 passed in 1.08s`

## 明天继续建议

- 先运行 `git status --short` 查看当前未提交改动。
- 如需继续 UI 验证，可运行 `timeout 2s ./scripts/run_ui_linux.sh` 做启动冒烟检查。
- 若要收束版本，建议先区分“本次规则/UI需求相关改动”和“之前阶段遗留改动”，再决定是否提交。

## 关键文件

- `engine/phases/phase_base.py`：行动牌放置流程与落点校验。
- `engine/rules/script_validator.py`：规则 X 与事件日程校验。
- `ui/screens/new_game_screen.py`：新游戏下拉配置界面。
- `ui/controllers/new_game_controller.py`：新游戏表单 payload 组装。
- `ui/screens/game_screen.py`：四版图对局显示与公开事件信息。
- `tests/test_action_card_system.py`：行动牌落点规则测试。
- `tests/test_ui_new_game_controller.py`：新游戏 payload 与校验测试。
- `tests/test_ui_game_screen_model.py`：对局显示模型测试。
- `tests/test_wait_for_input_loop.py`：等待输入流程测试。
