from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QPixmap, QImage

class BaseModeWidget(QWidget):
    """
    An abstract base class for UI mode handlers. It defines the interface
    that MainWindow uses to interact with the current mode.
    """
    # Signals to communicate back to the MainWindow
    editing_started = Signal()
    editing_finished = Signal()
    viewer_zoom_changed = Signal(bool)

    # Signals to communicate with services
    request_image_load = Signal(str, bool) # path, force_reload
    request_rotation = Signal(str, float)
    request_crop = Signal(str, object) # path, rect
    request_split = Signal(str, int)
    layout_changed = Signal(str, dict) # path, layout

    def __init__(self, parent=None):
        super().__init__(parent)

    def load_images(self, files):
        """
        Abstract method to update the viewer(s) with new images.
        'files' is a list of paths to display (1 or 2 depending on mode).
        """
        raise NotImplementedError

    def on_image_loaded(self, path, q_image):
        """Callback when image is loaded by service."""
        raise NotImplementedError

    def get_visible_paths(self):
        """Returns the file path(s) currently visible in the viewer(s)."""
        raise NotImplementedError

    def clear_viewers(self):
        """Clears the content of the viewer(s)."""
        raise NotImplementedError

    def is_work_in_progress(self):
        """Returns True if the user is actively doing something."""
        return False
