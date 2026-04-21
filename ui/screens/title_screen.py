from __future__ import annotations

try:  # pragma: no cover - PySide6 may be absent in test env
    from PySide6.QtWidgets import (
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    QWidget = object  # type: ignore[misc,assignment]
else:
    class TitleScreen(QWidget):
        """主菜单页面。"""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("惨剧轮回"))
            self.new_game_button = QPushButton("开始新游戏")
            self.quit_button = QPushButton("退出")
            layout.addWidget(self.new_game_button)
            layout.addWidget(self.quit_button)

