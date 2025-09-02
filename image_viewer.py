from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, Signal, QSize, QTimer
from PySide6.QtGui import QPixmap, QPainter, QImage, QColor, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QWidget
from PIL import Image, ImageQt, ImageEnhance

class ImageViewer(QWidget):
    """
    A custom widget for displaying and interacting with an image.
    Supports panning, zooming, cropping, splitting, and color adjustments.
    """
    view_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: black;")

        # --- Image State ---
        self.base_image: Image.Image = None
        self.display_pixmap: QPixmap = None
        self.preview_pixmap: QPixmap = None # For non-destructive previews

        # --- Transformation State ---
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.rotation_angle = 0
        self.brightness = 1.0 # 1.0 is no change
        self.contrast = 1.0   # 1.0 is no change

        # --- Interaction State ---
        self.last_mouse_pos = QPoint()
        self.is_panning = False

        # --- Mode States ---
        self.is_cropping = False
        self.crop_rect = QRect()
        self.crop_handles = {}
        self._dragging_handle = None
        self._dragging_rect = False

        self.is_splitting = False
        self.split_line_x_ratio = 0.5 # 0.0 to 1.0
        self._is_dragging_split_line = False

        # --- Animation State ---
        self.trail_timer = QTimer(self)
        self.trail_timer.timeout.connect(self._update_trail_step)
        self.trail_progress = 0 # 0.0 to 1.0

    # --- Public API ---

    def load_image(self, file_path: str):
        """Loads an image from a file path and resets the view."""
        self.clear_preview()
        if file_path and self.base_image and hasattr(self.base_image, 'fp') and self.base_image.fp is None:
             pass

        if file_path:
            try:
                self.base_image = Image.open(file_path)
                self.display_pixmap = self.image_to_pixmap(self.base_image)
                self.start_trail_animation()
            except Exception as e:
                print(f"Error loading image {file_path}: {e}")
                self.base_image = None
                self.display_pixmap = None
        else:
            self.base_image = None
            self.display_pixmap = None

        self.reset_view()
        self.update()
        return self.base_image is not None

    def set_cropping_mode(self, enabled: bool):
        if enabled:
            self.set_splitting_mode(False)
        self.is_cropping = enabled
        if enabled and self.display_pixmap:
            img_rect = self.display_pixmap.rect()
            w, h = int(img_rect.width() * 0.8), int(img_rect.height() * 0.8)
            x, y = int((img_rect.width() - w) / 2), int((img_rect.height() - h) / 2)
            self.crop_rect = QRect(x, y, w, h)
        self.update()

    def set_splitting_mode(self, enabled: bool):
        if enabled:
            self.set_cropping_mode(False)
        self.is_splitting = enabled
        self.split_line_x_ratio = 0.5
        self.update()

    def reset_view(self):
        """Resets zoom, pan, and all adjustments."""
        self.clear_preview()
        self.rotation_angle = 0
        self.brightness = 1.0
        self.contrast = 1.0
        self.is_cropping = False
        self.is_splitting = False

        if self.display_pixmap:
            self.fit_to_window()
        else:
            self.zoom_factor = 1.0
            self.pan_offset = QPointF(0, 0)
        self.update()

    def set_brightness(self, value: int): # Range from -100 to 100
        self.brightness = 1.0 + (value / 100.0)
        self.update_preview_pixmap()

    def set_contrast(self, value: int): # Range from -100 to 100
        self.contrast = 1.0 + (value / 100.0)
        self.update_preview_pixmap()

    def set_rotation(self, angle: int):
        self.rotation_angle = angle
        self.update_preview_pixmap()

    def update_preview_pixmap(self):
        """Applies current adjustments to the base image and generates a preview."""
        if not self.base_image:
            return

        temp_image = self.base_image

        # Apply adjustments
        if self.contrast != 1.0:
            enhancer = ImageEnhance.Contrast(temp_image)
            temp_image = enhancer.enhance(self.contrast)
        if self.brightness != 1.0:
            enhancer = ImageEnhance.Brightness(temp_image)
            temp_image = enhancer.enhance(self.brightness)
        if self.rotation_angle != 0:
            temp_image = temp_image.rotate(self.rotation_angle, resample=Image.Resampling.BICUBIC, expand=True)

        self.preview_pixmap = self.image_to_pixmap(temp_image)
        self.update()

    def clear_preview(self):
        self.preview_pixmap = None
        self.update()

    def get_crop_coords(self) -> QRect:
        return self.crop_rect

    def get_split_ratio(self) -> float:
        return self.split_line_x_ratio

    def get_image_operations(self) -> dict:
        return {
            "rotation": self.rotation_angle,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "crop": self.get_crop_coords() if self.is_cropping else None
        }

    # --- Event Handlers ---

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        pixmap_to_draw = self.preview_pixmap if self.preview_pixmap else self.display_pixmap
        if not pixmap_to_draw:
            painter.setPen(QColor("white"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No Image")
            return

        widget_center = self.rect().center()
        draw_center = widget_center + self.pan_offset
        current_w = pixmap_to_draw.width() * self.zoom_factor
        current_h = pixmap_to_draw.height() * self.zoom_factor
        target_rect = QRectF(
            draw_center.x() - current_w / 2,
            draw_center.y() - current_h / 2,
            current_w, current_h
        )

        painter.drawPixmap(target_rect, pixmap_to_draw, pixmap_to_draw.rect())

        if self.is_cropping:
            self.draw_cropping_ui(painter, target_rect)
        elif self.is_splitting:
            self.draw_splitting_ui(painter, target_rect)

        if self.trail_timer.isActive():
            self.draw_trail_animation(painter, target_rect)

    def draw_cropping_ui(self, painter, target_rect):
        painter.save()
        scale_x = target_rect.width() / (self.preview_pixmap if self.preview_pixmap else self.display_pixmap).width()
        scale_y = target_rect.height() / (self.preview_pixmap if self.preview_pixmap else self.display_pixmap).height()

        display_crop_rect = QRectF(
            target_rect.left() + self.crop_rect.left() * scale_x,
            target_rect.top() + self.crop_rect.top() * scale_y,
            self.crop_rect.width() * scale_x,
            self.crop_rect.height() * scale_y
        ).normalized()

        path = QPainterPath()
        path.addRect(target_rect)
        path.addRect(display_crop_rect)
        painter.fillPath(path, QColor(0, 0, 0, 128))
        pen = QPen(QColor("#5A9BD5"), 2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(display_crop_rect)
        handle_size = 8
        self.crop_handles = self.get_handle_rects(display_crop_rect, handle_size)
        painter.setBrush(QColor("#5A9BD5"))
        for handle in self.crop_handles.values():
            painter.drawRect(handle)
        painter.restore()

    def draw_splitting_ui(self, painter, target_rect):
        painter.save()
        split_x = target_rect.left() + target_rect.width() * self.split_line_x_ratio
        pen = QPen(QColor("#E574E8"), 3, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(split_x, target_rect.top()), QPointF(split_x, target_rect.bottom()))
        painter.restore()

    def wheelEvent(self, event):
        if not self.display_pixmap: return
        delta = event.angleDelta().y()
        zoom_factor_change = 1.2 if delta > 0 else 1 / 1.2
        self.zoom_factor *= zoom_factor_change
        mouse_pos = event.position()
        widget_center = self.rect().center()
        center_to_mouse = mouse_pos - widget_center
        self.pan_offset = mouse_pos - widget_center - (center_to_mouse - self.pan_offset) * zoom_factor_change
        self.update()
        self.view_changed.emit()

    def mousePressEvent(self, event):
        self.last_mouse_pos = event.position()
        if event.button() == Qt.LeftButton:
            if self.is_cropping:
                self._dragging_handle = self.get_handle_at(event.position())
                if self._dragging_handle: return
                display_crop_rect = self.image_to_widget_rect(self.crop_rect)
                if display_crop_rect.contains(event.position()):
                    self._dragging_rect = True
                    return
            elif self.is_splitting:
                display_rect = self.image_to_widget_rect(self.display_pixmap.rect())
                split_x_in_widget = display_rect.left() + display_rect.width() * self.split_line_x_ratio
                if abs(event.position().x() - split_x_in_widget) < 10:
                    self._is_dragging_split_line = True
                    return
            self.is_panning = True
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        delta = QPointF(event.position() - self.last_mouse_pos)
        if self._dragging_handle: self.resize_crop_rect(delta)
        elif self._dragging_rect: self.move_crop_rect(delta)
        elif self._is_dragging_split_line: self.move_split_line(event.position())
        elif self.is_panning:
            self.pan_offset += delta
            self.update()
            self.view_changed.emit()
        self.last_mouse_pos = event.position()

    def mouseReleaseEvent(self, event):
        self.is_panning = False
        self._dragging_handle = None
        self._dragging_rect = False
        self._is_dragging_split_line = False
        self.setCursor(Qt.ArrowCursor)

    def resizeEvent(self, event):
        self.fit_to_window()
        super().resizeEvent(event)

    # --- Helper Methods ---

    def fit_to_window(self):
        if not self.display_pixmap: return
        w_ratio = self.width() / self.display_pixmap.width()
        h_ratio = self.height() / self.display_pixmap.height()
        self.zoom_factor = min(w_ratio, h_ratio) * 0.98
        self.pan_offset = QPointF(0, 0)
        self.update()
        self.view_changed.emit()

    def image_to_pixmap(self, image: Image.Image) -> QPixmap:
        return QPixmap.fromImage(ImageQt.toqimage(image))

    def image_to_widget_rect(self, image_rect: QRect) -> QRectF:
        pixmap_to_draw = self.preview_pixmap if self.preview_pixmap else self.display_pixmap
        if not pixmap_to_draw: return QRectF()
        widget_center = self.rect().center()
        draw_center = widget_center + self.pan_offset
        pixmap_w = pixmap_to_draw.width() * self.zoom_factor
        pixmap_h = pixmap_to_draw.height() * self.zoom_factor
        top_left_in_widget = draw_center - QPointF(pixmap_w / 2, pixmap_h / 2)
        scale_x = pixmap_w / pixmap_to_draw.width()
        scale_y = pixmap_h / pixmap_to_draw.height()
        return QRectF(
            top_left_in_widget.x() + image_rect.left() * scale_x,
            top_left_in_widget.y() + image_rect.top() * scale_y,
            image_rect.width() * scale_x,
            image_rect.height() * scale_y
        )

    def get_handle_rects(self, rect: QRectF, size: int) -> dict:
        s2 = size / 2
        return {
            "top_left": QRectF(rect.topLeft() - QPointF(s2, s2), QSizeF(size, size)), "top_right": QRectF(rect.topRight() - QPointF(s2, s2), QSizeF(size, size)),
            "bottom_left": QRectF(rect.bottomLeft() - QPointF(s2, s2), QSizeF(size, size)), "bottom_right": QRectF(rect.bottomRight() - QPointF(s2, s2), QSizeF(size, size)),
            "top": QRectF(QPointF(rect.center().x() - s2, rect.top() - s2), QSizeF(size, size)), "bottom": QRectF(QPointF(rect.center().x() - s2, rect.bottom() - s2), QSizeF(size, size)),
            "left": QRectF(QPointF(rect.left() - s2, rect.center().y() - s2), QSizeF(size, size)), "right": QRectF(QPointF(rect.right() - s2, rect.center().y() - s2), QSizeF(size, size)),
        }

    def get_handle_at(self, pos: QPointF) -> str:
        for name, rect in self.crop_handles.items():
            if rect.contains(pos): return name
        return None

    def move_crop_rect(self, delta: QPointF):
        pixmap_to_draw = self.preview_pixmap if self.preview_pixmap else self.display_pixmap
        scale_x = pixmap_to_draw.width() / (pixmap_to_draw.width() * self.zoom_factor)
        scale_y = pixmap_to_draw.height() / (pixmap_to_draw.height() * self.zoom_factor)
        self.crop_rect.translate(int(delta.x() * scale_x), int(delta.y() * scale_y))
        self.crop_rect = self.crop_rect.intersected(pixmap_to_draw.rect())
        self.update()

    def resize_crop_rect(self, delta: QPointF):
        pixmap_to_draw = self.preview_pixmap if self.preview_pixmap else self.display_pixmap
        scale_x = pixmap_to_draw.width() / (pixmap_to_draw.width() * self.zoom_factor)
        scale_y = pixmap_to_draw.height() / (pixmap_to_draw.height() * self.zoom_factor)
        dx, dy = delta.x() * scale_x, delta.y() * scale_y
        if "top" in self._dragging_handle: self.crop_rect.setTop(self.crop_rect.top() + dy)
        if "bottom" in self._dragging_handle: self.crop_rect.setBottom(self.crop_rect.bottom() + dy)
        if "left" in self._dragging_handle: self.crop_rect.setLeft(self.crop_rect.left() + dx)
        if "right" in self._dragging_handle: self.crop_rect.setRight(self.crop_rect.right() + dx)
        self.crop_rect = self.crop_rect.intersected(pixmap_to_draw.rect()).normalized()
        self.update()

    def move_split_line(self, pos: QPointF):
        display_rect = self.image_to_widget_rect(self.display_pixmap.rect())
        if display_rect.width() == 0: return
        self.split_line_x_ratio = (pos.x() - display_rect.left()) / display_rect.width()
        self.split_line_x_ratio = max(0.0, min(1.0, self.split_line_x_ratio))
        self.update()

    # --- Animation Methods ---
    def start_trail_animation(self):
        self.trail_progress = 0
        self.trail_timer.start(20) # Update every 20ms

    def _update_trail_step(self):
        self.trail_progress += 0.05 # Speed of the trail
        if self.trail_progress > 1.0:
            self.trail_timer.stop()
            self.trail_progress = 0
        self.update() # Trigger repaint

    def draw_trail_animation(self, painter, target_rect):
        painter.save()

        # Trail properties
        trail_length = 0.25 # Percentage of the perimeter
        pen = QPen(QColor(100, 150, 255, 150), 6, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)

        path = QPainterPath()
        path.addRect(target_rect)

        path_length = path.length()
        trail_start = path_length * (self.trail_progress - trail_length)
        trail_end = path_length * self.trail_progress

        for i in range(int(trail_start), int(trail_end)):
            percent = float(i) / path_length
            if percent < 0: continue

            # This is a simplified way to draw segments.
            # QPainterPath::pointAtPercent is what we need.
            p1 = path.pointAtPercent(percent)
            p2 = path.pointAtPercent(min(1.0, (i + 1) / path_length))
            painter.drawLine(p1, p2)

        painter.restore()
