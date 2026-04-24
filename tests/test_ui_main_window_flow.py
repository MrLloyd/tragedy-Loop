from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from engine.models.enums import GamePhase
from engine.event_bus import GameEvent, GameEventType
from ui.controllers.game_session_controller import GameSessionController
from ui.controllers.test_mode_controller import TestCharacterDraft, TestModeController

try:
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from ui.screens.game_screen import GameScreen
    from ui.screens.new_game_screen import NewGameScreen
    from ui.screens.test_mode_screen import TestModeScreen
    from ui.screens.title_screen import TitleScreen
except Exception:  # pragma: no cover - optional UI dependency
    QApplication = None  # type: ignore[assignment]


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_start_new_game_click_flow_keeps_main_window_open() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()

    assert isinstance(window._stack.currentWidget(), TitleScreen)

    window.title_screen.new_game_button.click()

    assert window.isVisible()
    assert isinstance(window._stack.currentWidget(), NewGameScreen)
    assert window.session is not None
    assert window.session.current_wait_input_type() == "script_setup"

    assert window.new_game_screen is not None
    window.new_game_screen.start_button.click()

    assert window.isVisible()
    assert isinstance(window._stack.currentWidget(), GameScreen)
    assert window.session.current_wait_input_type() == "place_action_card"

    window.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_start_test_mode_click_flow_opens_test_mode_screen() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()

    assert isinstance(window._stack.currentWidget(), TitleScreen)

    window.title_screen.test_mode_button.click()
    app.processEvents()

    assert window.isVisible()
    assert isinstance(window._stack.currentWidget(), TestModeScreen)
    assert window.test_mode_controller is not None

    window.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_test_mode_screen_renders_phase_and_board_snapshot() -> None:
    app = QApplication.instance() or QApplication([])
    controller = TestModeController("first_steps")
    controller.set_runtime(
        current_loop=2,
        current_day=2,
        current_phase=GamePhase.INCIDENT.value,
    )
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="mastermind",
                area="school",
                tokens={"intrigue": 1},
                revealed=True,
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="city",
            ),
        ]
    )
    controller.rebuild_session()

    screen = TestModeScreen(controller)
    screen.show()
    app.processEvents()

    assert screen.phase_value.text() == "事件阶段"
    assert screen.character_summary_value.text() == "2/2 存活"
    assert screen.loop_input.maximum() == 3
    assert screen.day_input.maximum() == 3
    assert "已公开" in screen.board_area_texts["school"].toPlainText()
    assert "office_worker" in screen.board_area_texts["school"].toPlainText()
    assert "ai" in screen.board_area_texts["city"].toPlainText()

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_test_mode_screen_uses_dropdown_targets() -> None:
    app = QApplication.instance() or QApplication([])
    controller = TestModeController("first_steps")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="mastermind",
                area="school",
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="school",
            ),
        ]
    )
    controller.rebuild_session()

    screen = TestModeScreen(controller)
    screen.show()
    app.processEvents()

    assert len(screen.incident_target_character_inputs) == 3
    assert all(combo.count() > 0 for combo in screen.incident_target_character_inputs)

    screen.actor_input.setCurrentIndex(screen.actor_input.findData("office_worker"))
    screen.timing_input.setCurrentIndex(screen.timing_input.findData("playwright_ability"))
    screen.identity_ability_input.setCurrentIndex(
        screen.identity_ability_input.findData("mastermind_playwright_place_intrigue_character")
    )
    app.processEvents()

    enabled_targets = [combo for combo in screen.ability_target_inputs if combo.isEnabled()]
    assert len(enabled_targets) == 1
    assert enabled_targets[0].findData("ai") >= 0

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_test_mode_screen_trigger_identity_ability_keeps_previous_effects() -> None:
    app = QApplication.instance() or QApplication([])
    controller = TestModeController("first_steps")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="rumormonger",
                area="school",
            ),
            TestCharacterDraft(
                character_id="male_student",
                identity_id="rumormonger",
                area="city",
            ),
            TestCharacterDraft(
                character_id="shrine_maiden",
                identity_id="平民",
                area="school",
            ),
            TestCharacterDraft(
                character_id="teacher",
                identity_id="平民",
                area="city",
            ),
        ]
    )
    controller.rebuild_session()

    screen = TestModeScreen(controller)
    screen.show()
    app.processEvents()

    screen.actor_input.setCurrentIndex(screen.actor_input.findData("office_worker"))
    screen.timing_input.setCurrentIndex(screen.timing_input.findData("playwright_ability"))
    screen.identity_ability_input.setCurrentIndex(
        screen.identity_ability_input.findData("rumormonger_playwright_place_paranoia")
    )
    screen.ability_target_inputs[0].setCurrentIndex(
        screen.ability_target_inputs[0].findData("shrine_maiden")
    )
    screen.trigger_identity_ability_button.click()
    app.processEvents()

    assert controller.session is not None
    assert controller.session.state.characters["shrine_maiden"].tokens.paranoia == 1

    screen.actor_input.setCurrentIndex(screen.actor_input.findData("male_student"))
    screen.identity_ability_input.setCurrentIndex(
        screen.identity_ability_input.findData("rumormonger_playwright_place_paranoia")
    )
    screen.ability_target_inputs[0].setCurrentIndex(
        screen.ability_target_inputs[0].findData("teacher")
    )
    screen.trigger_identity_ability_button.click()
    app.processEvents()

    assert controller.session.state.characters["shrine_maiden"].tokens.paranoia == 1
    assert controller.session.state.characters["teacher"].tokens.paranoia == 1

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_test_mode_screen_can_execute_and_advance_phase() -> None:
    app = QApplication.instance() or QApplication([])
    controller = TestModeController("first_steps")
    controller.set_runtime(
        current_loop=1,
        current_day=1,
        current_phase=GamePhase.LEADER_ROTATE.value,
    )
    controller.rebuild_session()

    screen = TestModeScreen(controller)
    screen.show()
    app.processEvents()

    screen.execute_phase_button.click()
    app.processEvents()

    assert controller.session is not None
    assert controller.session.state.leader_index == 1
    assert "执行完成" in screen.status_value.text()

    screen.advance_phase_button.click()
    app.processEvents()

    assert screen.phase_value.text() == "回合结束阶段"

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_test_mode_screen_can_apply_rules_and_rebuild_session() -> None:
    app = QApplication.instance() or QApplication([])
    controller = TestModeController("first_steps")
    screen = TestModeScreen(controller)
    screen.show()
    app.processEvents()

    screen.rule_y_input.setCurrentIndex(screen.rule_y_input.findData("fs_murder_plan"))
    screen.rule_x_inputs[0].setCurrentIndex(screen.rule_x_inputs[0].findData("fs_ripper_shadow"))
    screen.apply_rules_button.click()
    app.processEvents()

    assert controller.session is not None
    assert controller.session.state.script.rule_y is not None
    assert controller.session.state.script.rule_y.rule_id == "fs_murder_plan"
    assert [rule.rule_id for rule in controller.session.state.script.rules_x] == ["fs_ripper_shadow"]
    assert "规则已更新并重建调试局" in screen.status_value.text()

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_test_mode_screen_shows_triggered_failure_condition(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    controller = TestModeController("basic_tragedy_x")
    controller.set_runtime(
        current_loop=1,
        current_day=1,
        current_phase=GamePhase.LOOP_END.value,
    )
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="friend",
                identity_id="friend",
                area="school",
                is_alive=False,
            ),
        ]
    )
    controller.rebuild_session()

    from ui.screens import test_mode_screen as test_mode_screen_module

    monkeypatch.setattr(
        test_mode_screen_module.QMessageBox,
        "information",
        lambda *_args, **_kwargs: 0,
    )

    screen = TestModeScreen(controller)
    screen.show()
    app.processEvents()

    screen.execute_phase_button.click()
    app.processEvents()

    assert screen.protagonist_dead_value.text() == "否"
    assert screen.failure_state_value.text() == "已触发"
    assert screen.failure_flags_value.text() == "friend_dead"
    assert "触发失败条件：friend_dead" in screen.status_value.text()

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_game_screen_shows_identity_revealed_popup_once(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    session = GameSessionController()
    session.view_state.revealed_identity_messages.append("男学生的身份是主谋")

    from ui.screens import game_screen as game_screen_module

    popup_calls: list[tuple[str, str]] = []

    def _fake_information(_parent, title: str, text: str) -> int:
        popup_calls.append((title, text))
        return 0

    monkeypatch.setattr(game_screen_module.QMessageBox, "information", _fake_information)

    screen = GameScreen(session)
    screen.show()
    app.processEvents()

    assert popup_calls == [("身份公开", "男学生的身份是主谋")]

    screen.refresh()
    app.processEvents()

    assert popup_calls == [("身份公开", "男学生的身份是主谋")]

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_test_mode_screen_shows_identity_revealed_popup_once(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    controller = TestModeController("first_steps")
    assert controller.session is not None
    controller.session.event_bus.emit(GameEvent(
        GameEventType.IDENTITY_REVEALED,
        {"character_id": "male_student", "identity_id": "mastermind"},
    ))

    from ui.screens import test_mode_screen as test_mode_screen_module

    popup_calls: list[tuple[str, str]] = []

    def _fake_information(_parent, title: str, text: str) -> int:
        popup_calls.append((title, text))
        return 0

    monkeypatch.setattr(test_mode_screen_module.QMessageBox, "information", _fake_information)

    screen = TestModeScreen(controller)
    screen.show()
    app.processEvents()

    assert popup_calls == [("身份公开", "男子学生的身份是主谋")]

    screen.refresh()
    app.processEvents()

    assert popup_calls == [("身份公开", "男子学生的身份是主谋")]

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_new_game_screen_rule_dropdowns_show_full_btx_options_and_allow_reselect() -> None:
    app = QApplication.instance() or QApplication([])
    screen = NewGameScreen()
    screen.show()

    screen.module_input.setCurrentIndex(screen.module_input.findData("basic_tragedy_x"))
    app.processEvents()

    rule_y_values = [
        screen.rule_y_input.itemData(index)
        for index in range(screen.rule_y_input.count())
    ]
    assert rule_y_values == [
        "btx_murder_plan",
        "btx_cursed_contract",
        "btx_sealed_evil",
        "btx_change_future",
        "btx_giant_time_bomb_x",
    ]

    first_rule_x_values = [
        screen._rule_x_inputs[0].itemData(index)
        for index in range(screen._rule_x_inputs[0].count())
    ]
    assert first_rule_x_values == [
        "btx_friends_circle",
        "btx_love_scenic_line",
        "btx_rumors",
        "btx_latent_serial_killer",
        "btx_causal_line",
        "btx_delusion_spread_virus",
        "btx_unknown_factor_chi",
    ]

    screen.rule_y_input.setCurrentIndex(screen.rule_y_input.findData("btx_change_future"))
    app.processEvents()
    assert screen.model.draft.rule_y_id == "btx_change_future"

    screen.rule_y_input.setCurrentIndex(screen.rule_y_input.findData("btx_murder_plan"))
    app.processEvents()
    assert screen.model.draft.rule_y_id == "btx_murder_plan"

    screen._rule_x_inputs[0].setCurrentIndex(screen._rule_x_inputs[0].findData("btx_unknown_factor_chi"))
    screen._rule_x_inputs[1].setCurrentIndex(screen._rule_x_inputs[1].findData("btx_love_scenic_line"))
    app.processEvents()
    assert screen.model.draft.rule_x_ids == [
        "btx_unknown_factor_chi",
        "btx_love_scenic_line",
    ]

    screen._rule_x_inputs[0].setCurrentIndex(screen._rule_x_inputs[0].findData("btx_friends_circle"))
    app.processEvents()
    assert screen.model.draft.rule_x_ids[0] == "btx_friends_circle"

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_new_game_screen_character_buttons_update_visible_state() -> None:
    app = QApplication.instance() or QApplication([])
    screen = NewGameScreen()
    screen.show()

    assert len(screen._character_inputs) == 5
    assert screen.character_count_label.text() == "当前 5 名角色"

    screen.add_character_button.click()
    app.processEvents()

    assert len(screen._character_inputs) == 6
    assert screen.character_count_label.text() == "当前 6 名角色"

    screen.remove_character_button.click()
    app.processEvents()

    assert len(screen._character_inputs) == 5
    assert screen.character_count_label.text() == "当前 5 名角色"

    screen.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PySide6 is not installed")
def test_new_game_screen_day_count_changes_rebuild_incident_rows() -> None:
    app = QApplication.instance() or QApplication([])
    screen = NewGameScreen()
    screen.show()

    assert len(screen._incident_inputs) == 3

    screen.day_input.setValue(1)
    app.processEvents()

    assert len(screen._incident_inputs) == 1
    assert screen.model.draft.days_per_loop == 1

    screen.day_input.setValue(3)
    app.processEvents()

    assert len(screen._incident_inputs) == 3
    assert screen.model.draft.days_per_loop == 3

    screen.close()
    app.processEvents()
