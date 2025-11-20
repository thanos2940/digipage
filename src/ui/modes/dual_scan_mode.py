from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QFrame, QToolButton, QSpacerItem, QSizePolicy, QStackedWidget
)
from ...core import config
from ..image_viewer import ImageViewer

class DualScanModeWidget(QWidget):
    """
    UI for the 'dual_scan' mode, featuring two image viewers side-by-side.
    """
    def __init__(self, main_window, app_config, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.app_config = app_config
        self.viewer1 = None
        self.viewer2 = None
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        self.viewer1 = self._create_viewer_panel()
        self.viewer2 = self._create_viewer_panel()

        layout.addWidget(self.viewer1['frame'])
        layout.addWidget(self.viewer2['frame'])

    def _create_viewer_panel(self):
        frame = QFrame()
        frame.setObjectName("ViewerFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        viewer = ImageViewer()
        viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        theme_data = config.THEMES.get(self.app_config.get("theme"), config.THEMES["Material Dark"])
        primary_color = theme_data.get("PRIMARY", "#b0c6ff")
        tertiary_color = theme_data.get("TERTIARY", "#e2bada")
        viewer.set_theme_colors(primary_color, tertiary_color)

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

        normal_controls_page = QWidget()
        normal_layout = QHBoxLayout(normal_controls_page)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_layout.setSpacing(10)

        controls['crop'] = QToolButton(); controls['crop'].setText("Περικοπή"); controls['crop'].setToolTip("Εφαρμογή Περικοπής"); controls['crop'].setObjectName("crop_button")
        controls['split'] = QToolButton(); controls['split'].setText("Διαχωρισμός"); controls['split'].setToolTip("Διαχωρισμός")
        controls['rotate'] = QToolButton(); controls['rotate'].setText("Περιστροφή"); controls['rotate'].setToolTip("Περιστροφή")
        controls['fix_color'] = QToolButton(); controls['fix_color'].setText("Χρώμα"); controls['fix_color'].setToolTip("Διόρθωση Χρώματος")
        controls['restore'] = QToolButton(); controls['restore'].setText("Επαναφορά"); controls['restore'].setToolTip("Επαναφορά"); controls['restore'].setObjectName("restore_button")
        controls['delete'] = QToolButton(); controls['delete'].setText("Διαγραφή"); controls['delete'].setToolTip("Διαγραφή"); controls['delete'].setObjectName("delete_button")

        normal_layout.addStretch()
        normal_layout.addWidget(controls['crop'])
        normal_layout.addWidget(controls['split'])
        normal_layout.addWidget(controls['rotate'])
        normal_layout.addWidget(controls['fix_color'])
        normal_layout.addWidget(controls['restore'])
        normal_layout.addWidget(controls['delete'])
        normal_layout.addStretch()
        controls_stack.addWidget(normal_controls_page)

        split_controls_page = QWidget()
        split_layout = QHBoxLayout(split_controls_page)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(10)

        controls['split_mode_label'] = QLabel("ΔΙΑΧΩΡΙΣΜΟΣ")
        controls['confirm_split'] = QPushButton("Επιβεβαίωση"); controls['confirm_split'].setProperty("class", "success filled")
        controls['cancel_split'] = QPushButton("Άκυρο"); controls['cancel_split'].setProperty("class", "destructive")

        split_layout.addStretch()
        split_layout.addWidget(controls['split_mode_label'])
        split_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Fixed, QSizePolicy.Minimum))
        split_layout.addWidget(controls['confirm_split'])
        split_layout.addWidget(controls['cancel_split'])
        split_layout.addStretch()
        controls_stack.addWidget(split_controls_page)

        rotate_controls_page = QWidget()
        rotate_layout = QHBoxLayout(rotate_controls_page)
        rotate_layout.setContentsMargins(0, 0, 0, 0)
        rotate_layout.setSpacing(10)

        controls['rotate_mode_label'] = QLabel("ΠΕΡΙΣΤΡΟΦΗ")
        controls['cancel_rotate'] = QPushButton("Τέλος"); controls['cancel_rotate'].setProperty("class", "destructive")

        rotate_layout.addStretch()
        rotate_layout.addWidget(controls['rotate_mode_label'])
        rotate_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Fixed, QSizePolicy.Minimum))
        rotate_layout.addWidget(controls['cancel_rotate'])
        rotate_layout.addStretch()
        controls_stack.addWidget(rotate_controls_page)

        layout.addWidget(toolbar)

        panel_widgets = {'frame': frame, 'viewer': viewer, 'toolbar': toolbar, 'controls_stack': controls_stack, **controls}

        controls['crop'].clicked.connect(lambda: self.main_window.apply_crop(panel_widgets))
        controls['fix_color'].clicked.connect(lambda: self.main_window.apply_color_fix(panel_widgets))
        controls['split'].clicked.connect(lambda: self.main_window.toggle_split_mode(panel_widgets, True))
        controls['rotate'].clicked.connect(lambda: self.main_window.toggle_rotate_mode(panel_widgets, True))
        controls['delete'].clicked.connect(lambda: self.main_window.delete_single_image(panel_widgets))
        controls['restore'].clicked.connect(lambda: self.main_window.restore_image(panel_widgets))
        controls['confirm_split'].clicked.connect(lambda: self.main_window.apply_split(panel_widgets))
        controls['cancel_split'].clicked.connect(lambda: self.main_window.toggle_split_mode(panel_widgets, False))
        controls['cancel_rotate'].clicked.connect(lambda: self.main_window.toggle_rotate_mode(panel_widgets, False))

        controls_stack.setCurrentIndex(0)
        toolbar.setEnabled(False)

        return panel_widgets
