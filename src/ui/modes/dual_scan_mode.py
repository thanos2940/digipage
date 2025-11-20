from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QFrame, QToolButton, QSpacerItem, QSizePolicy, QStackedWidget, QMessageBox
)
from PySide6.QtCore import Slot, Signal
from core.config_service import ConfigService
from core.constants import THEMES
from ..image_viewer import ImageViewer
from .base_mode import BaseModeWidget

class DualScanMode(BaseModeWidget):
    # Add Signals directly here if BaseModeWidget inheritance is tricky
    request_color_fix = Signal(str)
    request_delete = Signal(str)
    request_restore = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_service = ConfigService()
        self.viewer1_panel = None
        self.viewer2_panel = None
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        self.viewer1_panel = self._create_viewer_panel()
        self.viewer2_panel = self._create_viewer_panel()

        layout.addWidget(self.viewer1_panel['frame'])
        layout.addWidget(self.viewer2_panel['frame'])

    def _create_viewer_panel(self):
        frame = QFrame()
        frame.setObjectName("ViewerFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        viewer = ImageViewer()
        viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        theme_name = self.config_service.get("theme", "Material Dark")
        theme_data = THEMES.get(theme_name, THEMES["Material Dark"])
        viewer.set_theme_colors(theme_data['PRIMARY'], theme_data['TERTIARY'])

        layout.addWidget(viewer)

        toolbar = QFrame(frame)
        toolbar.setObjectName("StaticToolbar")
        toolbar.setFixedHeight(55)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        toolbar_layout.setSpacing(10)

        controls = {}
        controls_stack = QStackedWidget()
        toolbar_layout.addWidget(controls_stack)

        # Normal Page
        normal_controls_page = QWidget()
        normal_layout = QHBoxLayout(normal_controls_page)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_layout.setSpacing(10)

        controls['crop'] = QToolButton(); controls['crop'].setText("Περικοπή"); controls['crop'].setObjectName("crop_button")
        controls['split'] = QToolButton(); controls['split'].setText("Διαχωρισμός")
        controls['rotate'] = QToolButton(); controls['rotate'].setText("Περιστροφή")
        controls['fix_color'] = QToolButton(); controls['fix_color'].setText("Χρώμα")
        controls['restore'] = QToolButton(); controls['restore'].setText("Επαναφορά"); controls['restore'].setObjectName("restore_button")
        controls['delete'] = QToolButton(); controls['delete'].setText("Διαγραφή"); controls['delete'].setObjectName("delete_button")

        for key in ['crop', 'split', 'rotate', 'fix_color', 'restore', 'delete']:
             normal_layout.addWidget(controls[key])

        normal_layout.insertStretch(0)
        normal_layout.addStretch()
        controls_stack.addWidget(normal_controls_page)

        # Split Page
        split_controls_page = QWidget()
        split_layout = QHBoxLayout(split_controls_page)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(10)
        controls['split_mode_label'] = QLabel("ΔΙΑΧΩΡΙΣΜΟΣ")
        controls['confirm_split'] = QPushButton("Επιβεβαίωση"); controls['confirm_split'].setProperty("class", "success filled")
        controls['cancel_split'] = QPushButton("Άκυρο"); controls['cancel_split'].setProperty("class", "destructive")

        split_layout.addStretch()
        split_layout.addWidget(controls['split_mode_label'])
        split_layout.addWidget(controls['confirm_split'])
        split_layout.addWidget(controls['cancel_split'])
        split_layout.addStretch()
        controls_stack.addWidget(split_controls_page)

        # Rotate Page
        rotate_controls_page = QWidget()
        rotate_layout = QHBoxLayout(rotate_controls_page)
        rotate_layout.setContentsMargins(0, 0, 0, 0)
        rotate_layout.setSpacing(10)
        controls['rotate_mode_label'] = QLabel("ΠΕΡΙΣΤΡΟΦΗ")
        controls['cancel_rotate'] = QPushButton("Τέλος"); controls['cancel_rotate'].setProperty("class", "destructive")

        rotate_layout.addStretch()
        rotate_layout.addWidget(controls['rotate_mode_label'])
        rotate_layout.addWidget(controls['cancel_rotate'])
        rotate_layout.addStretch()
        controls_stack.addWidget(rotate_controls_page)

        layout.addWidget(toolbar)

        panel_widgets = {'frame': frame, 'viewer': viewer, 'toolbar': toolbar, 'controls_stack': controls_stack, **controls}

        # Local connections to handlers
        controls['crop'].clicked.connect(lambda: self.apply_crop(panel_widgets))
        controls['fix_color'].clicked.connect(lambda: self.apply_color_fix(panel_widgets))
        controls['split'].clicked.connect(lambda: self.toggle_split_mode(panel_widgets, True))
        controls['rotate'].clicked.connect(lambda: self.toggle_rotate_mode(panel_widgets, True))
        # For delete and restore, we need help from services, emit signals?
        # Actually, we can emit signal with path
        controls['delete'].clicked.connect(lambda: self.delete_image(panel_widgets))
        controls['restore'].clicked.connect(lambda: self.restore_image(panel_widgets))

        controls['confirm_split'].clicked.connect(lambda: self.apply_split(panel_widgets))
        controls['cancel_split'].clicked.connect(lambda: self.toggle_split_mode(panel_widgets, False))
        controls['cancel_rotate'].clicked.connect(lambda: self.toggle_rotate_mode(panel_widgets, False))

        # Connect viewer signals
        viewer.load_requested.connect(self.request_image_load)
        viewer.crop_adjustment_started.connect(self.editing_started)
        viewer.crop_adjustment_finished.connect(self.editing_finished)
        viewer.zoom_state_changed.connect(self.viewer_zoom_changed)
        viewer.rotation_finished.connect(self.request_rotation) # Pass through

        controls_stack.setCurrentIndex(0)
        toolbar.setEnabled(False)

        return panel_widgets

    # --- Handlers ---

    def load_images(self, files):
        # Expects 2 files max
        path1 = files[0] if len(files) > 0 else None
        path2 = files[1] if len(files) > 1 else None

        self.viewer1_panel['viewer'].request_image_load(path1)
        self.viewer2_panel['viewer'].request_image_load(path2)

        self.viewer1_panel['toolbar'].setEnabled(path1 is not None)
        self.viewer2_panel['toolbar'].setEnabled(path2 is not None)

    def on_image_loaded(self, path, pixmap):
        if self.viewer1_panel['viewer'].image_path == path:
            self.viewer1_panel['viewer'].on_image_loaded(path, pixmap)
        if self.viewer2_panel['viewer'].image_path == path:
            self.viewer2_panel['viewer'].on_image_loaded(path, pixmap)

    def get_visible_paths(self):
        paths = []
        if self.viewer1_panel['viewer'].image_path: paths.append(self.viewer1_panel['viewer'].image_path)
        if self.viewer2_panel['viewer'].image_path: paths.append(self.viewer2_panel['viewer'].image_path)
        return paths

    def clear_viewers(self):
        self.viewer1_panel['viewer'].clear_image()
        self.viewer2_panel['viewer'].clear_image()
        self.viewer1_panel['toolbar'].setEnabled(False)
        self.viewer2_panel['toolbar'].setEnabled(False)

    # --- Action Logic ---

    def apply_crop(self, panel):
        viewer = panel['viewer']
        if viewer.image_path:
             rect = viewer.get_image_space_crop_rect()
             if rect:
                 self.request_crop.emit(viewer.image_path, rect)


    def apply_color_fix(self, panel):
        if panel['viewer'].image_path:
             self.request_color_fix.emit(panel['viewer'].image_path)

    def delete_image(self, panel):
        if panel['viewer'].image_path:
            reply = QMessageBox.question(self, "Confirm Delete", f"Delete {panel['viewer'].image_path}?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.request_delete.emit(panel['viewer'].image_path)
                panel['viewer'].clear_image()
                panel['toolbar'].setEnabled(False)

    def restore_image(self, panel):
        if panel['viewer'].image_path:
            self.request_restore.emit(panel['viewer'].image_path)

    def toggle_split_mode(self, panel, enable):
        panel['viewer'].set_splitting_mode(enable)
        if enable:
            panel['controls_stack'].setCurrentIndex(1)
            self.editing_started.emit()
        else:
            panel['controls_stack'].setCurrentIndex(0)
            self.editing_finished.emit()

    def toggle_rotate_mode(self, panel, enable):
        panel['viewer'].set_rotating_mode(enable)
        if enable:
            panel['controls_stack'].setCurrentIndex(2)
            self.editing_started.emit()
        else:
            panel['controls_stack'].setCurrentIndex(0)
            self.editing_finished.emit()

    def apply_split(self, panel):
        viewer = panel['viewer']
        if viewer.image_path:
             split_x = viewer.get_split_x_in_image_space()
             if split_x is not None:
                 self.request_split.emit(viewer.image_path, split_x)
        self.toggle_split_mode(panel, False)
