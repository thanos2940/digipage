import sys
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QDockWidget, QListWidget, QLineEdit, QGroupBox, QFormLayout,
    QSlider, QFrame, QMessageBox, QDialog
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QIcon # For future icons

import config
from image_viewer import ImageViewer
from workers import ScanWorker, Watcher
from settings_dialog import SettingsDialog

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner")

        self.app_config = config.load_config()
        self.image_files = []
        self.current_index = 0

        self.setup_ui()
        self.setup_workers()

        # Trigger initial scan
        self.scan_worker.perform_initial_scan()
        self.scan_worker.calculate_today_stats()

    def setup_ui(self):
        # --- Central Widget (Image Viewers) ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        self.viewer1 = self._create_viewer_panel()
        self.viewer2 = self._create_viewer_panel()
        main_layout.addWidget(self.viewer1['frame'])
        main_layout.addWidget(self.viewer2['frame'])

        # --- Right Sidebar (Dock Widget) ---
        self.create_sidebar()

        # --- Bottom Control Bar ---
        self.create_bottom_bar()

    def _create_viewer_panel(self):
        """Creates a single image viewer panel with its controls."""
        frame = QFrame()
        frame.setLayout(QVBoxLayout())

        viewer = ImageViewer()

        controls = {}
        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        control_layout.setAlignment(Qt.AlignCenter)

        controls['crop'] = QPushButton("Crop")
        controls['split'] = QPushButton("Split")
        controls['restore'] = QPushButton("Restore")
        controls['delete'] = QPushButton("Delete")

        # Sliders/Dials would go here
        # For now, simple placeholders
        # rotation_slider = QSlider(Qt.Horizontal)
        # color_slider = QSlider(Qt.Horizontal)

        control_layout.addWidget(controls['crop'])
        control_layout.addWidget(controls['split'])
        control_layout.addWidget(controls['restore'])
        control_layout.addWidget(controls['delete'])

        frame.layout().addWidget(viewer)
        frame.layout().addWidget(control_panel)

        panel_widgets = {'frame': frame, 'viewer': viewer, **controls}

        # Connect buttons
        controls['crop'].clicked.connect(lambda: self.toggle_crop_mode(viewer))
        controls['delete'].clicked.connect(lambda: self.delete_single_image(panel_widgets))
        controls['restore'].clicked.connect(lambda: self.restore_image(panel_widgets))

        return panel_widgets

    def create_sidebar(self):
        sidebar_dock = QDockWidget("Controls & Stats", self)
        sidebar_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        sidebar_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)

        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_dock.setWidget(sidebar_widget)

        # Performance Stats Group
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

        # Book Creation Group
        book_group = QGroupBox("Book Creation")
        book_layout = QVBoxLayout()
        self.book_name_edit = QLineEdit()
        self.book_name_edit.setPlaceholderText("Enter book name (QR code)...")
        create_book_btn = QPushButton("Create Book")
        create_book_btn.clicked.connect(self.create_book)
        book_layout.addWidget(self.book_name_edit)
        book_layout.addWidget(create_book_btn)
        book_group.setLayout(book_layout)

        # Today's Books Group
        today_group = QGroupBox("Today's Books")
        today_layout = QVBoxLayout()
        self.today_books_list = QListWidget()
        transfer_all_btn = QPushButton("Transfer All to Data")
        transfer_all_btn.clicked.connect(self.transfer_all_books)
        today_layout.addWidget(self.today_books_list)
        today_layout.addWidget(transfer_all_btn)
        today_group.setLayout(today_layout)

        # Settings Button
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings_dialog)

        sidebar_layout.addWidget(stats_group)
        sidebar_layout.addWidget(book_group)
        sidebar_layout.addWidget(today_group)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(settings_btn)

        self.addDockWidget(Qt.RightDockWidgetArea, sidebar_dock)

    def create_bottom_bar(self):
        # Using a QFrame as a status bar container for more flexibility
        bottom_bar = QFrame()
        bottom_bar.setFixedHeight(50)
        bottom_bar.setLayout(QHBoxLayout())
        bottom_bar.layout().setContentsMargins(10, 0, 10, 0)

        # This is not a real status bar, so we add it to the main layout.
        # A better approach is to set it as a permanent widget on a QStatusBar
        # For now, let's just make it a custom widget at the bottom.
        # This is complex, so we will create a proper status bar.

        self.status_label = QLabel("Pages 0-0 of 0")
        self.statusBar().addPermanentWidget(self.status_label)

        self.prev_btn = QPushButton("Previous Pair")
        self.next_btn = QPushButton("Next Pair")
        self.jump_end_btn = QPushButton("Jump to End")
        self.delete_pair_btn = QPushButton("Delete Pair")

        self.prev_btn.clicked.connect(self.prev_pair)
        self.next_btn.clicked.connect(self.next_pair)
        self.jump_end_btn.clicked.connect(self.jump_to_end)
        self.delete_pair_btn.clicked.connect(self.delete_current_pair)

        self.statusBar().addWidget(self.prev_btn)
        self.statusBar().addWidget(self.next_btn)
        self.statusBar().addWidget(self.jump_end_btn)
        self.statusBar().addWidget(self.delete_pair_btn)

    def setup_workers(self):
        # ScanWorker for on-demand tasks
        self.scan_worker_thread = QThread()
        self.scan_worker = ScanWorker(self.app_config)
        self.scan_worker.moveToThread(self.scan_worker_thread)
        self.scan_worker_thread.started.connect(self.scan_worker.perform_initial_scan)

        self.scan_worker.initial_scan_complete.connect(self.on_initial_scan_complete)
        self.scan_worker.stats_updated.connect(self.on_stats_updated)
        self.scan_worker.error.connect(self.show_error)
        self.scan_worker.file_operation_complete.connect(self.on_file_operation_complete)

        self.scan_worker_thread.start()

        # ImageProcessor for intensive image operations
        self.image_processor_thread = QThread()
        self.image_processor = ImageProcessor()
        self.image_processor.moveToThread(self.image_processor_thread)
        self.image_processor.processing_complete.connect(self.on_processing_complete)
        self.image_processor.error.connect(self.show_error)
        self.image_processor_thread.start()

        # Watcher for live file system monitoring
        self.watcher_thread = QThread()
        self.watcher = Watcher(self.app_config.get("scan_folder"))
        self.watcher.moveToThread(self.watcher_thread)

        self.watcher_thread.started.connect(self.watcher.run)
        self.watcher.finished.connect(self.watcher_thread.quit)
        self.watcher.new_image_detected_passthrough.connect(self.on_new_image_detected)
        self.watcher.error.connect(self.show_error)

        self.watcher_thread.start()

    # --- Slots for Worker Signals ---

    @Slot(list)
    def on_initial_scan_complete(self, files):
        self.image_files = files
        self.current_index = 0
        self.update_display()
        self.stats_labels['pending'].setText(str(len(self.image_files)))

    @Slot(dict)
    def on_stats_updated(self, stats):
        self.stats_labels['staged'].setText(f"{stats['books_in_today']} ({stats['pages_in_today']} pages)")
        total_pages = stats['pages_in_today'] + stats['pages_in_data'] + len(self.image_files)
        self.stats_labels['total'].setText(str(total_pages))

        # Update book list
        self.today_books_list.clear()
        # This part requires more logic to get the book names, which is in the main app in scanner2.py
        # For now, just showing the count.

    @Slot(str)
    def on_new_image_detected(self, path):
        if path not in self.image_files:
            self.image_files.append(path)
            self.image_files.sort(key=lambda x: config.natural_sort_key(os.path.basename(x)))
            self.update_display() # Or could jump to end
            self.stats_labels['pending'].setText(str(len(self.image_files)))
            self.statusBar().showMessage(f"New image detected: {os.path.basename(path)}", 3000)

    @Slot(str)
    def show_error(self, message):
        QMessageBox.critical(self, "Worker Error", message)

    # --- UI Logic Methods ---

    def update_display(self):
        """Loads the current pair of images into the viewers."""
        path1 = self.image_files[self.current_index] if self.current_index < len(self.image_files) else None
        path2 = self.image_files[self.current_index + 1] if (self.current_index + 1) < len(self.image_files) else None

        self.viewer1['viewer'].load_image(path1)
        self.viewer2['viewer'].load_image(path2)

        total = len(self.image_files)
        page1_num = self.current_index + 1 if path1 else 0
        page2_num = self.current_index + 2 if path2 else 0

        status_text = f"Pages {page1_num}-{page2_num} of {total}" if path2 else f"Page {page1_num} of {total}"
        if not path1:
            status_text = "No images found."
        self.status_label.setText(status_text)

        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index + 2 < len(self.image_files))

    def next_pair(self):
        if self.current_index + 2 < len(self.image_files):
            self.current_index += 2
            self.update_display()

    def prev_pair(self):
        if self.current_index > 0:
            self.current_index -= 2
            self.update_display()

    def jump_to_end(self):
        if not self.image_files: return
        new_index = len(self.image_files) - 2
        self.current_index = max(0, new_index)
        self.update_display()

    def toggle_crop_mode(self, viewer_panel):
        viewer = viewer_panel['viewer']
        is_cropping = not viewer.is_cropping
        viewer.set_cropping_mode(is_cropping)

        # If we just finished cropping, get the coords
        if not is_cropping:
            crop_rect = viewer.get_crop_coords()
            if crop_rect and viewer.image_path:
                # Convert QRect to a tuple for the worker
                coords = (crop_rect.x(), crop_rect.y(), crop_rect.width(), crop_rect.height())
                self.image_processor.crop_image(viewer.image_path, coords)
                self.statusBar().showMessage(f"Cropping {os.path.basename(viewer.image_path)}...", 3000)

    @Slot(str)
    def on_processing_complete(self, path):
        """Called when an image worker finishes processing an image."""
        self.statusBar().showMessage(f"Finished processing {os.path.basename(path)}", 3000)
        # Find the viewer showing this image and reload it
        if self.viewer1['viewer'].image_path == path:
            self.viewer1['viewer'].load_image(path)
        elif self.viewer2['viewer'].image_path == path:
            self.viewer2['viewer'].load_image(path)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.app_config = config.load_config()
            # Re-apply theme
            stylesheet = config.generate_stylesheet(self.app_config.get("theme"))
            self.setStyleSheet(stylesheet)
            # Restart watcher if path changed
            self.watcher.stop()
            self.watcher_thread.quit()
            self.watcher_thread.wait()
            self.setup_workers() # This is a bit heavy, should be more granular
            self.statusBar().showMessage("Settings saved and applied.", 3000)

    def delete_single_image(self, viewer_panel):
        """Deletes the image currently shown in a specific viewer."""
        image_path = viewer_panel['viewer'].image_path
        if not image_path:
            self.statusBar().showMessage("No image to delete.", 3000)
            return

        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to permanently delete this image?\n\n{os.path.basename(image_path)}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.scan_worker.delete_file(image_path)

    def delete_current_pair(self):
        """Deletes the two images currently visible."""
        path1 = self.viewer1['viewer'].image_path
        path2 = self.viewer2['viewer'].image_path

        paths_to_delete = [p for p in [path1, path2] if p]
        if not paths_to_delete:
            self.statusBar().showMessage("No images to delete.", 3000)
            return

        file_names = "\n".join([os.path.basename(p) for p in paths_to_delete])
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to permanently delete these images?\n\n{file_names}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            for path in paths_to_delete:
                self.scan_worker.delete_file(path)

    def create_book(self):
        """Creates a new book folder and moves all current scans into it."""
        book_name = self.book_name_edit.text().strip()
        if not book_name:
            self.show_error("Book name cannot be empty.")
            return

        if not self.image_files:
            self.show_error("There are no scanned images to add to a book.")
            return

        reply = QMessageBox.question(self, "Confirm Book Creation",
                                     f"Create book '{book_name}' and move {len(self.image_files)} scans into it?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            # Pass a copy of the list to the worker
            files_to_move = list(self.image_files)
            self.scan_worker.create_book(book_name, files_to_move)
            self.statusBar().showMessage(f"Creating book '{book_name}'...", 3000)

    def restore_image(self, viewer_panel):
        """Restores an image from its backup."""
        image_path = viewer_panel['viewer'].image_path
        if not image_path:
            self.statusBar().showMessage("No image to restore.", 3000)
            return

        reply = QMessageBox.question(self, "Confirm Restore",
                                     f"Are you sure you want to restore the original image? This will overwrite any changes.\n\n{os.path.basename(image_path)}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.image_processor.restore_image(image_path)

    def transfer_all_books(self):
        """Calls the worker to transfer all staged books to their data folders."""
        reply = QMessageBox.question(self, "Confirm Transfer",
                                     "Are you sure you want to transfer all staged books to their final data folders?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.statusBar().showMessage("Starting transfer...", 3000)
            self.scan_worker.transfer_all_to_data()

    @Slot(str, str)
    def on_file_operation_complete(self, operation_type, path):
        """Handles the UI update after a file operation from a worker."""
        if operation_type == "delete":
            if path in self.image_files:
                self.image_files.remove(path)
                self.statusBar().showMessage(f"Deleted: {os.path.basename(path)}", 3000)
                self.update_display()
            self.stats_labels['pending'].setText(str(len(self.image_files)))

        elif operation_type == "create_book":
            self.statusBar().showMessage(f"Successfully created book '{path}'", 3000)
            self.book_name_edit.clear()
            # Refresh everything
            self.scan_worker.perform_initial_scan()
            self.scan_worker.calculate_today_stats()

        elif operation_type == "transfer_all":
            self.statusBar().showMessage(path, 5000) # The 'path' is the message here
            # Refresh stats
            self.scan_worker.calculate_today_stats()


    def closeEvent(self, event):
        """Gracefully shut down worker threads."""
        self.watcher.stop()
        self.watcher_thread.quit()
        self.watcher_thread.wait()

        self.scan_worker_thread.quit()
        self.scan_worker_thread.wait()

        self.image_processor_thread.quit()
        self.image_processor_thread.wait()

        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(config.generate_stylesheet("Neutral Grey"))
    # This check is needed because main.py handles the config check
    if not config.load_config().get("scan_folder"):
         QMessageBox.critical(None, "Error", "Configuration not found. Please run main.py")
         sys.exit(1)

    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())
