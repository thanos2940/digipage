import os
import re
import time
import json
import shutil
from datetime import datetime
from collections import OrderedDict
import math
import numpy as np
import threading # Added for navigation lock in MainWindow context
from concurrent.futures import ThreadPoolExecutor, as_completed # Added for parallel splitting

from PySide6.QtCore import QObject, Signal, Slot, QSize, Qt, QThread, QRect, QTimer
from PySide6.QtGui import QPixmap, QTransform, QImage
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileDeletedEvent, FileMovedEvent, FileCreatedEvent

# Use PIL imports directly
from PIL import Image, ImageOps, ImageFilter
from PIL.ImageQt import ImageQt

import config

# --- Utility Functions ---
def natural_sort_key(s):
# ... (rest of function remains unchanged)
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

# --- ScanWorker ---
class ScanWorker(QObject):
# ... (rest of ScanWorker remains unchanged until perform_page_split)
    initial_scan_complete = Signal(list)
    stats_updated = Signal(dict)
    error = Signal(str)
    file_operation_complete = Signal(str, str)
    book_creation_progress = Signal(int, int)
    
    transfer_preparation_complete = Signal(list, list)

    def __init__(self, app_config):
        super().__init__()
        self.config = app_config
        self._is_cancelled = False
        # ThreadPoolExecutor for parallel file operations (Issue 5.1)
        self.executor = ThreadPoolExecutor(max_workers=2) 

    def cancel_operation(self):
        self._is_cancelled = True
        
    def create_backup(self, path):
        if not os.path.exists(config.BACKUP_DIR): os.makedirs(config.BACKUP_DIR)
        backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
        # Use shutil.copy2 to preserve metadata (timestamps)
        if not os.path.exists(backup_path): shutil.copy2(path, backup_path)

    def _robust_move(self, src_path, dest_path):
        """
        Attempts to copy and then delete a file, with retries on deletion 
        to handle transient file locks.
        """
        # Note: This version of _robust_move is largely deprecated by the file system watcher
        # changes, but kept for book creation logic stability.
        try:
            # Copy the file first. copy2 preserves metadata.
            shutil.copy2(src_path, dest_path)
        except Exception as e:
            raise IOError(f"Failed to copy {os.path.basename(src_path)}: {e}")

        # Try to delete the source file with retries
        delete_attempts = 4
        for i in range(delete_attempts):
            try:
                os.remove(src_path)
                return True 
            except OSError:
                if i < delete_attempts - 1:
                    time.sleep(0.25)
                    continue
                else:
                    return False # Deletion failed, but copy succeeded
        return False

    def _correct_color_cast(self, image):
# ... (rest of _correct_color_cast remains unchanged)
        """
        Corrects color cast in an image using NumPy for high performance.
        (Logic remains consistent with original optimized intent.)
        """
        img_array = np.array(image.convert('RGB'), dtype=np.float32)

        r_white = np.percentile(img_array[:, :, 0], 99.5)
        g_white = np.percentile(img_array[:, :, 1], 99.5)
        b_white = np.percentile(img_array[:, :, 2], 99.5)

        avg_white_point = (r_white + g_white + b_white) / 3.0
        MIN_WHITE_POINT_THRESHOLD = 180
        if avg_white_point < MIN_WHITE_POINT_THRESHOLD:
            return image

        r_scale = 255.0 / r_white if r_white > 0 else 1.0
        g_scale = 255.0 / g_white if g_white > 0 else 1.0
        b_scale = 255.0 / b_white if b_white > 0 else 1.0

        img_array[:, :, 0] *= r_scale
        img_array[:, :, 1] *= g_scale
        img_array[:, :, 2] *= b_scale

        np.clip(img_array, 0, 255, out=img_array)
        corrected_image = Image.fromarray(img_array.astype(np.uint8), 'RGB')
        
        return corrected_image

    @Slot()
    def perform_initial_scan(self):
# ... (rest of perform_initial_scan remains unchanged)
        scan_directory = self.config.get("scan_folder")
        if not scan_directory or not os.path.isdir(scan_directory):
            self.error.emit(f"Ο Φάκελος Σάρωσης δεν είναι έγκυρος: {scan_directory}")
            self.initial_scan_complete.emit([])
            return
        try:
            files = [os.path.join(scan_directory, f) for f in os.listdir(scan_directory)
                     if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS]
            files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            self.initial_scan_complete.emit(files)
        except Exception as e:
            self.error.emit(f"Σφάλμα κατά την αρχική σάρωση: {e}")
            self.initial_scan_complete.emit([])

    @Slot()
    def calculate_today_stats(self):
