from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal, Slot
from core.config_service import ConfigService

class BottomBar(QFrame):
    prev_clicked = Signal()
    next_clicked = Signal()
    jump_end_clicked = Signal()
    refresh_clicked = Signal()
    delete_clicked = Signal()
    replace_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_service = ConfigService()
        self.setObjectName("BottomBar")
        self.setMinimumHeight(60)
        self.setup_ui()
        self._replace_mode = False

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(15)

        self.status_label = QLabel("Pages 0-0 of 0")

        self.prev_btn = QPushButton("◀ Prev")
        self.next_btn = QPushButton("Next ▶")
        self.jump_end_btn = QPushButton("Jump to End")
        self.refresh_btn = QPushButton("⟳ Refresh")

        for btn in [self.prev_btn, self.next_btn, self.jump_end_btn, self.refresh_btn]:
             btn.setMinimumHeight(40)

        self.prev_btn.setProperty("class", "filled")
        self.next_btn.setProperty("class", "filled")

        self.replace_btn = QPushButton("🔁 Replace")
        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setProperty("class", "destructive filled")
        self.delete_btn.setMinimumHeight(40)
        self.replace_btn.setMinimumHeight(40)

        self.prev_btn.clicked.connect(self.prev_clicked.emit)
        self.next_btn.clicked.connect(self.next_clicked.emit)
        self.jump_end_btn.clicked.connect(self.jump_end_clicked.emit)
        self.refresh_btn.clicked.connect(self.refresh_clicked.emit)
        self.delete_btn.clicked.connect(self.delete_clicked.emit)
        self.replace_btn.clicked.connect(self.replace_clicked.emit)

        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.next_btn)
        layout.addWidget(self.jump_end_btn)
        layout.addWidget(self.refresh_btn)
        layout.addStretch()
        layout.addWidget(self.replace_btn)
        layout.addWidget(self.delete_btn)

    def update_status(self, text):
        self.status_label.setText(text)

    def set_replace_mode(self, active):
        self._replace_mode = active
        if active:
            self.replace_btn.setText("Cancel Replace")
            self.replace_btn.setProperty("class", "destructive filled")
        else:
            self.replace_btn.setText("Replace")
            self.replace_btn.setProperty("class", "")

        self.replace_btn.style().unpolish(self.replace_btn)
        self.replace_btn.style().polish(self.replace_btn)
