import os
import time
import shutil
from collections import OrderedDict
from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtGui import QPixmap, QTransform, QImage
from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt

from ..core import config
from .scan_service import ScanWorker

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
                with Image.open(path) as img:
                    img.load()  # Force loading the image data to catch truncation
                    # Create a copy to ensure the data is in memory after the file handle is closed
                    pil_img = img.copy()
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

        # Note: rotated image isn't cached here to avoid cache pollution with many angles
        # self.image_rotated.emit(path, rotated) # Signal not defined in original code?
        pass


    def create_backup(self, path):
        if not os.path.exists(config.BACKUP_DIR): os.makedirs(config.BACKUP_DIR)
        backup_path = os.path.join(config.BACKUP_DIR, os.path.basename(path))
        if not os.path.exists(backup_path): shutil.copy(path, backup_path)

    @Slot(list)
    def clear_cache_for_paths(self, paths):
        for path in paths:
            if path in self._pixmap_cache:
                del self._pixmap_cache[path]
