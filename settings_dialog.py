import os
import sys
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QTabWidget, QWidget, QVBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QFileDialog, QListWidget,
    QHBoxLayout, QCheckBox, QMessageBox, QDialogButtonBox
)

import config

class SettingsDialog(QDialog):
    # Signal to notify the main app that settings were saved and it might be time to open the main window
    settings_saved = Signal()

    def __init__(self, parent=None, is_initial_setup=False):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner - Settings")
        self.setMinimumSize(700, 500)
        self.is_initial_setup = is_initial_setup

        # Load the current config
        self.config_data = config.load_config()

        # Main layout
        self.main_layout = QVBoxLayout(self)

        # Tab widget
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Create tabs
        self.create_paths_workflow_tab()
        self.create_lighting_correction_tab()
        self.create_theme_tab()

        # Dialog buttons (Save, Cancel)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_settings)
        self.button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(self.button_box)

        self.setLayout(self.main_layout)

        # Load data into UI fields
        self.load_settings_to_ui()

    def create_paths_workflow_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # --- Paths Group ---
        paths_group = QGroupBox("Folder Paths")
        paths_layout = QGridLayout()

        self.scan_folder_edit = QLineEdit()
        self.today_books_folder_edit = QLineEdit()

        paths_layout.addWidget(QLabel("Scan Folder:"), 0, 0)
        paths_layout.addWidget(self.scan_folder_edit, 0, 1)
        paths_layout.addWidget(self.create_browse_button(self.scan_folder_edit), 0, 2)

        paths_layout.addWidget(QLabel("Today's Books Folder:"), 1, 0)
        paths_layout.addWidget(self.today_books_folder_edit, 1, 1)
        paths_layout.addWidget(self.create_browse_button(self.today_books_folder_edit), 1, 2)

        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)

        # --- City Data Paths Group ---
        city_group = QGroupBox("City Data Paths")
        city_layout = QGridLayout()

        self.city_list = QListWidget()
        self.city_list.itemClicked.connect(self.city_list_item_clicked)

        self.city_code_edit = QLineEdit()
        self.city_code_edit.setPlaceholderText("3-digit code (e.g., 001)")
        self.city_path_edit = QLineEdit()
        self.city_path_edit.setPlaceholderText("Path to city data folder")

        add_update_button = QPushButton("Add/Update")
        add_update_button.clicked.connect(self.add_update_city)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_city)

        city_layout.addWidget(self.city_list, 0, 0, 1, 3)
        city_layout.addWidget(QLabel("City Code:"), 1, 0)
        city_layout.addWidget(self.city_code_edit, 1, 1, 1, 2)
        city_layout.addWidget(QLabel("Folder Path:"), 2, 0)
        city_layout.addWidget(self.city_path_edit, 2, 1)
        city_layout.addWidget(self.create_browse_button(self.city_path_edit), 2, 2)

        button_layout = QHBoxLayout()
        button_layout.addWidget(add_update_button)
        button_layout.addWidget(remove_button)
        city_layout.addLayout(button_layout, 3, 1, 1, 2)

        city_group.setLayout(city_layout)
        layout.addWidget(city_group)

        layout.addStretch()
        self.tabs.addTab(tab, "Paths & Workflow")

    def create_lighting_correction_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # --- Reference Images Group ---
        ref_group = QGroupBox("Folder with reference images")
        ref_layout = QGridLayout()

        self.ref_folder_edit = QLineEdit()
        ref_layout.addWidget(self.ref_folder_edit, 0, 0)
        ref_layout.addWidget(self.create_browse_button(self.ref_folder_edit), 0, 1)

        calc_button = QPushButton("Calculate and Save Standard")
        calc_button.clicked.connect(self.calculate_standard)
        ref_layout.addWidget(calc_button, 1, 0, 1, 2)

        ref_group.setLayout(ref_layout)
        layout.addWidget(ref_group)

        # --- Auto Corrections Group ---
        corr_group = QGroupBox("Automatic Corrections on New Scans")
        corr_layout = QVBoxLayout()

        self.auto_lighting_check = QCheckBox("Auto-adjust Lighting & Contrast")
        self.auto_color_check = QCheckBox("Auto-correct Color Tint")
        self.auto_sharpen_check = QCheckBox("Apply gentle Sharpening")

        corr_layout.addWidget(self.auto_lighting_check)
        corr_layout.addWidget(self.auto_color_check)
        corr_layout.addWidget(self.auto_sharpen_check)

        corr_group.setLayout(corr_layout)
        layout.addWidget(corr_group)

        layout.addStretch()
        self.tabs.addTab(tab, "Lighting & Correction")

    def create_theme_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        group = QGroupBox("Select a Theme")
        theme_layout = QHBoxLayout()

        for theme_name in config.THEMES.keys():
            btn = QPushButton(theme_name)
            btn.clicked.connect(lambda checked, name=theme_name: self.apply_theme(name))
            theme_layout.addWidget(btn)

        group.setLayout(theme_layout)
        layout.addWidget(group)
        layout.addStretch()
        self.tabs.addTab(tab, "Theme")

    def create_browse_button(self, target_line_edit):
        """Helper to create a browse button."""
        button = QPushButton("Browse...")
        button.clicked.connect(lambda: self.browse_for_folder(target_line_edit))
        return button

    def browse_for_folder(self, target_line_edit):
        """Opens a QFileDialog to select a directory."""
        path = QFileDialog.getExistingDirectory(self, "Select Folder", target_line_edit.text())
        if path:
            target_line_edit.setText(path)

    def load_settings_to_ui(self):
        """Populates the UI fields with values from the config dictionary."""
        self.scan_folder_edit.setText(self.config_data.get("scan_folder", ""))
        self.today_books_folder_edit.setText(self.config_data.get("today_books_folder", ""))
        self.ref_folder_edit.setText(self.config_data.get("reference_images_folder", ""))

        self.auto_lighting_check.setChecked(self.config_data.get("auto_adjust_lighting", True))
        self.auto_color_check.setChecked(self.config_data.get("auto_correct_color", True))
        self.auto_sharpen_check.setChecked(self.config_data.get("apply_sharpening", True))

        self.update_city_list()

    def update_city_list(self):
        self.city_list.clear()
        city_paths = self.config_data.get("city_data_paths", {})
        for code, path in sorted(city_paths.items()):
            self.city_list.addItem(f"{code}: {path}")

    def city_list_item_clicked(self, item):
        parts = item.text().split(":", 1)
        self.city_code_edit.setText(parts[0].strip())
        self.city_path_edit.setText(parts[1].strip())

    def add_update_city(self):
        code = self.city_code_edit.text().strip()
        path = self.city_path_edit.text().strip()
        if not code.isdigit() or len(code) != 3:
            QMessageBox.warning(self, "Invalid Code", "City code must be a 3-digit number.")
            return
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "Invalid Path", "The provided path is not a valid directory.")
            return

        self.config_data["city_data_paths"][code] = path
        self.update_city_list()
        self.city_code_edit.clear()
        self.city_path_edit.clear()

    def remove_city(self):
        selected_item = self.city_list.currentItem()
        if not selected_item:
            QMessageBox.warning(self, "No Selection", "Please select a city mapping to remove.")
            return

        code = selected_item.text().split(":", 1)[0].strip()
        if code in self.config_data["city_data_paths"]:
            del self.config_data["city_data_paths"][code]
        self.update_city_list()
        self.city_code_edit.clear()
        self.city_path_edit.clear()

    def calculate_standard(self):
        # This will eventually trigger a worker thread. For now, it's a placeholder.
        ref_folder = self.ref_folder_edit.text()
        if not ref_folder or not os.path.isdir(ref_folder):
            QMessageBox.warning(self, "Missing Folder", "Please select a valid reference images folder first.")
            return
        QMessageBox.information(self, "Not Implemented", f"Calculation for images in '{ref_folder}' will be implemented later.")

    def apply_theme(self, theme_name):
        self.config_data["current_theme"] = theme_name
        stylesheet = config.generate_stylesheet(theme_name)
        QApplication.instance().setStyleSheet(stylesheet)

    def save_settings(self):
        """Validates inputs and saves them to the config file."""
        # Update config_data from UI
        self.config_data["scan_folder"] = self.scan_folder_edit.text().strip()
        self.config_data["today_books_folder"] = self.today_books_folder_edit.text().strip()
        self.config_data["reference_images_folder"] = self.ref_folder_edit.text().strip()
        self.config_data["auto_adjust_lighting"] = self.auto_lighting_check.isChecked()
        self.config_data["auto_correct_color"] = self.auto_color_check.isChecked()
        self.config_data["apply_sharpening"] = self.auto_sharpen_check.isChecked()

        # Validate essential paths
        if not config.is_config_valid(self.config_data):
            QMessageBox.critical(
                self, "Configuration Incomplete",
                "The 'Scan Folder' and 'Today's Books Folder' must be set to valid directories."
            )
            return

        # Save the updated configuration
        config.save_config(self.config_data)

        QMessageBox.information(self, "Settings Saved", "Your settings have been saved successfully.")

        # Emit the signal and accept the dialog
        self.settings_saved.emit()
        self.accept()

    def reject(self):
        # If this is the first time setup, closing the dialog should quit the app
        if self.is_initial_setup:
            reply = QMessageBox.question(self, "Exit Application?",
                                         "Configuration is not complete. Are you sure you want to exit?")
            if reply == QMessageBox.Yes:
                sys.exit() # Exit the entire application
            else:
                return # Do not close the dialog
        super().reject()
