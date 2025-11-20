from PySide6.QtWidgets import QHBoxLayout, QFrame
from PySide6.QtCore import Qt
from digipage.ui.modes.base import BaseScanMode
from digipage.ui.viewer.canvas import ImageCanvas
from digipage.workers.image_worker import ImageWorker

class DualScanMode(BaseScanMode):
    """
    Standard mode: Displays two images side-by-side (Left Page, Right Page).
    """
    def __init__(self, image_worker: ImageWorker, parent=None):
        super().__init__(parent)
        self.image_worker = image_worker
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Create two canvases
        self.canvas_l = ImageCanvas()
        self.canvas_r = ImageCanvas()
        
        # Connect signals for rotation/cropping
        self._connect_canvas(self.canvas_l)
        self._connect_canvas(self.canvas_r)

        layout.addWidget(self.create_frame(self.canvas_l))
        layout.addWidget(self.create_frame(self.canvas_r))

    def create_frame(self, canvas):
        f = QFrame()
        f.setStyleSheet("background: transparent; border: 1px solid #444; border-radius: 8px;")
        l = QHBoxLayout(f)
        l.setContentsMargins(0,0,0,0)
        l.addWidget(canvas)
        return f

    def _connect_canvas(self, canvas: ImageCanvas):
        # Connect image loading from worker to canvas
        self.image_worker.image_loaded.connect(
            lambda path, pix: canvas.set_image(path, pix) if canvas.image_path == path else None
        )
        # Connect interaction results back to main window (via base class signal)
        canvas.crop_applied.connect(lambda p, r: self.request_worker_action.emit("crop", (p, r)))
        canvas.rotation_applied.connect(lambda p, a: self.request_worker_action.emit("rotate", (p, a)))

    def refresh_view(self):
        total = len(self.image_files)
        p1 = self.image_files[self.current_index] if self.current_index < total else None
        p2 = self.image_files[self.current_index + 1] if (self.current_index + 1) < total else None

        # Request loads
        self.canvas_l.image_path = p1 # Set immediately so callback checks match
        self.image_worker.load_image(p1)
        
        self.canvas_r.image_path = p2
        self.image_worker.load_image(p2)

        # Update navigation state
        has_prev = self.current_index > 0
        has_next = (self.current_index + 2) < total
        self.update_nav_buttons.emit(has_prev, has_next)
        
        # Update status text
        pg1 = self.current_index + 1
        pg2 = self.current_index + 2
        if p2:
            self.status_message.emit(f"Σελίδες {pg1}-{pg2} από {total}")
        elif p1:
            self.status_message.emit(f"Σελίδα {pg1} από {total}")
        else:
            self.status_message.emit("Αναμονή για εικόνες...")

    def go_next(self):
        if self.current_index + 2 < len(self.image_files):
            self.current_index += 2
            self.refresh_view()

    def go_prev(self):
        if self.current_index > 0:
            self.current_index -= 2
            self.refresh_view()
            
    def go_to_end(self):
        if not self.image_files: return
        # Ensure we land on an even index
        target = len(self.image_files)
        if target % 2 != 0: target -= 1 # Adjust logic as needed for pairing
        # If even count (e.g. 4 items: 0,1,2,3), we want index 2 to show (2,3)
        # If odd count (e.g. 3 items: 0,1,2), we want index 2 to show (2, None)
        step_back = 2 if len(self.image_files) >= 2 else 0
        self.current_index = max(0, len(self.image_files) - (len(self.image_files)%2) - step_back if len(self.image_files) %2 == 0 else len(self.image_files)-1)
        
        # Simplified logic: Just show the last pair
        if len(self.image_files) >= 2:
             self.current_index = len(self.image_files) - 2 if len(self.image_files) % 2 == 0 else len(self.image_files) - 1
        else:
             self.current_index = 0
             
        self.refresh_view()

    def get_current_paths(self):
        paths = []
        if self.canvas_l.image_path: paths.append(self.canvas_l.image_path)
        if self.canvas_r.image_path: paths.append(self.canvas_r.image_path)
        return paths