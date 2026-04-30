from __future__ import annotations

try:  # pragma: no cover - optional UI dependency
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    QDialog = object  # type: ignore[misc,assignment]
else:
    class StepChoiceDialog(QDialog):
        """居中的单步选择弹框，可由上层串成多步流程。"""

        def __init__(
            self,
            *,
            title: str,
            prompt: str,
            options: list[tuple[str, str]],
            summary_lines: list[str] | None = None,
            allow_back: bool = False,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._selected_value = ""
            self.back_requested = False
            self.setWindowTitle(title)
            self.setModal(True)
            self.resize(440, 360)

            layout = QVBoxLayout(self)

            self.prompt_label = QLabel(prompt)
            self.prompt_label.setWordWrap(True)
            layout.addWidget(self.prompt_label)

            self.summary_text = QTextEdit()
            self.summary_text.setReadOnly(True)
            self.summary_text.setMinimumHeight(84)
            summary = "\n".join(summary_lines or [])
            self.summary_text.setPlainText(summary or "尚未选择")
            self.summary_text.setVisible(bool(summary_lines))
            layout.addWidget(self.summary_text)

            self.options_list = QListWidget()
            for value, label in options:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, value)
                self.options_list.addItem(item)
            if self.options_list.count() > 0:
                self.options_list.setCurrentRow(0)
            self.options_list.itemDoubleClicked.connect(lambda _item: self._accept_selected())
            layout.addWidget(self.options_list)

            button_row = QHBoxLayout()
            button_row.addStretch(1)
            self.back_button = QPushButton("上一步")
            self.back_button.setVisible(allow_back)
            self.back_button.clicked.connect(self._go_back)
            button_row.addWidget(self.back_button)
            self.cancel_button = QPushButton("取消")
            self.cancel_button.clicked.connect(self.reject)
            button_row.addWidget(self.cancel_button)
            self.confirm_button = QPushButton("确认")
            self.confirm_button.clicked.connect(self._accept_selected)
            button_row.addWidget(self.confirm_button)
            layout.addLayout(button_row)

        def selected_value(self) -> str:
            return self._selected_value

        def _go_back(self) -> None:
            self.back_requested = True
            self.reject()

        def _accept_selected(self) -> None:
            current = self.options_list.currentItem()
            if current is None:
                return
            value = current.data(Qt.ItemDataRole.UserRole)
            self._selected_value = str(value) if value is not None else current.text()
            self.accept()
