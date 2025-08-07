import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox, QFrame, QMessageBox, QListWidget, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, QTimer
from .styles import DARK_STYLE_SHEET
from .photo_viewer import PhotoViewer
from .workers import WatchdogWorker, FileOperationWorker, StatsWorker, InitialScanWorker
from .utils import natural_sort_key
import os
import time
from PIL import Image

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}

class MainWindow(QMainWindow):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("DigiPage Scanner")
        self.setGeometry(100, 100, 1600, 900)
        self.setStyleSheet(DARK_STYLE_SHEET)

        self.image_files = []
        self.current_index = 0

        self.setup_ui()
        self.setup_workers()

    def setup_ui(self):
        # --- Central Widget and Main Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- Image Display Area (Left and Center) ---
        image_display_area = QFrame()
        image_display_layout = QVBoxLayout(image_display_area)

        # This will hold the two PhotoViewer widgets
        image_panes_layout = QHBoxLayout()

        # Add PhotoViewer widgets and their control areas
        self.photo_viewer_left = PhotoViewer()
        self.photo_viewer_right = PhotoViewer()

        left_pane = self._create_image_pane(self.photo_viewer_left)
        right_pane = self._create_image_pane(self.photo_viewer_right)

        image_panes_layout.addWidget(left_pane)
        image_panes_layout.addWidget(right_pane)

        # This will hold the control bar at the bottom
        control_bar = self._create_control_bar()

        image_display_layout.addLayout(image_panes_layout, 1) # 1 stretch factor
        image_display_layout.addWidget(control_bar)

        # --- Sidebar (Right) ---
        sidebar = self._create_sidebar()
        sidebar.setFixedWidth(300)

        main_layout.addWidget(image_display_area, 1) # 1 stretch factor
        main_layout.addWidget(sidebar)

        # --- Status Bar ---
        self.statusBar().showMessage("Ready")

    def setup_workers(self):
        # Setup and start the WatchdogWorker
        self.watchdog_thread = QThread()
        self.watchdog_worker = WatchdogWorker(self.settings['scan'])
        self.watchdog_worker.moveToThread(self.watchdog_thread)
        self.watchdog_thread.started.connect(self.watchdog_worker.run)
        self.watchdog_worker.new_image_found.connect(self._add_new_image)
        self.watchdog_thread.start()

        # Setup the FileOperationWorker
        self.file_op_thread = QThread()
        self.file_op_worker = FileOperationWorker()
        self.file_op_worker.moveToThread(self.file_op_thread)
        self.file_op_worker.operation_successful.connect(self._on_operation_successful)
        self.file_op_worker.operation_failed.connect(self._on_operation_failed)
        self.file_op_thread.start()

        # Setup the StatsWorker
        self.stats_thread = QThread()
        self.stats_worker = StatsWorker(
            scan_directory=self.settings['scan'],
            todays_books_folder=self.settings['today'],
            books_log_file="books_complete_log.json" # Hardcoded for now
        )
        self.stats_worker.moveToThread(self.stats_thread)
        self.stats_thread.started.connect(self.stats_worker.run)
        self.stats_worker.stats_updated.connect(self._update_stats_display)
        self.stats_thread.start()

        # Setup and start the InitialScanWorker
        self.initial_scan_thread = QThread()
        self.initial_scan_worker = InitialScanWorker(self.settings['scan'])
        self.initial_scan_worker.moveToThread(self.initial_scan_thread)
        self.initial_scan_thread.started.connect(self.initial_scan_worker.run)
        self.initial_scan_worker.scan_complete.connect(self._on_initial_scan_complete)
        self.initial_scan_worker.scan_error.connect(self._on_initial_scan_error)
        # Clean up the thread when it's finished
        self.initial_scan_worker.scan_complete.connect(self.initial_scan_thread.quit)
        self.initial_scan_worker.scan_error.connect(self.initial_scan_thread.quit)
        self.initial_scan_thread.start()

    def _on_initial_scan_complete(self, image_files):
        """Slot to handle the results of the initial directory scan."""
        self.image_files = image_files
        self.current_index = 0
        self.update_display()
        self.initial_scan_thread.deleteLater() # Mark thread for deletion

    def _on_initial_scan_error(self, error_message):
        """Slot to handle errors from the initial scan."""
        self.statusBar().showMessage(error_message, 5000)
        self.initial_scan_thread.deleteLater()

    def _add_new_image(self, path):
        """Slot to handle new images found by the watchdog."""
        if path not in self.image_files and os.path.exists(path):
            self.image_files.append(path)
            self.image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

            # Notify stats worker for live performance
            if hasattr(self, 'stats_worker'):
                self.stats_worker.scan_timestamps.append(time.time())

            self.update_display()

    def update_display(self):
        """Updates the image viewers to show the current pair."""
        # Left image
        left_path_index = self.current_index
        if left_path_index < len(self.image_files):
            self.photo_viewer_left.set_image(self.image_files[left_path_index])
        else:
            self.photo_viewer_left.clear()

        # Right image
        right_path_index = self.current_index + 1
        if right_path_index < len(self.image_files):
            self.photo_viewer_right.set_image(self.image_files[right_path_index])
        else:
            self.photo_viewer_right.clear()

        # Update status bar
        total_pages = len(self.image_files)
        if not total_pages:
            self.statusBar().showMessage("Waiting for images...")
        else:
            current_page_num = self.current_index + 1
            has_right_page = (self.current_index + 1) < total_pages
            status_text = f"Pages {current_page_num}-{current_page_num+1} of {total_pages}" if has_right_page else f"Page {current_page_num} of {total_pages}"
            self.statusBar().showMessage(status_text)

    def _on_operation_successful(self, op_type, message):
        self.statusBar().showMessage(message, 3000) # Show for 3 seconds
        if op_type == "save_image":
            # After saving, we need to reload the image to get the new state
            viewer = self.sender().parent() # This is a bit of a hack to get the viewer
            if viewer and hasattr(viewer, 'image_path'):
                 viewer.set_image(viewer.image_path)
            else:
                 self.update_display()
        elif op_type == "create_book":
            self.image_files.clear()
            self.current_index = 0
            self.book_name_entry.clear()
            self.update_display()
            # We should also trigger a refresh of the "Today's Books" list
        elif op_type == "delete_pair":
            # This is tricky because the worker deleted the files, we need to resync our list
            # A simple approach is to re-scan the directory
            self.image_files = [f for f in self.image_files if os.path.exists(f)]
            if self.current_index >= len(self.image_files):
                self.current_index = max(0, len(self.image_files) - 2)
            self.update_display()

    def _on_operation_failed(self, op_type, error_message):
        self.statusBar().showMessage(f"Error during {op_type}: {error_message}", 5000)

    def closeEvent(self, event):
        """Ensure worker threads are stopped cleanly."""
        print("Closing application, stopping workers...")
        self.watchdog_worker.stop()
        self.watchdog_thread.quit()
        self.watchdog_thread.wait(2000)

        self.file_op_thread.quit()
        self.file_op_thread.wait(2000)

        self.stats_worker.stop()
        self.stats_thread.quit()
        self.stats_thread.wait(2000)

        event.accept()

    def initial_scan(self):
        """Performs an initial scan of the scan directory on startup."""
        try:
            self.image_files = [
                os.path.join(self.settings['scan'], f)
                for f in os.listdir(self.settings['scan'])
                if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
            ]
            self.image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            self.current_index = 0
            # Defer the first display update to prevent blocking the constructor
            QTimer.singleShot(0, self.update_display)
        except FileNotFoundError:
            self.statusBar().showMessage(f"Error: Scan directory not found at {self.settings['scan']}", 5000)
        except Exception as e:
            self.statusBar().showMessage(f"An error occurred during initial scan: {e}", 5000)

    def _update_stats_display(self, stats):
        """Slot to update the statistics labels in the sidebar."""
        self.scans_min_label.setText(f"Performance: {stats['scans_per_minute']:.1f} pages/min")
        self.books_today_label.setText(f"Pending Books: {stats['books_in_today']} ({stats['pages_in_today']} pages)")

        # Total pages = pending scans + pages in today's books + pages in data
        total_pages = len(self.image_files) + stats['pages_in_today'] + stats['pages_in_data']
        self.total_scans_today_label.setText(f"Total Pages Today: {total_pages}")

        # Also update the pending scans count
        self.current_scans_label.setText(f"Pending Scans: {len(self.image_files)}")

    def create_book(self):
        book_name = self.book_name_entry.text().strip()
        if not book_name:
            QMessageBox.warning(self, "Input Error", "Please provide a book name.")
            return

        if not self.image_files:
            QMessageBox.information(self, "No Images", "There are no images in the scan folder to create a book.")
            return

        self.file_op_worker.run_operation(
            'create_book',
            {
                'book_name': book_name,
                'scanned_files': self.image_files.copy(),
                'todays_books_folder': self.settings['today']
            }
        )

    def delete_current_pair(self):
        if not self.image_files:
            return

        left_path = self.image_files[self.current_index] if self.current_index < len(self.image_files) else None
        right_path = self.image_files[self.current_index + 1] if (self.current_index + 1) < len(self.image_files) else None

        files_to_delete = [p for p in [left_path, right_path] if p]
        if not files_to_delete:
            return

        files_str = "\\n".join([os.path.basename(f) for f in files_to_delete])
        reply = QMessageBox.question(self, 'Confirm Deletion',
                                     f"Are you sure you want to permanently delete:\\n{files_str}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.file_op_worker.run_operation(
                'delete_pair',
                {'files_to_delete': files_to_delete}
            )

    def save_image(self, viewer: PhotoViewer):
        if not viewer.image_path:
            return

        edited_image = None
        if viewer.is_crop_mode:
            # This is a destructive action, so turn off crop mode after
            edited_image = viewer.apply_crop()
            viewer.toggle_crop_mode()
        elif viewer.rotation_angle != 0:
            edited_image = viewer.pil_image.rotate(
                viewer.rotation_angle,
                resample=Image.Resampling.BICUBIC,
                expand=True
            )

        if edited_image:
            # This needs to be thread-safe if the worker uses the object directly
            # For now, we assume the worker will handle it immediately
            self.file_op_worker.run_operation(
                'save_image',
                {'path': viewer.image_path, 'image_obj': edited_image}
            )
        else:
            self.statusBar().showMessage("No edits to save.", 3000)


    # --- Navigation Slots ---
    def prev_pair(self):
        if self.current_index > 0:
            self.current_index = max(0, self.current_index - 2)
            self.update_display()

    def next_pair(self):
        if self.current_index + 2 < len(self.image_files):
            self.current_index += 2
            self.update_display()

    def jump_to_end(self):
        if not self.image_files:
            return
        new_index = len(self.image_files) - 2 if len(self.image_files) >= 2 else 0
        self.current_index = max(0, new_index)
        self.update_display()

    def _create_image_pane(self, viewer_widget):
        """Creates a container for a PhotoViewer and its controls."""
        pane_frame = QFrame()
        layout = QVBoxLayout(pane_frame)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(5)

        layout.addWidget(viewer_widget, 1) # Viewer gets the stretch factor

        # Placeholder for controls for now
        controls_frame = QFrame()
        # In a real app, you'd populate this with actual controls
        controls_layout = QHBoxLayout(controls_frame)

        save_btn = QPushButton("Save Edits")
        toggle_crop_btn = QPushButton("Toggle Crop")
        restore_btn = QPushButton("Restore Original")
        rot_left_btn = QPushButton("⟲")
        rot_right_btn = QPushButton("⟳")

        controls_layout.addWidget(save_btn)
        controls_layout.addWidget(toggle_crop_btn)
        controls_layout.addWidget(restore_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(rot_left_btn)
        controls_layout.addWidget(rot_right_btn)

        # --- Connect Control Signals ---
        rot_left_btn.clicked.connect(lambda: viewer_widget.rotate_image(90))
        rot_right_btn.clicked.connect(lambda: viewer_widget.rotate_image(-90))
        toggle_crop_btn.clicked.connect(viewer_widget.toggle_crop_mode)
        save_btn.clicked.connect(lambda: self.save_image(viewer_widget))

        layout.addWidget(controls_frame)

        return pane_frame

    def _create_control_bar(self):
        control_bar_frame = QFrame()
        layout = QHBoxLayout(control_bar_frame)
        layout.setContentsMargins(0, 10, 0, 10)

        self.prev_btn = QPushButton("◀ Previous")
        self.next_btn = QPushButton("Next ▶")
        self.jump_to_end_btn = QPushButton("Jump to End")
        self.refresh_btn = QPushButton("Refresh")
        self.delete_pair_btn = QPushButton("Delete Pair")
        self.delete_pair_btn.setStyleSheet(f"background-color: #dc3545;")

        layout.addStretch()
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.next_btn)
        layout.addWidget(self.jump_to_end_btn)
        layout.addWidget(self.refresh_btn)
        layout.addStretch()
        layout.addWidget(self.delete_pair_btn)
        layout.addStretch()

        # --- Connect Signals ---
        self.prev_btn.clicked.connect(self.prev_pair)
        self.next_btn.clicked.connect(self.next_pair)
        self.jump_to_end_btn.clicked.connect(self.jump_to_end)
        self.delete_pair_btn.clicked.connect(self.delete_current_pair)

        return control_bar_frame

    def _create_sidebar(self):
        sidebar_frame = QFrame()
        layout = QVBoxLayout(sidebar_frame)
        layout.setContentsMargins(10, 10, 10, 10)

        # Stats Group
        stats_group = QGroupBox("Performance Stats")
        stats_layout = QVBoxLayout(stats_group)
        self.scans_min_label = QLabel("Performance: 0.0 pages/min")
        self.current_scans_label = QLabel("Pending Scans: 0")
        self.books_today_label = QLabel("Pending Books: 0 (0 pages)")
        self.total_scans_today_label = QLabel("Total Pages Today: 0")
        stats_layout.addWidget(self.scans_min_label)
        stats_layout.addWidget(self.current_scans_label)
        stats_layout.addWidget(self.books_today_label)
        stats_layout.addWidget(self.total_scans_today_label)

        # Today's Books Group
        todays_books_group = QGroupBox("Today's Books")
        todays_books_layout = QVBoxLayout(todays_books_group)

        # Book creation
        book_creation_layout = QHBoxLayout()
        self.book_name_entry = QLineEdit()
        self.book_name_entry.setPlaceholderText("Enter Book Name (from QR)...")
        create_book_btn = QPushButton("Create")
        book_creation_layout.addWidget(self.book_name_entry)
        book_creation_layout.addWidget(create_book_btn)
        todays_books_layout.addLayout(book_creation_layout)

        # List of books
        self.todays_books_list = QListWidget()
        todays_books_layout.addWidget(self.todays_books_list)

        # Transfer button
        transfer_to_data_btn = QPushButton("Transfer to Data")
        todays_books_layout.addWidget(transfer_to_data_btn)

        # --- Connect Sidebar Signals ---
        create_book_btn.clicked.connect(self.create_book)

        layout.addWidget(stats_group)
        layout.addWidget(todays_books_group, 1) # 1 stretch factor
        layout.addStretch()

        return sidebar_frame

if __name__ == '__main__':
    # This is for testing the MainWindow layout
    app = QApplication(sys.argv)
    # Dummy settings for testing
    test_settings = {
        "scan": "/path/to/scan",
        "today": "/path/to/today",
        "city_paths": {"123": "/path/to/city"}
    }
    window = MainWindow(settings=test_settings)
    window.show()
    sys.exit(app.exec())
