from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, Signal, QSize
from PySide6.QtGui import QPixmap, QPainter, QImage, QColor, QPen, QBrush, QTransform
from PySide6.QtWidgets import QWidget, QApplication
from PIL import Image, ImageQt

class ImageViewer(QWidget):
    """
    A custom widget for displaying and interacting with an image.
    Supports panning, zooming, and cropping.
    """
    # Signal to request a preview for a heavy operation
    preview_requested = Signal(object, dict) # e.g., (Pillow.Image, {"rotate": 45})
    # Signal to indicate the view has changed (pan, zoom)
    view_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setBackgroundRole(QColor("black"))

        # --- Image State ---
        self.base_image: Image.Image = None
        self.display_pixmap: QPixmap = None

        # --- Transformation State ---
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.rotation_angle = 0

        # --- Interaction State ---
        self.last_mouse_pos = QPoint()
        self.is_panning = False

        # --- Cropping State ---
        self.is_cropping = False
        self.crop_rect = QRect()
        self.crop_handles = {}
        self._dragging_handle = None
        self._dragging_rect = False

    # --- Public API ---

    def load_image(self, file_path: str):
        """Loads an image from a file path and resets the view."""
        try:
            self.base_image = Image.open(file_path)
            self.display_pixmap = self.image_to_pixmap(self.base_image)
            self.reset_view()
            self.update()
            return True
        except Exception as e:
            print(f"Error loading image {file_path}: {e}")
            self.base_image = None
            self.display_pixmap = None
            self.update()
            return False

    def set_cropping_mode(self, enabled: bool):
        """Enables or disables cropping mode."""
        self.is_cropping = enabled
        if enabled and self.display_pixmap:
            # Initialize crop rect to be 80% of the image size, centered
            img_rect = self.display_pixmap.rect()
            w, h = int(img_rect.width() * 0.8), int(img_rect.height() * 0.8)
            x, y = int((img_rect.width() - w) / 2), int((img_rect.height() - h) / 2)
            self.crop_rect = QRect(x, y, w, h)
        self.update()

    def reset_view(self):
        """Resets zoom, pan, and rotation to fit the image in the widget."""
        if not self.display_pixmap:
            return

        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.rotation_angle = 0
        self.fit_to_window()
        self.update()

    # --- Event Handlers ---

    def paintEvent(self, event):
        """Renders the image and cropping UI."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if not self.display_pixmap:
            painter.drawText(self.rect(), Qt.AlignCenter, "No Image Loaded")
            return

        # Center the pixmap in the widget
        widget_center = self.rect().center()

        # Apply pan offset
        draw_center = widget_center + self.pan_offset

        # Calculate the target rectangle for drawing
        current_w = self.display_pixmap.width() * self.zoom_factor
        current_h = self.display_pixmap.height() * self.zoom_factor
        target_rect = QRectF(
            draw_center.x() - current_w / 2,
            draw_center.y() - current_h / 2,
            current_w, current_h
        )

        painter.drawPixmap(target_rect, self.display_pixmap, self.display_pixmap.rect())

        if self.is_cropping:
            self.draw_cropping_ui(painter, target_rect)

    def draw_cropping_ui(self, painter, target_rect):
        """Draws the cropping rectangle and handles."""
        painter.save()

        # Convert crop_rect (in image coords) to widget coords
        scale_x = target_rect.width() / self.display_pixmap.width()
        scale_y = target_rect.height() / self.display_pixmap.height()

        display_crop_rect = QRectF(
            target_rect.left() + self.crop_rect.left() * scale_x,
            target_rect.top() + self.crop_rect.top() * scale_y,
            self.crop_rect.width() * scale_x,
            self.crop_rect.height() * scale_y
        ).normalized()

        # Draw semi-transparent overlay outside the crop rect
        path = QPainterPath()
        path.addRect(target_rect)
        path.addRect(display_crop_rect)
        painter.fillPath(path, QColor(0, 0, 0, 128))

        # Draw crop rect border
        pen = QPen(QColor("#5A9BD5"), 2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(display_crop_rect)

        # Draw handles
        handle_size = 8
        self.crop_handles = self.get_handle_rects(display_crop_rect, handle_size)
        painter.setBrush(QColor("#5A9BD5"))
        for handle in self.crop_handles.values():
            painter.drawRect(handle)

        painter.restore()

    def wheelEvent(self, event):
        """Handles zooming with the mouse wheel."""
        if not self.display_pixmap:
            return

        delta = event.angleDelta().y()
        zoom_factor_change = 1.2 if delta > 0 else 1 / 1.2

        old_zoom = self.zoom_factor
        self.zoom_factor *= zoom_factor_change

        # Zoom towards the mouse cursor
        mouse_pos = event.position()
        widget_center = self.rect().center()

        # Vector from widget center to mouse pos
        center_to_mouse = mouse_pos - widget_center

        # Adjust pan offset to keep the point under the cursor stationary
        self.pan_offset = mouse_pos - widget_center - (center_to_mouse - self.pan_offset) * zoom_factor_change

        self.update()
        self.view_changed.emit()

    def mousePressEvent(self, event):
        self.last_mouse_pos = event.position()
        if event.button() == Qt.LeftButton:
            if self.is_cropping:
                self._dragging_handle = self.get_handle_at(event.position())
                if self._dragging_handle:
                    return

                # Convert crop_rect to widget coords to check for move
                display_crop_rect = self.image_to_widget_rect(self.crop_rect)
                if display_crop_rect.contains(event.position()):
                    self._dragging_rect = True
                    return

            # If not cropping, or clicked outside crop UI, start panning
            self.is_panning = True
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        delta = QPointF(event.position() - self.last_mouse_pos)

        if self._dragging_handle:
            self.resize_crop_rect(delta)
        elif self._dragging_rect:
            self.move_crop_rect(delta)
        elif self.is_panning:
            self.pan_offset += delta
            self.update()
            self.view_changed.emit()

        self.last_mouse_pos = event.position()

    def mouseReleaseEvent(self, event):
        self.is_panning = False
        self._dragging_handle = None
        self._dragging_rect = False
        self.setCursor(Qt.ArrowCursor)

    def resizeEvent(self, event):
        """Handle widget resizing."""
        self.fit_to_window()
        super().resizeEvent(event)

    # --- Helper Methods ---

    def fit_to_window(self):
        """Adjusts zoom to fit the image within the widget."""
        if not self.display_pixmap:
            return

        w_ratio = self.width() / self.display_pixmap.width()
        h_ratio = self.height() / self.display_pixmap.height()
        self.zoom_factor = min(w_ratio, h_ratio) * 0.98 # Add a small margin
        self.pan_offset = QPointF(0, 0) # Recenter
        self.update()
        self.view_changed.emit()

    def image_to_pixmap(self, image: Image.Image) -> QPixmap:
        """Converts a Pillow Image to a QPixmap."""
        return QPixmap.fromImage(ImageQt.toqimage(image))

    def widget_to_image_coords(self, widget_pos: QPointF) -> QPointF:
        """Converts widget coordinates to image coordinates."""
        if not self.display_pixmap: return QPointF()

        widget_center = self.rect().center()
        draw_center = widget_center + self.pan_offset

        pixmap_w = self.display_pixmap.width() * self.zoom_factor
        pixmap_h = self.display_pixmap.height() * self.zoom_factor

        top_left_in_widget = draw_center - QPointF(pixmap_w / 2, pixmap_h / 2)

        relative_pos = widget_pos - top_left_in_widget

        image_x = (relative_pos.x() / pixmap_w) * self.display_pixmap.width()
        image_y = (relative_pos.y() / pixmap_h) * self.display_pixmap.height()

        return QPointF(image_x, image_y)

    def image_to_widget_rect(self, image_rect: QRect) -> QRectF:
        """Converts a QRect in image coordinates to widget coordinates."""
        if not self.display_pixmap: return QRectF()

        widget_center = self.rect().center()
        draw_center = widget_center + self.pan_offset

        pixmap_w = self.display_pixmap.width() * self.zoom_factor
        pixmap_h = self.display_pixmap.height() * self.zoom_factor

        top_left_in_widget = draw_center - QPointF(pixmap_w / 2, pixmap_h / 2)

        scale_x = pixmap_w / self.display_pixmap.width()
        scale_y = pixmap_h / self.display_pixmap.height()

        return QRectF(
            top_left_in_widget.x() + image_rect.left() * scale_x,
            top_left_in_widget.y() + image_rect.top() * scale_y,
            image_rect.width() * scale_x,
            image_rect.height() * scale_y
        )

    def get_handle_rects(self, rect: QRectF, size: int) -> dict:
        """Calculates the positions of the 8 resize handles."""
        s2 = size / 2
        return {
            "top_left": QRectF(rect.topLeft() - QPointF(s2, s2), QSizeF(size, size)),
            "top_right": QRectF(rect.topRight() - QPointF(s2, s2), QSizeF(size, size)),
            "bottom_left": QRectF(rect.bottomLeft() - QPointF(s2, s2), QSizeF(size, size)),
            "bottom_right": QRectF(rect.bottomRight() - QPointF(s2, s2), QSizeF(size, size)),
            "top": QRectF(QPointF(rect.center().x() - s2, rect.top() - s2), QSizeF(size, size)),
            "bottom": QRectF(QPointF(rect.center().x() - s2, rect.bottom() - s2), QSizeF(size, size)),
            "left": QRectF(QPointF(rect.left() - s2, rect.center().y() - s2), QSizeF(size, size)),
            "right": QRectF(QPointF(rect.right() - s2, rect.center().y() - s2), QSizeF(size, size)),
        }

    def get_handle_at(self, pos: QPointF) -> str:
        """Finds which handle is at a given widget position."""
        for name, rect in self.crop_handles.items():
            if rect.contains(pos):
                return name
        return None

    def move_crop_rect(self, delta: QPointF):
        """Moves the crop rectangle by a delta in widget coordinates."""
        # Convert widget delta to image delta
        scale_x = self.display_pixmap.width() / (self.display_pixmap.width() * self.zoom_factor)
        scale_y = self.display_pixmap.height() / (self.display_pixmap.height() * self.zoom_factor)

        self.crop_rect.translate(int(delta.x() * scale_x), int(delta.y() * scale_y))

        # Clamp to image boundaries
        self.crop_rect = self.crop_rect.intersected(self.display_pixmap.rect())
        self.update()

    def resize_crop_rect(self, delta: QPointF):
        """Resizes the crop rectangle based on which handle is being dragged."""
        # Convert widget delta to image delta
        scale_x = self.display_pixmap.width() / (self.display_pixmap.width() * self.zoom_factor)
        scale_y = self.display_pixmap.height() / (self.display_pixmap.height() * self.zoom_factor)

        dx = delta.x() * scale_x
        dy = delta.y() * scale_y

        if "top" in self._dragging_handle: self.crop_rect.setTop(self.crop_rect.top() + dy)
        if "bottom" in self._dragging_handle: self.crop_rect.setBottom(self.crop_rect.bottom() + dy)
        if "left" in self._dragging_handle: self.crop_rect.setLeft(self.crop_rect.left() + dx)
        if "right" in self._dragging_handle: self.crop_rect.setRight(self.crop_rect.right() + dx)

        # Clamp to image boundaries
        self.crop_rect = self.crop_rect.intersected(self.display_pixmap.rect()).normalized()
        self.update()
