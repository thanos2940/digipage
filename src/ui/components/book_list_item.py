from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from ...core.theme import MODERN_THEME

class BookListItemWidget(QFrame):
    def __init__(self, name, status, pages, parent=None):
        super().__init__(parent)
        self.setObjectName("BookItem")
        # Transparent background for list items usually, but let's make it subtle
        self.setStyleSheet(f"""
            #BookItem {{
                background-color: transparent;
                border-bottom: 1px solid {MODERN_THEME['BORDER']};
            }}
        """)
        self.setFixedHeight(45)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        # Book Name
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(f"font-weight: 600; color: {MODERN_THEME['TEXT_MAIN']};")

        # Status Badge
        self.status_label = QLabel(status)
        status_bg = MODERN_THEME['SUCCESS'] if status == "DATA" else MODERN_THEME['WARNING']
        status_text = "#000000" if status == "DATA" else "#000000" # Dark text for contrast on bright badges

        self.status_label.setStyleSheet(f"""
            background-color: {status_bg};
            color: {status_text};
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 8pt;
            font-weight: 700;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)

        # Page Count
        self.pages_label = QLabel(f"{pages} p.")
        self.pages_label.setStyleSheet(f"color: {MODERN_THEME['TEXT_SECONDARY']}; font-size: 9pt;")
        self.pages_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self.name_label, 1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.pages_label)
