from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from ...core import config

class BookListItemWidget(QWidget):
    def __init__(self, name, status, pages, theme, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(50)

        # Main layout with a subtle bottom border for separation
        self.setStyleSheet(f"""
            QWidget {{
                border-bottom: 1px solid {theme['OUTLINE']};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)

        name_label = QLabel(name)
        status_label = QLabel(status)
        pages_label = QLabel(f"{pages} σελ.")

        # --- Style Book Name ---
        name_label.setStyleSheet(f"border: none; color: {theme['ON_SURFACE']}; background-color: transparent; font-weight: bold;")

        # --- Style Status Pill ---
        status_color = theme['SUCCESS'] if status == "DATA" else theme['WARNING']
        # Convert hex to rgba for background with transparency
        rgb_color = QColor(status_color).getRgb()
        bg_color_rgba = f"rgba({rgb_color[0]}, {rgb_color[1]}, {rgb_color[2]}, 40)" # ~15% opacity

        status_stylesheet = f"""
            border: none;
            color: {status_color};
            background-color: {bg_color_rgba};
            padding: 4px 10px;
            border-radius: 11px;
            font-weight: bold;
            font-size: 8pt;
        """
        status_label.setStyleSheet(status_stylesheet)
        status_label.setAlignment(Qt.AlignCenter)

        # --- Style Page Count ---
        page_count_color = config.lighten_color(theme['PRIMARY'], 0.2)
        pages_label.setStyleSheet(f"border: none; font-weight: bold; color: {page_count_color}; font-size: 11pt; background-color: transparent;")
        pages_label.setAlignment(Qt.AlignRight)

        layout.addWidget(name_label, 1)
        layout.addStretch(1)
        layout.addWidget(status_label)
        layout.addWidget(pages_label)
