import os
import shutil
import math
import re
import time
from datetime import datetime
import numpy as np
from PIL import Image, ImageOps

from PySide6.QtCore import QObject, Signal, Slot, QRect

from digipage.core.config import AppConfig, BACKUP_DIR, ALLOWED_EXTENSIONS
from digipage.data.io import LogManager, count_pages_in_folder
from digipage.utils.string_utils import natural_sort_key

class ScannerWorker(QObject):
    """
    Handles heavy I/O operations:
    - Scanning directories
    - Image manipulation (Crop, Split, Rotate, Auto-Correct)
    - File management (Move, Delete, Archive)
    """
    # Signals
    initial_scan_done = Signal(list)
    stats_calculated = Signal(dict)
    operation_complete = Signal(str, str) # type, message/path
    book_progress = Signal(int, int)
    transfer_ready = Signal(list, list) # moves, warnings
    error_occurred = Signal(str)

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self._cancel_flag = False

    @Slot()
    def cancel_current_op(self):
        self._cancel_flag = True

    # --- 1. Scanning & Stats ---
    
    @Slot()
    def scan_directory(self):
        folder = self.config.scan_folder
        if not folder or not os.path.isdir(folder):
            self.error_occurred.emit("Invalid scan folder configured.")
            self.initial_scan_done.emit([])
            return

        try:
            files = [
                os.path.join(folder, f) 
                for f in os.listdir(folder) 
                if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
            ]
            files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            self.initial_scan_done.emit(files)
        except Exception as e:
            self.error_occurred.emit(f"Scan failed: {e}")

    @Slot()
    def calculate_stats(self):
        try:
            # 1. Staged Books
            staged_details = {}
            today_folder = self.config.todays_books_folder
            if os.path.isdir(today_folder):
                subfolders = [f.path for f in os.scandir(today_folder) if f.is_dir()]
                for sub in subfolders:
                    staged_details[os.path.basename(sub)] = count_pages_in_folder(sub)

            # 2. Archived Books (Log)
            data_pages, data_books = LogManager.get_today_stats()
            
            stats = {
                "staged_books": staged_details,
                "archived_books": data_books,
                "archived_pages_count": data_pages
            }
            self.stats_calculated.emit(stats)
        except Exception as e:
            self.error_occurred.emit(f"Stats calculation error: {e}")

    # --- 2. Image Manipulation ---

    def _backup_image(self, path):
        if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
        dest = os.path.join(BACKUP_DIR, os.path.basename(path))
        if not os.path.exists(dest):
            try:
                shutil.copy2(path, dest)
            except Exception:
                pass # Non-critical

    @Slot(str, QRect)
    def crop_image(self, path, rect):
        try:
            self._backup_image(path)
            with Image.open(path) as img:
                cropped = img.crop((rect.x(), rect.y(), rect.x()+rect.width(), rect.y()+rect.height()))
                cropped.save(path)
            self.operation_complete.emit("crop", path)
        except Exception as e:
            self.error_occurred.emit(f"Crop failed: {e}")

    @Slot(str, float)
    def rotate_and_crop(self, path, angle):
        try:
            self._backup_image(path)
            with Image.open(path) as img:
                # Calculate zoom needed to eliminate black borders after rotation
                w, h = img.size
                rads = math.radians(angle)
                # Calculate bounding box of rotated image to know how much to zoom
                # Simplified logic: zoom to fit original bounds
                cos_a, sin_a = abs(math.cos(rads)), abs(math.sin(rads))
                # Zoom factor ensures the rotated image covers the original frame
                zoom = max(
                    cos_a + (h/w)*sin_a if w > 0 else 1,
                    (w/h)*sin_a + cos_a if h > 0 else 1
                )

                rotated = img.rotate(-angle, resample=Image.BICUBIC, expand=True)
                
                # Scale up
                new_w = int(rotated.width * zoom)
                new_h = int(rotated.height * zoom)
                scaled = rotated.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                # Center Crop to original size
                left = (new_w - w) / 2
                top = (new_h - h) / 2
                final = scaled.crop((left, top, left + w, top + h))
                final.save(path)
                
            self.operation_complete.emit("rotate", path)
        except Exception as e:
            self.error_occurred.emit(f"Rotate failed: {e}")

    @Slot(str, dict)
    def split_page(self, source_path, layout):
        """
        Single-Shot Mode: Splits one wide image into two files in /final/ subdir.
        Layout dict contains relative ratios for left and right pages.
        """
        try:
            scan_dir = os.path.dirname(source_path)
            final_dir = os.path.join(scan_dir, 'final')
            os.makedirs(final_dir, exist_ok=True)
            
            base_name = os.path.basename(source_path)
            name, ext = os.path.splitext(base_name)

            with Image.open(source_path) as img:
                w, h = img.size
                
                # Helper to convert ratio dict to pixel tuple
                def to_px(r):
                    return (int(r['x']*w), int(r['y']*h), int((r['x']+r['w'])*w), int((r['y']+r['h'])*h))

                # Process Left
                left_path = os.path.join(final_dir, f"{name}_L{ext}")
                if layout.get('left_enabled', True):
                    img.crop(to_px(layout['left'])).save(left_path)
                elif os.path.exists(left_path):
                    os.remove(left_path)

                # Process Right
                right_path = os.path.join(final_dir, f"{name}_R{ext}")
                if layout.get('right_enabled', True):
                    img.crop(to_px(layout['right'])).save(right_path)
                elif os.path.exists(right_path):
                    os.remove(right_path)

            self.operation_complete.emit("page_split", source_path)
        except Exception as e:
            self.error_occurred.emit(f"Split failed: {e}")

    # --- 3. File Management ---

    @Slot(str)
    def delete_file(self, path):
        try:
            if os.path.exists(path):
                os.remove(path)
            self.operation_complete.emit("delete", path)
        except OSError as e:
            self.error_occurred.emit(f"Could not delete {os.path.basename(path)}: {e}")

    @Slot(str, list, str)
    def create_book(self, book_name, file_paths, source_folder):
        self._cancel_flag = False
        target_dir = os.path.join(self.config.todays_books_folder, book_name)
        
        try:
            os.makedirs(target_dir, exist_ok=True)
            total = len(file_paths)
            
            # Sort using natural sort (e.g. 1, 2, 10 instead of 1, 10, 2)
            file_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

            for i, fpath in enumerate(file_paths):
                if self._cancel_flag:
                    shutil.rmtree(target_dir)
                    self.operation_complete.emit("create_book_cancelled", book_name)
                    return
                
                if os.path.exists(fpath):
                    ext = os.path.splitext(fpath)[1]
                    new_name = f"{i+1:04d}{ext}"
                    shutil.move(fpath, os.path.join(target_dir, new_name))
                
                self.book_progress.emit(i+1, total)

            # Cleanup for Single Split Mode (remove source images if we processed 'final' folder)
            if "final" in source_folder:
                parent_scan = os.path.dirname(source_folder) # The root scan folder
                # Clean original scans
                for f in os.listdir(parent_scan):
                    full = os.path.join(parent_scan, f)
                    if os.path.isfile(full) and os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
                        try: os.remove(full)
                        except: pass
                # Remove the final folder and layout file
                shutil.rmtree(source_folder, ignore_errors=True)
                layout_file = os.path.join(parent_scan, 'layout_data.json')
                if os.path.exists(layout_file): os.remove(layout_file)

            self.operation_complete.emit("create_book", book_name)

        except Exception as e:
            self.error_occurred.emit(f"Book creation failed: {e}")

    @Slot()
    def prepare_transfer(self):
        """Analyzes Today's folder and matches books with City Codes."""
        moves = []
        warnings = []
        today_dir = self.config.todays_books_folder
        city_map = self.config.city_paths
        
        try:
            if not os.path.exists(today_dir):
                self.error_occurred.emit("Today's folder not found.")
                return

            folders = [f.name for f in os.scandir(today_dir) if f.is_dir()]
            
            for book in folders:
                # Extract city code (e.g. "-297-")
                match = re.search(r'-(\d{3})-', book)
                if not match:
                    warnings.append(f"No city code found in: {book}")
                    continue
                
                code = match.group(1)
                target_root = city_map.get(code)
                
                if not target_root or not os.path.isdir(target_root):
                    warnings.append(f"Invalid path for city {code}: {book}")
                    continue
                
                # Build paths
                date_subdir = datetime.now().strftime('%d-%m')
                final_dest = os.path.join(target_root, date_subdir, book)
                
                moves.append({
                    "name": book,
                    "src": os.path.join(today_dir, book),
                    "dest": final_dest,
                    "dest_parent": os.path.join(target_root, date_subdir)
                })
            
            self.transfer_ready.emit(moves, warnings)

        except Exception as e:
            self.error_occurred.emit(f"Transfer prep failed: {e}")

    @Slot(list)
    def execute_transfer(self, moves):
        self._cancel_flag = False
        success_count = 0
        
        try:
            for move in moves:
                if self._cancel_flag: break
                
                os.makedirs(move["dest_parent"], exist_ok=True)
                shutil.move(move["src"], move["dest"])
                
                # Log success
                page_count = count_pages_in_folder(move["dest"])
                LogManager.append_entry({
                    "name": move["name"],
                    "pages": page_count,
                    "path": move["dest"],
                    "timestamp": datetime.now().isoformat()
                })
                success_count += 1
            
            self.operation_complete.emit("transfer", f"Transferred {success_count} books.")
        except Exception as e:
            self.error_occurred.emit(f"Transfer interrupted: {e}")