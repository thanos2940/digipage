from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal

class ImageViewer(QWidget):
    """
    A custom widget for displaying and interacting with images.
    Handles loading, displaying, scaling, panning, and cropping.
    """
    # Signal emitted when a change is made that might require a backup
    change_occurred = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 200)

        # Image and display state
        self.image_path = None
        self.pixmap = QPixmap()
        self.scaled_pixmap = QPixmap()
        self.rotation_angle = 0

        # Interaction state
        self.is_panning = False
        self.is_cropping = False
        self.last_mouse_pos = QPoint()
        self.pan_offset = QPoint()

        # Zoom state
        self.zoom_factor = 1.0

        # Cropping state
        self.crop_rect_widget = QRect() # Crop rect in widget coordinates
        self.crop_handles = {}
        self.active_handle = None

    def load_image(self, path):
        """Loads an image from a file path."""
        if not path:
            self.pixmap = QPixmap()
        else:
            self.pixmap = QPixmap(path)

        self.image_path = path
        self.reset_view()

    def reset_view(self):
        """Resets all transformations (zoom, pan, crop, rotation)."""
        self.rotation_angle = 0
        self.zoom_factor = 1.0
        self.pan_offset = QPoint()
        self.is_cropping = False
        self.crop_rect_widget = QRect()
        self._update_scaled_pixmap()
        self.update()

    def apply_rotation(self, angle):
        """Applies a rotation to the base pixmap."""
        if self.pixmap.isNull():
            return

        self.rotation_angle = (self.rotation_angle + angle) % 360
        transform = QTransform().rotate(self.rotation_angle)
        # Reloading from path is safer to avoid cumulative degradation
        self.pixmap = QPixmap(self.image_path).transformed(transform)

        self._update_scaled_pixmap()
        self.update()
        self.change_occurred.emit()

    def set_cropping_mode(self, enabled):
        """Toggles cropping mode."""
        if self.pixmap.isNull():
            return

        self.is_cropping = enabled
        if enabled:
            # Initialize crop rect to the full scaled image area
            pixmap_rect = self._get_pixmap_rect_in_widget()
            self.crop_rect_widget = pixmap_rect
            self._update_crop_handles()
        self.update()

    def get_crop_coords(self):
        """
        Converts the widget-space crop rectangle to image-space coordinates.
        Returns a QRect of the area to be cropped from the original image.
        """
        if self.pixmap.isNull() or self.crop_rect_widget.isNull():
            return None

        pixmap_rect_in_widget = self._get_pixmap_rect_in_widget()
        if pixmap_rect_in_widget.width() == 0 or pixmap_rect_in_widget.height() == 0:
            return None

        # Calculate scales
        scale_x = self.pixmap.width() / pixmap_rect_in_widget.width()
        scale_y = self.pixmap.height() / pixmap_rect_in_widget.height()

        # Top-left corner of the crop rect relative to the pixmap rect
        rel_x = self.crop_rect_widget.x() - pixmap_rect_in_widget.x()
        rel_y = self.crop_rect_widget.y() - pixmap_rect_in_widget.y()

        # Scale up to original image coordinates
        img_x = int(rel_x * scale_x)
        img_y = int(rel_y * scale_y)
        img_w = int(self.crop_rect_widget.width() * scale_x)
        img_h = int(self.crop_rect_widget.height() * scale_y)

        return QRect(img_x, img_y, img_w, img_h)

    # --- Protected Methods and Event Handlers ---

    def paintEvent(self, event):
        """Draws the scaled pixmap and cropping UI."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.scaled_pixmap.isNull():
            painter.drawText(self.rect(), Qt.AlignCenter, "No Image")
            return

        # Draw the pixmap centered in the widget
        pixmap_rect = self._get_pixmap_rect_in_widget()
        painter.drawPixmap(pixmap_rect.topLeft(), self.scaled_pixmap)

        if self.is_cropping:
            self._draw_cropping_ui(painter, pixmap_rect)

    def _draw_cropping_ui(self, painter, pixmap_rect):
        """Draws the semi-transparent overlay and crop handles."""
        # Semi-transparent overlay outside the crop rect
        path = QPainterPath()
        path.addRect(QRectF(pixmap_rect))
        path.addRect(QRectF(self.crop_rect_widget))
        painter.fillPath(path, QBrush(QColor(0, 0, 0, 128)))

        # Draw the crop rectangle border
        pen = QPen(QColor("#6C95FF"), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(self.crop_rect_widget)

        # Draw handles
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#6C95FF"))
        for handle, rect in self.crop_handles.items():
            painter.drawRect(rect)

    def resizeEvent(self, event):
        """Handles widget resizing by re-scaling the pixmap."""
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def mousePressEvent(self, event):
        """Handles mouse presses for panning or cropping."""
        if event.button() == Qt.LeftButton:
            if self.is_cropping:
                self.active_handle = self._get_handle_at(event.pos())
                if self.active_handle:
                    self.is_panning = False
                elif self.crop_rect_widget.contains(event.pos()):
                    self.active_handle = "move"
                    self.is_panning = False
                else: # Pan if zoomed, otherwise do nothing
                    self.is_panning = self.zoom_factor > 1.0
            else: # Not cropping, so pan if zoomed
                self.is_panning = self.zoom_factor > 1.0

            self.last_mouse_pos = event.pos()

    def mouseMoveEvent(self, event):
        """Handles mouse movement for panning or dragging crop handles."""
        delta = event.pos() - self.last_mouse_pos
        self.last_mouse_pos = event.pos()

        if self.is_panning:
            self.pan_offset += delta
            self._clamp_pan_offset()
            self.update()
        elif self.is_cropping and self.active_handle:
            self._move_crop_handle(delta)
            self.update()

    def mouseReleaseEvent(self, event):
        """Stops panning or cropping actions."""
        if event.button() == Qt.LeftButton:
            self.is_panning = False
            self.active_handle = None

    def wheelEvent(self, event):
        """Handles mouse wheel events for zooming."""
        if self.pixmap.isNull() or self.is_cropping:
            return

        # Zoom in/out
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_factor *= 1.15
        else:
            self.zoom_factor /= 1.15

        self.zoom_factor = max(1.0, min(self.zoom_factor, 10.0))

        self._clamp_pan_offset()
        self._update_scaled_pixmap()
        self.update()

    # --- Helper Methods ---

    def _update_scaled_pixmap(self):
        """
        Calculates the scaled pixmap to fit the widget while preserving aspect ratio.
        """
        if self.pixmap.isNull():
            self.scaled_pixmap = QPixmap()
            return

        widget_size = self.size()

        # Apply zoom factor
        scaled_size = self.pixmap.size() * self.zoom_factor

        # If zoomed, we don't scale to fit, we just use the zoomed size
        if self.zoom_factor > 1.0:
             self.scaled_pixmap = self.pixmap.scaled(
                scaled_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        else: # Scale to fit inside the widget
            self.scaled_pixmap = self.pixmap.scaled(
                widget_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

    def _get_pixmap_rect_in_widget(self):
        """
        Calculates the QRect where the scaled pixmap is drawn within the widget.
        Takes into account widget size, pixmap size, and pan offset.
        """
        if self.scaled_pixmap.isNull():
            return QRect()

        pixmap_size = self.scaled_pixmap.size()
        widget_size = self.size()

        # Center the pixmap
        x = (widget_size.width() - pixmap_size.width()) / 2
        y = (widget_size.height() - pixmap_size.height()) / 2

        # Apply pan offset if zoomed
        if self.zoom_factor > 1.0:
            x += self.pan_offset.x()
            y += self.pan_offset.y()

        return QRect(QPoint(int(x), int(y)), pixmap_size)

    def _clamp_pan_offset(self):
        """Ensures the pan offset doesn't allow panning beyond the image edges."""
        if self.zoom_factor <= 1.0 or self.scaled_pixmap.isNull():
            self.pan_offset = QPoint()
            return

        pixmap_size = self.scaled_pixmap.size()
        widget_size = self.size()

        # How much the pixmap overhangs the widget
        overhang_x = (pixmap_size.width() - widget_size.width()) / 2.0
        overhang_y = (pixmap_size.height() - widget_size.height()) / 2.0

        # The pan offset can't be more than the overhang
        self.pan_offset.setX(max(-overhang_x, min(self.pan_offset.x(), overhang_x)))
        self.pan_offset.setY(max(-overhang_y, min(self.pan_offset.y(), overhang_y)))

    def _update_crop_handles(self):
        """Calculates the positions of the 8 crop handles."""
        r = self.crop_rect_widget
        s = 8  # Handle size
        s2 = s // 2
        self.crop_handles = {
            "top_left": QRect(r.left() - s2, r.top() - s2, s, s),
            "top_right": QRect(r.right() - s2, r.top() - s2, s, s),
            "bottom_left": QRect(r.left() - s2, r.bottom() - s2, s, s),
            "bottom_right": QRect(r.right() - s2, r.bottom() - s2, s, s),
            "top": QRect(r.center().x() - s2, r.top() - s2, s, s),
            "bottom": QRect(r.center().x() - s2, r.bottom() - s2, s, s),
            "left": QRect(r.left() - s2, r.center().y() - s2, s, s),
            "right": QRect(r.right() - s2, r.center().y() - s2, s, s),
        }

    def _get_handle_at(self, pos):
        """Checks if a position is inside any crop handle."""
        for handle, rect in self.crop_handles.items():
            if rect.contains(pos):
                return handle
        return None

    def _move_crop_handle(self, delta):
        """Moves the crop rectangle based on which handle is being dragged."""
        r = self.crop_rect_widget
        pixmap_rect = self._get_pixmap_rect_in_widget()

        if self.active_handle == "move":
            r.translate(delta)
        elif "left" in self.active_handle:
            r.setLeft(r.left() + delta.x())
        elif "right" in self.active_handle:
            r.setRight(r.right() + delta.x())

        if "top" in self.active_handle:
            r.setTop(r.top() + delta.y())
        elif "bottom" in self.active_handle:
            r.setBottom(r.bottom() + delta.y())

        # Ensure the crop rect doesn't go outside the pixmap area
        r.setLeft(max(r.left(), pixmap_rect.left()))
        r.setRight(min(r.right(), pixmap_rect.right()))
        r.setTop(max(r.top(), pixmap_rect.top()))
        r.setBottom(min(r.bottom(), pixmap_rect.bottom()))

        # Ensure rect has a minimum size
        if r.width() < 20: r.setWidth(20)
        if r.height() < 20: r.setHeight(20)

        self.crop_rect_widget = r
        self._update_crop_handles()
        self.change_occurred.emit()

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    viewer = ImageViewer()
    # You need a test image named 'test.jpg' in the same directory to run this
    if len(sys.argv) > 1:
        viewer.load_image(sys.argv[1])
    else:
        # Create a dummy pixmap for testing if no image is provided
        dummy_pixmap = QPixmap(600, 400)
        dummy_pixmap.fill(Qt.gray)
        painter = QPainter(dummy_pixmap)
        painter.setPen(Qt.white)
        painter.drawText(dummy_pixmap.rect(), Qt.AlignCenter, "Provide an image path or this is a test.")
        painter.end()
        viewer.pixmap = dummy_pixmap
        viewer._update_scaled_pixmap()

    # Example of how to use it from a main window
    def toggle_crop():
        viewer.set_cropping_mode(not viewer.is_cropping)
        print(f"Cropping mode: {viewer.is_cropping}")
        if not viewer.is_cropping:
            coords = viewer.get_crop_coords()
            print(f"Final crop coordinates (in image space): {coords}")

    button = QPushButton("Toggle Cropping")
    button.clicked.connect(toggle_crop)

    layout = QVBoxLayout()
    layout.addWidget(viewer)
    layout.addWidget(button)

    main_widget = QWidget()
    main_widget.setLayout(layout)
    main_widget.resize(800, 600)
    main_widget.show()

    sys.exit(app.exec())
