import os
import time
import threading
import shutil
from PyQt6.QtCore import QObject, pyqtSignal

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Allowed extensions from the original app
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}
BACKUP_DIR = "scan_viewer_backups"

class NewImageHandler(FileSystemEventHandler):
    """
    A watchdog event handler that signals when a new file is created.
    """
    def __init__(self, signal_emitter):
        super().__init__()
        self.signal_emitter = signal_emitter

    def on_created(self, event):
        if not event.is_directory:
            ext = os.path.splitext(event.src_path)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                # Let the worker emit the signal in the correct thread context
                self.signal_emitter(event.src_path)

class WatchdogWorker(QObject):
    """
    Monitors a directory for new image files using watchdog and emits a signal.
    This worker runs in a separate QThread.
    """
    new_image_found = pyqtSignal(str)

    def __init__(self, scan_directory: str):
        super().__init__()
        self.scan_directory = scan_directory
        self.observer = Observer()
        self._stop_event = threading.Event()

    def run(self):
        """Starts the watchdog observer."""
        handler = NewImageHandler(self.new_image_found.emit)
        self.observer.schedule(handler, self.scan_directory, recursive=False)
        self.observer.start()

        # Keep the thread alive until stop() is called
        while not self._stop_event.is_set():
            time.sleep(0.5)

        self.observer.stop()
        self.observer.join()

    def stop(self):
        """Signals the run loop to exit."""
        self._stop_event.set()


from collections import deque
import json
from datetime import datetime

class StatsWorker(QObject):
    """
    Calculates statistics in the background and emits them.
    """
    stats_updated = pyqtSignal(dict)

    def __init__(self, scan_directory, todays_books_folder, books_log_file):
        super().__init__()
        self.scan_directory = scan_directory
        self.todays_books_folder = todays_books_folder
        self.books_log_file = books_log_file
        self._is_running = False
        self.scan_timestamps = deque()

    def run(self):
        self._is_running = True
        while self._is_running:
            self._calculate_stats()
            time.sleep(2) # Update stats every 2 seconds

    def stop(self):
        self._is_running = False

    def _count_pages_in_folder(self, folder_path):
        count = 0
        try:
            if os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
                        count += 1
        except Exception:
            pass
        return count

    def _calculate_stats(self):
        # 1. Live Performance
        now = time.time()
        performance_window = 20 # seconds
        while self.scan_timestamps and self.scan_timestamps[0] < now - performance_window:
            self.scan_timestamps.popleft()

        scans_per_minute = 0
        if self.scan_timestamps:
            time_span = now - self.scan_timestamps[0] if len(self.scan_timestamps) > 1 else performance_window
            scans_per_minute = (len(self.scan_timestamps) / max(time_span, 1)) * 60

        # 2. Stats from "Todays Books" folder
        pages_in_today_folder = 0
        books_in_today_folder = 0
        if os.path.isdir(self.todays_books_folder):
            book_folders = [d for d in os.listdir(self.todays_books_folder) if os.path.isdir(os.path.join(self.todays_books_folder, d))]
            books_in_today_folder = len(book_folders)
            for book_folder in book_folders:
                pages_in_today_folder += self._count_pages_in_folder(os.path.join(self.todays_books_folder, book_folder))

        # 3. Stats from the log file for today
        pages_in_data_today = 0
        try:
            if os.path.exists(self.books_log_file):
                with open(self.books_log_file, 'r') as f:
                    log_data = json.load(f)
                today_str = datetime.now().strftime('%Y-%m-%d')
                todays_entries = log_data.get(today_str, [])
                for entry in todays_entries:
                    if isinstance(entry, dict):
                        pages_in_data_today += entry.get("pages", 0)
        except (IOError, json.JSONDecodeError):
            pass

        stats = {
            "scans_per_minute": scans_per_minute,
            "pages_in_today": pages_in_today_folder,
            "books_in_today": books_in_today_folder,
            "pages_in_data": pages_in_data_today,
        }
        self.stats_updated.emit(stats)

class FileOperationWorker(QObject):
    """
    Placeholder for the file operation worker (create book, transfer, etc.).
    """
    operation_successful = pyqtSignal(str, str) # operation_type, message
    operation_failed = pyqtSignal(str, str) # operation_type, error_message

    def __init__(self):
        super().__init__()

    def run_operation(self, operation_type: str, data: dict):
        try:
            if operation_type == 'save_image':
                path = data['path']
                image_obj = data['image_obj']

                os.makedirs(BACKUP_DIR, exist_ok=True)
                backup_path = os.path.join(BACKUP_DIR, os.path.basename(path))
                if not os.path.exists(backup_path):
                    shutil.copy(path, backup_path)

                image_obj.save(path)
                self.operation_successful.emit(operation_type, f"Saved: {os.path.basename(path)}")

            elif operation_type == 'create_book':
                book_name = data['book_name']
                scanned_files = data['scanned_files']
                todays_books_folder = data['todays_books_folder']

                new_book_path = os.path.join(todays_books_folder, book_name)
                os.makedirs(new_book_path, exist_ok=True)

                for file_path in scanned_files:
                    if os.path.exists(file_path):
                        shutil.move(file_path, new_book_path)

                message = f"{len(scanned_files)} pages moved to '{book_name}'"
                self.operation_successful.emit(operation_type, message)

            elif operation_type == 'delete_pair':
                files_to_delete = data['files_to_delete']
                deleted_names = []
                for f_path in files_to_delete:
                    if os.path.exists(f_path):
                        deleted_names.append(os.path.basename(f_path))
                        os.remove(f_path)
                message = f"Deleted: {', '.join(deleted_names)}"
                self.operation_successful.emit(operation_type, message)


        except Exception as e:
            self.operation_failed.emit(operation_type, str(e))
