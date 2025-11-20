import json
import os
from datetime import datetime
from typing import Dict, List, Any
from digipage.core.config import BOOKS_LOG_FILE, ALLOWED_EXTENSIONS

class LogManager:
    """
    Handles reading and writing to the books_complete_log.json file.
    """
    
    @staticmethod
    def load_logs() -> Dict[str, List[Dict[str, Any]]]:
        if not os.path.exists(BOOKS_LOG_FILE):
            return {}
        
        try:
            with open(BOOKS_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    @staticmethod
    def save_logs(data: Dict[str, List[Dict[str, Any]]]):
        try:
            with open(BOOKS_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving logs: {e}")

    @staticmethod
    def append_entry(entry: Dict[str, Any]):
        data = LogManager.load_logs()
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        if today_str not in data:
            data[today_str] = []
            
        data[today_str].append(entry)
        LogManager.save_logs(data)

    @staticmethod
    def get_today_stats() -> tuple[int, List[Dict[str, Any]]]:
        """Returns (total_pages_processed_today, list_of_today_books)"""
        data = LogManager.load_logs()
        today_str = datetime.now().strftime('%Y-%m-%d')
        books = data.get(today_str, [])
        
        total_pages = sum(b.get('pages', 0) for b in books if isinstance(b, dict))
        return total_pages, books

def count_pages_in_folder(folder_path: str) -> int:
    """Utility to count valid image files in a directory."""
    count = 0
    try:
        if os.path.isdir(folder_path):
            with os.scandir(folder_path) as entries:
                for entry in entries:
                    if entry.is_file() and os.path.splitext(entry.name)[1].lower() in ALLOWED_EXTENSIONS:
                        count += 1
    except OSError:
        pass
    return count