import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QStackedWidget,
    QLabel, QSpacerItem, QSizePolicy, QToolButton
)
from PySide6.QtCore import Slot, QTimer

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

    WORKFLOW:
    1. A new image is detected in the scan folder.
    2. The system automatically:
       - Loads the crop layout from the previous image.
       - Saves this layout for the new image (inheritance).
       - Performs an automatic crop/split operation.
       - Saves the cropped pages to the 'final' subfolder.
    3. The user can navigate to any image and see its specific crop areas.
    4. If the auto-crop is incorrect, the user adjusts the layout and clicks "Update Layout".
    5. When an image is deleted, all related files (original, crops, layout) are removed.
    """
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.app_config = main_window.app_config
        self._current_image_path = None
        self._layout_data_path = None
        self.is_dirty = False

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

        self.controls_stack = QStackedWidget()
        toolbar_layout.addWidget(self.controls_stack)

        # --- Normal Controls ---
        normal_controls_page = QWidget()
        normal_layout = QHBoxLayout(normal_controls_page)
        normal_layout.setContentsMargins(0, 0, 0, 0)

        self.update_button = QPushButton("Ενημέρωση Layout")
        self.update_button.setToolTip("Αποθηκεύει τις τρέχουσες θέσεις των πλαισίων και ενημερώνει τις εικόνες στο φάκελο 'final'.")
        self.update_button.setProperty("class", "filled success")
        self.update_button.setMinimumHeight(40)
        self.update_button.setEnabled(False)

        self.left_page_toggle = self._create_toggle_button("Αριστερή Σελίδα")
        self.right_page_toggle = self._create_toggle_button("Δεξιά Σελίδα")

        self.rotate_left_button = QToolButton(); self.rotate_left_button.setText("⟲ Αριστερά"); self.rotate_left_button.setMinimumHeight(40)
        self.rotate_right_button = QToolButton(); self.rotate_right_button.setText("Δεξιά ⟳"); self.rotate_right_button.setMinimumHeight(40)

        normal_layout.addStretch()
        normal_layout.addWidget(self.left_page_toggle)
        normal_layout.addWidget(self.rotate_left_button)
        normal_layout.addWidget(self.update_button)
        normal_layout.addWidget(self.rotate_right_button)
        normal_layout.addWidget(self.right_page_toggle)
        normal_layout.addStretch()
        self.controls_stack.addWidget(normal_controls_page)

        # --- Rotate Controls ---
        rotate_controls_page = QWidget()
        rotate_layout = QHBoxLayout(rotate_controls_page)
        rotate_layout.setContentsMargins(0, 0, 0, 0)
        rotate_layout.setSpacing(10)

        self.rotate_mode_label = QLabel("ΠΕΡΙΣΤΡΟΦΗ")
        self.cancel_rotate_button = QPushButton("Τέλος"); self.cancel_rotate_button.setProperty("class", "destructive")

        rotate_layout.addStretch()
        rotate_layout.addWidget(self.rotate_mode_label)
        rotate_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Fixed, QSizePolicy.Minimum))
        rotate_layout.addWidget(self.cancel_rotate_button)
        rotate_layout.addStretch()
        self.controls_stack.addWidget(rotate_controls_page)

        main_layout.addWidget(self.viewer)
        main_layout.addWidget(toolbar)

        # --- Connections (to be handled by MainWindow)---
        self.viewer.layout_changed.connect(self.on_layout_changed)
        self.update_button.clicked.connect(self.on_update_clicked)
        self.viewer.image_loaded_for_layout.connect(self.on_viewer_ready_for_layout)
        self.rotate_left_button.clicked.connect(lambda: self.toggle_rotate_mode('left', True))
        self.rotate_right_button.clicked.connect(lambda: self.toggle_rotate_mode('right', True))
        self.cancel_rotate_button.clicked.connect(self.on_cancel_rotate)
        self.viewer.rotation_changed_by_drag.connect(self.on_rotation_drag_finished)


    def on_rotation_drag_finished(self):
        self.on_update_clicked()

    def toggle_rotate_mode(self, page, enabled):
        self.viewer.set_page_split_rotating_mode(page, enabled)
        if enabled:
            self.controls_stack.setCurrentIndex(1)
        else:
            self.controls_stack.setCurrentIndex(0)
            # After finishing rotation, trigger an update
            self.on_update_clicked()

    def on_cancel_rotate(self):
        page = self.viewer.rotating_page
        if page:
            self.toggle_rotate_mode(page, False)

    def is_work_in_progress(self):
        """Returns True if the user is editing or has unsaved changes."""
        return self.main_window.is_actively_editing or self.is_dirty

    def _create_toggle_button(self, text):
        """Helper to create a styled, checkable button."""
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(True)
        button.setMinimumHeight(40)
        button.clicked.connect(self._on_toggle_clicked)
        return button

    def _update_toggle_styles(self):
        """Updates the visual style of toggle buttons based on their checked state."""
        for button in [self.left_page_toggle, self.right_page_toggle]:
            if button.isChecked():
                button.setProperty("class", "")
            else:
                button.setProperty("class", "destructive")
            # Force style re-application
            button.style().unpolish(button)
            button.style().polish(button)

    def _on_toggle_clicked(self):
        """
        Handles the logic when a page toggle is clicked.
        This method immediately updates the layout, shows/hides the crop area,
        and triggers the worker to create or delete the cropped image file.
        """
        self._update_toggle_styles()
        self.on_layout_changed(immediate_update=True)

        if not self._current_image_path:
            return

        # Get the current layout from the viewer; if it's not there, get the default.
        current_layout = self.viewer.get_layout_ratios()
        if not current_layout:
            # This can happen if the layout hasn't been initialized yet.
            # We can try to get it from the image data, which will establish a default if needed.
            layout_from_storage = self.get_layout_for_image(self._current_image_path)
            if layout_from_storage:
                self.viewer.set_layout_ratios(layout_from_storage)
                current_layout = layout_from_storage
            else:
                # If there's still no layout, we can't proceed.
                return

        # Update the layout data based on which toggle was clicked
        current_layout['left_enabled'] = self.left_page_toggle.isChecked()
        current_layout['right_enabled'] = self.right_page_toggle.isChecked()

        # Ensure rotation values are present
        current_layout.setdefault('rotation_left', 0.0)
        current_layout.setdefault('rotation_right', 0.0)

        # 1. Immediately update the viewer's UI to show/hide the crop rect
        self.viewer.set_layout_ratios(current_layout)

        # 2. Trigger the worker to create/delete the cropped files
        # The worker's perform_page_split handles both creation and deletion
        self.main_window.perform_page_split(self._current_image_path, current_layout)

        # 3. Save the updated layout data to the JSON file immediately.
        # This ensures the toggle state is remembered when navigating away and back.
        self.save_layout_data(self._current_image_path, current_layout)

        # 4. The call to _update_toggle_styles() already enables the "Update" button
        #    via on_layout_changed(), so the user can still save this as a
        #    permanent layout change for subsequent images.



    def on_layout_changed(self, immediate_update=False):
        """
        Activates the update button when the user starts editing.
        If immediate_update is True, it also saves and processes the image.
        """
        self.update_button.setEnabled(True)
        self.is_dirty = True
        if immediate_update:
            self.on_update_clicked()

    def on_update_clicked(self):
        """Saves the current layout and triggers the reprocessing of the image."""
        if not self._current_image_path:
            return

        current_layout = self.viewer.get_layout_ratios()
        if not current_layout:
            return

        # Add the toggle states to the layout data
        current_layout['left_enabled'] = self.left_page_toggle.isChecked()
        current_layout['right_enabled'] = self.right_page_toggle.isChecked()

        # Ensure rotation values are carried over
        current_layout.setdefault('rotation_left', 0.0)
        current_layout.setdefault('rotation_right', 0.0)

        # 1. Save the new layout data for the *current* image
        self.save_layout_data(self._current_image_path, current_layout)

        # 2. Trigger the worker to re-split the page with the new layout
        self.main_window.perform_page_split(self._current_image_path, current_layout)

        # 3. Disable the button and editing state, as the action is complete
        self.update_button.setEnabled(False)
        self.is_dirty = False
        self.main_window.is_actively_editing = False

        # 4. Show feedback to user
        self.main_window.statusBar().showMessage(
            f"Ενημέρωση layout για {os.path.basename(self._current_image_path)}...", 3000
        )

    @Slot(str)
    def on_viewer_ready_for_layout(self, image_path):
        """Applies the correct layout once the viewer confirms the image is loaded."""
        if image_path != self._current_image_path:
            return

        layout = self.get_layout_for_image(self._current_image_path)

        if layout:
            # Apply the existing layout
            self.viewer.set_layout_ratios(layout)
            # Set the toggle buttons state from the loaded layout
            self.left_page_toggle.setChecked(layout.get('left_enabled', True))
            self.right_page_toggle.setChecked(layout.get('right_enabled', True))
        else:
            # No layout found - get the default, save it, and trigger the first split
            default_layout = self.viewer.get_layout_ratios()
            if default_layout:
                default_layout['left_enabled'] = True
                default_layout['right_enabled'] = True
                self.save_layout_data(self._current_image_path, default_layout)
                self.viewer.set_layout_ratios(default_layout) # Apply the default to the view
                # Also trigger the initial split for this first image
                self.main_window.perform_page_split(self._current_image_path, default_layout)

        # Apply the correct visual style to the toggles
        self._update_toggle_styles()
        # After applying the definitive layout, reset the dirty flag.
        # Any subsequent change will set it back to True via on_layout_changed.
        self.is_dirty = False
        self.update_button.setEnabled(False)


    @Slot(str)
    def load_image(self, image_path):
        """Public method to load a new image and its corresponding layout."""
        self._current_image_path = image_path
        self.viewer.request_image_load(image_path)
        self.update_button.setEnabled(False)
        self.is_dirty = False
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

    def remove_layout_data(self, image_path):
        """Removes the layout data for a specific image filename."""
        if not self._layout_data_path:
             scan_folder = os.path.dirname(image_path)
             self._layout_data_path = os.path.join(scan_folder, 'layout_data.json')

        all_data = self._load_all_layout_data()
        image_filename = os.path.basename(image_path)

        if image_filename in all_data:
            del all_data[image_filename]
            try:
                with open(self._layout_data_path, 'w', encoding='utf-8') as f:
                    json.dump(all_data, f, indent=4)
            except IOError as e:
                self.main_window.show_error(f"Could not update layout data after deletion: {e}")

    def _load_all_layout_data(self):
        """Loads the entire layout data file, returning {} if it doesn't exist."""
        if self._layout_data_path and os.path.exists(self._layout_data_path):
            try:
                with open(self._layout_data_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (IOError, json.JSONDecodeError):
                return {} # Return empty dict on error
        return {}