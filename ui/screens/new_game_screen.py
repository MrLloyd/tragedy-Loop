from __future__ import annotations

from dataclasses import replace

from engine.display_names import (
    area_name,
    character_option_label,
    identity_option_label,
    incident_option_label,
    module_option_label,
    rule_option_label,
)
from engine.models.enums import AreaId
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
            initial_area_id=original.initial_area_id,
            territory_area_id=original.territory_area_id,
            entry_loop=original.entry_loop,
            entry_day=original.entry_day,
        )
        self._draft = replace(self._draft, characters=characters)

    def update_character_initial_area(self, index: int, initial_area_id: str) -> None:
        characters = list(self._draft.characters)
        original = characters[index]
        characters[index] = CharacterDraft(
            character_id=original.character_id,
            identity_id=original.identity_id,
            initial_area_id=initial_area_id,
            territory_area_id=original.territory_area_id,
            entry_loop=original.entry_loop,
            entry_day=original.entry_day,
        )
        self._draft = replace(self._draft, characters=characters)

    def update_character_territory_area(self, index: int, territory_area_id: str) -> None:
        characters = list(self._draft.characters)
        original = characters[index]
        characters[index] = CharacterDraft(
            character_id=original.character_id,
            identity_id=original.identity_id,
            initial_area_id=original.initial_area_id,
            territory_area_id=territory_area_id,
            entry_loop=original.entry_loop,
            entry_day=original.entry_day,
        )
        self._draft = replace(self._draft, characters=characters)

    def update_character_entry_loop(self, index: int, entry_loop: int) -> None:
        characters = list(self._draft.characters)
        original = characters[index]
        characters[index] = CharacterDraft(
            character_id=original.character_id,
            identity_id=original.identity_id,
            initial_area_id=original.initial_area_id,
            territory_area_id=original.territory_area_id,
            entry_loop=entry_loop,
            entry_day=original.entry_day,
        )
        self._draft = replace(self._draft, characters=characters)

    def update_character_entry_day(self, index: int, entry_day: int) -> None:
        characters = list(self._draft.characters)
        original = characters[index]
        characters[index] = CharacterDraft(
            character_id=original.character_id,
            identity_id=original.identity_id,
            initial_area_id=original.initial_area_id,
            territory_area_id=original.territory_area_id,
            entry_loop=original.entry_loop,
            entry_day=entry_day,
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

    def character_initial_area_spec(self, character_id: str) -> dict[str, object]:
        raw_specs = self._wait_context.get("character_initial_area_specs", {})
        if not isinstance(raw_specs, dict):
            return {}
        raw = raw_specs.get(character_id, {})
        return dict(raw) if isinstance(raw, dict) else {}

    def character_can_set_entry_loop(self, character_id: str) -> bool:
        allowed = self.available_ids("entry_loop_character_ids")
        return character_id in allowed

    def character_can_set_entry_day(self, character_id: str) -> bool:
        allowed = self.available_ids("entry_day_character_ids")
        return character_id in allowed

    def character_initial_area_options(self, character_id: str) -> tuple[list[tuple[str, str]], bool]:
        spec = self.character_initial_area_spec(character_id)
        mode = str(spec.get("mode", "fixed") or "fixed")
        default_area = str(spec.get("default_area", "") or "")
        raw_candidates = spec.get("candidates", [])
        candidates = [str(item) for item in raw_candidates] if isinstance(raw_candidates, list) else []

        if mode == "script_choice":
            return ([(area_id, area_name(area_id)) for area_id in candidates], True)
        if mode == "mastermind_each_loop":
            return ([("", "每轮回开始由剧作家决定")], False)
        label = f"固定：{area_name(default_area)}" if default_area else "固定"
        return ([("", label)], False)

    @staticmethod
    def character_territory_area_options(character_id: str) -> tuple[list[tuple[str, str]], bool]:
        if character_id != "vip":
            return ([("", "无领地")], False)
        options = [(area.value, area_name(area.value)) for area in AreaId if area != AreaId.FARAWAY]
        return (options, True)

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
            self._character_inputs: list[tuple[QComboBox, QComboBox, QComboBox, QComboBox, QSpinBox, QSpinBox]] = []
            self._incident_inputs: list[tuple[QLabel, QComboBox, QComboBox]] = []
            self._rule_x_inputs: list[QComboBox] = []

            outer = QVBoxLayout(self)
            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll.setMinimumSize(0, 0)
            self._content = QWidget()
            layout = QVBoxLayout(self._content)
            self._scroll.setWidget(self._content)
            outer.addWidget(self._scroll)
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
            self.character_count_label = QLabel("")
            character_actions.addWidget(self.add_character_button)
            character_actions.addWidget(self.remove_character_button)
            character_actions.addWidget(self.character_count_label)
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
            self.rule_y_input.currentIndexChanged.connect(self._on_rule_y_changed)
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
            for index, (character_input, identity_input, initial_area_input, territory_area_input, entry_loop_input, entry_day_input) in enumerate(self._character_inputs):
                self.model.update_character(
                    index,
                    character_id=self._combo_value(character_input),
                    identity_id=self._combo_value(identity_input),
                )
                self.model.update_character_initial_area(
                    index,
                    initial_area_id=self._combo_value(initial_area_input),
                )
                self.model.update_character_territory_area(
                    index,
                    territory_area_id=self._combo_value(territory_area_input),
                )
                character_id = self._combo_value(character_input)
                if self.model.character_can_set_entry_loop(character_id):
                    self.model.update_character_entry_loop(index, entry_loop_input.value())
                else:
                    self.model.update_character_entry_loop(index, 0)
                if self.model.character_can_set_entry_day(character_id):
                    self.model.update_character_entry_day(index, entry_day_input.value())
                else:
                    self.model.update_character_entry_day(index, 0)
            active_incident_inputs = self._incident_inputs[:self.model.draft.days_per_loop]
            for index, (_, incident_input, perpetrator_input) in enumerate(active_incident_inputs):
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
            module_id = self._combo_value(self.module_input)
            if not module_id:
                return
            self.model.set_basic(
                module_id=module_id,
                loop_count=self.loop_input.value(),
                days_per_loop=self.day_input.value(),
                rule_y_id="",
                rule_x_ids=[],
            )
            self.model.refresh_available_options(
                module_id=module_id,
                loop_count=self.loop_input.value(),
                days_per_loop=self.day_input.value(),
            )
            self._refresh_select_options()
            self._sync_rule_selection_to_model()

        def _on_rule_y_changed(self) -> None:
            self.model.set_basic(rule_y_id=self._combo_value(self.rule_y_input))

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
            self._focus_character_row(len(self._character_inputs) - 1)

        def _on_remove_character(self) -> None:
            self.sync_model_from_inputs()
            self.model.remove_character()
            self._rebuild_character_inputs()
            self._refresh_select_options()
            self._focus_character_row(len(self._character_inputs) - 1)

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
            for index, (character_input, identity_input, _initial_area_input, _territory_area_input, _entry_loop_input, _entry_day_input) in enumerate(self._character_inputs):
                current_character = draft.characters[index].character_id
                current_identity = draft.characters[index].identity_id
                self._set_combo_items(character_input, character_options, current_character)
                self._set_combo_items(identity_input, identity_options, current_identity)
            self._refresh_character_initial_area_inputs()
            self._refresh_character_territory_area_inputs()
            self._refresh_character_entry_inputs()

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
            self.character_count_label.setText(f"当前 {len(draft.characters)} 名角色")
            self.remove_character_button.setEnabled(len(draft.characters) > 1)
            self._refresh_dynamic_layout()

        def _rebuild_character_inputs(self) -> None:
            while self.characters_grid.count():
                item = self.characters_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            self._character_inputs.clear()
            self.characters_grid.addWidget(QLabel("角色"), 0, 0)
            self.characters_grid.addWidget(QLabel("身份"), 0, 1)
            self.characters_grid.addWidget(QLabel("初始区域"), 0, 2)
            self.characters_grid.addWidget(QLabel("领地"), 0, 3)
            self.characters_grid.addWidget(QLabel("登场轮回"), 0, 4)
            self.characters_grid.addWidget(QLabel("登场天数"), 0, 5)
            for index, _item in enumerate(self.model.draft.characters, start=1):
                character_input = QComboBox()
                identity_input = QComboBox()
                initial_area_input = QComboBox()
                territory_area_input = QComboBox()
                entry_loop_input = QSpinBox()
                entry_loop_input.setMinimum(0)
                entry_loop_input.setMaximum(999)
                entry_day_input = QSpinBox()
                entry_day_input.setMinimum(0)
                entry_day_input.setMaximum(999)
                character_input.currentIndexChanged.connect(self._refresh_perpetrator_options)
                character_input.currentIndexChanged.connect(self._refresh_character_initial_area_inputs)
                character_input.currentIndexChanged.connect(self._refresh_character_territory_area_inputs)
                character_input.currentIndexChanged.connect(self._refresh_character_entry_inputs)
                self.characters_grid.addWidget(character_input, index, 0)
                self.characters_grid.addWidget(identity_input, index, 1)
                self.characters_grid.addWidget(initial_area_input, index, 2)
                self.characters_grid.addWidget(territory_area_input, index, 3)
                self.characters_grid.addWidget(entry_loop_input, index, 4)
                self.characters_grid.addWidget(entry_day_input, index, 5)
                self._character_inputs.append(
                    (
                        character_input,
                        identity_input,
                        initial_area_input,
                        territory_area_input,
                        entry_loop_input,
                        entry_day_input,
                    )
                )

        def _focus_character_row(self, index: int) -> None:
            if not self._character_inputs:
                return
            target_index = max(0, min(index, len(self._character_inputs) - 1))
            target_widget = self._character_inputs[target_index][0]
            target_widget.setFocus()
            self._scroll.ensureWidgetVisible(target_widget)

        def _refresh_dynamic_layout(self) -> None:
            self.characters_grid.invalidate()
            self.incidents_grid.invalidate()
            self._content.adjustSize()
            self._content.updateGeometry()

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
            self._sync_rule_selection_to_model()

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
                for character_input, _, _, _, _, _ in self._character_inputs
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

        def _refresh_character_initial_area_inputs(self) -> None:
            for index, (character_input, _, initial_area_input, _, _, _) in enumerate(self._character_inputs):
                current_character = self._combo_value(character_input)
                current_initial_area = self._combo_value(initial_area_input)
                if not current_initial_area and index < len(self.model.draft.characters):
                    current_initial_area = self.model.draft.characters[index].initial_area_id
                area_options, enabled = self.model.character_initial_area_options(current_character)
                self._set_combo_items(initial_area_input, area_options, current_initial_area)
                initial_area_input.setEnabled(enabled)

        def _refresh_character_territory_area_inputs(self) -> None:
            for index, (character_input, _, _, territory_area_input, _, _) in enumerate(self._character_inputs):
                current_character = self._combo_value(character_input)
                current_territory_area = self._combo_value(territory_area_input)
                if not current_territory_area and index < len(self.model.draft.characters):
                    current_territory_area = self.model.draft.characters[index].territory_area_id
                area_options, enabled = self.model.character_territory_area_options(current_character)
                self._set_combo_items(territory_area_input, area_options, current_territory_area)
                territory_area_input.setEnabled(enabled)

        def _refresh_character_entry_inputs(self) -> None:
            for index, (character_input, _, _, _, entry_loop_input, entry_day_input) in enumerate(self._character_inputs):
                current_character = self._combo_value(character_input)
                current_entry_loop = self.model.draft.characters[index].entry_loop
                current_entry_day = self.model.draft.characters[index].entry_day
                entry_loop_enabled = self.model.character_can_set_entry_loop(current_character)
                entry_day_enabled = self.model.character_can_set_entry_day(current_character)

                entry_loop_input.blockSignals(True)
                entry_loop_input.setValue(current_entry_loop)
                entry_loop_input.setEnabled(entry_loop_enabled)
                entry_loop_input.blockSignals(False)

                entry_day_input.blockSignals(True)
                entry_day_input.setValue(current_entry_day)
                entry_day_input.setEnabled(entry_day_enabled)
                entry_day_input.blockSignals(False)

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

        def _sync_rule_selection_to_model(self) -> None:
            self.model.set_basic(
                rule_y_id=self._combo_value(self.rule_y_input),
                rule_x_ids=[
                    self._combo_value(combo)
                    for combo in self._rule_x_inputs
                    if self._combo_value(combo)
                ],
            )