# ... (rest of calculate_today_stats remains unchanged)
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
                    self.error.emit(f"Δεν ήταν δυνατή η ανάγνωση του αρχείου καταγραφής: {e}")

            stats_result = {
                "staged_book_details": staged_book_details,
                "book_list_data": book_list_data,
                "pages_in_data": pages_in_data_today,
            }
            self.stats_updated.emit(stats_result)
        except Exception as e:
            self.error.emit(f"Σφάλμα κατά τον υπολογισμό των στατιστικών: {e}")

    def _count_pages_in_folder(self, folder_path):
# ... (rest of _count_pages_in_folder remains unchanged)
        count = 0
        try:
            if os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS:
                        count += 1
        except Exception as e:
            self.error.emit(f"Σφάλμα κατά την καταμέτρηση σελίδων στο {folder_path}: {e}")
        return count

    @Slot(str)
    def delete_file(self, path):
# ... (rest of delete_file remains unchanged)
        max_retries = 5
        retry_delay = 0.1
        for i in range(max_retries):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    self.file_operation_complete.emit("delete", path)
                    return
                else:
                    self.file_operation_complete.emit("delete", path)
                    return
            except PermissionError as e:
                if i < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    self.error.emit(f"Σφάλμα κατά τη διαγραφή αρχείου {os.path.basename(path)}: {e}")
            except Exception as e:
                self.error.emit(f"Σφάλμα κατά τη διαγραφή αρχείου {os.path.basename(path)}: {e}")
                return

    @Slot(str, list, str)
    def create_book(self, book_name, files_to_move, source_folder):
# ... (rest of create_book remains unchanged)
        self._is_cancelled = False
        scan_folder = self.config.get("scan_folder")
        is_single_split_mode = "final" in source_folder

        try:
            todays_folder = self.config.get("todays_books_folder")
            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Ο Φάκελος Σημερινών Βιβλίων δεν είναι έγκυρος: {todays_folder}")
                return

            new_book_path = os.path.join(todays_folder, book_name)
            os.makedirs(new_book_path, exist_ok=True)

            total_files = len(files_to_move)
            files_to_move.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

            for i, file_path in enumerate(files_to_move):
                if self._is_cancelled:
                    shutil.rmtree(new_book_path, ignore_errors=True)
                    self.file_operation_complete.emit("create_book", f"Η δημιουργία του βιβλίου '{book_name}' ακυρώθηκε.")
                    return

                if os.path.exists(file_path):
                    _, extension = os.path.splitext(file_path)
                    new_base_name = f"{i + 1:04d}{extension}" 
                    dest_path = os.path.join(new_book_path, new_base_name)
                    shutil.move(file_path, dest_path)

                self.book_creation_progress.emit(i + 1, total_files)

            # --- Cleanup for Single Split Mode (Only deletes if process was successful) ---
            if is_single_split_mode:
                # Delete original full-size images from the main scan folder
                # The logic for identifying originals is simple: anything in the root scan_folder with allowed extension.
                original_files = [f for f in os.listdir(scan_folder) if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS]
                for f in original_files:
                    try:
                        os.remove(os.path.join(scan_folder, f))
                    except OSError:
                        pass
                
                final_folder_path = os.path.join(scan_folder, 'final')
                if os.path.isdir(final_folder_path):
                    shutil.rmtree(final_folder_path, ignore_errors=True)

                layout_data_path = os.path.join(scan_folder, 'layout_data.json')
                if os.path.exists(layout_data_path):
                    try:
                        os.remove(layout_data_path)
                    except OSError:
                        pass 
            
            self.file_operation_complete.emit("create_book", f"Το βιβλίο '{book_name}' δημιουργήθηκε.")

        except Exception as e:
            self.error.emit(f"Αποτυχία δημιουργίας βιβλίου {book_name}: {e}")

    @Slot()
    def prepare_transfer(self):
