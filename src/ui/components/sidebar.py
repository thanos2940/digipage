from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QScrollArea, QGroupBox
from PySide6.QtCore import Qt, Signal
from ...core.theme import MODERN_THEME
from .stats_card import StatsCardWidget
from .book_list_item import BookListItemWidget

class Sidebar(QWidget):
    create_book_requested = Signal(str)
    transfer_all_requested = Signal()
    open_log_requested = Signal()
    open_settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 20, 15, 20)
        layout.setSpacing(20)

        # --- Stats Section ---
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)

        # We'll use a vertical stack for stats to save width or grid
        # Actually, horizontal cards might be too squeezed. Let's do small cards.
        self.speed_card = StatsCardWidget("PAGES/MIN", "0.0", MODERN_THEME['PRIMARY'])
        self.pending_card = StatsCardWidget("PENDING", "0", MODERN_THEME['WARNING'])
        # Total is maybe less critical for the top view, can go below

        stats_layout.addWidget(self.speed_card)
        stats_layout.addWidget(self.pending_card)
        layout.addLayout(stats_layout)

        self.total_card = StatsCardWidget("TOTAL TODAY", "0", MODERN_THEME['SUCCESS'])
        self.total_card.setFixedHeight(70) # Slightly smaller
        layout.addWidget(self.total_card)

        # --- Book Creation ---
        create_group = QGroupBox("NEW BOOK")
        create_layout = QVBoxLayout(create_group)

        self.book_name_input = QLineEdit()
        self.book_name_input.setPlaceholderText("Scan QR or enter name...")

        self.create_btn = QPushButton("Create Book")
        self.create_btn.setProperty("class", "primary")
        self.create_btn.clicked.connect(self._on_create_clicked)

        create_layout.addWidget(self.book_name_input)
        create_layout.addWidget(self.create_btn)
        layout.addWidget(create_group)

        # --- Today's Books List ---
        list_group = QGroupBox("TODAY'S BOOKS")
        list_layout = QVBoxLayout(list_group)
        list_layout.setContentsMargins(0, 10, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.book_list_container = QWidget()
        self.book_list_layout = QVBoxLayout(self.book_list_container)
        self.book_list_layout.setAlignment(Qt.AlignTop)
        self.book_list_layout.setSpacing(0)
        self.book_list_layout.setContentsMargins(0,0,0,0)

        scroll.setWidget(self.book_list_container)
        list_layout.addWidget(scroll)
        layout.addWidget(list_group)

        # --- Actions ---
        action_layout = QVBoxLayout()
        self.transfer_btn = QPushButton("Transfer All to Data")
        self.transfer_btn.setProperty("class", "success") # Green button? Or just standard.
        self.transfer_btn.clicked.connect(self.transfer_all_requested.emit)

        self.log_btn = QPushButton("View Logs")
        self.log_btn.clicked.connect(self.open_log_requested.emit)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self.open_settings_requested.emit)

        action_layout.addWidget(self.transfer_btn)
        action_layout.addWidget(self.log_btn)
        action_layout.addWidget(self.settings_btn)

        layout.addLayout(action_layout)

    def _on_create_clicked(self):
        name = self.book_name_input.text().strip()
        if name:
            self.create_book_requested.emit(name)

    def update_stats(self, speed, pending, total):
        self.speed_card.set_value(speed)
        self.pending_card.set_value(pending)
        self.total_card.set_value(total)

    def update_book_list(self, books_data):
        # Clear list
        while self.book_list_layout.count():
            child = self.book_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for book in books_data:
            item = BookListItemWidget(book['name'], book['status'], book['pages'])
            self.book_list_layout.addWidget(item)
