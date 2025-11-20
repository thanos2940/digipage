from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Slot

class BaseScanMode(QWidget):
    """
    Abstract base class for scanner modes. 
    Handles the logic of how images are displayed and navigated.
    """
    # Signals to update the main window state
    status_message = Signal(str)
    update_nav_buttons = Signal(bool, bool) # has_prev, has_next
    request_worker_action = Signal(str, object) # action_name, payload

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_files = []
        self.current_index = 0

    @Slot(list)
    def set_file_list(self, files):
        self.image_files = files
        # Clamp index
        if self.current_index >= len(self.image_files):
            self.current_index = max(0, len(self.image_files) - 1)
        self.refresh_view()

    @Slot(str)
    def handle_new_scan(self, new_path):
        """Called when a new file arrives from the watcher."""
        if new_path not in self.image_files:
            self.image_files.append(new_path)
            # Auto-navigate to end logic usually happens here
            self.go_to_end()

    def go_next(self):
        """Move selection forward."""
        pass

    def go_prev(self):
        """Move selection backward."""
        pass

    def go_to_end(self):
        """Jump to the newest scan."""
        pass

    def refresh_view(self):
        """Update the canvases."""
        pass

    def get_current_paths(self) -> list:
        """Returns list of file paths currently visible."""
        return []