# ... (rest of prepare_transfer remains unchanged)
        try:
            todays_folder = self.config.get("todays_books_folder")
            city_paths = self.config.get("city_paths", {})
            
            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Ο Φάκελος Σημερινών Βιβλίων δεν είναι έγκυρος: {todays_folder}")
                return
            
            book_folders = [d for d in os.listdir(todays_folder) if os.path.isdir(os.path.join(todays_folder, d))]
            
            moves_to_confirm = []
            warnings = []
            code_pattern = re.compile(r'-(\d{3})-')

            for book_name in book_folders:
                match = code_pattern.search(book_name)
                if not match:
                    warnings.append(f"- Δεν βρέθηκε κωδικός πόλης για: {book_name}")
                    continue

                city_code = match.group(1)
                city_path = city_paths.get(city_code)
                if not city_path or not os.path.isdir(city_path):
                    warnings.append(f"- Μη έγκυρη διαδρομή για τον κωδικό πόλης '{city_code}' (Βιβλίο: {book_name})")
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
            self.error.emit(f"Αποτυχία προετοιμασίας μεταφοράς: {e}")

    @Slot(list)
    def transfer_all_to_data(self, moves_to_perform):
# ... (rest of transfer_all_to_data remains unchanged)
        self._is_cancelled = False
        try:
            if not moves_to_perform:
                self.file_operation_complete.emit("transfer_all", "Δεν υπάρχουν βιβλία για μεταφορά.")
                return

            log_data = {}
            if os.path.exists(config.BOOKS_COMPLETE_LOG_FILE):
                with open(config.BOOKS_COMPLETE_LOG_FILE, 'r', encoding='utf-8') as f:
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
                
                page_count = self._count_pages_in_folder(source_path)
                
                shutil.move(source_path, final_book_path)
                                
                if self._is_cancelled: break

                log_entry = {
                    "name": book_name, "pages": page_count,
                    "path": final_book_path, "timestamp": datetime.now().isoformat()
                }
                log_data[today_str].append(log_entry)
                moved_count += 1
            
            with open(config.BOOKS_COMPLETE_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=4)
            
            message = f"Επιτυχής μεταφορά {moved_count} βιβλίων."
            if self._is_cancelled: message = f"Η μεταφορά ακυρώθηκε. {moved_count} βιβλία μεταφέρθηκαν."
            self.file_operation_complete.emit("transfer_all", message)

        except Exception as e:
            self.error.emit(f"Αποτυχία μεταφοράς βιβλίων: {e}")

    @Slot(str, int)
    def split_image(self, path, split_x):
