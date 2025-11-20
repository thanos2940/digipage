from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from ...core.theme import MODERN_THEME

class ControlBar(QFrame):
    """
    A floating-style bottom bar for main navigation and actions.
    """
    prev_clicked = Signal()
    next_clicked = Signal()
    jump_end_clicked = Signal()
    refresh_clicked = Signal()
    replace_clicked = Signal()
    delete_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card") # Re-use card style for background
        self.setFixedHeight(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(15)

        # Status Label (Left)
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {MODERN_THEME['TEXT_SECONDARY']}; font-weight: 600;")

        # Center Controls (Nav)
        self.prev_btn = QPushButton("◄ Prev")
        self.prev_btn.clicked.connect(self.prev_clicked.emit)

        self.next_btn = QPushButton("Next ►")
        self.next_btn.setProperty("class", "primary")
        self.next_btn.clicked.connect(self.next_clicked.emit)

        self.jump_btn = QPushButton("Jump to End")
        self.jump_btn.clicked.connect(self.jump_end_clicked.emit)

        # Right Controls (Actions)
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setFixedWidth(40)
        self.refresh_btn.setToolTip("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_clicked.emit)

        self.replace_btn = QPushButton("Replace")
        self.replace_btn.setToolTip("Replace current image(s) with next scan")
        self.replace_btn.clicked.connect(self.replace_clicked.emit)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setProperty("class", "danger")
        self.delete_btn.clicked.connect(self.delete_clicked.emit)

        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.next_btn)
        layout.addWidget(self.jump_btn)
        layout.addStretch()
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.replace_btn)
        layout.addWidget(self.delete_btn)

    def set_status(self, text):
        self.status_label.setText(text)

    def set_replace_active(self, active):
        if active:
            self.replace_btn.setText("Cancel Replace")
            self.replace_btn.setProperty("class", "danger")
        else:
            self.replace_btn.setText("Replace")
            self.replace_btn.setProperty("class", "")
        self.replace_btn.style().unpolish(self.replace_btn)
        self.replace_btn.style().polish(self.replace_btn)
