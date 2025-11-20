import sys
from PySide6.QtWidgets import (
    QApplication, QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QFileDialog, QMessageBox,
    QCheckBox, QDialogButtonBox, QFormLayout, QListWidgetItem, QGroupBox, QRadioButton
)
from PySide6.QtCore import Qt

import numpy as np
from PIL import Image
import os

from core.config_service import ConfigService

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DigiPage Scanner - Ρυθμίσεις")
        self.setMinimumSize(700, 600)

        self.config_service = ConfigService()
        self.current_config = self.config_service.get_config().copy()
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
        scan_folder_btn = QPushButton("Αναζήτηση...")
        scan_folder_btn.clicked.connect(lambda: self.browse_folder(self.scan_folder_edit, "Επιλογή Φακέλου Σάρωσης"))
        scan_folder_layout = QHBoxLayout()
        scan_folder_layout.addWidget(self.scan_folder_edit)
        scan_folder_layout.addWidget(scan_folder_btn)
        layout.addRow("Φάκελος Σάρωσης:", scan_folder_layout)

        # --- Today's Books Folder ---
        self.today_folder_edit = QLineEdit()
        self.today_folder_edit.setReadOnly(True)
        today_folder_btn = QPushButton("Αναζήτηση...")
        today_folder_btn.clicked.connect(lambda: self.browse_folder(self.today_folder_edit, "Επιλογή Φακέλου Σημερινών Βιβλίων"))
        today_folder_layout = QHBoxLayout()
        today_folder_layout.addWidget(self.today_folder_edit)
        today_folder_layout.addWidget(today_folder_btn)
        layout.addRow("Φάκελος Σημερινών Βιβλίων:", today_folder_layout)
        
        # --- Caching Checkbox ---
        self.caching_checkbox = QCheckBox("Ενεργοποίηση Προσωρινής Αποθήκευσης Εικόνων για Απόδοση")
        self.caching_checkbox.setToolTip("Όταν είναι ενεργοποιημένη, οι εικόνες διατηρούνται στη μνήμη για ταχύτερη επαναφόρτωση. Απενεργοποιήστε για δοκιμές ή για εξοικονόμηση μνήμης RAM.")
        layout.addRow(self.caching_checkbox)

        # --- Scanner Mode ---
        scanner_mode_group = QGroupBox("Τύπος Scanner / Λειτουργία")
        scanner_mode_layout = QVBoxLayout()
        self.dual_scan_radio = QRadioButton("Dual Scan (Δύο εικόνες, μία για κάθε σελίδα)")
        self.dual_scan_radio.setToolTip("Η προεπιλεγμένη λειτουργία για standard scanners που παράγουν μία εικόνα ανά σελίδα.")
        self.single_split_radio = QRadioButton("Single-Shot Split (Μία εικόνα για ένα πλήρες άνοιγμα βιβλίου)")
        self.single_split_radio.setToolTip("Λειτουργία για ειδικούς scanners που καταγράφουν και τις δύο σελίδες σε μία πλατιά εικόνα.")
        scanner_mode_layout.addWidget(self.dual_scan_radio)
        scanner_mode_layout.addWidget(self.single_split_radio)
        scanner_mode_group.setLayout(scanner_mode_layout)
        layout.addRow(scanner_mode_group)


        # --- City Data Paths ---
        layout.addRow(QLabel("Διαδρομές Δεδομένων Πόλεων:"))
        self.city_list_widget = QListWidget()
        self.city_list_widget.itemSelectionChanged.connect(self.on_city_selected)
        layout.addRow(self.city_list_widget)

        city_form_layout = QFormLayout()
        self.city_code_edit = QLineEdit()
        self.city_code_edit.setPlaceholderText("π.χ., 001")
        self.city_code_edit.setMaxLength(3)
        city_form_layout.addRow("Κωδικός Πόλης:", self.city_code_edit)

        self.city_path_edit = QLineEdit()
        self.city_path_edit.setReadOnly(True)
        city_path_btn = QPushButton("Αναζήτηση...")
        city_path_btn.clicked.connect(lambda: self.browse_folder(self.city_path_edit, "Επιλογή Φακέλου Δεδομένων Πόλης"))
        city_path_layout = QHBoxLayout()
        city_path_layout.addWidget(self.city_path_edit)
        city_path_layout.addWidget(city_path_btn)
        city_form_layout.addRow("Διαδρομή Φακέλου:", city_path_layout)
        layout.addRow(city_form_layout)

        city_button_layout = QHBoxLayout()
        add_update_btn = QPushButton("Προσθήκη/Ενημέρωση")
        add_update_btn.setProperty("class", "filled")
        add_update_btn.clicked.connect(self.add_update_city)
        remove_btn = QPushButton("Αφαίρεση")
        remove_btn.setProperty("class", "destructive")
        remove_btn.clicked.connect(self.remove_city)
        city_button_layout.addStretch()
        city_button_layout.addWidget(add_update_btn)
        city_button_layout.addWidget(remove_btn)
        layout.addRow(city_button_layout)

        self.tab_widget.addTab(tab, "Διαδρομές & Ροή Εργασίας")

    def create_lighting_correction_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        # --- Reference Images Folder ---
        self.ref_folder_edit = QLineEdit()
        self.ref_folder_edit.setReadOnly(True)
        ref_folder_btn = QPushButton("Αναζήτηση...")
        ref_folder_btn.clicked.connect(lambda: self.browse_folder(self.ref_folder_edit, "Επιλογή Φακέλου με Εικόνες Αναφοράς"))
        ref_folder_layout = QHBoxLayout()
        ref_folder_layout.addWidget(self.ref_folder_edit)
        ref_folder_layout.addWidget(ref_folder_btn)
        layout.addRow("Φάκελος Εικόνων Αναφοράς:", ref_folder_layout)

        # --- Calculate Standard Button ---
        calc_btn = QPushButton("Υπολογισμός και Αποθήκευση Προτύπου")
        calc_btn.setProperty("class", "filled")
        calc_btn.clicked.connect(self.calculate_and_save_standard)
        layout.addRow(calc_btn)

        # --- Auto Correction Toggles ---
        layout.addRow(QLabel("Αυτόματες Διορθώσεις σε Νέες Σαρώσεις:"))
        self.auto_lighting_checkbox = QCheckBox("Αυτόματη Προσαρμογή Φωτισμού & Αντίθεσης")
        self.auto_color_checkbox = QCheckBox("Αυτόματη Διόρθωση Απόχρωσης Χρώματος")
        self.auto_sharpen_checkbox = QCheckBox("Εφαρμογή ήπιας Ευκρίνειας")
        layout.addRow(self.auto_lighting_checkbox)
        layout.addRow(self.auto_color_checkbox)
        layout.addRow(self.auto_sharpen_checkbox)

        self.tab_widget.addTab(tab, "Φωτισμός & Διόρθωση")

    def create_theme_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)

        layout.addWidget(QLabel("Επιλέξτε ένα θέμα για άμεση εφαρμογή:"))

        from core.constants import THEMES

        button_layout = QHBoxLayout()
        for theme_name in THEMES.keys():
            btn = QPushButton(theme_name)
            btn.clicked.connect(lambda checked=False, name=theme_name: self.apply_theme(name))
            button_layout.addWidget(btn)

        layout.addLayout(button_layout)
        layout.addStretch()
        self.tab_widget.addTab(tab, "Θέμα")

    def browse_folder(self, line_edit, title):
        folder_path = QFileDialog.getExistingDirectory(self, title, line_edit.text())
        if folder_path:
            line_edit.setText(folder_path)

    def load_initial_values(self):
        self.scan_folder_edit.setText(self.current_config.get("scan_folder", ""))
        self.today_folder_edit.setText(self.current_config.get("todays_books_folder", ""))
        self.ref_folder_edit.setText(self.current_config.get("lighting_standard_folder", ""))
        self.caching_checkbox.setChecked(self.current_config.get("caching_enabled", True))

        scanner_mode = self.current_config.get("scanner_mode", "dual_scan")
        if scanner_mode == "single_split":
            self.single_split_radio.setChecked(True)
        else:
            self.dual_scan_radio.setChecked(True)

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
            QMessageBox.warning(self, "Σφάλμα Εισόδου", "Ο κωδικός πόλης και η διαδρομή δεν μπορούν να είναι κενά.")
            return

        if not code.isdigit() or len(code) != 3:
            QMessageBox.warning(self, "Σφάλμα Εισόδου", "Ο κωδικός πόλης πρέπει να είναι ακριβώς 3 ψηφία.")
            return

        self.city_paths[code] = path
        self.update_city_list()
        self.city_code_edit.clear()
        self.city_path_edit.clear()

    def remove_city(self):
        selected_items = self.city_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Σφάλμα Επιλογής", "Παρακαλώ επιλέξτε μια πόλη για αφαίρεση.")
            return

        item_text = selected_items[0].text()
        code = item_text.split(":", 1)[0].strip()

        reply = QMessageBox.question(self, "Επιβεβαίωση Διαγραφής", f"Είστε βέβαιοι ότι θέλετε να αφαιρέσετε την αντιστοίχιση για τον κωδικό πόλης '{code}'?")
        if reply == QMessageBox.Yes:
            if code in self.city_paths:
                del self.city_paths[code]
                self.update_city_list()

    def calculate_and_save_standard(self):
        folder_path = self.ref_folder_edit.text()
        if not os.path.isdir(folder_path):
            QMessageBox.critical(self, "Σφάλμα", "Η καθορισμένη διαδρομή δεν είναι έγκυρος φάκελος.")
            return

        image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in ['.jpg', '.png']] # Assume extension

        if not image_files:
            QMessageBox.warning(self, "Δεν Βρέθηκαν Εικόνες", "Ο επιλεγμένος φάκελος δεν περιέχει υποστηριζόμενα αρχεία εικόνων.")
            return

        try:
            pil_images = [Image.open(p).convert('RGB') for p in image_files]
            if not pil_images:
                QMessageBox.warning(self, "Προειδοποίηση", "Δεν ήταν δυνατή η πρόσβαση σε έγκυρες εικόνες.")
                return

            target_size = pil_images[0].size
            resized_images_np = []
            for img in pil_images:
                resized_img = img.resize(target_size, Image.Resampling.LANCZOS)
                resized_images_np.append(np.array(resized_img))

            avg_image_array = np.mean(resized_images_np, axis=0).astype(np.uint8)
            template_image = Image.fromarray(avg_image_array, 'RGB')

            from core.constants import CONFIG_FILE
            template_path = os.path.splitext(CONFIG_FILE)[0] + "_template.png"
            template_image.save(template_path)

            self.current_config['lighting_standard_metrics'] = {'histogram_template_path': template_path}
            QMessageBox.information(self, "Επιτυχία", f"Υπολογίστηκε με επιτυχία το πρότυπο από {len(pil_images)} εικόνες.\nΠρότυπο αποθηκεύτηκε στη διαδρομή: {template_path}")
        except Exception as e:
            QMessageBox.critical(self, "Αποτυχία Υπολογισμού", f"Προέκυψε ένα σφάλμα: {e}")

    def apply_theme(self, theme_name):
        self.current_config["theme"] = theme_name
        # Save temporarily to config service so changes persist across dialog
        self.config_service.set("theme", theme_name)
        stylesheet = self.config_service.generate_stylesheet()
        QApplication.instance().setStyleSheet(stylesheet)

    def save_settings(self):
        # Validation
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

        # Save via service
        for key, value in self.current_config.items():
            self.config_service.set(key, value)

        QMessageBox.information(self, "Επιτυχία", "Οι ρυθμίσεις έχουν αποθηκευτεί.")
        self.accept()
