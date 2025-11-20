from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from core.config_service import ConfigService
from core.constants import THEMES

class StatsCardWidget(QWidget):
    def __init__(self, title, initial_value, color, theme, parent=None):
        super().__init__(parent)
        self.setObjectName("StatsCard")
        self.setFixedHeight(85)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(f"#StatsCard {{ background-color: {theme['SURFACE_CONTAINER']}; border-radius: 12px; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(2)

        self.value_label = QLabel(initial_value)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet(f"font-size: 20pt; font-weight: bold; color: {color}; background-color: transparent;")

        self.title_label = QLabel(title.upper())
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(f"font-size: 7pt; font-weight: bold; color: {theme['ON_SURFACE_VARIANT']}; background-color: transparent;")

        layout.addStretch()
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)
        layout.addStretch()

    def set_value(self, value_text):
        self.value_label.setText(str(value_text))

class Sidebar(QWidget):
    create_book_requested = Signal(str)
    transfer_all_requested = Signal()
    view_log_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_service = ConfigService()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Stats
        self.stats_group = QGroupBox("Στατιστικά Απόδοσης")
        stats_layout = QVBoxLayout(self.stats_group)
        cards_widget = QWidget()
        cards_layout = QHBoxLayout(cards_widget)
        cards_layout.setContentsMargins(0,0,0,0)
        cards_layout.setSpacing(10)

        theme = self.get_theme()
        self.speed_card = StatsCardWidget("ΣΕΛ./ΛΕΠΤΟ", "0.0", theme['PRIMARY'], theme)
        self.pending_card = StatsCardWidget("ΕΚΚΡΕΜΕΙ", "0", theme['WARNING'], theme)
        self.total_card = StatsCardWidget("ΣΥΝΟΛΟ ΣΗΜΕΡΑ", "0", theme['SUCCESS'], theme)

        cards_layout.addWidget(self.speed_card)
        cards_layout.addWidget(self.pending_card)
        cards_layout.addWidget(self.total_card)
        stats_layout.addWidget(cards_widget)
        layout.addWidget(self.stats_group)

        # Book Creation
        book_group = QGroupBox("Δημιουργία Βιβλίου")
        book_layout = QVBoxLayout()
        self.book_name_edit = QLineEdit()
        self.book_name_edit.setPlaceholderText("Εισαγωγή ονόματος βιβλίου (από QR code)...")
        create_btn = QPushButton("Δημιουργία Βιβλίου")
        create_btn.setProperty("class", "filled")
        create_btn.clicked.connect(self.on_create_book_clicked)
        book_layout.addWidget(self.book_name_edit)
        book_layout.addWidget(create_btn)
        book_group.setLayout(book_layout)
        layout.addWidget(book_group)

        # Today's Books
        today_group = QGroupBox("Σημερινά Βιβλία")
        today_layout = QVBoxLayout(today_group)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.books_list_widget = QWidget()
        self.books_list_layout = QVBoxLayout(self.books_list_widget)
        self.books_list_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.books_list_widget)

        self.transfer_btn = QPushButton("Μεταφορά Όλων στα Δεδομένα")
        self.transfer_btn.setProperty("class", "filled")
        self.transfer_btn.clicked.connect(self.transfer_all_requested.emit)

        self.log_btn = QPushButton("📖 Προβολή Αρχείου Καταγραφής")
        self.log_btn.clicked.connect(self.view_log_requested.emit)

        today_layout.addWidget(self.scroll_area)
        today_layout.addWidget(self.transfer_btn)
        today_layout.addWidget(self.log_btn)
        layout.addWidget(today_group)

        layout.addStretch()

        settings_btn = QPushButton("Ρυθμίσεις")
        settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(settings_btn)

    def get_theme(self):
        name = self.config_service.get("theme", "Material Dark")
        return THEMES.get(name, THEMES["Material Dark"])

    def on_create_book_clicked(self):
        name = self.book_name_edit.text().strip()
        if name:
            self.create_book_requested.emit(name)

    def update_stats(self, speed, pending, total):
        self.speed_card.set_value(speed)
        self.pending_card.set_value(pending)
        self.total_card.set_value(total)

    def clear_book_list(self):
        # Clear logic
        for i in reversed(range(self.books_list_layout.count())):
            self.books_list_layout.itemAt(i).widget().setParent(None)

    def add_book_to_list(self, widget):
        self.books_list_layout.addWidget(widget)
