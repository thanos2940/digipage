from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame
from PySide6.QtCore import Slot, Signal
import os
import json

from .base_mode import BaseModeWidget
from ..image_viewer import ImageViewer, InteractionMode
from core.config_service import ConfigService
from core.constants import THEMES

class SingleSplitMode(BaseModeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_service = ConfigService()
        self._current_image_path = None
        self._layout_data_path = None
        self.is_dirty = False
        self.image_files = [] # Ref to main file list, needed for "previous image" logic

        # --- UI ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.viewer = ImageViewer(self)
        self.viewer.set_page_splitting_mode(True)

        # Apply theme
        theme_name = self.config_service.get("theme", "Material Dark")
        theme_data = THEMES.get(theme_name, THEMES["Material Dark"])
        self.viewer.set_theme_colors(theme_data['PRIMARY'], theme_data['TERTIARY'])

        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("StaticToolbar")
        toolbar.setFixedHeight(60)
        toolbar_layout = QHBoxLayout(toolbar)

        self.update_button = QPushButton("Ενημέρωση Layout")
        self.update_button.setProperty("class", "filled success")
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

        # Connections
        self.viewer.layout_changed.connect(self.on_layout_changed)
        self.update_button.clicked.connect(self.on_update_clicked)
        self.viewer.image_loaded_for_layout.connect(self.on_viewer_ready_for_layout)
        self.viewer.load_requested.connect(self.request_image_load)
        self.viewer.crop_adjustment_started.connect(self.editing_started)
        self.viewer.crop_adjustment_finished.connect(self.editing_finished)
        self.viewer.zoom_state_changed.connect(self.viewer_zoom_changed)

    def _create_toggle_button(self, text):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(True)
        button.setMinimumHeight(40)
        button.clicked.connect(self._on_toggle_clicked)
        return button

    def load_images(self, files):
        # In single mode, we expect 1 file
        self.image_files = files # Just for context if needed, though usually we get just the current one
        if not files:
            self.clear_viewers()
            return

        # We actually need the full list from ScanSession to do the "previous layout" logic
        # But load_images is usually called with the current view.
        # So we will assume 'files' contains just the image to show.
        path = files[0]
        self._current_image_path = path
        self.viewer.request_image_load(path)
        self.update_button.setEnabled(False)
        self.is_dirty = False

    def on_image_loaded(self, path, pixmap):
        if path == self._current_image_path:
            self.viewer.on_image_loaded(path, pixmap)

    def get_visible_paths(self):
        return [self._current_image_path] if self._current_image_path else []

    def clear_viewers(self):
        self._current_image_path = None
        self.viewer.clear_image()
        self.update_button.setEnabled(False)

    def is_work_in_progress(self):
        return self.is_dirty

    def set_file_list_context(self, all_files):
        """Need this to look up previous image layout."""
        self.image_files = all_files

    def _update_toggle_styles(self):
        for button in [self.left_page_toggle, self.right_page_toggle]:
            if button.isChecked():
                button.setProperty("class", "")
            else:
                button.setProperty("class", "destructive")
            button.style().unpolish(button)
            button.style().polish(button)
        self.on_layout_changed()

    def _on_toggle_clicked(self):
        self._update_toggle_styles()
        if not self._current_image_path: return

        current_layout = self.viewer.get_layout_ratios()
        if not current_layout:
            # Try to fetch if not set
             current_layout = self.get_layout_for_image(self._current_image_path)
             if current_layout:
                 self.viewer.set_layout_ratios(current_layout)
             else:
                 return

        current_layout['left_enabled'] = self.left_page_toggle.isChecked()
        current_layout['right_enabled'] = self.right_page_toggle.isChecked()

        self.viewer.set_layout_ratios(current_layout)

        # Emit signal to trigger backend processing
        # We are reimplementing perform_page_split via signal
        # The MainWindow will connect this to the service
        self.layout_changed.emit(self._current_image_path, current_layout)

        self.save_layout_data(self._current_image_path, current_layout)

    def on_layout_changed(self, path=None, layout=None):
        self.update_button.setEnabled(True)
        self.is_dirty = True
        self.editing_started.emit()

    def on_update_clicked(self):
        if not self._current_image_path: return
        current_layout = self.viewer.get_layout_ratios()
        if not current_layout: return

        current_layout['left_enabled'] = self.left_page_toggle.isChecked()
        current_layout['right_enabled'] = self.right_page_toggle.isChecked()

        self.save_layout_data(self._current_image_path, current_layout)
        self.layout_changed.emit(self._current_image_path, current_layout)

        self.update_button.setEnabled(False)
        self.is_dirty = False
        self.editing_finished.emit()

    @Slot(str)
    def on_viewer_ready_for_layout(self, image_path):
        if image_path != self._current_image_path: return

        layout = self.get_layout_for_image(self._current_image_path)
        if layout:
            self.viewer.set_layout_ratios(layout)
            self.left_page_toggle.setChecked(layout.get('left_enabled', True))
            self.right_page_toggle.setChecked(layout.get('right_enabled', True))
        else:
            default_layout = self.viewer.get_layout_ratios()
            if default_layout:
                default_layout['left_enabled'] = True
                default_layout['right_enabled'] = True
                self.save_layout_data(self._current_image_path, default_layout)
                self.viewer.set_layout_ratios(default_layout)
                # Auto-split first time
                self.layout_changed.emit(self._current_image_path, default_layout)

        self._update_toggle_styles()
        self.is_dirty = False
        self.update_button.setEnabled(False)

    # Layout Persistence Logic (Keep local or move to service? Local seems fine for mode-specific data)
    def get_layout_for_image(self, image_path):
        scan_folder = os.path.dirname(image_path)
        self._layout_data_path = os.path.join(scan_folder, 'layout_data.json')
        image_filename = os.path.basename(image_path)
        all_data = self._load_all_layout_data()

        if image_filename in all_data:
            return all_data[image_filename]

        # Find previous
        try:
            # Using self.image_files which should be updated by set_file_list_context
            sorted_files = sorted(self.image_files, key=lambda p: os.path.basename(p))
            if image_path in sorted_files:
                idx = sorted_files.index(image_path)
                if idx > 0:
                    prev_name = os.path.basename(sorted_files[idx-1])
                    if prev_name in all_data:
                        return all_data[prev_name]
        except Exception: pass
        return None

    def save_layout_data(self, image_path, layout_data):
        if not self._layout_data_path:
             scan_folder = os.path.dirname(image_path)
             self._layout_data_path = os.path.join(scan_folder, 'layout_data.json')

        all_data = self._load_all_layout_data()
        image_filename = os.path.basename(image_path)
        all_data[image_filename] = layout_data

        try:
            with open(self._layout_data_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=4)
        except IOError: pass

    def remove_layout_data(self, image_path):
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
            except IOError: pass

    def _load_all_layout_data(self):
        if self._layout_data_path and os.path.exists(self._layout_data_path):
            try:
                with open(self._layout_data_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (IOError, json.JSONDecodeError):
                return {}
        return {}
