import sys
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QApplication, QFrame, QVBoxLayout, QPushButton
import time
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QRectF
from PIL import Image
from .utils import pil_to_qpixmap
from .crop_rect_item import CropRectItem

class PhotoViewer(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        print("[PhotoViewer] Initializing...")
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.setScene(self._scene)

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        self.image_path = None
        self.pil_image = None
        self.rotation_angle = 0

        self.is_crop_mode = False
        self.crop_rect_item = None
        self.handle_drag_info = {}

    def set_image(self, path: str, timeout_ms=2000):
        """
        Load and display an image from a file path using Pillow, with a retry mechanism.
        """
        self.clear() # Clear previous image first
        self.image_path = path

        retry_delay_ms = 50
        max_retries = int(timeout_ms / retry_delay_ms) if timeout_ms > 0 else 1

        for i in range(max_retries):
            try:
                # Try to open and verify the image
                img_temp = Image.open(path)
                img_temp.verify()

                # If verify() is successful, re-open the image to work with it
                self.pil_image = Image.open(path)
                pixmap = pil_to_qpixmap(self.pil_image)

                if not pixmap.isNull():
                    self._pixmap_item.setPixmap(pixmap)
                    self.fit_view()
                    return # Success
            except Exception as e:
                # If it fails, wait and retry
                print(f"Attempt {i+1} failed for {path}: {e}. Retrying...")
                time.sleep(retry_delay_ms / 1000)

        # If all retries fail, print an error and ensure the view is clear
        print(f"Error loading image {path} after {timeout_ms}ms. Could not identify image file.")
        self.clear()


    def clear(self):
        """Clears the view."""
        self._pixmap_item.setPixmap(QPixmap())
        self.image_path = None
        self.rotation_angle = 0
        if self.pil_image:
            self.pil_image.close()
            self.pil_image = None

    def update_pixmap(self, pil_img: Image.Image):
        """Updates the pixmap item with a new Pillow image."""
        pixmap = pil_to_qpixmap(pil_img)
        self._pixmap_item.setPixmap(pixmap)

    def rotate_image(self, angle_degrees: float):
        """Rotates the displayed image by the given angle."""
        if not self.pil_image:
            return

        self.rotation_angle = (self.rotation_angle + angle_degrees) % 360

        # Use high-quality resampling for the rotation
        rotated_image = self.pil_image.rotate(
            self.rotation_angle,
            resample=Image.Resampling.BICUBIC,
            expand=True
        )
        self.update_pixmap(rotated_image)

    def wheelEvent(self, event):
        """Zoom in or out using the mouse wheel."""
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor

        # Save the scene pos
        old_pos = self.mapToScene(event.position().toPoint())

        # Zoom
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
        self.scale(zoom_factor, zoom_factor)

        # Get the new position
        new_pos = self.mapToScene(event.position().toPoint())

        # Move scene to old position
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    def fit_view(self):
        """Fits the image to the view, preserving aspect ratio."""
        if self._pixmap_item.pixmap():
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        """Handle resize events to keep the image fitted."""
        super().resizeEvent(event)
        self.fit_view()

    def toggle_crop_mode(self):
        self.is_crop_mode = not self.is_crop_mode

        if self.is_crop_mode and self._pixmap_item.pixmap():
            if not self.crop_rect_item:
                self.crop_rect_item = CropRectItem()
                self._scene.addItem(self.crop_rect_item)

            # Set rect to the bounds of the image in the scene
            self.crop_rect_item.setRect(self._pixmap_item.boundingRect())
            self.crop_rect_item.setVisible(True)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        elif self.crop_rect_item:
            self.crop_rect_item.setVisible(False)
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        return self.is_crop_mode

    def apply_crop(self):
        if not self.is_crop_mode or not self.crop_rect_item or not self.pil_image:
            return None

        crop_rect_in_pixmap = self.crop_rect_item.get_crop_coords_in_pixmap(self._pixmap_item)

        # The crop rect is in the original pixmap's coordinate space.
        # We need to account for any rotation before cropping.
        # A common approach is to crop the *original* un-rotated image.

        # Get the original image dimensions
        original_w, original_h = self.pil_image.size

        # Get the bounding rect of the displayed pixmap (which could be rotated)
        pixmap_w = self._pixmap_item.pixmap().width()
        pixmap_h = self._pixmap_item.pixmap().height()

        # Simple case: if not rotated, the mapping is direct.
        # For a rotated image, the logic is more complex. For now, assume we crop the original.
        if self.rotation_angle == 0:
            # Map crop coordinates from pixmap space to original image space
            # This can be a simple ratio mapping if the aspect ratio is maintained.
            x_ratio = original_w / pixmap_w
            y_ratio = original_h / pixmap_h

            crop_x = int(crop_rect_in_pixmap.x() * x_ratio)
            crop_y = int(crop_rect_in_pixmap.y() * y_ratio)
            crop_w = int(crop_rect_in_pixmap.width() * x_ratio)
            crop_h = int(crop_rect_in_pixmap.height() * y_ratio)

            cropped_pil = self.pil_image.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
            return cropped_pil
        else:
            # TODO: Handle cropping on a rotated image. This is non-trivial.
            # For now, we return None to indicate failure.
            print("Cropping on a rotated image is not yet implemented.")
            return None

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Create a main window to hold the viewer
    main_win = QWidget()
    main_win.setWindowTitle("Photo Viewer Test")
    main_win.setGeometry(100, 100, 800, 600)

    layout = QVBoxLayout(main_win)
    viewer = PhotoViewer()
    layout.addWidget(viewer)

    # A button to test loading an image
    btn = QPushButton("Load Image (replace with a valid path)")
    def load_test_image():
        # IMPORTANT: Replace this with a path to an actual image on your system for testing
        # For example: "C:/Users/YourUser/Pictures/test.jpg" or "/home/user/Pictures/test.png"
        test_image_path = "test.jpg" # Replace this!
        import os
        if os.path.exists(test_image_path):
            viewer.set_image(test_image_path)
        else:
            print(f"Test image not found at: {test_image_path}. Please update the path in photo_viewer.py")

    btn.clicked.connect(load_test_image)
    layout.addWidget(btn)

    main_win.show()
    sys.exit(app.exec())
