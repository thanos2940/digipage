from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QHBoxLayout
from PySide6.QtCore import Qt
from digipage.core.config import lighten_color

class StatsCardWidget(QWidget):
    """Displays a single statistic in a styled card."""
    def __init__(self, title: str, initial_value: str, color: str, theme: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("StatsCard")
        self.setFixedHeight(85)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setStyleSheet(f"""
            #StatsCard {{
                background-color: {theme['SURFACE_CONTAINER']};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
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
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(f"""
            font-size: 7pt;
            font-weight: bold;
            color: {theme['ON_SURFACE_VARIANT']};
            background-color: transparent;
        """)
        
        layout.addStretch()
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)
        layout.addStretch()

    def set_value(self, value_text):
        self.value_label.setText(str(value_text))

class BookListItemWidget(QWidget):
    """Row displaying book info in the sidebar."""
    def __init__(self, name, status, pages, theme, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(50)
        self.setStyleSheet(f"border-bottom: 1px solid {theme['OUTLINE']};")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)

        name_label = QLabel(name)
        status_label = QLabel(status)
        pages_label = QLabel(f"{pages} σελ.")

        name_label.setStyleSheet(f"border:none; color:{theme['ON_SURFACE']}; font-weight:bold;")
        
        # Status Pill Styling
        status_color = theme['SUCCESS'] if status == "DATA" else theme['WARNING']
        # Quick hex to rgba approximation
        c = status_color.lstrip('#')
        rgb = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
        bg_color = f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 40)"

        status_label.setStyleSheet(f"""
            border: none; color: {status_color}; background-color: {bg_color};
            padding: 4px 10px; border-radius: 11px; font-weight: bold; font-size: 8pt;
        """)
        status_label.setAlignment(Qt.AlignCenter)

        page_color = lighten_color(theme['PRIMARY'], 0.2)
        pages_label.setStyleSheet(f"border:none; font-weight:bold; color:{page_color}; font-size:11pt;")
        pages_label.setAlignment(Qt.AlignRight)

        layout.addWidget(name_label, 1)
        layout.addStretch(1)
        layout.addWidget(status_label)
        layout.addWidget(pages_label)