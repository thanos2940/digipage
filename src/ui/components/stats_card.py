from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from ...core.theme import MODERN_THEME

class StatsCardWidget(QFrame):
    def __init__(self, title, value, color, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedHeight(90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(5)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"font-size: 24pt; font-weight: 800; color: {color};")
        self.value_label.setAlignment(Qt.AlignLeft)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("H3")
        self.title_label.setStyleSheet(f"color: {MODERN_THEME['TEXT_SECONDARY']}; font-size: 8pt;")

        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)

    def set_value(self, value):
        self.value_label.setText(str(value))
