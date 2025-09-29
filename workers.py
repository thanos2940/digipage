import os
import re
import time
import json
import shutil
from datetime import datetime
from collections import OrderedDict
import math
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, QSize, Qt, QThread, QRect
from PySide6.QtGui import QPixmap, QTransform, QImage
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileDeletedEvent, FileMovedEvent
from PIL import Image, ImageOps, ImageFilter
from PIL.ImageQt import ImageQt

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

    def __init__(self, app_config):
        super().__init__()
        self.config = app_config
        self._is_cancelled = False

    def cancel_operation(self):
        self._is_cancelled = True
        
    def create_backup(self, path):
        if not os.path.exists(config.BACKUP_DIR): os.makedirs(config.BACKUP_DIR)
        backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
        if not os.path.exists(backup_path): shutil.copy(path, backup_path)

    def _robust_move(self, src_path, dest_path):
        """
        Attempts to copy and then delete a file, with retries on deletion 
        to handle transient file locks.
        Returns True on full success, False if deletion fails but copy succeeds.
        """
        try:
            # Copy the file first. copy2 preserves metadata.
            shutil.copy2(src_path, dest_path)
        except Exception as e:
            # If copy fails, it's a hard error.
            raise IOError(f"Failed to copy {os.path.basename(src_path)}: {e}")

        # Try to delete the source file with retries
        delete_attempts = 4
        for i in range(delete_attempts):
            try:
                os.remove(src_path)
                return True # Success
            except OSError:
                if i < delete_attempts - 1:
                    time.sleep(0.25) # Wait 250ms before retrying
                    continue
                else:
                    # All retries failed
                    return False # Deletion failed, but copy succeeded
        return False

    def _correct_color_cast(self, image):
        """
        Corrects color cast in an image using NumPy for high performance.
        This method balances the white point by scaling the color channels based on
        their 99.5th percentile, but only if the image is reasonably bright to begin with.
        """
        img_array = np.array(image.convert('RGB'), dtype=np.float32)

        # Calculate the 99.5th percentile to find the white point for each channel
        r_white = np.percentile(img_array[:, :, 0], 99.5)
        g_white = np.percentile(img_array[:, :, 1], 99.5)
        b_white = np.percentile(img_array[:, :, 2], 99.5)

        # --- ΒΕΛΤΙΩΣΗ ---
        # Υπολογίζουμε το μέσο "λευκό" σημείο.
        avg_white_point = (r_white + g_white + b_white) / 3.0
        
        # Ορίζουμε ένα κατώφλι. Αν η εικόνα είναι πολύ σκοτεινή (π.χ. το "λευκό" της είναι κάτω από 180),
        # η αυτόματη διόρθωση μπορεί να την καταστρέψει. Σε αυτή την περίπτωση, την επιστρέφουμε ως έχει.
        MIN_WHITE_POINT_THRESHOLD = 180
        if avg_white_point < MIN_WHITE_POINT_THRESHOLD:
            return image
        # --- ΤΕΛΟΣ ΒΕΛΤΙΩΣΗΣ ---

        # Calculate scaling factors, avoiding division by zero
        r_scale = 255.0 / r_white if r_white > 0 else 1.0
        g_scale = 255.0 / g_white if g_white > 0 else 1.0
        b_scale = 255.0 / b_white if b_white > 0 else 1.0

        # Apply scaling to all pixels at once using vectorized multiplication
        img_array[:, :, 0] *= r_scale
        img_array[:, :, 1] *= g_scale
        img_array[:, :, 2] *= b_scale

        # Clip values to the valid 0-255 range to prevent color overflow
        np.clip(img_array, 0, 255, out=img_array)

        # Convert the array back to an 8-bit integer type and then to a PIL image
        corrected_image = Image.fromarray(img_array.astype(np.uint8), 'RGB')
        
        return corrected_image

    @Slot()
    def perform_initial_scan(self):
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
        max_retries = 5
        retry_delay = 0.1 # seconds
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

    @Slot(str, list)
    def create_book(self, book_name, files_to_move):
        self._is_cancelled = False
        try:
            todays_folder = self.config.get("todays_books_folder")
            if not todays_folder or not os.path.isdir(todays_folder):
                self.error.emit(f"Ο Φάκελος Σημερινών Βιβλίων δεν είναι έγκυρος: {todays_folder}")
                return
            new_book_path = os.path.join(todays_folder, book_name)
            os.makedirs(new_book_path, exist_ok=True)

            total_files = len(files_to_move)
            failed_deletions = []

            # --- Throttling Logic ---
            last_update_time = time.time()
            update_interval = 0.25  # seconds

            for i, file_path in enumerate(files_to_move):
                if self._is_cancelled:
                    try:
                        shutil.rmtree(new_book_path)
                    except OSError as e:
                        self.error.emit(f"Could not clean up partially created book folder: {e}")
                    self.file_operation_complete.emit("create_book", f"Η δημιουργία του βιβλίου '{book_name}' ακυρώθηκε.")
                    return

                if os.path.exists(file_path):
                    _, extension = os.path.splitext(file_path)
                    new_base_name = f"{i + 1}{extension}"
                    dest_path = os.path.join(new_book_path, new_base_name)
                    
                    if not self._robust_move(file_path, dest_path):
                        original_base_name = os.path.basename(file_path)
                        failed_deletions.append(original_base_name)
                
                # --- Emit progress signal on a timer ---
                current_time = time.time()
                # Also emit on the very last file to guarantee it reaches 100%
                if (current_time - last_update_time >= update_interval) or (i + 1 == total_files):
                    self.book_creation_progress.emit(i + 1, total_files)
                    last_update_time = current_time
            
            # Construct final message
            final_message = f"Το βιβλίο '{book_name}' δημιουργήθηκε με {total_files} σελίδες."
            if failed_deletions:
                failed_files_str = ', '.join(failed_deletions)
                final_message += (f"\nΠΡΟΕΙΔΟΠΟΙΗΣΗ: Δεν ήταν δυνατή η διαγραφή {len(failed_deletions)} αρχείων "
                                  f"από τον φάκελο σάρωσης: {failed_files_str}")

            self.file_operation_complete.emit("create_book", final_message)

        except Exception as e:
            self.error.emit(f"Αποτυχία δημιουργίας βιβλίου {book_name}: {e}")



    @Slot()
    def prepare_transfer(self):
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
            
            self.file_operation_complete.emit("crop", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία περικοπής και αποθήκευσης εικόνας {os.path.basename(path)}: {e}")

    @Slot(str, float)
    def rotate_crop_and_save(self, path, angle):
        try:
            self.create_backup(path)
            with Image.open(path) as img:
                original_width, original_height = img.size
                angle_rad = math.radians(angle)
                
                # --- New Logic: Calculate the zoom required to fill the original bounds ---
                w, h = original_width, original_height
                cosa = abs(math.cos(angle_rad))
                sina = abs(math.sin(angle_rad))

                # The required zoom is determined by the point on the rotated image that must
                # reach the corner of the original frame. We calculate the zoom needed for
                # both width and height and take the maximum to ensure full coverage.
                zoom_factor_w = cosa + (h / w) * sina if w > 0 else 1
                zoom_factor_h = (w / h) * sina + cosa if h > 0 else 1
                zoom_factor = max(zoom_factor_w, zoom_factor_h)

                # 1. Rotate the image, expanding the canvas to fit the new bounding box.
                #    Pillow rotates counter-clockwise, so we negate the angle from the Qt UI.
                rotated_img = img.rotate(-angle, resample=Image.BICUBIC, expand=True)
                
                # 2. Scale the rotated image up to fill the frame.
                new_size = (int(rotated_img.width * zoom_factor), int(rotated_img.height * zoom_factor))
                zoomed_rotated_img = rotated_img.resize(new_size, Image.Resampling.LANCZOS)
                
                # 3. Crop the center of the zoomed, rotated image to the original dimensions.
                left = (zoomed_rotated_img.width - original_width) / 2
                top = (zoomed_rotated_img.height - original_height) / 2
                right = left + original_width
                bottom = top + original_height
                
                final_img = zoomed_rotated_img.crop((left, top, right, bottom))
                final_img.save(path)

            self.file_operation_complete.emit("rotate", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία περιστροφής και περικοπής εικόνας {os.path.basename(path)}: {e}")

    @Slot(str)
    def restore_image(self, path):
        try:
            backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
            if not os.path.exists(backup_path):
                self.error.emit(f"Δεν βρέθηκε αντίγραφο ασφαλείας για το {os.path.basename(path)}")
                return
            shutil.copy(backup_path, path)
            self.file_operation_complete.emit("restore", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία επαναφοράς εικόνας {os.path.basename(path)}: {e}")
            
    @Slot(str)
    def correct_color_and_save(self, path):
        try:
            self.create_backup(path)
            with Image.open(path) as img:
                corrected_img = self._correct_color_cast(img)
                corrected_img.save(path)
            self.file_operation_complete.emit("color_fix", path)
        except Exception as e:
            self.error.emit(f"Αποτυχία διόρθωσης χρώματος για την εικόνα {os.path.basename(path)}: {e}")

    @Slot(str, str, str, str)
    def replace_pair(self, old_path1, old_path2, new_path1, new_path2):
        try:
            if os.path.exists(old_path1):
                os.remove(old_path1)
            if os.path.exists(old_path2):
                os.remove(old_path2)
            
            os.rename(new_path1, old_path1)
            os.rename(new_path2, old_path2)
            
            self.file_operation_complete.emit("replace_pair", "Το ζεύγος αντικαταστάθηκε με επιτυχία.")
        except Exception as e:
            self.error.emit(f"Αποτυχία αντικατάστασης ζεύγους: {e}")


class NewImageHandler(FileSystemEventHandler):
    def __init__(self, callback, general_change_callback):
        super().__init__()
        self.callback = callback
        self.general_change_callback = general_change_callback

    def _wait_for_file_to_stabilize(self, file_path):
        """Waits for the file size to stop changing before proceeding."""
        last_size = -1
        try:
            for _ in range(30): 
                if not os.path.exists(file_path):
                    return False
                
                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
                time.sleep(0.1)
        except (IOError, OSError):
            return False
        return False

    def on_created(self, event):
        if not event.is_directory:
            file_ext = os.path.splitext(event.src_path)[1].lower()
            if file_ext in config.ALLOWED_EXTENSIONS:
                if self._wait_for_file_to_stabilize(event.src_path):
                    self.callback(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            file_ext = os.path.splitext(event.src_path)[1].lower()
            if file_ext in config.ALLOWED_EXTENSIONS:
                self.general_change_callback()

    def on_moved(self, event):
        if not event.is_directory:
             self.general_change_callback()


class Watcher(QObject):
    error = Signal(str)
    finished = Signal()
    new_image_detected = Signal(str)
    scan_folder_changed = Signal()

    def __init__(self, scan_directory):
        super().__init__()
        self.scan_directory = scan_directory
        self.observer = Observer()
        self.event_handler = NewImageHandler(
            callback=self.handle_new_image,
            general_change_callback=self.handle_general_change
        )
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.finished.connect(self.thread.quit)

    @Slot(str)
    def handle_new_image(self, path):
        self.new_image_detected.emit(path)
        
    @Slot()
    def handle_general_change(self):
        self.scan_folder_changed.emit()

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
        """
        Actively stops the running observer to ensure a quick and clean shutdown.
        """
        self._is_stopped = True
        # Actively stop the observer. This will cause its thread to terminate,
        # which in turn allows our QThread's run() method to exit its loop
        # and finish cleanly.
        if hasattr(self, 'observer') and self.observer.is_alive():
            self.observer.stop()


class ImageProcessor(QObject):
    image_loaded = Signal(str, QPixmap)
    processing_complete = Signal(str)
    thumbnail_loaded = Signal(int, str, QPixmap)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._pixmap_cache = OrderedDict()
        self._caching_enabled = True
        self.CACHE_SIZE = 20

    @Slot(bool)
    def set_caching_enabled(self, enabled):
        self._caching_enabled = enabled
        if not enabled:
            self.clear_cache()
            
    def clear_cache(self):
        self._pixmap_cache.clear()

    @Slot(str, bool)
    def request_image_load(self, path, force_reload=False):
        if not path or not os.path.exists(path):
            self.image_loaded.emit(path, QPixmap())
            return
        
        if force_reload and path in self._pixmap_cache:
            del self._pixmap_cache[path]

        if self._caching_enabled and path in self._pixmap_cache:
            self._pixmap_cache.move_to_end(path)
            self.image_loaded.emit(path, self._pixmap_cache[path])
            return

        pil_img = None
        for i in range(5):  # Retry up to 5 times
            try:
                img = Image.open(path)
                img.load()  # Force loading the image data to catch truncation
                pil_img = img
                break  # Success
            except (IOError, OSError) as e:
                if "truncated" in str(e).lower():
                    if i < 4:  # If not the last attempt
                        time.sleep(0.2)  # Wait 200ms and try again
                        continue
                    else:  # Last attempt failed
                        self.error.emit(f"Αποτυχία φόρτωσης εικόνας {os.path.basename(path)}: {e}")
                        self.image_loaded.emit(path, QPixmap())
                        return
                else:  # It's a different kind of error
                    self.error.emit(f"Αποτυχία φόρτωσης εικόνας {os.path.basename(path)}: {e}")
                    self.image_loaded.emit(path, QPixmap())
                    return
        
        if not pil_img:
            self.image_loaded.emit(path, QPixmap())
            return

        try:
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            q_image = ImageQt(pil_img)
            
            pixmap = QPixmap.fromImage(q_image)
            
            if self._caching_enabled:
                self._pixmap_cache[path] = pixmap
                if len(self._pixmap_cache) > self.CACHE_SIZE:
                    self._pixmap_cache.popitem(last=False)

            self.image_loaded.emit(path, pixmap)
        except Exception as e:
            self.error.emit(f"Αποτυχία επεξεργασίας εικόνας {path}: {e}")

    @Slot(str, bool, bool)
    def auto_process_image(self, path, apply_lighting, apply_color):
        # This is now a simple wrapper; the actual processing is in ScanWorker
        # We need a reference to the scan worker to call it, which complicates the design.
        # For this iteration, we will keep the logic here but note it's a candidate for refactoring.
        try:
            with Image.open(path) as original_image:
                image_to_save = original_image.copy().convert('RGB')
                
                scan_worker_ref = ScanWorker(config.load_config()) # Temporary instance

                if apply_lighting:
                    image_to_save = ImageOps.autocontrast(image_to_save, cutoff=0.5)

                if apply_color:
                    image_to_save = scan_worker_ref._correct_color_cast(image_to_save)

                self.create_backup(path)
                image_to_save.save(path)
                if path in self._pixmap_cache: del self._pixmap_cache[path]
                self.processing_complete.emit(path)

        except Exception as e:
            self.error.emit(f"Η αυτόματη επεξεργασία απέτυχε για το {os.path.basename(path)}: {e}")
        
    @Slot(str, int)
    def get_rotated_pixmap(self, path, angle):
        if path in self._pixmap_cache:
            original_pixmap = self._pixmap_cache[path]
        else:
            temp_image = QImage(path)
            if temp_image.isNull(): return
            original_pixmap = QPixmap.fromImage(temp_image)

        transform = QTransform().rotate(angle)
        rotated = original_pixmap.transformed(transform, Qt.SmoothTransformation)
        
        if self._caching_enabled:
            pass
        
        self.image_rotated.emit(path, rotated)


    def create_backup(self, path):
        if not os.path.exists(config.BACKUP_DIR): os.makedirs(config.BACKUP_DIR)
        backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
        if not os.path.exists(backup_path): shutil.copy(path, backup_path)

    @Slot(list)
    def clear_cache_for_paths(self, paths):
        for path in paths:
            if path in self._pixmap_cache:
                del self._pixmap_cache[path]

