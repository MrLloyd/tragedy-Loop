from __future__ import annotations

import traceback
from typing import Optional

from engine.game_controller import GameController
from ui.controllers.game_session_controller import GameSessionController
from ui.debug_snapshot_server import ReadOnlyDebugSnapshotServer
from ui.screens.game_screen import GameScreen
from ui.screens.new_game_screen import NewGameScreen, NewGameScreenModel
from ui.screens.result_screen import ResultScreen
from ui.screens.title_screen import TitleScreen

try:  # pragma: no cover - integration wiring
    from PySide6.QtWidgets import (
        QMainWindow,
        QMessageBox,
        QStackedWidget,
        QWidget,
    )
except Exception:  # pragma: no cover
    QMainWindow = object  # type: ignore[misc,assignment]
else:
    class MainWindow(QMainWindow):
        """Phase 6 最小 UI 闭环主窗口。"""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("惨剧轮回")
            self.resize(1200, 900)

            self._stack = QStackedWidget(self)
            self.setCentralWidget(self._stack)

            self.title_screen = TitleScreen(self)
            self.result_screen = ResultScreen(self)
            self.game_screen = GameScreen(parent=self)

            self._stack.addWidget(self.title_screen)
            self._stack.addWidget(self.game_screen)
            self._stack.addWidget(self.result_screen)

            self.new_game_screen: Optional[NewGameScreen] = None
            self.new_game_model: Optional[NewGameScreenModel] = None
            self.session: Optional[GameSessionController] = None
            self.game_controller: Optional[GameController] = None
            self._debug_snapshot_server = ReadOnlyDebugSnapshotServer(self._read_local_debug_snapshot)
            self._debug_snapshot_server.start()

            self.title_screen.new_game_button.clicked.connect(self._start_new_game_flow)
            self.title_screen.quit_button.clicked.connect(self.close)
            self.result_screen.back_button.clicked.connect(self._show_title)
            self.game_screen.set_after_submit(self._handle_session_update)

            if self._debug_snapshot_server.is_running:
                self.statusBar().showMessage(
                    f"本地只读调试快照：{self._debug_snapshot_server.snapshot_url}"
                )
            else:
                self.statusBar().showMessage(
                    f"本地只读调试快照未启动：{self._debug_snapshot_server.start_error}"
                )
            self._show_title()

        def _show_title(self) -> None:
            self._stack.setCurrentWidget(self.title_screen)

        def _start_new_game_flow(self) -> None:
            try:
                self._start_new_game_flow_impl()
            except Exception as exc:
                self._show_unexpected_error("开始新游戏失败", exc)

        def _start_new_game_flow_impl(self) -> None:
            self.new_game_model = NewGameScreenModel()
            self.session = GameSessionController()
            self.game_controller = GameController(ui_callback=self.session)
            self.session.bind(self.game_controller)
            self.session.bind_new_game_model(self.new_game_model)

            if self.new_game_screen is not None:
                self._stack.removeWidget(self.new_game_screen)
                self.new_game_screen.deleteLater()

            self.new_game_screen = NewGameScreen(self.new_game_model, self)
            self.new_game_screen.start_button.clicked.connect(self._submit_script_setup)
            self._stack.addWidget(self.new_game_screen)
            self._stack.setCurrentWidget(self.new_game_screen)

            draft = self.new_game_model.draft
            try:
                self.game_controller.start_game(
                    draft.module_id,
                    loop_count=draft.loop_count,
                    days_per_loop=draft.days_per_loop,
                )
            except Exception as exc:
                QMessageBox.critical(self, "开局失败", str(exc))
                return

            self._refresh_new_game_screen()

        def _submit_script_setup(self) -> None:
            try:
                if self.session is None or self.new_game_model is None or self.new_game_screen is None:
                    return

                self.new_game_screen.sync_model_from_inputs()

                try:
                    self.session.submit_script_setup(self.new_game_model.build_payload())
                except Exception as exc:
                    QMessageBox.warning(self, "提交失败", str(exc))
                    self._refresh_new_game_screen()
                    return

                self._handle_session_update()
            except Exception as exc:
                self._show_unexpected_error("提交非公开信息表失败", exc)

        def _handle_session_update(self) -> None:
            if self.session is None:
                return

            wait_type = self.session.current_wait_input_type()
            if wait_type == "script_setup":
                self._refresh_new_game_screen()
                return

            if self.session.view_state.outcome is not None:
                self.result_screen.set_result(self.session.view_state.outcome.value)
                self._stack.setCurrentWidget(self.result_screen)
                return

            self.game_screen.bind_session(self.session)
            self._stack.setCurrentWidget(self.game_screen)

        def _refresh_new_game_screen(self) -> None:
            if self.new_game_screen is None:
                return
            self.new_game_screen.refresh_errors()

        def _read_local_debug_snapshot(self) -> dict[str, object]:
            if self.session is None:
                return {"status": "idle"}
            return self.session.read_debug_snapshot()

        def closeEvent(self, event) -> None:  # type: ignore[override]
            self._debug_snapshot_server.close()
            super().closeEvent(event)

        def _show_unexpected_error(self, title: str, exc: Exception) -> None:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
            QMessageBox.critical(self, title, str(exc))
