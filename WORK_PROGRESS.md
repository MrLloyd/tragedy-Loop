# 工作进度断点

日期：2026-04-22

## 当前状态

- 已建立三份定位文档：
  - `docs/rules_to_engine_mapping.md`
  - `docs/rules_to_ui_mapping.md`
  - `docs/engine_ui_boundary_mapping.md`
- 已按附录补齐 `First Steps` 与 `Basic Tragedy X` 的规则条目数量：
  - `First Steps`：`规则Y=3`、`规则X=3`
  - `Basic Tragedy X`：`规则Y=5`、`规则X=7`
- 已更新版图布局：
  - 医院左上、神社右上、都市左下、学校右下
- 已同步修正：
  - `data/board.json`
  - `engine/models/board.py`
  - `ui/screens/game_screen.py`
- 新游戏 UI 已修复规则下拉问题：
  - `BTX` 规则 `Y/X` 现在会显示完整已录入列表
  - `规则Y` 可反复切换，不会只生效一次
  - `规则X` 多选框重刷时不再莫名丢状态
- 角色选择下拉已显示初始区域，便于新版图下做视觉核对。
- 对局页已拆为主人公 / 剧作家双栏日志，并接入原子结算后的即时刷新。

## 今日关键验证

- `python3 -m engine.validation`
- `pytest -q tests/test_ui_new_game_controller.py tests/test_ui_main_window_flow.py`
- `pytest -q tests/test_action_card_system.py tests/test_ui_game_screen_model.py`
- 结果：全部通过

## 明天继续建议

- 先手动运行一次 `bash scripts/run_ui_linux.sh`，重点验证：
  - `FS` / `BTX` 规则下拉是否与附录数量一致
  - 版图显示位置是否符合新版图
  - 角色初始区域观感是否还需继续增强
- 若继续补规则能力，优先检查：
  - 已补条目是否都已有完整结构化实现
  - 哪些规则目前仍只有 `description`
- 如继续排错，先按三份映射文档判断属于 `engine`、`ui` 还是边界适配。

## 关键文件

- `data/modules/first_steps.json`：FS 规则条目补齐。
- `data/modules/basic_tragedy_x.json`：BTX 规则条目补齐。
- `data/board.json`：新版图布局。
- `engine/models/board.py`：相邻关系与默认坐标。
- `ui/screens/new_game_screen.py`：规则下拉修复。
- `ui/screens/game_screen.py`：新版图显示与双栏日志。
- `ui/controllers/game_session_controller.py`：即时刷新与详细日志整理。
- `docs/rules_to_engine_mapping.md`：规则到 engine 映射。
- `docs/rules_to_ui_mapping.md`：规则到 UI 映射。
- `docs/engine_ui_boundary_mapping.md`：适配边界映射。
