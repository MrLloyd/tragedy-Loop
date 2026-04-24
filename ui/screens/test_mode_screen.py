from __future__ import annotations

from typing import Callable

from engine.display_names import (
    area_name,
    character_name,
    character_option_label,
    format_tokens,
    identity_name,
    identity_option_label,
    incident_option_label,
    module_option_label,
    phase_name,
    revealed_identity_message,
    rule_option_label,
    token_name,
)
from engine.models.enums import GamePhase
from ui.controllers.test_mode_controller import (
    TEST_MODE_DAYS_PER_LOOP,
    TEST_MODE_LOOP_COUNT,
    TestCharacterDraft,
    TestModeController,
)

try:  # pragma: no cover - optional UI dependency
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
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
    class TestModeScreen(QWidget):
        """独立测试模式：自由配置角色并触发事件 / 身份能力。"""

        __test__ = False
        INCIDENT_CHARACTER_TARGET_SLOTS = 3
        INCIDENT_AREA_TARGET_SLOTS = 2
        INCIDENT_TOKEN_TARGET_SLOTS = 2
        ABILITY_TARGET_SLOTS = 4

        def __init__(
            self,
            controller: TestModeController | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.controller = controller or TestModeController()
            self._after_apply: Callable[[], None] | None = None
            self._refreshing = False
            self._character_inputs: list[dict[str, QWidget]] = []
            self._shown_reveal_message_count = 0

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
            self.loop_value = QLabel("-")
            self.day_value = QLabel("-")
            self.phase_value = QLabel("-")
            self.character_summary_value = QLabel("-")
            self.protagonist_dead_value = QLabel("-")
            self.failure_state_value = QLabel("-")
            self.failure_flags_value = QLabel("-")
            self.status_value = QLabel("-")
            self.status_value.setWordWrap(True)
            current_form.addRow("模组", self.module_value)
            current_form.addRow("规则 Y", self.rule_y_value)
            current_form.addRow("规则 X", self.rule_x_value)
            current_form.addRow("轮回", self.loop_value)
            current_form.addRow("天数", self.day_value)
            current_form.addRow("阶段", self.phase_value)
            current_form.addRow("角色", self.character_summary_value)
            current_form.addRow("主人公死亡", self.protagonist_dead_value)
            current_form.addRow("失败状态", self.failure_state_value)
            current_form.addRow("失败标记", self.failure_flags_value)
            current_form.addRow("状态", self.status_value)
            root.addWidget(current_box)

            board_box = QGroupBox("当前版图")
            board_layout = QGridLayout(board_box)
            self.board_area_texts: dict[str, QTextEdit] = {}
            for area_id, row, col in (
                ("hospital", 0, 0),
                ("shrine", 0, 1),
                ("city", 1, 0),
                ("school", 1, 1),
            ):
                area_box = QGroupBox(area_name(area_id))
                area_layout = QVBoxLayout(area_box)
                area_text = QTextEdit()
                area_text.setReadOnly(True)
                area_text.setMinimumHeight(110)
                area_text.setMaximumHeight(150)
                area_layout.addWidget(area_text)
                board_layout.addWidget(area_box, row, col)
                self.board_area_texts[area_id] = area_text
            root.addWidget(board_box)

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
            phase_actions.addWidget(self.execute_phase_button)
            phase_actions.addWidget(self.advance_phase_button)
            phase_layout.addLayout(phase_actions)
            self.phase_wait_value = QLabel("无")
            self.phase_wait_value.setWordWrap(True)
            phase_layout.addWidget(self.phase_wait_value)
            root.addWidget(phase_box)

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

            incident_box = QGroupBox("触发事件")
            incident_form = QFormLayout(incident_box)
            self.incident_input = QComboBox()
            self.perpetrator_input = QComboBox()
            self.incident_target_character_inputs = self._build_target_combos(self.INCIDENT_CHARACTER_TARGET_SLOTS)
            self.incident_target_area_inputs = self._build_target_combos(self.INCIDENT_AREA_TARGET_SLOTS)
            self.incident_target_token_inputs = self._build_target_combos(self.INCIDENT_TOKEN_TARGET_SLOTS)
            self.trigger_incident_button = QPushButton("触发事件")
            incident_form.addRow("事件", self.incident_input)
            incident_form.addRow("当事人", self.perpetrator_input)
            incident_form.addRow("角色目标", self._build_target_combo_row(self.incident_target_character_inputs))
            incident_form.addRow("版图目标", self._build_target_combo_row(self.incident_target_area_inputs))
            incident_form.addRow("指示物", self._build_target_combo_row(self.incident_target_token_inputs))
            incident_form.addRow("", self.trigger_incident_button)
            root.addWidget(incident_box)

            ability_box = QGroupBox("触发身份能力")
            ability_form = QFormLayout(ability_box)
            self.actor_input = QComboBox()
            self.timing_input = QComboBox()
            self.identity_ability_input = QComboBox()
            self.ability_target_inputs = self._build_target_combos(self.ABILITY_TARGET_SLOTS)
            self.refresh_ability_button = QPushButton("刷新能力列表")
            self.trigger_identity_ability_button = QPushButton("触发身份能力")
            ability_form.addRow("角色", self.actor_input)
            ability_form.addRow("时点过滤", self.timing_input)
            ability_form.addRow("能力", self.identity_ability_input)
            ability_form.addRow("目标选择", self._build_target_combo_row(self.ability_target_inputs))
            ability_row = QHBoxLayout()
            ability_row.addWidget(self.refresh_ability_button)
            ability_row.addWidget(self.trigger_identity_ability_button)
            ability_form.addRow("", ability_row)
            root.addWidget(ability_box)

            reserved_box = QGroupBox("角色能力（预留）")
            reserved_layout = QVBoxLayout(reserved_box)
            self.trigger_character_ability_button = QPushButton("角色能力入口（预留）")
            self.trigger_character_ability_button.setEnabled(False)
            reserved_layout.addWidget(self.trigger_character_ability_button)
            reserved_layout.addWidget(QLabel("后续接入角色能力专项测试。"))
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
            self.identity_ability_input.currentIndexChanged.connect(self._refresh_identity_target_inputs)
            self.execute_phase_button.clicked.connect(self._on_execute_phase)
            self.advance_phase_button.clicked.connect(self._on_advance_phase)
            self.refresh_ability_button.clicked.connect(self._refresh_identity_abilities)
            self.trigger_incident_button.clicked.connect(self._on_trigger_incident)
            self.trigger_identity_ability_button.clicked.connect(self._on_trigger_identity_ability)

            self.refresh()

        def set_after_apply(self, callback: Callable[[], None]) -> None:
            self._after_apply = callback

        def read_debug_snapshot(self) -> dict[str, object]:
            return self.controller.read_debug_snapshot()

        def refresh(self) -> None:
            self._refreshing = True
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
            self._refresh_incident_inputs()
            self._refresh_actor_inputs()
            self._refresh_identity_abilities()
            snapshot = self.controller.snapshot()
            self._render_live_snapshot(snapshot)
            self.snapshot_text.setPlainText(self._format_recent_logs(snapshot))
            self._show_revealed_identity_popups(snapshot)
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

        def _on_trigger_incident(self) -> None:
            try:
                self._ensure_session()
                self.controller.trigger_incident(
                    incident_id=self._combo_value(self.incident_input),
                    perpetrator_id=self._combo_value(self.perpetrator_input),
                    target_character_ids=self._selected_combo_values(self.incident_target_character_inputs),
                    target_area_ids=self._selected_combo_values(self.incident_target_area_inputs),
                    chosen_token_types=self._selected_combo_values(self.incident_target_token_inputs),
                )
            except Exception as exc:
                QMessageBox.warning(self, "触发事件失败", str(exc))
                return
            self.refresh()

        def _on_trigger_identity_ability(self) -> None:
            try:
                self._ensure_session()
                timing = self._combo_value(self.timing_input) or None
                self.controller.trigger_identity_ability(
                    actor_id=self._combo_value(self.actor_input),
                    ability_id=self._combo_value(self.identity_ability_input),
                    timing=timing,
                    target_choices=self._selected_combo_values(self.ability_target_inputs),
                )
            except Exception as exc:
                QMessageBox.warning(self, "触发能力失败", str(exc))
                return
            self.refresh()

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
                        area=self._combo_value(row["area"]),  # type: ignore[arg-type]
                        is_alive=row["alive"].isChecked(),  # type: ignore[index]
                        is_removed=row["removed"].isChecked(),  # type: ignore[index]
                        revealed=row["revealed"].isChecked(),  # type: ignore[index]
                        tokens=tokens,
                    )
                )
            self.controller.replace_characters(rows)

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
                "角色", "身份", "区域", "存活", "移除", "公开",
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
                area_input = QComboBox()
                alive_input = QCheckBox()
                removed_input = QCheckBox()
                revealed_input = QCheckBox()
                self._set_combo_items(character_input, character_options, item.character_id)
                self._set_combo_items(identity_input, identity_options, item.identity_id)
                self._set_combo_items(area_input, area_options, item.area)
                alive_input.setChecked(item.is_alive)
                removed_input.setChecked(item.is_removed)
                revealed_input.setChecked(item.revealed)
                self.characters_grid.addWidget(character_input, row_index, 0)
                self.characters_grid.addWidget(identity_input, row_index, 1)
                self.characters_grid.addWidget(area_input, row_index, 2)
                self.characters_grid.addWidget(alive_input, row_index, 3)
                self.characters_grid.addWidget(removed_input, row_index, 4)
                self.characters_grid.addWidget(revealed_input, row_index, 5)

                token_spins: dict[str, QSpinBox] = {}
                for column_offset, (token_id, _label) in enumerate(token_columns, start=6):
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
                        "area": area_input,
                        "alive": alive_input,
                        "removed": removed_input,
                        "revealed": revealed_input,
                        "token_spins": token_spins,
                    }
                )

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
            self._set_optional_target_items(self.incident_target_character_inputs, character_options)
            self._set_optional_target_items(
                self.incident_target_area_inputs,
                [(area_id, area_name(area_id)) for area_id in self.controller.available_area_ids()],
            )
            self._set_optional_target_items(
                self.incident_target_token_inputs,
                [(token_id, token_name(token_id)) for token_id in self.controller.available_token_ids()],
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
            timing_options = [("", "全部时点")]
            timing_options.extend(
                (phase.value, phase.value)
                for phase in []
            )
            from engine.models.enums import AbilityTiming

            timing_options = [("", "全部时点")] + [
                (timing.value, timing.value)
                for timing in AbilityTiming
            ]
            self._set_combo_items(
                self.timing_input,
                timing_options,
                self._combo_value(self.timing_input),
            )

        def _refresh_identity_abilities(self) -> None:
            actor_id = self._combo_value(self.actor_input)
            timing = self._combo_value(self.timing_input) or None
            options = self.controller.available_identity_abilities(actor_id=actor_id or None, timing=timing)
            self._set_combo_items(self.identity_ability_input, options, self._combo_value(self.identity_ability_input))
            self._refresh_identity_target_inputs()

        def _refresh_identity_target_inputs(self) -> None:
            actor_id = self._combo_value(self.actor_input)
            ability_id = self._combo_value(self.identity_ability_input)
            timing = self._combo_value(self.timing_input) or None
            option_groups = self.controller.available_identity_ability_target_options(
                actor_id=actor_id,
                ability_id=ability_id,
                timing=timing,
            ) if actor_id and ability_id else []
            for index, combo in enumerate(self.ability_target_inputs):
                current_value = self._combo_value(combo)
                if index < len(option_groups):
                    self._set_combo_items(combo, [("", "—")] + option_groups[index], current_value)
                    combo.setEnabled(True)
                else:
                    self._set_combo_items(combo, [("", "—")], "")
                    combo.setEnabled(False)

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
            self.loop_value.setText(f"第 {int(snapshot.get('current_loop', self.controller.draft.current_loop))} 轮")
            self.day_value.setText(f"第 {int(snapshot.get('current_day', self.controller.draft.current_day))} 天")
            self.phase_value.setText(
                phase_name(str(snapshot.get("current_phase", self.controller.draft.current_phase)))
            )
            characters = snapshot.get("characters", {})
            total_count = 0
            alive_count = 0
            if isinstance(characters, dict):
                total_count = len(characters)
                alive_count = sum(
                    1
                    for item in characters.values()
                    if isinstance(item, dict) and bool(item.get("is_alive", False))
                )
            self.character_summary_value.setText(f"{alive_count}/{total_count} 存活")
            failure_flags = snapshot.get("failure_flags", [])
            protagonist_dead = bool(snapshot.get("protagonist_dead", False))
            failure_reached = protagonist_dead
            if isinstance(failure_flags, list) and failure_flags:
                self.failure_flags_value.setText("、".join(str(item) for item in failure_flags))
                failure_reached = True
            else:
                self.failure_flags_value.setText("无")
            self.protagonist_dead_value.setText("是" if protagonist_dead else "否")
            self.failure_state_value.setText("已触发" if failure_reached else "未触发")
            self.status_value.setText(self.controller.status_message or "调试局已就绪")
            pending_wait = snapshot.get("pending_wait")
            if isinstance(pending_wait, dict):
                self.phase_wait_value.setText(
                    f"{pending_wait.get('input_type', '?')}｜{pending_wait.get('player', '?')}｜{pending_wait.get('prompt', '')}"
                )
            else:
                self.phase_wait_value.setText("无")
            self._render_board(snapshot)

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
        def _format_character_line(character_id: str, item: dict[str, object]) -> str:
            display_name = str(item.get("name") or "").strip()
            if not display_name:
                display_name = character_name(character_id)
            if display_name and display_name != character_id:
                head = f"{display_name}（{character_id}）"
            else:
                head = character_id
            status = []
            status.append("存活" if bool(item.get("is_alive", False)) else "死亡")
            if bool(item.get("is_removed", False)):
                status.append("已移除")
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

        @staticmethod
        def _build_target_combos(count: int) -> list[QComboBox]:
            return [QComboBox() for _ in range(count)]

        @staticmethod
        def _build_target_combo_row(combos: list[QComboBox]) -> QWidget:
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            for combo in combos:
                combo.setMinimumWidth(120)
                layout.addWidget(combo)
            return container

        def _set_optional_target_items(
            self,
            combos: list[QComboBox],
            options: list[tuple[str, str]],
        ) -> None:
            for combo in combos:
                self._set_combo_items(combo, [("", "—")] + options, self._combo_value(combo))
                combo.setEnabled(True)

        @staticmethod
        def _selected_combo_values(combos: list[QComboBox]) -> list[str]:
            return [
                value
                for combo in combos
                if (value := TestModeScreen._combo_value(combo))
            ]

        def _notify_after_apply(self) -> None:
            if self._after_apply is not None:
                self._after_apply()

        def _ensure_session(self) -> None:
            if self.controller.session is None:
                self.controller.rebuild_session()
