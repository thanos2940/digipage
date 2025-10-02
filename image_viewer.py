import sys
import os
import math
from PySide6.QtWidgets import QWidget, QApplication, QPushButton, QVBoxLayout, QFrame, QGraphicsOpacityEffect
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QLinearGradient, QTransform
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, Slot, QPropertyAnimation, QEasingCurve, QRectF, QPointF, QTimer, Property, QEvent

class InteractionMode:
    """Defines the exclusive state of user interaction with the viewer."""
    CROPPING = 1
    SPLITTING = 2 # Legacy single-line splitting
    PANNING = 3
    ROTATING = 4
    PAGE_SPLITTING = 5 # New dual-rectangle splitting

class ImageViewer(QWidget):
    """
    A custom widget for displaying and interacting with images.
    Handles loading, displaying, scaling, panning, cropping, splitting, and animations.
    """
    load_requested = Signal(str, bool)
    crop_adjustment_started = Signal()
    zoom_state_changed = Signal(bool)
    rotation_finished = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True) 

        # Image and display state
        self.image_path = None
        self._loading_path = None
        self.pixmap = QPixmap()
        self.display_pixmap = QPixmap()
        self.rotation_angle = 0.0
        self.accent_color = QColor("#b0c6ff")
        self.tertiary_color = QColor("#e2bada")
        self.left_page_color = QColor(64, 220, 120)  # Green
        self.right_page_color = QColor(230, 80, 80) # Red


        # Interaction state management
        self.interaction_mode = InteractionMode.CROPPING
        self.is_zoomed = False
        self.active_handle = None
        self.last_mouse_pos = QPoint()
        self.pan_offset = QPointF()
        
        # Cropping/Splitting/Rotating state
        self.crop_rect_widget = QRect()
        self.crop_handles = {}

        self.left_rect_widget = QRectF()
        self.right_rect_widget = QRectF()
        self.left_handles = {}
        self.right_handles = {}

        self.is_dragging_rotate_handle = False
        self.rotation_on_press = 0.0
        self.drag_start_pos = QPoint()

        # Animation properties
        self._scan_line_progress = 0.0
        self._zoom_level = 1.0
        self.is_loading = False
        self.loading_animation_angle = 0
        
        # --- Floating Toolbar ---
        self.toolbar = None
        self.toolbar_animation = None
        self.toolbar_opacity_effect = None
        self.toolbar_hide_timer = QTimer(self)
        self.toolbar_hide_timer.setSingleShot(True)
        self.toolbar_hide_timer.setInterval(100) # 100ms delay before hiding
        self.toolbar_hide_timer.timeout.connect(self._hide_toolbar_animated)


        self.scan_line_animation = QPropertyAnimation(self, b"scan_line_progress", self)
        self.scan_line_animation.setDuration(800)
        self.scan_line_animation.setEasingCurve(QEasingCurve.InOutCubic)

        self.zoom_animation = QPropertyAnimation(self, b"zoom_level", self)
        self.zoom_animation.setDuration(300) 
        self.zoom_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.zoom_animation.finished.connect(self._on_zoom_animation_finished)

        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self._update_loading_animation)

    # --- Qt Properties for Animation ---
    def get_scan_line_progress(self):
        return self._scan_line_progress

    def update_toolbar_position(self):
        """Public method to trigger a repositioning of the toolbar."""
        self._update_toolbar_position()

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
    def set_toolbar(self, toolbar):
        self.toolbar = toolbar
        if self.toolbar:
            self.toolbar_opacity_effect = QGraphicsOpacityEffect(self.toolbar)
            self.toolbar.setGraphicsEffect(self.toolbar_opacity_effect)
            self.toolbar_animation = QPropertyAnimation(self.toolbar_opacity_effect, b"opacity")
            self.toolbar_animation.setDuration(200)
            self.toolbar_animation.setEasingCurve(QEasingCurve.OutQuad)
            self.toolbar.hide()

    def _show_toolbar_animated(self):
        """Shows the toolbar with a fade-in animation."""
        if self.toolbar:
            self.toolbar_hide_timer.stop()
            self._update_toolbar_position()
            self.toolbar_animation.stop()
            # Ensure effect and toolbar are visible before starting animation
            self.toolbar_opacity_effect.setOpacity(self.toolbar_opacity_effect.opacity())
            self.toolbar.show()
            self.toolbar_animation.setStartValue(self.toolbar_opacity_effect.opacity())
            self.toolbar_animation.setEndValue(1.0)
            self.toolbar_animation.start()
                    
    def cancel_toolbar_hide(self):
        self.toolbar_hide_timer.stop()

    def set_theme_colors(self, primary_hex, tertiary_hex):
        self.accent_color = QColor(primary_hex)
        self.tertiary_color = QColor(tertiary_hex)

    def clear_image(self):
        """Clears the currently displayed image and resets state."""
        self.image_path = None
        self._loading_path = None
        self.is_loading = False
        self.loading_timer.stop()
        self.pixmap = QPixmap()
        self.display_pixmap = QPixmap()
        self.update()
        if self.toolbar:
            self.toolbar.hide()

    def request_image_load(self, path, force_reload=False, show_loading_animation=True):
        if self.image_path == path and not self.pixmap.isNull() and not force_reload:
            return
        if self._loading_path == path and not force_reload:
            return
            
        self._loading_path = path

        self.pixmap = QPixmap()
        self.display_pixmap = QPixmap()
        
        if show_loading_animation:
            self.is_loading = True
            self.loading_timer.start(25)

        self.update()
        
        if path is None:
            self.on_image_loaded(None, QPixmap())
        else:
            self.load_requested.emit(path, force_reload)

    @Slot(str, QPixmap)
    def on_image_loaded(self, path, pixmap):
        self.is_loading = False
        self.loading_timer.stop()

        if path != self._loading_path:
            return
            
        self.pixmap = pixmap
        self.image_path = path 
        self._loading_path = None 
        self.rotation_angle = 0
        self.reset_view()

        if not self.pixmap.isNull():
            self._start_scan_line_animation()
    
    # --- View and State Management ---
    def reset_view(self):
        self.is_zoomed = False
        self.pan_offset = QPointF()
        
        if self.interaction_mode not in [InteractionMode.SPLITTING, InteractionMode.ROTATING, InteractionMode.PAGE_SPLITTING]:
            self.interaction_mode = InteractionMode.CROPPING

        fit_zoom = 1.0
        if not self.pixmap.isNull() and self.pixmap.width() > 0 and self.width() > 0:
            fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
    
        self.set_zoom_level(fit_zoom)

        if self.interaction_mode == InteractionMode.CROPPING:
            pixmap_rect = self._get_pixmap_rect_in_widget()
            self.crop_rect_widget = pixmap_rect.toRect()
            self._update_crop_handles()
        elif self.interaction_mode == InteractionMode.PAGE_SPLITTING:
            self._reset_page_split_rects()
        else:
            self.crop_rect_widget = QRect()
    
        self.update()

    def set_page_splitting_mode(self, enabled):
        if self.pixmap.isNull(): return
        if enabled:
            self.interaction_mode = InteractionMode.PAGE_SPLITTING
            self.is_zoomed = False
            self.zoom_state_changed.emit(False)
            self.pan_offset = QPointF()
            fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
            self.set_zoom_level(fit_zoom)
            self._reset_page_split_rects()
        else:
            self._enter_cropping_mode()
        self.update()

    def set_splitting_mode(self, enabled): # Legacy
        pass # This mode is no longer used, but the method is kept to avoid breaking old calls.
        
    def set_rotating_mode(self, enabled):
        if self.pixmap.isNull(): return

        if enabled:
            if self.zoom_animation.state() == QPropertyAnimation.Running:
                self.zoom_animation.stop()
            self.interaction_mode = InteractionMode.ROTATING
            self.is_zoomed = False
            self.zoom_state_changed.emit(False)
            self.pan_offset = QPointF()
            fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
            self.set_zoom_level(fit_zoom)
            self.crop_rect_widget = QRect() # Ensure crop UI is hidden
        else:
            self.rotation_angle = 0.0
            self._enter_cropping_mode()
        self.update()

    def get_image_space_crop_rect(self):
        if self.pixmap.isNull() or self.crop_rect_widget.isNull(): return None
        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.width() == 0: return None
        
        scale_w = self.pixmap.width() / pixmap_rect.width()
        scale_h = self.pixmap.height() / pixmap_rect.height()
        
        img_x = int((self.crop_rect_widget.x() - pixmap_rect.x()) * scale_w)
        img_y = int((self.crop_rect_widget.y() - pixmap_rect.y()) * scale_h)
        img_w = int(self.crop_rect_widget.width() * scale_w)
        img_h = int(self.crop_rect_widget.height() * scale_h)

        return QRect(img_x, img_y, img_w, img_h)

    def get_page_split_rects(self):
        if self.pixmap.isNull() or self.left_rect_widget.isNull() or self.right_rect_widget.isNull():
            return None

        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.width() == 0: return None

        scale_w = self.pixmap.width() / pixmap_rect.width()
        scale_h = self.pixmap.height() / pixmap_rect.height()

        def to_image_space(widget_rect):
            img_x = int((widget_rect.x() - pixmap_rect.x()) * scale_w)
            img_y = int((widget_rect.y() - pixmap_rect.y()) * scale_h)
            img_w = int(widget_rect.width() * scale_w)
            img_h = int(widget_rect.height() * scale_h)
            return QRect(img_x, img_y, img_w, img_h)

        return {
            "left": to_image_space(self.left_rect_widget),
            "right": to_image_space(self.right_rect_widget)
        }

    def set_page_split_rects(self, rects_data):
        """Sets the widget-space rectangles based on incoming image-space data."""
        if self.pixmap.isNull(): return

        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.width() == 0: return

        scale_w = pixmap_rect.width() / self.pixmap.width()
        scale_h = pixmap_rect.height() / self.pixmap.height()

        def to_widget_space(img_rect_dict):
            # The data from JSON is a dict, not a QRect
            img_rect = QRect(img_rect_dict['x'], img_rect_dict['y'], img_rect_dict['width'], img_rect_dict['height'])
            widget_x = pixmap_rect.x() + img_rect.x() * scale_w
            widget_y = pixmap_rect.y() + img_rect.y() * scale_h
            widget_w = img_rect.width() * scale_w
            widget_h = img_rect.height() * scale_h
            return QRectF(widget_x, widget_y, widget_w, widget_h)

        self.left_rect_widget = to_widget_space(rects_data['left'])
        self.right_rect_widget = to_widget_space(rects_data['right'])
        self._update_split_page_handles()
        self.update()

    def reset_split_rects_to_default(self):
        """Public method to allow MainWindow to reset the rects."""
        self._reset_page_split_rects()
        self.update()

    # --- Event Handlers ---
    def enterEvent(self, event):
        if self.toolbar and not self.pixmap.isNull():
            is_dragging = self.active_handle is not None and self.active_handle != "pan"
            if not is_dragging:
                self._show_toolbar_animated()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.toolbar:
            self.toolbar_hide_timer.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.is_loading:
            self._draw_loading_animation(painter)
            return

        if self.display_pixmap.isNull():
            return

        pixmap_rect_unrotated = self._get_pixmap_rect_in_widget()

        if self.interaction_mode == InteractionMode.ROTATING:
            crop_frame = pixmap_rect_unrotated
            painter.save()
            path = QPainterPath()
            path.addRect(QRectF(self.rect()))
            path.addRect(crop_frame)
            painter.fillPath(path, QBrush(QColor(0, 0, 0, 128)))
            painter.setClipRect(crop_frame)
            zoom_factor = self._calculate_rotation_zoom()
            center = crop_frame.center()
            painter.translate(center)
            painter.scale(zoom_factor, zoom_factor)
            painter.rotate(self.rotation_angle)
            painter.translate(-center)
            painter.drawPixmap(pixmap_rect_unrotated.toRect(), self.display_pixmap)
            painter.restore()
            self._draw_rotation_ui(painter, pixmap_rect_unrotated)
        else:
            painter.drawPixmap(pixmap_rect_unrotated.toRect(), self.display_pixmap)
            if not self.is_zoomed:
                if self.interaction_mode == InteractionMode.PAGE_SPLITTING:
                    self._draw_page_splitting_ui(painter)
                elif self.interaction_mode == InteractionMode.CROPPING:
                    self._draw_cropping_ui(painter, pixmap_rect_unrotated)

        if self.scan_line_animation.state() == QPropertyAnimation.Running:
            self._draw_border_animation(painter, pixmap_rect_unrotated)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reset_view()
        if self.toolbar and self.toolbar.isVisible():
            self._update_toolbar_position()

    def wheelEvent(self, event):
        if self.pixmap.isNull() or self.interaction_mode in [InteractionMode.SPLITTING, InteractionMode.ROTATING, InteractionMode.PAGE_SPLITTING]:
            super().wheelEvent(event)
            return

        if self.interaction_mode != InteractionMode.PANNING:
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        new_zoom = self._zoom_level * factor
        
        if new_zoom < fit_zoom:
            self.is_zoomed = False
            self.interaction_mode = InteractionMode.CROPPING
            self.pan_offset = QPointF()
            self.set_zoom_level(fit_zoom)
            self.zoom_state_changed.emit(False)
            self._enter_cropping_mode()
        else:
            self.set_zoom_level(min(new_zoom, 5.0)) # Clamp max zoom
        self.update()
        
    def mouseDoubleClickEvent(self, event):
        if self.pixmap.isNull(): return
        
        self.is_zoomed = not self.is_zoomed
        self.zoom_state_changed.emit(self.is_zoomed)
        self.scan_line_animation.stop()
        
        start_zoom = self._zoom_level
        fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        end_zoom = fit_zoom * 1.5 if self.is_zoomed else fit_zoom

        self.interaction_mode = InteractionMode.PANNING if self.is_zoomed else InteractionMode.CROPPING

        self.zoom_animation.stop()
        self.zoom_animation.setStartValue(start_zoom)
        self.zoom_animation.setEndValue(end_zoom)
        self.zoom_animation.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.active_handle = None
            if self.is_zoomed:
                if self.interaction_mode == InteractionMode.PANNING:
                    self.active_handle = "pan"
            elif self.interaction_mode == InteractionMode.PAGE_SPLITTING:
                self.active_handle = self._get_split_page_handle_at(event.pos())
            elif self.interaction_mode == InteractionMode.ROTATING:
                 handle_rect = self._get_rotation_handle_rect()
                 if handle_rect.contains(event.pos()):
                     self.active_handle = "rotate"
                     self.is_dragging_rotate_handle = True
                     self.rotation_on_press = self.rotation_angle
                     self.drag_start_pos = event.pos()
            elif self.interaction_mode == InteractionMode.CROPPING:
                self.active_handle = self._get_handle_at(event.pos())
                if not self.active_handle and self.crop_rect_widget.contains(event.pos()):
                    self.active_handle = "move"
            
            if self.active_handle:
                self.last_mouse_pos = event.pos()
                if self.active_handle != "pan":
                    self._hide_toolbar_animated()

    def mouseMoveEvent(self, event):
        if not self.active_handle:
            cursor = Qt.ArrowCursor
            if not self.is_zoomed:
                if self.interaction_mode == InteractionMode.PAGE_SPLITTING:
                    handle = self._get_split_page_handle_at(event.pos())
                    if handle:
                        if handle[1] in ["top_left", "bottom_right"]: cursor = Qt.SizeFDiagCursor
                        elif handle[1] in ["top_right", "bottom_left"]: cursor = Qt.SizeBDiagCursor
                        elif handle[1] in ["top", "bottom"]: cursor = Qt.SizeVerCursor
                        elif handle[1] in ["left", "right"]: cursor = Qt.SizeHorCursor
                        elif handle[1] == "move": cursor = Qt.SizeAllCursor
                elif self.interaction_mode == InteractionMode.ROTATING:
                    if self._get_rotation_handle_rect().contains(event.pos()): cursor = Qt.SizeHorCursor
                elif self.interaction_mode == InteractionMode.CROPPING:
                    handle = self._get_handle_at(event.pos())
                    if handle in ["top_left", "bottom_right"]: cursor = Qt.SizeFDiagCursor
                    elif handle in ["top_right", "bottom_left"]: cursor = Qt.SizeBDiagCursor
                    elif handle in ["top", "bottom"]: cursor = Qt.SizeVerCursor
                    elif handle in ["left", "right"]: cursor = Qt.SizeHorCursor
            self.setCursor(cursor)
            return

        delta = QPointF(event.pos() - self.last_mouse_pos)
        
        if self.active_handle == "rotate":
            self.crop_adjustment_started.emit()
            sensitivity = 90.0 / self.width() 
            dx = event.pos().x() - self.drag_start_pos.x()
            self.rotation_angle = self.rotation_on_press + dx * sensitivity
            self.rotation_angle = max(-45.0, min(45.0, self.rotation_angle))
        elif self.active_handle == "pan":
            self.pan_offset += delta
            self._clamp_pan_offset()
        elif self.interaction_mode == InteractionMode.PAGE_SPLITTING and self.active_handle:
            self.crop_adjustment_started.emit()
            self._move_split_page_handle(delta)
        elif self.active_handle in self.crop_handles.keys() or self.active_handle == "move":
            self.crop_adjustment_started.emit()
            self._move_crop_handle(delta)
        
        self.last_mouse_pos = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.rect().contains(event.pos()):
                self._show_toolbar_animated()
            if self.active_handle == "rotate":
                if abs(self.rotation_angle) > 0.1: 
                    self.rotation_finished.emit(self.image_path, self.rotation_angle)
                self.is_dragging_rotate_handle = False
            self.active_handle = None

    # --- Private Helper Methods ---
    def _hide_toolbar_animated(self):
        if self.toolbar:
            self.toolbar_animation.stop()
            self.toolbar_animation.setStartValue(self.toolbar_opacity_effect.opacity())
            self.toolbar_animation.setEndValue(0.0)
            self.toolbar_animation.start()
            
    def _update_toolbar_position(self):
        if self.toolbar:
            x = (self.width() - self.toolbar.width()) / 2
            y = self.height() - self.toolbar.height() - 15
            self.toolbar.move(int(x), int(y))

    def _calculate_rotation_zoom(self):
        if self.pixmap.isNull() or self.rotation_angle == 0: return 1.0
        w, h = self.pixmap.width(), self.pixmap.height()
        angle_rad = abs(math.radians(self.rotation_angle))
        if w <= 0 or h <= 0: return 1.0
        cosa, sina = math.cos(angle_rad), math.sin(angle_rad)
        zoom_factor_w = cosa + (h / w) * sina if w > 0 else 1
        zoom_factor_h = (w / h) * sina + cosa if h > 0 else 1
        return max(zoom_factor_w, zoom_factor_h)

    def _enter_cropping_mode(self):
        if self.pixmap.isNull(): return
        self.interaction_mode = InteractionMode.CROPPING
        pixmap_rect = self._get_pixmap_rect_in_widget()
        self.crop_rect_widget = pixmap_rect.toRect()
        self._update_crop_handles()
        self.update()

    def _on_zoom_animation_finished(self):
        if not self.is_zoomed and self.interaction_mode not in [InteractionMode.SPLITTING, InteractionMode.ROTATING, InteractionMode.PAGE_SPLITTING]:
            self.pan_offset = QPointF()
            self._enter_cropping_mode()
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

    def _update_split_page_handles(self):
        s = 10; s2 = s // 2
        for side, r in [("left", self.left_rect_widget), ("right", self.right_rect_widget)]:
            handles = {
                "top_left": QRectF(r.left() - s2, r.top() - s2, s, s),
                "top_right": QRectF(r.right() - s2, r.top() - s2, s, s),
                "bottom_left": QRectF(r.left() - s2, r.bottom() - s2, s, s),
                "bottom_right": QRectF(r.right() - s2, r.bottom() - s2, s, s),
                "top": QRectF(r.center().x() - s2, r.top() - s2, s, s),
                "bottom": QRectF(r.center().x() - s2, r.bottom() - s2, s, s),
                "left": QRectF(r.left() - s2, r.center().y() - s2, s, s),
                "right": QRectF(r.right() - s2, r.center().y() - s2, s, s),
            }
            if side == "left": self.left_handles = handles
            else: self.right_handles = handles

    def _get_handle_at(self, pos):
        for handle, rect in self.crop_handles.items():
            if rect.adjusted(-4, -4, 4, 4).contains(pos): return handle
        return None
        
    def _get_split_page_handle_at(self, pos):
        for side, handles in [("left", self.left_handles), ("right", self.right_handles)]:
            for name, rect in handles.items():
                if rect.adjusted(-4, -4, 4, 4).contains(pos): return (side, name)
        if self.left_rect_widget.contains(pos): return ("left", "move")
        if self.right_rect_widget.contains(pos): return ("right", "move")
        return None

    def _move_crop_handle(self, delta):
        r = QRectF(self.crop_rect_widget)
        pixmap_rect = self._get_pixmap_rect_in_widget()
        if self.active_handle == "move":
            dx, dy = delta.x(), delta.y()
            if dx < 0: dx = max(dx, pixmap_rect.left() - r.left())
            elif dx > 0: dx = min(dx, pixmap_rect.right() - r.right())
            if dy < 0: dy = max(dy, pixmap_rect.top() - r.top())
            elif dy > 0: dy = min(dy, pixmap_rect.bottom() - r.bottom())
            r.translate(dx, dy)
        else:
            if "left" in self.active_handle: r.setLeft(r.left() + delta.x())
            if "right" in self.active_handle: r.setRight(r.right() + delta.x())
            if "top" in self.active_handle: r.setTop(r.top() + delta.y())
            if "bottom" in self.active_handle: r.setBottom(r.bottom() + delta.y())
            r.setLeft(max(r.left(), pixmap_rect.left())); r.setRight(min(r.right(), pixmap_rect.right()))
            r.setTop(max(r.top(), pixmap_rect.top())); r.setBottom(min(r.bottom(), pixmap_rect.bottom()))
        if r.width() < 20:
            if "left" in self.active_handle: r.setLeft(r.right() - 20)
            else: r.setRight(r.left() + 20)
        if r.height() < 20:
            if "top" in self.active_handle: r.setTop(r.bottom() - 20)
            else: r.setBottom(r.top() + 20)
        self.crop_rect_widget = r.toRect()
        self._update_crop_handles()

    def _move_split_page_handle(self, delta):
        side, handle_name = self.active_handle
        r = self.left_rect_widget if side == "left" else self.right_rect_widget
        pixmap_rect = self._get_pixmap_rect_in_widget()

        if handle_name == "move":
            dx, dy = delta.x(), delta.y()
            if dx < 0: dx = max(dx, pixmap_rect.left() - r.left())
            elif dx > 0: dx = min(dx, pixmap_rect.right() - r.right())
            if dy < 0: dy = max(dy, pixmap_rect.top() - r.top())
            elif dy > 0: dy = min(dy, pixmap_rect.bottom() - r.bottom())
            r.translate(dx, dy)
        else:
            if "left" in handle_name: r.setLeft(r.left() + delta.x())
            if "right" in handle_name: r.setRight(r.right() + delta.x())
            if "top" in handle_name: r.setTop(r.top() + delta.y())
            if "bottom" in handle_name: r.setBottom(r.bottom() + delta.y())
            r.setLeft(max(r.left(), pixmap_rect.left())); r.setRight(min(r.right(), pixmap_rect.right()))
            r.setTop(max(r.top(), pixmap_rect.top())); r.setBottom(min(r.bottom(), pixmap_rect.bottom()))

        if r.width() < 20:
            if "left" in handle_name: r.setLeft(r.right() - 20)
            else: r.setRight(r.left() + 20)
        if r.height() < 20:
            if "top" in handle_name: r.setTop(r.bottom() - 20)
            else: r.setBottom(r.top() + 20)

        if side == "left": self.left_rect_widget = r
        else: self.right_rect_widget = r
        self._update_split_page_handles()

    def _reset_page_split_rects(self):
        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.isEmpty(): return

        page_width = pixmap_rect.width() * 0.48
        page_height = pixmap_rect.height() * 0.95
        center_y = pixmap_rect.center().y()

        self.left_rect_widget = QRectF(
            pixmap_rect.left() + pixmap_rect.width() * 0.02,
            center_y - page_height / 2, page_width, page_height)

        self.right_rect_widget = QRectF(
            pixmap_rect.right() - pixmap_rect.width() * 0.02 - page_width,
            center_y - page_height / 2, page_width, page_height)

        self._update_split_page_handles()

    def _start_scan_line_animation(self):
        self.scan_line_animation.stop()
        self.scan_line_animation.setStartValue(0.0)
        self.scan_line_animation.setEndValue(1.0)
        self.scan_line_animation.start()
        
    def _update_loading_animation(self):
        self.loading_animation_angle = (self.loading_animation_angle + 10) % 360
        self.update()

    def _get_rotation_handle_rect(self):
        slider_width = self.width() * 0.6; slider_x = (self.width() - slider_width) / 2
        slider_y = self.height() - 150
        handle_pos_ratio = (self.rotation_angle + 45) / 90.0
        handle_x = slider_x + slider_width * handle_pos_ratio
        handle_size = 24
        return QRectF(handle_x - handle_size/2, slider_y - handle_size/2, handle_size, handle_size)
        
    # --- Drawing Methods ---
    def _draw_loading_animation(self, painter):
        side = min(self.width(), self.height()); diameter = side * 0.2
        pen_width = max(2, int(diameter * 0.1))
        rect = QRectF((self.width()-diameter)/2, (self.height()-diameter)/2, diameter, diameter)
        pen = QPen(self.accent_color, pen_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, self.loading_animation_angle * 16, 90 * 16)

    def _draw_border_animation(self, painter, rect):
        progress = self._scan_line_progress
        if progress in [0, 1]: return
        scan_y = rect.top() + rect.height() * progress
        line_height = rect.height() * 0.1
        grad = QLinearGradient(rect.left(), scan_y - line_height, rect.left(), scan_y)
        c1 = QColor(self.accent_color); c1.setAlpha(0)
        c2 = QColor(self.accent_color); c2.setAlpha(200)
        grad.setColorAt(0, c1); grad.setColorAt(1, c2)
        painter.fillRect(QRectF(rect.left(), scan_y - line_height, rect.width(), line_height), grad)
        painter.setPen(QPen(self.accent_color, 2));
        painter.drawLine(QPointF(rect.left(), scan_y), QPointF(rect.right(), scan_y))

    def _draw_cropping_ui(self, painter, pixmap_rect):
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        path.addRect(QRectF(self.crop_rect_widget))
        painter.fillPath(path, QBrush(QColor(0, 0, 0, 128)))
        painter.setPen(QPen(self.accent_color, 2, Qt.DashLine))
        painter.drawRect(self.crop_rect_widget)
        painter.setPen(Qt.NoPen); painter.setBrush(self.accent_color)
        for rect in self.crop_handles.values():
            painter.drawRect(rect)

    def _draw_page_splitting_ui(self, painter):
        # Dim the area outside the selection rectangles
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        path.addRect(self.left_rect_widget)
        path.addRect(self.right_rect_widget)
        painter.fillPath(path, QBrush(QColor(0, 0, 0, 100)))

        # Draw left rectangle
        painter.setPen(QPen(self.left_page_color, 2, Qt.SolidLine))
        painter.drawRect(self.left_rect_widget)
        painter.setBrush(self.left_page_color)
        for handle in self.left_handles.values():
            painter.drawRect(handle)

        # Draw right rectangle
        painter.setPen(QPen(self.right_page_color, 2, Qt.SolidLine))
        painter.drawRect(self.right_rect_widget)
        painter.setBrush(self.right_page_color)
        for handle in self.right_handles.values():
            painter.drawRect(handle)

    def _draw_rotation_ui(self, painter, pixmap_rect_unrotated):
        if pixmap_rect_unrotated.isEmpty(): return
        painter.setPen(QPen(self.tertiary_color, 2, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(pixmap_rect_unrotated)
        slider_width = self.width() * 0.6; slider_height = 4
        slider_x = (self.width() - slider_width) / 2; slider_y = self.height() - 150
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.tertiary_color).lighter(120))
        painter.drawRoundedRect(QRectF(slider_x, slider_y - slider_height/2, slider_width, slider_height), 2, 2)
        painter.setBrush(QColor(self.accent_color))
        painter.drawRect(QRectF(self.width()/2 - 1, slider_y - 8, 2, 16))
        handle_rect = self._get_rotation_handle_rect()
        painter.setBrush(self.accent_color)
        painter.drawEllipse(handle_rect)
        font = painter.font(); font.setBold(True); font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(self.accent_color)
        painter.drawText(QRectF(0, handle_rect.bottom(), self.width(), 20), Qt.AlignCenter, f"{self.rotation_angle:.1f}°")