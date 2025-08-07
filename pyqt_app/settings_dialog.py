import sys
import os
import json
from PyQt6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QListWidget,
    QMessageBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt

# Constants from the original app
CONFIG_FILE = "scan_viewer_config.json"
DEFAULT_IMAGE_LOAD_TIMEOUT_MS = 2000

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner - Settings")
        self.setMinimumSize(800, 600)
        self.settings = {}

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # --- Main Title ---
        title_label = QLabel("Configure Workflow Directories")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(title_label)

        # --- Path Selection ---
        self.path_inputs = {}
        path_layout = QVBoxLayout()

        scan_path_widget, self.path_inputs['scan'] = self._create_path_selector("1. Scan Folder", "Select the folder to monitor for new scans.")
        path_layout.addWidget(scan_path_widget)

        today_path_widget, self.path_inputs['today'] = self._create_path_selector("2. Today's Books Folder", "Select the folder for temporary book staging.")
        path_layout.addWidget(today_path_widget)

        layout.addLayout(path_layout)
        layout.addSpacing(20)

        # --- City Path Configuration ---
        city_groupbox = QWidget() # Using QWidget as a container, can be styled later
        city_layout = QVBoxLayout(city_groupbox)

        city_title = QLabel("3. City Path Mappings")
        city_title.setStyleSheet("font-size: 11pt; font-weight: bold;")
        city_layout.addWidget(city_title)

        # --- City Path UI ---
        city_ui_layout = QHBoxLayout()

        # Left side: Listbox
        self.city_listbox = QListWidget()
        city_ui_layout.addWidget(self.city_listbox, 1) # Give it stretch factor 1

        # Right side: Controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        city_ui_layout.addWidget(controls_widget, 1) # Stretch factor 1

        # Code Entry
        code_layout = QHBoxLayout()
        code_label = QLabel("Code (XXX):")
        self.city_code_entry = QLineEdit()
        self.city_code_entry.setPlaceholderText("e.g., 297")
        code_layout.addWidget(code_label)
        code_layout.addWidget(self.city_code_entry)
        controls_layout.addLayout(code_layout)

        # Path Entry
        path_layout = QHBoxLayout()
        path_label = QLabel("Path:")
        self.city_path_entry = QLineEdit()
        self.city_path_entry.setPlaceholderText("e.g., //server/data/...")
        city_browse_btn = QPushButton("...")
        city_browse_btn.setFixedWidth(30)
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.city_path_entry)
        path_layout.addWidget(city_browse_btn)
        controls_layout.addLayout(path_layout)

        # Add/Remove Buttons
        city_btn_layout = QHBoxLayout()
        add_update_btn = QPushButton("Add / Update")
        remove_btn = QPushButton("Remove Selected")
        city_btn_layout.addStretch()
        city_btn_layout.addWidget(add_update_btn)
        city_btn_layout.addWidget(remove_btn)
        controls_layout.addLayout(city_btn_layout)
        controls_layout.addStretch()

        city_layout.addLayout(city_ui_layout)

        layout.addWidget(city_groupbox)
        layout.addStretch()

        # --- Connect City UI Signals ---
        city_browse_btn.clicked.connect(self._browse_city_path)
        self.city_listbox.currentItemChanged.connect(self._on_city_select)
        add_update_btn.clicked.connect(self._add_or_update_city)
        remove_btn.clicked.connect(self._remove_city)

        # --- Dialog Buttons (OK/Cancel) ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.on_ok)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_path_selector(self, label_text, dialog_title):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(label_text)
        label.setFixedWidth(200)

        line_edit = QLineEdit()
        line_edit.setReadOnly(True)

        button = QPushButton("Browse...")

        layout.addWidget(label)
        layout.addWidget(line_edit)
        layout.addWidget(button)

        button.clicked.connect(lambda: self._get_directory(line_edit, dialog_title))

        return widget, line_edit

    def _get_directory(self, line_edit, title):
        path = QFileDialog.getExistingDirectory(self, title)
        if path:
            line_edit.setText(path)

    def _browse_city_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select City Data Directory")
        if path:
            self.city_path_entry.setText(path)

    def _update_city_listbox(self):
        self.city_listbox.clear()
        city_paths = self.settings.get("city_paths", {})
        for code, path in sorted(city_paths.items()):
            self.city_listbox.addItem(f"{code}: {path}")

    def _on_city_select(self, current_item, previous_item):
        if not current_item:
            return

        selected_text = current_item.text()
        code, path = selected_text.split(':', 1)

        self.city_code_entry.setText(code.strip())
        self.city_path_entry.setText(path.strip())

    def _add_or_update_city(self):
        code = self.city_code_entry.text().strip()
        path = self.city_path_entry.text().strip()

        if not code or not path:
            QMessageBox.warning(self, "Incomplete Data", "Please provide both a code and a path.")
            return

        if not code.isdigit() or len(code) != 3:
            QMessageBox.warning(self, "Invalid Code", "The city code must be exactly 3 digits.")
            return

        if "city_paths" not in self.settings:
            self.settings["city_paths"] = {}

        self.settings["city_paths"][code] = path
        self._update_city_listbox()
        self.city_code_entry.clear()
        self.city_path_entry.clear()

    def _remove_city(self):
        current_item = self.city_listbox.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a city from the list to remove.")
            return

        selected_text = current_item.text()
        code = selected_text.split(':', 1)[0].strip()

        if "city_paths" in self.settings and code in self.settings["city_paths"]:
            del self.settings["city_paths"][code]
            self._update_city_listbox()
            self.city_code_entry.clear()
            self.city_path_entry.clear()

    def load_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    self.settings = json.load(f)

                self.path_inputs['scan'].setText(self.settings.get('scan', ''))
                self.path_inputs['today'].setText(self.settings.get('today', ''))
                self._update_city_listbox()
        except (IOError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "Load Error", f"Could not load config file: {e}")
            self.settings = {}

    def save_settings(self):
        self.settings['scan'] = self.path_inputs['scan'].text()
        self.settings['today'] = self.path_inputs['today'].text()
        # The self.settings['city_paths'] is already up-to-date due to the add/remove methods.

        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except IOError as e:
            QMessageBox.critical(self, "Save Error", f"Could not save config file: {e}")

    def on_ok(self):
        self.save_settings()
        if not all([self.settings.get('scan'), self.settings.get('today')]):
            QMessageBox.warning(self, "Incomplete Setup", "Please select all required directories.")
            return
        self.accept()

    def get_settings(self):
        return self.settings

if __name__ == '__main__':
    app = QApplication(sys.argv)
    dialog = SettingsDialog()
    if dialog.exec():
        print("Settings saved:", dialog.get_settings())
    sys.exit()
