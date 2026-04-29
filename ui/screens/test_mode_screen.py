from __future__ import annotations

from typing import Callable

from engine.display_names import (
    area_name,
    character_name,
    character_option_label,
    display_target_name,
    format_tokens,
    identity_name,
    identity_option_label,
    incident_option_label,
    module_option_label,
    phase_name,
    revealed_incident_message,
    revealed_identity_message,
    rule_option_label,
    token_name,
)
from engine.models.enums import CharacterLifeState, GamePhase
from engine.models.incident import IncidentSchedule
from engine.models.selectors import area_choice_selector, character_choice_selector
from ui.controllers.test_mode_controller import (
    TEST_MODE_DAYS_PER_LOOP,
    TEST_MODE_LOOP_COUNT,
    TestCharacterDraft,
    TestIncidentDraft,
    TestModeController,
)

try:  # pragma: no cover - optional UI dependency
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    QWidget = object  # type: ignore[misc,assignment]
else:
    from ui.controllers.test_mode_game_session import TestModeGameSessionController
    from ui.screens.game_screen import GameScreen
    from ui.widgets import StepChoiceDialog

    class _EmbeddedGameScreen(GameScreen):
        def _show_revealed_identity_popups(self) -> None:
            return

        def _show_revealed_incident_popups(self) -> None:
            return

    class TestModeScreen(QWidget):
        """独立测试模式：自由配置角色并触发事件 / 身份能力。"""

        __test__ = False
        INCIDENT_CHARACTER_TARGET_SLOTS = 3
        INCIDENT_AREA_TARGET_SLOTS = 2
        INCIDENT_TOKEN_TARGET_SLOTS = 2
        ABILITY_TARGET_SLOTS = 4
        RULE_ABILITY_TARGET_SLOTS = 4

        def __init__(
            self,
            controller: TestModeController | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.controller = controller or TestModeController()
            self.phase_session = TestModeGameSessionController(self.controller)
            self._after_apply: Callable[[], None] | None = None
            self._refreshing = False
            self._character_inputs: list[dict[str, QWidget]] = []
            self._script_incident_inputs: list[tuple[QLabel, QComboBox, QComboBox]] = []
            self._shown_reveal_message_count = 0
            self._shown_incident_reveal_message_count = 0

            outer = QVBoxLayout(self)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setMinimumSize(0, 0)
            content = QWidget()
            root = QVBoxLayout(content)
            scroll.setWidget(content)
            outer.addWidget(scroll)

            root.addWidget(QLabel("测试模式 / 调试局"))

            current_box = QGroupBox("当前调试局")
            current_form = QFormLayout(current_box)
            self.module_value = QLabel("-")
            self.rule_y_value = QLabel("-")
            self.rule_x_value = QLabel("-")
            self.character_summary_value = QLabel("-")
            self.failure_report_value = QLabel("-")
            self.failure_state_value = QLabel("-")
            self.failure_reasons_value = QLabel("-")
            self.status_value = QLabel("-")
            self.status_value.setWordWrap(True)
            current_form.addRow("模组", self.module_value)
            current_form.addRow("规则 Y", self.rule_y_value)
            current_form.addRow("规则 X", self.rule_x_value)
            current_form.addRow("角色", self.character_summary_value)
            current_form.addRow("失败报送", self.failure_report_value)
            current_form.addRow("失败状态", self.failure_state_value)
            current_form.addRow("失败原因", self.failure_reasons_value)
            current_form.addRow("状态", self.status_value)
            root.addWidget(current_box)

            basic_box = QGroupBox("基础设置")
            basic_form = QFormLayout(basic_box)
            self.module_input = QComboBox()
            self.loop_input = QSpinBox()
            self.loop_input.setMinimum(1)
            self.loop_input.setMaximum(TEST_MODE_LOOP_COUNT)
            self.day_input = QSpinBox()
            self.day_input.setMinimum(1)
            self.day_input.setMaximum(TEST_MODE_DAYS_PER_LOOP)
            self.phase_input = QComboBox()
            basic_form.addRow("模组", self.module_input)
            basic_form.addRow("轮回", self.loop_input)
            basic_form.addRow("天数", self.day_input)
            basic_form.addRow("阶段", self.phase_input)
            root.addWidget(basic_box)

            rules_box = QGroupBox("规则配置")
            rules_form = QFormLayout(rules_box)
            self.rule_y_input = QComboBox()
            self.rule_x_widget = QWidget()
            self.rule_x_layout = QHBoxLayout(self.rule_x_widget)
            self.rule_x_layout.setContentsMargins(0, 0, 0, 0)
            self.rule_x_inputs: list[QComboBox] = []
            self.apply_rules_button = QPushButton("应用规则并重建对局")
            rules_form.addRow("规则 Y", self.rule_y_input)
            rules_form.addRow("规则 X", self.rule_x_widget)
            rules_form.addRow("", self.apply_rules_button)
            root.addWidget(rules_box)

            phase_box = QGroupBox("阶段推进")
            phase_layout = QVBoxLayout(phase_box)
            phase_actions = QHBoxLayout()
            self.execute_phase_button = QPushButton("执行当前阶段")
            self.advance_phase_button = QPushButton("推进到下一阶段")
            self.run_formal_flow_button = QPushButton("按正式流程推进到下一次输入")
            phase_actions.addWidget(self.execute_phase_button)
            phase_actions.addWidget(self.advance_phase_button)
            phase_actions.addWidget(self.run_formal_flow_button)
            phase_layout.addLayout(phase_actions)
            self.phase_wait_value = QLabel("无")
            self.phase_wait_value.setWordWrap(True)
            phase_layout.addWidget(self.phase_wait_value)
            self.phase_game_screen = _EmbeddedGameScreen(parent=self)
            self.phase_game_screen.setMinimumHeight(520)
            self.phase_game_screen.bind_session(self.phase_session)
            self.phase_game_screen.set_after_submit(self._on_phase_wait_submitted)
            phase_layout.addWidget(self.phase_game_screen)
            root.addWidget(phase_box)
            self.loop_value = self.phase_game_screen.loop_value
            self.day_value = self.phase_game_screen.day_value
            self.phase_value = self.phase_game_screen.phase_value
            self.board_area_texts = self.phase_game_screen.board_area_texts

            roster_box = QGroupBox("角色配置")
            roster_layout = QVBoxLayout(roster_box)
            roster_actions = QHBoxLayout()
            self.add_character_button = QPushButton("增加角色")
            self.remove_character_button = QPushButton("减少角色")
            self.apply_button = QPushButton("应用到调试局")
            roster_actions.addWidget(self.add_character_button)
            roster_actions.addWidget(self.remove_character_button)
            roster_actions.addStretch(1)
            roster_actions.addWidget(self.apply_button)
            roster_layout.addLayout(roster_actions)
            self.characters_grid = QGridLayout()
            roster_layout.addLayout(self.characters_grid)
            root.addWidget(roster_box)

            script_incident_box = QGroupBox("剧本事件配置")
            script_incident_layout = QVBoxLayout(script_incident_box)
            script_incident_hint = QLabel("用于测试依赖公开/非公开事件表的角色能力，如 AI、神灵、侦探。")
            script_incident_hint.setWordWrap(True)
            script_incident_layout.addWidget(script_incident_hint)
            self.script_incidents_grid = QGridLayout()
            script_incident_layout.addLayout(self.script_incidents_grid)
            root.addWidget(script_incident_box)

            board_setup_box = QGroupBox("版图配置")
            board_setup_layout = QVBoxLayout(board_setup_box)
            self.board_setup_grid = QGridLayout()
            board_setup_layout.addLayout(self.board_setup_grid)
            root.addWidget(board_setup_box)

            incident_box = QGroupBox("触发事件")
            incident_form = QFormLayout(incident_box)
            self.incident_input = QComboBox()
            self.perpetrator_input = QComboBox()
            self.trigger_incident_button = QPushButton("触发事件")
            incident_form.addRow("事件", self.incident_input)
            incident_form.addRow("当事人", self.perpetrator_input)
            self.incident_target_hint = QLabel("如事件需要目标，将在触发后逐步弹出选择。")
            self.incident_target_hint.setWordWrap(True)
            incident_form.addRow("目标", self.incident_target_hint)
            incident_form.addRow("", self.trigger_incident_button)
            root.addWidget(incident_box)

            ability_box = QGroupBox("触发身份能力")
            ability_form = QFormLayout(ability_box)
            self.actor_input = QComboBox()
            self.timing_input = QComboBox()
            self.identity_ability_input = QComboBox()
            self.refresh_ability_button = QPushButton("刷新能力列表")
            self.trigger_identity_ability_button = QPushButton("触发身份能力")
            ability_form.addRow("角色", self.actor_input)
            ability_form.addRow("时点过滤", self.timing_input)
            ability_form.addRow("能力", self.identity_ability_input)
            self.identity_target_hint = QLabel("如能力需要目标，将在触发后逐步弹出选择。")
            self.identity_target_hint.setWordWrap(True)
            ability_form.addRow("目标", self.identity_target_hint)
            ability_row = QHBoxLayout()
            ability_row.addWidget(self.refresh_ability_button)
            ability_row.addWidget(self.trigger_identity_ability_button)
            ability_form.addRow("", ability_row)
            root.addWidget(ability_box)

            rule_ability_box = QGroupBox("触发规则能力")
            rule_ability_form = QFormLayout(rule_ability_box)
            self.rule_ability_timing_input = QComboBox()
            self.rule_ability_input = QComboBox()
            self.refresh_rule_ability_button = QPushButton("刷新规则能力列表")
            self.trigger_rule_ability_button = QPushButton("触发规则能力")
            rule_ability_form.addRow("时点过滤", self.rule_ability_timing_input)
            rule_ability_form.addRow("能力", self.rule_ability_input)
            self.rule_target_hint = QLabel("如规则能力需要目标，将在触发后逐步弹出选择。")
            self.rule_target_hint.setWordWrap(True)
            rule_ability_form.addRow("目标", self.rule_target_hint)
            rule_ability_row = QHBoxLayout()
            rule_ability_row.addWidget(self.refresh_rule_ability_button)
            rule_ability_row.addWidget(self.trigger_rule_ability_button)
            rule_ability_form.addRow("", rule_ability_row)
            root.addWidget(rule_ability_box)

            reserved_box = QGroupBox("角色能力 / 特性")
            reserved_layout = QVBoxLayout(reserved_box)
            helper = QLabel(
                "友好能力与可声明特性统一复用正式阶段处理器。"
                "友好能力可直接切到主人公能力阶段执行；其他特性请把上方阶段切到对应时点后执行。"
            )
            helper.setWordWrap(True)
            reserved_layout.addWidget(helper)
            character_actions = QHBoxLayout()
            self.enter_goodwill_phase_button = QPushButton("切到主人公能力阶段并执行")
            self.execute_character_phase_button = QPushButton("执行当前阶段角色特性")
            character_actions.addWidget(self.enter_goodwill_phase_button)
            character_actions.addWidget(self.execute_character_phase_button)
            reserved_layout.addLayout(character_actions)
            root.addWidget(reserved_box)

            snapshot_box = QGroupBox("最近记录")
            snapshot_layout = QVBoxLayout(snapshot_box)
            self.snapshot_text = QTextEdit()
            self.snapshot_text.setReadOnly(True)
            self.snapshot_text.setMinimumHeight(140)
            snapshot_layout.addWidget(self.snapshot_text)
            root.addWidget(snapshot_box)
            self.status_label = self.status_value

            self.module_input.currentIndexChanged.connect(self._on_module_changed)
            self.add_character_button.clicked.connect(self._on_add_character)
            self.remove_character_button.clicked.connect(self._on_remove_character)
            self.apply_button.clicked.connect(self._on_apply)
            self.apply_rules_button.clicked.connect(self._on_apply_rules)
            self.actor_input.currentIndexChanged.connect(self._refresh_identity_abilities)
            self.timing_input.currentIndexChanged.connect(self._refresh_identity_abilities)
            self.identity_ability_input.currentIndexChanged.connect(self._refresh_identity_abilities)
            self.rule_ability_timing_input.currentIndexChanged.connect(self._refresh_rule_abilities)
            self.rule_ability_input.currentIndexChanged.connect(self._refresh_rule_abilities)
            self.execute_phase_button.clicked.connect(self._on_execute_phase)
            self.advance_phase_button.clicked.connect(self._on_advance_phase)
            self.run_formal_flow_button.clicked.connect(self._on_run_formal_flow)
            self.refresh_ability_button.clicked.connect(self._refresh_identity_abilities)
            self.refresh_rule_ability_button.clicked.connect(self._refresh_rule_abilities)
            self.trigger_incident_button.clicked.connect(self._on_trigger_incident)
            self.trigger_identity_ability_button.clicked.connect(self._on_trigger_identity_ability)
            self.trigger_rule_ability_button.clicked.connect(self._on_trigger_rule_ability)
            self.enter_goodwill_phase_button.clicked.connect(self._on_enter_goodwill_phase)
            self.execute_character_phase_button.clicked.connect(self._on_execute_phase)

            self.refresh()

        def set_after_apply(self, callback: Callable[[], None]) -> None:
            self._after_apply = callback

        def read_debug_snapshot(self) -> dict[str, object]:
            return self.controller.read_debug_snapshot()

        def refresh(self) -> None:
            self._refreshing = True
            self.phase_session.refresh_from_test_mode()
            self._set_combo_items(
                self.module_input,
                [(module_id, module_option_label(module_id)) for module_id in self.controller.available_modules],
                self.controller.draft.module_id,
            )
            self.loop_input.setValue(self.controller.draft.current_loop)
            self.day_input.setValue(self.controller.draft.current_day)
            self._set_combo_items(
                self.phase_input,
                [(phase_id, phase_name(phase_id)) for phase_id in self.controller.available_phase_ids],
                self.controller.draft.current_phase,
            )
            self._set_combo_items(
                self.rule_y_input,
                [("", "无规则 Y")] + [
                    (rule_id, rule_option_label(rule_id))
                    for rule_id in self.controller.available_rule_y_ids
                ],
                self.controller.draft.rule_y_id,
            )
            self._ensure_rule_x_inputs()
            self._refresh_rule_x_options()
            self._rebuild_character_rows()
            self._refresh_character_script_inputs()
            self._rebuild_script_incident_rows()
            self._refresh_script_incident_inputs()
            self._rebuild_board_token_rows()
            self._refresh_incident_inputs()
            self._refresh_actor_inputs()
            self._refresh_identity_abilities()
            self._refresh_rule_abilities()
            snapshot = self.controller.snapshot()
            self._render_live_snapshot(snapshot)
            self.snapshot_text.setPlainText(self._format_recent_logs(snapshot))
            self._show_revealed_identity_popups(snapshot)
            self._show_revealed_incident_popups(snapshot)
            self._refreshing = False

        def _on_module_changed(self) -> None:
            if self._refreshing:
                return
            self._commit_inputs(module_override=self._combo_value(self.module_input))
            self.refresh()

        def _on_add_character(self) -> None:
            self._commit_inputs()
            self.controller.add_character()
            self.refresh()

        def _on_remove_character(self) -> None:
            self._commit_inputs()
            self.controller.remove_character()
            self.refresh()

        def _on_apply(self) -> None:
            try:
                self._commit_inputs()
                self.controller.rebuild_session()
            except Exception as exc:
                QMessageBox.warning(self, "应用失败", str(exc))
                return
            self.refresh()
            self._notify_after_apply()

        def _on_apply_rules(self) -> None:
            try:
                self._commit_inputs()
                self.controller.apply_rules_and_rebuild(
                    rule_y_id=self._combo_value(self.rule_y_input),
                    rule_x_ids=[self._combo_value(combo) for combo in self.rule_x_inputs],
                )
            except Exception as exc:
                QMessageBox.warning(self, "应用规则失败", str(exc))
                return
            self.refresh()

        def _on_execute_phase(self) -> None:
            try:
                self._ensure_session()
                self.controller.execute_current_phase()
            except Exception as exc:
                QMessageBox.warning(self, "执行阶段失败", str(exc))
                return
            self.refresh()

        def _on_advance_phase(self) -> None:
            try:
                self._ensure_session()
                self.controller.advance_phase()
            except Exception as exc:
                QMessageBox.warning(self, "推进阶段失败", str(exc))
                return
            self.refresh()

        def _on_run_formal_flow(self) -> None:
            try:
                self._ensure_session()
                self.controller.run_formal_flow_until_wait_or_end()
            except Exception as exc:
                QMessageBox.warning(self, "按正式流程推进失败", str(exc))
                return
            self.refresh()

        def _on_trigger_incident(self) -> None:
            try:
                self._ensure_session()
                target_values = self._prompt_incident_targets(
                    incident_id=self._combo_value(self.incident_input),
                    perpetrator_id=self._combo_value(self.perpetrator_input),
                )
                if target_values is None:
                    return
                self.controller.trigger_incident(
                    incident_id=self._combo_value(self.incident_input),
                    perpetrator_id=self._combo_value(self.perpetrator_input),
                    target_selectors=target_values[0],
                    target_character_ids=target_values[1],
                    target_area_ids=target_values[2],
                    chosen_token_types=target_values[3],
                )
            except Exception as exc:
                QMessageBox.warning(self, "触发事件失败", str(exc))
                return
            self.refresh()

        def _on_trigger_identity_ability(self) -> None:
            try:
                self._ensure_session()
                timing = self._combo_value(self.timing_input) or None
                target_choices = self._prompt_static_target_groups(
                    title=f"触发身份能力：{self.identity_ability_input.currentText()}",
                    option_groups=self.controller.available_identity_ability_target_options(
                        actor_id=self._combo_value(self.actor_input),
                        ability_id=self._combo_value(self.identity_ability_input),
                        timing=timing,
                    ),
                    choice_label="目标",
                )
                if target_choices is None:
                    return
                self.controller.trigger_identity_ability(
                    actor_id=self._combo_value(self.actor_input),
                    ability_id=self._combo_value(self.identity_ability_input),
                    timing=timing,
                    target_choices=target_choices,
                )
            except Exception as exc:
                QMessageBox.warning(self, "触发能力失败", str(exc))
                return
            self.refresh()

        def _on_trigger_rule_ability(self) -> None:
            try:
                self._ensure_session()
                timing = self._combo_value(self.rule_ability_timing_input) or None
                target_choices = self._prompt_static_target_groups(
                    title=f"触发规则能力：{self.rule_ability_input.currentText()}",
                    option_groups=self.controller.available_rule_ability_target_options(
                        ability_id=self._combo_value(self.rule_ability_input),
                        timing=timing,
                    ),
                    choice_label="目标",
                )
                if target_choices is None:
                    return
                self.controller.trigger_rule_ability(
                    ability_id=self._combo_value(self.rule_ability_input),
                    timing=timing,
                    target_choices=target_choices,
                )
            except Exception as exc:
                QMessageBox.warning(self, "触发规则能力失败", str(exc))
                return
            self.refresh()

        def _on_enter_goodwill_phase(self) -> None:
            index = self.phase_input.findData(GamePhase.PROTAGONIST_ABILITY.value)
            if index >= 0:
                self.phase_input.setCurrentIndex(index)
            try:
                self._commit_inputs()
                self.controller.rebuild_session()
                self.controller.execute_current_phase()
            except Exception as exc:
                QMessageBox.warning(self, "进入角色能力阶段失败", str(exc))
                return
            self.refresh()
            self._notify_after_apply()

        def _commit_inputs(self, *, module_override: str | None = None) -> None:
            module_id = module_override or self._combo_value(self.module_input)
            self.controller.set_module(module_id)
            self.controller.set_rules(
                rule_y_id=self._combo_value(self.rule_y_input),
                rule_x_ids=[self._combo_value(combo) for combo in self.rule_x_inputs],
            )
            self.controller.set_runtime(
                current_loop=self.loop_input.value(),
                current_day=self.day_input.value(),
                current_phase=self._combo_value(self.phase_input) or GamePhase.PLAYWRIGHT_ABILITY.value,
            )
            rows: list[TestCharacterDraft] = []
            for row in self._character_inputs:
                tokens = {
                    token_id: int(spin.value())
                    for token_id, spin in row["token_spins"].items()  # type: ignore[index]
                    if int(spin.value()) > 0
                }
                rows.append(
                    TestCharacterDraft(
                        character_id=self._combo_value(row["character"]),  # type: ignore[arg-type]
                        identity_id=self._combo_value(row["identity"]),  # type: ignore[arg-type]
                        initial_area_id=self._combo_value(row["initial_area"]),  # type: ignore[arg-type]
                        territory_area_id=self._combo_value(row["territory_area"]),  # type: ignore[arg-type]
                        entry_loop=row["entry_loop"].value(),  # type: ignore[index]
                        entry_day=row["entry_day"].value(),  # type: ignore[index]
                        hermit_x=row["hermit_x"].value(),  # type: ignore[index]
                        area=self._combo_value(row["area"]),  # type: ignore[arg-type]
                        life_state=self._combo_value(row["life_state"]),  # type: ignore[arg-type]
                        revealed=row["revealed"].isChecked(),  # type: ignore[index]
                        tokens=tokens,
                    )
                )
            self.controller.replace_characters(rows)
            incidents: list[TestIncidentDraft] = []
            for day_label, incident_input, perpetrator_input in self._script_incident_inputs:
                del day_label
                incidents.append(
                    TestIncidentDraft(
                        incident_id=self._combo_value(incident_input),
                        day=len(incidents) + 1,
                        perpetrator_id=self._combo_value(perpetrator_input),
                    )
                )
            self.controller.replace_incidents(incidents)
            board_tokens: dict[str, dict[str, int]] = {}
            for area_id, token_spins in self._board_token_inputs.items():
                board_tokens[area_id] = {
                    token_id: int(spin.value())
                    for token_id, spin in token_spins.items()
                    if int(spin.value()) > 0
                }
            self.controller.replace_board_tokens(board_tokens)

        def _ensure_rule_x_inputs(self) -> None:
            while len(self.rule_x_inputs) > self.controller.rule_x_count:
                combo = self.rule_x_inputs.pop()
                self.rule_x_layout.removeWidget(combo)
                combo.deleteLater()
            while len(self.rule_x_inputs) < self.controller.rule_x_count:
                combo = QComboBox()
                self.rule_x_inputs.append(combo)
                self.rule_x_layout.addWidget(combo)

        def _refresh_rule_x_options(self) -> None:
            current_values = []
            for index, combo in enumerate(self.rule_x_inputs):
                current = self._combo_value(combo)
                if not current and index < len(self.controller.draft.rule_x_ids):
                    current = self.controller.draft.rule_x_ids[index]
                current_values.append(current)
            options = [("", "无规则 X")] + [
                (rule_id, rule_option_label(rule_id))
                for rule_id in self.controller.available_rule_x_ids
            ]
            for index, combo in enumerate(self.rule_x_inputs):
                current = current_values[index] if index < len(current_values) else ""
                self._set_combo_items(combo, options, current)

        def _rebuild_character_rows(self) -> None:
            while self.characters_grid.count():
                item = self.characters_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self._character_inputs.clear()

            headers = [
                "角色", "身份", "剧本初始区", "领地", "登场轮", "登场天", "仙人X", "当前区域", "状态", "公开",
                "不安", "密谋", "友好", "希望", "绝望", "护卫",
            ]
            for column, header in enumerate(headers):
                label = QLabel(header)
                label.setAlignment(Qt.AlignCenter)
                self.characters_grid.addWidget(label, 0, column)

            character_options = [
                (character_id, character_option_label(character_id))
                for character_id in self.controller.available_character_ids
            ]
            identity_options = [
                (identity_id, identity_option_label(identity_id))
                for identity_id in self.controller.available_identity_ids
            ]
            area_options = [(area_id, area_name(area_id)) for area_id in self.controller.available_area_ids()]
            token_columns = [
                ("paranoia", "不安"),
                ("intrigue", "密谋"),
                ("goodwill", "友好"),
                ("hope", "希望"),
                ("despair", "绝望"),
                ("guard", "护卫"),
            ]

            for row_index, item in enumerate(self.controller.draft.characters, start=1):
                character_input = QComboBox()
                identity_input = QComboBox()
                initial_area_input = QComboBox()
                territory_area_input = QComboBox()
                entry_loop_input = QSpinBox()
                entry_loop_input.setMinimum(0)
                entry_loop_input.setMaximum(TEST_MODE_LOOP_COUNT)
                entry_day_input = QSpinBox()
                entry_day_input.setMinimum(0)
                entry_day_input.setMaximum(TEST_MODE_DAYS_PER_LOOP)
                hermit_x_input = QSpinBox()
                hermit_x_input.setMinimum(0)
                hermit_x_input.setMaximum(99)
                area_input = QComboBox()
                life_state_input = QComboBox()
                revealed_input = QCheckBox()
                self._set_combo_items(character_input, character_options, item.character_id)
                self._set_combo_items(identity_input, identity_options, item.identity_id)
                self._set_combo_items(area_input, area_options, item.area)
                self._set_combo_items(
                    life_state_input,
                    [(state.value, state.value) for state in CharacterLifeState],
                    item.life_state,
                )
                entry_loop_input.setValue(item.entry_loop)
                entry_day_input.setValue(item.entry_day)
                hermit_x_input.setValue(item.hermit_x)
                revealed_input.setChecked(item.revealed)
                character_input.currentIndexChanged.connect(self._refresh_character_script_inputs)
                character_input.currentIndexChanged.connect(self._refresh_script_incident_inputs)
                self.characters_grid.addWidget(character_input, row_index, 0)
                self.characters_grid.addWidget(identity_input, row_index, 1)
                self.characters_grid.addWidget(initial_area_input, row_index, 2)
                self.characters_grid.addWidget(territory_area_input, row_index, 3)
                self.characters_grid.addWidget(entry_loop_input, row_index, 4)
                self.characters_grid.addWidget(entry_day_input, row_index, 5)
                self.characters_grid.addWidget(hermit_x_input, row_index, 6)
                self.characters_grid.addWidget(area_input, row_index, 7)
                self.characters_grid.addWidget(life_state_input, row_index, 8)
                self.characters_grid.addWidget(revealed_input, row_index, 9)

                token_spins: dict[str, QSpinBox] = {}
                for column_offset, (token_id, _label) in enumerate(token_columns, start=10):
                    spin = QSpinBox()
                    spin.setMinimum(0)
                    spin.setMaximum(99)
                    spin.setValue(int(item.tokens.get(token_id, 0)))
                    self.characters_grid.addWidget(spin, row_index, column_offset)
                    token_spins[token_id] = spin

                self._character_inputs.append(
                    {
                        "character": character_input,
                        "identity": identity_input,
                        "initial_area": initial_area_input,
                        "territory_area": territory_area_input,
                        "entry_loop": entry_loop_input,
                        "entry_day": entry_day_input,
                        "hermit_x": hermit_x_input,
                        "area": area_input,
                        "life_state": life_state_input,
                        "revealed": revealed_input,
                        "token_spins": token_spins,
                    }
                )

        def _refresh_character_script_inputs(self) -> None:
            for index, row in enumerate(self._character_inputs):
                character_id = self._combo_value(row["character"])  # type: ignore[arg-type]
                draft_item = self.controller.draft.characters[index]

                current_initial_area = self._combo_value(row["initial_area"])  # type: ignore[arg-type]
                if not current_initial_area:
                    current_initial_area = draft_item.initial_area_id
                initial_area_options, initial_area_enabled = self.controller.character_initial_area_options(character_id)
                self._set_combo_items(row["initial_area"], initial_area_options, current_initial_area)  # type: ignore[arg-type]
                row["initial_area"].setEnabled(initial_area_enabled)  # type: ignore[index]

                current_territory_area = self._combo_value(row["territory_area"])  # type: ignore[arg-type]
                if not current_territory_area:
                    current_territory_area = draft_item.territory_area_id
                territory_options, territory_enabled = self.controller.character_territory_area_options(character_id)
                self._set_combo_items(row["territory_area"], territory_options, current_territory_area)  # type: ignore[arg-type]
                row["territory_area"].setEnabled(territory_enabled)  # type: ignore[index]

                entry_loop_enabled = self.controller.character_can_set_entry_loop(character_id)
                current_entry_loop = row["entry_loop"].value() if row["entry_loop"].isEnabled() else draft_item.entry_loop  # type: ignore[index]
                row["entry_loop"].blockSignals(True)  # type: ignore[index]
                row["entry_loop"].setValue(current_entry_loop if entry_loop_enabled else 0)  # type: ignore[index]
                row["entry_loop"].setEnabled(entry_loop_enabled)  # type: ignore[index]
                row["entry_loop"].blockSignals(False)  # type: ignore[index]

                entry_day_enabled = self.controller.character_can_set_entry_day(character_id)
                current_entry_day = row["entry_day"].value() if row["entry_day"].isEnabled() else draft_item.entry_day  # type: ignore[index]
                row["entry_day"].blockSignals(True)  # type: ignore[index]
                row["entry_day"].setValue(current_entry_day if entry_day_enabled else 0)  # type: ignore[index]
                row["entry_day"].setEnabled(entry_day_enabled)  # type: ignore[index]
                row["entry_day"].blockSignals(False)  # type: ignore[index]

                hermit_x_enabled = self.controller.character_can_set_hermit_x(character_id)
                hermit_spec = self.controller.character_hermit_x_spec(character_id)
                current_hermit_x = row["hermit_x"].value() if row["hermit_x"].isEnabled() else draft_item.hermit_x  # type: ignore[index]
                hermit_value = current_hermit_x if hermit_x_enabled else 0
                row["hermit_x"].blockSignals(True)  # type: ignore[index]
                row["hermit_x"].setMinimum(int(hermit_spec.get("min", 0)))  # type: ignore[index]
                row["hermit_x"].setValue(hermit_value)  # type: ignore[index]
                row["hermit_x"].setEnabled(hermit_x_enabled)  # type: ignore[index]
                row["hermit_x"].blockSignals(False)  # type: ignore[index]

        def _rebuild_script_incident_rows(self) -> None:
            while self.script_incidents_grid.count():
                item = self.script_incidents_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self._script_incident_inputs.clear()

            self.script_incidents_grid.addWidget(QLabel("天数"), 0, 0)
            self.script_incidents_grid.addWidget(QLabel("事件"), 0, 1)
            self.script_incidents_grid.addWidget(QLabel("当事人"), 0, 2)
            for index, item in enumerate(self.controller.draft.incidents, start=1):
                day_label = QLabel(f"第 {item.day} 天")
                incident_input = QComboBox()
                perpetrator_input = QComboBox()
                self.script_incidents_grid.addWidget(day_label, index, 0)
                self.script_incidents_grid.addWidget(incident_input, index, 1)
                self.script_incidents_grid.addWidget(perpetrator_input, index, 2)
                self._script_incident_inputs.append((day_label, incident_input, perpetrator_input))

        def _refresh_script_incident_inputs(self) -> None:
            incident_options = [("", "无事件")] + [
                (incident_id, incident_option_label(incident_id))
                for incident_id in self.controller.available_incident_ids
            ]
            selected_characters = self._selected_character_ids_from_inputs()
            if not selected_characters:
                selected_characters = self.controller.available_character_ids
            character_options = [("", "未选择")] + [
                (character_id, character_option_label(character_id))
                for character_id in selected_characters
            ]
            for index, (_day_label, incident_input, perpetrator_input) in enumerate(self._script_incident_inputs):
                draft_item = self.controller.draft.incidents[index]
                current_incident = self._combo_value(incident_input) or draft_item.incident_id
                current_perpetrator = self._combo_value(perpetrator_input) or draft_item.perpetrator_id
                self._set_combo_items(incident_input, incident_options, current_incident)
                self._set_combo_items(perpetrator_input, character_options, current_perpetrator)

        def _selected_character_ids_from_inputs(self) -> list[str]:
            selected: list[str] = []
            for row in self._character_inputs:
                character_id = self._combo_value(row["character"])  # type: ignore[arg-type]
                if character_id and character_id not in selected:
                    selected.append(character_id)
            return selected

        def _rebuild_board_token_rows(self) -> None:
            while self.board_setup_grid.count():
                item = self.board_setup_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            token_columns = [
                ("intrigue", "密谋"),
            ]
            self._board_token_inputs: dict[str, dict[str, QSpinBox]] = {}

            self.board_setup_grid.addWidget(QLabel("版图"), 0, 0)
            for column, (_token_id, label) in enumerate(token_columns, start=1):
                header = QLabel(label)
                header.setAlignment(Qt.AlignCenter)
                self.board_setup_grid.addWidget(header, 0, column)

            board_tokens = self.controller.draft.board_tokens
            for row_index, area_id in enumerate(self.controller.available_area_ids(), start=1):
                self.board_setup_grid.addWidget(QLabel(area_name(area_id)), row_index, 0)
                token_spins: dict[str, QSpinBox] = {}
                area_tokens = board_tokens.get(area_id, {})
                for column, (token_id, _label) in enumerate(token_columns, start=1):
                    spin = QSpinBox()
                    spin.setMinimum(0)
                    spin.setMaximum(3)
                    spin.setValue(int(area_tokens.get(token_id, 0)))
                    self.board_setup_grid.addWidget(spin, row_index, column)
                    token_spins[token_id] = spin
                self._board_token_inputs[area_id] = token_spins

        def _refresh_incident_inputs(self) -> None:
            self._set_combo_items(
                self.incident_input,
                [(incident_id, incident_option_label(incident_id)) for incident_id in self.controller.available_incident_ids],
                self._combo_value(self.incident_input),
            )
            character_options = [
                (character_id, character_option_label(character_id))
                for character_id in self.controller.available_perpetrator_ids()
            ]
            self._set_combo_items(
                self.perpetrator_input,
                character_options,
                self._combo_value(self.perpetrator_input),
            )

        def _refresh_actor_inputs(self) -> None:
            character_options = [
                (character_id, character_option_label(character_id))
                for character_id in self.controller.available_perpetrator_ids()
            ]
            self._set_combo_items(
                self.actor_input,
                character_options,
                self._combo_value(self.actor_input),
            )
            timing_options = self._ability_timing_options()
            self._set_combo_items(
                self.timing_input,
                timing_options,
                self._combo_value(self.timing_input),
            )
            self._set_combo_items(
                self.rule_ability_timing_input,
                timing_options,
                self._combo_value(self.rule_ability_timing_input),
            )

        @staticmethod
        def _ability_timing_options() -> list[tuple[str, str]]:
            from engine.models.enums import AbilityTiming

            return [("", "全部时点")] + [
                (timing.value, timing.value)
                for timing in AbilityTiming
            ]

        def _refresh_identity_abilities(self) -> None:
            actor_id = self._combo_value(self.actor_input)
            timing = self._combo_value(self.timing_input) or None
            options = self.controller.available_identity_abilities(actor_id=actor_id or None, timing=timing)
            self._set_combo_items(self.identity_ability_input, options, self._combo_value(self.identity_ability_input))

        def _refresh_rule_abilities(self) -> None:
            timing = self._combo_value(self.rule_ability_timing_input) or None
            options = self.controller.available_rule_abilities(timing=timing)
            self._set_combo_items(self.rule_ability_input, options, self._combo_value(self.rule_ability_input))

        def _render_live_snapshot(self, snapshot: dict[str, object]) -> None:
            self.module_value.setText(module_option_label(self.controller.draft.module_id))
            rule_y_id = str(snapshot.get("rule_y_id", "") or "")
            rule_x_ids = snapshot.get("rule_x_ids", [])
            self.rule_y_value.setText(rule_option_label(rule_y_id) if rule_y_id else "无")
            if isinstance(rule_x_ids, list) and any(str(item) for item in rule_x_ids):
                self.rule_x_value.setText(
                    "、".join(
                        rule_option_label(str(item))
                        for item in rule_x_ids
                        if str(item)
                    )
                )
            else:
                self.rule_x_value.setText("无")
            characters = snapshot.get("characters", {})
            total_count = 0
            alive_count = 0
            if isinstance(characters, dict):
                total_count = len(characters)
                alive_count = sum(
                    1
                    for item in characters.values()
                    if isinstance(item, dict) and str(item.get("life_state", "")) == CharacterLifeState.ALIVE.value
                )
            self.character_summary_value.setText(f"{alive_count}/{total_count} 存活")
            failure_flags = snapshot.get("failure_flags", [])
            protagonist_dead = bool(snapshot.get("protagonist_dead", False))
            failure_reasons: list[str] = []
            if protagonist_dead:
                failure_reasons.append("protagonist_death")
            if isinstance(failure_flags, list):
                seen_reasons = set(failure_reasons)
                for item in failure_flags:
                    reason = str(item)
                    if not reason or reason in seen_reasons:
                        continue
                    failure_reasons.append(reason)
                    seen_reasons.add(reason)
            failure_reached = bool(failure_reasons)
            if protagonist_dead:
                self.failure_report_value.setText("主人公死亡")
            elif failure_reached:
                self.failure_report_value.setText("主人公失败")
            else:
                self.failure_report_value.setText("无")
            if failure_reasons:
                self.failure_reasons_value.setText("、".join(failure_reasons))
            else:
                self.failure_reasons_value.setText("无")
            self.failure_state_value.setText("已触发" if failure_reached else "未触发")
            self.status_value.setText(self.controller.status_message or "调试局已就绪")
            pending_wait = snapshot.get("pending_wait")
            if isinstance(pending_wait, dict):
                self.phase_wait_value.setText(
                    f"{pending_wait.get('input_type', '?')}｜{pending_wait.get('player', '?')}｜{pending_wait.get('prompt', '')}"
                )
            else:
                self.phase_wait_value.setText("无")

        def _render_board(self, snapshot: dict[str, object]) -> None:
            board_tokens = snapshot.get("board_tokens", {})
            characters = snapshot.get("characters", {})
            if not isinstance(board_tokens, dict):
                board_tokens = {}
            if not isinstance(characters, dict):
                characters = {}

            for area_id, text_widget in self.board_area_texts.items():
                lines = [
                    f"版图标记物：{format_tokens(dict(board_tokens.get(area_id, {})) if isinstance(board_tokens.get(area_id, {}), dict) else {})}",
                    "角色：",
                ]
                area_characters: list[tuple[str, dict[str, object]]] = []
                for character_id, item in characters.items():
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("area", "")) != area_id:
                        continue
                    area_characters.append((str(character_id), item))
                if not area_characters:
                    lines.append("- 无")
                else:
                    for character_id, item in sorted(area_characters):
                        lines.append(self._format_character_line(character_id, item))
                text_widget.setPlainText("\n".join(lines))

        def _format_recent_logs(self, snapshot: dict[str, object]) -> str:
            incident_lines = ["事件结果："]
            incident_results = snapshot.get("incident_results", [])
            if isinstance(incident_results, list) and incident_results:
                for item in incident_results[-5:]:
                    if not isinstance(item, dict):
                        continue
                    status = "有现象" if item.get("has_phenomenon") else "无现象"
                    occurred = "发生" if item.get("occurred") else "未发生"
                    incident_lines.append(
                        f"- 第 {item.get('day', '?')} 天｜{incident_option_label(str(item.get('incident_id', '?')))}｜{occurred}｜{status}"
                    )
            else:
                incident_lines.append("- 暂无")

            debug_lines = ["", "调试日志："]
            debug_log = snapshot.get("debug_log", [])
            if isinstance(debug_log, list) and debug_log:
                for item in debug_log[-5:]:
                    debug_lines.append(f"- {self._format_debug_item(item)}")
            else:
                debug_lines.append("- 暂无")
            return "\n".join(incident_lines + debug_lines)

        def _show_revealed_identity_popups(self, snapshot: dict[str, object]) -> None:
            messages = self._extract_revealed_identity_messages(snapshot)
            if self._shown_reveal_message_count > len(messages):
                self._shown_reveal_message_count = 0
            if self._shown_reveal_message_count >= len(messages):
                return
            for message in messages[self._shown_reveal_message_count:]:
                QMessageBox.information(self, "身份公开", message)
            self._shown_reveal_message_count = len(messages)

        def _show_revealed_incident_popups(self, snapshot: dict[str, object]) -> None:
            messages = self._extract_revealed_incident_messages(snapshot)
            if self._shown_incident_reveal_message_count > len(messages):
                self._shown_incident_reveal_message_count = 0
            if self._shown_incident_reveal_message_count >= len(messages):
                return
            for message in messages[self._shown_incident_reveal_message_count:]:
                QMessageBox.information(self, "当事人公开", message)
            self._shown_incident_reveal_message_count = len(messages)

        @staticmethod
        def _extract_revealed_identity_messages(snapshot: dict[str, object]) -> list[str]:
            event_log = snapshot.get("event_log", [])
            if not isinstance(event_log, list):
                return []
            messages: list[str] = []
            for item in event_log:
                if not isinstance(item, dict):
                    continue
                if str(item.get("event_type", "")) != "IDENTITY_REVEALED":
                    continue
                data = item.get("data", {})
                if not isinstance(data, dict):
                    continue
                character_id = str(data.get("character_id", "") or "")
                identity_id = str(data.get("identity_id", "") or "")
                if not character_id or not identity_id:
                    continue
                messages.append(revealed_identity_message(character_id, identity_id))
            return messages

        @staticmethod
        def _extract_revealed_incident_messages(snapshot: dict[str, object]) -> list[str]:
            event_log = snapshot.get("event_log", [])
            if not isinstance(event_log, list):
                return []
            messages: list[str] = []
            for item in event_log:
                if not isinstance(item, dict):
                    continue
                if str(item.get("event_type", "")) != "INCIDENT_REVEALED":
                    continue
                data = item.get("data", {})
                if not isinstance(data, dict):
                    continue
                incident_id = str(data.get("incident_id", "") or "")
                perpetrator_id = str(data.get("perpetrator_id", "") or "")
                if not incident_id or not perpetrator_id:
                    continue
                messages.append(revealed_incident_message(incident_id, perpetrator_id))
            return messages

        @staticmethod
        def _format_character_line(character_id: str, item: dict[str, object]) -> str:
            display_name = str(item.get("name") or "").strip()
            if not display_name:
                display_name = character_name(character_id)
            if display_name and display_name != character_id:
                head = f"{display_name}（{character_id}）"
            else:
                head = character_id
            status = []
            life_state = str(item.get("life_state", CharacterLifeState.ALIVE.value))
            if life_state == CharacterLifeState.ALIVE.value:
                status.append("存活")
            elif life_state == CharacterLifeState.DEAD.value:
                status.append("死亡")
            elif life_state == CharacterLifeState.REMOVED.value:
                status.append("移除")
            else:
                status.append(life_state)
            if bool(item.get("revealed", False)):
                status.append("已公开")
            return (
                f"- {head}｜{'｜'.join(status)}｜身份：{identity_name(str(item.get('identity_id', '?')))}"
                f"｜标记物：{format_tokens(dict(item.get('tokens', {})) if isinstance(item.get('tokens', {}), dict) else {})}"
            )

        @staticmethod
        def _format_debug_item(item: object) -> str:
            if isinstance(item, dict):
                action = str(item.get("action", "debug"))
                pairs = [
                    f"{key}={value}"
                    for key, value in item.items()
                    if key != "action"
                ]
                if pairs:
                    return f"{action}｜" + "｜".join(pairs)
                return action
            return str(item)

        @staticmethod
        def _set_combo_items(combo: QComboBox, options: list[tuple[str, str]], current_value: str) -> None:
            combo.blockSignals(True)
            combo.clear()
            for value, label in options:
                combo.addItem(label, value)
            index = combo.findData(current_value)
            if index < 0 and combo.count() > 0:
                index = 0
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)

        @staticmethod
        def _combo_value(combo: QComboBox) -> str:
            value = combo.currentData()
            return str(value) if value is not None else combo.currentText().strip()

        def _prompt_incident_targets(
            self,
            *,
            incident_id: str,
            perpetrator_id: str,
        ) -> tuple[list[dict[str, str]], list[str], list[str], list[str]] | None:
            if self.controller.session is None or not incident_id or not perpetrator_id:
                return ([], [], [], [])
            incident_def = self.controller.session.state.incident_defs.get(incident_id)
            if incident_def is None:
                return ([], [], [], [])

            history: list[tuple[str, str]] = []
            while True:
                schedule = IncidentSchedule(
                    incident_id=incident_id,
                    day=self.controller.session.state.current_day,
                    perpetrator_id=perpetrator_id,
                    target_selectors=[
                        character_choice_selector(value) if kind == "character" else area_choice_selector(value)
                        for kind, value in history
                        if kind in {"character", "area"}
                    ],
                    target_character_ids=[value for kind, value in history if kind == "character"],
                    target_area_ids=[value for kind, value in history if kind == "area"],
                    chosen_token_types=[value for kind, value in history if kind == "token"],
                )
                next_choice = self.controller.session.incident_resolver.next_runtime_choice(
                    self.controller.session.state,
                    schedule,
                    incident_def,
                )
                if next_choice is None:
                    return (
                        [
                            character_choice_selector(value) if kind == "character" else area_choice_selector(value)
                            for kind, value in history
                            if kind in {"character", "area"}
                        ],
                        [value for kind, value in history if kind == "character"],
                        [value for kind, value in history if kind == "area"],
                        [value for kind, value in history if kind == "token"],
                    )

                choice_type, candidates = next_choice
                dialog = StepChoiceDialog(
                    title=f"触发事件：{incident_option_label(incident_id)}",
                    prompt=self._incident_choice_prompt(choice_type, len(history) + 1),
                    options=[
                        (candidate_id, self._target_dialog_label(choice_type, candidate_id))
                        for candidate_id in candidates
                    ],
                    summary_lines=self._incident_history_lines(history),
                    allow_back=bool(history),
                    parent=self,
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    if dialog.back_requested and history:
                        history.pop()
                        continue
                    return None
                history.append((choice_type, dialog.selected_value()))

        def _prompt_static_target_groups(
            self,
            *,
            title: str,
            option_groups: list[list[tuple[str, str]]],
            choice_label: str,
        ) -> list[str] | None:
            if not option_groups:
                return []
            selections: list[str] = []
            while len(selections) < len(option_groups):
                index = len(selections)
                dialog = StepChoiceDialog(
                    title=title,
                    prompt=f"请选择第 {index + 1} 个{choice_label}",
                    options=option_groups[index],
                    summary_lines=self._static_history_lines(option_groups, selections, choice_label),
                    allow_back=bool(selections),
                    parent=self,
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    if dialog.back_requested and selections:
                        selections.pop()
                        continue
                    return None
                selections.append(dialog.selected_value())
            return selections

        def _static_history_lines(
            self,
            option_groups: list[list[tuple[str, str]]],
            selections: list[str],
            choice_label: str,
        ) -> list[str]:
            lines: list[str] = []
            for index, value in enumerate(selections):
                label = dict(option_groups[index]).get(value, value)
                lines.append(f"第 {index + 1} 个{choice_label}：{label}")
            return lines

        def _incident_history_lines(self, history: list[tuple[str, str]]) -> list[str]:
            labels = {
                "character": "角色目标",
                "area": "版图目标",
                "token": "指示物",
            }
            return [
                f"第 {index + 1} 步｜{labels.get(choice_type, choice_type)}：{self._target_dialog_label(choice_type, value)}"
                for index, (choice_type, value) in enumerate(history)
            ]

        @staticmethod
        def _incident_choice_prompt(choice_type: str, step_number: int) -> str:
            mapping = {
                "character": "请选择角色目标",
                "area": "请选择版图目标",
                "token": "请选择指示物类型",
            }
            return f"第 {step_number} 步：{mapping.get(choice_type, '请选择目标')}"

        @staticmethod
        def _target_dialog_label(choice_type: str, value: str) -> str:
            if choice_type == "token":
                return token_name(value)
            return display_target_name(value) if choice_type == "area" else character_option_label(value)

        def _notify_after_apply(self) -> None:
            if self._after_apply is not None:
                self._after_apply()

        def _on_phase_wait_submitted(self) -> None:
            self.refresh()

        def _ensure_session(self) -> None:
            if self.controller.session is None:
                self.controller.rebuild_session()
