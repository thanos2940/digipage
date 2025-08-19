import os
import time
import shutil
import json
import re
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import asyncio
from PIL import Image, ImageOps, ImageEnhance

# --- App Configuration ---
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}
BACKUP_DIR = "scan_viewer_backups"
CONFIG_FILE = "scan_viewer_config.json"
BOOKS_COMPLETE_LOG_FILE = "books_complete_log.json"

# --- Global State ---
# This will be managed by the server startup and shutdown events
observer = None
image_files = []
scan_directory = ""
todays_books_folder = ""
city_paths = {}
file_change_callback = None

def natural_sort_key(s):
    """Sorts strings with numbers in a natural way."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def load_settings():
    """Loads settings from the config file."""
    global scan_directory, todays_books_folder, city_paths
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        scan_directory = settings.get("scan", "")
        todays_books_folder = settings.get("today", "")
        city_paths = settings.get("city_paths", {})
        return settings
    return {}

def save_settings(settings):
    """Saves settings to the config file."""
    global scan_directory, todays_books_folder, city_paths
    scan_directory = settings.get("scan", "")
    todays_books_folder = settings.get("today", "")
    city_paths = settings.get("city_paths", {})
    with open(CONFIG_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

def get_image_files():
    """Returns the current list of image files."""
    global image_files
    try:
        files = [os.path.join(scan_directory, f) for f in os.listdir(scan_directory) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
        files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
        image_files = files
        return image_files
    except Exception as e:
        print(f"Error reading scan directory: {e}")
        return []

class NewImageHandler(FileSystemEventHandler):
    """Handles file system events from watchdog."""
    def __init__(self, loop, callback):
        self.loop = loop
        self.callback = callback

    def on_created(self, event):
        if not event.is_directory and os.path.splitext(event.src_path)[1].lower() in ALLOWED_EXTENSIONS:
            print(f"New image detected: {event.src_path}")
            # Schedule the callback in the asyncio event loop
            asyncio.run_coroutine_threadsafe(self.callback(os.path.basename(event.src_path)), self.loop)
            get_image_files() # Refresh the list

    def on_deleted(self, event):
         if not event.is_directory:
            print(f"Image deleted: {event.src_path}")
            get_image_files() # Refresh the list
            asyncio.run_coroutine_threadsafe(self.callback(None), self.loop)


def start_watcher(loop, callback):
    """Starts the watchdog file system observer."""
    global observer, file_change_callback
    file_change_callback = callback
    load_settings()
    if not scan_directory or not os.path.isdir(scan_directory):
        print(f"Scan directory not configured or does not exist: {scan_directory}")
        return

    if observer and observer.is_alive():
        observer.stop()
        observer.join()

    event_handler = NewImageHandler(loop, callback)
    observer = Observer()
    observer.schedule(event_handler, scan_directory, recursive=False)
    observer.start()
    print(f"Started watching directory: {scan_directory}")

def stop_watcher():
    """Stops the watchdog file system observer."""
    global observer
    if observer and observer.is_alive():
        observer.stop()
        observer.join()
        print("Stopped watching directory.")

# --- Image Editing Logic (adapted from ZoomPanCanvas) ---

def apply_edits(image_path, edits):
    """
    Applies a set of edits to an image and saves it.
    Edits is a dictionary with keys like 'rotation', 'crop', 'brightness', 'contrast'.
    """
    try:
        img = Image.open(image_path)

        # Create backup on first edit
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(image_path))
        if not os.path.exists(backup_path):
            shutil.copy(image_path, backup_path)

        if 'rotation' in edits:
            img = img.rotate(edits['rotation'], resample=Image.Resampling.BICUBIC, expand=True)

        if 'brightness' in edits or 'contrast' in edits:
            brightness = edits.get('brightness', 1.0)
            contrast = edits.get('contrast', 1.0)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(brightness)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(contrast)

        if 'crop' in edits:
            # Crop coordinates are expected as (left, top, right, bottom)
            img = img.crop(edits['crop'])

        img.save(image_path)
        return {"status": "success", "message": f"Image {os.path.basename(image_path)} edited successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Book and Transfer Logic (adapted from ImageScannerApp) ---

def _count_pages_in_folder(folder_path):
    count = 0
    try:
        if os.path.isdir(folder_path):
            for f in os.listdir(folder_path):
                if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
                    count += 1
    except Exception as e:
        print(f"Error counting pages in {folder_path}: {e}")
    return count

def create_new_book(book_name):
    """Creates a new book folder and moves all current scans into it."""
    if not book_name:
        return {"status": "error", "message": "Book name cannot be empty."}

    scanned_files = get_image_files()
    if not scanned_files:
        return {"status": "info", "message": "Scan folder is empty."}

    new_book_path = os.path.join(todays_books_folder, book_name)
    os.makedirs(new_book_path, exist_ok=True)

    for file_path in scanned_files:
        try:
            shutil.move(file_path, new_book_path)
        except Exception as e:
            return {"status": "error", "message": f"Failed to move {os.path.basename(file_path)}: {e}"}

    return {"status": "success", "message": f"{len(scanned_files)} scans moved to '{book_name}'."}

def transfer_to_data():
    """Transfers books from 'today's folder' to the final city data folders."""
    try:
        books_in_today_folder = [d for d in os.listdir(todays_books_folder) if os.path.isdir(os.path.join(todays_books_folder, d))]
    except FileNotFoundError:
        return {"status": "error", "message": f"Folder '{todays_books_folder}' not found."}

    if not books_in_today_folder:
        return {"status": "info", "message": "No books to transfer."}

    moved_count = 0
    failed_moves = []
    code_pattern = re.compile(r'-(\d{3})-')

    # Load log file
    try:
        log_data = {}
        if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
            with open(BOOKS_COMPLETE_LOG_FILE, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
    except (IOError, json.JSONDecodeError):
        log_data = {}

    today_str = datetime.now().strftime('%Y-%m-%d')
    if today_str not in log_data:
        log_data[today_str] = []

    for book_name in books_in_today_folder:
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

        source_path = os.path.join(todays_books_folder, book_name)
        final_book_path = os.path.join(destination_folder, book_name)

        try:
            page_count = _count_pages_in_folder(source_path)
            shutil.move(source_path, final_book_path)

            log_entry = {
                "name": book_name,
                "pages": page_count,
                "path": final_book_path,
                "timestamp": datetime.now().isoformat()
            }
            log_data[today_str].append(log_entry)
            moved_count += 1
        except Exception as e:
            failed_moves.append(book_name)
            print(f"ERROR moving book {book_name}: {e}")

    # Save log file
    try:
        with open(BOOKS_COMPLETE_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=4)
    except IOError as e:
        print(f"Could not write to log file: {e}")

    if not failed_moves:
        return {"status": "success", "message": f"Successfully transferred {moved_count} books."}
    else:
        return {"status": "warning", "message": f"Transferred {moved_count} books. Failed to transfer: {', '.join(failed_moves)}"}

def get_stats():
    """Calculates and returns performance statistics."""
    # This is a simplified version. The original had more complex live tracking.
    # We can add more sophisticated tracking later if needed.

    pages_in_scan_folder = len(get_image_files())

    pages_in_today_folder = 0
    books_in_today_folder = 0
    if os.path.isdir(todays_books_folder):
        book_folders = [d for d in os.listdir(todays_books_folder) if os.path.isdir(os.path.join(todays_books_folder, d))]
        books_in_today_folder = len(book_folders)
        for book_folder in book_folders:
            pages_in_today_folder += _count_pages_in_folder(os.path.join(todays_books_folder, book_folder))

    pages_in_data_today = 0
    try:
        if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
            with open(BOOKS_COMPLETE_LOG_FILE, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
            today_str = datetime.now().strftime('%Y-%m-%d')
            todays_entries = log_data.get(today_str, [])
            for entry in todays_entries:
                if isinstance(entry, dict):
                    pages_in_data_today += entry.get("pages", 0)
    except (IOError, json.JSONDecodeError):
        pass

    total_pages_today = pages_in_scan_folder + pages_in_today_folder + pages_in_data_today

    return {
        "pages_in_scan_folder": pages_in_scan_folder,
        "books_in_today_folder": books_in_today_folder,
        "pages_in_today_folder": pages_in_today_folder,
        "pages_in_data_today": pages_in_data_today,
        "total_pages_today": total_pages_today,
    }
