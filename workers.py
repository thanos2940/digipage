import os
import re
import time
import json
import shutil
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import config

def natural_sort_key(s):
    """
    Key for natural sorting. E.g. 'image10.png' comes after 'image2.png'.
    From scanner2.py.
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

class ScanWorker(QObject):
    """
    Performs on-demand, potentially long-running scans and calculations.
    Designed to be moved to a QThread.
    """
    initial_scan_complete = Signal(list)
    stats_updated = Signal(dict)
    error = Signal(str)
    file_operation_complete = Signal(str, str) # operation_type, message

    def __init__(self, app_config):
        super().__init__()
        self.config = app_config

    @Slot()
    def perform_initial_scan(self):
        """Scans the scan_directory for image files and emits the sorted list."""
        scan_directory = self.config.get("scan_folder")
        if not scan_directory or not os.path.isdir(scan_directory):
            self.error.emit(f"Scan folder is not valid: {scan_directory}")
            self.initial_scan_complete.emit([])
            return

        try:
            files = [os.path.join(scan_directory, f) for f in os.listdir(scan_directory)
                     if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS]
            files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            self.initial_scan_complete.emit(files)
        except Exception as e:
            self.error.emit(f"Error during initial scan: {e}")
            self.initial_scan_complete.emit([])

    @Slot()
    def calculate_today_stats(self):
        """Calculates statistics for today's progress and emits them."""
        todays_books_folder = self.config.get("todays_books_folder")
        pages_in_today_folder = 0
        books_in_today_folder = 0

        try:
            if os.path.isdir(todays_books_folder):
                book_folders = [d for d in os.listdir(todays_books_folder) if os.path.isdir(os.path.join(todays_books_folder, d))]
                books_in_today_folder = len(book_folders)
                for book_folder in book_folders:
                    pages_in_today_folder += self._count_pages_in_folder(os.path.join(todays_books_folder, book_folder))

            pages_in_data_today = 0
            if os.path.exists(config.BOOKS_COMPLETE_LOG_FILE):
                with open(config.BOOKS_COMPLETE_LOG_FILE, 'r') as f:
                    log_data = json.load(f)
                today_str = datetime.now().strftime('%Y-%m-%d')
                todays_entries = log_data.get(today_str, [])
                for entry in todays_entries:
                    if isinstance(entry, dict):
                        pages_in_data_today += entry.get("pages", 0)

            stats_result = {
                "pages_in_today": pages_in_today_folder,
                "books_in_today": books_in_today_folder,
                "pages_in_data": pages_in_data_today,
            }
            self.stats_updated.emit(stats_result)

        except Exception as e:
            self.error.emit(f"Error calculating stats: {e}")

    def _count_pages_in_folder(self, folder_path):
        """Helper to count image files in a directory."""
        count = 0
        try:
            if os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS:
                        count += 1
        except Exception as e:
            self.error.emit(f"Error counting pages in {folder_path}: {e}")
        return count

    @Slot(str)
    def delete_file(self, path):
        """Deletes a single file from the file system."""
        try:
            if os.path.exists(path):
                filename = os.path.basename(path)
                os.remove(path)
                # Emit with operation type 'delete' and the path of the deleted file
                self.file_operation_complete.emit("delete", path)
            else:
                self.error.emit(f"File not found for deletion: {path}")
        except Exception as e:
            self.error.emit(f"Error deleting file {path}: {e}")

    @Slot(str, list)
    def create_book(self, book_name, files_to_move):
        """Creates a new book folder and moves files into it."""
        try:
            todays_folder = self.config.get("todays_books_folder")
            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Today's Books Folder is not valid: {todays_folder}")
                return

            new_book_path = os.path.join(todays_folder, book_name)
            os.makedirs(new_book_path, exist_ok=True)

            for file_path in files_to_move:
                if os.path.exists(file_path):
                    shutil.move(file_path, new_book_path)

            self.file_operation_complete.emit("create_book", book_name)

        except Exception as e:
            self.error.emit(f"Failed to create book {book_name}: {e}")

    @Slot()
    def transfer_all_to_data(self):
        """Moves books from the staging folder to their final city data folders."""
        try:
            todays_folder = self.config.get("todays_books_folder")
            city_paths = self.config.get("city_paths", {})
            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Today's Books Folder is not valid: {todays_folder}")
                return

            book_folders = [d for d in os.listdir(todays_folder) if os.path.isdir(os.path.join(todays_folder, d))]
            if not book_folders:
                self.file_operation_complete.emit("transfer_all", "No books to transfer.")
                return

            code_pattern = re.compile(r'-(\d{3})-')
            log_data = {}
            if os.path.exists(config.BOOKS_COMPLETE_LOG_FILE):
                with open(config.BOOKS_COMPLETE_LOG_FILE, 'r') as f:
                    log_data = json.load(f)
            today_str = datetime.now().strftime('%Y-%m-%d')
            if today_str not in log_data:
                log_data[today_str] = []

            moved_count = 0
            for book_name in book_folders:
                match = code_pattern.search(book_name)
                if not match:
                    continue

                city_code = match.group(1)
                city_path = city_paths.get(city_code)
                if not city_path or not os.path.isdir(city_path):
                    continue

                date_folder_name = datetime.now().strftime('%d-%m')
                destination_folder = os.path.join(city_path, date_folder_name)
                os.makedirs(destination_folder, exist_ok=True)

                source_path = os.path.join(todays_folder, book_name)
                final_book_path = os.path.join(destination_folder, book_name)

                page_count = self._count_pages_in_folder(source_path)
                shutil.move(source_path, final_book_path)

                log_entry = {
                    "name": book_name, "pages": page_count,
                    "path": final_book_path, "timestamp": datetime.now().isoformat()
                }
                log_data[today_str].append(log_entry)
                moved_count += 1

            with open(config.BOOKS_COMPLETE_LOG_FILE, 'w') as f:
                json.dump(log_data, f, indent=4)

            self.file_operation_complete.emit("transfer_all", f"Successfully transferred {moved_count} books.")

        except Exception as e:
            self.error.emit(f"Failed to transfer books: {e}")


