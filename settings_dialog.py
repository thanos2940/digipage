import sys
from PySide6.QtWidgets import (
    QApplication, QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QFileDialog, QMessageBox,
    QCheckBox, QDialogButtonBox, QFormLayout, QListWidgetItem
)
from PySide6.QtCore import Qt

import config
import numpy as np
from PIL import Image
import os

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner - Settings")
        self.setMinimumSize(700, 600)

        # Load current config
        self.current_config = config.load_config()
        self.city_paths = self.current_config.get("city_paths", {})

        # Main layout
        self.layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)

        # Create tabs
        self.create_paths_workflow_tab()
        self.create_lighting_correction_tab()
        self.create_theme_tab()

        # Dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_settings)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

        self.load_initial_values()

    def create_paths_workflow_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        # --- Scan Folder ---
        self.scan_folder_edit = QLineEdit()
        self.scan_folder_edit.setReadOnly(True)
        scan_folder_btn = QPushButton("Browse...")
        scan_folder_btn.clicked.connect(lambda: self.browse_folder(self.scan_folder_edit, "Select Scan Folder"))
        scan_folder_layout = QHBoxLayout()
        scan_folder_layout.addWidget(self.scan_folder_edit)
        scan_folder_layout.addWidget(scan_folder_btn)
        layout.addRow("Scan Folder:", scan_folder_layout)

        # --- Today's Books Folder ---
        self.today_folder_edit = QLineEdit()
        self.today_folder_edit.setReadOnly(True)
        today_folder_btn = QPushButton("Browse...")
        today_folder_btn.clicked.connect(lambda: self.browse_folder(self.today_folder_edit, "Select Today's Books Folder"))
        today_folder_layout = QHBoxLayout()
        today_folder_layout.addWidget(self.today_folder_edit)
        today_folder_layout.addWidget(today_folder_btn)
        layout.addRow("Today's Books Folder:", today_folder_layout)

        # --- City Data Paths ---
        layout.addRow(QLabel("City Data Paths:"))
        self.city_list_widget = QListWidget()
        self.city_list_widget.itemSelectionChanged.connect(self.on_city_selected)
        layout.addRow(self.city_list_widget)

        city_form_layout = QFormLayout()
        self.city_code_edit = QLineEdit()
        self.city_code_edit.setPlaceholderText("e.g., 001")
        self.city_code_edit.setMaxLength(3)
        city_form_layout.addRow("City Code:", self.city_code_edit)

        self.city_path_edit = QLineEdit()
        self.city_path_edit.setReadOnly(True)
        city_path_btn = QPushButton("Browse...")
        city_path_btn.clicked.connect(lambda: self.browse_folder(self.city_path_edit, "Select City Data Folder"))
        city_path_layout = QHBoxLayout()
        city_path_layout.addWidget(self.city_path_edit)
        city_path_layout.addWidget(city_path_btn)
        city_form_layout.addRow("Folder Path:", city_path_layout)
        layout.addRow(city_form_layout)

        city_button_layout = QHBoxLayout()
        add_update_btn = QPushButton("Add/Update")
        add_update_btn.clicked.connect(self.add_update_city)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_city)
        city_button_layout.addStretch()
        city_button_layout.addWidget(add_update_btn)
        city_button_layout.addWidget(remove_btn)
        layout.addRow(city_button_layout)

        self.tab_widget.addTab(tab, "Paths & Workflow")

    def create_lighting_correction_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        # --- Reference Images Folder ---
        self.ref_folder_edit = QLineEdit()
        self.ref_folder_edit.setReadOnly(True)
        ref_folder_btn = QPushButton("Browse...")
        ref_folder_btn.clicked.connect(lambda: self.browse_folder(self.ref_folder_edit, "Select Folder with Reference Images"))
        ref_folder_layout = QHBoxLayout()
        ref_folder_layout.addWidget(self.ref_folder_edit)
        ref_folder_layout.addWidget(ref_folder_btn)
        layout.addRow("Reference Images Folder:", ref_folder_layout)

        # --- Calculate Standard Button ---
        calc_btn = QPushButton("Calculate and Save Standard")
        calc_btn.clicked.connect(self.calculate_and_save_standard)
        layout.addRow(calc_btn)

        # --- Auto Correction Toggles ---
        layout.addRow(QLabel("Automatic Corrections on New Scans:"))
        self.auto_lighting_checkbox = QCheckBox("Auto-adjust Lighting & Contrast")
        self.auto_color_checkbox = QCheckBox("Auto-correct Color Tint")
        self.auto_sharpen_checkbox = QCheckBox("Apply gentle Sharpening")
        layout.addRow(self.auto_lighting_checkbox)
        layout.addRow(self.auto_color_checkbox)
        layout.addRow(self.auto_sharpen_checkbox)

        self.tab_widget.addTab(tab, "Lighting & Correction")

    def create_theme_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)

        layout.addWidget(QLabel("Select a theme to apply it immediately:"))

        button_layout = QHBoxLayout()
        for theme_name in config.THEMES.keys():
            btn = QPushButton(theme_name)
            btn.clicked.connect(lambda checked=False, name=theme_name: self.apply_theme(name))
            button_layout.addWidget(btn)

        layout.addLayout(button_layout)
        self.tab_widget.addTab(tab, "Theme")

    def browse_folder(self, line_edit, title):
        folder_path = QFileDialog.getExistingDirectory(self, title, line_edit.text())
        if folder_path:
            line_edit.setText(folder_path)

    def load_initial_values(self):
        self.scan_folder_edit.setText(self.current_config.get("scan_folder", ""))
        self.today_folder_edit.setText(self.current_config.get("todays_books_folder", ""))
        self.ref_folder_edit.setText(self.current_config.get("lighting_standard_folder", ""))

        self.auto_lighting_checkbox.setChecked(self.current_config.get("auto_lighting_correction_enabled", False))
        self.auto_color_checkbox.setChecked(self.current_config.get("auto_color_correction_enabled", False))
        self.auto_sharpen_checkbox.setChecked(self.current_config.get("auto_sharpening_enabled", False))

        self.update_city_list()

    def update_city_list(self):
        self.city_list_widget.clear()
        for code, path in sorted(self.city_paths.items()):
            self.city_list_widget.addItem(f"{code}: {path}")

    def on_city_selected(self):
        selected_items = self.city_list_widget.selectedItems()
        if not selected_items:
            return

        item_text = selected_items[0].text()
        code, path = item_text.split(":", 1)
        self.city_code_edit.setText(code.strip())
        self.city_path_edit.setText(path.strip())

    def add_update_city(self):
        code = self.city_code_edit.text().strip()
        path = self.city_path_edit.text().strip()

        if not code or not path:
            QMessageBox.warning(self, "Input Error", "City code and path cannot be empty.")
            return

        if not code.isdigit() or len(code) != 3:
            QMessageBox.warning(self, "Input Error", "City code must be exactly 3 digits.")
            return

        self.city_paths[code] = path
        self.update_city_list()
        self.city_code_edit.clear()
        self.city_path_edit.clear()

    def remove_city(self):
        selected_items = self.city_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selection Error", "Please select a city to remove.")
            return

        item_text = selected_items[0].text()
        code = item_text.split(":", 1)[0].strip()

        reply = QMessageBox.question(self, "Confirm Deletion", f"Are you sure you want to remove the mapping for city code '{code}'?")
        if reply == QMessageBox.Yes:
            if code in self.city_paths:
                del self.city_paths[code]
                self.update_city_list()

    def calculate_and_save_standard(self):
        folder_path = self.ref_folder_edit.text()
        if not os.path.isdir(folder_path):
            QMessageBox.critical(self, "Error", "The specified path is not a valid folder.")
            return

        allowed_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}
        image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in allowed_extensions]

        if not image_files:
            QMessageBox.warning(self, "No Images Found", "The selected folder contains no supported image files.")
            return

        try:
            pil_images = [Image.open(p).convert('RGB') for p in image_files]
            if not pil_images:
                QMessageBox.warning(self, "Warning", "No valid images could be opened.")
                return

            target_size = pil_images[0].size
            resized_images_np = []
            for img in pil_images:
                resized_img = img.resize(target_size, Image.Resampling.LANCZOS)
                resized_images_np.append(np.array(resized_img))

            avg_image_array = np.mean(np.array(resized_images_np), axis=0).astype(np.uint8)
            template_image = Image.fromarray(avg_image_array, 'RGB')

            template_path = os.path.splitext(config.CONFIG_FILE)[0] + "_template.png"
            template_image.save(template_path)

            self.current_config['lighting_standard_metrics'] = {
                'histogram_template_path': template_path
            }

            QMessageBox.information(self, "Success", f"Successfully calculated standard from {len(pil_images)} images.\nTemplate saved to: {template_path}")

        except Exception as e:
            QMessageBox.critical(self, "Calculation Failed", f"An error occurred: {e}")


    def apply_theme(self, theme_name):
        self.current_config["theme"] = theme_name
        stylesheet = config.generate_stylesheet(theme_name)
        QApplication.instance().setStyleSheet(stylesheet)

    def save_settings(self):
        # Validation
        if not self.scan_folder_edit.text() or not self.today_folder_edit.text():
            QMessageBox.warning(self, "Validation Error", "Scan Folder and Today's Books Folder must be set.")
            return

        # Update config dictionary
        self.current_config["scan_folder"] = self.scan_folder_edit.text()
        self.current_config["todays_books_folder"] = self.today_folder_edit.text()
        self.current_config["lighting_standard_folder"] = self.ref_folder_edit.text()
        self.current_config["city_paths"] = self.city_paths
        self.current_config["auto_lighting_correction_enabled"] = self.auto_lighting_checkbox.isChecked()
        self.current_config["auto_color_correction_enabled"] = self.auto_color_checkbox.isChecked()
        self.current_config["auto_sharpening_enabled"] = self.auto_sharpen_checkbox.isChecked()
        # Theme is already updated in apply_theme

        # Save to file
        config.save_config(self.current_config)
        QMessageBox.information(self, "Success", "Settings have been saved.")
        self.accept()

if __name__ == '__main__':
    # Example usage for testing
    app = QApplication(sys.argv)
    # Apply a default theme for the test run
    initial_config = config.load_config()
    app.setStyleSheet(config.generate_stylesheet(initial_config.get("theme")))

    dialog = SettingsDialog()
    if dialog.exec():
        print("Settings saved.")
    else:
        print("Settings dialog cancelled.")
    sys.exit()
