from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PySide6.QtCore import Signal, Qt

class ToolbarPanel(QFrame):
    """
    The persistent bottom toolbar containing navigation and action buttons.
    """
    nav_prev = Signal()
    nav_next = Signal()
    nav_end = Signal()
    refresh = Signal()
    delete = Signal()
    replace = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BottomBar")
        self.setMinimumHeight(60)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        
        # Status Label
        self.lbl_status = QLabel("Ready")
        layout.addWidget(self.lbl_status)
        
        layout.addStretch()
        
        # Navigation
        self.btn_prev = self._create_btn("◀ Prev", self.nav_prev)
        self.btn_next = self._create_btn("Next ▶", self.nav_next)
        self.btn_end = self._create_btn("End", self.nav_end)
        
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_end)
        
        layout.addSpacing(20)
        
        # Actions
        self.btn_refresh = self._create_btn("⟳", self.refresh)
        layout.addWidget(self.btn_refresh)
        
        layout.addStretch()
        
        # Critical Actions
        self.btn_replace = self._create_btn("Replace", self.replace)
        self.btn_delete = self._create_btn("Delete", self.delete)
        self.btn_delete.setProperty("class", "destructive filled")
        
        layout.addWidget(self.btn_replace)
        layout.addWidget(self.btn_delete)

    def _create_btn(self, text, signal):
        btn = QPushButton(text)
        btn.setMinimumHeight(40)
        btn.clicked.connect(signal.emit)
        return btn

    def set_status(self, text):
        self.lbl_status.setText(text)

    def set_nav_enabled(self, has_prev, has_next):
        self.btn_prev.setEnabled(has_prev)
        self.btn_next.setEnabled(has_next)