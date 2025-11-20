import os
import shutil
import time
import math
import numpy as np
from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, Signal, Slot, QThread, QRect
from PySide6.QtGui import QPixmap, QImage, QTransform, Qt
from collections import OrderedDict

from core.constants import BACKUP_DIR, ALLOWED_EXTENSIONS
from core.config_service import ConfigService

class ImageService(QObject):
    """
    Handles image manipulation (crop, rotate, split, color correction) and loading.
    Combines responsibilities of ScanWorker (manipulation) and ImageProcessor (loading).
    """
    # Change: Emit QImage instead of QPixmap for thread safety
    image_loaded = Signal(str, QImage)
    processing_complete = Signal(str)
    error = Signal(str)
    file_operation_complete = Signal(str, str) # type, path/msg

    def __init__(self):
        super().__init__()
        self._image_cache = OrderedDict() # Cache QImage now
        self.CACHE_SIZE = 20
        self._caching_enabled = True
        self.config_service = ConfigService()

    @Slot(bool)
    def set_caching_enabled(self, enabled):
        self._caching_enabled = enabled
        if not enabled:
            self.clear_cache()

    def clear_cache(self):
        self._image_cache.clear()

    @Slot(list)
    def clear_cache_for_paths(self, paths):
        for path in paths:
            if path in self._image_cache:
                del self._image_cache[path]

    def create_backup(self, path):
        if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(path))
        if not os.path.exists(backup_path): shutil.copy(path, backup_path)

    # --- Loading ---

    @Slot(str, bool)
    def request_image_load(self, path, force_reload=False):
        if not path or not os.path.exists(path):
            self.image_loaded.emit(path, QImage())
            return

        if force_reload and path in self._image_cache:
            del self._image_cache[path]

        if self._caching_enabled and path in self._image_cache:
            self._image_cache.move_to_end(path)
            self.image_loaded.emit(path, self._image_cache[path])
            return

        pil_img = None
        for i in range(5):  # Retry
            try:
                with Image.open(path) as img:
                    img.load()
                    pil_img = img.copy()
                break
            except (IOError, OSError) as e:
                if i < 4:
                    time.sleep(0.2)
                else:
                    self.error.emit(f"Failed to load image {os.path.basename(path)}: {e}")
                    self.image_loaded.emit(path, QImage())
                    return

        if not pil_img:
            self.image_loaded.emit(path, QImage())
            return

        try:
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")

            # Convert PIL to QImage directly
            q_image = ImageQt(pil_img).copy() # Ensure deep copy for QImage

            if self._caching_enabled:
                self._image_cache[path] = q_image
                if len(self._image_cache) > self.CACHE_SIZE:
                    self._image_cache.popitem(last=False)

            self.image_loaded.emit(path, q_image)
        except Exception as e:
            self.error.emit(f"Failed to process image {path}: {e}")


    # --- Manipulation ---

    def _correct_color_cast(self, image):
        img_array = np.array(image.convert('RGB'), dtype=np.float32)
        r_white = np.percentile(img_array[:, :, 0], 99.5)
        g_white = np.percentile(img_array[:, :, 1], 99.5)
        b_white = np.percentile(img_array[:, :, 2], 99.5)

        avg_white_point = (r_white + g_white + b_white) / 3.0
        if avg_white_point < 180: return image

        r_scale = 255.0 / r_white if r_white > 0 else 1.0
        g_scale = 255.0 / g_white if g_white > 0 else 1.0
        b_scale = 255.0 / b_white if b_white > 0 else 1.0

        img_array[:, :, 0] *= r_scale
        img_array[:, :, 1] *= g_scale
        img_array[:, :, 2] *= b_scale
        np.clip(img_array, 0, 255, out=img_array)
        return Image.fromarray(img_array.astype(np.uint8), 'RGB')

    @Slot(str, QRect)
    def crop_and_save_image(self, path, crop_rect):
        try:
            self.create_backup(path)
            with Image.open(path) as img:
                cropped_img = img.crop((
                    crop_rect.x(), crop_rect.y(),
                    crop_rect.x() + crop_rect.width(),
                    crop_rect.y() + crop_rect.height()
                ))
                cropped_img.save(path)
            self.file_operation_complete.emit("crop", path)
        except Exception as e:
            self.error.emit(f"Crop failed: {e}")

    @Slot(str, float)
    def rotate_crop_and_save(self, path, angle):
        try:
            self.create_backup(path)
            with Image.open(path) as img:
                original_width, original_height = img.size
                angle_rad = math.radians(angle)
                w, h = original_width, original_height
                cosa = abs(math.cos(angle_rad))
                sina = abs(math.sin(angle_rad))
                zoom_factor = max(
                    cosa + (h / w) * sina if w > 0 else 1,
                    (w / h) * sina + cosa if h > 0 else 1
                )

                rotated_img = img.rotate(-angle, resample=Image.BICUBIC, expand=True)
                new_size = (int(rotated_img.width * zoom_factor), int(rotated_img.height * zoom_factor))
                zoomed_rotated_img = rotated_img.resize(new_size, Image.Resampling.LANCZOS)

                left = (zoomed_rotated_img.width - original_width) / 2
                top = (zoomed_rotated_img.height - original_height) / 2
                final_img = zoomed_rotated_img.crop((left, top, left + original_width, top + original_height))
                final_img.save(path)

            self.file_operation_complete.emit("rotate", path)
        except Exception as e:
            self.error.emit(f"Rotate failed: {e}")

    @Slot(str)
    def correct_color_and_save(self, path):
        try:
            self.create_backup(path)
            with Image.open(path) as img:
                corrected_img = self._correct_color_cast(img)
                corrected_img.save(path)
            self.file_operation_complete.emit("color_fix", path)
        except Exception as e:
            self.error.emit(f"Color fix failed: {e}")

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
            self.error.emit(f"Split failed: {e}")

    @Slot(str, dict)
    def perform_page_split(self, source_path, layout_data):
        try:
            scan_folder = os.path.dirname(source_path)
            final_folder = os.path.join(scan_folder, 'final')
            os.makedirs(final_folder, exist_ok=True)

            with Image.open(source_path) as img:
                w, h = img.size

                def get_abs_rect(ratios):
                    return (
                        int(ratios['x'] * w), int(ratios['y'] * h),
                        int(ratios['x'] * w) + int(ratios['w'] * w),
                        int(ratios['y'] * h) + int(ratios['h'] * h)
                    )

                base, ext = os.path.splitext(os.path.basename(source_path))
                left_out_path = os.path.join(final_folder, f"{base}_L{ext}")
                right_out_path = os.path.join(final_folder, f"{base}_R{ext}")

                if layout_data.get('left_enabled', True):
                    img.crop(get_abs_rect(layout_data['left'])).save(left_out_path)
                elif os.path.exists(left_out_path):
                    os.remove(left_out_path)

                if layout_data.get('right_enabled', True):
                    img.crop(get_abs_rect(layout_data['right'])).save(right_out_path)
                elif os.path.exists(right_out_path):
                    os.remove(right_out_path)

            self.file_operation_complete.emit("page_split", source_path)

        except Exception as e:
            self.error.emit(f"Page split failed: {e}")
