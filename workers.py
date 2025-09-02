import os
import re
import time
import json
import shutil
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot, QSize, Qt, QThread, QRect
from PySide6.QtGui import QPixmap, QTransform, QImage
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image, ImageOps, ImageFilter

import config

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

class ScanWorker(QObject):
    initial_scan_complete = Signal(list)
    stats_updated = Signal(dict)
    error = Signal(str)
    file_operation_complete = Signal(str, str)
    book_creation_progress = Signal(int, int)
    
    transfer_preparation_complete = Signal(list, list)
    transfer_started = Signal(int, int)
    transfer_progress = Signal(str, int, int)

    def __init__(self, app_config):
        super().__init__()
        self.config = app_config
        self._is_cancelled = False

    def cancel_operation(self):
        self._is_cancelled = True

    @Slot()
    def perform_initial_scan(self):
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
        todays_books_folder = self.config.get("todays_books_folder")
        staged_book_details = {}
        try:
            if os.path.isdir(todays_books_folder):
                book_folders = [d for d in os.listdir(todays_books_folder) if os.path.isdir(os.path.join(todays_books_folder, d))]
                for book_folder in book_folders:
                    staged_book_details[book_folder] = self._count_pages_in_folder(os.path.join(todays_books_folder, book_folder))

            book_list_data = []
            pages_in_data_today = 0
            if os.path.exists(config.BOOKS_COMPLETE_LOG_FILE):
                try:
                    with open(config.BOOKS_COMPLETE_LOG_FILE, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    book_list_data = log_data.get(today_str, [])
                    for entry in book_list_data:
                        if isinstance(entry, dict):
                            pages_in_data_today += entry.get("pages", 0)
                except (json.JSONDecodeError, IOError) as e:
                    self.error.emit(f"Could not read log file: {e}")

            stats_result = {
                "staged_book_details": staged_book_details,
                "book_list_data": book_list_data,
                "pages_in_data": pages_in_data_today,
            }
            self.stats_updated.emit(stats_result)
        except Exception as e:
            self.error.emit(f"Error calculating stats: {e}")

    def _count_pages_in_folder(self, folder_path):
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
        try:
            if os.path.exists(path):
                os.remove(path)
                self.file_operation_complete.emit("delete", path)
            else:
                self.error.emit(f"File not found for deletion: {path}")
        except Exception as e:
            self.error.emit(f"Error deleting file {path}: {e}")

    @Slot(str, list)
    def create_book(self, book_name, files_to_move):
        self._is_cancelled = False
        try:
            todays_folder = self.config.get("todays_books_folder")
            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Today's Books Folder is not valid: {todays_folder}")
                return
            new_book_path = os.path.join(todays_folder, book_name)
            os.makedirs(new_book_path, exist_ok=True)

            total_files = len(files_to_move)
            for i, file_path in enumerate(files_to_move):
                if self._is_cancelled:
                    self.file_operation_complete.emit("create_book_cancelled", "Book creation cancelled.")
                    return
                if os.path.exists(file_path):
                    shutil.move(file_path, new_book_path)
                
                if i % 5 == 0 or i == total_files - 1:
                    self.book_creation_progress.emit(i + 1, total_files)
                    QThread.msleep(1) 

            self.file_operation_complete.emit("create_book", book_name)
        except Exception as e:
            self.error.emit(f"Failed to create book {book_name}: {e}")

    @Slot()
    def prepare_transfer(self):
        try:
            todays_folder = self.config.get("todays_books_folder")
            city_paths = self.config.get("city_paths", {})
            
            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Today's Books Folder is not valid: {todays_folder}")
                return
            
            book_folders = [d for d in os.listdir(todays_folder) if os.path.isdir(os.path.join(todays_folder, d))]
            
            moves_to_confirm = []
            warnings = []
            code_pattern = re.compile(r'-(\d{3})-')

            for book_name in book_folders:
                match = code_pattern.search(book_name)
                if not match:
                    warnings.append(f"- No city code found for: {book_name}")
                    continue

                city_code = match.group(1)
                city_path = city_paths.get(city_code)
                if not city_path or not os.path.isdir(city_path):
                    warnings.append(f"- Invalid path for city code '{city_code}' (Book: {book_name})")
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
            self.error.emit(f"Failed to prepare transfer: {e}")

    @Slot(list)
    def transfer_all_to_data(self, moves_to_perform):
        self._is_cancelled = False
        try:
            if not moves_to_perform:
                self.file_operation_complete.emit("transfer_all", "No books to transfer.")
                return

            total_pages_to_transfer = sum(self._count_pages_in_folder(move['source_path']) for move in moves_to_perform)
            self.transfer_started.emit(len(moves_to_perform), total_pages_to_transfer)

            log_data = {}
            if os.path.exists(config.BOOKS_COMPLETE_LOG_FILE):
                with open(config.BOOKS_COMPLETE_LOG_FILE, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            today_str = datetime.now().strftime('%Y-%m-%d')
            if today_str not in log_data:
                log_data[today_str] = []

            moved_count = 0
            total_pages_done = 0
            for move in moves_to_perform:
                if self._is_cancelled: break

                book_name = move['book_name']
                source_path = move['source_path']
                destination_folder = move['destination_folder']
                final_book_path = move['final_book_path']
                
                # Create the final destination book folder first
                os.makedirs(final_book_path, exist_ok=True)
                page_count = self._count_pages_in_folder(source_path)
                
                source_files = os.listdir(source_path)
                for i, filename in enumerate(source_files):
                    if self._is_cancelled: break
                    # Move each file into the newly created destination folder
                    shutil.move(os.path.join(source_path, filename), final_book_path)
                    total_pages_done += 1
                    self.transfer_progress.emit(book_name, i + 1, total_pages_done)
                    QThread.msleep(1)
                
                if self._is_cancelled: break

                os.rmdir(source_path)

                log_entry = {
                    "name": book_name, "pages": page_count,
                    "path": final_book_path, "timestamp": datetime.now().isoformat()
                }
                log_data[today_str].append(log_entry)
                moved_count += 1
            
            with open(config.BOOKS_COMPLETE_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=4)
            
            message = f"Successfully transferred {moved_count} books."
            if self._is_cancelled: message = f"Transfer cancelled. {moved_count} books transferred."
            self.file_operation_complete.emit("transfer_all", message)

        except Exception as e:
            self.error.emit(f"Failed to transfer books: {e}")

class NewImageHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def on_created(self, event):
        if not event.is_directory:
            time.sleep(0.1) 
            file_ext = os.path.splitext(event.src_path)[1].lower()
            if file_ext in config.ALLOWED_EXTENSIONS:
                self.callback(event.src_path)

class Watcher(QObject):
    error = Signal(str)
    finished = Signal()
    new_image_detected = Signal(str)

    def __init__(self, scan_directory):
        super().__init__()
        self.scan_directory = scan_directory
        self.observer = Observer()
        self.event_handler = NewImageHandler(callback=self.handle_new_image)
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.finished.connect(self.thread.quit)

    @Slot(str)
    def handle_new_image(self, path):
        self.new_image_detected.emit(path)

    @Slot()
    def run(self):
        if not self.scan_directory or not os.path.isdir(self.scan_directory):
            self.error.emit(f"Watchdog error: Invalid directory specified: {self.scan_directory}")
            self.finished.emit()
            return

        self.observer.schedule(self.event_handler, self.scan_directory, recursive=False)
        self.observer.start()

    @Slot()
    def stop(self):
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        self.finished.emit()


class ImageProcessor(QObject):
    image_loaded = Signal(str, QPixmap)
    image_rescaled = Signal(str, QPixmap)
    image_rotated = Signal(str, QPixmap)
    processing_complete = Signal(str)
    error = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._pixmap_cache = {}

    @Slot(str, bool)
    def request_image_load(self, path, force_reload=False):
        if not path or not os.path.exists(path):
            self.image_loaded.emit(path, QPixmap())
            return
        
        if force_reload and path in self._pixmap_cache:
            del self._pixmap_cache[path]

        if path in self._pixmap_cache:
            self.image_loaded.emit(path, self._pixmap_cache[path])
            return
        try:
            q_image = QImage(path)
            pixmap = QPixmap.fromImage(q_image)
            self._pixmap_cache[path] = pixmap
            self.image_loaded.emit(path, pixmap)
        except Exception as e:
            self.error.emit(f"Failed to load image {path}: {e}")

    @Slot(str, bool, bool)
    def auto_process_image(self, path, apply_lighting, apply_color):
        if not path or not os.path.exists(path):
            return
        try:
            with Image.open(path) as original_image:
                image_to_save = original_image.copy().convert('RGB')

                if apply_lighting:
                    image_to_save = ImageOps.autocontrast(image_to_save, cutoff=0.5)

                if apply_color:
                    image_to_save = self._correct_color_cast(image_to_save)

                self.create_backup(path)
                image_to_save.save(path)
                if path in self._pixmap_cache: del self._pixmap_cache[path]
                self.processing_complete.emit(path)

        except Exception as e:
            self.error.emit(f"Auto-processing failed for {os.path.basename(path)}: {e}")

    def _numpy_percentile_flat(self, arr_flat, q):
        arr_flat_sorted = sorted(arr_flat)
        k = (len(arr_flat_sorted) - 1) * (q / 100.0)
        f = int(k)
        c = k - f
        if f + 1 < len(arr_flat_sorted):
            return arr_flat_sorted[f] * (1 - c) + arr_flat_sorted[f + 1] * c
        else:
            return arr_flat_sorted[f]

    def _correct_color_cast(self, image, percentile=99.5):
        img_rgb = image.convert('RGB')
        pixels = list(img_rgb.getdata())

        r_channel = [p[0] for p in pixels]
        g_channel = [p[1] for p in pixels]
        b_channel = [p[2] for p in pixels]

        r_white = self._numpy_percentile_flat(r_channel, percentile)
        g_white = self._numpy_percentile_flat(g_channel, percentile)
        b_white = self._numpy_percentile_flat(b_channel, percentile)
        
        r_scale = 255.0 / (r_white if r_white > 0 else 255)
        g_scale = 255.0 / (g_white if g_white > 0 else 255)
        b_scale = 255.0 / (b_white if b_white > 0 else 255)
        
        new_pixels = []
        for r, g, b in pixels:
            new_r = min(255, int(r * r_scale))
            new_g = min(255, int(g * g_scale))
            new_b = min(255, int(b * b_scale))
            new_pixels.append((new_r, new_g, new_b))
        
        corrected_image = Image.new('RGB', image.size)
        corrected_image.putdata(new_pixels)
        
        return corrected_image

    @Slot(str, QSize)
    def get_zoomed_pixmap(self, path, target_size):
        if path not in self._pixmap_cache: return
        pixmap = self._pixmap_cache[path]
        scaled = pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_rescaled.emit(path, scaled)
        
    @Slot(str, int)
    def get_rotated_pixmap(self, path, angle):
        if path not in self._pixmap_cache: return
        original_pixmap = self._pixmap_cache[path]
        transform = QTransform().rotate(angle)
        rotated = original_pixmap.transformed(transform, Qt.SmoothTransformation)
        self._pixmap_cache[path] = rotated 
        self.image_rotated.emit(path, rotated)

    @Slot(str, QRect)
    def crop_and_save_image(self, path, crop_rect):
        try:
            self.create_backup(path)
            
            with Image.open(path) as img:
                cropped_img = img.crop((
                    crop_rect.x(),
                    crop_rect.y(),
                    crop_rect.x() + crop_rect.width(),
                    crop_rect.y() + crop_rect.height()
                ))
                cropped_img.save(path)
            
            if path in self._pixmap_cache:
                del self._pixmap_cache[path]
            
            self.processing_complete.emit(path)
        except Exception as e:
            self.error.emit(f"Failed to crop and save image {os.path.basename(path)}: {e}")

    def create_backup(self, path):
        if not os.path.exists(config.BACKUP_DIR): os.makedirs(config.BACKUP_DIR)
        backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
        if not os.path.exists(backup_path): shutil.copy(path, backup_path)

    @Slot(str)
    def restore_image(self, path):
        try:
            backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
            if not os.path.exists(backup_path):
                self.error.emit(f"No backup found for {os.path.basename(path)}")
                return
            shutil.copy(backup_path, path)
            if path in self._pixmap_cache: del self._pixmap_cache[path]
            self.processing_complete.emit(path)
        except Exception as e:
            self.error.emit(f"Failed to restore image {os.path.basename(path)}: {e}")

    @Slot(list)
    def clear_cache_for_paths(self, paths):
        for path in paths:
            if path in self._pixmap_cache:
                del self._pixmap_cache[path]

