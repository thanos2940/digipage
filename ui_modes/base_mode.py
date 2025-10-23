# In ui_modes/base_mode.py

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Slot

class BaseModeHandler(QWidget):
    """
    An abstract base class for UI mode handlers. It defines the interface
    that MainWindow uses to interact with the current mode.
    """
    # Signals to communicate back to the MainWindow
    editing_started = Signal()
    viewer_zoom_changed = Signal(bool)
    request_image_load = Signal(str, bool)
    rotation_finished = Signal(str, float)

    def __init__(self, app_config, parent=None):
        super().__init__(parent)
        self.app_config = app_config

    @Slot(list, int, bool)
    def update_display(self, image_files, current_index, force_reload=False):
        """Abstract method to update the viewer(s) with new images."""
        raise NotImplementedError

    def connect_image_processor(self, image_processor):
        """Connects the mode's viewers to the central image processor."""
        raise NotImplementedError

    def get_visible_paths(self):
        """Returns the file path(s) currently visible in the viewer(s)."""
        raise NotImplementedError

    def clear_viewers(self):
        """Clears the content of the viewer(s)."""
        raise NotImplementedError