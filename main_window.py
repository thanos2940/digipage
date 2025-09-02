import os
import sys
from PySide6.QtCore import Qt, QThread, Signal, Slot, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QDockWidget, QListWidget, QLineEdit, QGroupBox,
    QSlider, QFrame, QMessageBox, QApplication
)

import config
from settings_dialog import SettingsDialog
from image_viewer import ImageViewer
from workers import ScanWorker, DirectoryWatcher

class MainWindow(QMainWindow):
    # --- Signals to Worker ---
    request_initial_scan = Signal(str)
    request_stats_update = Signal(str)
    request_delete_files = Signal(list)
    request_restore_file = Signal(str)
    request_create_book = Signal(str, str, str)
    request_save_operations = Signal(str, dict)
    request_split_image = Signal(str, float)
    request_transfer_all = Signal(dict, str)
    request_auto_correct = Signal(str, dict)

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
        # A proper status bar is better for showing messages
        self.status_bar = self.statusBar()
        self.status_bar.addPermanentWidget(self._create_bottom_bar())

        # --- Worker Threads ---
        self._setup_workers()

        # --- Animation ---
        self._setup_animations()

        # --- Initial Actions ---
        self.update_navigation_buttons()
        self.trigger_initial_scan()
        self.trigger_stats_update()

    def _create_central_widget(self):
        container = QWidget()
        main_layout = QHBoxLayout(container)
        main_layout.addWidget(self._create_viewer_panel(self.viewer_left, "left"))
        main_layout.addWidget(self._create_viewer_panel(self.viewer_right, "right"))
        return container

    def _create_viewer_panel(self, viewer, side):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(viewer)
        layout.addWidget(self._create_image_controls(viewer, side))
        return panel

    def _create_image_controls(self, viewer: ImageViewer, side: str):
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QGridLayout(panel)

        # --- Buttons ---
        crop_btn = QPushButton("Crop")
        crop_btn.setCheckable(True)
        split_btn = QPushButton("Split")
        split_btn.setCheckable(True)
        restore_btn = QPushButton("Restore")
        delete_btn = QPushButton("Delete This")

        # Connections
        crop_btn.toggled.connect(viewer.set_cropping_mode)
        split_btn.toggled.connect(viewer.set_splitting_mode)
        restore_btn.clicked.connect(lambda: self.on_restore(viewer))
        delete_btn.clicked.connect(lambda: self.on_delete_single(viewer))

        apply_crop_btn = QPushButton("Apply Crop")
        apply_crop_btn.setVisible(False)
        apply_crop_btn.clicked.connect(lambda: self.on_apply_crop(viewer))

        apply_split_btn = QPushButton("Apply Split")
        apply_split_btn.setVisible(False)
        apply_split_btn.clicked.connect(lambda: self.on_apply_split(viewer))

        crop_btn.toggled.connect(apply_crop_btn.setVisible)
        split_btn.toggled.connect(apply_split_btn.setVisible)

        # --- Sliders ---
        rot_slider = QSlider(Qt.Horizontal, toolTip="Rotation")
        rot_slider.setRange(-45, 45)
        bright_slider = QSlider(Qt.Horizontal, toolTip="Brightness")
        bright_slider.setRange(-100, 100)
        contrast_slider = QSlider(Qt.Horizontal, toolTip="Contrast")
        contrast_slider.setRange(-100, 100)

        # Connections
        rot_slider.valueChanged.connect(viewer.set_rotation)
        bright_slider.valueChanged.connect(viewer.set_brightness)
        contrast_slider.valueChanged.connect(viewer.set_contrast)

        # Save on release
        rot_slider.sliderReleased.connect(lambda: self.on_adjustment_finished(viewer))
        bright_slider.sliderReleased.connect(lambda: self.on_adjustment_finished(viewer))
        contrast_slider.sliderReleased.connect(lambda: self.on_adjustment_finished(viewer))

        # Layout
        layout.addWidget(crop_btn, 0, 0)
        layout.addWidget(split_btn, 0, 1)
        layout.addWidget(restore_btn, 0, 2)
        layout.addWidget(delete_btn, 0, 3)

        layout.addWidget(apply_crop_btn, 0, 4)
        layout.addWidget(apply_split_btn, 0, 4) # They occupy the same space, only one is visible

        layout.addWidget(QLabel("Rotate:"), 1, 0)
        layout.addWidget(rot_slider, 1, 1, 1, 4)
        layout.addWidget(QLabel("Bright:"), 2, 0)
        layout.addWidget(bright_slider, 2, 1, 1, 4)
        layout.addWidget(QLabel("Contrast:"), 3, 0)
        layout.addWidget(contrast_slider, 3, 1, 1, 4)

        # Store sliders to reset them
        viewer.property("sliders") # Custom property
        setattr(viewer, "sliders", {'rot': rot_slider, 'bright': bright_slider, 'contrast': contrast_slider})

        return panel

    def _create_sidebar(self):
        sidebar = QDockWidget("Controls & Stats")
        sidebar.setAllowedAreas(Qt.RightDockWidgetArea)
        sidebar.setFeatures(QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetMovable)

        container = QWidget()
        layout = QVBoxLayout(container)

        # Stats Group
        stats_group = QGroupBox("Performance Stats")
        stats_layout = QGridLayout()
        self.stats_pages_min_label = QLabel("0")
        self.stats_pending_label = QLabel("0")
        self.stats_staged_label = QLabel("0")
        self.stats_total_today_label = QLabel("0")
        stats_layout.addWidget(QLabel("Pages/Minute:"), 0, 0); stats_layout.addWidget(self.stats_pages_min_label, 0, 1)
        stats_layout.addWidget(QLabel("Pending Scans:"), 1, 0); stats_layout.addWidget(self.stats_pending_label, 1, 1)
        stats_layout.addWidget(QLabel("Staged Books:"), 2, 0); stats_layout.addWidget(self.stats_staged_label, 2, 1)
        stats_layout.addWidget(QLabel("Total Pages Today:"), 3, 0); stats_layout.addWidget(self.stats_total_today_label, 3, 1)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Book Creation
        book_group = QGroupBox("Book Creation")
        book_layout = QVBoxLayout()
        self.book_name_edit = QLineEdit(placeholderText="Scan QR Code for Book Name")
        create_book_btn = QPushButton("Create Book")
        create_book_btn.clicked.connect(self.on_create_book)
        book_layout.addWidget(self.book_name_edit); book_layout.addWidget(create_book_btn)
        book_group.setLayout(book_layout)
        layout.addWidget(book_group)

        # Today's Books
        today_group = QGroupBox("Today's Books")
        today_layout = QVBoxLayout()
        self.today_books_list = QListWidget()
        today_layout.addWidget(self.today_books_list)
        today_group.setLayout(today_layout)
        layout.addWidget(today_group)

        layout.addStretch()

        # Main Actions
        transfer_btn = QPushButton("Transfer all to Data")
        transfer_btn.clicked.connect(self.on_transfer_all)
        transfer_btn.setStyleSheet("background-color: #77DD77; color: black;")
        layout.addWidget(transfer_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings_dialog)
        layout.addWidget(settings_btn)

        sidebar.setWidget(container)
        return sidebar

    def _create_bottom_bar(self):
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
        delete_pair_btn.clicked.connect(self.on_delete_pair)

        layout.addWidget(self.prev_pair_btn)
        layout.addWidget(self.next_pair_btn)
        layout.addWidget(self.jump_end_btn)
        layout.addStretch()
        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(delete_pair_btn)

        return bar

    def _setup_workers(self):
        self.scan_thread = QThread()
        self.scan_worker = ScanWorker()
        self.scan_worker.moveToThread(self.scan_thread)
        # Connect worker signals
        self.scan_worker.initial_scan_complete.connect(self.on_initial_scan_complete)
        self.scan_worker.stats_updated.connect(self.update_stats_display)
        self.scan_worker.error.connect(self.on_worker_error)
        self.scan_worker.operation_successful.connect(self.on_operation_successful)
        self.scan_worker.file_operation_finished.connect(self.trigger_initial_scan)
        # Connect main window requests to worker slots
        self.request_initial_scan.connect(self.scan_worker.perform_initial_scan)
        self.request_stats_update.connect(self.scan_worker.calculate_today_stats)
        self.request_delete_files.connect(self.scan_worker.delete_files)
        self.request_restore_file.connect(self.scan_worker.restore_from_backup)
        self.request_create_book.connect(self.scan_worker.create_book)
        self.request_save_operations.connect(self.scan_worker.apply_and_save_operations)
        self.request_split_image.connect(self.scan_worker.split_image)
        self.request_transfer_all.connect(self.scan_worker.transfer_books_to_data)
        self.request_auto_correct.connect(self.scan_worker.auto_correct_image)
        self.scan_thread.start()

        self.watch_thread = QThread()
        self.watcher = DirectoryWatcher(self.config_data.get("scan_folder"))
        self.watcher.moveToThread(self.watch_thread)
        self.watcher.new_image_detected.connect(self.add_new_image)
        self.watcher.error.connect(self.on_worker_error)
        self.watch_thread.started.connect(self.watcher.start_watching)
        self.watch_thread.start()

    # --- Slots for UI actions ---
    @Slot()
    def on_delete_single(self, viewer: ImageViewer):
        if viewer.base_image and QMessageBox.question(self, "Delete", f"Delete {os.path.basename(viewer.base_image.filename)}?") == QMessageBox.Yes:
            self.request_delete_files.emit([viewer.base_image.filename])

    @Slot()
    def on_delete_pair(self):
        paths = []
        if self.viewer_left.base_image: paths.append(self.viewer_left.base_image.filename)
        if self.viewer_right.base_image: paths.append(self.viewer_right.base_image.filename)
        if paths and QMessageBox.question(self, "Delete", f"Delete both displayed images?") == QMessageBox.Yes:
            self.request_delete_files.emit(paths)

    @Slot()
    def on_restore(self, viewer: ImageViewer):
        if viewer.base_image and QMessageBox.question(self, "Restore", f"Restore {os.path.basename(viewer.base_image.filename)} from backup?") == QMessageBox.Yes:
            self.request_restore_file.emit(viewer.base_image.filename)

    @Slot()
    def on_create_book(self):
        book_name = self.book_name_edit.text().strip()
        if not book_name:
            QMessageBox.warning(self, "Input Error", "Book name cannot be empty.")
            return
        self.request_create_book.emit(book_name, self.config_data["scan_folder"], self.config_data["today_books_folder"])
        self.book_name_edit.clear()

    @Slot()
    def on_transfer_all(self):
        if QMessageBox.question(self, "Transfer", "Transfer all books from 'Today's Books' to their city data folders?") == QMessageBox.Yes:
            self.request_transfer_all.emit(self.config_data["city_data_paths"], self.config_data["today_books_folder"])

    @Slot()
    def on_adjustment_finished(self, viewer: ImageViewer):
        """Called when a slider is released to save the operation."""
        if not viewer.base_image: return
        ops = viewer.get_image_operations()
        self.request_save_operations.emit(viewer.base_image.filename, ops)
        viewer.clear_preview()

    @Slot()
    def on_apply_crop(self, viewer: ImageViewer):
        if not viewer.base_image: return
        ops = viewer.get_image_operations() # This will include the crop rect
        self.request_save_operations.emit(viewer.base_image.filename, ops)
        viewer.set_cropping_mode(False) # Exit mode after applying

    @Slot()
    def on_apply_split(self, viewer: ImageViewer):
        if not viewer.base_image: return
        ratio = viewer.get_split_ratio()
        self.request_split_image.emit(viewer.base_image.filename, ratio)
        viewer.set_splitting_mode(False) # Exit mode after applying

    # --- Slots for Worker Signals ---
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
        self.image_paths.append(path)
        self.image_paths.sort()
        self.update_navigation_buttons()
        # Auto-correction logic
        corrections_to_apply = {
            "lighting": self.config_data.get("auto_adjust_lighting", False),
            "color": self.config_data.get("auto_correct_color", False),
            "sharpen": self.config_data.get("apply_sharpening", False)
        }
        if any(corrections_to_apply.values()):
            self.request_auto_correct.emit(path, corrections_to_apply)
        # Auto-navigate if at the end
        if self.current_index >= len(self.image_paths) - 2:
             self.display_current_pair()

    @Slot(dict)
    def update_stats_display(self, stats: dict):
        self.stats_staged_label.setText(str(stats.get("staged_books", 0)))
        self.stats_total_today_label.setText(str(stats.get("total_pages_today", 0)))

    @Slot(str, str)
    def on_operation_successful(self, message, op_type):
        self.status_bar.showMessage(message, 5000)

    @Slot(str)
    def on_worker_error(self, message: str):
        QMessageBox.critical(self, "Worker Error", message)

    # --- Core Logic ---
    def display_current_pair(self):
        num_images = len(self.image_paths)
        viewers = [self.viewer_left, self.viewer_right]
        for i, viewer in enumerate(viewers):
            path_index = self.current_index + i
            path = self.image_paths[path_index] if path_index < num_images else None
            viewer.load_image(path)
            # Reset sliders
            sliders = getattr(viewer, "sliders", {})
            if sliders:
                sliders['rot'].setValue(0)
                sliders['bright'].setValue(0)
                sliders['contrast'].setValue(0)
        self.status_label.setText(f"Pages {self.current_index + 1}-{self.current_index + 2} of {num_images}")
        self.stats_pending_label.setText(str(max(0, num_images - (self.current_index + 2))))

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
        self.config_data = config.load_config()
        QApplication.instance().setStyleSheet(config.generate_stylesheet(self.config_data.get("current_theme")))
        # A more robust solution would restart workers if paths changed.
        self.status_bar.showMessage("Settings saved. Some changes may require a restart.", 5000)

    def _setup_animations(self):
        self.jump_anim = QVariantAnimation(self)
        self.jump_anim.setDuration(1500)
        self.jump_anim.setLoopCount(-1)
        self.jump_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.jump_anim.valueChanged.connect(self._animate_jump_button_stylesheet)

    @Slot(QColor)
    def _animate_jump_button_stylesheet(self, color):
        self.jump_to_end_btn.setStyleSheet(f"background-color: {color.name()};")

    def _update_jump_button_animation(self):
        theme_colors = config.THEMES.get(self.config_data.get("current_theme", "Neutral Grey"))
        base_color = QColor(theme_colors.get("ACCENT_PRIMARY"))
        pulse_color = QColor(base_color).lighter(130)

        self.jump_anim.setStartValue(base_color)
        self.jump_anim.setEndValue(pulse_color)

        has_unseen_images = self.current_index + 2 < len(self.image_paths)
        if has_unseen_images and self.jump_anim.state() == QVariantAnimation.Stopped:
            self.jump_anim.start()
        elif not has_unseen_images and self.jump_anim.state() == QVariantAnimation.Running:
            self.jump_anim.stop()
            self.jump_to_end_btn.setStyleSheet("") # Reset stylesheet

    def update_navigation_buttons(self):
        self.prev_pair_btn.setEnabled(self.current_index > 0)
        self.next_pair_btn.setEnabled(self.current_index + 2 < len(self.image_paths))
        self.jump_end_btn.setEnabled(self.current_index + 2 < len(self.image_paths))
        self._update_jump_button_animation()

    def closeEvent(self, event):
        self.watcher.stop_watching()
        self.watch_thread.quit()
        self.scan_thread.quit()
        self.watch_thread.wait(5000)
        self.scan_thread.wait(5000)
        event.accept()
