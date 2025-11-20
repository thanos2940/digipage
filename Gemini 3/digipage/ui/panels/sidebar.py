from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QLineEdit, QPushButton, QScrollArea, QDockWidget
from PySide6.QtCore import Qt, Signal
from digipage.ui.widgets.cards import StatsCardWidget, BookListItemWidget
from digipage.core.config import AppConfig, THEMES

class SidebarPanel(QWidget):
    """
    The right-hand sidebar containing statistics, book creation, and the list of today's books.
    """
    create_book_requested = Signal(str)
    transfer_requested = Signal()
    open_settings_requested = Signal()
    open_log_requested = Signal()

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.theme_data = THEMES.get(config.theme, THEMES["Material Dark"])
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 1. Stats
        self.stats_group = self._init_stats_ui()
        layout.addWidget(self.stats_group)
        
        # 2. Book Creation
        self.book_group = self._init_book_ui()
        layout.addWidget(self.book_group)
        
        # 3. Today's Books
        self.list_group = self._init_list_ui()
        layout.addWidget(self.list_group)
        
        # 4. Settings Button
        self.settings_btn = QPushButton("Ρυθμίσεις")
        self.settings_btn.clicked.connect(self.open_settings_requested.emit)
        layout.addStretch()
        layout.addWidget(self.settings_btn)

    def _init_stats_ui(self):
        group = QGroupBox("Στατιστικά Απόδοσης")
        layout = QVBoxLayout()
        
        # Cards
        self.card_speed = StatsCardWidget("ΣΕΛ./ΛΕΠΤΟ", "0.0", self.theme_data['PRIMARY'], self.theme_data)
        self.card_pending = StatsCardWidget("ΕΚΚΡΕΜΕΙ", "0", self.theme_data['WARNING'], self.theme_data)
        self.card_total = StatsCardWidget("ΣΥΝΟΛΟ", "0", self.theme_data['SUCCESS'], self.theme_data)
        
        # Layout horizontally
        h_layout = QVBoxLayout() # Or HBox if width permits
        h_layout.addWidget(self.card_speed)
        h_layout.addWidget(self.card_pending)
        h_layout.addWidget(self.card_total)
        
        layout.addLayout(h_layout)
        group.setLayout(layout)
        return group

    def _init_book_ui(self):
        group = QGroupBox("Δημιουργία Βιβλίου")
        layout = QVBoxLayout()
        
        self.book_name_input = QLineEdit()
        self.book_name_input.setPlaceholderText("Scan QR Code...")
        
        btn = QPushButton("Δημιουργία")
        btn.setProperty("class", "filled")
        btn.clicked.connect(lambda: self.create_book_requested.emit(self.book_name_input.text()))
        
        layout.addWidget(self.book_name_input)
        layout.addWidget(btn)
        group.setLayout(layout)
        return group

    def _init_list_ui(self):
        group = QGroupBox("Σημερινά Βιβλία")
        layout = QVBoxLayout()
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        self.book_list_container = QWidget()
        self.book_list_layout = QVBoxLayout(self.book_list_container)
        self.book_list_layout.setAlignment(Qt.AlignTop)
        self.book_list_layout.setSpacing(0)
        self.book_list_layout.setContentsMargins(0,0,0,0)
        scroll.setWidget(self.book_list_container)
        
        trans_btn = QPushButton("Μεταφορά στα Δεδομένα")
        trans_btn.setProperty("class", "filled")
        trans_btn.clicked.connect(self.transfer_requested.emit)
        
        log_btn = QPushButton("Ιστορικό")
        log_btn.clicked.connect(self.open_log_requested.emit)
        
        layout.addWidget(scroll)
        layout.addWidget(trans_btn)
        layout.addWidget(log_btn)
        group.setLayout(layout)
        return group

    def update_stats(self, speed: str, pending: int, total: int):
        self.card_speed.set_value(speed)
        self.card_pending.set_value(str(pending))
        self.card_total.set_value(str(total))

    def clear_book_list(self):
        # Clear existing items
        while self.book_list_layout.count():
            child = self.book_list_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

    def add_book_item(self, name, status, pages):
        item = BookListItemWidget(name, status, pages, self.theme_data)
        self.book_list_layout.addWidget(item)