import os
import time
import shutil
import re
import json
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

# Define common image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif'}
BACKUP_DIR = "digipage_backups"
BOOKS_COMPLETE_LOG_FILE = "books_complete_log.json"

class ScanWorker(QObject):
    """
    A QObject worker for performing scans, calculations, and file operations in a background thread.
    """
    # --- Signals ---
    initial_scan_complete = Signal(list)
    stats_updated = Signal(dict)
    error = Signal(str)
    operation_successful = Signal(str, str) # message, operation_type
    file_operation_finished = Signal()      # To trigger a rescan/UI update
    standard_calculated = Signal(dict)      # To send back calculated lighting standard metrics

    def _ensure_backup_dir(self):
        """Creates the backup directory if it doesn't exist."""
        os.makedirs(BACKUP_DIR, exist_ok=True)

    def _create_backup(self, file_path):
        """Creates a backup of a single file if one doesn't already exist."""
        if not os.path.exists(file_path): return
        self._ensure_backup_dir()
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(file_path))
        if not os.path.exists(backup_path):
            shutil.copy(file_path, backup_path)

    # --- Core Slots ---
    @Slot(str)
    def perform_initial_scan(self, scan_folder: str):
        """Scans the target folder for existing image files and emits the result."""
        try:
            if not os.path.isdir(scan_folder):
                raise FileNotFoundError(f"Scan folder not found: {scan_folder}")
            files = [os.path.join(scan_folder, f) for f in os.listdir(scan_folder) if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]
            files.sort()
            self.initial_scan_complete.emit(files)
        except Exception as e:
            self.error.emit(f"Error during initial scan: {e}")

    @Slot(str)
    def calculate_today_stats(self, today_books_folder: str):
        """Calculates statistics about the work done today."""
        # This implementation remains the same as before.
        try:
            if not os.path.isdir(today_books_folder):
                raise FileNotFoundError(f"Today's books folder not found: {today_books_folder}")
            staged_books = [d for d in os.listdir(today_books_folder) if os.path.isdir(os.path.join(today_books_folder, d))]
            total_pages = sum(len([f for f in os.listdir(os.path.join(today_books_folder, book)) if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]) for book in staged_books)
            stats = {"staged_books": len(staged_books), "total_pages_today": total_pages}
            self.stats_updated.emit(stats)
        except Exception as e:
            self.error.emit(f"Error calculating stats: {e}")

    # --- New File Operation Slots ---
    @Slot(list)
    def delete_files(self, file_paths: list):
        try:
            for path in file_paths:
                if os.path.exists(path):
                    self._create_backup(path)
                    os.remove(path)
            basenames = [os.path.basename(p) for p in file_paths]
            self.operation_successful.emit(f"Deleted: {', '.join(basenames)}", "delete")
        except Exception as e:
            self.error.emit(f"Delete failed: {e}")
        finally:
            self.file_operation_finished.emit()

    @Slot(str, str, str)
    def create_book(self, book_name: str, scan_folder: str, today_books_folder: str):
        try:
            new_book_path = os.path.join(today_books_folder, book_name)
            if os.path.exists(new_book_path):
                raise FileExistsError(f"Book '{book_name}' already exists.")
            os.makedirs(new_book_path)
            scanned_files = [os.path.join(scan_folder, f) for f in os.listdir(scan_folder) if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]
            if not scanned_files:
                self.operation_successful.emit("No scans in folder, empty book created.", "create_book")
                return
            for file_path in scanned_files:
                shutil.move(file_path, new_book_path)
            self.operation_successful.emit(f"Book '{book_name}' created with {len(scanned_files)} pages.", "create_book")
        except Exception as e:
            self.error.emit(f"Create book failed: {e}")
        finally:
            self.file_operation_finished.emit()

    @Slot(str, dict)
    def apply_and_save_operations(self, file_path: str, operations: dict):
        """Applies a dictionary of operations to an image and saves it."""
        try:
            self._create_backup(file_path)
            with Image.open(file_path) as img:
                img = img.convert("RGB")
                if "contrast" in operations and operations["contrast"] != 1.0:
                    img = ImageEnhance.Contrast(img).enhance(operations["contrast"])
                if "brightness" in operations and operations["brightness"] != 1.0:
                    img = ImageEnhance.Brightness(img).enhance(operations["brightness"])
                if "rotation" in operations and operations["rotation"] != 0:
                    img = img.rotate(operations["rotation"], resample=Image.Resampling.BICUBIC, expand=True)
                if "sharpen" in operations and operations["sharpen"]:
                    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))
                if "crop" in operations and operations["crop"]:
                    crop_rect = operations["crop"]
                    if crop_rect.width() > 0 and crop_rect.height() > 0:
                        img = img.crop((crop_rect.left(), crop_rect.top(), crop_rect.right(), crop_rect.bottom()))
                img.save(file_path, quality=95)
            self.operation_successful.emit(f"Saved changes to {os.path.basename(file_path)}", "save")
        except Exception as e:
            self.error.emit(f"Save failed: {e}")
        finally:
            self.file_operation_finished.emit()

    @Slot(str, float)
    def split_image(self, file_path: str, ratio: float):
        try:
            self._create_backup(file_path)
            with Image.open(file_path) as img:
                img_w, img_h = img.size
                split_x = int(img_w * ratio)
                if not (0 < split_x < img_w): raise ValueError("Split is out of bounds.")
                left_image = img.crop((0, 0, split_x, img_h))
                right_image = img.crop((split_x, 0, img_w, img_h))
                base_name, ext = os.path.splitext(file_path)
                right_path = f"{base_name}_split{ext}"
                right_image.save(right_path, quality=95)
                left_image.save(file_path, quality=95)
            self.operation_successful.emit(f"Split {os.path.basename(file_path)}", "split")
        except Exception as e:
            self.error.emit(f"Split failed: {e}")
        finally:
            self.file_operation_finished.emit()

    @Slot(str)
    def restore_from_backup(self, file_path: str):
        try:
            backup_path = os.path.join(BACKUP_DIR, os.path.basename(file_path))
            if not os.path.exists(backup_path):
                raise FileNotFoundError("No backup found for this file.")
            shutil.copy(backup_path, file_path)
            self.operation_successful.emit(f"Restored {os.path.basename(file_path)} from backup.", "restore")
        except Exception as e:
            self.error.emit(f"Restore failed: {e}")
        finally:
            self.file_operation_finished.emit()

    @Slot(dict, str)
    def transfer_books_to_data(self, city_paths: dict, todays_books_folder: str):
        try:
            book_folders = [d for d in os.listdir(todays_books_folder) if os.path.isdir(os.path.join(todays_books_folder, d))]
            if not book_folders:
                self.operation_successful.emit("No books to transfer.", "transfer")
                return

            code_pattern = re.compile(r'-(\d{3})-')
            log_data = {}
            if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
                with open(BOOKS_COMPLETE_LOG_FILE, 'r') as f: log_data = json.load(f)
            today_str = datetime.now().strftime('%Y-%m-%d')
            if today_str not in log_data: log_data[today_str] = []

            moved_count = 0
            for book_name in book_folders:
                match = code_pattern.search(book_name)
                if not match: continue
                city_code = match.group(1)
                city_path = city_paths.get(city_code)
                if not city_path or not os.path.isdir(city_path): continue

                destination_folder = os.path.join(city_path, datetime.now().strftime('%d-%m'))
                os.makedirs(destination_folder, exist_ok=True)
                source_path = os.path.join(todays_books_folder, book_name)
                page_count = len([f for f in os.listdir(source_path) if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS])
                shutil.move(source_path, os.path.join(destination_folder, book_name))
                log_data[today_str].append({"name": book_name, "pages": page_count, "timestamp": datetime.now().isoformat()})
                moved_count += 1

            with open(BOOKS_COMPLETE_LOG_FILE, 'w') as f: json.dump(log_data, f, indent=4)
            self.operation_successful.emit(f"Transferred {moved_count} books.", "transfer")
        except Exception as e:
            self.error.emit(f"Transfer failed: {e}")
        finally:
            self.file_operation_finished.emit()

    @Slot(str)
    def calculate_lighting_standard(self, reference_folder: str):
        try:
            if not os.path.isdir(reference_folder):
                raise FileNotFoundError("Reference folder not found.")

            image_files = [os.path.join(reference_folder, f) for f in os.listdir(reference_folder) if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]
            if not image_files:
                raise FileNotFoundError("No images found in the reference folder.")

            # Create the template image
            pil_images = [Image.open(p).convert('RGB') for p in image_files]
            target_size = pil_images[0].size
            resized_images_np = [np.array(img.resize(target_size, Image.Resampling.LANCZOS)) for img in pil_images]
            avg_image_array = np.mean(np.array(resized_images_np), axis=0).astype(np.uint8)
            template_image = Image.fromarray(avg_image_array, 'RGB')
            template_path = "_template.png"
            template_image.save(template_path)

            # Calculate metrics
            total_brightness, total_contrast, valid_count = 0, 0, 0
            for img in pil_images:
                gray_img = img.convert('L')
                img_array = np.array(gray_img)
                total_brightness += np.mean(img_array)
                total_contrast += np.std(img_array)
                valid_count += 1

            avg_brightness = total_brightness / valid_count
            avg_contrast = total_contrast / valid_count

            metrics = {
                'brightness': avg_brightness,
                'contrast': avg_contrast,
                'histogram_template_path': template_path
            }
            self.standard_calculated.emit(metrics)
        except Exception as e:
            self.error.emit(f"Failed to calculate standard: {e}")

    @Slot(str, dict)
    def auto_correct_image(self, file_path: str, corrections: dict):
        try:
            self._create_backup(file_path)
            with Image.open(file_path) as img:
                img = img.convert("RGB")

                if corrections.get("lighting"):
                    from PIL import ImageOps
                    img = ImageOps.autocontrast(img, cutoff=0.5)

                if corrections.get("color"):
                    img_array = np.array(img, dtype=np.float32)
                    for i in range(3): # R, G, B channels
                        percentile = np.percentile(img_array[:, :, i], 99.5)
                        if percentile > 0:
                            scale = 255.0 / percentile
                            img_array[:, :, i] *= scale
                    img = Image.fromarray(np.clip(img_array, 0, 255).astype('uint8'), 'RGB')

                if corrections.get("sharpen"):
                    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))

                img.save(file_path, quality=95)
            self.operation_successful.emit(f"Auto-corrected {os.path.basename(file_path)}", "auto_correct")
        except Exception as e:
            self.error.emit(f"Auto-correction failed for {os.path.basename(file_path)}: {e}")
        finally:
            self.file_operation_finished.emit()


class _NewImageHandler(FileSystemEventHandler, QObject):
    """
    A handler for watchdog that emits a Qt signal when a new image is created.
    Inherits from QObject to handle signals properly across threads.
    """
    new_image_detected = Signal(str)

    def __init__(self):
        FileSystemEventHandler.__init__(self)
        QObject.__init__(self)

    def on_created(self, event):
        if not event.is_directory and os.path.splitext(event.src_path)[1].lower() in IMAGE_EXTENSIONS:
            time.sleep(0.1)
            self.new_image_detected.emit(event.src_path)

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
        self.handler.new_image_detected.connect(self.new_image_detected)

    @Slot()
    def start_watching(self):
        if not os.path.isdir(self.path_to_watch):
            self.error.emit(f"Cannot watch invalid directory: {self.path_to_watch}")
            return
        self.observer.schedule(self.handler, self.path_to_watch, recursive=False)
        self.observer.start()

    @Slot()
    def stop_watching(self):
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
