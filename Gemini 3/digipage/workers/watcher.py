import os
import time
from PySide6.QtCore import QObject, Signal, Slot, QThread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from digipage.core.config import ALLOWED_EXTENSIONS

class NewImageHandler(FileSystemEventHandler):
    """Handles file system events for the watchdog."""
    def __init__(self, new_image_callback, change_callback):
        super().__init__()
        self.new_image_callback = new_image_callback
        self.change_callback = change_callback

    def _wait_for_file_stability(self, file_path, timeout=3.0):
        """Waits until file size stops changing (upload/write complete)."""
        last_size = -1
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                if not os.path.exists(file_path): return False
                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
                time.sleep(0.1)
            except OSError:
                time.sleep(0.1)
        return False

    def on_created(self, event):
        if event.is_directory: return
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            if self._wait_for_file_stability(event.src_path):
                self.new_image_callback(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.change_callback()

    def on_moved(self, event):
        if not event.is_directory:
            self.change_callback()

class WatcherWorker(QObject):
    """Qt-friendly wrapper for the Watchdog library."""
    new_image_detected = Signal(str)
    folder_changed = Signal()
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, scan_directory: str):
        super().__init__()
        self.scan_directory = scan_directory
        self.observer = Observer()
        self.handler = NewImageHandler(
            new_image_callback=self.emit_new_image,
            change_callback=self.emit_folder_changed
        )
        
    def emit_new_image(self, path):
        self.new_image_detected.emit(path)
        
    def emit_folder_changed(self):
        self.folder_changed.emit()

    @Slot()
    def start_watching(self):
        if not self.scan_directory or not os.path.isdir(self.scan_directory):
            self.error_occurred.emit(f"Invalid scan directory: {self.scan_directory}")
            self.finished.emit()
            return

        try:
            self.observer.schedule(self.handler, self.scan_directory, recursive=False)
            self.observer.start()
        except Exception as e:
            self.error_occurred.emit(f"Watcher failed to start: {e}")
            self.finished.emit()

    @Slot()
    def stop(self):
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        self.finished.emit()