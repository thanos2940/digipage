from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt
from digipage.ui.modes.base import BaseScanMode
from digipage.ui.viewer.canvas import ImageCanvas
from digipage.workers.image_worker import ImageWorker

class SingleSplitMode(BaseScanMode):
    """
    Single-Shot mode: Displays one image.
    User defines crop boxes, system auto-splits.
    """
    def __init__(self, image_worker: ImageWorker, parent=None):
        super().__init__(parent)
        self.image_worker = image_worker
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Main Viewer
        self.canvas = ImageCanvas()
        # Set default tool to 'crop' (which will be the page splitter handler in this context)
        # For this refactor, we reuse the CropHandler but logically it acts as the splitter definition
        self.canvas.set_mode("crop") 
        
        self.image_worker.image_loaded.connect(
            lambda path, pix: self.canvas.set_image(path, pix) if self.canvas.image_path == path else None
        )
        
        layout.addWidget(self.canvas)

    def handle_new_scan(self, new_path):
        super().handle_new_scan(new_path)
        # In single mode, a new scan triggers automatic processing request
        # We assume the MainWindow/Worker pipeline handles the 'auto-split'
        # This UI just updates to show it.
        self.request_worker_action.emit("auto_split_trigger", new_path)

    def refresh_view(self):
        total = len(self.image_files)
        if not self.image_files:
            self.status_message.emit("No images.")
            self.canvas.set_image(None, None)
            return
            
        path = self.image_files[self.current_index]
        self.canvas.image_path = path
        self.image_worker.load_image(path)
        
        has_prev = self.current_index > 0
        has_next = self.current_index < total - 1
        self.update_nav_buttons.emit(has_prev, has_next)
        self.status_message.emit(f"Image {self.current_index + 1} of {total}")

    def go_next(self):
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.refresh_view()

    def go_prev(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.refresh_view()

    def go_to_end(self):
        if self.image_files:
            self.current_index = len(self.image_files) - 1
            self.refresh_view()

    def get_current_paths(self):
        return [self.canvas.image_path] if self.canvas.image_path else []