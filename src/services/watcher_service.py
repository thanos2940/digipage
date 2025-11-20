import os
import time
from PySide6.QtCore import QObject, Signal, Slot, QThread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from core.constants import ALLOWED_EXTENSIONS

class NewImageHandler(FileSystemEventHandler):
    def __init__(self, callback, general_change_callback):
        super().__init__()
        self.callback = callback
        self.general_change_callback = general_change_callback

    def _wait_for_file_to_stabilize(self, file_path):
        last_size = -1
        try:
            for _ in range(30):
                if not os.path.exists(file_path):
                    return False
                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
                time.sleep(0.1)
        except (IOError, OSError):
            return False
        return False

    def on_created(self, event):
        if not event.is_directory:
            file_ext = os.path.splitext(event.src_path)[1].lower()
            if file_ext in ALLOWED_EXTENSIONS:
                if self._wait_for_file_to_stabilize(event.src_path):
                    self.callback(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            file_ext = os.path.splitext(event.src_path)[1].lower()
            if file_ext in ALLOWED_EXTENSIONS:
                self.general_change_callback()

    def on_moved(self, event):
        if not event.is_directory:
             self.general_change_callback()

class WatcherService(QObject):
    error = Signal(str)
    new_image_detected = Signal(str)
    scan_folder_changed = Signal()

    def __init__(self, scan_directory):
        super().__init__()
        self.scan_directory = scan_directory
        self.observer = Observer()
        self.event_handler = NewImageHandler(
            callback=self.handle_new_image,
            general_change_callback=self.handle_general_change
        )

    @Slot(str)
    def handle_new_image(self, path):
        self.new_image_detected.emit(path)

    @Slot()
    def handle_general_change(self):
        self.scan_folder_changed.emit()

    def start(self):
        if not self.scan_directory or not os.path.isdir(self.scan_directory):
            # Don't emit error immediately on init, maybe just log
            # self.error.emit(f"Watcher Error: Invalid folder: {self.scan_directory}")
            return

        self.observer.schedule(self.event_handler, self.scan_directory, recursive=False)
        self.observer.start()

    def stop(self):
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
