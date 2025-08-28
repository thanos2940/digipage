import os
import queue
import threading
import json
import re
from datetime import datetime

from config import ALLOWED_EXTENSIONS, BOOKS_COMPLETE_LOG_FILE

# Helper for natural sorting
def natural_sort_key(s):
    # Splits a string into a list of strings and numbers for natural sorting.
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

class ScanWorker(threading.Thread):
    # Initializes the scan worker thread
    def __init__(self, command_queue, result_queue, scan_directory, todays_books_folder, city_paths):
        super().__init__(daemon=True)
        self.command_queue = command_queue
        self.result_queue = result_queue
        self.scan_directory = scan_directory
        self.todays_books_folder = todays_books_folder
        self.city_paths = city_paths
        self._stop_event = threading.Event()

    # Runs the main loop for the worker thread
    def run(self):
        while not self._stop_event.is_set():
            try:
                command, data = self.command_queue.get(timeout=0.1)
                if command == 'stop':
                    break
                elif command == 'initial_scan':
                    self._initial_scan_worker(data)
                elif command == 'calculate_today_stats':
                    self._calculate_today_stats_worker()
                self.command_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"ERROR: ScanWorker error: {e}")
                self.result_queue.put(('error', str(e)))

    # Stops the worker thread
    def stop(self):
        self._stop_event.set()

    # Helper to count image files in a directory
    def _count_pages_in_folder(self, folder_path):
        count = 0
        try:
            if os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
                        count += 1
        except Exception as e:
            print(f"Error counting pages in {folder_path}: {e}")
        return count

    # Worker function to perform initial scan
    def _initial_scan_worker(self, scan_directory):
        try:
            files = [os.path.join(scan_directory, f) for f in os.listdir(scan_directory) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
            # Sort files using the natural_sort_key
            files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            self.result_queue.put(('initial_scan_result', files))
        except Exception as e:
            self.result_queue.put(('error', f"Σφάλμα ανάγνωσης φακέλου σάρωσης: {e}"))

    # Worker function to calculate all stats for today
    def _calculate_today_stats_worker(self):
        try:
            # 1. Stats from "Todays Books" folder
            pages_in_today_folder = 0
            books_in_today_folder = 0
            if os.path.isdir(self.todays_books_folder):
                book_folders = [d for d in os.listdir(self.todays_books_folder) if os.path.isdir(os.path.join(self.todays_books_folder, d))]
                books_in_today_folder = len(book_folders)
                for book_folder in book_folders:
                    pages_in_today_folder += self._count_pages_in_folder(os.path.join(self.todays_books_folder, book_folder))

            # 2. Stats from the log file for today
            pages_in_data_today = 0
            try:
                if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
                    with open(BOOKS_COMPLETE_LOG_FILE, 'r') as f:
                        log_data = json.load(f)
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    todays_entries = log_data.get(today_str, [])
                    for entry in todays_entries:
                        # FIX: Check if entry is a dictionary to support old log formats
                        if isinstance(entry, dict):
                            pages_in_data_today += entry.get("pages", 0)
            except (IOError, json.JSONDecodeError) as e:
                print(f"Could not read or parse log file: {e}")

            stats_result = {
                "pages_in_today": pages_in_today_folder,
                "books_in_today": books_in_today_folder,
                "pages_in_data": pages_in_data_today,
            }
            self.result_queue.put(('today_stats_result', stats_result))

        except Exception as e:
            print(f"Σφάλμα υπολογισμού στατιστικών: {e}")
            self.result_queue.put(('error', f"Σφάλμα υπολογισμού στατιστικών: {e}"))
