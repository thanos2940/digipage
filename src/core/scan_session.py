from PySide6.QtCore import QObject, Signal, Slot
import os
import re

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

class ScanSession(QObject):
    """
    Manages the state of the current scanning session.
    Holds the list of files, the current index, and mode-specific details.
    """
    # Signals
    file_list_changed = Signal()
    current_index_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self._image_files = []
        self._current_index = 0

    @property
    def image_files(self):
        return self._image_files

    @property
    def current_index(self):
        return self._current_index

    def set_files(self, files):
        """Sets the list of files and resets index if needed."""
        self._image_files = files
        self._image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
        self.file_list_changed.emit()

        # Ensure index is valid
        if self._current_index >= len(self._image_files):
            self.set_index(max(0, len(self._image_files) - 1))
        elif len(self._image_files) == 0:
             self.set_index(0)

    def add_file(self, path):
        if path not in self._image_files:
            self._image_files.append(path)
            self._image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            self.file_list_changed.emit()

    def remove_file(self, path):
        if path in self._image_files:
            self._image_files.remove(path)
            self.file_list_changed.emit()
            # Re-validate index
            if self._current_index >= len(self._image_files):
                 self.set_index(max(0, len(self._image_files) - 1))
            else:
                 # Force update even if index number didn't change, the content did
                 self.current_index_changed.emit(self._current_index)

    def set_index(self, index):
        if 0 <= index < len(self._image_files) or (index == 0 and len(self._image_files) == 0):
            if self._current_index != index:
                self._current_index = index
                self.current_index_changed.emit(index)
        elif len(self._image_files) > 0:
             # Clamp
             new_index = max(0, min(index, len(self._image_files) - 1))
             if self._current_index != new_index:
                 self._current_index = new_index
                 self.current_index_changed.emit(new_index)

    def get_current_files(self, count=1):
        """Returns a list of files starting from current index."""
        if not self._image_files:
            return []
        return self._image_files[self._current_index : self._current_index + count]
