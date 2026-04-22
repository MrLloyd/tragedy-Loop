from __future__ import annotations

from dataclasses import replace

from engine.display_names import (
    character_option_label,
    identity_option_label,
    incident_option_label,
    module_option_label,
    rule_option_label,
)
from ui.controllers.new_game_controller import (
    CharacterDraft,
    IncidentDraft,
    NewGameDraft,
    default_phase5_draft,
)


class NewGameScreenModel:
    """非公开信息表的无 UI 框架状态模型。"""

    def __init__(self, draft: NewGameDraft | None = None) -> None:
        self._draft = self._normalize_draft(draft or default_phase5_draft())
        self._engine_errors: list[str] = []
        self._wait_context: dict[str, object] = {}
        self.refresh_available_options()

    @property
    def draft(self) -> NewGameDraft:
        return self._draft

    @property
    def character_rows(self) -> list[CharacterDraft]:
        return list(self._draft.characters)

    @property
    def incident_rows(self) -> list[IncidentDraft]:
        return list(self._draft.incidents)

    @property
    def engine_errors(self) -> list[str]:
        return list(self._engine_errors)

    @property
    def wait_context(self) -> dict[str, object]:
        return dict(self._wait_context)

    def set_basic(
        self,
        *,
        module_id: str | None = None,
        loop_count: int | None = None,
        days_per_loop: int | None = None,
        rule_y_id: str | None = None,
        rule_x_ids: list[str] | None = None,
    ) -> None:
        updated = replace(
            self._draft,
            module_id=module_id if module_id is not None else self._draft.module_id,
            loop_count=loop_count if loop_count is not None else self._draft.loop_count,
            days_per_loop=days_per_loop if days_per_loop is not None else self._draft.days_per_loop,
            rule_y_id=rule_y_id if rule_y_id is not None else self._draft.rule_y_id,
            rule_x_ids=list(rule_x_ids) if rule_x_ids is not None else list(self._draft.rule_x_ids),
        )
        self._draft = self._normalize_draft(updated)

    def set_rule_x_ids_from_text(self, value: str) -> None:
        rule_x_ids = [item.strip() for item in value.split(",") if item.strip()]
        self.set_basic(rule_x_ids=rule_x_ids)

    def update_character(self, index: int, *, character_id: str | None = None, identity_id: str | None = None) -> None:
        characters = list(self._draft.characters)
        original = characters[index]
        characters[index] = CharacterDraft(
            character_id=character_id if character_id is not None else original.character_id,
            identity_id=identity_id if identity_id is not None else original.identity_id,
        )
        self._draft = replace(self._draft, characters=characters)

    def add_character(self) -> None:
        characters = list(self._draft.characters)
        characters.append(CharacterDraft("", "平民"))
        self._draft = replace(self._draft, characters=characters)

    def remove_character(self) -> None:
        if len(self._draft.characters) <= 1:
            return
        characters = list(self._draft.characters)
        characters.pop()
        self._draft = replace(self._draft, characters=characters)

    def update_incident(
        self,
        index: int,
        *,
        incident_id: str | None = None,
        day: int | None = None,
        perpetrator_id: str | None = None,
    ) -> None:
        incidents = list(self._draft.incidents)
        original = incidents[index]
        incidents[index] = IncidentDraft(
            incident_id=incident_id if incident_id is not None else original.incident_id,
            day=day if day is not None else original.day,
            perpetrator_id=perpetrator_id if perpetrator_id is not None else original.perpetrator_id,
        )
        self._draft = replace(self._draft, incidents=incidents)

    def validate(self) -> list[str]:
        issues: list[str] = []
        draft = self._draft
        if not draft.module_id:
            issues.append("模组不能为空")
        if draft.loop_count <= 0:
            issues.append("轮回数必须大于 0")
        if draft.days_per_loop <= 0:
            issues.append("每轮天数必须大于 0")
        if not draft.rule_y_id:
            issues.append("规则 Y 不能为空")
        required_rule_x_count = self.rule_x_count()
        if len(draft.rule_x_ids) != required_rule_x_count:
            issues.append(f"规则 X 数量必须为 {required_rule_x_count}")
        if any(not rule_x_id for rule_x_id in draft.rule_x_ids):
            issues.append("规则 X 不能为空")
        if len(set(draft.rule_x_ids)) != len(draft.rule_x_ids):
            issues.append("规则 X 不能重复")

        character_ids = [item.character_id for item in draft.characters]
        if any(not item.character_id or not item.identity_id for item in draft.characters):
            issues.append("角色与身份不能为空")
        if len(character_ids) != len(set(character_ids)):
            issues.append("角色列表中存在重复角色")

        valid_character_ids = set(character_ids)
        seen_perpetrators: set[str] = set()
        for item in draft.incidents:
            if not item.incident_id:
                continue
            if item.day <= 0 or item.day > draft.days_per_loop:
                issues.append(f"事件 {item.incident_id or '?'} 的天数超出范围")
            if not item.perpetrator_id:
                issues.append(f"第 {item.day} 天事件的当事人不能为空")
            if item.perpetrator_id not in valid_character_ids:
                issues.append(f"事件 {item.incident_id or '?'} 的当事人不在角色列表中")
            if item.perpetrator_id in seen_perpetrators:
                issues.append("不同天的事件当事人不能重复")
            if item.perpetrator_id:
                seen_perpetrators.add(item.perpetrator_id)

        return issues

    def apply_wait_context(self, context: dict[str, object] | None) -> None:
        self._wait_context = dict(context or {})
        raw_errors = self._wait_context.get("errors", [])
        self._engine_errors = [str(item) for item in raw_errors] if isinstance(raw_errors, list) else []

    def refresh_available_options(
        self,
        *,
        module_id: str | None = None,
        loop_count: int | None = None,
        days_per_loop: int | None = None,
    ) -> None:
        from engine.rules.module_loader import build_script_setup_context

        selected_module_id = module_id or self._draft.module_id
        self._wait_context = build_script_setup_context(
            selected_module_id,
            loop_count=loop_count if loop_count is not None else self._draft.loop_count,
            days_per_loop=days_per_loop if days_per_loop is not None else self._draft.days_per_loop,
            errors=self._engine_errors,
        )

    def available_ids(self, key: str) -> list[str]:
        raw = self._wait_context.get(key, [])
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw]

    def rule_x_count(self) -> int:
        raw = self._wait_context.get("rule_x_count", len(self._draft.rule_x_ids))
        return max(1, int(raw))

    def build_payload(self) -> dict[str, object]:
        from ui.controllers.new_game_controller import NewGameController

        return NewGameController.build_payload(self._draft)

    @staticmethod
    def _normalize_draft(draft: NewGameDraft) -> NewGameDraft:
        incidents_by_day = {
            item.day: item
            for item in draft.incidents
            if 1 <= item.day <= draft.days_per_loop
        }
        normalized_incidents = [
            incidents_by_day.get(day, IncidentDraft("", day=day, perpetrator_id=""))
            for day in range(1, draft.days_per_loop + 1)
        ]
        return replace(
            draft,
            incidents=normalized_incidents,
        )


