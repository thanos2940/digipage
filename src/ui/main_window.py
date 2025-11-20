from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QMessageBox, QProgressDialog, QApplication
)
from PySide6.QtCore import Qt, QThread, Slot, QTimer
from PySide6.QtGui import QIcon

from ..core import config, theme
from ..core.utils import natural_sort_key
from ..services.scan_service import ScanWorker
from ..services.watcher_service import Watcher
from ..services.image_service import ImageProcessor

# New UI Components
from .components.sidebar import Sidebar
from .components.control_bar import ControlBar
from .components.toast import ToastNotification
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.log_viewer_dialog import LogViewerDialog
from .modes.dual_scan_mode import DualScanModeWidget
from .modes.single_split_mode import SingleSplitModeWidget

import os
import time
from collections import deque
import re

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DigiPage Scanner Pro")
        self.resize(1400, 900)

        # Core State
        self.app_config = config.load_config()
        self.image_files = []
        self.current_index = 0
        self.is_actively_editing = False
        self.replace_mode_active = False
        self.replace_candidates = []
        self._force_reload_on_next_scan = False

        # Performance State
        self.scan_timestamps = deque(maxlen=20)

        # UI Setup
        self._init_ui()
        self._apply_theme()

        # Workers
        self._init_workers()

        # Initial Load
        QTimer.singleShot(100, self.trigger_full_refresh)

    def _apply_theme(self):
        self.setStyleSheet(theme.get_stylesheet())

    def _init_ui(self):
        # Main Container
        main_widget = QWidget()
        main_widget.setObjectName("MainContainer")
        self.setCentralWidget(main_widget)

        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # --- Center Content (Viewer + ControlBar) ---
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(20, 20, 20, 20)
        center_layout.setSpacing(20)

        # Modes Stack
        self.mode_stack = QStackedWidget()

        # Initialize Modes
        self.mode_dual = DualScanModeWidget(self, self.app_config)
        self.mode_split = SingleSplitModeWidget(self)

        self.mode_stack.addWidget(self.mode_dual)
        self.mode_stack.addWidget(self.mode_split)

        # Determine Active Mode
        self._set_active_mode()

        center_layout.addWidget(self.mode_stack)

        # Control Bar
        self.control_bar = ControlBar()
        self.control_bar.prev_clicked.connect(self.prev_pair)
        self.control_bar.next_clicked.connect(self.next_pair)
        self.control_bar.jump_end_clicked.connect(self.jump_to_end)
        self.control_bar.refresh_clicked.connect(self.trigger_full_refresh)
        self.control_bar.replace_clicked.connect(self.toggle_replace_mode)
        self.control_bar.delete_clicked.connect(self.delete_current_pair)

        center_layout.addWidget(self.control_bar)

        # --- Right Sidebar ---
        self.sidebar = Sidebar()
        self.sidebar.create_book_requested.connect(self.create_book)
        self.sidebar.transfer_all_requested.connect(self.transfer_all_books)
        self.sidebar.open_log_requested.connect(self.open_log_viewer)
        self.sidebar.open_settings_requested.connect(self.open_settings)

        # Add to main layout
        main_layout.addWidget(center_container, 1) # Expand
        main_layout.addWidget(self.sidebar, 0) # Fixed width

        # Toast Overlay
        self.toast = ToastNotification(self)

    def _init_workers(self):
        # Scan Service
        self.scan_thread = QThread()
        self.scan_worker = ScanWorker(self.app_config)
        self.scan_worker.moveToThread(self.scan_thread)

        self.scan_worker.initial_scan_complete.connect(self.on_scan_complete)
        self.scan_worker.stats_updated.connect(self.on_stats_updated)
        self.scan_worker.error.connect(self.show_error_toast) # Use Toast
        self.scan_worker.file_operation_complete.connect(self.on_file_op_complete)
        self.scan_worker.book_creation_progress.connect(self.on_book_progress)
        self.scan_worker.transfer_preparation_complete.connect(self.on_transfer_prep_complete)

        self.scan_thread.start()

        # Image Processor
        self.img_thread = QThread()
        self.image_processor = ImageProcessor()
        self.image_processor.set_caching_enabled(self.app_config.get("caching_enabled", True))
        self.image_processor.moveToThread(self.img_thread)

        self.image_processor.image_loaded.connect(self._on_image_loaded)
        self.image_processor.error.connect(lambda e: self.show_error_toast(e)) # Simple error

        self.img_thread.start()

        # Watcher
        scan_folder = self.app_config.get("scan_folder")
        if scan_folder and os.path.isdir(scan_folder):
            self.watcher = Watcher(scan_folder)
            self.watcher.new_image_detected.connect(self.on_new_image)
            self.watcher.scan_folder_changed.connect(self.trigger_full_refresh)
            self.watcher.thread.start()

    def _set_active_mode(self):
        mode = self.app_config.get("scanner_mode", "dual_scan")
        if mode == "dual_scan":
            self.mode_stack.setCurrentWidget(self.mode_dual)
            self.current_ui_mode = self.mode_dual
            self.viewer1 = self.mode_dual.viewer1
            self.viewer2 = self.mode_dual.viewer2
        else:
            self.mode_stack.setCurrentWidget(self.mode_split)
            self.current_ui_mode = self.mode_split
            self.viewer1 = None
            self.viewer2 = None

    # --- Mode Interface Connectors ---
    # The Modes (Dual/Single) need access to worker functions.
    # We bridge them here.

    @Slot(str, dict)
    def perform_page_split(self, source_path, layout_data):
        self.scan_worker.perform_page_split(source_path, layout_data)

    @Slot(object)
    def apply_crop(self, viewer_panel):
        viewer = viewer_panel['viewer']
        if viewer.image_path and viewer.interaction_mode == InteractionMode.CROPPING:
            crop_rect = viewer.get_image_space_crop_rect()
            if crop_rect:
                self.image_processor.clear_cache_for_paths([viewer.image_path])
                self.scan_worker.crop_and_save_image(viewer.image_path, crop_rect)

    @Slot(object)
    def apply_color_fix(self, viewer_panel):
        if viewer_panel['viewer'].image_path:
            path = viewer_panel['viewer'].image_path
            self.image_processor.clear_cache_for_paths([path])
            self.scan_worker.correct_color_and_save(path)
            self.toast.show_message("Color correction applied")

    @Slot(object)
    def delete_single_image(self, viewer_panel):
        path = viewer_panel['viewer'].image_path
        if path:
            self.image_processor.clear_cache_for_paths([path])
            self.scan_worker.delete_file(path)

    @Slot(object)
    def restore_image(self, viewer_panel):
        path = viewer_panel['viewer'].image_path
        if path:
            self.image_processor.clear_cache_for_paths([path])
            self.scan_worker.restore_image(path)

    @Slot(object, bool)
    def toggle_rotate_mode(self, viewer_panel, enable):
        viewer_panel['viewer'].set_rotating_mode(enable)
        self.is_actively_editing = enable
        if enable:
            viewer_panel['controls_stack'].setCurrentIndex(2)
        else:
            viewer_panel['controls_stack'].setCurrentIndex(0)

    @Slot(object, bool)
    def toggle_split_mode(self, viewer_panel, enable):
        viewer_panel['viewer'].set_splitting_mode(enable)
        self.is_actively_editing = enable
        if enable:
            viewer_panel['controls_stack'].setCurrentIndex(1)
        else:
            viewer_panel['controls_stack'].setCurrentIndex(0)

    @Slot(object)
    def apply_split(self, viewer_panel):
        viewer = viewer_panel['viewer']
        if viewer.image_path:
            split_x = viewer.get_split_x_in_image_space()
            if split_x:
                 self.image_processor.clear_cache_for_paths([viewer.image_path])
                 self.scan_worker.split_image(viewer.image_path, split_x)
        self.toggle_split_mode(viewer_panel, False)


    # --- Event Handlers ---

    @Slot(str, object)
    def _on_image_loaded(self, path, pixmap):
        # Dispatch to correct viewer
        if self.current_ui_mode == self.mode_dual:
            self.mode_dual.viewer1['viewer'].on_image_loaded(path, pixmap)
            self.mode_dual.viewer2['viewer'].on_image_loaded(path, pixmap)
        elif self.current_ui_mode == self.mode_split:
            self.mode_split.viewer.on_image_loaded(path, pixmap)

    @Slot()
    def trigger_full_refresh(self):
        self.scan_worker.perform_initial_scan()
        self.scan_worker.calculate_today_stats()

    @Slot(list)
    def on_scan_complete(self, files):
        self.image_files = files
        self._update_view()

        # Update sidebar counts
        self._update_sidebar_stats()

    def _update_view(self):
        # Logic to load images into viewers based on current_index
        total = len(self.image_files)
        mode = self.app_config.get("scanner_mode", "dual_scan")

        if mode == "dual_scan":
            path1 = self.image_files[self.current_index] if self.current_index < total else None
            path2 = self.image_files[self.current_index + 1] if self.current_index + 1 < total else None

            self.mode_dual.viewer1['viewer'].request_image_load(path1)
            self.mode_dual.viewer2['viewer'].request_image_load(path2)

            status = f"Pages {self.current_index+1}-{self.current_index+2} of {total}" if path2 else f"Page {self.current_index+1} of {total}"
            self.control_bar.set_status(status)

        else:
            path = self.image_files[self.current_index] if self.current_index < total else None
            self.mode_split.load_image(path)
            status = f"Image {self.current_index+1} of {total}"
            self.control_bar.set_status(status)

        # Enable/Disable nav
        step = 1 if mode == "single_split" else 2
        self.control_bar.prev_btn.setEnabled(self.current_index > 0)
        self.control_bar.next_btn.setEnabled(self.current_index + step < total)

    @Slot(str)
    def on_new_image(self, path):
        if self.replace_mode_active:
            self.replace_candidates.append(path)
            self._check_replace_condition()
            return

        if path not in self.image_files:
            self.image_files.append(path)
            self.image_files.sort(key=natural_sort_key)

            # Record stats
            self.scan_timestamps.append(time.time())
            self._update_sidebar_stats()

            # Auto-process
            self._auto_process_new_image(path)

            # Auto-jump if not editing
            if not self.is_actively_editing:
                self.jump_to_end()
            else:
                self.toast.show_message("New scan received", "info")

    def _auto_process_new_image(self, path):
         mode = self.app_config.get("scanner_mode", "dual_scan")
         if mode == "single_split":
             layout = self.mode_split.get_layout_for_image(path)
             if layout:
                 self.mode_split.save_layout_data(path, layout)
                 QTimer.singleShot(100, lambda: self.perform_page_split(path, layout))
         else:
             # Dual scan auto-correct
             auto_light = self.app_config.get("auto_lighting_correction_enabled", False)
             auto_color = self.app_config.get("auto_color_correction_enabled", False)
             if auto_light or auto_color:
                 QTimer.singleShot(300, lambda: self.image_processor.auto_process_image(path, auto_light, auto_color))

    def _update_sidebar_stats(self):
        # Speed
        if len(self.scan_timestamps) > 1:
            duration = self.scan_timestamps[-1] - self.scan_timestamps[0]
            ppm = (len(self.scan_timestamps) - 1) / duration * 60 if duration > 0 else 0
            speed_text = f"{ppm:.1f}"
        else:
            speed_text = "0.0"

        # Pending
        mode = self.app_config.get("scanner_mode", "dual_scan")
        pending = 0
        if mode == "single_split":
             scan_folder = self.app_config.get("scan_folder")
             final_folder = os.path.join(scan_folder, 'final')
             if os.path.isdir(final_folder):
                 pending = len([f for f in os.listdir(final_folder) if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS])
        else:
            pending = len(self.image_files)

        total = self.scan_worker.staged_pages_count if hasattr(self.scan_worker, 'staged_pages_count') else 0
        # We rely on on_stats_updated for exact total usually, but we can pass placeholders
        self.sidebar.update_stats(speed_text, str(pending), str(total)) # Total will update via signal

    @Slot(dict)
    def on_stats_updated(self, stats):
        staged = stats.get('staged_book_details', {})
        total = sum(staged.values()) + stats.get('pages_in_data', 0)

        # Update Book List
        books_data = []
        # Staged
        for name, pages in staged.items():
            books_data.append({'name': name, 'status': "TODAY'S", 'pages': pages})
        # Data
        for entry in stats.get('book_list_data', []):
            books_data.append({'name': entry.get('name'), 'status': "DATA", 'pages': entry.get('pages')})

        self.sidebar.update_book_list(books_data)

        # Update Total Card
        # Re-fetch other stats to update the whole block
        self._update_sidebar_stats() # This updates speed/pending
        self.sidebar.total_card.set_value(str(total)) # Override total

    # --- Actions ---

    def next_pair(self):
        step = 1 if self.app_config.get("scanner_mode") == "single_split" else 2
        if self.current_index + step < len(self.image_files):
            self.current_index += step
            self._update_view()

    def prev_pair(self):
        step = 1 if self.app_config.get("scanner_mode") == "single_split" else 2
        if self.current_index > 0:
            self.current_index = max(0, self.current_index - step)
            self._update_view()

    def jump_to_end(self):
        step = 1 if self.app_config.get("scanner_mode") == "single_split" else 2
        total = len(self.image_files)
        if total > 0:
            self.current_index = max(0, total - step)
            self._update_view()

    def toggle_replace_mode(self):
        self.replace_mode_active = not self.replace_mode_active
        self.replace_candidates = []
        self.control_bar.set_replace_active(self.replace_mode_active)
        if self.replace_mode_active:
            self.toast.show_message("Replace Mode: Scan new pages to replace current view.", "info")

    def _check_replace_condition(self):
        mode = self.app_config.get("scanner_mode", "dual_scan")
        required = 1 if mode == "single_split" else 2

        if len(self.replace_candidates) >= required:
            # Ready to replace
            if mode == "dual_scan":
                old1 = self.mode_dual.viewer1['viewer'].image_path
                old2 = self.mode_dual.viewer2['viewer'].image_path
                new1, new2 = self.replace_candidates[0], self.replace_candidates[1]
                self.scan_worker.replace_pair(old1, old2, new1, new2)
            else:
                old = self.mode_split.viewer.image_path
                new = self.replace_candidates[0]
                # Get layout
                layout = self.mode_split.get_layout_for_image(old)
                self.scan_worker.replace_single_image(old, new, layout)

            self.toggle_replace_mode() # Reset

    def delete_current_pair(self):
        # Simple delete logic
        mode = self.app_config.get("scanner_mode", "dual_scan")
        if mode == "dual_scan":
            path1 = self.mode_dual.viewer1['viewer'].image_path
            path2 = self.mode_dual.viewer2['viewer'].image_path
            paths = [p for p in [path1, path2] if p]
            if paths:
                 for p in paths: self.scan_worker.delete_file(p)
        else:
            path = self.mode_split.viewer.image_path
            if path:
                self.mode_split.remove_layout_data(path)
                self.scan_worker.delete_split_image_and_artifacts(path)

    # --- Dialogs & External ---

    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.app_config = config.load_config()
            self._set_active_mode()
            self.trigger_full_refresh()

    def open_log_viewer(self):
        dlg = LogViewerDialog(self)
        dlg.exec()

    def create_book(self, name):
        # Gather files
        mode = self.app_config.get("scanner_mode", "dual_scan")
        scan_folder = self.app_config.get("scan_folder")

        source = scan_folder
        if mode == "single_split":
            source = os.path.join(scan_folder, 'final')
            files = [os.path.join(source, f) for f in os.listdir(source) if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS]
        else:
            files = self.image_files

        if not files:
            self.toast.show_message("No images to create book.", "error")
            return

        self.scan_worker.create_book(name, files, source)
        self.toast.show_message(f"Creating book '{name}'...", "info")

    def transfer_all_books(self):
        self.scan_worker.prepare_transfer()

    # --- Signal Handlers ---

    @Slot(str, str)
    def on_file_op_complete(self, op_type, msg):
        self.toast.show_message(f"Operation Complete: {op_type}", "success")
        self.trigger_full_refresh()

    @Slot(int, int)
    def on_book_progress(self, current, total):
        # We could show a progress bar here, or just toast updates on finish
        pass

    @Slot(list, list)
    def on_transfer_prep_complete(self, moves, warnings):
        if not moves:
            self.toast.show_message("No books to transfer.", "info")
            return

        reply = QMessageBox.question(self, "Transfer", f"Transfer {len(moves)} books?")
        if reply == QMessageBox.Yes:
             self.scan_worker.transfer_all_to_data(moves)

    def show_error_toast(self, msg):
        self.toast.show_message(str(msg), "error")

    # --- Close ---
    def closeEvent(self, event):
        self._is_closing = True
        # Cleanup threads
        self.watcher.stop()
        self.scan_worker.cancel_operation()
        event.accept()
