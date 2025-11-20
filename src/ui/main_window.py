from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QDockWidget, QMessageBox, QProgressDialog, QDialog
)
from PySide6.QtCore import Qt, QThread, QTimer, Slot, QSize
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap

import os
import re
import time
from collections import deque

from core.config_service import ConfigService
from core.scan_session import ScanSession
from core.constants import THEMES
from services.image_service import ImageService
from services.file_service import FileService
from services.watcher_service import WatcherService
from services.stats_service import StatsService

from .components.sidebar import Sidebar
from .components.bottom_bar import BottomBar
from .components.book_list_item import BookListItemWidget
from .modes.dual_scan_mode import DualScanMode
from .modes.single_split_mode import SingleSplitMode

from .dialogs.settings_dialog import SettingsDialog
from .dialogs.log_viewer_dialog import LogViewerDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DigiPage Scanner Refactored")

        # Services
        self.config_service = ConfigService()
        self.scan_session = ScanSession()
        self.image_service = ImageService()
        self.file_service = FileService()
        self.stats_service = StatsService()

        # Threads
        self.image_thread = QThread()
        self.file_thread = QThread()
        self.stats_thread = QThread()

        self.image_service.moveToThread(self.image_thread)
        self.file_service.moveToThread(self.file_thread)
        self.stats_service.moveToThread(self.stats_thread)

        self.image_thread.start()
        self.file_thread.start()
        self.stats_thread.start()

        # Watcher
        scan_folder = self.config_service.get("scan_folder")
        self.watcher_service = WatcherService(scan_folder)

        # State
        self.is_actively_editing = False
        self.replace_mode_active = False
        self.replace_candidates = []
        self.scan_timestamps = deque(maxlen=20)
        self._is_closing = False
        self._force_reload_next = False

        # UI Setup
        self.setup_ui()
        self.connect_signals()

        # Start Watcher
        self.watcher_service.start()

        # Initial Scan
        QTimer.singleShot(100, self.initial_scan)

    def setup_ui(self):
        # Main Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        content_area = QWidget()
        content_layout = QHBoxLayout(content_area)
        content_layout.setContentsMargins(10,10,10,10)

        self.mode_stack = QStackedWidget()

        # Modes
        self.dual_mode = DualScanMode(self)
        self.single_mode = SingleSplitMode(self)

        self.mode_stack.addWidget(self.dual_mode)
        self.mode_stack.addWidget(self.single_mode)

        content_layout.addWidget(self.mode_stack)
        main_layout.addWidget(content_area)

        # Bottom Bar
        self.bottom_bar = BottomBar()
        main_layout.addWidget(self.bottom_bar)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar_dock = QDockWidget("Controls", self)
        self.sidebar_dock.setWidget(self.sidebar)
        self.sidebar_dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.sidebar_dock)

        # Apply Mode
        self.apply_mode()

    def apply_mode(self):
        mode = self.config_service.get("scanner_mode", "dual_scan")
        if mode == "dual_scan":
            self.mode_stack.setCurrentWidget(self.dual_mode)
        else:
            self.mode_stack.setCurrentWidget(self.single_mode)

        # Refresh logic
        self.update_display()

    def connect_signals(self):
        # Watcher
        self.watcher_service.new_image_detected.connect(self.on_new_image)
        self.watcher_service.scan_folder_changed.connect(self.trigger_refresh)

        # Session
        self.scan_session.file_list_changed.connect(self.update_display)
        self.scan_session.current_index_changed.connect(lambda i: self.update_display())

        # Bottom Bar
        self.bottom_bar.prev_clicked.connect(self.prev_pair)
        self.bottom_bar.next_clicked.connect(self.next_pair)
        self.bottom_bar.jump_end_clicked.connect(self.jump_to_end)
        self.bottom_bar.refresh_clicked.connect(self.trigger_refresh)
        self.bottom_bar.delete_clicked.connect(self.delete_current_pair)
        self.bottom_bar.replace_clicked.connect(self.toggle_replace_mode)

        # Sidebar
        self.sidebar.create_book_requested.connect(self.create_book)
        self.sidebar.transfer_all_requested.connect(self.prepare_transfer)
        self.sidebar.view_log_requested.connect(self.open_log_viewer)
        self.sidebar.settings_requested.connect(self.open_settings)

        # Services
        self.stats_service.stats_updated.connect(self.on_stats_updated)
        self.file_service.operation_complete.connect(self.on_file_op_complete)
        self.file_service.book_creation_progress.connect(self.on_book_progress)
        self.file_service.transfer_preparation_complete.connect(self.on_transfer_prep_complete)

        # Image Service
        self.image_service.image_loaded.connect(self.on_image_loaded)
        self.image_service.file_operation_complete.connect(self.on_file_op_complete)

        # Mode Signals (Dual)
        self.dual_mode.request_image_load.connect(self.image_service.request_image_load)
        self.dual_mode.request_crop.connect(self.image_service.crop_and_save_image)
        self.dual_mode.request_rotation.connect(self.image_service.rotate_crop_and_save)
        self.dual_mode.request_split.connect(self.image_service.split_image)
        self.dual_mode.request_delete.connect(self.file_service.delete_file)
        self.dual_mode.request_restore.connect(self.file_service.restore_image)
        self.dual_mode.editing_started.connect(self.set_editing_active)
        self.dual_mode.editing_finished.connect(self.set_editing_inactive)

        # Mode Signals (Single)
        self.single_mode.request_image_load.connect(self.image_service.request_image_load)
        # self.single_mode.request_split # Single mode does split differently via perform_page_split logic
        self.single_mode.layout_changed.connect(self.image_service.perform_page_split)
        self.single_mode.editing_started.connect(self.set_editing_active)
        self.single_mode.editing_finished.connect(self.set_editing_inactive)

    # --- Logic ---

    def set_editing_active(self): self.is_actively_editing = True
    def set_editing_inactive(self): self.is_actively_editing = False

    def initial_scan(self):
        self.trigger_refresh()

    def trigger_refresh(self, force_reload=False):
        self._force_reload_next = force_reload
        scan_folder = self.config_service.get("scan_folder")
        if not scan_folder or not os.path.isdir(scan_folder):
            return

        files = [os.path.join(scan_folder, f) for f in os.listdir(scan_folder)
                 if os.path.splitext(f)[1].lower() in ['.jpg', '.jpeg', '.png', '.bmp']] # use constant
        self.scan_session.set_files(files)
        self.stats_service.calculate_today_stats()

    def update_display(self):
        if self._is_closing: return

        files = self.scan_session.image_files
        idx = self.scan_session.current_index
        mode = self.config_service.get("scanner_mode", "dual_scan")

        total = len(files)

        if mode == "dual_scan":
            path1 = files[idx] if idx < total else None
            path2 = files[idx+1] if idx+1 < total else None

            # Status
            p1 = idx + 1
            p2 = idx + 2 if path2 else 0
            self.bottom_bar.update_status(f"Pages {p1}-{p2} of {total}")

            # Load
            self.dual_mode.load_images([p for p in [path1, path2] if p])

            self.bottom_bar.prev_btn.setEnabled(idx > 0)
            self.bottom_bar.next_btn.setEnabled(idx + 2 < total)

        else:
            path = files[idx] if idx < total else None
            self.bottom_bar.update_status(f"Image {idx+1} of {total}")

            # Context for single mode
            self.single_mode.set_file_list_context(files)
            self.single_mode.load_images([path] if path else [])

            self.bottom_bar.prev_btn.setEnabled(idx > 0)
            self.bottom_bar.next_btn.setEnabled(idx + 1 < total)

        self._force_reload_next = False

    def on_new_image(self, path):
        if self.replace_mode_active:
            self.replace_candidates.append(path)
            self.check_replace_status()
            return

        self.scan_session.add_file(path)
        self.scan_timestamps.append(time.time())
        self.update_speed_stats()

        # Auto-jump if not editing
        if not self.is_actively_editing:
             self.jump_to_end()

        # Auto Process for Single Mode
        if self.config_service.get("scanner_mode") == "single_split":
            layout = self.single_mode.get_layout_for_image(path)
            if layout:
                self.single_mode.save_layout_data(path, layout)
                QTimer.singleShot(100, lambda: self.image_service.perform_page_split(path, layout))

    def prev_pair(self):
        step = 2 if self.config_service.get("scanner_mode") == "dual_scan" else 1
        self.scan_session.set_index(self.scan_session.current_index - step)

    def next_pair(self):
        step = 2 if self.config_service.get("scanner_mode") == "dual_scan" else 1
        self.scan_session.set_index(self.scan_session.current_index + step)

    def jump_to_end(self):
        step = 2 if self.config_service.get("scanner_mode") == "dual_scan" else 1
        total = len(self.scan_session.image_files)
        if total > 0:
            self.scan_session.set_index(max(0, total - step))

    # --- Replace Mode ---
    def toggle_replace_mode(self):
        self.replace_mode_active = not self.replace_mode_active
        self.bottom_bar.set_replace_mode(self.replace_mode_active)
        self.replace_candidates = []
        if self.replace_mode_active:
            self.bottom_bar.update_status("Waiting for new scans to replace...")

    def check_replace_status(self):
        mode = self.config_service.get("scanner_mode", "dual_scan")
        required = 2 if mode == "dual_scan" else 1

        if len(self.replace_candidates) >= required:
            # Do replace
            idx = self.scan_session.current_index
            files = self.scan_session.image_files

            if mode == "dual_scan":
                 p1 = files[idx] if idx < len(files) else None
                 p2 = files[idx+1] if idx+1 < len(files) else None
                 if p1 and p2:
                     self.file_service.replace_pair(p1, p2, self.replace_candidates[0], self.replace_candidates[1])
            else:
                 p1 = files[idx] if idx < len(files) else None
                 if p1:
                     # Special logic for single split replace - retrieve layout first
                     layout = self.single_mode.get_layout_for_image(p1)
                     self.file_service.replace_single_image_file(p1, self.replace_candidates[0])
                     # Then re-split
                     if layout:
                         QTimer.singleShot(500, lambda: self.image_service.perform_page_split(p1, layout))

            self.toggle_replace_mode() # disable
            self.trigger_refresh(force_reload=True)

    # --- Deletion ---
    def delete_current_pair(self):
        idx = self.scan_session.current_index
        files = self.scan_session.image_files
        mode = self.config_service.get("scanner_mode", "dual_scan")

        to_delete = []
        if mode == "dual_scan":
            if idx < len(files): to_delete.append(files[idx])
            if idx+1 < len(files): to_delete.append(files[idx+1])
        else:
            if idx < len(files): to_delete.append(files[idx])

        if not to_delete: return

        reply = QMessageBox.question(self, "Confirm Delete", f"Delete {len(to_delete)} images?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if mode == "single_split":
                 # Single split delete needs to cleanup artifacts
                 self.file_service.delete_split_image_and_artifacts(to_delete[0])
                 self.single_mode.remove_layout_data(to_delete[0])
            else:
                for p in to_delete:
                    self.file_service.delete_file(p)

            self.trigger_refresh()

    # --- Stats & Sidebar ---
    def update_speed_stats(self):
        if len(self.scan_timestamps) < 2:
            self.sidebar.update_stats("0.0", self.get_pending_count(), 0) # Total updated elsewhere
            return

        delta = self.scan_timestamps[-1] - self.scan_timestamps[0]
        if delta < 1:
             self.sidebar.update_stats("---", self.get_pending_count(), 0)
             return

        count = len(self.scan_timestamps) - 1
        ppm = (count / delta) * 60
        self.sidebar.speed_card.set_value(f"{ppm:.1f}")

    def get_pending_count(self):
        mode = self.config_service.get("scanner_mode", "dual_scan")
        if mode == "single_split":
            scan_folder = self.config_service.get("scan_folder")
            final_folder = os.path.join(scan_folder, 'final')
            if os.path.isdir(final_folder):
                return len([f for f in os.listdir(final_folder) if os.path.splitext(f)[1].lower() in ['.jpg','.png']]) # Should use constant
            return 0
        else:
            return len(self.scan_session.image_files)

    @Slot(dict)
    def on_stats_updated(self, stats):
        self.sidebar.clear_book_list()
        staged = stats.get('staged_book_details', {})
        data_books = stats.get('book_list_data', [])

        # Merge and sort
        # ... (simplified for brevity, assuming similar logic to original)
        # Re-implementing the book list populating logic

        for name, pages in staged.items():
             w = BookListItemWidget(name, "TODAY'S", pages, THEMES["Material Dark"]) # Use current theme
             self.sidebar.add_book_to_list(w)

        for entry in data_books:
             if isinstance(entry, dict):
                 w = BookListItemWidget(entry['name'], "DATA", entry['pages'], THEMES["Material Dark"])
                 self.sidebar.add_book_to_list(w)

        total = stats.get('pages_in_data', 0) + sum(staged.values()) + self.get_pending_count()
        self.sidebar.total_card.set_value(total)
        self.sidebar.pending_card.set_value(self.get_pending_count())

    # --- Actions ---

    def create_book(self, name):
        mode = self.config_service.get("scanner_mode", "dual_scan")
        scan_folder = self.config_service.get("scan_folder")

        src = scan_folder
        files = []

        if mode == "single_split":
            src = os.path.join(scan_folder, 'final')
            if os.path.isdir(src):
                files = [os.path.join(src, f) for f in os.listdir(src)]
        else:
            files = self.scan_session.image_files

        if not files:
             QMessageBox.warning(self, "Empty", "No files to create book.")
             return

        self.file_service.create_book(name, files, src)

        # Progress dialog
        self.progress_dialog = QProgressDialog(f"Creating '{name}'...", "Cancel", 0, len(files), self)
        self.progress_dialog.show()

    def prepare_transfer(self):
        self.file_service.prepare_transfer()

    def on_transfer_prep_complete(self, moves, warnings):
        if not moves and not warnings:
            QMessageBox.information(self, "Info", "Nothing to transfer.")
            return

        msg = f"Ready to transfer {len(moves)} books.\n" + "\n".join(warnings)
        reply = QMessageBox.question(self, "Transfer", msg, QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.file_service.transfer_all_to_data(moves)

    @Slot(str, str)
    def on_file_op_complete(self, op_type, msg):
        if op_type in ['crop', 'rotate', 'split', 'color_fix', 'restore']:
             # Refresh specific image?
             # Msg is path
             self.image_service.request_image_load(msg, force_reload=True)
             if op_type == 'split':
                 # Dual mode split creates new file, so full refresh needed usually
                 # or logic to add it.
                 # Original logic did full refresh
                 self.trigger_refresh(force_reload=True)

        elif op_type in ['delete', 'create_book', 'replace_pair', 'replace_single_file']:
             self.trigger_refresh(force_reload=True)
             if op_type == 'create_book':
                  if hasattr(self, 'progress_dialog'): self.progress_dialog.close()

        elif op_type == 'page_split':
             # Single mode split
             # Just update stats
             self.stats_service.calculate_today_stats()

    @Slot(int, int)
    def on_book_progress(self, curr, total):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.setValue(curr)

    @Slot(str, QPixmap)
    def on_image_loaded(self, path, pixmap):
        # Route to active mode
        mode = self.config_service.get("scanner_mode", "dual_scan")
        if mode == "dual_scan":
            self.dual_mode.on_image_loaded(path, pixmap)
        else:
            self.single_mode.on_image_loaded(path, pixmap)

    # --- Dialogs ---
    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            # Reload config
            # Re-apply theme
            # Restart services if needed (watcher)
            self.config_service = ConfigService() # Reload
            # ... apply updates
            self.apply_mode()
            self.trigger_refresh()

    def open_log_viewer(self):
        dlg = LogViewerDialog(self)
        dlg.exec()

    def closeEvent(self, event):
        self._is_closing = True
        self.watcher_service.stop()
        self.image_thread.quit()
        self.file_thread.quit()
        self.stats_thread.quit()
        event.accept()
