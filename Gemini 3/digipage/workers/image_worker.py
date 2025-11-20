import os
import time
from collections import OrderedDict
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QPixmap

class ImageWorker(QObject):
    """
    Background worker responsible for loading images from disk into QPixmaps
    for the UI. Handles caching to improve performance.
    """
    image_loaded = Signal(str, QPixmap)
    error_occurred = Signal(str)

    def __init__(self, caching_enabled=True):
        super().__init__()
        self._cache = OrderedDict()
        self._caching_enabled = caching_enabled
        self.CACHE_LIMIT = 20

    @Slot(bool)
    def set_caching(self, enabled: bool):
        self._caching_enabled = enabled
        if not enabled:
            self._cache.clear()
            
    @Slot()
    def clear_cache(self):
        self._cache.clear()

    @Slot(list)
    def clear_specific_paths(self, paths: list):
        for path in paths:
            if path in self._cache:
                del self._cache[path]

    @Slot(str, bool)
    def load_image(self, path: str, force_reload: bool = False):
        if not path or not os.path.exists(path):
            self.image_loaded.emit(path, QPixmap())
            return
        
        # Cache Hit
        if not force_reload and self._caching_enabled and path in self._cache:
            self._cache.move_to_end(path)
            self.image_loaded.emit(path, self._cache[path])
            return

        # Cache Miss - Load from disk
        try:
            # Retry logic for loading files that might be currently writing
            pil_img = self._safe_open_image(path)
            
            if pil_img:
                if pil_img.mode != "RGBA":
                    pil_img = pil_img.convert("RGBA")
                
                q_image = ImageQt(pil_img)
                pixmap = QPixmap.fromImage(q_image)
                
                if self._caching_enabled:
                    self._cache[path] = pixmap
                    if len(self._cache) > self.CACHE_LIMIT:
                        self._cache.popitem(last=False) # Remove oldest
                
                self.image_loaded.emit(path, pixmap)
            else:
                self.image_loaded.emit(path, QPixmap())

        except Exception as e:
            self.error_occurred.emit(f"Failed to load image {os.path.basename(path)}: {e}")

    def _safe_open_image(self, path):
        for i in range(5):
            try:
                with Image.open(path) as img:
                    img.load()
                    return img.copy()
            except (IOError, OSError):
                time.sleep(0.1)
        return None