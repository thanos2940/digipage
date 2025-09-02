import os
import sys
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QDockWidget, QListWidget, QLineEdit, QGroupBox,
    QSlider, QFrame, QMessageBox
)

import config
from settings_dialog import SettingsDialog
from image_viewer import ImageViewer
from workers import ScanWorker, DirectoryWatcher

class MainWindow(QMainWindow):
    # Signal to request a background task from the scan worker
    request_initial_scan = Signal(str)
    request_stats_update = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DigiPage Scanner")
        self.resize(1600, 900)

        # --- Application State ---
        self.config_data = config.load_config()
        self.image_paths = []
        self.current_index = 0

        # --- UI Components ---
        self.viewer_left = ImageViewer()
        self.viewer_right = ImageViewer()
        self.sidebar = self._create_sidebar()
        self.addDockWidget(Qt.RightDockWidgetArea, self.sidebar)

        self.setCentralWidget(self._create_central_widget())
        self.setStatusBar(self._create_bottom_bar())

        # --- Worker Threads ---
        self._setup_workers()

        # --- Initial Actions ---
        self.update_navigation_buttons()
        self.trigger_initial_scan()
        self.trigger_stats_update()

    def _create_central_widget(self):
        """Creates the main area with two image viewers and their controls."""
        container = QWidget()
        main_layout = QHBoxLayout(container)

        # Left viewer and controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(self.viewer_left)
        left_layout.addWidget(self._create_image_controls(self.viewer_left, "left"))

        # Right viewer and controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.viewer_right)
        right_layout.addWidget(self._create_image_controls(self.viewer_right, "right"))

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        return container

    def _create_image_controls(self, viewer: ImageViewer, side: str):
        """Creates the control panel for a single image viewer."""
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QGridLayout(panel)

        crop_btn = QPushButton("Crop")
        split_btn = QPushButton("Split")
        restore_btn = QPushButton("Restore")
        delete_btn = QPushButton("Delete")

        crop_btn.setCheckable(True)
        crop_btn.toggled.connect(viewer.set_cropping_mode)
        restore_btn.clicked.connect(viewer.reset_view)
        # TODO: Connect delete_btn and split_btn

        rot_slider = QSlider(Qt.Horizontal)
        rot_slider.setRange(-45, 45)
        rot_slider.setValue(0)
        rot_slider.setToolTip("Rotation")

        layout.addWidget(crop_btn, 0, 0)
        layout.addWidget(split_btn, 0, 1)
        layout.addWidget(restore_btn, 0, 2)
        layout.addWidget(delete_btn, 0, 3)
        layout.addWidget(QLabel("Rotate:"), 1, 0)
        layout.addWidget(rot_slider, 1, 1, 1, 3)

        return panel

    def _create_sidebar(self):
        """Creates the right-hand dock widget."""
        sidebar = QDockWidget("Controls & Stats")
        sidebar.setAllowedAreas(Qt.RightDockWidgetArea)
        sidebar.setFeatures(QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetMovable)

        container = QWidget()
        layout = QVBoxLayout(container)

        # --- Stats Group ---
        stats_group = QGroupBox("Performance Stats")
        stats_layout = QGridLayout()
        self.stats_pages_min_label = QLabel("0")
        self.stats_pending_label = QLabel("0")
        self.stats_staged_label = QLabel("0")
        self.stats_total_today_label = QLabel("0")
        stats_layout.addWidget(QLabel("Pages/Minute:"), 0, 0)
        stats_layout.addWidget(self.stats_pages_min_label, 0, 1)
        stats_layout.addWidget(QLabel("Pending Scans:"), 1, 0)
        stats_layout.addWidget(self.stats_pending_label, 1, 1)
        stats_layout.addWidget(QLabel("Staged Books:"), 2, 0)
        stats_layout.addWidget(self.stats_staged_label, 2, 1)
        stats_layout.addWidget(QLabel("Total Pages Today:"), 3, 0)
        stats_layout.addWidget(self.stats_total_today_label, 3, 1)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # --- Book Creation ---
        book_group = QGroupBox("Book Creation")
        book_layout = QVBoxLayout()
        self.book_name_edit = QLineEdit()
        self.book_name_edit.setPlaceholderText("Scan QR Code for Book Name")
        create_book_btn = QPushButton("Create Book")
        book_layout.addWidget(self.book_name_edit)
        book_layout.addWidget(create_book_btn)
        book_group.setLayout(book_layout)
        layout.addWidget(book_group)

        # --- Today's Books ---
        today_group = QGroupBox("Today's Books")
        today_layout = QVBoxLayout()
        self.today_books_list = QListWidget()
        today_layout.addWidget(self.today_books_list)
        today_group.setLayout(today_layout)
        layout.addWidget(today_group)

        layout.addStretch()

        # --- Main Actions ---
        transfer_btn = QPushButton("Transfer all to Data")
        transfer_btn.setStyleSheet("background-color: #77DD77; color: #2E2E2E;")
        layout.addWidget(transfer_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings_dialog)
        layout.addWidget(settings_btn)

        sidebar.setWidget(container)
        return sidebar

    def _create_bottom_bar(self):
        """Creates the status bar with navigation controls."""
        bar = QWidget()
        layout = QHBoxLayout(bar)

        self.prev_pair_btn = QPushButton("<< Previous Pair")
        self.next_pair_btn = QPushButton("Next Pair >>")
        self.jump_end_btn = QPushButton("Jump to End")
        self.status_label = QLabel("Pages 0-0 of 0")
        delete_pair_btn = QPushButton("Delete Pair")
        delete_pair_btn.setStyleSheet("background-color: #FF5252;")

        self.prev_pair_btn.clicked.connect(self.show_previous_pair)
        self.next_pair_btn.clicked.connect(self.show_next_pair)
        self.jump_end_btn.clicked.connect(self.jump_to_end)

        layout.addWidget(self.prev_pair_btn)
        layout.addWidget(self.next_pair_btn)
        layout.addWidget(self.jump_end_btn)
        layout.addStretch()
        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(delete_pair_btn)

        return bar

    def _setup_workers(self):
        """Initializes and starts the background worker threads."""
        # --- Scan Worker ---
        self.scan_thread = QThread()
        self.scan_worker = ScanWorker()
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_worker.initial_scan_complete.connect(self.on_initial_scan_complete)
        self.scan_worker.stats_updated.connect(self.update_stats_display)
        self.scan_worker.error.connect(self.on_worker_error)
        self.request_initial_scan.connect(self.scan_worker.perform_initial_scan)
        self.request_stats_update.connect(self.scan_worker.calculate_today_stats)
        self.scan_thread.start()

        # --- Directory Watcher ---
        self.watch_thread = QThread()
        self.watcher = DirectoryWatcher(self.config_data.get("scan_folder"))
        self.watcher.moveToThread(self.watch_thread)
        self.watcher.new_image_detected.connect(self.add_new_image)
        self.watcher.error.connect(self.on_worker_error)
        self.watch_thread.started.connect(self.watcher.start_watching)
        self.watch_thread.start()

    # --- Slots and Logic ---

    @Slot()
    def trigger_initial_scan(self):
        self.request_initial_scan.emit(self.config_data.get("scan_folder"))

    @Slot()
    def trigger_stats_update(self):
        self.request_stats_update.emit(self.config_data.get("today_books_folder"))

    @Slot(list)
    def on_initial_scan_complete(self, files: list):
        self.image_paths = files
        self.stats_pending_label.setText(str(len(self.image_paths)))
        self.current_index = 0
        self.display_current_pair()
        self.update_navigation_buttons()

    @Slot(str)
    def add_new_image(self, path: str):
        """Adds a newly detected image to the list."""
        self.image_paths.append(path)
        self.stats_pending_label.setText(str(len(self.image_paths) - self.current_index))

        # If user is at the end, show the new image
        if self.current_index >= len(self.image_paths) - 2:
            self.display_current_pair()

        self.update_navigation_buttons()

    @Slot(dict)
    def update_stats_display(self, stats: dict):
        self.stats_pages_min_label.setText(str(stats.get("pages_per_minute", 0)))
        # Pending scans is managed by the file list length, not this stat
        self.stats_staged_label.setText(str(stats.get("staged_books", 0)))
        self.stats_total_today_label.setText(str(stats.get("total_pages_today", 0)))

    def display_current_pair(self):
        """Loads the current pair of images into the viewers."""
        num_images = len(self.image_paths)

        # Left image
        if self.current_index < num_images:
            self.viewer_left.load_image(self.image_paths[self.current_index])
        else:
            self.viewer_left.load_image(None) # Clear viewer

        # Right image
        if self.current_index + 1 < num_images:
            self.viewer_right.load_image(self.image_paths[self.current_index + 1])
        else:
            self.viewer_right.load_image(None) # Clear viewer

        self.status_label.setText(f"Pages {self.current_index + 1}-{self.current_index + 2} of {num_images}")
        self.stats_pending_label.setText(str(max(0, num_images - (self.current_index + 2))))

    def update_navigation_buttons(self):
        """Enables or disables navigation buttons based on the current index."""
        self.prev_pair_btn.setEnabled(self.current_index > 0)
        self.next_pair_btn.setEnabled(self.current_index + 2 < len(self.image_paths))
        self.jump_end_btn.setEnabled(self.current_index + 2 < len(self.image_paths))

    @Slot()
    def show_next_pair(self):
        if self.current_index + 2 < len(self.image_paths):
            self.current_index += 2
            self.display_current_pair()
            self.update_navigation_buttons()

    @Slot()
    def show_previous_pair(self):
        if self.current_index > 0:
            self.current_index -= 2
            self.display_current_pair()
            self.update_navigation_buttons()

    @Slot()
    def jump_to_end(self):
        num_images = len(self.image_paths)
        # Go to the start of the last pair
        self.current_index = max(0, num_images - (num_images % 2 or 2))
        self.display_current_pair()
        self.update_navigation_buttons()

    @Slot()
    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.settings_saved.connect(self.on_settings_saved)
        dialog.exec()

    @Slot()
    def on_settings_saved(self):
        """Called when settings are saved to update the application."""
        QMessageBox.information(self, "Settings Updated", "Settings have been saved. Please restart the application for all changes to take effect.")
        # A more robust implementation would selectively restart workers
        self.config_data = config.load_config()

    @Slot(str)
    def on_worker_error(self, message: str):
        print(f"ERROR from worker: {message}")
        # Optionally show a non-modal message to the user
        self.statusBar().showMessage(f"Error: {message}", 5000)

    def closeEvent(self, event):
        """Gracefully shut down worker threads on application close."""
        print("Closing application. Stopping worker threads...")
        self.watcher.stop_watching()
        self.watch_thread.quit()
        self.scan_thread.quit()

        self.watch_thread.wait(5000)
        self.scan_thread.wait(5000)

        print("Threads stopped.")
        event.accept()
