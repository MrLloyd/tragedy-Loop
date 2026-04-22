from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from engine.display_names import (
    area_name,
    card_name,
    character_name,
    display_target_name,
    format_public_incidents,
    format_tokens,
    identity_name,
    outcome_name,
    phase_name,
    player_name,
    wait_type_name,
)
from engine.models.enums import AreaId
from ui.controllers.game_session_controller import SessionViewState

if TYPE_CHECKING:
    from ui.controllers.game_session_controller import GameSessionController


@dataclass
class GameCharacterRow:
    character_id: str
    name: str
    area_id: str
    area: str
    is_alive: bool
    identity_id: str
    identity: str
    tokens: dict[str, int]


@dataclass
class GameScreenSnapshot:
    phase: str = ""
    loop_text: str = ""
    day_text: str = ""
    leader_text: str = ""
    module_id: str = ""
    characters: list[GameCharacterRow] = field(default_factory=list)
    board_tokens: dict[str, dict[str, int]] = field(default_factory=dict)
    public_info: dict[str, object] = field(default_factory=dict)
    protagonist_announcements: list[str] = field(default_factory=list)
    mastermind_announcements: list[str] = field(default_factory=list)
    wait_input_type: str = ""
    wait_prompt: str = ""
    wait_player: str = ""
    wait_option_labels: list[str] = field(default_factory=list)
    debug_snapshot: dict[str, object] = field(default_factory=dict)
    debug_text: str = ""
    outcome: str = ""

    @property
    def announcements(self) -> list[str]:
        return self.protagonist_announcements


class GameScreenModel:
    """对局主界面状态模型（P6-4/P6-5 最小闭环）。"""

    def __init__(self) -> None:
        self.snapshot = GameScreenSnapshot()

    def sync_from_session(
        self,
        view_state: SessionViewState,
        *,
        debug_snapshot: dict[str, object] | None = None,
    ) -> None:
        snapshot = GameScreenSnapshot()
        visible = view_state.protagonist_visible_state
        if visible is not None:
            snapshot.phase = phase_name(visible.phase)
            snapshot.loop_text = f"第 {visible.current_loop} / {visible.max_loops} 轮"
            snapshot.day_text = f"第 {visible.current_day} / {visible.max_days} 天"
            snapshot.leader_text = f"主人公 {visible.leader_index + 1}"
            snapshot.module_id = str(visible.public_info.get("module_id", ""))
            snapshot.characters = [
                GameCharacterRow(
                    character_id=character.character_id,
                    name=character.name,
                    area_id=character.area.value,
                    area=area_name(character.area.value),
                    is_alive=character.is_alive,
                    identity_id=character.identity,
                    identity=identity_name(character.identity),
                    tokens=dict(character.tokens),
                )
                for character in visible.characters
            ]
            snapshot.board_tokens = {
                area_id: dict(tokens)
                for area_id, tokens in visible.board_tokens.items()
            }
            snapshot.public_info = dict(visible.public_info)

        snapshot.protagonist_announcements = list(view_state.protagonist_announcements)
        snapshot.mastermind_announcements = list(view_state.mastermind_announcements)

        wait = view_state.current_wait
        if wait is not None:
            snapshot.wait_input_type = wait.input_type
            snapshot.wait_prompt = wait.prompt
            snapshot.wait_player = wait.player
            snapshot.wait_option_labels = [
                self._format_wait_option(option)
                for option in wait.options
            ]

        snapshot.debug_snapshot = dict(debug_snapshot or {})
        snapshot.debug_text = self._format_debug_snapshot(snapshot.debug_snapshot)

        if view_state.outcome is not None:
            snapshot.outcome = outcome_name(view_state.outcome.value)

        self.snapshot = snapshot

    @staticmethod
    def board_target_options() -> list[str]:
        return [
            AreaId.HOSPITAL.value,
            AreaId.SHRINE.value,
            AreaId.CITY.value,
            AreaId.SCHOOL.value,
        ]

    @staticmethod
    def _format_wait_option(option: Any) -> str:
        if isinstance(option, str):
            if option == "pass":
                return "放弃 / 结束声明"
            return display_target_name(option)
        card_type = getattr(option, "card_type", None)
        if card_type is not None:
            return card_name(card_type.value)
        ability = getattr(option, "ability", None)
        source_id = getattr(option, "source_id", "")
        if ability is not None and hasattr(ability, "name"):
            if source_id:
                return f"{character_name(source_id)}：{ability.name}"
            return f"ability:{ability.name}"
        return str(option)

    @staticmethod
    def _format_debug_snapshot(debug_snapshot: dict[str, object]) -> str:
        if not debug_snapshot:
            return ""
        return json.dumps(debug_snapshot, ensure_ascii=False, indent=2, sort_keys=True)