class NewImageHandler(FileSystemEventHandler, QObject):
    """
    Handles file system events from watchdog and emits Qt signals.
    Inherits from QObject to support signals.
    """
    new_image_detected = Signal(str)

    def __init__(self):
        # The super() call will initialize both FileSystemEventHandler and QObject
        super().__init__()

    def on_created(self, event):
        """Called when a file or directory is created."""
        if not event.is_directory:
            file_ext = os.path.splitext(event.src_path)[1].lower()
            if file_ext in config.ALLOWED_EXTENSIONS:
                self.new_image_detected.emit(event.src_path)


class Watcher(QObject):
    """
    Manages the watchdog observer in a separate thread.
    """
    error = Signal(str)
    finished = Signal()

    def __init__(self, scan_directory):
        super().__init__()
        self.scan_directory = scan_directory
        self.observer = Observer()
        self._running = True

    def run(self):
        """The main worker loop."""
        if not self.scan_directory or not os.path.isdir(self.scan_directory):
            self.error.emit(f"Watchdog error: Invalid directory specified: {self.scan_directory}")
            self.finished.emit()
            return

        event_handler = NewImageHandler()
        # We need to connect the handler's signal to another signal in this class
        # so that the main thread can connect to the Watcher instance.
        event_handler.new_image_detected.connect(self.new_image_detected_passthrough)

        self.observer.schedule(event_handler, self.scan_directory, recursive=False)
        self.observer.start()

        try:
            while self._running:
                time.sleep(1)
        finally:
            self.observer.stop()
            self.observer.join()

        self.finished.emit()

    def stop(self):
        self._running = False

    # This is a signal that will be emitted from the watcher thread
    new_image_detected_passthrough = Signal(str)


class ImageProcessor(QObject):
    """
    Handles CPU-intensive image processing tasks in a separate thread.
    """
    processing_complete = Signal(str) # path
    error = Signal(str)

    @Slot(str, tuple)
    def crop_image(self, path, crop_coords):
        """Crops an image and saves it, overwriting the original."""
        try:
            # 1. Create backup
            if not os.path.exists(config.BACKUP_DIR):
                os.makedirs(config.BACKUP_DIR)

            backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
            if not os.path.exists(backup_path):
                shutil.copy(path, backup_path)

            # 2. Open, crop, and save
            from PIL import Image

            x, y, w, h = crop_coords
            with Image.open(path) as img:
                cropped_img = img.crop((x, y, x + w, y + h))
                # Overwrite the original file
                cropped_img.save(path)

            self.processing_complete.emit(path)

        except Exception as e:
            self.error.emit(f"Failed to crop image {os.path.basename(path)}: {e}")

    @Slot(str)
    def restore_image(self, path):
        """Restores an image from its backup."""
        try:
            backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
            if not os.path.exists(backup_path):
                self.error.emit(f"No backup found for {os.path.basename(path)}")
                return

            # Copy the backup back to the original path
            shutil.copy(backup_path, path)
            self.processing_complete.emit(path)

        except Exception as e:
            self.error.emit(f"Failed to restore image {os.path.basename(path)}: {e}")
