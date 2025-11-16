import os
import json
import time # Added for time.time() usage in cache
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QMessageBox
from PySide6.QtCore import Slot, QTimer, QRectF
from PySide6.QtGui import QMouseEvent

import config
from image_viewer import ImageViewer

class SingleSplitModeWidget(QWidget):
    """
    UI for the 'Single-Shot Splitting Mode'.
    """
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.app_config = main_window.app_config
        self._current_image_path = None
        self._layout_data_path = None
        self.is_dirty = False
        
        # --- Layout Data Cache (Issue 3.1 Fix) ---
        self._layout_cache = {}  # filename -> layout_data
        self._layout_cache_dirty = False
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(500)  # Debounce saves
        self._layout_save_timer.timeout.connect(self._flush_layout_cache)
        # -------------------------------------------

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
        self.update_button.setEnabled(False)

        self.left_page_toggle = self._create_toggle_button("Αριστερή Σελίδα")
        self.right_page_toggle = self._create_toggle_button("Δεξιά Σελίδα")

        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.left_page_toggle)
        toolbar_layout.addWidget(self.update_button)
        toolbar_layout.addWidget(self.right_page_toggle)
        toolbar_layout.addStretch()

        main_layout.addWidget(self.viewer)
        main_layout.addWidget(toolbar)

        # --- Connections ---
        self.viewer.layout_changed.connect(self.on_layout_changed)
        self.update_button.clicked.connect(self.on_update_clicked)
        self.viewer.image_loaded_for_layout.connect(self.on_viewer_ready_for_layout)

    def is_work_in_progress(self):
        """Returns True if the user is editing or has unsaved changes."""
        return self.main_window.is_navigation_allowed(check_only=True) == False

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
        # When a toggle is clicked, it's an edit, so enable the update button
        self.on_layout_changed()

    def _on_toggle_clicked(self):
        """
        Handles the logic when a page toggle is clicked.
        This operation immediately re-runs the page split logic and saves the layout.
        """
        self._update_toggle_styles()

        if not self._current_image_path:
            return

        current_layout = self.viewer.get_layout_ratios()
        if not current_layout:
            # If the viewer hasn't produced a layout yet, it means the image isn't ready
            return

        # Update the layout data based on which toggle was clicked
        current_layout['left_enabled'] = self.left_page_toggle.isChecked()
        current_layout['right_enabled'] = self.right_page_toggle.isChecked()

        # 1. Immediately update the viewer's UI to show/hide the crop rect
        self.viewer.set_layout_ratios(current_layout)

        # 2. Trigger the worker to create/delete the cropped files
        self.main_window.perform_page_split(self._current_image_path, current_layout)

        # 3. Save the updated layout data to the JSON file immediately (to cache)
        self.save_layout_data(self._current_image_path, current_layout)

    @Slot()
    def on_layout_changed(self):
        """Activates the update button when the user starts editing."""
        self.update_button.setEnabled(True)
        self.is_dirty = True
        self.main_window.update_work_state(dirty_layout=True)

    @Slot()
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

        # 1. Save the new layout data for the *current* image
        self.save_layout_data(self._current_image_path, current_layout)

        # 2. Trigger the worker to re-split the page with the new layout
        self.main_window.perform_page_split(self._current_image_path, current_layout)

        # 3. Disable the button and editing state, as the action is complete
        self.update_button.setEnabled(False)
        self.is_dirty = False
        self.main_window.update_work_state(dirty_layout=False)

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
            # No layout found - get the default, save it (to cache), and trigger the first split
            default_layout = self.viewer.get_layout_ratios()
            if default_layout:
                default_layout['left_enabled'] = True
                default_layout['right_enabled'] = True
                self.save_layout_data(self._current_image_path, default_layout)
                self.viewer.set_layout_ratios(default_layout)
                # Also trigger the initial split for this first image
                self.main_window.perform_page_split(self._current_image_path, default_layout)

        # Apply the correct visual style to the toggles
        self._update_toggle_styles()
        self.is_dirty = False
        self.update_button.setEnabled(False)
        self.main_window.update_work_state(dirty_layout=False)


    @Slot(str)
    def load_image(self, image_path):
        """Public method to load a new image and its corresponding layout."""
        self._current_image_path = image_path
        self.viewer.request_image_load(image_path)
        self.update_button.setEnabled(False)
        self.is_dirty = False
        self.main_window.update_work_state(editing=False, zoomed=False, dirty_layout=False)


    def _validate_layout_data(self, layout_data):
        """Validates layout data structure and value ranges (Issue 3.2 Fix)"""
        if not isinstance(layout_data, dict):
            return False
        
        required_keys = {'left', 'right'}
        if not required_keys.issubset(layout_data.keys()):
            return False
        
        for page_key in ['left', 'right']:
            page_layout = layout_data[page_key]
            if not isinstance(page_layout, dict):
                return False
            
            if not {'x', 'y', 'w', 'h'}.issubset(page_layout.keys()):
                return False
            
            for coord_key in ['x', 'y', 'w', 'h']:
                val = page_layout[coord_key]
                if not isinstance(val, (int, float)) or not (0 <= val <= 1):
                    return False
            
            if page_layout['w'] <= 0 or page_layout['h'] <= 0:
                return False
        
        return True


    def get_layout_for_image(self, image_path):
        """
        Retrieves the layout data for a given image from cache or previous file.
        (Uses cached data via _load_all_layout_data - Issue 3.1 Fix)
        """
        scan_folder = os.path.dirname(image_path)
        self._layout_data_path = os.path.join(scan_folder, 'layout_data.json')

        image_filename = os.path.basename(image_path)
        all_data = self._load_all_layout_data()

        # Case 1: Layout for the specific image exists
        if image_filename in all_data:
            layout = all_data[image_filename]
            if self._validate_layout_data(layout):
                return layout
            else:
                QMessageBox.critical(self, "Διόρθωση Σφάλματος", f"Το αρχείο layout για το '{image_filename}' βρέθηκε, αλλά ήταν κατεστραμμένο. Θα χρησιμοποιηθεί το προηγούμενο.")
                del all_data[image_filename] # Remove corrupted entry
                self._layout_cache_dirty = True
                # Fall through to case 2

        # Case 2: Find layout from the previous image
        sorted_files = sorted(self.main_window.image_files, key=lambda p: os.path.basename(p))
        try:
            current_index = sorted_files.index(image_path)
            if current_index > 0:
                prev_image_path = sorted_files[current_index - 1]
                prev_image_filename = os.path.basename(prev_image_path)
                layout = all_data.get(prev_image_filename)
                if layout and self._validate_layout_data(layout):
                    return layout
        except (ValueError, IndexError):
            pass

        # Case 3: No specific or previous valid layout found
        return None

    def save_layout_data(self, image_path, layout_data):
        """Saves the layout data for a specific image filename to the memory cache."""
        if not self._layout_data_path:
             scan_folder = os.path.dirname(image_path)
             self._layout_data_path = os.path.join(scan_folder, 'layout_data.json')

        image_filename = os.path.basename(image_path)
        
        # Load all data first to ensure we don't overwrite if cache is empty
        self._load_all_layout_data() 
        self._layout_cache[image_filename] = layout_data
        
        self._layout_save_timer.start() # Debounce disk write (Issue 3.1 Fix)

    @Slot()
    def _flush_layout_cache(self):
        """Writes cached layout data to disk atomically (Issue 3.1 Fix)"""
        if not self._layout_data_path or not self._layout_cache:
            return
        
        temp_path = self._layout_data_path + '.tmp'
        try:
            # 1. Write to temp file
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._layout_cache, f, indent=4, ensure_ascii=False)
            
            # 2. Atomic rename (rename/replace handles the final step)
            if os.path.exists(self._layout_data_path):
                os.remove(self._layout_data_path) # Need to remove before rename on windows if target exists
            os.rename(temp_path, self._layout_data_path)
            self._layout_cache_dirty = False
                
        except IOError as e:
            self.main_window.show_error(f"Could not save layout data: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def remove_layout_data(self, image_path):
        """Removes the layout data for a specific image filename from cache and disk."""
        if not self._layout_data_path:
             scan_folder = os.path.dirname(image_path)
             self._layout_data_path = os.path.join(scan_folder, 'layout_data.json')

        # Ensure cache is up-to-date before modification
        all_data = self._load_all_layout_data()
        image_filename = os.path.basename(image_path)

        if image_filename in all_data:
            del all_data[image_filename]
            self._layout_cache_dirty = True
            self._flush_layout_cache() # Force immediate flush after deletion


    def _load_all_layout_data(self):
        """Loads layout data only if cache is empty or invalidated (Issue 3.1 Fix)"""
        if not self._layout_cache_dirty and self._layout_cache:
            return self._layout_cache
            
        if self._layout_data_path and os.path.exists(self._layout_data_path):
            try:
                with open(self._layout_data_path, 'r', encoding='utf-8') as f:
                    self._layout_cache = json.load(f)
                self._layout_cache_dirty = False
                return self._layout_cache
            except (IOError, json.JSONDecodeError):
                self._layout_cache = {}
                self._layout_cache_dirty = True # Mark as dirty to prevent repeated file attempts
                return {}
        
        self._layout_cache = {}
        return {}