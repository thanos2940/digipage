import os
import shutil
import time
import json
import re
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot
from core.constants import BACKUP_DIR, BOOKS_COMPLETE_LOG_FILE, ALLOWED_EXTENSIONS
from core.config_service import ConfigService

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

class FileService(QObject):
    """
    Handles file operations: delete, restore, book creation, transfer, replace.
    """
    operation_complete = Signal(str, str)
    error = Signal(str)
    book_creation_progress = Signal(int, int)
    transfer_preparation_complete = Signal(list, list)

    def __init__(self):
        super().__init__()
        self.config_service = ConfigService()
        self._is_cancelled = False

    def cancel_operation(self):
        self._is_cancelled = True

    @Slot(str)
    def delete_file(self, path):
        for i in range(5):
            try:
                if os.path.exists(path):
                    os.remove(path)
                self.operation_complete.emit("delete", path)
                return
            except (PermissionError, OSError) as e:
                if i < 4: time.sleep(0.1)
                else: self.error.emit(f"Delete failed for {os.path.basename(path)}: {e}")

    @Slot(str)
    def restore_image(self, path):
        try:
            backup_path = os.path.join(BACKUP_DIR, os.path.basename(path))
            if not os.path.exists(backup_path):
                self.error.emit(f"No backup found for {os.path.basename(path)}")
                return
            shutil.copy(backup_path, path)
            self.operation_complete.emit("restore", path)
        except Exception as e:
            self.error.emit(f"Restore failed: {e}")

    @Slot(str, str, str, str)
    def replace_pair(self, old_path1, old_path2, new_path1, new_path2):
        try:
            if os.path.exists(old_path1): os.remove(old_path1)
            if os.path.exists(old_path2): os.remove(old_path2)
            os.rename(new_path1, old_path1)
            os.rename(new_path2, old_path2)
            self.operation_complete.emit("replace_pair", "Pair replaced successfully.")
        except Exception as e:
            self.error.emit(f"Replace pair failed: {e}")

    @Slot(str, str)
    def replace_single_image_file(self, old_path, new_path):
         # This only does the file swap. Re-splitting is handled by ImageService or Controller
        try:
            if os.path.exists(old_path): os.remove(old_path)

            rename_attempts = 5
            for i in range(rename_attempts):
                try:
                    os.rename(new_path, old_path)
                    break
                except OSError as e:
                    if i < rename_attempts - 1:
                        time.sleep(0.2)
                        continue
                    else:
                        raise e
            self.operation_complete.emit("replace_single_file", old_path)
        except Exception as e:
             self.error.emit(f"Replace single file failed: {e}")

    @Slot(str)
    def delete_split_image_and_artifacts(self, source_path):
        try:
            if os.path.exists(source_path): os.remove(source_path)

            scan_folder = os.path.dirname(source_path)
            base, ext = os.path.splitext(os.path.basename(source_path))
            final_folder = os.path.join(scan_folder, 'final')

            for suffix in ["_L", "_R"]:
                artifact = os.path.join(final_folder, f"{base}{suffix}{ext}")
                if os.path.exists(artifact): os.remove(artifact)

            backup = os.path.join(BACKUP_DIR, os.path.basename(source_path))
            if os.path.exists(backup): os.remove(backup)

            self.operation_complete.emit("delete", source_path)
        except Exception as e:
            self.error.emit(f"Delete artifacts failed: {e}")

    @Slot(str, list, str)
    def create_book(self, book_name, files_to_move, source_folder):
        self._is_cancelled = False
        scan_folder = self.config_service.get("scan_folder")
        is_single_split_mode = "final" in source_folder

        try:
            todays_folder = self.config_service.get("todays_books_folder")
            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Invalid Today's Books folder: {todays_folder}")
                return

            new_book_path = os.path.join(todays_folder, book_name)
            os.makedirs(new_book_path, exist_ok=True)

            total_files = len(files_to_move)
            files_to_move.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

            for i, file_path in enumerate(files_to_move):
                if self._is_cancelled:
                    shutil.rmtree(new_book_path)
                    self.operation_complete.emit("create_book", f"Book creation '{book_name}' cancelled.")
                    return

                if os.path.exists(file_path):
                    _, extension = os.path.splitext(file_path)
                    new_base_name = f"{i + 1:04d}{extension}"
                    dest_path = os.path.join(new_book_path, new_base_name)
                    shutil.move(file_path, dest_path)

                self.book_creation_progress.emit(i + 1, total_files)

            # Cleanup for single split mode
            if is_single_split_mode:
                original_files = [f for f in os.listdir(scan_folder) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
                for f in original_files:
                    try:
                        os.remove(os.path.join(scan_folder, f))
                    except OSError: pass

                final_folder_path = os.path.join(scan_folder, 'final')
                if os.path.isdir(final_folder_path):
                    shutil.rmtree(final_folder_path, ignore_errors=True)

                layout_data_path = os.path.join(scan_folder, 'layout_data.json')
                if os.path.exists(layout_data_path):
                    try: os.remove(layout_data_path)
                    except OSError: pass

            self.operation_complete.emit("create_book", f"Book '{book_name}' created.")

        except Exception as e:
            self.error.emit(f"Failed to create book {book_name}: {e}")

    @Slot()
    def prepare_transfer(self):
        try:
            todays_folder = self.config_service.get("todays_books_folder")
            city_paths = self.config_service.get("city_paths", {})

            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Invalid Today's Books folder.")
                return

            book_folders = [d for d in os.listdir(todays_folder) if os.path.isdir(os.path.join(todays_folder, d))]

            moves_to_confirm = []
            warnings = []
            code_pattern = re.compile(r'-(\d{3})-')

            for book_name in book_folders:
                match = code_pattern.search(book_name)
                if not match:
                    warnings.append(f"- No city code found: {book_name}")
                    continue

                city_code = match.group(1)
                city_path = city_paths.get(city_code)
                if not city_path or not os.path.isdir(city_path):
                    warnings.append(f"- Invalid city path for '{city_code}' (Book: {book_name})")
                    continue

                source_path = os.path.join(todays_folder, book_name)
                date_folder_name = datetime.now().strftime('%d-%m')
                destination_folder = os.path.join(city_path, date_folder_name)
                final_book_path = os.path.join(destination_folder, book_name)

                moves_to_confirm.append({
                    'book_name': book_name,
                    'source_path': source_path,
                    'destination_folder': destination_folder,
                    'final_book_path': final_book_path
                })

            self.transfer_preparation_complete.emit(moves_to_confirm, warnings)

        except Exception as e:
            self.error.emit(f"Transfer prep failed: {e}")

    @Slot(list)
    def transfer_all_to_data(self, moves_to_perform):
        self._is_cancelled = False
        try:
            if not moves_to_perform:
                self.operation_complete.emit("transfer_all", "No books to transfer.")
                return

            log_data = {}
            if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
                with open(BOOKS_COMPLETE_LOG_FILE, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            today_str = datetime.now().strftime('%Y-%m-%d')
            if today_str not in log_data:
                log_data[today_str] = []

            moved_count = 0
            for move in moves_to_perform:
                if self._is_cancelled: break

                book_name = move['book_name']
                source_path = move['source_path']
                destination_folder = move['destination_folder']
                final_book_path = move['final_book_path']

                os.makedirs(destination_folder, exist_ok=True)

                # Count pages
                page_count = 0
                if os.path.isdir(source_path):
                    page_count = len([f for f in os.listdir(source_path) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS])

                shutil.move(source_path, final_book_path)

                if self._is_cancelled: break

                log_entry = {
                    "name": book_name, "pages": page_count,
                    "path": final_book_path, "timestamp": datetime.now().isoformat()
                }
                log_data[today_str].append(log_entry)
                moved_count += 1

            with open(BOOKS_COMPLETE_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=4)

            message = f"Successfully transferred {moved_count} books."
            if self._is_cancelled: message = f"Transfer cancelled. {moved_count} books moved."
            self.operation_complete.emit("transfer_all", message)

        except Exception as e:
            self.error.emit(f"Transfer failed: {e}")
