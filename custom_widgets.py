# In custom_widgets.py

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import QEvent, Qt

# This class is now a simple, styled Frame. The hover logic has been removed.
class HoverAwareToolbar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

# A custom widget for displaying book information in a structured, table-like row.
class BookListItemWidget(QWidget):
#... (the rest of the file remains the same)
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
        pages_label = QLabel(str(pages))
        
        status_label.setFixedWidth(100)
        pages_label.setFixedWidth(50)
        
        layout.addWidget(name_label, 1) # Name takes up available space
        layout.addWidget(status_label)
        layout.addWidget(pages_label)