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
