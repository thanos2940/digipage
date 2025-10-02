import sys
import os
import re
import time
from collections import deque
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QDockWidget, QScrollArea, QLineEdit, QGroupBox, QFormLayout,
    QFrame, QMessageBox, QDialog, QToolButton, QSpacerItem, QSizePolicy, QApplication,
    QProgressDialog, QProgressBar, QStackedWidget
)
from PySide6.QtCore import Qt, QThread, Slot, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap, QColor

import config
from image_viewer import ImageViewer, InteractionMode
from workers import ScanWorker, Watcher, ImageProcessor, natural_sort_key
from settings_dialog import SettingsDialog
from log_viewer_dialog import LogViewerDialog


# A custom widget for displaying book information in a structured, table-like row.
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


# A custom widget for displaying a single statistic in a styled card.
class StatsCardWidget(QWidget):
    def __init__(self, title, initial_value, color, theme, parent=None):
        super().__init__(parent)
        self.setObjectName("StatsCard")
        # Make the card compact and prevent vertical stretching
        self.setFixedHeight(85)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setStyleSheet(f"""
            #StatsCard {{
                background-color: {theme['SURFACE_CONTAINER']};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        # Symmetrical and reduced margins for a tighter look
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
        self.title_label.setWordWrap(True) # Ensure text wraps
        self.title_label.setStyleSheet(f"""
            font-size: 7pt;
            font-weight: bold;
            color: {theme['ON_SURFACE_VARIANT']};
            background-color: transparent;
        """)
        
        # Add stretches to vertically center the content
        layout.addStretch()
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)
        layout.addStretch()

    def set_value(self, value_text):
        self.value_label.setText(str(value_text))

class HoverAwareToolbar(QFrame):
    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self.setMouseTracking(True)

    def enterEvent(self, event):
        if self.viewer:
            self.viewer.cancel_toolbar_hide()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.viewer:
            self.viewer.leaveEvent(event)
        super().leaveEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner")
        self.app_config = config.load_config()
        self.image_files = []
        self.current_index = 0
        self.is_actively_editing = False # State to control auto-navigation
        self.replace_mode_active = False
        self.replace_candidates = []
        self._force_reload_on_next_scan = False
        self._split_op_index = None # Track index for post-split navigation
        
        self._initial_load_done = False
        
        # --- Performance Tracking ---
        self.scan_timestamps = deque(maxlen=20) # For calculating rolling speed
        self.staged_pages_count = 0
        self.data_pages_count = 0
        
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(300) 
        self.update_timer.timeout.connect(self.jump_to_end)

        self.jump_button_animation = QTimer(self)
        self.jump_button_animation.timeout.connect(self._update_jump_button_animation)
        self.jump_button_animation_step = 0

        self._layout_data = {} # To store page split coordinates

        self.setup_ui()
        self.setup_workers()
        self.connect_signals()
        
    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_load_done:
            QTimer.singleShot(100, self.initial_load)
            self._initial_load_done = True

    def open_log_viewer_dialog(self):
        dialog = LogViewerDialog(self)
        dialog.exec()

    def initial_load(self):
        if self.app_config.get("scanner_mode") == "single_split":
            self._load_layout_data()
        self.trigger_full_refresh()

    def setup_ui(self):
        # The main central widget will be a container with a vertical layout
        main_container = QWidget()
        main_v_layout = QVBoxLayout(main_container)
        main_v_layout.setSpacing(0)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(main_container)

        # Use a QStackedWidget to hold the different UI modes
        self.main_stack = QStackedWidget()

        # Create and add the different UI modes
        self.dual_scan_widget = self._setup_dual_scan_ui()
        self.single_split_widget = self._setup_single_split_ui()

        self.main_stack.addWidget(self.dual_scan_widget)
        self.main_stack.addWidget(self.single_split_widget)

        # Add the main stack to the vertical layout
        main_v_layout.addWidget(self.main_stack)

        # Create and add the persistent bottom bar
        self.create_bottom_bar(main_v_layout)

        # Create and dock the sidebar
        self.create_sidebar()

        # Select the correct UI based on config
        if self.app_config.get("scanner_mode") == "single_split":
            self.main_stack.setCurrentWidget(self.single_split_widget)
            # Adapt UI elements for single-shot mode
            self.replace_pair_btn.hide()
            self.delete_pair_btn.hide()
            self.prev_btn.setText("◀")
            self.next_btn.setText("▶")
            self.jump_end_btn.setText("Τέλος")
            self.refresh_btn.setText("⟳")
        else:
            self.main_stack.setCurrentWidget(self.dual_scan_widget)

    def _setup_dual_scan_ui(self):
        content_area = QWidget()
        main_h_layout = QHBoxLayout(content_area)
        main_h_layout.setSpacing(10)
        main_h_layout.setContentsMargins(10, 10, 10, 10)

        viewers_container = QWidget()
        viewers_layout = QHBoxLayout(viewers_container)
        viewers_layout.setSpacing(10)
        viewers_layout.setContentsMargins(0, 0, 0, 0)

        self.viewer1 = self._create_viewer_panel()
        self.viewer2 = self._create_viewer_panel()
        viewers_layout.addWidget(self.viewer1['frame'])
        viewers_layout.addWidget(self.viewer2['frame'])

        main_h_layout.addWidget(viewers_container)
        return content_area

    def _setup_single_split_ui(self):
        content_area = QWidget()
        main_h_layout = QHBoxLayout(content_area)
        main_h_layout.setSpacing(10)
        main_h_layout.setContentsMargins(10, 10, 10, 10)

        self.split_viewer_panel = self._create_viewer_panel()
        main_h_layout.addWidget(self.split_viewer_panel['frame'])

        # Customize the single viewer's toolbar for splitting
        # Hide irrelevant buttons
        self.split_viewer_panel['split'].hide()
        self.split_viewer_panel['rotate'].hide()
        self.split_viewer_panel['crop'].hide()
        self.split_viewer_panel['fix_color'].hide()
        # Rename delete button
        self.split_viewer_panel['delete'].setText("Διαγραφή Σάρωσης")
        self.split_viewer_panel['delete'].setToolTip("Διαγραφή της αρχικής σάρωσης και των τελικών σελίδων της.")
        # Rename restore button
        self.split_viewer_panel['restore'].setText("Επαναφορά Πλαισίων")
        self.split_viewer_panel['restore'].setToolTip("Επαναφορά των πλαισίων διαχωρισμού στην αρχική τους θέση.")
        # Create the main action button 'Update'
        self.update_split_btn = QPushButton("Ενημέρωση")
        self.update_split_btn.setProperty("class", "success filled")
        self.update_split_btn.setToolTip("Ενημέρωση των τελικών σελίδων με τα τρέχοντα πλαίσια.")
        self.split_viewer_panel['toolbar'].layout().insertWidget(0, self.update_split_btn)

        # Connect the new buttons for this specific mode
        self.update_split_btn.clicked.connect(self.update_single_split)
        self.split_viewer_panel['restore'].clicked.connect(self.restore_split_rects)


        return content_area

    def _create_viewer_panel(self):
        frame = QFrame()
        frame.setObjectName("ViewerFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0,0,0,0)
        
        viewer = ImageViewer()
        viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        theme_data = config.THEMES.get(self.app_config.get("theme"), config.THEMES["Material Dark"])
        primary_color = theme_data.get("PRIMARY", "#b0c6ff")
        tertiary_color = theme_data.get("TERTIARY", "#e2bada")
        viewer.set_theme_colors(primary_color, tertiary_color)
        
        layout.addWidget(viewer, 1)

        # --- Floating Toolbar (Adaptive Width) ---
        toolbar = HoverAwareToolbar(viewer, frame)
        toolbar.setObjectName("FloatingToolbar")
        toolbar.setFixedHeight(48) # Maintain consistent height
        toolbar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed) # Let layout determine width
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8,0,8,0)
        toolbar_layout.setSpacing(5)

        controls = {}
        
        # --- Create All Controls ---
        # Mode Indicator
        controls['mode_label'] = QLabel()
        controls['mode_label'].setObjectName("ModeIndicatorLabel")

        # Normal Controls
        controls['crop'] = QToolButton(); controls['crop'].setText("Περικοπή"); controls['crop'].setToolTip("Εφαρμογή Περικοπής"); controls['crop'].setObjectName("crop_button")
        controls['split'] = QToolButton(); controls['split'].setText("Διαχωρισμός"); controls['split'].setToolTip("Διαχωρισμός")
        controls['rotate'] = QToolButton(); controls['rotate'].setText("Περιστροφή"); controls['rotate'].setToolTip("Περιστροφή")
        controls['fix_color'] = QToolButton(); controls['fix_color'].setText("Χρώμα"); controls['fix_color'].setToolTip("Διόρθωση Χρώματος")
        controls['restore'] = QToolButton(); controls['restore'].setText("Επαναφορά"); controls['restore'].setToolTip("Επαναφορά")
        controls['delete'] = QToolButton(); controls['delete'].setText("Διαγραφή"); controls['delete'].setToolTip("Διαγραφή"); controls['delete'].setObjectName("delete_button")
        
        
        # Split Mode Controls
        controls['confirm_split'] = QPushButton("Επιβεβαίωση"); controls['confirm_split'].setProperty("class", "success filled")
        controls['cancel_split'] = QPushButton("Άκυρο"); controls['cancel_split'].setProperty("class", "destructive")

        # Rotate Mode Controls
        controls['cancel_rotate'] = QPushButton("Τέλος"); controls['cancel_rotate'].setProperty("class", "destructive")

        # --- Add All Controls to Layout ---
        toolbar_layout.addWidget(controls['crop'])
        toolbar_layout.addWidget(controls['mode_label'])
        toolbar_layout.addWidget(controls['confirm_split'])
        toolbar_layout.addWidget(controls['cancel_split'])
        toolbar_layout.addWidget(controls['cancel_rotate'])

        toolbar_layout.addWidget(controls['split'])
        toolbar_layout.addWidget(controls['rotate'])
        toolbar_layout.addWidget(controls['fix_color'])
        toolbar_layout.addWidget(controls['restore'])
        toolbar_layout.addWidget(controls['delete'])
        toolbar_layout.addStretch()
        
        
        viewer.set_toolbar(toolbar)

        panel_widgets = {'frame': frame, 'viewer': viewer, 'toolbar': toolbar, **controls}
        
        # Connect signals
        controls['crop'].clicked.connect(lambda: self.apply_crop(panel_widgets))
        controls['fix_color'].clicked.connect(lambda: self.apply_color_fix(panel_widgets))
        controls['split'].clicked.connect(lambda: self.toggle_split_mode(panel_widgets, True))
        controls['rotate'].clicked.connect(lambda: self.toggle_rotate_mode(panel_widgets, True))
        controls['delete'].clicked.connect(lambda: self.delete_single_image(panel_widgets))
        controls['restore'].clicked.connect(lambda: self.restore_image(panel_widgets))
        controls['confirm_split'].clicked.connect(lambda: self.apply_split(panel_widgets))
        controls['cancel_split'].clicked.connect(lambda: self.toggle_split_mode(panel_widgets, False))
        controls['cancel_rotate'].clicked.connect(lambda: self.toggle_rotate_mode(panel_widgets, False))

        # Initial state
        self.toggle_split_mode(panel_widgets, False)

        return panel_widgets

    def create_sidebar(self):
        sidebar_dock = QDockWidget("Χειριστήρια & Στατιστικά", self)
        sidebar_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        sidebar_dock.setFeatures(QDockWidget.DockWidgetMovable)
        sidebar_dock.setFixedWidth(320)

        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setSpacing(15)
        sidebar_dock.setWidget(sidebar_widget)
        
        # --- New Statistics Panel ---
        stats_group = QGroupBox("Στατιστικά Απόδοσης")
        stats_group_layout = QVBoxLayout(stats_group)
        
        stats_cards_widget = QWidget()
        stats_cards_layout = QHBoxLayout(stats_cards_widget)
        stats_cards_layout.setContentsMargins(0,0,0,0)
        stats_cards_layout.setSpacing(10)

        theme_name = self.app_config.get("theme", "Material Dark")
        theme = config.THEMES.get(theme_name, config.THEMES["Material Dark"])

        self.speed_card = StatsCardWidget("ΣΕΛ./ΛΕΠΤΟ", "0.0", theme['PRIMARY'], theme)
        self.pending_card = StatsCardWidget("ΕΚΚΡΕΜΕΙ", "0", theme['WARNING'], theme)
        self.total_card = StatsCardWidget("ΣΥΝΟΛΟ ΣΗΜΕΡΑ", "0", theme['SUCCESS'], theme)
        
        stats_cards_layout.addWidget(self.speed_card)
        stats_cards_layout.addWidget(self.pending_card)
        stats_cards_layout.addWidget(self.total_card)
        
        stats_group_layout.addWidget(stats_cards_widget)

        # --- Book Creation Panel ---
        book_group = QGroupBox("Δημιουργία Βιβλίου")
        book_layout = QVBoxLayout()
        self.book_name_edit = QLineEdit()
        self.book_name_edit.setPlaceholderText("Εισαγωγή ονόματος βιβλίου (από QR code)...")
        create_book_btn = QPushButton("Δημιουργία Βιβλίου")
        create_book_btn.setToolTip("Δημιουργία ενός νέου βιβλίου από όλες τις εικόνες που βρίσκονται στον φάκελο σάρωσης.")
        create_book_btn.setProperty("class", "filled")
        create_book_btn.clicked.connect(self.create_book)
        book_layout.addWidget(self.book_name_edit)
        book_layout.addWidget(create_book_btn)
        book_group.setLayout(book_layout)

        # --- Today's Books Panel ---
        today_group = QGroupBox("Σημερινά Βιβλία")
        today_layout = QVBoxLayout(today_group)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.books_list_widget = QWidget()
        self.books_list_layout = QVBoxLayout(self.books_list_widget)
        self.books_list_layout.setAlignment(Qt.AlignTop)
        self.books_list_layout.setSpacing(0) 
        scroll_area.setWidget(self.books_list_widget)
        
        self.transfer_all_btn = QPushButton("Μεταφορά Όλων στα Δεδομένα")
        self.transfer_all_btn.setToolTip("Μεταφορά όλων των ολοκληρωμένων βιβλίων από τον φάκελο 'Σημερινά' στο τελικό αρχείο δεδομένων.")
        self.transfer_all_btn.setProperty("class", "filled")
        self.transfer_all_btn.clicked.connect(self.transfer_all_books)
        
        self.view_log_btn = QPushButton("📖 Προβολή Αρχείου Καταγραφής")
        self.view_log_btn.setToolTip("Άνοιγμα του παραθύρου με το πλήρες ιστορικό των βιβλίων που έχουν μεταφερθεί.")
        self.view_log_btn.clicked.connect(self.open_log_viewer_dialog)

        today_layout.addWidget(scroll_area)
        today_layout.addWidget(self.transfer_all_btn)
        today_layout.addWidget(self.view_log_btn) # Προσθέστε το νέο κουμπί εδώ
        
        settings_btn = QPushButton("Ρυθμίσεις")
        settings_btn.setToolTip("Άνοιγμα του παραθύρου ρυθμίσεων της εφαρμογής.")
        settings_btn.clicked.connect(self.open_settings_dialog)

        sidebar_layout.addWidget(stats_group)
        sidebar_layout.addWidget(book_group)
        sidebar_layout.addWidget(today_group)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(settings_btn)

        self.addDockWidget(Qt.RightDockWidgetArea, sidebar_dock)


    def create_bottom_bar(self, main_layout):
        bottom_bar = QFrame()
        bottom_bar.setObjectName("BottomBar")
        bottom_bar.setMinimumHeight(60)
        bottom_bar_layout = QHBoxLayout(bottom_bar)
        bottom_bar_layout.setContentsMargins(15, 5, 15, 5)
        bottom_bar_layout.setSpacing(15)

        self.status_label = QLabel("Σελίδες 0-0 από 0")
        self.status_label.setWordWrap(True)
        
        self.prev_btn = QPushButton("◀ Προηγούμενο")
        self.prev_btn.setToolTip("Μετάβαση στο προηγούμενο ζεύγος σελίδων.")
        self.next_btn = QPushButton("Επόμενο ▶")
        self.next_btn.setToolTip("Μετάβαση στο επόμενο ζεύγος σελίδων.")
        self.jump_end_btn = QPushButton("Μετάβαση στο Τέλος")
        self.jump_end_btn.setToolTip("Μετάβαση στο τελευταίο ζεύγος σαρωμένων σελίδων.")
        self.refresh_btn = QPushButton("⟳ Ανανέωση")
        self.refresh_btn.setToolTip("Μη αυτόματη ανανέωση της λίστας των σαρωμένων εικόνων.")

        self.prev_btn.setProperty("class", "filled")
        self.next_btn.setProperty("class", "filled")
        
        self.prev_btn.setMinimumHeight(40)
        self.next_btn.setMinimumHeight(40)
        self.jump_end_btn.setMinimumHeight(40)
        self.refresh_btn.setMinimumHeight(40)

        self.prev_btn.clicked.connect(self.prev_pair)
        self.next_btn.clicked.connect(self.next_pair)
        self.jump_end_btn.clicked.connect(self.jump_to_end)
        self.refresh_btn.clicked.connect(self.trigger_full_refresh)
        
        self.delete_pair_btn = QPushButton("🗑️ Διαγραφή Ζεύγους")
        self.delete_pair_btn.setToolTip("Οριστική διαγραφή των δύο εικόνων που εμφανίζονται.")
        self.delete_pair_btn.setProperty("class", "destructive filled")
        self.delete_pair_btn.setMinimumHeight(40)
        self.delete_pair_btn.clicked.connect(self.delete_current_pair)
        
        self.replace_pair_btn = QPushButton("🔁 Αντικατάσταση Ζεύγους")
        self.replace_pair_btn.setToolTip("Αντικατάσταση του τρέχοντος ζεύγους με τις δύο επόμενες σαρωμένες εικόνες.")
        self.replace_pair_btn.setMinimumHeight(40)
        self.replace_pair_btn.clicked.connect(self.toggle_replace_mode)

        bottom_bar_layout.addWidget(self.status_label)
        bottom_bar_layout.addStretch()
        bottom_bar_layout.addWidget(self.prev_btn)
        bottom_bar_layout.addWidget(self.next_btn)
        bottom_bar_layout.addWidget(self.jump_end_btn)
        bottom_bar_layout.addWidget(self.refresh_btn)
        bottom_bar_layout.addStretch()
        bottom_bar_layout.addWidget(self.replace_pair_btn)
        bottom_bar_layout.addWidget(self.delete_pair_btn)

        main_layout.addWidget(bottom_bar)


    @Slot()
    def trigger_full_refresh(self, force_reload_viewers=False):
        """A single slot to completely refresh the application state."""
        self._force_reload_on_next_scan = force_reload_viewers
        if self.is_actively_editing:
            return
        self.scan_worker.perform_initial_scan()
        self.scan_worker.calculate_today_stats()

    def wheelEvent(self, event):
        if self.is_actively_editing: return

        if self.app_config.get("scanner_mode") == "single_split":
            if self.split_viewer_panel['viewer'].underMouse():
                if not self.split_viewer_panel['viewer'].is_zoomed:
                    if event.angleDelta().y() > 0:
                        self.prev_pair()
                    else:
                        self.next_pair()
            else: # Allow scroll outside viewer
                if event.angleDelta().y() > 0:
                    self.prev_pair()
                else:
                    self.next_pair()
        else: # dual_scan mode
            if self.viewer1['viewer'].underMouse() or self.viewer2['viewer'].underMouse():
                if not self.viewer1['viewer'].is_zoomed and not self.viewer2['viewer'].is_zoomed:
                    if event.angleDelta().y() > 0:
                        self.prev_pair()
                    else:
                        self.next_pair()
            else:
                if event.angleDelta().y() > 0:
                    self.prev_pair()
                else:
                    self.next_pair()

    def setup_workers(self):
        self.scan_worker_thread = QThread()
        self.scan_worker = ScanWorker(self.app_config)
        self.scan_worker.moveToThread(self.scan_worker_thread)
        self.scan_worker_thread.start()
        
        self.image_processor_thread = QThread()
        self.image_processor = ImageProcessor()
        self.image_processor.set_caching_enabled(self.app_config.get("caching_enabled", True))
        self.image_processor.moveToThread(self.image_processor_thread)
        self.image_processor_thread.start()
        
        scan_folder = self.app_config.get("scan_folder")
        if scan_folder and os.path.isdir(scan_folder):
            self.watcher = Watcher(scan_folder)
            self.watcher.thread.started.connect(self.watcher.run)
            self.watcher.thread.start()
        else:
            self.watcher = None

    def connect_signals(self):
        # ScanWorker signals
        self.scan_worker.initial_scan_complete.connect(self.on_initial_scan_complete)
        self.scan_worker.stats_updated.connect(self.on_stats_updated)
        self.scan_worker.error.connect(self.show_error)
        self.scan_worker.file_operation_complete.connect(self.on_file_operation_complete)
        self.scan_worker.book_creation_progress.connect(self.on_book_creation_progress)
        self.scan_worker.transfer_preparation_complete.connect(self.on_transfer_preparation_complete)
        self.scan_worker.file_operation_complete.connect(self.on_file_operation_complete)
        
        # ImageProcessor signals
        if self.app_config.get("scanner_mode") == "single_split":
            self.image_processor.image_loaded.connect(self.split_viewer_panel['viewer'].on_image_loaded)
        else:
            self.image_processor.image_loaded.connect(self.viewer1['viewer'].on_image_loaded)
            self.image_processor.image_loaded.connect(self.viewer2['viewer'].on_image_loaded)
        self.image_processor.processing_complete.connect(self.on_processing_complete)
        self.image_processor.error.connect(self.show_error)

        # ImageViewer -> ScanWorker
        if self.app_config.get("scanner_mode") == "single_split":
            self.split_viewer_panel['viewer'].rotation_finished.connect(self.scan_worker.rotate_crop_and_save)
        else:
            self.viewer1['viewer'].rotation_finished.connect(self.scan_worker.rotate_crop_and_save)
            self.viewer2['viewer'].rotation_finished.connect(self.scan_worker.rotate_crop_and_save)

        # ImageViewer -> ImageProcessor
        if self.app_config.get("scanner_mode") == "single_split":
            self.split_viewer_panel['viewer'].load_requested.connect(self.image_processor.request_image_load)
        else:
            self.viewer1['viewer'].load_requested.connect(self.image_processor.request_image_load)
            self.viewer2['viewer'].load_requested.connect(self.image_processor.request_image_load)

        # ImageViewer -> MainWindow (for editing state)
        if self.app_config.get("scanner_mode") == "single_split":
            self.split_viewer_panel['viewer'].crop_adjustment_started.connect(self.on_editing_started)
            self.split_viewer_panel['viewer'].zoom_state_changed.connect(self.on_viewer_zoom_changed)
        else:
            self.viewer1['viewer'].crop_adjustment_started.connect(self.on_editing_started)
            self.viewer2['viewer'].crop_adjustment_started.connect(self.on_editing_started)
            self.viewer1['viewer'].zoom_state_changed.connect(self.on_viewer_zoom_changed)
            self.viewer2['viewer'].zoom_state_changed.connect(self.on_viewer_zoom_changed)

        # Watcher signals
        if self.watcher:
            self.watcher.new_image_detected.connect(self.on_new_image_detected)
            self.watcher.scan_folder_changed.connect(self.trigger_full_refresh)
            self.watcher.error.connect(self.show_error)
            self.watcher.finished.connect(self.watcher.thread.quit)
            
    @Slot(bool)
    def on_viewer_zoom_changed(self, is_zoomed):
        if self.app_config.get("scanner_mode") == "single_split":
            self.is_actively_editing = self.split_viewer_panel['viewer'].is_zoomed
        else:
            self.is_actively_editing = self.viewer1['viewer'].is_zoomed or self.viewer2['viewer'].is_zoomed
        self._check_and_update_jump_button_animation()

    @Slot()
    def on_editing_started(self):
        self.is_actively_editing = True
        self._check_and_update_jump_button_animation()

    @Slot(list)
    def on_initial_scan_complete(self, files):
        self.image_files = files
        
        if self.app_config.get("scanner_mode") != "single_split":
            if hasattr(self, '_split_op_index') and self._split_op_index is not None:
                self.current_index = self._split_op_index
                self.current_index = max(0, self.current_index)
                self._split_op_index = None
            else:
                if self.current_index + 1 >= len(self.image_files) and len(self.image_files) > 0:
                    self.current_index = max(0, len(self.image_files) - 2)
        else:
            if self.current_index + 1 >= len(self.image_files) and len(self.image_files) > 0:
                self.current_index = max(0, len(self.image_files) - 1)

        force_reload = getattr(self, '_force_reload_on_next_scan', False)
        self.update_display(force_reload=force_reload)
        self._force_reload_on_next_scan = False
        
        self.pending_card.set_value(str(len(self.image_files)))
        self.update_total_pages()


    @Slot(dict)
    def on_stats_updated(self, stats):
        staged_details = stats.get('staged_book_details', {})
        
        self.staged_pages_count = sum(staged_details.values())
        self.data_pages_count = stats.get('pages_in_data', 0)
        self.update_total_pages()

        for i in reversed(range(self.books_list_layout.count())): 
            self.books_list_layout.itemAt(i).widget().setParent(None)

        data_books_list = stats.get('book_list_data', [])
        data_books = {entry['name']: entry for entry in data_books_list if isinstance(entry, dict)}
        all_book_names = sorted(list(set(staged_details.keys()) | set(data_books.keys())))
        
        theme_name = self.app_config.get("theme", "Material Dark")
        theme = config.THEMES.get(theme_name, config.THEMES["Material Dark"])
        name_pattern = re.compile(r'-(\d{3})-([^-]+)')

        for book_name in all_book_names:
            match = name_pattern.search(book_name)
            display_name = book_name[:15]
            if match:
                city_code, book_id_part = match.group(1), match.group(2)
                book_number_part = "".join(filter(str.isdigit, book_id_part))[:5]
                display_id = book_number_part.lstrip('0') or '0'
                display_name = f"{city_code} - {display_id}"

            status, pages = ("DATA", data_books[book_name].get('pages', 0)) if book_name in data_books else ("TODAY'S", staged_details.get(book_name, 0))
            
            item_widget = BookListItemWidget(display_name, status, pages, theme)
            self.books_list_layout.addWidget(item_widget)

    @Slot(str)
    def on_new_image_detected(self, path):
        if self.replace_mode_active:
            self.replace_candidates.append(path)
            if len(self.replace_candidates) >= 2:
                self.execute_replace()
            else:
                self.status_label.setText("Αναμονή για 1 ακόμα σάρωση για αντικατάσταση του ζεύγους...")
            return

        if path not in self.image_files:
            self.image_files.append(path)
            self.image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

            # --- Performance Tracking & Stats Update ---
            self.scan_timestamps.append(time.time())
            self.update_scan_speed()
            self.pending_card.set_value(str(len(self.image_files)))
            self.update_total_pages()
            
            # --- Mode-Specific Handling ---
            if self.app_config.get("scanner_mode") == "single_split":
                # Automatically apply the layout from the previous image and process
                new_image_key = os.path.basename(path)

                # Find the most recent layout data available
                last_layout_data = None
                if len(self.image_files) > 1:
                    previous_image_key = os.path.basename(self.image_files[-2])
                    if previous_image_key in self._layout_data:
                        last_layout_data = self._layout_data[previous_image_key]

                if last_layout_data:
                    self._layout_data[new_image_key] = last_layout_data
                    self._save_layout_data()

                    # The worker needs QRect, not dicts
                    rects_for_worker = {
                        'left': QRect(last_layout_data['left']['x'], last_layout_data['left']['y'], last_layout_data['left']['width'], last_layout_data['left']['height']),
                        'right': QRect(last_layout_data['right']['x'], last_layout_data['right']['y'], last_layout_data['right']['width'], last_layout_data['right']['height'])
                    }
                    self.scan_worker.perform_page_split(path, rects_for_worker)

            else: # dual_scan mode auto-corrections
                auto_light = self.app_config.get("auto_lighting_correction_enabled", False)
                auto_color = self.app_config.get("auto_color_correction_enabled", False)
                if auto_light or auto_color:
                    QTimer.singleShot(500, lambda p=path: self.image_processor.auto_process_image(p, auto_light, auto_color))

            # --- UI Navigation ---
            if not self.is_actively_editing:
                self.update_timer.start() # Jump to the new image after a short delay
            
            self._check_and_update_jump_button_animation()

    @Slot(str)
    def show_error(self, message):
        QMessageBox.critical(self, "Σφάλμα Εργασιών", message)

    def update_display(self, force_reload=False):
        if self.app_config.get("scanner_mode") == "single_split":
            self._update_display_single_split(force_reload)
        else:
            self._update_display_dual_scan(force_reload)

    def _update_display_dual_scan(self, force_reload=False):
        path1 = self.image_files[self.current_index] if self.current_index < len(self.image_files) else None
        path2 = self.image_files[self.current_index + 1] if (self.current_index + 1) < len(self.image_files) else None

        self.viewer1['viewer'].request_image_load(path1, force_reload=force_reload)
        self.viewer2['viewer'].request_image_load(path2, force_reload=force_reload)

        total = len(self.image_files)
        page1_num = self.current_index + 1 if path1 else 0
        page2_num = self.current_index + 2 if path2 else 0

        status_text = f"Σελίδες {page1_num}-{page2_num} από {total}" if path2 else f"Σελίδα {page1_num} από {total}"
        if not path1: status_text = "Δεν βρέθηκαν εικόνες."
        self.status_label.setText(status_text)
        
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index + 2 < len(self.image_files))
        self._check_and_update_jump_button_animation()

    def _update_display_single_split(self, force_reload=False):
        path = self.image_files[self.current_index] if self.current_index < len(self.image_files) else None

        self.split_viewer_panel['viewer'].request_image_load(path, force_reload=force_reload)

        if path:
            image_key = os.path.basename(path)
            if image_key in self._layout_data:
                rects_data = self._layout_data[image_key]
                # Use a timer to ensure the pixmap is loaded and scaled before we set rects
                QTimer.singleShot(50, lambda: self.split_viewer_panel['viewer'].set_page_split_rects(rects_data))
            else:
                # If no data exists, reset to default
                QTimer.singleShot(50, lambda: self.split_viewer_panel['viewer'].reset_split_rects_to_default())


        total = len(self.image_files)
        page_num = self.current_index + 1 if path else 0

        status_text = f"Σάρωση {page_num} από {total}" if path else "Δεν βρέθηκαν εικόνες."
        self.status_label.setText(status_text)

        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index + 1 < len(self.image_files))
        self._check_and_update_jump_button_animation()

    @Slot()
    def update_scan_speed(self):
        if len(self.scan_timestamps) < 2:
            self.speed_card.set_value("0.0")
            return

        delta_time_seconds = self.scan_timestamps[-1] - self.scan_timestamps[0]
        if delta_time_seconds < 1: # Avoid division by zero or inflated numbers for very fast scans
             self.speed_card.set_value("---") # Indicate high speed
             return

        # We have len-1 intervals over len timestamps
        scans_in_period = len(self.scan_timestamps) - 1
        pages_per_minute = (scans_in_period / delta_time_seconds) * 60
        self.speed_card.set_value(f"{pages_per_minute:.1f}")

    @Slot()
    def update_total_pages(self):
        """Calculates and updates the total pages for the day."""
        total = self.staged_pages_count + self.data_pages_count + len(self.image_files)
        self.total_card.set_value(str(total))

    def next_pair(self):
        if self.is_actively_editing or self.replace_mode_active: return

        increment = 1 if self.app_config.get("scanner_mode") == "single_split" else 2

        if self.current_index + increment < len(self.image_files):
            self.current_index += increment
            self.update_display()
            self._check_and_update_jump_button_animation()

    def prev_pair(self):
        if self.is_actively_editing or self.replace_mode_active: return

        decrement = 1 if self.app_config.get("scanner_mode") == "single_split" else 2

        if self.current_index > 0:
            self.current_index -= decrement
            self.update_display()
            self._check_and_update_jump_button_animation()

    def jump_to_end(self):
        if self.replace_mode_active: return
        if not self.image_files: return

        if self.app_config.get("scanner_mode") == "single_split":
            new_index = len(self.image_files) - 1
        else:
            new_index = len(self.image_files) - 2 if len(self.image_files) >= 2 else 0

        self.current_index = max(0, new_index)
        self.update_display()
        self.is_actively_editing = False # Jumping to end is a navigation action
        self._check_and_update_jump_button_animation()

    @Slot(str)
    def on_processing_complete(self, path):
        if self.app_config.get("scanner_mode") == "single_split":
            if self.split_viewer_panel['viewer'].image_path == path:
                self.split_viewer_panel['viewer'].request_image_load(path, force_reload=True)
        else:
            if self.viewer1['viewer'].image_path == path:
                self.viewer1['viewer'].request_image_load(path, force_reload=True)
            if self.viewer2['viewer'].image_path == path:
                self.viewer2['viewer'].request_image_load(path, force_reload=True)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            new_config = config.load_config()
            old_mode = self.app_config.get("scanner_mode")
            new_mode = new_config.get("scanner_mode")

            if old_mode != new_mode:
                QMessageBox.information(self, "Απαιτείται Επανεκκίνηση", "Η αλλαγή του τύπου Scanner απαιτεί επανεκκίνηση της εφαρμογής για να εφαρμοστεί, η οποία θα κλείσει τώρα.")
                self.close()
                return

            self.app_config = new_config
            QApplication.instance().setStyleSheet(config.generate_stylesheet(self.app_config.get("theme")))
            
            theme_data = config.THEMES.get(self.app_config.get("theme"), config.THEMES["Material Dark"])
            primary_color = theme_data.get("PRIMARY", "#b0c6ff")
            tertiary_color = theme_data.get("TERTIARY", "#e2bada")

            if self.app_config.get("scanner_mode") == "single_split":
                 self.split_viewer_panel['viewer'].set_theme_colors(primary_color, tertiary_color)
            else:
                self.viewer1['viewer'].set_theme_colors(primary_color, tertiary_color)
                self.viewer2['viewer'].set_theme_colors(primary_color, tertiary_color)
            
            self.image_processor.set_caching_enabled(self.app_config.get("caching_enabled", True))

            if self.watcher and self.watcher.thread:
                try:
                    self.watcher.new_image_detected.disconnect()
                    self.watcher.scan_folder_changed.disconnect()
                    self.watcher.error.disconnect()
                except RuntimeError:
                    pass
                
                self.watcher.stop()
                self.watcher.thread.wait(2000)

            self.setup_workers()
            self.connect_signals()
            self.trigger_full_refresh()

    def delete_single_image(self, viewer_panel):
        if self.replace_mode_active: return
        image_path = viewer_panel['viewer'].image_path
        if not image_path: return
        reply = QMessageBox.question(self, "Επιβεβαίωση Διαγραφής",
                                     f"Είστε βέβαιοι ότι θέλετε να διαγράψετε οριστικά αυτή την εικόνα;\n\n{os.path.basename(image_path)}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Proactively clear UI and cache before telling worker to delete
            viewer_panel['viewer'].clear_image()
            self.image_processor.clear_cache_for_paths([image_path])
            self.scan_worker.delete_file(image_path)

    def delete_current_pair(self):
        if self.replace_mode_active: return
        path1 = self.viewer1['viewer'].image_path
        path2 = self.viewer2['viewer'].image_path
        paths_to_delete = [p for p in [path1, path2] if p]
        if not paths_to_delete: return
        file_names = "\n".join([os.path.basename(p) for p in paths_to_delete])
        reply = QMessageBox.question(self, "Επιβεβαίωση Διαγραφής",
                                     f"Είστε βέβαιοι ότι θέλετε να διαγράψετε οριστικά αυτές τις εικόνες;\n\n{file_names}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Proactively clear UI and cache
            self.viewer1['viewer'].clear_image()
            self.viewer2['viewer'].clear_image()
            self.image_processor.clear_cache_for_paths(paths_to_delete)
            for path in paths_to_delete:
                self.scan_worker.delete_file(path)

    def create_book(self):
        book_name = self.book_name_edit.text().strip()
        if not book_name: return self.show_error("Το όνομα του βιβλίου δεν μπορεί να είναι κενό.")
        if not self.image_files: return self.show_error("Δεν υπάρχουν σαρωμένες εικόνες για να προστεθούν σε ένα βιβλίο.")
        
        reply = QMessageBox.question(self, "Επιβεβαίωση Δημιουργίας Βιβλίου",
                                     f"Δημιουργία βιβλίου '{book_name}' και μετακίνηση {len(self.image_files)} σαρώσεων σε αυτό;",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.progress_dialog = QProgressDialog(f"Δημιουργία βιβλίου '{book_name}'...", "Ακύρωση", 0, len(self.image_files), self)
            self.progress_dialog.setWindowTitle("Μεταφορά Εικόνων")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setAutoClose(True)
            self.progress_dialog.canceled.connect(self.scan_worker.cancel_operation)
            self.progress_dialog.show()

            files_to_move = list(self.image_files)
            self.image_processor.clear_cache_for_paths(files_to_move)
            self.scan_worker.create_book(book_name, files_to_move)

    @Slot(int, int)
    def on_book_creation_progress(self, processed, total):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.setValue(processed)
            if processed >= total: self.progress_dialog.close()

    def restore_image(self, viewer_panel):
        image_path = viewer_panel['viewer'].image_path
        if not image_path: return
        reply = QMessageBox.question(self, "Επιβεβαίωση Επαναφοράς",
                                     f"Επαναφορά της αρχικής εικόνας; Αυτό θα αντικαταστήσει τυχόν αλλαγές.\n\n{os.path.basename(image_path)}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.image_processor.clear_cache_for_paths([image_path])
            self.scan_worker.restore_image(image_path)

    def transfer_all_books(self):
        self.scan_worker.prepare_transfer()

    @Slot(list, list)
    def on_transfer_preparation_complete(self, moves_to_confirm, warnings):
        if not moves_to_confirm and not warnings:
            QMessageBox.information(self, "Δεν Υπάρχουν Βιβλία", "Δεν υπάρχουν έγκυρα βιβλία στον φάκελο προσωρινής στάθμευσης για μεταφορά.")
            return
            
        moves_details = [f"'{move['book_name']}'\n  -> '{move['final_book_path']}'" for move in moves_to_confirm]
        confirmation_message = "Τα ακόλουθα βιβλία θα μεταφερθούν:\n\n" + "\n\n".join(moves_details)
        if warnings:
            confirmation_message += "\n\nΠροειδοποιήσεις (αυτά τα βιβλία θα παραλειφθούν):\n" + "\n".join(warnings)
        confirmation_message += "\n\nΘέλετε να συνεχίσετε;"

        reply = QMessageBox.question(self, "Επιβεβαίωση Μεταφοράς", confirmation_message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Show a "Please Wait" dialog as this can be a long operation
            self.transfer_progress_dialog = QProgressDialog("Μεταφορά βιβλίων στα δεδομένα...\n\nΑυτή η διαδικασία μπορεί να διαρκέσει μερικά λεπτά.", None, 0, 0, self)
            self.transfer_progress_dialog.setWindowTitle("Παρακαλώ Περιμένετε")
            self.transfer_progress_dialog.setCancelButton(None)  # Make it non-cancellable
            self.transfer_progress_dialog.setWindowModality(Qt.WindowModal)
            self.transfer_progress_dialog.show()

            self.transfer_all_btn.setEnabled(False)
            self.status_label.setText(f"Μεταφορά {len(moves_to_confirm)} βιβλίων...")
            QApplication.processEvents()
            self.scan_worker.transfer_all_to_data(moves_to_confirm)

    @Slot(str, str)
    def on_file_operation_complete(self, operation_type, message_or_path):
        """Handles the UI updates after a file operation from the worker is complete."""
        self.is_actively_editing = False  # Reset editing state after any operation

        # Targeted refresh for single-image edits that don't change the file list
        if operation_type in ["crop", "color_fix", "restore", "rotate"]:
            path = message_or_path
            if self.app_config.get("scanner_mode") == "single_split":
                if self.split_viewer_panel['viewer'].image_path == path:
                    self.split_viewer_panel['viewer'].request_image_load(path, force_reload=True, show_loading_animation=False)
            else:
                if self.viewer1['viewer'].image_path == path:
                    self.viewer1['viewer'].request_image_load(path, force_reload=True, show_loading_animation=False)
                if self.viewer2['viewer'].image_path == path:
                    self.viewer2['viewer'].request_image_load(path, force_reload=True, show_loading_animation=False)

        elif operation_type == "split":
            self.viewer1['viewer'].set_splitting_mode(False)
            self.viewer2['viewer'].set_splitting_mode(False)
            
            self.image_processor.clear_cache()
            
            self.status_label.setText("Ανανέωση λίστας αρχείων...")
            self.trigger_full_refresh(force_reload_viewers=True)

        elif operation_type in ["delete", "create_book", "replace_pair"]:
            if self.app_config.get("scanner_mode") == "single_split":
                self.split_viewer_panel['viewer'].clear_image()
            else:
                self.viewer1['viewer'].clear_image()
                self.viewer2['viewer'].clear_image()

            self.status_label.setText("Ανανέωση λίστας αρχείων...")
            self.trigger_full_refresh(force_reload_viewers=True)

        elif operation_type == "transfer_all":
            if hasattr(self, 'transfer_progress_dialog'):
                self.transfer_progress_dialog.close()
                del self.transfer_progress_dialog

            self.transfer_all_btn.setEnabled(True)
            self.statusBar().showMessage(message_or_path, 5000)
            self.trigger_full_refresh()

        self._check_and_update_jump_button_animation()


    def apply_crop(self, viewer_panel):
        viewer = viewer_panel['viewer']
        if viewer.image_path and viewer.interaction_mode == InteractionMode.CROPPING:
            crop_rect = viewer.get_image_space_crop_rect()
            if crop_rect:
                self.image_processor.clear_cache_for_paths([viewer.image_path])
                self.scan_worker.crop_and_save_image(viewer.image_path, crop_rect)
    
    def apply_color_fix(self, viewer_panel):
        viewer = viewer_panel['viewer']
        if viewer.image_path:
            self.image_processor.clear_cache_for_paths([viewer.image_path])
            self.scan_worker.correct_color_and_save(viewer.image_path)

    def toggle_split_mode(self, viewer_panel, enable):
        viewer = viewer_panel['viewer']
        viewer.set_splitting_mode(enable)
        self.is_actively_editing = enable

        viewer_panel['mode_label'].setText("ΔΙΑΧΩΡΙΣΜΟΣ")
        viewer_panel['mode_label'].setVisible(enable)
        
        viewer_panel['confirm_split'].setVisible(enable)
        viewer_panel['cancel_split'].setVisible(enable)
        
        # Hide all other controls
        viewer_panel['cancel_rotate'].setVisible(False)
        for name in ['split', 'rotate', 'fix_color', 'restore', 'delete', 'crop']:
            viewer_panel[name].setVisible(not enable)
        
        viewer_panel['toolbar'].adjustSize()

        if not enable:
            self._check_and_update_jump_button_animation()

    def toggle_rotate_mode(self, viewer_panel, enable):
        viewer = viewer_panel['viewer']
        viewer.set_rotating_mode(enable)
        self.is_actively_editing = enable

        viewer_panel['mode_label'].setText("ΠΕΡΙΣΤΡΟΦΗ")
        viewer_panel['mode_label'].setVisible(enable)

        viewer_panel['cancel_rotate'].setVisible(enable)

        # Hide all other controls
        viewer_panel['confirm_split'].setVisible(False)
        viewer_panel['cancel_split'].setVisible(False)
        for name in ['split', 'rotate', 'fix_color', 'restore', 'delete', 'crop']:
            viewer_panel[name].setVisible(not enable)

        viewer_panel['toolbar'].adjustSize()

        if not enable:
            self._check_and_update_jump_button_animation()

    def apply_split(self, viewer_panel):
        viewer = viewer_panel['viewer']
        if viewer.image_path:
            path_to_split = viewer.image_path
            if path_to_split in self.image_files:
                self._split_op_index = self.image_files.index(path_to_split)
            else:
                self._split_op_index = None

            split_x = viewer.get_split_x_in_image_space()
            if split_x is not None:
                self.image_processor.clear_cache_for_paths([path_to_split])
                self.scan_worker.split_image(path_to_split, split_x)
        
        self.toggle_split_mode(viewer_panel, False)

    def toggle_replace_mode(self):
        self.replace_mode_active = not self.replace_mode_active
        
        theme_name = self.app_config.get("theme", "Material Dark")
        theme = config.THEMES.get(theme_name, config.THEMES["Material Dark"])
        
        if self.replace_mode_active:
            path1 = self.viewer1['viewer'].image_path
            path2 = self.viewer2['viewer'].image_path
            if not path1 or not path2:
                QMessageBox.warning(self, "Η Ενέργεια Αποκλείστηκε", "Πρέπει να υπάρχει ένα πλήρες ζεύγος στην οθόνη για τη χρήση της λειτουργίας Αντικατάστασης.")
                self.replace_mode_active = False
                return

            self.replace_pair_btn.setText("❌ Ακύρωση Αντικατάστασης")
            self.replace_pair_btn.setProperty("class", "destructive filled")
            self.status_label.setText("Αναμονή για 2 νέες σαρώσεις για αντικατάσταση του ζεύγους...")

            tertiary_color = QColor(theme['TERTIARY'])
            tertiary_rgb = tertiary_color.getRgb()
            accent_style = f"""
                QFrame#ViewerFrame {{
                    background-color: rgba({tertiary_rgb[0]}, {tertiary_rgb[1]}, {tertiary_rgb[2]}, 25);
                    border: 1px solid {theme['TERTIARY']};
                    border-radius: 12px;
                }}
            """
            self.viewer1['frame'].setStyleSheet(accent_style)
            self.viewer2['frame'].setStyleSheet(accent_style)
            self.replace_candidates = []
        else:
            self.replace_pair_btn.setText("🔁 Αντικατάσταση Ζεύγους")
            self.replace_pair_btn.setProperty("class", "")
            
            self.viewer1['frame'].setStyleSheet("")
            self.viewer2['frame'].setStyleSheet("")
            self.update_display() 
        
        self.replace_pair_btn.style().unpolish(self.replace_pair_btn)
        self.replace_pair_btn.style().polish(self.replace_pair_btn)

    def execute_replace(self):
        old_path1 = self.viewer1['viewer'].image_path
        old_path2 = self.viewer2['viewer'].image_path
        new_path1 = self.replace_candidates[0]
        new_path2 = self.replace_candidates[1]

        self.image_processor.clear_cache_for_paths([old_path1, old_path2])
        self.scan_worker.replace_pair(old_path1, old_path2, new_path1, new_path2)
        self.toggle_replace_mode() # Deactivate mode

    def update_single_split(self):
        """Saves the current split layout and triggers the processing worker."""
        viewer = self.split_viewer_panel['viewer']
        if not viewer.image_path:
            return

        rects = viewer.get_page_split_rects()
        if rects:
            # Convert QRect to a serializable dict
            serializable_rects = {
                'left': {'x': rects['left'].x(), 'y': rects['left'].y(), 'width': rects['left'].width(), 'height': rects['left'].height()},
                'right': {'x': rects['right'].x(), 'y': rects['right'].y(), 'width': rects['right'].width(), 'height': rects['right'].height()}
            }
            image_key = os.path.basename(viewer.image_path)
            self._layout_data[image_key] = serializable_rects
            self._save_layout_data()

            # Trigger the worker to perform the split
            self.scan_worker.perform_page_split(viewer.image_path, rects)

    def restore_split_rects(self):
        """Resets the rectangles in the viewer to their default state and applies it."""
        self.split_viewer_panel['viewer'].reset_split_rects_to_default()
        # After resetting, immediately trigger an update to save and process this default state
        self.update_single_split()


    def _load_layout_data(self):
        """Loads the layout data from the JSON file in the scan folder."""
        scan_folder = self.app_config.get("scan_folder")
        if not scan_folder:
            return
        layout_file_path = os.path.join(scan_folder, 'layout_data.json')
        if os.path.exists(layout_file_path):
            try:
                with open(layout_file_path, 'r', encoding='utf-8') as f:
                    self._layout_data = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                print(f"Could not load layout data: {e}")
                self._layout_data = {}
        else:
            self._layout_data = {}

    def _save_layout_data(self):
        """Saves the current layout data to the JSON file in the scan folder."""
        scan_folder = self.app_config.get("scan_folder")
        if not scan_folder:
            return
        layout_file_path = os.path.join(scan_folder, 'layout_data.json')
        try:
            with open(layout_file_path, 'w', encoding='utf-8') as f:
                json.dump(self._layout_data, f, indent=4)
        except IOError as e:
            print(f"Could not save layout data: {e}")

    def closeEvent(self, event):
        """Gracefully shut down all background threads before closing."""
        self.image_processor.clear_cache()

        if self.watcher and self.watcher.thread.isRunning():
            self.watcher.stop()
            self.watcher.thread.wait(500)

        if self.scan_worker_thread.isRunning():
            self.scan_worker_thread.quit()
            self.scan_worker_thread.wait(500)

        if self.image_processor_thread.isRunning():
            self.image_processor_thread.quit()
            self.image_processor_thread.wait(500)
        
        event.accept()
        
    def _check_and_update_jump_button_animation(self):
        has_unseen_images = self.current_index + 2 < len(self.image_files)
        if self.app_config.get("scanner_mode") == "single_split":
            has_unseen_images = self.current_index + 1 < len(self.image_files)

        if has_unseen_images:
            if not self.jump_button_animation.isActive():
                self.jump_button_animation_step = 0
                self.jump_button_animation.start(50)
        else:
            if self.jump_button_animation.isActive():
                self.jump_button_animation.stop()
                self.jump_end_btn.setStyleSheet("") # Reset style

    def _update_jump_button_animation(self):
        # A simple sine wave for smooth pulsing
        from math import sin, pi
        # A value that goes from 0 to 1 and back to 0 over 40 steps
        progress = self.jump_button_animation_step / 40.0
        eased_progress = sin(progress * pi)

        theme = config.THEMES.get(self.app_config.get("theme", "Material Dark"))
        start_color = QColor(theme['SURFACE_CONTAINER'])
        end_color = QColor(theme['TERTIARY'])

        r = int(start_color.red() + (end_color.red() - start_color.red()) * eased_progress)
        g = int(start_color.green() + (end_color.green() - start_color.green()) * eased_progress)
        b = int(start_color.blue() + (end_color.blue() - start_color.blue()) * eased_progress)
        
        self.jump_end_btn.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: none;")

        self.jump_button_animation_step = (self.jump_button_animation_step + 1) % 41