# ... (rest of split_image remains unchanged)
        try:
            self.create_backup(path)
            with Image.open(path) as img:
                w, h = img.size
                left_img = img.crop((0, 0, split_x, h))
                right_img = img.crop((split_x, 0, w, h))
                
                base, ext = os.path.splitext(path)
                right_path = f"{base}_2{ext}"

                left_img.save(path)
                right_img.save(right_path)
            
            self.file_operation_complete.emit("split", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία διαχωρισμού εικόνας {os.path.basename(path)}: {e}")

    @Slot(str, QRect)
    def crop_and_save_image(self, path, crop_rect):
# ... (rest of crop_and_save_image remains unchanged)
        try:
            self.create_backup(path)
            
            with Image.open(path) as img:
                cropped_img = img.crop((
                    crop_rect.x(),
                    crop_rect.y(),
                    crop_rect.x() + crop_rect.width(),
                    crop_rect.y() + crop_rect.height()
                ))
                cropped_img.save(path, quality=95, optimize=True) # Added save optimization
            
            self.file_operation_complete.emit("crop", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία περικοπής και αποθήκευσης εικόνας {os.path.basename(path)}: {e}")

    @Slot(str, float)
    def rotate_crop_and_save(self, path, angle):
# ... (rest of rotate_crop_and_save remains unchanged)
        try:
            self.create_backup(path)
            with Image.open(path) as img:
                original_width, original_height = img.size
                angle_rad = math.radians(angle)
                
                w, h = original_width, original_height
                cosa = abs(math.cos(angle_rad))
                sina = abs(math.sin(angle_rad))

                zoom_factor_w = cosa + (h / w) * sina if w > 0 else 1
                zoom_factor_h = (w / h) * sina + cosa if h > 0 else 1
                zoom_factor = max(zoom_factor_w, zoom_factor_h)

                # Use LANCZOS for rotation (Issue 5.2 Fix)
                rotated_img = img.rotate(-angle, resample=Image.Resampling.LANCZOS, expand=True) 
                
                new_size = (int(rotated_img.width * zoom_factor), int(rotated_img.height * zoom_factor))
                # Use LANCZOS for resizing (Issue 5.2 Fix)
                zoomed_rotated_img = rotated_img.resize(new_size, Image.Resampling.LANCZOS) 
                
                left = (zoomed_rotated_img.width - original_width) / 2
                top = (zoomed_rotated_img.height - original_height) / 2
                right = left + original_width
                bottom = top + original_height
                
                final_img = zoomed_rotated_img.crop((left, top, right, bottom))
                
                # Apply light sharpening (Issue 5.2 Fix)
                final_img = final_img.filter(ImageFilter.UnsharpMask(radius=0.5, percent=50, threshold=3))

                final_img.save(path, quality=95, optimize=True) # Added save optimization

            self.file_operation_complete.emit("rotate", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία περιστροφής και περικοπής εικόνας {os.path.basename(path)}: {e}")

    @Slot(str)
    def restore_image(self, path):
# ... (rest of restore_image remains unchanged)
        try:
            backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
            if not os.path.exists(backup_path):
                self.error.emit(f"Δεν βρέθηκε αντίγραφο ασφαλείας για το {os.path.basename(path)}")
                return
            shutil.copy2(backup_path, path) # Use copy2 to preserve metadata
            self.file_operation_complete.emit("restore", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία επαναφοράς εικόνας {os.path.basename(path)}: {e}")
            
    @Slot(str)
    def correct_color_and_save(self, path):
# ... (rest of correct_color_and_save remains unchanged)
        try:
            self.create_backup(path)
            with Image.open(path) as img:
                corrected_img = self._correct_color_cast(img)
                corrected_img.save(path, quality=95, optimize=True) # Added save optimization
            self.file_operation_complete.emit("color_fix", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία διόρθωσης χρώματος για την εικόνα {os.path.basename(path)}: {e}")

    @Slot(str, str, str, str)
    def replace_pair(self, old_path1, old_path2, new_path1, new_path2):
# ... (rest of replace_pair remains unchanged)
        # Increased robustness for file operations here
        retry_delay = 0.3 # seconds
        max_retries = 5
        
        def safe_delete(path):
            if os.path.exists(path):
                for i in range(max_retries):
                    try:
                        os.remove(path)
                        return True
                    except OSError:
                        time.sleep(retry_delay)
                raise OSError(f"Failed to delete old file {os.path.basename(path)} after retries.")

        def safe_rename(old_path, new_path):
            for i in range(max_retries):
                try:
                    os.rename(old_path, new_path)
                    return True
                except OSError:
                    time.sleep(retry_delay)
            raise OSError(f"Failed to rename {os.path.basename(old_path)} to {os.path.basename(new_path)} after retries.")

        try:
            # Delete old files first
            safe_delete(old_path1)
            safe_delete(old_path2)
            
            # Rename new files to old paths
            safe_rename(new_path1, old_path1)
            safe_rename(new_path2, old_path2)
            
            self.file_operation_complete.emit("replace_pair", "Το ζεύγος αντικαταστάθηκε με επιτυχία.")
        except Exception as e:
            self.error.emit(f"Αποτυχία αντικατάστασης ζεύγους: {e}")

    @Slot(str, str, dict)
    def replace_single_image(self, old_path, new_path, layout_data):
# ... (rest of replace_single_image remains unchanged)
        """
        Replaces a single source image with a new one, then re-applies the
        page split operation using the layout from the original image.
        (Bug 8.2 Fix)
        """
        retry_delay = 0.3 # seconds
        max_retries = 5
        
        try:
            # 1. Delete the old image and its artifacts (with retry mechanism in the helper)
            self.delete_split_image_and_artifacts(old_path)
            time.sleep(0.1) # Give OS a moment to release handles

            # 2. Rename the new image to the old image path with retries
            for i in range(max_retries):
                try:
                    os.rename(new_path, old_path)
                    break 
                except OSError as e:
                    if i < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise e

            # 3. Re-run the page split process on the newly renamed image (parallelized in perform_page_split)
            self.perform_page_split(old_path, layout_data)

            # 4. Signal completion
            self.file_operation_complete.emit("replace_single", old_path)

        except Exception as e:
            self.error.emit(f"Αποτυχία αντικατάστασης εικόνας: {e}")


    @Slot(str, dict)
    def perform_page_split(self, source_path, layout_data):
        """
        Crops two pages from a single source image based on layout data and
        saves them to a 'final' subdirectory using parallel execution. (Issue 5.1 Fix)
        """
        # We need a robust way to open the file to avoid 'unrecognized data stream contents'
        img = None
        for i in range(5):
            try:
                img = Image.open(source_path)
                img.load()
                break # Success
            except (IOError, OSError) as e:
                # If it's a truncated error, wait and retry.
                if "truncated" in str(e).lower() or "unrecognized data stream" in str(e).lower():
                    if i < 4:
                        time.sleep(0.25)
                        continue
                raise # Re-raise final exception if retries fail or it's a different error
        
        if not img:
            self.error.emit(f"Αποτυχία διαχωρισμού σελίδων: Δεν ήταν δυνατή η φόρτωση της πηγής.")
            return

        try:
            scan_folder = os.path.dirname(source_path)
            final_folder = os.path.join(scan_folder, 'final')
            os.makedirs(final_folder, exist_ok=True)

            with img: # Ensure the file handle is closed
                w, h = img.size
                
                # Helper function to get absolute pixel rect from ratios
                def get_abs_rect(ratios):
                    x = int(ratios['x'] * w)
                    y = int(ratios['y'] * h)
                    width = int(ratios['w'] * w)
                    height = int(ratios['h'] * h)
                    return (x, y, x + width, y + height)

                base, ext = os.path.splitext(os.path.basename(source_path))
                
                def save_page(page_id, ratios, enabled):
                    out_path = os.path.join(final_folder, f"{base}_{page_id}{ext}")
                    
                    if not enabled:
                        if os.path.exists(out_path):
                            os.remove(out_path)
                        return None
                    
                    box = get_abs_rect(ratios)
                    page_crop = img.crop(box)
                    
                    # Save with optimizations
                    save_kwargs = {'quality': 95, 'optimize': True}
                    if ext.lower() in ['.jpg', '.jpeg']:
                        save_kwargs['progressive'] = True
                    
                    page_crop.save(out_path, **save_kwargs)
                    return out_path
                
                # --- Parallel Execution ---
                futures = {
                    self.executor.submit(
                        save_page,
                        'L',
                        layout_data['left'],
                        layout_data.get('left_enabled', True)
                    ): 'left',
                    self.executor.submit(
                        save_page,
                        'R',
                        layout_data['right'],
                        layout_data.get('right_enabled', True)
                    ): 'right'
                }
                
                for future in as_completed(futures):
                    future.result() # Wait for results (will re-raise exceptions)

            self.file_operation_complete.emit("page_split", source_path)

        except Exception as e:
            # Check if the error came from the futures (Image.open error)
            error_message = f"Αποτυχία διαχωρισμού σελίδων: {e}"
            self.error.emit(error_message)

    @Slot(str)
    def delete_split_image_and_artifacts(self, source_path):
# ... (rest of delete_split_image_and_artifacts remains unchanged)
        """
        Deletes a source image, its cropped artifacts (_L.jpg, _R.jpg),
        and its backup.
        """
        max_retries = 5
        retry_delay = 0.2
        paths_to_delete = []

        try:
            # Paths to delete
            scan_folder = os.path.dirname(source_path)
            base, ext = os.path.splitext(os.path.basename(source_path))
            final_folder = os.path.join(scan_folder, 'final')

            paths_to_delete.append(source_path)
            paths_to_delete.append(os.path.join(final_folder, f"{base}_L{ext}"))
            paths_to_delete.append(os.path.join(final_folder, f"{base}_R{ext}"))
            paths_to_delete.append(os.path.join(config.BACKUP_DIR, os.path.basename(source_path)))

            # Delete all paths with retries
            for path in paths_to_delete:
                if os.path.exists(path):
                    for i in range(max_retries):
                        try:
                            os.remove(path)
                            break
                        except OSError:
                            time.sleep(retry_delay)
                    
            self.file_operation_complete.emit("delete", source_path)
        except Exception as e:
            self.error.emit(f"Αποτυχία διαγραφής: {e}")

    @Slot(str, str)
    def delete_split_artifact(self, source_path, side):
# ... (rest of delete_split_artifact remains unchanged)
        """Deletes a single cropped artifact (_L or _R) for a given source image."""
        try:
            scan_folder = os.path.dirname(source_path)
            base, ext = os.path.splitext(os.path.basename(source_path))
            final_folder = os.path.join(scan_folder, 'final')

            side_suffix = "_L" if side == "left" else "_R"
            artifact_path = os.path.join(final_folder, f"{base}{side_suffix}{ext}")

            if os.path.exists(artifact_path):
                os.remove(artifact_path)
        except Exception as e:
            self.error.emit(f"Αποτυχία διαγραφής παραγώγου: {e}")

# --- New Watcher/Handler Implementations ---
class NewImageHandler(FileSystemEventHandler):
# ... (rest of NewImageHandler remains unchanged)
    def __init__(self, new_file_callback, deletion_callback, rename_callback):
        super().__init__()
        self.new_file_callback = new_file_callback
        self.deletion_callback = deletion_callback
        self.rename_callback = rename_callback

    def _wait_for_file_to_stabilize(self, file_path, timeout=10):
        """
        Waits for file to be completely written and released by writer.
        (Issue 2.1 Fix)
        """
        start_time = time.time()
        last_size = -1
        last_mtime = -1
        stable_checks = 0
        required_stable_checks = 3
        
        while time.time() - start_time < timeout:
            try:
                if not os.path.exists(file_path):
                    return False
                
                current_size = os.path.getsize(file_path)
                current_mtime = os.path.getmtime(file_path)
                
                # Check stability
                if current_size == last_size and current_mtime == last_mtime and current_size > 0:
                    stable_checks += 1
                    
                    if stable_checks >= required_stable_checks:
                        # Test if the file is truly released by attempting to open and read
                        try:
                            with open(file_path, 'rb') as f:
                                f.read(1024)
                            return True
                        except (IOError, OSError):
                            stable_checks = 0 # File still locked, reset
                else:
                    stable_checks = 0
                
                last_size = current_size
                last_mtime = current_mtime
                time.sleep(0.15) # Wait 150ms between checks
                
            except (IOError, OSError):
                time.sleep(0.15)
                continue
        
        return False


    def on_created(self, event):
        if not event.is_directory:
            file_ext = os.path.splitext(event.src_path)[1].lower()
            if file_ext in config.ALLOWED_EXTENSIONS:
                # Wait for stabilization before processing
                if self._wait_for_file_to_stabilize(event.src_path):
                    self.new_file_callback(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            file_ext = os.path.splitext(event.src_path)[1].lower()
            if file_ext in config.ALLOWED_EXTENSIONS:
                self.deletion_callback(event.src_path) # Differential update (Issue 2.2)

    def on_moved(self, event):
        if not event.is_directory:
            src_ext = os.path.splitext(event.src_path)[1].lower()
            dest_ext = os.path.splitext(event.dest_path)[1].lower()
            
            # We only care about moves/renames involving our file types
            if src_ext in config.ALLOWED_EXTENSIONS or dest_ext in config.ALLOWED_EXTENSIONS:
                self.rename_callback(event.src_path, event.dest_path) # Differential update (Issue 2.2)


class Watcher(QObject):
# ... (rest of Watcher remains unchanged)
    error = Signal(str)
    finished = Signal()
    new_image_detected = Signal(str)
    file_deleted = Signal(str) # New Signal (Issue 2.2)
    file_renamed = Signal(str, str) # New Signal (Issue 2.2)

    def __init__(self, scan_directory):
        super().__init__()
        self.scan_directory = scan_directory
        self.observer = Observer()
        
        # New ImageHandler instance with specific callbacks
        self.event_handler = NewImageHandler(
            new_file_callback=self.handle_new_image,
            deletion_callback=self.handle_file_deleted,
            rename_callback=self.handle_file_renamed
        )
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.finished.connect(self.thread.quit)

    @Slot(str)
    def handle_new_image(self, path):
        self.new_image_detected.emit(path)
        
    @Slot(str)
    def handle_file_deleted(self, path):
        self.file_deleted.emit(path)
        
    @Slot(str, str)
    def handle_file_renamed(self, old_path, new_path):
        self.file_renamed.emit(old_path, new_path)

    @Slot()
    def run(self):
        if not self.scan_directory or not os.path.isdir(self.scan_directory):
            self.error.emit(f"Σφάλμα Watchdog: Μη έγκυρος φάκελος καθορισμένος: {self.scan_directory}")
            self.finished.emit()
            return

        self.observer.schedule(self.event_handler, self.scan_directory, recursive=False)
        self.observer.start()

    @Slot()
    def stop(self):
        if hasattr(self, 'observer') and self.observer.is_alive():
            self.observer.stop()
            self.thread.wait(500) # Wait for thread to finish cleanly


# --- ImageProcessor ---
import psutil # Added for memory monitoring (Issue 7.1)
class ImageProcessor(QObject):
# ... (rest of ImageProcessor remains unchanged)
    image_loaded = Signal(str, QPixmap)
    processing_complete = Signal(str)
    thumbnail_loaded = Signal(int, str, QPixmap)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._pixmap_cache = {}  # Changed to dict (Issue 1.2 Fix)
        self._cache_access_order = []  # List of (path, size_bytes)
        self._caching_enabled = True
        
        # Fixed cache size is replaced by a max memory limit
        self.MAX_CACHE_BYTES = 500 * 1024 * 1024  # 500MB (Issue 1.2 Fix)
        self._current_cache_bytes = 0

        # Memory Pressure Monitor (Issue 7.1 Fix)
        self._memory_monitor_timer = QTimer()
        self._memory_monitor_timer.setInterval(5000)
        self._memory_monitor_timer.timeout.connect(self._check_memory_pressure)
        self._memory_monitor_timer.start()

    @Slot(bool)
    def set_caching_enabled(self, enabled):
        self._caching_enabled = enabled
        if not enabled:
            self.clear_cache()
            
    def clear_cache(self):
        self._pixmap_cache.clear()
        self._cache_access_order.clear()
        self._current_cache_bytes = 0

    @Slot(list)
    def clear_cache_for_paths(self, paths):
        for path in paths:
            if path in self._pixmap_cache:
                pixmap = self._pixmap_cache.pop(path)
                bytes_used = pixmap.width() * pixmap.height() * (pixmap.depth() // 8)
                self._current_cache_bytes -= bytes_used
                # Remove from access order list
                self._cache_access_order[:] = [(p, ts, s) for p, ts, s in self._cache_access_order if p != path]
        
    def _calculate_pixmap_bytes(self, pixmap):
        return pixmap.width() * pixmap.height() * (pixmap.depth() // 8)

    def _add_to_cache(self, path, pixmap):
        """Adds to cache with size-aware LRU eviction."""
        if not self._caching_enabled: return

        bytes_used = self._calculate_pixmap_bytes(pixmap)
        
        # Evict until we have space
        while (self._current_cache_bytes + bytes_used > self.MAX_CACHE_BYTES 
               and self._cache_access_order):
            # LRU policy: remove oldest (first in list)
            oldest_path, _, oldest_size = self._cache_access_order.pop(0)
            if oldest_path in self._pixmap_cache:
                del self._pixmap_cache[oldest_path]
                self._current_cache_bytes -= oldest_size
        
        self._pixmap_cache[path] = pixmap
        # Store tuple: (path, timestamp, size_bytes)
        self._cache_access_order.append((path, time.time(), bytes_used))
        self._current_cache_bytes += bytes_used

    def _update_access_order(self, path):
        """Moves accessed item to end (most recent)."""
        if not self._caching_enabled: return
        
        for i, (p, ts, size) in enumerate(self._cache_access_order):
            if p == path:
                # Move accessed item to end (most recent)
                self._cache_access_order.append(
                    self._cache_access_order.pop(i)
                )
                break
                
    def _check_memory_pressure(self):
        """Reduces cache size under memory pressure (Issue 7.1 Fix)"""
        try:
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_percent = process.memory_percent()
            
            # If using > 1GB or > 30% of system RAM, aggressively trim cache
            if mem_info.rss > 1024**3 or mem_percent > 30:
                target_cache_bytes = self.MAX_CACHE_BYTES // 2
                
                while (self._current_cache_bytes > target_cache_bytes and 
                       self._cache_access_order):
                    # Aggressively remove oldest item
                    oldest_path, _, oldest_size = self._cache_access_order.pop(0)
                    if oldest_path in self._pixmap_cache:
                        del self._pixmap_cache[oldest_path]
                        self._current_cache_bytes -= oldest_size
        except Exception:
            # Handle potential psutil errors gracefully
            pass

    @Slot(str, bool)
    def request_image_load(self, path, force_reload=False):
        if not path or not os.path.exists(path):
            self.image_loaded.emit(path, QPixmap())
            return
        
        if force_reload and path in self._pixmap_cache:
            self.clear_cache_for_paths([path])

        if self._caching_enabled and path in self._pixmap_cache:
            self._update_access_order(path) # Update LRU position (Issue 1.2 Fix)
            self.image_loaded.emit(path, self._pixmap_cache[path])
            return

        pil_img = None
        for i in range(5): 
            try:
                with Image.open(path) as img:
                    img.load()  
                    pil_img = img.copy()
                break
            except (IOError, OSError) as e:
                if "truncated" in str(e).lower() and i < 4:
                    time.sleep(0.2)
                    continue
                else:
                    self.error.emit(f"Αποτυχία φόρτωσης εικόνας {os.path.basename(path)}: {e}")
                    self.image_loaded.emit(path, QPixmap())
                    return
        
        if not pil_img:
            self.image_loaded.emit(path, QPixmap())
            return

        try:
            # --- Efficient Format Conversion (Issue 1.1 Fix) ---
            # Most scanned docs are RGB. Only convert to RGBA if necessary.
            needs_rgba = pil_img.mode in ('P', 'LA', 'PA', 'RGBA') or (
                pil_img.mode == 'RGB' and pil_img.info.get('transparency') is not None
            )
            if needs_rgba and pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            elif not needs_rgba and pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            # --- End Fix ---
            
            q_image = ImageQt(pil_img)
            pixmap = QPixmap.fromImage(q_image)
            
            if self._caching_enabled:
                self._add_to_cache(path, pixmap) # Use size-aware cache (Issue 1.2 Fix)

            self.image_loaded.emit(path, pixmap)
        except Exception as e:
            self.error.emit(f"Αποτυχία επεξεργασίας εικόνας {path}: {e}")

    @Slot(str)
    def prefetch_image(self, path):
# ... (rest of prefetch_image remains unchanged)
        """Low-priority background load that doesn't emit signals (Issue 1.3 Fix)."""
        if not self._caching_enabled or path in self._pixmap_cache or not os.path.exists(path):
            return
        
        pil_img = None
        try:
            with Image.open(path) as img:
                img.load()
                pil_img = img.copy()
            
            if pil_img:
                # Use the same efficient conversion logic
                needs_rgba = pil_img.mode in ('P', 'LA', 'PA', 'RGBA') or (
                    pil_img.mode == 'RGB' and pil_img.info.get('transparency') is not None
                )
                if needs_rgba and pil_img.mode != "RGBA":
                    pil_img = pil_img.convert("RGBA")
                elif not needs_rgba and pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                
                q_image = ImageQt(pil_img)
                pixmap = QPixmap.fromImage(q_image)
                
                self._add_to_cache(path, pixmap) # Add to cache
        except:
            pass  # Silent failure for prefetch
            
    # Auto-processing left as is but noted for future refactoring (should pass original worker instance)
    @Slot(str, bool, bool)
    def auto_process_image(self, path, apply_lighting, apply_color):
# ... (rest of auto_process_image remains unchanged)
        try:
            with Image.open(path) as original_image:
                image_to_save = original_image.copy().convert('RGB')
                
                scan_worker_ref = ScanWorker(config.load_config()) # Temporary instance

                if apply_lighting:
                    image_to_save = ImageOps.autocontrast(image_to_save, cutoff=0.5)

                if apply_color:
                    image_to_save = scan_worker_ref._correct_color_cast(image_to_save)

                self.create_backup(path)
                image_to_save.save(path, quality=95, optimize=True) # Added save optimization
                
                if path in self._pixmap_cache: self.clear_cache_for_paths([path])
                self.processing_complete.emit(path)

        except Exception as e:
            self.error.emit(f"Η αυτόματη επεξεργασία απέτυχε για το {os.path.basename(path)}: {e}")
        
    def create_backup(self, path):
        if not os.path.exists(config.BACKUP_DIR): os.makedirs(config.BACKUP_DIR)
        backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
        if not os.path.exists(backup_path): shutil.copy2(path, backup_path) # Use copy2