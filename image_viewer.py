import sys
import os
from PySide6.QtWidgets import QWidget, QApplication, QPushButton, QVBoxLayout, QFrame
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, Slot, QPropertyAnimation, QEasingCurve, QRectF, QPointF

class ImageViewer(QWidget):
    """
    A custom widget for displaying and interacting with images.
    Handles loading, displaying, scaling, panning, cropping, and animations.
    """
    load_requested = Signal(str)
    rescale_requested = Signal(str, QSize)
    rotation_requested = Signal(str, int)
    save_requested = Signal(str, QPixmap)
    crop_requested = Signal(str, QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True) # Required for cursor changes on handles

        # Image and display state
        self.image_path = None
        self.pixmap = QPixmap()
        self.display_pixmap = QPixmap()
        self.rotation_angle = 0
        self.accent_color = QColor("#b0c6ff")

        # Interaction state
        self.is_panning = False
        self.is_cropping = False
        self.is_zoomed = False
        self.last_mouse_pos = QPoint()
        self.pan_offset = QPointF()
        self.zoom_factor = 1.0

        # Cropping state
        self.crop_rect_widget = QRect()
        self.crop_handles = {}
        self.active_handle = None
        
        # Animation
        self.opacity_animation = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_animation.setDuration(150)

    def set_accent_color(self, color_hex):
        self.accent_color = QColor(color_hex)

    def request_image_load(self, path, force_reload=False):
        # If the path is the same and we are not forcing a reload, do nothing.
        if self.image_path == path and not self.pixmap.isNull() and not force_reload:
            return
        
        self.image_path = path
        self.fade_out()
        self.load_requested.emit(path)

    @Slot(str, QPixmap)
    def on_image_loaded(self, path, pixmap):
        if path != self.image_path:
            return
            
        self.pixmap = pixmap
        self.rotation_angle = 0
        self.reset_view()
        self.fade_in()
        # Set cropping mode by default for new images
        self.set_cropping_mode(True)

    @Slot(str, QPixmap)
    def on_image_rescaled(self, path, pixmap):
        if path == self.image_path:
            self.display_pixmap = pixmap
            self.update()

    @Slot(str, QPixmap)
    def on_image_rotated(self, path, pixmap):
        if path == self.image_path:
            self.pixmap = pixmap
            self.display_pixmap = pixmap
            self.update()

    def reset_view(self):
        self.zoom_factor = 1.0
        self.pan_offset = QPointF()
        self.is_zoomed = False
        self.is_cropping = True # Default to cropping mode
        self.crop_rect_widget = QRect()
        self._update_display_pixmap()
        self.update()

    def apply_rotation(self, angle_delta):
        if self.pixmap.isNull(): return
        self.rotation_angle = (self.rotation_angle + angle_delta) % 360
        self.rotation_requested.emit(self.image_path, self.rotation_angle)

    def apply_crop(self):
        if self.pixmap.isNull() or self.image_path is None: return
        crop_coords = self.get_crop_coords()
        if crop_coords:
            self.crop_requested.emit(self.image_path, crop_coords)

    def set_cropping_mode(self, enabled):
        if self.pixmap.isNull(): return
        self.is_cropping = enabled
        if enabled:
            # When enabling crop, reset rect to full pixmap bounds
            pixmap_rect = self._get_pixmap_rect_in_widget()
            self.crop_rect_widget = pixmap_rect.toRect()
            self._update_crop_handles()
        self.update()

    def get_crop_coords(self):
        if self.pixmap.isNull() or self.crop_rect_widget.isNull(): return None

        pixmap_rect_in_widget = self._get_pixmap_rect_in_widget()
        if pixmap_rect_in_widget.width() == 0 or pixmap_rect_in_widget.height() == 0: return None

        scale_x = self.pixmap.width() / pixmap_rect_in_widget.width()
        scale_y = self.pixmap.height() / pixmap_rect_in_widget.height()

        rel_x = self.crop_rect_widget.x() - pixmap_rect_in_widget.x()
        rel_y = self.crop_rect_widget.y() - pixmap_rect_in_widget.y()

        img_x = int(rel_x * scale_x)
        img_y = int(rel_y * scale_y)
        img_w = int(self.crop_rect_widget.width() * scale_x)
        img_h = int(self.crop_rect_widget.height() * scale_y)

        return QRect(img_x, img_y, img_w, img_h)

    def fade_in(self):
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)
        self.opacity_animation.start()

    def fade_out(self):
        self.opacity_animation.setStartValue(1.0)
        self.opacity_animation.setEndValue(0.0)
        self.opacity_animation.start()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.display_pixmap.isNull():
            return

        pixmap_rect = self._get_pixmap_rect_in_widget().toRect()
        painter.drawPixmap(pixmap_rect, self.display_pixmap)

        if self.is_cropping and not self.is_zoomed:
            self._draw_cropping_ui(painter)

    def _draw_cropping_ui(self, painter):
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        path.addRect(QRectF(self.crop_rect_widget))
        painter.fillPath(path, QBrush(QColor(0, 0, 0, 128)))

        pen = QPen(self.accent_color, 2, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(self.crop_rect_widget)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.accent_color)
        for handle, rect in self.crop_handles.items():
            painter.drawRect(rect)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.is_zoomed:
             self._update_display_pixmap()
             if self.is_cropping:
                self.set_cropping_mode(True) # Recalculate crop box on resize
        else:
            self._update_display_pixmap()


    def mouseDoubleClickEvent(self, event):
        if self.pixmap.isNull(): return
        self.is_zoomed = not self.is_zoomed
        if self.is_zoomed:
            self.zoom_factor = 1.1 # Initial slight zoom
        else:
            self.zoom_factor = 1.0
            self.pan_offset = QPointF()
            self.set_cropping_mode(True) # Restore crop box
        
        self._update_display_pixmap()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_cropping and not self.is_zoomed:
                self.active_handle = self._get_handle_at(event.pos())
                if self.active_handle:
                    self.is_panning = False
                elif self.crop_rect_widget.contains(event.pos()):
                    self.active_handle = "move"
                    self.is_panning = False
            elif self.is_zoomed:
                self.is_panning = True
            
            self.last_mouse_pos = event.pos()

    def mouseMoveEvent(self, event):
        delta = QPointF(event.pos() - self.last_mouse_pos)
        self.last_mouse_pos = event.pos()

        if self.is_panning:
            self.pan_offset += delta
            self._clamp_pan_offset()
            self.update()
        elif self.is_cropping and self.active_handle and not self.is_zoomed:
            self._move_crop_handle(delta)
            self.update()
        
        # Update cursor if hovering over handles
        if self.is_cropping and not self.is_zoomed and not self.is_panning and not self.active_handle:
            handle = self._get_handle_at(event.pos())
            if handle in ["top_left", "bottom_right"]: self.setCursor(Qt.SizeFDiagCursor)
            elif handle in ["top_right", "bottom_left"]: self.setCursor(Qt.SizeBDiagCursor)
            elif handle in ["top", "bottom"]: self.setCursor(Qt.SizeVerCursor)
            elif handle in ["left", "right"]: self.setCursor(Qt.SizeHorCursor)
            else: self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_panning = False
            self.active_handle = None

    def wheelEvent(self, event):
        if self.is_zoomed:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.zoom_factor = max(1.0, min(self.zoom_factor * factor, 10.0))
            self._update_display_pixmap()
            self.update()
        else:
            # Allow parent widget (main window) to handle scroll for navigation
            super().wheelEvent(event)

    def _update_display_pixmap(self):
        if self.pixmap.isNull() or self.image_path is None:
            self.display_pixmap = QPixmap()
            return
        
        widget_size = self.size()
        
        if self.is_zoomed:
            scaled_size = self.pixmap.size() * self.zoom_factor
            self.rescale_requested.emit(self.image_path, scaled_size)
        else:
            # Fit to view
            scaled_pixmap = self.pixmap.scaled(widget_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.display_pixmap = scaled_pixmap
            self.update()


    def _get_pixmap_rect_in_widget(self):
        if self.display_pixmap.isNull(): return QRectF()
        pixmap_size = self.display_pixmap.size()
        widget_size = self.size()
        x = (widget_size.width() - pixmap_size.width()) / 2.0
        y = (widget_size.height() - pixmap_size.height()) / 2.0
        
        if self.is_zoomed:
            x += self.pan_offset.x()
            y += self.pan_offset.y()

        return QRectF(QPointF(x, y), pixmap_size)

    def _clamp_pan_offset(self):
        if not self.is_zoomed or self.display_pixmap.isNull():
            self.pan_offset = QPointF()
            return
            
        pixmap_size = self.display_pixmap.size()
        widget_size = self.size()
        
        overhang_x = max(0, (pixmap_size.width() - widget_size.width()) / 2.0)
        overhang_y = max(0, (pixmap_size.height() - widget_size.height()) / 2.0)

        self.pan_offset.setX(max(-overhang_x, min(self.pan_offset.x(), overhang_x)))
        self.pan_offset.setY(max(-overhang_y, min(self.pan_offset.y(), overhang_y)))

    def _update_crop_handles(self):
        r = self.crop_rect_widget
        s = 10
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
        for handle, rect in self.crop_handles.items():
            if rect.contains(pos):
                return handle
        return None

    def _move_crop_handle(self, delta):
        r = QRectF(self.crop_rect_widget)
        pixmap_rect = self._get_pixmap_rect_in_widget()

        if self.active_handle == "move": r.translate(delta)
        elif "left" in self.active_handle: r.setLeft(r.left() + delta.x())
        elif "right" in self.active_handle: r.setRight(r.right() + delta.x())
        if "top" in self.active_handle: r.setTop(r.top() + delta.y())
        elif "bottom" in self.active_handle: r.setBottom(r.bottom() + delta.y())
        
        # Clamp to pixmap boundaries
        r.setLeft(max(r.left(), pixmap_rect.left()))
        r.setRight(min(r.right(), pixmap_rect.right()))
        r.setTop(max(r.top(), pixmap_rect.top()))
        r.setBottom(min(r.bottom(), pixmap_rect.bottom()))

        if r.width() < 20: r.setWidth(20)
        if r.height() < 20: r.setHeight(20)
        
        self.crop_rect_widget = r.toRect()
        self._update_crop_handles()

