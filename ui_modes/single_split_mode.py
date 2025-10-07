import os
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame
from PySide6.QtCore import Slot

import config
from image_viewer import ImageViewer

class SingleSplitModeWidget(QWidget):
    """
    UI for the 'Single-Shot Splitting Mode'.

    This widget displays a single, wide image and allows the user to define
    two crop areas (left and right pages). The core philosophy is that the
    system performs the cropping automatically based on the last known layout,
    and the user only intervenes to adjust the layout and click "Update"
    if the automatic result is incorrect.
    """
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.app_config = main_window.app_config
        self._current_image_path = None
        self._layout_data_path = None

        # --- Main UI ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Viewer ---
        self.viewer = ImageViewer(self)
        theme_name = self.app_config.get("theme", "Material Dark")
        theme_data = config.THEMES.get(theme_name, config.THEMES["Material Dark"])
        self.viewer.set_theme_colors(theme_data['PRIMARY'], theme_data['TERTIARY'])
        self.viewer.set_page_splitting_mode(True)

        # --- Bottom Toolbar ---
        toolbar = QFrame()
        toolbar.setObjectName("StaticToolbar")
        toolbar.setFixedHeight(60)
        toolbar_layout = QHBoxLayout(toolbar)

        self.update_button = QPushButton("Ενημέρωση Layout")
        self.update_button.setToolTip("Αποθηκεύει τις τρέχουσες θέσεις των πλαισίων και ενημερώνει τις εικόνες στο φάκελο 'final'.")
        self.update_button.setProperty("class", "filled success")
        self.update_button.setMinimumHeight(40)
        self.update_button.setEnabled(False) # Disabled by default

        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.update_button)
        toolbar_layout.addStretch()

        main_layout.addWidget(self.viewer)
        main_layout.addWidget(toolbar)

        # --- Connections (to be handled by MainWindow)---
        self.viewer.layout_changed.connect(self.on_layout_changed)
        self.update_button.clicked.connect(self.on_update_clicked)

    def on_layout_changed(self):
        """Activates the update button when the user starts editing."""
        self.update_button.setEnabled(True)
        self.main_window.is_actively_editing = True

    def on_update_clicked(self):
        """Saves the current layout and triggers the reprocessing of the image."""
        if not self._current_image_path:
            return

        current_layout = self.viewer.get_layout_ratios()
        if not current_layout:
            return

        # 1. Save the new layout data for the *current* image
        self.save_layout_data(self._current_image_path, current_layout)

        # 2. Trigger the worker to re-split the page with the new layout
        self.main_window.perform_page_split(self._current_image_path, current_layout)

        # 3. Disable the button and editing state, as the action is complete
        self.update_button.setEnabled(False)
        self.main_window.is_actively_editing = False

    @Slot(str)
    def load_image(self, image_path):
        """Public method to load a new image and its corresponding layout."""
        self._current_image_path = image_path
        self.viewer.request_image_load(image_path)
        self.update_button.setEnabled(False)
        self.main_window.is_actively_editing = False

    def get_layout_for_image(self, image_path):
        """
        Retrieves the layout data for a given image.
        - If a layout for the specific image exists, it's returned.
        - If not, it retrieves the layout from the immediately preceding image.
        - If neither exists, returns None.
        """
        scan_folder = os.path.dirname(image_path)
        self._layout_data_path = os.path.join(scan_folder, 'layout_data.json')

        image_filename = os.path.basename(image_path)

        all_data = self._load_all_layout_data()

        # Case 1: Layout for the specific image exists
        if image_filename in all_data:
            return all_data[image_filename]

        # Case 2: Find layout from the previous image
        sorted_files = sorted(self.main_window.image_files, key=lambda p: os.path.basename(p))
        try:
            current_index = sorted_files.index(image_path)
            if current_index > 0:
                prev_image_path = sorted_files[current_index - 1]
                prev_image_filename = os.path.basename(prev_image_path)
                if prev_image_filename in all_data:
                    return all_data[prev_image_filename]
        except (ValueError, IndexError):
            pass

        # Case 3: No specific or previous layout found
        return None

    def save_layout_data(self, image_path, layout_data):
        """Saves the layout data for a specific image filename."""
        if not self._layout_data_path:
             scan_folder = os.path.dirname(image_path)
             self._layout_data_path = os.path.join(scan_folder, 'layout_data.json')

        all_data = self._load_all_layout_data()
        image_filename = os.path.basename(image_path)
        all_data[image_filename] = layout_data

        try:
            with open(self._layout_data_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=4)
        except IOError as e:
            self.main_window.show_error(f"Could not save layout data: {e}")

    def _load_all_layout_data(self):
        """Loads the entire layout data file, returning {} if it doesn't exist."""
        if self._layout_data_path and os.path.exists(self._layout_data_path):
            try:
                with open(self._layout_data_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (IOError, json.JSONDecodeError):
                return {} # Return empty dict on error
        return {}