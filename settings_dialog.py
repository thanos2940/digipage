import sys
from PySide6.QtWidgets import (
    QApplication, QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QFileDialog, QMessageBox,
    QCheckBox, QDialogButtonBox, QFormLayout, QListWidgetItem, QGroupBox, QRadioButton
)
from PySide6.QtCore import Qt

import config
import numpy as np
from PIL import Image
import os

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner - Ρυθμίσεις")
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
        form_layout = QFormLayout(tab)
        form_layout.setSpacing(15)

        # Scan Folder
        self.scan_folder_edit = QLineEdit()
        scan_folder_btn = QPushButton("...")
        scan_folder_btn.clicked.connect(lambda: self.browse_folder(self.scan_folder_edit))
        self.scan_folder_layout = QHBoxLayout()
        self.scan_folder_layout.addWidget(self.scan_folder_edit)
        self.scan_folder_layout.addWidget(scan_folder_btn)

        # Today's Books Folder
        self.today_folder_edit = QLineEdit()
        today_folder_btn = QPushButton("...")
        today_folder_btn.clicked.connect(lambda: self.browse_folder(self.today_folder_edit))
        self.today_folder_layout = QHBoxLayout()
        self.today_folder_layout.addWidget(self.today_folder_edit)
        self.today_folder_layout.addWidget(today_folder_btn)

        form_layout.addRow("Φάκελος Σάρωσης:", self.scan_folder_layout)
        form_layout.addRow("Φάκελος Σημερινών Βιβλίων:", self.today_folder_layout)
        
        # Scanner Mode Selection
        scanner_groupbox = QGroupBox("Τύπος Scanner")
        scanner_layout = QVBoxLayout()
        self.dual_scan_radio = QRadioButton("Scanner Διπλής Σάρωσης (2 εικόνες ανά σάρωση)")
        self.single_split_radio = QRadioButton("Scanner Ενιαίας Λήψης (1 εικόνα προς διαχωρισμό)")
        
        scanner_layout.addWidget(self.dual_scan_radio)
        scanner_layout.addWidget(self.single_split_radio)
        scanner_groupbox.setLayout(scanner_layout)
        
        form_layout.addRow(scanner_groupbox)

        # Caching and Auto-correction checkboxes
        self.caching_checkbox = QCheckBox("Ενεργοποίηση Caching Εικόνων")
        self.caching_checkbox.setToolTip("Αποθηκεύει προσωρινά τις εικόνες στη μνήμη για ταχύτερη εναλλαγή.")
        
        self.auto_lighting_checkbox = QCheckBox("Αυτόματη Διόρθωση Φωτισμού")
        self.auto_lighting_checkbox.setToolTip("Εφαρμόζει αυτόματη διόρθωση φωτεινότητας/αντίθεσης σε νέες σαρώσεις.")
        
        self.auto_color_checkbox = QCheckBox("Αυτόματη Διόρθωση Χρώματος")
        self.auto_color_checkbox.setToolTip("Εφαρμόζει αυτόματη διόρθωση χρωματικής ισορροπίας σε νέες σαρώσεις.")
        
        self.auto_sharpen_checkbox = QCheckBox("Αυτόματη Εφαρμογή Sharpen")
        self.auto_sharpen_checkbox.setToolTip("Εφαρμόζει ένα ελαφρύ φίλτρο sharpening σε νέες σαρώσεις.")

        checkbox_layout = QVBoxLayout()
        checkbox_layout.addWidget(self.caching_checkbox)
        checkbox_layout.addWidget(self.auto_lighting_checkbox)
        checkbox_layout.addWidget(self.auto_color_checkbox)
        checkbox_layout.addWidget(self.auto_sharpen_checkbox)
        
        checkbox_group = QGroupBox("Αυτοματοποιήσεις & Απόδοση")
        checkbox_group.setLayout(checkbox_layout)
        form_layout.addRow(checkbox_group)

        self.tab_widget.addTab(tab, "Βασικές Ρυθμίσεις")

    def create_lighting_correction_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Reference Folder
        ref_group = QGroupBox("Φάκελος Προτύπου Φωτισμού")
        ref_layout = QFormLayout(ref_group)
        self.ref_folder_edit = QLineEdit()
        ref_folder_btn = QPushButton("...")
        ref_folder_btn.clicked.connect(self.select_ref_folder)
        ref_folder_hbox = QHBoxLayout()
        ref_folder_hbox.addWidget(self.ref_folder_edit)
        ref_folder_hbox.addWidget(ref_folder_btn)
        ref_layout.addRow("Επιλογή Φακέλου:", ref_folder_hbox)
        layout.addWidget(ref_group)
        
        # City Paths
        city_group = QGroupBox("Διαδρομές Αποθήκευσης ανά Πόλη")
        city_layout = QVBoxLayout(city_group)
        self.city_list_widget = QListWidget()
        city_layout.addWidget(self.city_list_widget)
        
        city_buttons_layout = QHBoxLayout()
        add_city_btn = QPushButton("Προσθήκη")
        add_city_btn.clicked.connect(self.add_city)
        remove_city_btn = QPushButton("Αφαίρεση")
        remove_city_btn.clicked.connect(self.remove_city)
        city_buttons_layout.addWidget(add_city_btn)
        city_buttons_layout.addWidget(remove_city_btn)
        city_layout.addLayout(city_buttons_layout)
        
        layout.addWidget(city_group)
        self.tab_widget.addTab(tab, "Διαδρομές & Πρότυπα")

    def create_theme_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        groupbox = QGroupBox("Επιλογή Θέματος Εμφάνισης")
        theme_layout = QVBoxLayout(groupbox)
        
        self.theme_radios = {}
        for theme_name in config.THEMES.keys():
            radio = QRadioButton(theme_name)
            radio.toggled.connect(lambda checked, name=theme_name: self.apply_theme(name) if checked else None)
            theme_layout.addWidget(radio)
            self.theme_radios[theme_name] = radio
            
        layout.addWidget(groupbox)
        layout.addStretch()
        self.tab_widget.addTab(tab, "Εμφάνιση")

    def load_initial_values(self):
        self.scan_folder_edit.setText(self.current_config.get("scan_folder", ""))
        self.today_folder_edit.setText(self.current_config.get("todays_books_folder", ""))
        self.ref_folder_edit.setText(self.current_config.get("lighting_standard_folder", ""))
        self.caching_checkbox.setChecked(self.current_config.get("caching_enabled", True))
        self.auto_lighting_checkbox.setChecked(self.current_config.get("auto_lighting_correction_enabled", False))
        self.auto_color_checkbox.setChecked(self.current_config.get("auto_color_correction_enabled", False))
        self.auto_sharpen_checkbox.setChecked(self.current_config.get("auto_sharpening_enabled", False))
        
        scanner_mode = self.current_config.get("scanner_mode", "dual_scan")
        if scanner_mode == "single_split":
            self.single_split_radio.setChecked(True)
        else:
            self.dual_scan_radio.setChecked(True)

        # Load city paths into the list
        self.city_list_widget.clear()
        for city, path in self.city_paths.items():
            item = QListWidgetItem(f"{city}: {path}")
            item.setData(Qt.UserRole, (city, path))
            self.city_list_widget.addItem(item)
            
        # Set theme radio
        current_theme = self.current_config.get("theme", "Material Dark")
        if current_theme in self.theme_radios:
            self.theme_radios[current_theme].setChecked(True)

    def browse_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "Επιλέξτε Φάκελο")
        if folder:
            line_edit.setText(folder)

    def select_ref_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Επιλέξτε Φάκελο Προτύπου")
        if folder:
            self.ref_folder_edit.setText(folder)
            self.calculate_ref_metrics(folder)
    
    def calculate_ref_metrics(self, folder):
        image_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if not image_files:
            QMessageBox.warning(self, "Προσοχή", "Ο φάκελος δεν περιέχει εικόνες.")
            self.current_config["lighting_standard_metrics"] = None
            return

        all_means = []
        for img_path in image_files:
            try:
                with Image.open(img_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    rgb_mean = np.mean(img, axis=(0, 1))
                    all_means.append(rgb_mean)
            except Exception as e:
                print(f"Could not process {img_path}: {e}")
        
        if not all_means:
            QMessageBox.warning(self, "Σφάλμα", "Δεν ήταν δυνατή η επεξεργασία καμίας εικόνας.")
            self.current_config["lighting_standard_metrics"] = None
            return

        avg_metrics = np.mean(all_means, axis=0)
        self.current_config["lighting_standard_metrics"] = avg_metrics.tolist()
        QMessageBox.information(self, "Επιτυχία", f"Υπολογίστηκαν τα μετρικά προτύπου: {avg_metrics.tolist()}")

    def add_city(self):
        # Dummy implementation for adding a city
        pass 

    def remove_city(self):
        selected_items = self.city_list_widget.selectedItems()
        if not selected_items: return
        for item in selected_items:
            city, _ = item.data(Qt.UserRole)
            del self.city_paths[city]
            self.city_list_widget.takeItem(self.city_list_widget.row(item))
            
    def apply_theme(self, theme_name):
        self.current_config["theme"] = theme_name
        stylesheet = config.generate_stylesheet(theme_name)
        QApplication.instance().setStyleSheet(stylesheet)

    def save_settings(self):
        if not self.scan_folder_edit.text() or not self.today_folder_edit.text():
            QMessageBox.warning(self, "Σφάλμα Επικύρωσης", "Ο Φάκελος Σάρωσης και ο Φάκελος Σημερινών Βιβλίων πρέπει να οριστούν.")
            return

        # Update config dictionary
        self.current_config["scan_folder"] = self.scan_folder_edit.text()
        self.current_config["todays_books_folder"] = self.today_folder_edit.text()
        self.current_config["lighting_standard_folder"] = self.ref_folder_edit.text()
        self.current_config["city_paths"] = self.city_paths
        self.current_config["caching_enabled"] = self.caching_checkbox.isChecked()
        self.current_config["auto_lighting_correction_enabled"] = self.auto_lighting_checkbox.isChecked()
        self.current_config["auto_color_correction_enabled"] = self.auto_color_checkbox.isChecked()
        self.current_config["auto_sharpening_enabled"] = self.auto_sharpen_checkbox.isChecked()
        
        if self.single_split_radio.isChecked():
            self.current_config["scanner_mode"] = "single_split"
        else:
            self.current_config["scanner_mode"] = "dual_scan"
            
        # Theme is already updated in apply_theme

        # Save to file
        config.save_config(self.current_config)
        QMessageBox.information(self, "Επιτυχία", "Οι ρυθμίσεις έχουν αποθηκευτεί.")
        self.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    initial_config = config.load_config()
    app.setStyleSheet(config.generate_stylesheet(initial_config.get("theme", "Material Dark")))
    dialog = SettingsDialog()
    dialog.exec()

