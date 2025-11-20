from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt

class StatsCardWidget(QWidget):
    def __init__(self, title, initial_value, color, theme, parent=None):
        super().__init__(parent)
        self.setObjectName("StatsCard")
        # Make the card compact and prevent vertical stretching
        self.setFixedHeight(85)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setStyleSheet(f"""
            #StatsCard {{
                background-color: {theme['SURFACE_CONTAINER']};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        # Symmetrical and reduced margins for a tighter look
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(2)

        self.value_label = QLabel(initial_value)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet(f"""
            font-size: 20pt;
            font-weight: bold;
            color: {color};
            background-color: transparent;
        """)

        self.title_label = QLabel(title.upper())
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True) # Ensure text wraps
        self.title_label.setStyleSheet(f"""
            font-size: 7pt;
            font-weight: bold;
            color: {theme['ON_SURFACE_VARIANT']};
            background-color: transparent;
        """)

        # Add stretches to vertically center the content
        layout.addStretch()
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)
        layout.addStretch()

    def set_value(self, value_text):
        self.value_label.setText(str(value_text))