try:  # pragma: no cover - PySide6 may be absent in test env
    from PySide6.QtWidgets import (
        QComboBox,
        QGridLayout,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    QWidget = object  # type: ignore[misc,assignment]
else:
    class NewGameScreen(QWidget):
        """最小非公开信息表界面骨架；实际提交逻辑由 controller 绑定。"""

        def __init__(self, model: NewGameScreenModel | None = None, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.model = model or NewGameScreenModel()
            self._character_inputs: list[tuple[QComboBox, QComboBox]] = []
            self._incident_inputs: list[tuple[QLabel, QComboBox, QComboBox]] = []
            self._rule_x_inputs: list[QComboBox] = []

            outer = QVBoxLayout(self)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setMinimumSize(0, 0)
            content = QWidget()
            layout = QVBoxLayout(content)
            scroll.setWidget(content)
            outer.addWidget(scroll)
            layout.addWidget(QLabel("新游戏 / 非公开信息表"))

            form = QFormLayout()
            self.module_input = QComboBox()
            self.loop_input = QSpinBox()
            self.loop_input.setMinimum(1)
            self.loop_input.setValue(self.model.draft.loop_count)
            self.day_input = QSpinBox()
            self.day_input.setMinimum(1)
            self.day_input.setValue(self.model.draft.days_per_loop)
            self.rule_y_input = QComboBox()
            self.rule_x_widget = QWidget()
            self.rule_x_layout = QHBoxLayout(self.rule_x_widget)
            self.rule_x_layout.setContentsMargins(0, 0, 0, 0)
            form.addRow("模组", self.module_input)
            form.addRow("轮回数", self.loop_input)
            form.addRow("每轮天数", self.day_input)
            form.addRow("规则 Y", self.rule_y_input)
            form.addRow("规则 X", self.rule_x_widget)
            layout.addLayout(form)

            layout.addWidget(QLabel("登场角色与身份"))
            character_actions = QHBoxLayout()
            self.add_character_button = QPushButton("增加角色")
            self.remove_character_button = QPushButton("减少角色")
            character_actions.addWidget(self.add_character_button)
            character_actions.addWidget(self.remove_character_button)
            character_actions.addStretch(1)
            layout.addLayout(character_actions)

            self.characters_grid = QGridLayout()
            layout.addLayout(self.characters_grid)

            layout.addWidget(QLabel("事件日程"))
            self.incidents_grid = QGridLayout()
            layout.addLayout(self.incidents_grid)

            self.error_label = QLabel("")
            self.error_label.setWordWrap(True)
            layout.addWidget(self.error_label)

            self.start_button = QPushButton("开始游戏")
            layout.addWidget(self.start_button)

            self.module_input.currentIndexChanged.connect(self._on_module_changed)
            self.day_input.valueChanged.connect(self._on_days_changed)
            self.add_character_button.clicked.connect(self._on_add_character)
            self.remove_character_button.clicked.connect(self._on_remove_character)
            self._rebuild_character_inputs()
            self._rebuild_incident_inputs()
            self._refresh_select_options()
            self.refresh_errors()

        def sync_model_from_inputs(self) -> None:
            self.model.set_basic(
                module_id=self._combo_value(self.module_input),
                loop_count=self.loop_input.value(),
                days_per_loop=self.day_input.value(),
                rule_y_id=self._combo_value(self.rule_y_input),
                rule_x_ids=[
                    self._combo_value(combo)
                    for combo in self._rule_x_inputs
                    if self._combo_value(combo)
                ],
            )
            for index, (character_input, identity_input) in enumerate(self._character_inputs):
                self.model.update_character(
                    index,
                    character_id=self._combo_value(character_input),
                    identity_id=self._combo_value(identity_input),
                )
            for index, (_, incident_input, perpetrator_input) in enumerate(self._incident_inputs):
                self.model.update_incident(
                    index,
                    incident_id=self._combo_value(incident_input),
                    day=index + 1,
                    perpetrator_id=self._combo_value(perpetrator_input),
                )
            self.model.refresh_available_options(
                module_id=self.model.draft.module_id,
                loop_count=self.model.draft.loop_count,
                days_per_loop=self.model.draft.days_per_loop,
            )
            self.refresh_errors()

        def _on_module_changed(self) -> None:
            self.sync_model_from_inputs()
            module_id = self._combo_value(self.module_input)
            if not module_id:
                return
            self.model.set_basic(
                module_id=module_id,
                loop_count=self.loop_input.value(),
                days_per_loop=self.day_input.value(),
            )
            self.model.refresh_available_options(
                module_id=module_id,
                loop_count=self.loop_input.value(),
                days_per_loop=self.day_input.value(),
            )
            self._refresh_select_options()

        def _on_days_changed(self) -> None:
            self.sync_model_from_inputs()
            self.model.set_basic(days_per_loop=self.day_input.value())
            self._rebuild_incident_inputs()
            self._refresh_select_options()

        def _on_add_character(self) -> None:
            self.sync_model_from_inputs()
            self.model.add_character()
            self._rebuild_character_inputs()
            self._refresh_select_options()

        def _on_remove_character(self) -> None:
            self.sync_model_from_inputs()
            self.model.remove_character()
            self._rebuild_character_inputs()
            self._refresh_select_options()

        def _refresh_select_options(self) -> None:
            draft = self.model.draft
            self._set_combo_items(
                self.module_input,
                [
                    (module_id, module_option_label(module_id))
                    for module_id in self.model.available_ids("available_modules")
                ],
                draft.module_id,
            )
            self._set_combo_items(
                self.rule_y_input,
                [
                    (rule_id, rule_option_label(rule_id))
                    for rule_id in self.model.available_ids("available_rule_y_ids")
                ],
                draft.rule_y_id,
            )

            self._ensure_rule_x_inputs()
            self._refresh_rule_x_options()

            character_options = [
                (character_id, character_option_label(character_id))
                for character_id in self.model.available_ids("available_characters")
            ]
            identity_ids = [
                "平民",
                *[
                    identity_id for identity_id in self.model.available_ids("available_identities")
                    if identity_id not in {"平民", "commoner"}
                ],
            ]
            identity_options = [
                (identity_id, identity_option_label(identity_id))
                for identity_id in identity_ids
            ]
            for index, (character_input, identity_input) in enumerate(self._character_inputs):
                current_character = draft.characters[index].character_id
                current_identity = draft.characters[index].identity_id
                self._set_combo_items(character_input, character_options, current_character)
                self._set_combo_items(identity_input, identity_options, current_identity)

            incident_options = [
                ("", "无事件"),
                *[
                    (incident_id, incident_option_label(incident_id))
                    for incident_id in self.model.available_ids("available_incidents")
                ],
            ]
            for index, (day_label, incident_input, _) in enumerate(self._incident_inputs):
                current_incident = draft.incidents[index].incident_id
                day_label.setText(f"第 {index + 1} 天")
                self._set_combo_items(incident_input, incident_options, current_incident)

            self._refresh_perpetrator_options()
            self.remove_character_button.setEnabled(len(draft.characters) > 1)

        def _rebuild_character_inputs(self) -> None:
            while self.characters_grid.count():
                item = self.characters_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            self._character_inputs.clear()
            self.characters_grid.addWidget(QLabel("角色"), 0, 0)
            self.characters_grid.addWidget(QLabel("身份"), 0, 1)
            for index, _item in enumerate(self.model.draft.characters, start=1):
                character_input = QComboBox()
                identity_input = QComboBox()
                character_input.currentIndexChanged.connect(self._refresh_perpetrator_options)
                self.characters_grid.addWidget(character_input, index, 0)
                self.characters_grid.addWidget(identity_input, index, 1)
                self._character_inputs.append((character_input, identity_input))

        def _ensure_rule_x_inputs(self) -> None:
            while len(self._rule_x_inputs) > self.model.rule_x_count():
                combo = self._rule_x_inputs.pop()
                self.rule_x_layout.removeWidget(combo)
                combo.deleteLater()
            while len(self._rule_x_inputs) < self.model.rule_x_count():
                combo = QComboBox()
                combo.currentIndexChanged.connect(self._on_rule_x_changed)
                self._rule_x_inputs.append(combo)
                self.rule_x_layout.addWidget(combo)

        def _refresh_rule_x_options(self) -> None:
            available_rule_x = self.model.available_ids("available_rule_x_ids")
            current_values = []
            for index, combo in enumerate(self._rule_x_inputs):
                current = self._combo_value(combo)
                if not current and index < len(self.model.draft.rule_x_ids):
                    current = self.model.draft.rule_x_ids[index]
                current_values.append(current)
            for index, combo in enumerate(self._rule_x_inputs):
                current = current_values[index] if index < len(current_values) else ""
                options = [
                    (rule_id, rule_option_label(rule_id))
                    for rule_id in available_rule_x
                ]
                self._set_combo_items(combo, options, current)

        def _on_rule_x_changed(self) -> None:
            self.model.set_basic(
                rule_x_ids=[
                    self._combo_value(combo)
                    for combo in self._rule_x_inputs
                    if self._combo_value(combo)
                ],
            )

        def _rebuild_incident_inputs(self) -> None:
            while self.incidents_grid.count():
                item = self.incidents_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            while self._incident_inputs:
                self._incident_inputs.pop()

            self.incidents_grid.addWidget(QLabel("天数"), 0, 0)
            self.incidents_grid.addWidget(QLabel("事件"), 0, 1)
            self.incidents_grid.addWidget(QLabel("当事人"), 0, 2)
            for index in range(self.model.draft.days_per_loop):
                day_label = QLabel(f"第 {index + 1} 天")
                incident_input = QComboBox()
                perpetrator_input = QComboBox()
                self.incidents_grid.addWidget(day_label, index + 1, 0)
                self.incidents_grid.addWidget(incident_input, index + 1, 1)
                self.incidents_grid.addWidget(perpetrator_input, index + 1, 2)
                self._incident_inputs.append((day_label, incident_input, perpetrator_input))

        def _refresh_perpetrator_options(self) -> None:
            selected_characters = [
                self._combo_value(character_input)
                for character_input, _ in self._character_inputs
                if self._combo_value(character_input)
            ]
            if not selected_characters:
                selected_characters = self.model.available_ids("available_characters")
            options = [
                ("", "未选择"),
                *[
                    (character_id, character_option_label(character_id))
                    for character_id in selected_characters
                ],
            ]
            for index, (_, _, perpetrator_input) in enumerate(self._incident_inputs):
                current = self.model.draft.incidents[index].perpetrator_id
                if perpetrator_input.currentData():
                    current = self._combo_value(perpetrator_input)
                self._set_combo_items(perpetrator_input, options, current)

        @staticmethod
        def _combo_value(combo: QComboBox) -> str:
            value = combo.currentData()
            if value is None:
                return combo.currentText().strip()
            return str(value)

        @staticmethod
        def _set_combo_items(
            combo: QComboBox,
            options: list[tuple[str, str]],
            current_value: str,
        ) -> None:
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

        def refresh_errors(self, local_issues: list[str] | None = None) -> None:
            issues = list(local_issues or [])
            issues.extend(self.model.engine_errors)
            if not issues:
                self.error_label.setText("")
                return
            self.error_label.setText("校验问题：\n- " + "\n- ".join(issues))
