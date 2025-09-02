import os
import time
from PySide6.QtCore import QObject, Signal, Slot
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Define common image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif'}

# --- Worker for on-demand tasks ---

class ScanWorker(QObject):
    """
    A QObject worker for performing scans and calculations in a background thread.
    """
    initial_scan_complete = Signal(list)
    stats_updated = Signal(dict)
    error = Signal(str)

    @Slot(str)
    def perform_initial_scan(self, scan_folder: str):
        """
        Scans the target folder for existing image files and emits the result.
        """
        print(f"Worker: Starting initial scan of {scan_folder}")
        try:
            if not os.path.isdir(scan_folder):
                raise FileNotFoundError(f"Scan folder not found: {scan_folder}")

            image_files = []
            for item in os.listdir(scan_folder):
                path = os.path.join(scan_folder, item)
                if os.path.isfile(path) and os.path.splitext(item)[1].lower() in IMAGE_EXTENSIONS:
                    image_files.append(path)

            # Sort files, assuming filenames are sortable (e.g., timestamps)
            image_files.sort()

            print(f"Worker: Initial scan found {len(image_files)} images.")
            self.initial_scan_complete.emit(image_files)
        except Exception as e:
            self.error.emit(f"Error during initial scan: {e}")

    @Slot(str)
    def calculate_today_stats(self, today_books_folder: str):
        """
        Calculates statistics about the work done today.
        For now, this is a placeholder. In a real app, this would be more complex.
        """
        print(f"Worker: Calculating stats for {today_books_folder}")
        try:
            if not os.path.isdir(today_books_folder):
                raise FileNotFoundError(f"Today's books folder not found: {today_books_folder}")

            staged_books = [d for d in os.listdir(today_books_folder) if os.path.isdir(os.path.join(today_books_folder, d))]
            total_pages = 0
            for book_dir in staged_books:
                book_path = os.path.join(today_books_folder, book_dir)
                try:
                    num_files = len([f for f in os.listdir(book_path) if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS])
                    total_pages += num_files
                except OSError:
                    continue # Ignore files that are not directories, etc.

            stats = {
                "pages_per_minute": 0, # This would require tracking over time
                "pending_scans": 0, # This would be len(images_in_scan_folder)
                "staged_books": len(staged_books),
                "total_pages_today": total_pages,
            }
            self.stats_updated.emit(stats)
        except Exception as e:
            self.error.emit(f"Error calculating stats: {e}")


# --- Worker for watching the file system ---

class _NewImageHandler(FileSystemEventHandler, QObject):
    """
    A handler for watchdog that emits a Qt signal when a new image is created.
    Inherits from QObject to handle signals properly across threads.
    """
    # Define the signal as a class attribute
    new_image_detected = Signal(str)

    def __init__(self):
        # Explicitly call constructors of both parent classes
        FileSystemEventHandler.__init__(self)
        QObject.__init__(self)

    def on_created(self, event):
        """
        Called when a file or directory is created.
        """
        if not event.is_directory:
            file_path = event.src_path
            if os.path.splitext(file_path)[1].lower() in IMAGE_EXTENSIONS:
                print(f"Handler: Detected new image: {file_path}")
                # Give the system a moment to finish writing the file before we use it
                time.sleep(0.1)
                self.new_image_detected.emit(file_path)

class DirectoryWatcher(QObject):
    """
    A QObject that wraps the watchdog observer to monitor a directory.
    This entire object should be moved to a dedicated QThread.
    """
    new_image_detected = Signal(str)
    error = Signal(str)

    def __init__(self, path_to_watch: str):
        super().__init__()
        self.path_to_watch = path_to_watch
        self.observer = Observer()
        self.handler = _NewImageHandler()

        # Connect the handler's signal to this worker's signal
        self.handler.new_image_detected.connect(self.new_image_detected)

    @Slot()
    def start_watching(self):
        """
        Starts the watchdog observer.
        """
        print(f"Watcher: Starting to watch {self.path_to_watch}")
        if not os.path.isdir(self.path_to_watch):
            msg = f"Cannot watch invalid directory: {self.path_to_watch}"
            print(msg)
            self.error.emit(msg)
            return

        self.observer.schedule(self.handler, self.path_to_watch, recursive=False)
        self.observer.start()
        print("Watcher: Observer started.")

    @Slot()
    def stop_watching(self):
        """
        Stops the watchdog observer.
        """
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join() # Wait for the thread to finish
            print("Watcher: Observer stopped.")
