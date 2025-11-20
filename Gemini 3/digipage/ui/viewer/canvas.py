from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen, QPainterPath, QBrush
from PySide6.QtCore import Qt, Signal, Slot, QRectF, QPointF, QPropertyAnimation, QEasingCurve, QPoint

from digipage.ui.viewer.handlers import InteractionHandler, PanHandler, CropHandler, RotateHandler
import math

class ImageCanvas(QWidget):
    """
    The central widget for displaying an image and handling user interactions.
    Delegates specific logic to an active InteractionHandler.
    """
    # Signals
    interaction_started = Signal()
    interaction_finished = Signal()
    zoom_changed = Signal(bool)
    crop_applied = Signal(str, object) # path, rect
    rotation_applied = Signal(str, float) # path, angle

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(300, 200)
        
        # Data
        self.image_path = None
        self.pixmap = QPixmap()
        self.display_pixmap = QPixmap()
        
        # Appearance
        self.accent_color = QColor("#b0c6ff")
        self.tertiary_color = QColor("#e2bada")
        
        # State
        self._zoom_level = 1.0
        self.pan_offset = QPointF(0, 0)
        self.rotation_angle = 0.0 # Visual only, actual rotation handled by worker
        
        # Interaction Handlers
        self.handlers = {
            "pan": PanHandler(self),
            "crop": CropHandler(self),
            "rotate": RotateHandler(self),
            # "split": SplitHandler(self) # To be implemented if needed
        }
        self.current_handler: InteractionHandler = self.handlers["crop"]
        
        # Wiring Signals
        self.handlers['crop'].crop_changed.connect(self._on_crop_finished)
        self.handlers['rotate'].angle_changed.connect(self._on_rotation_finished)
        
        # Animation
        self.zoom_animation = QPropertyAnimation(self, b"zoom_level", self)
        self.zoom_animation.setDuration(300)
        self.zoom_animation.setEasingCurve(QEasingCurve.InOutQuad)

    # --- Properties ---
    def get_zoom_level(self): return self._zoom_level
    def set_zoom_level(self, val):
        self._zoom_level = val
        self.zoom_changed.emit(val > self.get_fit_zoom())
        self.update()
    zoom_level = property(get_zoom_level, set_zoom_level)

    # --- Public API ---
    def set_image(self, path: str, pixmap: QPixmap):
        self.image_path = path
        self.pixmap = pixmap
        self.rotation_angle = 0.0
        self.pan_offset = QPointF(0, 0)
        
        if not pixmap.isNull():
            self.set_zoom_level(self.get_fit_zoom())
            self.current_handler.reset()
        
        self.update()

    def set_mode(self, mode: str):
        if mode in self.handlers:
            self.current_handler = self.handlers[mode]
            self.current_handler.reset()
            
            # Auto-reset zoom for rotation/split modes usually
            if mode in ['rotate', 'split']:
                self.reset_zoom()
            
            self.update()

    def reset_zoom(self):
        self.pan_offset = QPointF(0,0)
        self.zoom_animation.stop()
        self.zoom_animation.setStartValue(self._zoom_level)
        self.zoom_animation.setEndValue(self.get_fit_zoom())
        self.zoom_animation.start()

    def get_fit_zoom(self):
        if self.pixmap.isNull() or self.width() == 0 or self.height() == 0: return 1.0
        return min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())

    # --- Coordinate Mapping ---
    def map_image_to_widget(self, image_point: QPointF) -> QPointF:
        """Converts a point from Image Space to Widget Space."""
        # Calculate offset to center image
        scaled_w = self.pixmap.width() * self._zoom_level
        scaled_h = self.pixmap.height() * self._zoom_level
        x_offset = (self.width() - scaled_w) / 2 + self.pan_offset.x()
        y_offset = (self.height() - scaled_h) / 2 + self.pan_offset.y()
        
        return QPointF(
            image_point.x() * self._zoom_level + x_offset,
            image_point.y() * self._zoom_level + y_offset
        )

    def map_widget_to_image(self, widget_point: QPoint) -> QPointF:
        """Converts a point from Widget Space to Image Space."""
        scaled_w = self.pixmap.width() * self._zoom_level
        scaled_h = self.pixmap.height() * self._zoom_level
        x_offset = (self.width() - scaled_w) / 2 + self.pan_offset.x()
        y_offset = (self.height() - scaled_h) / 2 + self.pan_offset.y()
        
        img_x = (widget_point.x() - x_offset) / self._zoom_level
        img_y = (widget_point.y() - y_offset) / self._zoom_level
        return QPointF(img_x, img_y)

    def map_rect_to_widget(self, image_rect: QRectF) -> QRectF:
        tl = self.map_image_to_widget(image_rect.topLeft())
        br = self.map_image_to_widget(image_rect.bottomRight())
        return QRectF(tl, br)

    def _clamp_pan_offset(self):
        """Prevents panning the image too far out of view."""
        if self.pixmap.isNull(): return
        
        scaled_w = self.pixmap.width() * self._zoom_level
        scaled_h = self.pixmap.height() * self._zoom_level
        
        # Allow panning if image is larger than widget
        max_x = max(0, (scaled_w - self.width()) / 2)
        max_y = max(0, (scaled_h - self.height()) / 2)
        
        x = max(-max_x, min(self.pan_offset.x(), max_x))
        y = max(-max_y, min(self.pan_offset.y(), max_y))
        self.pan_offset = QPointF(x, y)

    # --- Event Handlers ---
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self.pixmap.isNull():
            painter.setPen(self.tertiary_color)
            painter.drawText(self.rect(), Qt.AlignCenter, "No Image")
            return

        # Draw Image
        # We calculate the target rect in widget coordinates
        target_rect = self.map_rect_to_widget(QRectF(self.pixmap.rect()))
        
        if self.rotation_angle != 0:
            # Complex rotation drawing handled by painter transform
            cx, cy = target_rect.center().x(), target_rect.center().y()
            painter.translate(cx, cy)
            painter.rotate(self.rotation_angle)
            painter.translate(-cx, -cy)
            painter.drawPixmap(target_rect.toRect(), self.pixmap)
            painter.resetTransform()
        else:
            painter.drawPixmap(target_rect.toRect(), self.pixmap)

        # Delegate UI drawing to handler
        self.current_handler.paint(painter)

    def mousePressEvent(self, event):
        img_pos = self.map_widget_to_image(event.pos())
        self.current_handler.on_mouse_press(event, img_pos)
        if self.current_handler.is_active:
            self.interaction_started.emit()

    def mouseMoveEvent(self, event):
        img_pos = self.map_widget_to_image(event.pos())
        self.current_handler.on_mouse_move(event, img_pos)

    def mouseReleaseEvent(self, event):
        img_pos = self.map_widget_to_image(event.pos())
        self.current_handler.on_mouse_release(event, img_pos)
        self.interaction_finished.emit()

    def wheelEvent(self, event):
        # Handle Zooming
        if self.pixmap.isNull(): return
        
        delta = event.angleDelta().y()
        zoom_factor = 1.1 if delta > 0 else 0.9
        new_zoom = self._zoom_level * zoom_factor
        
        # Clamp zoom
        fit = self.get_fit_zoom()
        new_zoom = max(fit, min(new_zoom, 5.0))
        
        self.set_zoom_level(new_zoom)
        self._clamp_pan_offset()
        
        # Switch to Pan mode if zoomed in significantly
        if new_zoom > fit * 1.05:
            if not isinstance(self.current_handler, PanHandler):
                self.set_mode("pan")
        else:
            if isinstance(self.current_handler, PanHandler):
                self.set_mode("crop") # Default back to crop

    def resizeEvent(self, event):
        # Re-fit image on resize if not zoomed in manually
        if not isinstance(self.current_handler, PanHandler):
            self.set_zoom_level(self.get_fit_zoom())
        super().resizeEvent(event)

    # --- Internal Slots ---
    @Slot(object)
    def _on_crop_finished(self, rect):
        if self.image_path:
            self.crop_applied.emit(self.image_path, rect)
            
    @Slot(float)
    def _on_rotation_finished(self, angle):
        if self.image_path:
            self.rotation_applied.emit(self.image_path, angle)