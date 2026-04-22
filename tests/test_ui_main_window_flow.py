from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from ui.screens.game_screen import GameScreen
    from ui.screens.new_game_screen import NewGameScreen
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

