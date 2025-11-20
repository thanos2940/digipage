import os
import json
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot
from core.constants import BOOKS_COMPLETE_LOG_FILE, ALLOWED_EXTENSIONS
from core.config_service import ConfigService

class StatsService(QObject):
    stats_updated = Signal(dict)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.config_service = ConfigService()

    @Slot()
    def calculate_today_stats(self):
        todays_books_folder = self.config_service.get("todays_books_folder")
        staged_book_details = {}
        try:
            if os.path.isdir(todays_books_folder):
                book_folders = [d for d in os.listdir(todays_books_folder) if os.path.isdir(os.path.join(todays_books_folder, d))]
                for book_folder in book_folders:
                    staged_book_details[book_folder] = self._count_pages_in_folder(os.path.join(todays_books_folder, book_folder))

            book_list_data = []
            pages_in_data_today = 0
            if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
                try:
                    with open(BOOKS_COMPLETE_LOG_FILE, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    book_list_data = log_data.get(today_str, [])
                    for entry in book_list_data:
                        if isinstance(entry, dict):
                            pages_in_data_today += entry.get("pages", 0)
                except (json.JSONDecodeError, IOError) as e:
                    self.error.emit(f"Failed to read log: {e}")

            stats_result = {
                "staged_book_details": staged_book_details,
                "book_list_data": book_list_data,
                "pages_in_data": pages_in_data_today,
            }
            self.stats_updated.emit(stats_result)
        except Exception as e:
            self.error.emit(f"Stats calculation failed: {e}")

    def _count_pages_in_folder(self, folder_path):
        count = 0
        try:
            if os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
                        count += 1
        except Exception as e:
            self.error.emit(f"Error counting pages in {folder_path}: {e}")
        return count
