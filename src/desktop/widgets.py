from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class MetricCard(QFrame):
    def __init__(self, label: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)

        label_widget = QLabel(label)
        label_widget.setObjectName("metricLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("metricValue")
        value_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout.addWidget(label_widget)
        layout.addWidget(value_widget)


class ContentCard(QFrame):
    def __init__(
        self,
        title: str,
        body: str,
        *,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("contentCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        title_widget = QLabel(title)
        title_widget.setStyleSheet("font-weight: 600;")
        body_widget = QLabel(body)
        body_widget.setObjectName("mutedText")
        body_widget.setWordWrap(True)
        body_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout.addWidget(title_widget)
        layout.addWidget(body_widget)
