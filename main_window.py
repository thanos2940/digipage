import sys
import os
import re
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QDockWidget, QScrollArea, QLineEdit, QGroupBox, QFormLayout,
    QFrame, QMessageBox, QDialog, QToolButton, QSpacerItem, QSizePolicy, QApplication,
    QProgressDialog, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Slot, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap, QColor

import config
from image_viewer import ImageViewer
from workers import ScanWorker, Watcher, ImageProcessor, natural_sort_key
from settings_dialog import SettingsDialog

# A custom widget for displaying book information in a structured, table-like row.
class BookListItemWidget(QWidget):
    def __init__(self, name, status, pages, theme, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(45)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        # Style for the main row background to highlight transferred books
        if status == "DATA":
            self.setAutoFillBackground(True)
            palette = self.palette()
            highlight_color = config.lighten_color(theme['FRAME_BG'], 0.1)
            palette.setColor(self.backgroundRole(), QColor(highlight_color))
            self.setPalette(palette)
            self.setStyleSheet("border-radius: 5px;")


        name_label = QLabel(name)
        status_label = QLabel(status)
        pages_label = QLabel(f"{pages} pgs")

        # Style for the book name
        name_label.setStyleSheet(f"color: {theme['ON_SURFACE']}; background-color: transparent;")

        # Style for the status pill (less prominent)
        status_stylesheet = """
            padding: 3px 8px;
            border-radius: 9px;
            font-weight: bold;
            font-size: 7pt;
            background-color: transparent;
        """
        if status == "DATA":
            status_stylesheet += f"color: {theme['SUCCESS']};"
        else: # TODAY'S
            status_stylesheet += f"color: {theme['WARNING']};"
        status_label.setStyleSheet(status_stylesheet)
        status_label.setAlignment(Qt.AlignCenter)

        # Style for the page count (more prominent)
        pages_label.setStyleSheet(f"color: {theme['PRIMARY']}; font-weight: bold; font-size: 11pt; background-color: transparent;")
        pages_label.setAlignment(Qt.AlignRight)

        layout.addWidget(name_label, 1) # Add stretch factor to push other elements to the right
        layout.addWidget(status_label)
        layout.addWidget(pages_label)


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner")
        self.app_config = config.load_config()
        self.image_files = []
        self.current_index = 0
        self.is_actively_editing = False # State to control auto-navigation
        
        self._initial_load_done = False
        
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(300) 
        self.update_timer.timeout.connect(self.jump_to_end)

        self.jump_button_animation = QTimer(self)
        self.jump_button_animation.timeout.connect(self._update_jump_button_animation)
        self.jump_button_animation_step = 0

        self.setup_ui()
        self.setup_workers()
        self.connect_signals()
        
    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_load_done:
            QTimer.singleShot(100, self.initial_load)
            self._initial_load_done = True

    def initial_load(self):
        self.trigger_full_refresh()

    def setup_ui(self):
        # The main central widget will be a container with a vertical layout
        main_container = QWidget()
        main_v_layout = QVBoxLayout(main_container)
        main_v_layout.setSpacing(0)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(main_container)

        # This widget holds the viewers and is the main area for the dock widget
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
        
        # Add the main content area (viewers) to the vertical layout
        main_v_layout.addWidget(content_area)

        # Create and add the persistent bottom bar
        self.create_bottom_bar(main_v_layout)
        
        # Create and dock the sidebar
        self.create_sidebar()


    def _create_viewer_panel(self):
        frame = QFrame()
        frame.setObjectName("ViewerFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        
        viewer = ImageViewer()
        viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        theme_data = config.THEMES.get(self.app_config.get("theme"), config.THEMES["Material Dark"])
        primary_color = theme_data.get("PRIMARY", "#b0c6ff")
        tertiary_color = theme_data.get("TERTIARY", "#e2bada")
        viewer.set_theme_colors(primary_color, tertiary_color)

        # Main controls below the image
        controls_panel = QWidget()
        controls_layout = QHBoxLayout(controls_panel)
        controls_layout.setContentsMargins(0, 8, 0, 0)
        
        controls = {}
        # The order of buttons is changed for better workflow
        controls['split'] = QPushButton("Split")
        controls['crop'] = QPushButton("Apply Crop")
        controls['restore'] = QPushButton("Restore")
        controls['delete'] = QPushButton("Delete")

        controls['crop'].setProperty("class", "success filled")
        controls['delete'].setProperty("class", "destructive")
        
        # Initially hide the split mode buttons
        controls['confirm_split'] = QPushButton("Confirm Split")
        controls['confirm_split'].setProperty("class", "success filled")
        controls['confirm_split'].setVisible(False)
        controls['cancel_split'] = QPushButton("Cancel Split")
        controls['cancel_split'].setProperty("class", "destructive")
        controls['cancel_split'].setVisible(False)
        
        controls_layout.addStretch()
        controls_layout.addWidget(controls['split'])
        controls_layout.addWidget(controls['crop'])
        controls_layout.addWidget(controls['restore'])
        controls_layout.addWidget(controls['delete'])
        controls_layout.addWidget(controls['confirm_split'])
        controls_layout.addWidget(controls['cancel_split'])
        controls_layout.addStretch()
        
        layout.addWidget(viewer)
        layout.addWidget(controls_panel)

        panel_widgets = {'frame': frame, 'viewer': viewer, **controls}
        
        # Connect signals
        controls['crop'].clicked.connect(lambda: self.apply_crop(panel_widgets))
        controls['split'].clicked.connect(lambda: self.toggle_split_mode(panel_widgets, True))
        controls['delete'].clicked.connect(lambda: self.delete_single_image(panel_widgets))
        controls['restore'].clicked.connect(lambda: self.restore_image(panel_widgets))
        controls['confirm_split'].clicked.connect(lambda: self.apply_split(panel_widgets))
        controls['cancel_split'].clicked.connect(lambda: self.toggle_split_mode(panel_widgets, False))

        return panel_widgets

    def create_sidebar(self):
        sidebar_dock = QDockWidget("Controls & Stats", self)
        sidebar_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        sidebar_dock.setFeatures(QDockWidget.DockWidgetMovable)
        sidebar_dock.setFixedWidth(320)

        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setSpacing(15)
        sidebar_dock.setWidget(sidebar_widget)
        
        stats_group = QGroupBox("Performance Stats")
        stats_layout = QFormLayout()
        self.stats_labels = {
            "ppm": QLabel("0.0"), "pending": QLabel("0"),
            "staged": QLabel("0"), "total": QLabel("0")
        }
        stats_layout.addRow("Pages/Minute:", self.stats_labels['ppm'])
        stats_layout.addRow("Pending Scans:", self.stats_labels['pending'])
        stats_layout.addRow("Staged Books:", self.stats_labels['staged'])
        stats_layout.addRow("Total Pages Today:", self.stats_labels['total'])
        stats_group.setLayout(stats_layout)

        book_group = QGroupBox("Book Creation")
        book_layout = QVBoxLayout()
        self.book_name_edit = QLineEdit()
        self.book_name_edit.setPlaceholderText("Enter book name (from QR code)...")
        create_book_btn = QPushButton("Create Book")
        create_book_btn.setProperty("class", "filled")
        create_book_btn.clicked.connect(self.create_book)
        book_layout.addWidget(self.book_name_edit)
        book_layout.addWidget(create_book_btn)
        book_group.setLayout(book_layout)

        today_group = QGroupBox("Today's Books")
        today_layout = QVBoxLayout(today_group)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.books_list_widget = QWidget()
        self.books_list_layout = QVBoxLayout(self.books_list_widget)
        self.books_list_layout.setAlignment(Qt.AlignTop)
        self.books_list_layout.setSpacing(4)
        scroll_area.setWidget(self.books_list_widget)
        
        transfer_all_btn = QPushButton("Transfer All to Data")
        transfer_all_btn.clicked.connect(self.transfer_all_books)
        
        self.transfer_progress_bar = QProgressBar()
        self.transfer_progress_bar.setVisible(False)
        self.transfer_status_label = QLabel("")
        self.transfer_status_label.setVisible(False)
        
        today_layout.addWidget(scroll_area)
        today_layout.addWidget(transfer_all_btn)
        today_layout.addWidget(self.transfer_status_label)
        today_layout.addWidget(self.transfer_progress_bar)

        settings_btn = QPushButton("Settings")
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

        self.status_label = QLabel("Pages 0-0 of 0")
        
        self.prev_btn = QPushButton("◀ Previous")
        self.next_btn = QPushButton("Next ▶")
        self.jump_end_btn = QPushButton("Jump to End")
        self.refresh_btn = QPushButton("⟳ Refresh")

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
        
        self.delete_pair_btn = QPushButton("🗑️ Delete Pair")
        self.delete_pair_btn.setProperty("class", "destructive filled")
        self.delete_pair_btn.setMinimumHeight(40)
        self.delete_pair_btn.clicked.connect(self.delete_current_pair)
        
        bottom_bar_layout.addWidget(self.status_label)
        bottom_bar_layout.addStretch()
        bottom_bar_layout.addWidget(self.prev_btn)
        bottom_bar_layout.addWidget(self.next_btn)
        bottom_bar_layout.addWidget(self.jump_end_btn)
        bottom_bar_layout.addWidget(self.refresh_btn)
        bottom_bar_layout.addStretch()
        bottom_bar_layout.addWidget(self.delete_pair_btn)

        main_layout.addWidget(bottom_bar)

    @Slot()
    def trigger_full_refresh(self):
        """A single slot to completely refresh the application state."""
        if self.is_actively_editing:
            return
        self.scan_worker.perform_initial_scan()
        self.scan_worker.calculate_today_stats()

    def wheelEvent(self, event):
        if self.is_actively_editing: return
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
        self.scan_worker.transfer_started.connect(self.on_transfer_started)
        self.scan_worker.transfer_progress.connect(self.on_transfer_progress)
        
        # ImageProcessor signals
        self.image_processor.image_loaded.connect(self.viewer1['viewer'].on_image_loaded)
        self.image_processor.image_loaded.connect(self.viewer2['viewer'].on_image_loaded)
        self.image_processor.processing_complete.connect(self.on_processing_complete)
        self.image_processor.error.connect(self.show_error)

        # ImageViewer -> ImageProcessor
        self.viewer1['viewer'].load_requested.connect(self.image_processor.request_image_load)
        self.viewer2['viewer'].load_requested.connect(self.image_processor.request_image_load)
        self.viewer1['viewer'].rotation_requested.connect(self.image_processor.get_rotated_pixmap)
        self.viewer2['viewer'].rotation_requested.connect(self.image_processor.get_rotated_pixmap)

        # ImageViewer -> MainWindow (for editing state)
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
        # If any viewer is zoomed, we are actively editing.
        self.is_actively_editing = self.viewer1['viewer'].is_zoomed or self.viewer2['viewer'].is_zoomed
        self._check_and_update_jump_button_animation()

    @Slot()
    def on_editing_started(self):
        self.is_actively_editing = True
        self._check_and_update_jump_button_animation()

    @Slot(list)
    def on_initial_scan_complete(self, files):
        self.image_files = files
        
        if self.current_index >= len(self.image_files):
            self.current_index = max(0, len(self.image_files) - 2)

        self.current_index = self.current_index - (self.current_index % 2)

        self.update_display()
        self.stats_labels['pending'].setText(str(len(self.image_files)))

    @Slot(dict)
    def on_stats_updated(self, stats):
        staged_details = stats.get('staged_book_details', {})
        staged_books_count = len(staged_details)
        staged_pages_count = sum(staged_details.values())

        self.stats_labels['staged'].setText(f"{staged_books_count} ({staged_pages_count} pages)")
        total_pages = staged_pages_count + stats.get('pages_in_data', 0) + len(self.image_files)
        self.stats_labels['total'].setText(str(total_pages))

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
        if path not in self.image_files:
            self.image_files.append(path)
            self.image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            
            auto_light = self.app_config.get("auto_lighting_correction_enabled", False)
            auto_color = self.app_config.get("auto_color_correction_enabled", False)
            if auto_light or auto_color:
                QTimer.singleShot(500, lambda p=path: self.image_processor.auto_process_image(p, auto_light, auto_color))

            if not self.is_actively_editing:
                self.update_timer.start()
            
            self._check_and_update_jump_button_animation() # Always check
            self.stats_labels['pending'].setText(str(len(self.image_files)))

    @Slot(str)
    def show_error(self, message):
        QMessageBox.critical(self, "Worker Error", message)

    def update_display(self):
        path1 = self.image_files[self.current_index] if self.current_index < len(self.image_files) else None
        path2 = self.image_files[self.current_index + 1] if (self.current_index + 1) < len(self.image_files) else None

        self.viewer1['viewer'].request_image_load(path1)
        self.viewer2['viewer'].request_image_load(path2)

        total = len(self.image_files)
        page1_num = self.current_index + 1 if path1 else 0
        page2_num = self.current_index + 2 if path2 else 0

        status_text = f"Pages {page1_num}-{page2_num} of {total}" if path2 else f"Page {page1_num} of {total}"
        if not path1: status_text = "No images found."
        self.status_label.setText(status_text)
        
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index + 2 < len(self.image_files))
        self._check_and_update_jump_button_animation()


    def next_pair(self):
        if self.is_actively_editing: return
        if self.current_index + 2 < len(self.image_files):
            self.current_index += 2
            self.update_display()
            self._check_and_update_jump_button_animation()

    def prev_pair(self):
        if self.is_actively_editing: return
        if self.current_index > 0:
            self.current_index -= 2
            self.update_display()
            self._check_and_update_jump_button_animation()

    def jump_to_end(self):
        if not self.image_files: return
        new_index = len(self.image_files) - 2 if len(self.image_files) > 1 else 0
        self.current_index = max(0, new_index)
        self.update_display()
        self.is_actively_editing = False # Jumping to end is a navigation action
        self._check_and_update_jump_button_animation()

    @Slot(str)
    def on_processing_complete(self, path):
        if self.viewer1['viewer'].image_path == path:
            self.viewer1['viewer'].request_image_load(path, force_reload=True)
        if self.viewer2['viewer'].image_path == path:
            self.viewer2['viewer'].request_image_load(path, force_reload=True)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.app_config = config.load_config()
            QApplication.instance().setStyleSheet(config.generate_stylesheet(self.app_config.get("theme")))
            
            theme_data = config.THEMES.get(self.app_config.get("theme"), config.THEMES["Material Dark"])
            primary_color = theme_data.get("PRIMARY", "#b0c6ff")
            tertiary_color = theme_data.get("TERTIARY", "#e2bada")
            self.viewer1['viewer'].set_theme_colors(primary_color, tertiary_color)
            self.viewer2['viewer'].set_theme_colors(primary_color, tertiary_color)
            
            self.image_processor.set_caching_enabled(self.app_config.get("caching_enabled", True))

            if self.watcher:
                self.watcher.stop()
                self.watcher.thread.wait() 
            self.setup_workers()
            self.connect_signals()
            self.trigger_full_refresh()

    def delete_single_image(self, viewer_panel):
        image_path = viewer_panel['viewer'].image_path
        if not image_path: return
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to permanently delete this image?\n\n{os.path.basename(image_path)}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Proactively clear UI and cache before telling worker to delete
            viewer_panel['viewer'].clear_image()
            self.image_processor.clear_cache_for_paths([image_path])
            self.scan_worker.delete_file(image_path)

    def delete_current_pair(self):
        path1 = self.viewer1['viewer'].image_path
        path2 = self.viewer2['viewer'].image_path
        paths_to_delete = [p for p in [path1, path2] if p]
        if not paths_to_delete: return
        file_names = "\n".join([os.path.basename(p) for p in paths_to_delete])
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to permanently delete these images?\n\n{file_names}",
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
        if not book_name: return self.show_error("Book name cannot be empty.")
        if not self.image_files: return self.show_error("There are no scanned images to add to a book.")
        
        reply = QMessageBox.question(self, "Confirm Book Creation",
                                     f"Create book '{book_name}' and move {len(self.image_files)} scans into it?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.progress_dialog = QProgressDialog(f"Creating book '{book_name}'...", "Cancel", 0, len(self.image_files), self)
            self.progress_dialog.setWindowTitle("Transferring Images")
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
        reply = QMessageBox.question(self, "Confirm Restore",
                                     f"Restore the original image? This will overwrite any changes.\n\n{os.path.basename(image_path)}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.image_processor.clear_cache_for_paths([image_path])
            self.scan_worker.restore_image(image_path)

    def transfer_all_books(self):
        self.scan_worker.prepare_transfer()

    @Slot(list, list)
    def on_transfer_preparation_complete(self, moves_to_confirm, warnings):
        if not moves_to_confirm and not warnings:
            QMessageBox.information(self, "No Books", "There are no valid books in the staging folder to transfer.")
            return
            
        moves_details = [f"'{move['book_name']}'\n  -> '{move['final_book_path']}'" for move in moves_to_confirm]
        confirmation_message = "The following books will be transferred:\n\n" + "\n\n".join(moves_details)
        if warnings:
            confirmation_message += "\n\nWarnings (these books will be skipped):\n" + "\n".join(warnings)
        confirmation_message += "\n\nDo you want to proceed?"

        reply = QMessageBox.question(self, "Confirm Transfer", confirmation_message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes: self.scan_worker.transfer_all_to_data(moves_to_confirm)

    @Slot(int, int)
    def on_transfer_started(self, total_books, total_pages):
        self.transfer_progress_bar.setRange(0, total_pages)
        self.transfer_progress_bar.setValue(0)
        self.transfer_progress_bar.setVisible(True)
        self.transfer_status_label.setText(f"Starting transfer of {total_books} books...")
        self.transfer_status_label.setVisible(True)

    @Slot(str, int, int)
    def on_transfer_progress(self, book_name, book_pages_done, total_pages_done):
        self.transfer_progress_bar.setValue(total_pages_done)
        self.transfer_status_label.setText(f"Transferring: {book_name} ({book_pages_done} pages)")

    @Slot(str, str)
    def on_file_operation_complete(self, operation_type, message_or_path):
        """Handles the UI updates after a file operation from the worker is complete."""
        
        if operation_type in ["crop", "restore"]:
            path = message_or_path
            if self.viewer1['viewer'].image_path == path:
                self.viewer1['viewer'].request_image_load(path, force_reload=True)
            if self.viewer2['viewer'].image_path == path:
                self.viewer2['viewer'].request_image_load(path, force_reload=True)
            self.scan_worker.calculate_today_stats()

        elif operation_type in ["split", "delete", "create_book"]:
            self.trigger_full_refresh()

        elif operation_type == "transfer_all":
            self.transfer_progress_bar.setVisible(False)
            self.transfer_status_label.setVisible(False)
            self.scan_worker.calculate_today_stats()
        
        # After any file operation, we are no longer "actively editing" in the sense of
        # auto-navigation being blocked. This allows the jump button to behave correctly.
        self.is_actively_editing = False 
        self._check_and_update_jump_button_animation()


    def apply_crop(self, viewer_panel):
        viewer = viewer_panel['viewer']
        if viewer.image_path and viewer.is_cropping:
            crop_rect = viewer.get_image_space_crop_rect()
            if crop_rect:
                self.image_processor.clear_cache_for_paths([viewer.image_path])
                self.scan_worker.crop_and_save_image(viewer.image_path, crop_rect)

    def toggle_split_mode(self, viewer_panel, enable):
        viewer = viewer_panel['viewer']
        viewer.set_splitting_mode(enable)
        self.is_actively_editing = enable

        # Toggle visibility of the buttons
        viewer_panel['split'].setVisible(not enable)
        viewer_panel['crop'].setVisible(not enable)
        viewer_panel['restore'].setVisible(not enable)
        viewer_panel['delete'].setVisible(not enable)
        
        viewer_panel['confirm_split'].setVisible(enable)
        viewer_panel['cancel_split'].setVisible(enable)
        
        if not enable:
            self._check_and_update_jump_button_animation()


    def apply_split(self, viewer_panel):
        viewer = viewer_panel['viewer']
        if viewer.image_path:
            split_x = viewer.get_split_x_in_image_space()
            if split_x is not None:
                self.image_processor.clear_cache_for_paths([viewer.image_path])
                self.scan_worker.split_image(viewer.image_path, split_x)
        self.toggle_split_mode(viewer_panel, False)


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

