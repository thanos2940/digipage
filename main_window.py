import sys
import os
import re
import time
from collections import deque
from datetime import datetime
import threading # Added for state lock
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QDockWidget, QScrollArea, QLineEdit, QGroupBox, QFormLayout,
    QFrame, QMessageBox, QDialog, QToolButton, QSpacerItem, QSizePolicy, QApplication,
    QProgressDialog, QProgressBar, QStackedWidget
)
from PySide6.QtCore import Qt, QThread, Slot, QSize, QTimer, QPointF
from PySide6.QtGui import QIcon, QPixmap, QColor

# Added for memory monitoring (Issue 7.1 Fix)
try:
    import psutil
except ImportError:
    psutil = None
    print("Warning: psutil not found. Memory pressure monitoring disabled.")


import config
from image_viewer import ImageViewer, InteractionMode
from workers import ScanWorker, Watcher, ImageProcessor, natural_sort_key
from settings_dialog import SettingsDialog
from log_viewer_dialog import LogViewerDialog
from ui_modes.dual_scan_mode import DualScanModeWidget
from ui_modes.single_split_mode import SingleSplitModeWidget


# A custom widget for displaying book information in a structured, table-like row.
class BookListItemWidget(QWidget):
    def __init__(self, name, status, pages, theme, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(50)

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

        name_label.setStyleSheet(f"border: none; color: {theme['ON_SURFACE']}; background-color: transparent; font-weight: bold;")

        status_color = theme['SUCCESS'] if status == "DATA" else theme['WARNING']
        rgb_color = QColor(status_color).getRgb()
        bg_color_rgba = f"rgba({rgb_color[0]}, {rgb_color[1]}, {rgb_color[2]}, 40)"

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


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner")
        self.app_config = config.load_config()
        self.image_files = []
        self.current_index = 0
        self.replace_mode_active = False
        self.replace_candidates = []
        self._force_reload_on_next_scan = False
        self._split_op_index = None
        self._is_closing = False
        
        self._initial_load_done = False

        self.viewer1 = None
        self.viewer2 = None
        self.current_ui_mode = None
        
        # --- State Management (Issue 6.1 Fix) ---
        self._navigation_lock = threading.Lock()
        self._work_state = {
            'editing': False,      # Is a viewer actively dragging a crop/split/rotation handle?
            'zoomed': False,       # Is a viewer currently zoomed in (panning mode)?
            'dirty_layout': False, # Does single_split mode have unsaved layout changes?
            'processing': False    # Is a background worker performing a long operation?
        }
        
        # --- Performance Tracking ---
        self.scan_timestamps = deque(maxlen=20)
        self.staged_pages_count = 0
        self.data_pages_count = 0
        
        # --- Auto-Navigation Timer (Issue 6.2 Fix: Debounced Queue) ---
        self._pending_navigation_target = None
        self.navigation_timer = QTimer(self)
        self.navigation_timer.setSingleShot(True)
        self.navigation_timer.setInterval(300) 
        self.navigation_timer.timeout.connect(self._execute_pending_navigation)

        self.jump_button_animation = QTimer(self)
        self.jump_button_animation.timeout.connect(self._update_jump_button_animation)
        self.jump_button_animation_step = 0
        
        self.setup_ui()
        self.setup_workers()
        self.connect_signals()

        # --- Memory Monitor (Issue 7.1 Fix) ---
        if psutil:
            self._memory_monitor_timer = QTimer(self)
            self._memory_monitor_timer.setInterval(5000)
            self._memory_monitor_timer.timeout.connect(self.image_processor._check_memory_pressure)
            self._memory_monitor_timer.start()
        
    @Slot()
    def _execute_pending_navigation(self):
        """Executes queued navigation if still allowed (Issue 6.2 Fix)."""
        if self._pending_navigation_target is not None and self.is_navigation_allowed(check_only=True):
            self.current_index = self._pending_navigation_target
            self._pending_navigation_target = None
            self.update_display()
            
    def update_work_state(self, **kwargs):
        """Thread-safe state updates (Issue 6.1 Fix)."""
        with self._navigation_lock:
            self._work_state.update(kwargs)
            
    def is_navigation_allowed(self, check_only=False):
        """Central method to determine if navigation should proceed (Issue 6.1 Fix)."""
        with self._navigation_lock:
            if self.replace_mode_active:
                return False
            
            # Prevent navigation if user is actively interacting with a viewer
            if self._work_state['editing'] or self._work_state['zoomed']:
                return False
            
            # Prevent navigation in single_split if layout is dirty (unsaved changes)
            scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
            if scanner_mode == "single_split" and self._work_state['dirty_layout']:
                if not check_only:
                    self.statusBar().showMessage("Παρακαλώ πατήστε 'Ενημέρωση Layout' ή 'Ανανέωση' για να συνεχίσετε.", 3000)
                return False
            
            return True

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_load_done:
            QTimer.singleShot(100, self.initial_load)
            self._initial_load_done = True

    # ... (open_log_viewer_dialog, get_current_theme, perform_page_split) ...
    def open_log_viewer_dialog(self):
        dialog = LogViewerDialog(self)
        dialog.exec()

    def get_current_theme(self):
        """Returns the dictionary for the currently configured theme."""
        theme_name = self.app_config.get("theme", "Material Dark")
        return config.THEMES.get(theme_name, config.THEMES["Material Dark"])

    @Slot(str, dict)
    def perform_page_split(self, source_path, layout_data):
        """A passthrough method to call the page split worker."""
        self.scan_worker.perform_page_split(source_path, layout_data)

    def initial_load(self):
        self.trigger_full_refresh()

    def setup_ui(self):
        main_container = QWidget()
        main_v_layout = QVBoxLayout(main_container)
        main_v_layout.setSpacing(0)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(main_container)

        content_area = QWidget()
        content_layout = QHBoxLayout(content_area)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(10, 10, 10, 10)

        self.ui_mode_stack = QStackedWidget()
        content_layout.addWidget(self.ui_mode_stack)

        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")

        if scanner_mode == "dual_scan":
            self.current_ui_mode = DualScanModeWidget(self, self.app_config)
            self.viewer1 = self.current_ui_mode.viewer1
            self.viewer2 = self.current_ui_mode.viewer2
            self.ui_mode_stack.addWidget(self.current_ui_mode)
        elif scanner_mode == "single_split":
            self.current_ui_mode = SingleSplitModeWidget(self)
            self.viewer1 = None
            self.viewer2 = None
            self.ui_mode_stack.addWidget(self.current_ui_mode)
        else:
            error_label = QLabel(f"Error: Unknown scanner_mode '{scanner_mode}'")
            error_label.setAlignment(Qt.AlignCenter)
            self.ui_mode_stack.addWidget(error_label)
            self.current_ui_mode = None
            self.viewer1 = None
            self.viewer2 = None

        self.ui_mode_stack.setCurrentIndex(0)
        
        main_v_layout.addWidget(content_area)

        self.create_bottom_bar(main_v_layout)
        
        self.create_sidebar()

    # ... (create_sidebar, _get_pending_page_count, create_bottom_bar) ...
    def create_sidebar(self):
        sidebar_dock = QDockWidget("Χειριστήρια & Στατιστικά", self)
        sidebar_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        sidebar_dock.setFeatures(QDockWidget.DockWidgetMovable)
        sidebar_dock.setFixedWidth(320)

        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setSpacing(15)
        sidebar_dock.setWidget(sidebar_widget)
        
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
        stats_group.setLayout(stats_group_layout)

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
        today_layout.addWidget(self.view_log_btn)
        today_group.setLayout(today_layout)
        
        settings_btn = QPushButton("Ρυθμίσεις")
        settings_btn.setToolTip("Άνοιγμα του παραθύρου ρυθμίσεων της εφαρμογής.")
        settings_btn.clicked.connect(self.open_settings_dialog)

        sidebar_layout.addWidget(stats_group)
        sidebar_layout.addWidget(book_group)
        sidebar_layout.addWidget(today_group)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(settings_btn)

        self.addDockWidget(Qt.RightDockWidgetArea, sidebar_dock)

    def _get_pending_page_count(self):
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        scan_folder = self.app_config.get("scan_folder")

        if scanner_mode == "single_split":
            final_folder = os.path.join(scan_folder, 'final')
            if os.path.isdir(final_folder):
                return len([f for f in os.listdir(final_folder) if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS])
            return 0
        else:
            return len(self.image_files)

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
        
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        if scanner_mode == "single_split":
            self.delete_pair_btn = QPushButton("🗑️ Διαγραφή Λήψης")
            self.delete_pair_btn.setToolTip("Οριστική διαγραφή της εικόνας που εμφανίζεται και των παραγώγων της.")
            self.replace_pair_btn = QPushButton("🔁 Αντικατάσταση Λήψης")
            self.replace_pair_btn.setToolTip("Αντικατάσταση της τρέχουσας λήψης με την επόμενη σάρωση.")
        else:
            self.delete_pair_btn = QPushButton("🗑️ Διαγραφή Ζεύγους")
            self.delete_pair_btn.setToolTip("Οριστική διαγραφή των δύο εικόνων που εμφανίζονται.")
            self.replace_pair_btn = QPushButton("🔁 Αντικατάσταση Ζεύγους")
            self.replace_pair_btn.setToolTip("Αντικατάσταση του τρέχοντος ζεύγους με τις δύο επόμενες σαρωμένες εικόνες.")

        self.delete_pair_btn.setProperty("class", "destructive filled")
        self.delete_pair_btn.setMinimumHeight(40)
        self.delete_pair_btn.clicked.connect(self.delete_current_pair)

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
        # Only proceed if navigation is allowed, otherwise this is a dirty layout refresh
        if not self.is_navigation_allowed():
            self.update_work_state(dirty_layout=False) # Clear dirty state as user forced refresh
            
        self._force_reload_on_next_scan = force_reload_viewers
        self.scan_worker.perform_initial_scan()
        self.scan_worker.calculate_today_stats()

    def wheelEvent(self, event):
        if not self.is_navigation_allowed(): 
            return

        # For dual scan mode, check for zoomed state on viewer to allow scrolling within image
        if isinstance(self.current_ui_mode, DualScanModeWidget):
            if self.viewer1['viewer'].underMouse() or self.viewer2['viewer'].underMouse():
                if self.viewer1['viewer'].is_zoomed or self.viewer2['viewer'].is_zoomed:
                    return

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
        
        # ImageProcessor signals
        self.image_processor.processing_complete.connect(self.on_processing_complete)
        self.image_processor.error.connect(self.show_error)

        # Mode-specific viewer connections
        if isinstance(self.current_ui_mode, DualScanModeWidget):
            self.image_processor.image_loaded.connect(self.viewer1['viewer'].on_image_loaded)
            self.image_processor.image_loaded.connect(self.viewer2['viewer'].on_image_loaded)

            # ImageViewer -> ScanWorker
            self.viewer1['viewer'].rotation_finished.connect(self.scan_worker.rotate_crop_and_save)
            self.viewer2['viewer'].rotation_finished.connect(self.scan_worker.rotate_crop_and_save)

            # ImageViewer -> ImageProcessor
            self.viewer1['viewer'].load_requested.connect(self.image_processor.request_image_load)
            self.viewer2['viewer'].load_requested.connect(self.image_processor.request_image_load)

            # ImageViewer -> MainWindow (for editing state)
            self.viewer1['viewer'].crop_adjustment_started.connect(lambda: self.update_work_state(editing=True))
            self.viewer2['viewer'].crop_adjustment_started.connect(lambda: self.update_work_state(editing=True))
            self.viewer1['viewer'].crop_adjustment_finished.connect(lambda: self.update_work_state(editing=False))
            self.viewer2['viewer'].crop_adjustment_finished.connect(lambda: self.update_work_state(editing=False))
            self.viewer1['viewer'].zoom_state_changed.connect(lambda z: self.update_work_state(zoomed=z))
            self.viewer2['viewer'].zoom_state_changed.connect(lambda z: self.update_work_state(zoomed=z))

        elif isinstance(self.current_ui_mode, SingleSplitModeWidget):
            self.image_processor.image_loaded.connect(self.current_ui_mode.viewer.on_image_loaded)
            self.current_ui_mode.viewer.load_requested.connect(self.image_processor.request_image_load)
            
            # Use the core viewer signals for state
            self.current_ui_mode.viewer.crop_adjustment_started.connect(lambda: self.update_work_state(editing=True))
            self.current_ui_mode.viewer.crop_adjustment_finished.connect(lambda: self.update_work_state(editing=False))
            self.current_ui_mode.viewer.zoom_state_changed.connect(lambda z: self.update_work_state(zoomed=z))

        # Watcher signals (Issue 2.2 Fix)
        if self.watcher:
            self.watcher.new_image_detected.connect(self.on_new_image_detected)
            self.watcher.file_deleted.connect(lambda path: self.on_file_system_change("deleted", path))
            self.watcher.file_renamed.connect(lambda old, new: self.on_file_system_change("renamed", (old, new)))
            self.watcher.error.connect(self.show_error)
            self.watcher.finished.connect(self.watcher.thread.quit)
            
    @Slot(str, object) # path can be string or tuple (old_path, new_path)
    def on_file_system_change(self, change_type, path):
        """Handles specific file system events for differential updates (Issue 2.2 Fix)"""
        if self._is_closing: return
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        step = 1 if scanner_mode == "single_split" else 2
        
        if change_type == "deleted":
            if path in self.image_files:
                old_index = self.image_files.index(path)
                self.image_files.remove(path)
                self.image_processor.clear_cache_for_paths([path])
                
                # Adjust current_index and bounds checking
                if self.current_index >= len(self.image_files):
                    self.current_index = max(0, len(self.image_files) - step)
                elif self.current_index > old_index:
                    self.current_index = max(0, self.current_index - step)
                
                self.update_display(force_reload=True)
                self.pending_card.set_value(str(self._get_pending_page_count()))
        
        elif change_type == "renamed":
            old_path, new_path = path
            if old_path in self.image_files:
                idx = self.image_files.index(old_path)
                self.image_files[idx] = new_path
                # Update cache (forwarding item is handled in ImageProcessor cache logic)
                self.image_processor.clear_cache_for_paths([old_path])
                
                if self.current_index == idx or (self.current_index + 1) == idx:
                    self.update_display(force_reload=True)
                    
            self.image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
        
        # Recalculate stats as a file operation occurred
        self.scan_worker.calculate_today_stats()

    @Slot(list)
    def on_initial_scan_complete(self, files):
        if self._is_closing: return
        self.image_files = files
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        
        if hasattr(self, '_split_op_index') and self._split_op_index is not None:
            self.current_index = self._split_op_index
            self.current_index = max(0, self.current_index)
            self._split_op_index = None
        else:
            step = 1 if scanner_mode == "single_split" else 2
            if self.current_index + step >= len(self.image_files) and len(self.image_files) > 0:
                self.current_index = max(0, len(self.image_files) - step)

        force_reload = getattr(self, '_force_reload_on_next_scan', False)
        self.update_display(force_reload=force_reload)
        self._force_reload_on_next_scan = False
        
        self.pending_card.set_value(str(self._get_pending_page_count()))
        self.update_total_pages()


    @Slot(dict)
    def on_stats_updated(self, stats):
        if self._is_closing: return
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
        if self._is_closing: return
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        step = 1 if scanner_mode == "single_split" else 2

        if self.replace_mode_active:
            self.replace_candidates.append(path)

            if scanner_mode == "single_split":
                if len(self.replace_candidates) >= 1:
                    self.execute_single_replace()
            else:
                if len(self.replace_candidates) >= 2:
                    self.execute_replace()
                else:
                    self.status_label.setText("Αναμονή για 1 ακόμα σάρωση για αντικατάσταση του ζεύγους...")
            return

        if path not in self.image_files:
            self.image_files.append(path)
            self.image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            
            # --- Performance Tracking & Stats ---
            self.scan_timestamps.append(time.time())
            self.update_scan_speed()
            self.pending_card.set_value(str(self._get_pending_page_count()))
            self.update_total_pages()
            
            # --- Prefetching (Issue 1.3 Fix) ---
            if self.current_index + step < len(self.image_files):
                for offset in range(step):
                    idx = len(self.image_files) - step + offset
                    if idx < len(self.image_files):
                        QTimer.singleShot(
                            100 * offset, 
                            lambda p=self.image_files[idx]: 
                                self.image_processor.prefetch_image(p)
                        )
            
            # --- Mode-Specific Auto-Processing ---
            if scanner_mode == "single_split" and isinstance(self.current_ui_mode, SingleSplitModeWidget):
                # Auto-processing logic is now handled by the SingleSplitModeWidget
                # The assumption is that the new file will inherit the previous layout,
                # save it (to cache), and trigger the split immediately.
                if len(self.image_files) >= 2:
                    prev_path = self.image_files[-2]
                    layout = self.current_ui_mode.get_layout_for_image(prev_path) # Try to get previous layout

                    if layout:
                        # Save this layout for the new image (inheritance)
                        self.current_ui_mode.save_layout_data(path, layout)
                        # Automatically perform the split in the background with delay
                        QTimer.singleShot(100, lambda p=path, l=layout: self.perform_page_split(p, l))
            else:
                auto_light = self.app_config.get("auto_lighting_correction_enabled", False)
                auto_color = self.app_config.get("auto_color_correction_enabled", False)
                if auto_light or auto_color:
                    QTimer.singleShot(500, lambda p=path: self.image_processor.auto_process_image(p, auto_light, auto_color))

            # --- UI Navigation (Issue 6.2 Fix: Debounced Queue) ---
            if self.is_navigation_allowed():
                self._pending_navigation_target = max(0, len(self.image_files) - step)
                self.navigation_timer.start()
            
            self._check_and_update_jump_button_animation()


    @Slot(str)
    def show_error(self, message):
        QMessageBox.critical(self, "Σφάλμα Εργασιών", message)

    def update_display(self, force_reload=False):
        self.update_work_state(editing=False, zoomed=False)
        total = len(self.image_files)
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        step = 1 if scanner_mode == "single_split" else 2

        path1_exists = self.current_index < total

        if not path1_exists:
            self.status_label.setText("Δεν βρέθηκαν εικόνες.")
            if self.current_ui_mode and hasattr(self.current_ui_mode, 'load_image'):
                self.current_ui_mode.load_image(None)
            elif self.viewer1 and self.viewer2:
                self.viewer1['viewer'].request_image_load(None, force_reload=force_reload)
                self.viewer2['viewer'].request_image_load(None, force_reload=force_reload)
            return

        page1_num = self.current_index + 1
        if scanner_mode == "dual_scan":
            path2_exists = (self.current_index + 1) < total
            page2_num = self.current_index + 2 if path2_exists else 0
            status_text = f"Σελίδες {page1_num}-{page2_num} από {total}" if path2_exists else f"Σελίδα {page1_num} από {total}"
        else:
            status_text = f"Εικόνα {page1_num} από {total}"
        
        self.status_label.setText(status_text)
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index + step < len(self.image_files))
        self._check_and_update_jump_button_animation()

        if scanner_mode == "single_split":
            path = self.image_files[self.current_index]
            self.current_ui_mode.load_image(path)

        elif scanner_mode == "dual_scan":
            path1 = self.image_files[self.current_index] if path1_exists else None
            path2 = self.image_files[self.current_index + 1] if (self.current_index + 1) < total else None

            self.viewer1['viewer'].request_image_load(path1, force_reload=force_reload)
            self.viewer2['viewer'].request_image_load(path2, force_reload=force_reload)

            self.viewer1['toolbar'].setEnabled(path1 is not None)
            self.viewer2['toolbar'].setEnabled(path2 is not None)

    @Slot()
    def update_scan_speed(self):
        if len(self.scan_timestamps) < 2:
            self.speed_card.set_value("0.0")
            return

        delta_time_seconds = self.scan_timestamps[-1] - self.scan_timestamps[0]
        if delta_time_seconds < 1:
             self.speed_card.set_value("---")
             return

        scans_in_period = len(self.scan_timestamps) - 1
        pages_per_minute = (scans_in_period / delta_time_seconds) * 60
        self.speed_card.set_value(f"{pages_per_minute:.1f}")

    @Slot()
    def update_total_pages(self):
        if self._is_closing: return
        total = self.staged_pages_count + self.data_pages_count + self._get_pending_page_count()
        self.total_card.set_value(str(total))

    def next_pair(self):
        if not self.is_navigation_allowed(): return

        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        step = 1 if scanner_mode == "single_split" else 2

        if self.current_index + step < len(self.image_files):
            self.current_index += step
            self.update_display()
            self._check_and_update_jump_button_animation()

    def prev_pair(self):
        if not self.is_navigation_allowed(): return

        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        step = 1 if scanner_mode == "single_split" else 2

        if self.current_index > 0:
            self.current_index -= step
            self.update_display()
            self._check_and_update_jump_button_animation()

    def jump_to_end(self):
        if self.replace_mode_active: return
        if not self.image_files: return
        
        # Allow jump even if layout is dirty, as it clears the dirty state.
        self.update_work_state(dirty_layout=False) 

        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        step = 1 if scanner_mode == "single_split" else 2

        new_index = len(self.image_files) - step if len(self.image_files) >= step else 0
        self.current_index = max(0, new_index)
        self.update_display()
        self._check_and_update_jump_button_animation()

    @Slot(str)
    def on_processing_complete(self, path):
        if self._is_closing: return
        
        if self.viewer1:
            if self.viewer1['viewer'].image_path == path:
                self.viewer1['viewer'].request_image_load(path, force_reload=True, show_loading_animation=False)
            if self.viewer2['viewer'].image_path == path:
                self.viewer2['viewer'].request_image_load(path, force_reload=True, show_loading_animation=False)
        
        self.scan_worker.calculate_today_stats()

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.app_config = config.load_config()
            QApplication.instance().setStyleSheet(config.generate_stylesheet(self.app_config.get("theme")))
            
            theme_data = config.THEMES.get(self.app_config.get("theme"), config.THEMES["Material Dark"])

            if self.viewer1 and self.viewer2:
                primary_color = theme_data.get("PRIMARY", "#b0c6ff")
                tertiary_color = theme_data.get("TERTIARY", "#e2bada")
                self.viewer1['viewer'].set_theme_colors(primary_color, tertiary_color)
                self.viewer2['viewer'].set_theme_colors(primary_color, tertiary_color)
            
            self.image_processor.set_caching_enabled(self.app_config.get("caching_enabled", True))

            if self.watcher and self.watcher.thread:
                try:
                    self.watcher.new_image_detected.disconnect()
                    self.watcher.file_deleted.disconnect()
                    self.watcher.file_renamed.disconnect()
                    self.watcher.error.disconnect()
                except RuntimeError:
                    pass
                
                self.watcher.stop()

            self.setup_workers()
            self.trigger_full_refresh()

    # ... (apply_crop, apply_color_fix, toggle_split_mode, toggle_rotate_mode, apply_split) ...
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
        self.update_work_state(editing=enable)

        if enable:
            viewer_panel['controls_stack'].setCurrentIndex(1)
        else:
            viewer_panel['controls_stack'].setCurrentIndex(0)

    def toggle_rotate_mode(self, viewer_panel, enable):
        viewer = viewer_panel['viewer']
        viewer.set_rotating_mode(enable)
        self.update_work_state(editing=enable)

        if enable:
            viewer_panel['controls_stack'].setCurrentIndex(2)
        else:
            viewer_panel['controls_stack'].setCurrentIndex(0)

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

    def delete_current_pair(self):
        if self.replace_mode_active:
            return

        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")

        if scanner_mode == "single_split":
            if self.current_index < len(self.image_files):
                path_to_delete = self.image_files[self.current_index]
                reply = QMessageBox.question(
                    self, "Επιβεβαίωση Διαγραφής",
                    f"Θα διαγραφούν:\n- Η πρωτότυπη εικόνα\n- Τα παράγωγά της (_L, _R)\n- Το layout\n\n{os.path.basename(path_to_delete)}",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.current_ui_mode.viewer.clear_image()
                    self.image_processor.clear_cache_for_paths([path_to_delete])
                    if hasattr(self.current_ui_mode, 'remove_layout_data'):
                         self.current_ui_mode.remove_layout_data(path_to_delete)
                    self.scan_worker.delete_split_image_and_artifacts(path_to_delete)
                    self.trigger_full_refresh(force_reload_viewers=True)
            return

        if not self.viewer1 or not self.viewer2:
            return

        path1 = self.viewer1['viewer'].image_path
        path2 = self.viewer2['viewer'].image_path
        paths_to_delete = [p for p in [path1, path2] if p]
        if not paths_to_delete:
            return
        file_names = "\n".join([os.path.basename(p) for p in paths_to_delete])
        reply = QMessageBox.question(self, "Επιβεβαίωση Διαγραφής",
                                     f"Είστε βέβαιοι ότι θέλετε να διαγράψετε οριστικά αυτές τις εικόνες;\n\n{file_names}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.viewer1['viewer'].clear_image()
            self.viewer1['toolbar'].setEnabled(False)
            self.viewer2['viewer'].clear_image()
            self.viewer2['toolbar'].setEnabled(False)
            self.image_processor.clear_cache_for_paths(paths_to_delete)
            for path in paths_to_delete:
                self.scan_worker.delete_file(path)

    def create_book(self):
        book_name = self.book_name_edit.text().strip()
        if not book_name:
            return self.show_error("Το όνομα του βιβλίου δεν μπορεί να είναι κενό.")

        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        scan_folder = self.app_config.get("scan_folder")
        source_folder = scan_folder
        files_in_source = []

        if scanner_mode == "single_split":
            final_folder = os.path.join(scan_folder, 'final')
            if os.path.isdir(final_folder):
                source_folder = final_folder
                files_in_source = [os.path.join(source_folder, f) for f in os.listdir(source_folder) if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS]
        else:
            files_in_source = self.image_files

        if not files_in_source:
            return self.show_error("Δεν υπάρχουν επεξεργασμένες εικόνες για να προστεθούν σε ένα βιβλίο.")

        reply = QMessageBox.question(self, "Επιβεβαίωση Δημιουργίας Βιβλίου",
                                     f"Δημιουργία βιβλίου '{book_name}' και μετακίνηση {len(files_in_source)} σελίδων σε αυτό;",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.progress_dialog = QProgressDialog(f"Δημιουργία βιβλίου '{book_name}'...", "Ακύρωση", 0, len(files_in_source), self)
            self.progress_dialog.setWindowTitle("Μεταφορά Εικόνων")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setAutoClose(True)
            self.progress_dialog.canceled.connect(self.scan_worker.cancel_operation)
            self.progress_dialog.show()

            self.image_processor.clear_cache_for_paths(files_in_source)
            self.scan_worker.create_book(book_name, files_in_source, source_folder)

    @Slot(int, int)
    def on_book_creation_progress(self, processed, total):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.setValue(processed)
            if processed >= total: self.progress_dialog.close()

    # ... (restore_image) ...
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
        if self._is_closing: return
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
            self.transfer_progress_dialog = QProgressDialog("Μεταφορά βιβλίων στα δεδομένα...\n\nΑυτή η διαδικασία μπορεί να διαρκέσει μερικά λεπτά.", None, 0, 0, self)
            self.transfer_progress_dialog.setWindowTitle("Παρακαλώ Περιμένετε")
            self.transfer_progress_dialog.setCancelButton(None)
            self.transfer_progress_dialog.setWindowModality(Qt.WindowModal)
            self.transfer_progress_dialog.show()

            self.transfer_all_btn.setEnabled(False)
            self.status_label.setText(f"Μεταφορά {len(moves_to_confirm)} βιβλίων...")
            QApplication.processEvents()
            self.scan_worker.transfer_all_to_data(moves_to_confirm)

    @Slot(str, str)
    def on_file_operation_complete(self, operation_type, message_or_path):
        if self._is_closing: return
        self.update_work_state(editing=False) # Reset editing state after any successful operation
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")

        if scanner_mode == "dual_scan" and isinstance(self.current_ui_mode, DualScanModeWidget):
            if operation_type in ["crop", "color_fix", "restore", "rotate"]:
                path = message_or_path
                self.update_work_state(processing=False)
                if self.viewer1['viewer'].image_path == path:
                    self.viewer1['viewer'].request_image_load(path, force_reload=True, show_loading_animation=False)
                if self.viewer2['viewer'].image_path == path:
                    self.viewer2['viewer'].request_image_load(path, force_reload=True, show_loading_animation=False)
            
            elif operation_type == "split":
                self.update_work_state(processing=False)
                self.viewer1['viewer'].set_splitting_mode(False)
                self.viewer2['viewer'].set_splitting_mode(False)
                self.image_processor.clear_cache()
                self.status_label.setText("Ανανέωση λίστας αρχείων...")
                self.trigger_full_refresh(force_reload_viewers=True)

            elif operation_type in ["delete", "create_book", "replace_pair"]:
                self.update_work_state(processing=False)
                self.viewer1['viewer'].clear_image()
                self.viewer2['viewer'].clear_image()
                self.status_label.setText("Ανανέωση λίστας αρχείων...")
                self.trigger_full_refresh(force_reload_viewers=True)

        elif scanner_mode == "single_split":
            if operation_type in ["page_split", "replace_single"]:
                filename = os.path.basename(message_or_path)
                self.statusBar().showMessage(f"✓ Αποθηκεύτηκαν οι σελίδες για: {filename}", 4000)
                self.pending_card.set_value(str(self._get_pending_page_count()))
                self.update_total_pages()

            elif operation_type == "delete":
                self.image_processor.clear_cache()
                self.status_label.setText("Ανανέωση λίστας αρχείων...")
                self.trigger_full_refresh(force_reload_viewers=True)


        if operation_type == "transfer_all":
            if hasattr(self, 'transfer_progress_dialog'):
                self.transfer_progress_dialog.close()
                del self.transfer_progress_dialog

            self.transfer_all_btn.setEnabled(True)
            self.statusBar().showMessage(message_or_path, 5000)
            self.trigger_full_refresh()

        self._check_and_update_jump_button_animation()


    def toggle_replace_mode(self):
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        self.replace_mode_active = not self.replace_mode_active
        
        theme = self.get_current_theme()

        if self.replace_mode_active:
            if scanner_mode == "single_split":
                if not self.current_ui_mode.viewer.image_path:
                    QMessageBox.warning(self, "Η Ενέργεια Αποκλείστηκε", "Πρέπει να υπάρχει μια εικόνα στην οθόνη για την αντικατάσταση.")
                    self.replace_mode_active = False
                    return
                self.replace_pair_btn.setText("❌ Ακύρωση")
                self.status_label.setText("Αναμονή για 1 νέα σάρωση για αντικατάσταση της λήψης...")
            else:
                if not self.viewer1['viewer'].image_path or not self.viewer2['viewer'].image_path:
                    QMessageBox.warning(self, "Η Ενέργεια Αποκλείστηκε", "Πρέπει να υπάρχει ένα πλήρες ζεύγος στην οθόνη για την αντικατάσταση.")
                    self.replace_mode_active = False
                    return
                self.replace_pair_btn.setText("❌ Ακύρωση Αντικατάστασης")
                self.status_label.setText("Αναμονή για 2 νέες σαρώσεις για αντικατάσταση του ζεύγους...")

            self.replace_pair_btn.setProperty("class", "destructive filled")
            self.replace_candidates = []

        else:
            if scanner_mode == "single_split":
                self.replace_pair_btn.setText("🔁 Αντικατάσταση Λήψης")
            else:
                self.replace_pair_btn.setText("🔁 Αντικατάσταση Ζεύγους")
            self.replace_pair_btn.setProperty("class", "")
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
        self.toggle_replace_mode()

    def execute_single_replace(self):
        old_path = self.current_ui_mode.viewer.image_path
        new_path = self.replace_candidates[0]

        layout_data = self.current_ui_mode.get_layout_for_image(old_path)
        if not layout_data:
            self.show_error("Δεν βρέθηκε layout για την παλιά εικόνα. Η αντικατάσταση απέτυχε.")
            self.toggle_replace_mode()
            return

        self.image_processor.clear_cache_for_paths([old_path, new_path])
        self.scan_worker.replace_single_image(old_path, new_path, layout_data)
        self.toggle_replace_mode()

    def closeEvent(self, event):
        self._is_closing = True
        self.image_processor.clear_cache()

        if self.watcher and self.watcher.thread.isRunning():
            self.watcher.stop()

        if self.scan_worker_thread.isRunning():
            self.scan_worker_thread.quit()
            self.scan_worker_thread.wait(500)

        if self.image_processor_thread.isRunning():
            self.image_processor_thread.quit()
            self.image_processor_thread.wait(500)
        
        event.accept()
        
    def _check_and_update_jump_button_animation(self):
        scanner_mode = self.app_config.get("scanner_mode", "dual_scan")
        step = 1 if scanner_mode == "single_split" else 2
        has_unseen_images = self.current_index + step < len(self.image_files)

        if has_unseen_images:
            if not self.jump_button_animation.isActive():
                self.jump_button_animation_step = 0
                self.jump_button_animation.start(50)
        else:
            if self.jump_button_animation.isActive():
                self.jump_button_animation.stop()
                self.jump_end_btn.setStyleSheet("")

    def _update_jump_button_animation(self):
        from math import sin, pi
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