try:  # pragma: no cover - widget rendering is not unit-tested
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QComboBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    QWidget = object  # type: ignore[misc,assignment]
else:
    class GameScreen(QWidget):
        """对局主界面：展示可见状态，并消费 WaitForInput。"""

        def __init__(
            self,
            session: GameSessionController | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._session = session
            self._model = GameScreenModel()
            self._after_submit: Callable[[], None] | None = None

            outer = QVBoxLayout(self)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setMinimumSize(0, 0)
            content = QWidget()
            root = QVBoxLayout(content)
            scroll.setWidget(content)
            outer.addWidget(scroll)

            status_box = QGroupBox("对局信息")
            status_layout = QFormLayout(status_box)
            self.phase_value = QLabel("-")
            self.loop_value = QLabel("-")
            self.day_value = QLabel("-")
            self.leader_value = QLabel("-")
            self.public_events_value = QLabel("-")
            self.public_events_value.setWordWrap(True)
            status_layout.addRow("阶段", self.phase_value)
            status_layout.addRow("轮回", self.loop_value)
            status_layout.addRow("天数", self.day_value)
            status_layout.addRow("队长", self.leader_value)
            status_layout.addRow("公开事件", self.public_events_value)
            root.addWidget(status_box)

            board_box = QGroupBox("版图")
            board_layout = QGridLayout(board_box)
            self.board_area_texts: dict[str, QTextEdit] = {}
            for area_id, row, col in (
                (AreaId.HOSPITAL.value, 0, 0),
                (AreaId.SHRINE.value, 0, 1),
                (AreaId.CITY.value, 1, 0),
                (AreaId.SCHOOL.value, 1, 1),
            ):
                area_box = QGroupBox(area_name(area_id))
                area_layout = QVBoxLayout(area_box)
                area_text = QTextEdit()
                area_text.setReadOnly(True)
                area_text.setMinimumHeight(120)
                area_layout.addWidget(area_text)
                board_layout.addWidget(area_box, row, col)
                self.board_area_texts[area_id] = area_text
            root.addWidget(board_box)

            token_box = QGroupBox("事件公告")
            token_layout = QHBoxLayout(token_box)
            protagonist_box = QGroupBox("主人公视角")
            protagonist_layout = QVBoxLayout(protagonist_box)
            self.protagonist_announce_text = QTextEdit()
            self.protagonist_announce_text.setReadOnly(True)
            protagonist_layout.addWidget(self.protagonist_announce_text)
            token_layout.addWidget(protagonist_box)

            mastermind_box = QGroupBox("剧作家视角")
            mastermind_layout = QVBoxLayout(mastermind_box)
            self.mastermind_announce_text = QTextEdit()
            self.mastermind_announce_text.setReadOnly(True)
            mastermind_layout.addWidget(self.mastermind_announce_text)
            token_layout.addWidget(mastermind_box)
            root.addWidget(token_box)

            debug_box = QGroupBox("调试快照（只读）")
            debug_layout = QVBoxLayout(debug_box)
            self.debug_text = QTextEdit()
            self.debug_text.setReadOnly(True)
            self.debug_refresh_button = QPushButton("刷新调试快照")
            debug_layout.addWidget(self.debug_text)
            debug_layout.addWidget(self.debug_refresh_button)
            root.addWidget(debug_box)

            wait_box = QGroupBox("等待输入")
            wait_layout = QVBoxLayout(wait_box)
            self.wait_prompt = QLabel("-")
            self.wait_prompt.setWordWrap(True)
            wait_layout.addWidget(self.wait_prompt)

            self.options_list = QListWidget()
            wait_layout.addWidget(self.options_list)

            self.target_row_widget = QWidget()
            target_row = QHBoxLayout(self.target_row_widget)
            target_row.setContentsMargins(0, 0, 0, 0)
            self.target_type = QComboBox()
            self.target_type.addItem("版图", "board")
            self.target_type.addItem("角色", "character")
            self.target_id = QComboBox()
            target_row.addWidget(QLabel("目标类型"))
            target_row.addWidget(self.target_type)
            target_row.addWidget(QLabel("目标"))
            target_row.addWidget(self.target_id)
            wait_layout.addWidget(self.target_row_widget)

            actions = QHBoxLayout()
            self.submit_button = QPushButton("提交选择")
            self.confirm_button = QPushButton("确认")
            self.pass_button = QPushButton("Pass")
            self.allow_button = QPushButton("允许")
            self.refuse_button = QPushButton("拒绝")
            actions.addWidget(self.submit_button)
            actions.addWidget(self.confirm_button)
            actions.addWidget(self.pass_button)
            actions.addWidget(self.allow_button)
            actions.addWidget(self.refuse_button)
            wait_layout.addLayout(actions)

            root.addWidget(wait_box)

            self.submit_button.clicked.connect(self._on_submit)
            self.confirm_button.clicked.connect(self._on_confirm)
            self.pass_button.clicked.connect(self._on_pass)
            self.allow_button.clicked.connect(lambda: self._on_goodwill_response(True))
            self.refuse_button.clicked.connect(lambda: self._on_goodwill_response(False))
            self.target_type.currentIndexChanged.connect(self._refresh_target_ids)
            self.debug_refresh_button.clicked.connect(self.refresh)

            self.refresh()

        def bind_session(self, session: GameSessionController) -> None:
            self._session = session
            self._session.set_state_updated_callback(self.refresh)
            self.refresh()

        def set_after_submit(self, callback: Callable[[], None]) -> None:
            self._after_submit = callback

        def refresh(self) -> None:
            if self._session is None:
                return

            self._model.sync_from_session(
                self._session.view_state,
                debug_snapshot=self._session.read_debug_snapshot(),
            )
            snapshot = self._model.snapshot
            self.phase_value.setText(snapshot.phase or "-")
            self.loop_value.setText(snapshot.loop_text or "-")
            self.day_value.setText(snapshot.day_text or "-")
            self.leader_value.setText(snapshot.leader_text or "-")
            self.public_events_value.setText(format_public_incidents(snapshot.public_info))

            self._render_board(snapshot)
            self.protagonist_announce_text.setPlainText(
                "\n".join(snapshot.protagonist_announcements)
            )
            self.mastermind_announce_text.setPlainText(
                "\n".join(snapshot.mastermind_announcements)
            )
            self.debug_text.setPlainText(snapshot.debug_text)
            self.wait_prompt.setText(
                f"[{wait_type_name(snapshot.wait_input_type)}] {snapshot.wait_prompt}（{player_name(snapshot.wait_player)}）"
                if snapshot.wait_input_type
                else "当前无需输入"
            )
            self._render_wait_options(snapshot)
            self._refresh_target_ids()
            self._toggle_action_buttons(snapshot.wait_input_type)

        def _render_board(self, snapshot: GameScreenSnapshot) -> None:
            for area_id, text_widget in self.board_area_texts.items():
                lines = [
                    f"版图标记物：{format_tokens(snapshot.board_tokens.get(area_id, {}))}",
                    "角色：",
                ]
                area_characters = [
                    item for item in snapshot.characters
                    if item.area_id == area_id
                ]
                if not area_characters:
                    lines.append("- 无")
                else:
                    for item in area_characters:
                        status = "存活" if item.is_alive else "死亡"
                        lines.append(
                            f"- {item.name or item.character_id}｜{status}｜"
                            f"身份：{item.identity}｜标记物：{format_tokens(item.tokens)}"
                        )
                text_widget.setPlainText("\n".join(lines))

        def _render_wait_options(self, snapshot: GameScreenSnapshot) -> None:
            self.options_list.clear()
            for label in snapshot.wait_option_labels:
                self.options_list.addItem(QListWidgetItem(label))
            self.options_list.setSelectionMode(QListWidget.SingleSelection)

        def _refresh_target_ids(self) -> None:
            if self._session is None:
                return
            self.target_id.clear()
            if self.target_type.currentData() == "board":
                for area_id in self._model.board_target_options():
                    self.target_id.addItem(area_name(area_id), area_id)
                return
            visible = self._session.view_state.mastermind_visible_state
            if visible is None:
                visible = self._session.view_state.protagonist_visible_state
            if visible is None:
                return
            for item in visible.characters:
                self.target_id.addItem(character_name(item.character_id), item.character_id)

        def _toggle_action_buttons(self, wait_type: str) -> None:
            allow_response = wait_type == "respond_goodwill_ability"
            self.allow_button.setVisible(allow_response)
            self.refuse_button.setVisible(allow_response)
            wait = self._session.view_state.current_wait if self._session is not None else None
            requires_target = wait_type in {"place_action_cards", "place_action_card"}
            supports_confirm = bool(wait_type) and wait is not None and not wait.options and not allow_response
            supports_submit = bool(wait_type) and wait is not None and bool(wait.options) and not allow_response
            self.target_row_widget.setVisible(requires_target)
            self.submit_button.setVisible(supports_submit)
            self.submit_button.setEnabled(supports_submit)
            self.confirm_button.setVisible(supports_confirm)
            self.confirm_button.setEnabled(supports_confirm)

            has_pass = False
            if wait is not None:
                has_pass = "pass" in wait.options
            self.pass_button.setVisible(has_pass)

        def _on_pass(self) -> None:
            if self._session is None:
                return
            try:
                self._session.submit_pass()
            except Exception as exc:
                QMessageBox.warning(self, "输入错误", str(exc))
            self.refresh()
            self._notify_after_submit()

        def _on_confirm(self) -> None:
            if self._session is None:
                return
            try:
                self._session.submit_confirm()
            except Exception as exc:
                QMessageBox.warning(self, "输入错误", str(exc))
            self.refresh()
            self._notify_after_submit()

        def _on_goodwill_response(self, allow: bool) -> None:
            if self._session is None:
                return
            try:
                self._session.submit_goodwill_response(allow=allow)
            except Exception as exc:
                QMessageBox.warning(self, "输入错误", str(exc))
            self.refresh()
            self._notify_after_submit()

        def _on_submit(self) -> None:
            if self._session is None:
                return
            wait = self._session.view_state.current_wait
            if wait is None:
                return

            try:
                if wait.input_type == "place_action_card":
                    self._submit_place_action_card(wait.options)
                else:
                    self._submit_single_choice(wait.options)
            except Exception as exc:
                QMessageBox.warning(self, "输入错误", str(exc))
            self.refresh()
            self._notify_after_submit()

        def _submit_place_action_card(self, options: list[Any]) -> None:
            if self._session is None:
                return
            indexes = self.options_list.selectedIndexes()
            if len(indexes) != 1:
                raise ValueError("请恰好选择 1 张行动牌")
            target_type = str(self.target_type.currentData())
            target_id = str(self.target_id.currentData())
            self._session.submit_place_action_card(
                card=options[indexes[0].row()],
                target_type=target_type,
                target_id=target_id,
            )

        def _submit_single_choice(self, options: list[Any]) -> None:
            if self._session is None:
                return
            indexes = self.options_list.selectedIndexes()
            if len(indexes) != 1:
                raise ValueError("请恰好选择 1 项")
            self._session.submit_input(options[indexes[0].row()])

        def _notify_after_submit(self) -> None:
            if self._after_submit is not None:
                self._after_submit()

        @staticmethod
        def _format_kv_text(data: dict[str, Any]) -> str:
            if not data:
                return ""
            lines: list[str] = []
            for key, value in data.items():
                lines.append(f"{key}: {value}")
            return "\n".join(lines)
