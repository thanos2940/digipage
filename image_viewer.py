import sys
import os
from PySide6.QtWidgets import QWidget, QApplication, QPushButton, QVBoxLayout, QFrame
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QLinearGradient
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, Slot, QPropertyAnimation, QEasingCurve, QRectF, QPointF, QTimer, Property

class ImageViewer(QWidget):
    """
    A custom widget for displaying and interacting with images.
    Handles loading, displaying, scaling, panning, cropping, splitting, and animations.
    """
    load_requested = Signal(str, bool)
    rotation_requested = Signal(str, int)
    crop_adjustment_started = Signal()
    zoom_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True) 

        # Image and display state
        self.image_path = None
        self._loading_path = None
        self.pixmap = QPixmap()
        self.display_pixmap = QPixmap()
        self.rotation_angle = 0
        self.accent_color = QColor("#b0c6ff")
        self.tertiary_color = QColor("#e2bada")

        # Interaction state
        self.is_panning = False
        self.is_cropping = False
        self.is_splitting = False
        self.is_zoomed = False
        self.last_mouse_pos = QPoint()
        self.pan_offset = QPointF()
        
        # Cropping/Splitting state
        self.crop_rect_widget = QRect()
        self.crop_handles = {}
        self.active_handle = None
        self.split_line_id = None
        self.split_line_x_ratio = 0.5

        # Animation properties
        self._scan_line_progress = 0.0
        self._zoom_level = 1.0

        self.scan_line_animation = QPropertyAnimation(self, b"scan_line_progress", self)
        self.scan_line_animation.setDuration(800)
        self.scan_line_animation.setEasingCurve(QEasingCurve.InOutCubic)

        self.zoom_animation = QPropertyAnimation(self, b"zoom_level", self)
        self.zoom_animation.setDuration(300) # Faster for responsiveness
        self.zoom_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.zoom_animation.finished.connect(self._on_zoom_animation_finished)

    # --- Qt Properties for Animation ---
    def get_scan_line_progress(self):
        return self._scan_line_progress

    def set_scan_line_progress(self, progress):
        self._scan_line_progress = progress
        self.update()

    def get_zoom_level(self):
        return self._zoom_level

    def set_zoom_level(self, level):
        self._zoom_level = level
        self._update_display_pixmap()
        self._clamp_pan_offset()
        self.update()

    scan_line_progress = Property(float, get_scan_line_progress, set_scan_line_progress)
    zoom_level = Property(float, get_zoom_level, set_zoom_level)
    
    # --- Public Methods ---
    def set_theme_colors(self, primary_hex, tertiary_hex):
        self.accent_color = QColor(primary_hex)
        self.tertiary_color = QColor(tertiary_hex)

    def clear_image(self):
        """Clears the currently displayed image and resets state."""
        self.image_path = None
        self._loading_path = None
        self.pixmap = QPixmap()
        self.display_pixmap = QPixmap()
        self.update()

    def request_image_load(self, path, force_reload=False):
        if self.image_path == path and not self.pixmap.isNull() and not force_reload:
            return
        if self._loading_path == path and not force_reload:
            return
            
        self._loading_path = path
        if path is None:
            self.on_image_loaded(None, QPixmap())
        else:
            self.load_requested.emit(path, force_reload)

    # --- Slots for Worker Signals ---
    @Slot(str, QPixmap)
    def on_image_loaded(self, path, pixmap):
        if path != self._loading_path:
            return
            
        self.pixmap = pixmap
        self.image_path = path 
        self._loading_path = None 
        self.rotation_angle = 0
        self.reset_view()

        if not self.pixmap.isNull():
            self._start_scan_line_animation()
    
    # --- View and Transformation Methods ---
    def reset_view(self):
        self.is_zoomed = False
        self.pan_offset = QPointF()
        self.is_splitting = False 
        self.is_cropping = True 
        self.crop_rect_widget = QRect()
        
        fit_zoom = 1.0
        if not self.pixmap.isNull() and self.pixmap.width() > 0 and self.width() > 0:
            fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())

        self.set_zoom_level(fit_zoom)
        self.set_cropping_mode(True)

    def apply_rotation(self, angle_delta):
        if self.pixmap.isNull(): return
        self.rotation_angle = (self.rotation_angle + angle_delta) % 360
        self.rotation_requested.emit(self.image_path, self.rotation_angle)
    
    def get_image_space_crop_rect(self):
        if self.pixmap.isNull() or self.crop_rect_widget.isNull(): return None

        pixmap_rect_in_widget = self._get_pixmap_rect_in_widget()
        if pixmap_rect_in_widget.width() == 0 or pixmap_rect_in_widget.height() == 0: return None

        scale_x = self.pixmap.width() / (pixmap_rect_in_widget.width() / self._zoom_level)
        scale_y = self.pixmap.height() / (pixmap_rect_in_widget.height() / self._zoom_level)

        rel_x = self.crop_rect_widget.x() - pixmap_rect_in_widget.x()
        rel_y = self.crop_rect_widget.y() - pixmap_rect_in_widget.y()

        img_x = int(rel_x * (self.pixmap.width() / (self.pixmap.width() * self._zoom_level)))
        img_y = int(rel_y * (self.pixmap.height() / (self.pixmap.height() * self._zoom_level)))
        img_w = int(self.crop_rect_widget.width() * (self.pixmap.width() / (self.pixmap.width() * self._zoom_level)))
        img_h = int(self.crop_rect_widget.height() * (self.pixmap.height() / (self.pixmap.height() * self._zoom_level)))
        
        return QRect(img_x, img_y, img_w, img_h)

    def set_cropping_mode(self, enabled):
        if self.pixmap.isNull(): return
        self.is_cropping = enabled
        if enabled:
            pixmap_rect = self._get_pixmap_rect_in_widget()
            self.crop_rect_widget = pixmap_rect.toRect()
            self._update_crop_handles()
        self.update()
        
    def set_splitting_mode(self, enabled):
        if self.pixmap.isNull(): return

        self.is_splitting = enabled
        self.is_cropping = not enabled # Mutually exclusive

        if enabled:
            # When entering split mode, we must exit zoom mode.
            if self.is_zoomed:
                self.is_zoomed = False
                self.zoom_state_changed.emit(False) # Notify main window
                self.reset_view() # Resets zoom to fit and enables cropping
                self.is_cropping = False # Immediately disable cropping again
            
            self.split_line_x_ratio = 0.5
        
        self.update() # Force a repaint with the new state

    def get_split_x_in_image_space(self):
        if self.pixmap.isNull(): return None
        pixmap_rect = self._get_pixmap_rect_in_widget()
        split_line_widget_x = pixmap_rect.left() + pixmap_rect.width() * self.split_line_x_ratio
        
        scale_x = self.pixmap.width() / pixmap_rect.width()
        split_x_image = int((split_line_widget_x - pixmap_rect.left()) * scale_x)
        return split_x_image

    # --- Event Handlers ---
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter()
        painter.begin(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            
            if self.display_pixmap.isNull():
                return

            pixmap_rect = self._get_pixmap_rect_in_widget().toRect()
            painter.drawPixmap(pixmap_rect, self.display_pixmap)

            if self.is_cropping and not self.is_zoomed:
                self._draw_cropping_ui(painter)
                
            if self.is_splitting and not self.is_zoomed:
                self._draw_split_line(painter)

            if self.scan_line_animation.state() == QPropertyAnimation.Running:
                self._draw_border_animation(painter, pixmap_rect)
        finally:
            painter.end()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reset_view()

    def mouseDoubleClickEvent(self, event):
        if self.pixmap.isNull(): return
        self.is_zoomed = not self.is_zoomed
        self.zoom_state_changed.emit(self.is_zoomed)
        
        self.scan_line_animation.stop()

        start_zoom = self._zoom_level
        
        fit_zoom = 1.0
        if not self.pixmap.isNull() and self.pixmap.width() > 0:
            fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())

        if self.is_zoomed:
            end_zoom = fit_zoom * 1.5 # Slight zoom relative to fit
        else:
            end_zoom = fit_zoom # Return to the default fit

        self.zoom_animation.stop()
        self.zoom_animation.setStartValue(start_zoom)
        self.zoom_animation.setEndValue(end_zoom)
        self.zoom_animation.start()


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_cropping and not self.is_zoomed:
                self.active_handle = self._get_handle_at(event.pos())
                if self.active_handle or self.crop_rect_widget.contains(event.pos()):
                    self.is_panning = False 
                    if not self.active_handle: self.active_handle = "move"
            elif self.is_splitting and not self.is_zoomed:
                 self.active_handle = "split_line"
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
            self.crop_adjustment_started.emit()
            self._move_crop_handle(delta)
            self.update()
        elif self.is_splitting and self.active_handle == "split_line" and not self.is_zoomed:
            self.crop_adjustment_started.emit()
            pixmap_rect = self._get_pixmap_rect_in_widget()
            if pixmap_rect.width() > 0:
                self.split_line_x_ratio += delta.x() / pixmap_rect.width()
                self.split_line_x_ratio = max(0.0, min(1.0, self.split_line_x_ratio))
            self.update()
        
        if self.is_cropping and not self.is_zoomed and not self.active_handle:
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

            fit_zoom = 1.0
            if not self.pixmap.isNull() and self.pixmap.width() > 0:
                fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
            
            min_zoom = fit_zoom

            new_zoom = max(min_zoom, min(self._zoom_level * factor, 10.0))
            self.set_zoom_level(new_zoom)
        else:
            super().wheelEvent(event)

    # --- Private Helper Methods ---
    def _on_zoom_animation_finished(self):
        if not self.is_zoomed:
            self.pan_offset = QPointF()
            self.set_cropping_mode(True)
            self._update_display_pixmap()

    def _update_display_pixmap(self):
        if self.pixmap.isNull():
            self.display_pixmap = QPixmap()
        else:
            scaled_size = self.pixmap.size() * self._zoom_level
            self.display_pixmap = self.pixmap.scaled(scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
        s = 10; s2 = s // 2
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
            if rect.contains(pos): return handle
        return None

    def _move_crop_handle(self, delta):
        r = QRectF(self.crop_rect_widget)
        pixmap_rect = self._get_pixmap_rect_in_widget()

        if self.active_handle == "move": r.translate(delta)
        elif "left" in self.active_handle: r.setLeft(r.left() + delta.x())
        elif "right" in self.active_handle: r.setRight(r.right() + delta.x())
        if "top" in self.active_handle: r.setTop(r.top() + delta.y())
        elif "bottom" in self.active_handle: r.setBottom(r.bottom() + delta.y())
        
        r.setLeft(max(r.left(), pixmap_rect.left()))
        r.setRight(min(r.right(), pixmap_rect.right()))
        r.setTop(max(r.top(), pixmap_rect.top()))
        r.setBottom(min(r.bottom(), pixmap_rect.bottom()))

        if r.width() < 20: r.setWidth(20)
        if r.height() < 20: r.setHeight(20)
        
        self.crop_rect_widget = r.toRect()
        self._update_crop_handles()

    def _start_scan_line_animation(self):
        self.scan_line_animation.stop()
        self.scan_line_animation.setStartValue(0.0)
        self.scan_line_animation.setEndValue(1.0)
        self.scan_line_animation.start()

    def _draw_border_animation(self, painter, rect):
        progress = self._scan_line_progress
        if progress == 0 or progress == 1:
            return

        scan_y = rect.top() + rect.height() * progress
        line_height = rect.height() * 0.1  # Height of the gradient part of the line

        grad = QLinearGradient(rect.left(), scan_y - line_height, rect.left(), scan_y)
        
        c1 = QColor(self.tertiary_color)
        c1.setAlpha(0)
        c2 = QColor(self.tertiary_color)
        c2.setAlpha(200)

        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)

        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRect(QRectF(rect.left(), scan_y - line_height, rect.width(), line_height))

        pen = QPen(self.tertiary_color, 2)
        painter.setPen(pen)
        painter.drawLine(QPointF(rect.left(), scan_y), QPointF(rect.right(), scan_y))

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

    def _draw_split_line(self, painter):
        pixmap_rect = self._get_pixmap_rect_in_widget()
        split_x = pixmap_rect.left() + pixmap_rect.width() * self.split_line_x_ratio
        pen = QPen(self.accent_color, 3, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(split_x), int(pixmap_rect.top()), int(split_x), int(pixmap_rect.bottom()))

