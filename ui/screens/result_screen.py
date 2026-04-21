from __future__ import annotations

from engine.display_names import outcome_name

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
    class ResultScreen(QWidget):
        """结算页面。"""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("对局结算"))
            self.result_label = QLabel("-")
            layout.addWidget(self.result_label)
            self.back_button = QPushButton("返回主菜单")
            layout.addWidget(self.back_button)

        def set_result(self, outcome: str) -> None:
            self.result_label.setText(outcome_name(outcome))
