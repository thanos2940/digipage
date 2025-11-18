import sys
import os
import math
from PySide6.QtWidgets import QWidget, QApplication, QPushButton, QVBoxLayout, QFrame
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QLinearGradient
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, Slot, QPropertyAnimation, QEasingCurve, QRectF, QPointF, QTimer, Property, QEvent

class InteractionMode:
    """Defines the exclusive state of user interaction with the viewer."""
    CROPPING = 1
    SPLITTING = 2
    PANNING = 3
    ROTATING = 4
    PAGE_SPLITTING = 5
    PAGE_SPLIT_ROTATING = 6

class ImageViewer(QWidget):
    """
    A custom widget for displaying and interacting with images.
    Handles loading, displaying, scaling, panning, cropping, splitting, and animations.
    """
    load_requested = Signal(str, bool)
    image_loaded_for_layout = Signal(str) # Emitted when the viewer is ready for a layout
    crop_adjustment_started = Signal()
    zoom_state_changed = Signal(bool)
    rotation_finished = Signal(str, float)
    layout_changed = Signal()
    crop_adjustment_finished = Signal()
    rotation_changed_by_drag = Signal()

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

        # Interaction state management
        self.interaction_mode = InteractionMode.CROPPING
        self.is_zoomed = False
        self.active_handle = None
        self.last_mouse_pos = QPoint()
        self.pan_offset = QPointF()
        self.interaction_mode_before_zoom = None
        
        # Cropping/Splitting/Rotating state
        self.crop_rect_widget = QRect()
        self.crop_handles = {}
        self.split_line_x_ratio = 0.5
        self.is_dragging_split_line = False
        self.is_dragging_rotate_handle = False
        self.rotation_on_press = 0.0
        self.drag_start_pos = QPoint()

        # Page Splitting state
        self.left_rect_widget = QRectF()
        self.right_rect_widget = QRectF()
        self.page_split_handles = {}
        self._pending_layout_ratios = None
        self.current_layout_ratios = None
        self.rotating_page = None # 'left' or 'right'
        self.rotation_on_press_page = 0.0

        # Animation properties
        self._scan_line_progress = 0.0
        self._zoom_level = 1.0
        self.is_loading = False
        self.loading_animation_angle = 0
        
        self.scan_line_animation = QPropertyAnimation(self, b"scan_line_progress", self)
        self.scan_line_animation.setDuration(800)
        self.scan_line_animation.setEasingCurve(QEasingCurve.InOutCubic)

        self.zoom_animation = QPropertyAnimation(self, b"zoom_level", self)
        self.zoom_animation.setDuration(300) 
        self.zoom_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.zoom_animation.finished.connect(self._on_zoom_animation_finished)

        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self._update_loading_animation)
        
        self.loading_animation_delay_timer = QTimer(self)
        self.loading_animation_delay_timer.setSingleShot(True)
        self.loading_animation_delay_timer.setInterval(250)
        self.loading_animation_delay_timer.timeout.connect(self._show_loading_animation)

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
        self.is_loading = False
        self.loading_timer.stop()
        self.loading_animation_delay_timer.stop()
        self.pixmap = QPixmap()
        self.display_pixmap = QPixmap()
        self.left_rect_widget = QRectF()
        self.right_rect_widget = QRectF()
        self.current_layout_ratios = None
        self.update()

    def request_image_load(self, path, force_reload=False, show_loading_animation=True):
        if self.image_path == path and not self.pixmap.isNull() and not force_reload:
            return
        if self._loading_path == path and not force_reload:
            return
            
        self._loading_path = path

        # Stop any pending animations for the old image
        self.loading_animation_delay_timer.stop()
        self.is_loading = False
        
        if show_loading_animation:
            self.loading_animation_delay_timer.start()

        # Don't clear the old pixmap here. Instead, we'll do a direct swap in
        # on_image_loaded to prevent a black flicker.
        self.update()
        
        if path is None:
            self.on_image_loaded(None, QPixmap())
        else:
            self.load_requested.emit(path, force_reload)

    @Slot()
    def _show_loading_animation(self):
        """Activates the loading animation if the delay has passed."""
        self.is_loading = True
        self.loading_timer.start(25)
        self.update()

    @Slot(str, QPixmap)
    def on_image_loaded(self, path, pixmap):
        self.loading_animation_delay_timer.stop()
        self.is_loading = False
        self.loading_timer.stop()

        if path != self._loading_path:
            return

        # Now we perform the swap. First, clear any old layout data.
        self.left_rect_widget = QRectF()
        self.right_rect_widget = QRectF()
        self.current_layout_ratios = None
            
        self.pixmap = pixmap
        self.image_path = path 
        self._loading_path = None 
        self.rotation_angle = 0

        self.reset_view()

        if not self.pixmap.isNull():
            if self.interaction_mode == InteractionMode.PAGE_SPLITTING:
                # Tell the controller that the image is loaded and ready for a layout
                self.image_loaded_for_layout.emit(path)
            
            self._start_scan_line_animation()
    
        self.update()
    
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
        else:
            self.crop_rect_widget = QRect()

        if self.interaction_mode != InteractionMode.PAGE_SPLITTING:
            self.left_rect_widget = QRectF()
            self.right_rect_widget = QRectF()

    def set_splitting_mode(self, enabled):
        if self.pixmap.isNull(): return

        if enabled:
            if self.zoom_animation.state() == QPropertyAnimation.Running:
                self.zoom_animation.stop()

            self.interaction_mode = InteractionMode.SPLITTING
            self.is_zoomed = False
            self.zoom_state_changed.emit(False)
            
            self.pan_offset = QPointF()
            fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
            
            self.set_zoom_level(fit_zoom)
            self.split_line_x_ratio = 0.5
            self.crop_rect_widget = QRect()
        else:
            self._enter_cropping_mode()
        
        self.update()

    def set_page_split_rotating_mode(self, page, enabled):
        if self.pixmap.isNull():
            return
        if enabled:
            self.interaction_mode = InteractionMode.PAGE_SPLIT_ROTATING
            self.rotating_page = page
        else:
            self.interaction_mode = InteractionMode.PAGE_SPLITTING
            self.rotating_page = None
        self.update()
        
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

    def get_split_x_in_image_space(self):
        if self.pixmap.isNull(): return None
        return int(self.split_line_x_ratio * self.pixmap.width())

    def set_page_splitting_mode(self, enabled):
        if enabled:
            self.interaction_mode = InteractionMode.PAGE_SPLITTING
            self.is_zoomed = False
            self.zoom_state_changed.emit(False)
            self.reset_view()
        else:
            self.interaction_mode = InteractionMode.CROPPING
            self.reset_view()
        self.update()

    def set_layout_ratios(self, layout_data):
        """
        Sets the position of the two page-splitting rectangles based on
        relative coordinates (ratios of the image dimensions).
        """
        if self.pixmap.isNull():
            self._pending_layout_ratios = layout_data
            return

        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.isEmpty() or not layout_data:
            # When no layout is provided, ensure the view is blank
            self.left_rect_widget = QRectF()
            self.right_rect_widget = QRectF()
            self.current_layout_ratios = None
            self.update()
            return

        self.current_layout_ratios = layout_data
        left_ratios = layout_data['left']
        right_ratios = layout_data['right']

        self.left_rect_widget = QRectF(
            pixmap_rect.x() + pixmap_rect.width() * left_ratios['x'],
            pixmap_rect.y() + pixmap_rect.height() * left_ratios['y'],
            pixmap_rect.width() * left_ratios['w'],
            pixmap_rect.height() * left_ratios['h']
        )
        self.right_rect_widget = QRectF(
            pixmap_rect.x() + pixmap_rect.width() * right_ratios['x'],
            pixmap_rect.y() + pixmap_rect.height() * right_ratios['y'],
            pixmap_rect.width() * right_ratios['w'],
            pixmap_rect.height() * right_ratios['h']
        )
        self._update_page_split_handles()
        self.update()

    def get_layout_ratios(self):
        """
        Returns the relative positions (ratios) of the page-splitting
        rectangles, suitable for saving to JSON.
        """
        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.isEmpty() or self.left_rect_widget.isEmpty() or self.right_rect_widget.isEmpty():
            # If we don't have a layout, return the default one based on current view
            if self.pixmap.isNull(): return None
            
            rect_h = 0.95
            rect_y = (1.0 - rect_h) / 2

            left_w = 0.46
            left_x = 0.02

            right_w = 0.46
            right_x = 1.0 - 0.46 - 0.02
            
            return {
                'left': {'x': left_x, 'y': rect_y, 'w': left_w, 'h': rect_h},
                'right': {'x': right_x, 'y': rect_y, 'w': right_w, 'h': rect_h},
                'rotation_left': 0.0,
                'rotation_right': 0.0
            }


        def get_ratios(widget_rect):
            if pixmap_rect.width() == 0 or pixmap_rect.height() == 0:
                return {'x': 0, 'y': 0, 'w': 0, 'h': 0}
            return {
                'x': (widget_rect.x() - pixmap_rect.x()) / pixmap_rect.width(),
                'y': (widget_rect.y() - pixmap_rect.y()) / pixmap_rect.height(),
                'w': widget_rect.width() / pixmap_rect.width(),
                'h': widget_rect.height() / pixmap_rect.height(),
            }

        return {
            'left': get_ratios(self.left_rect_widget),
            'right': get_ratios(self.right_rect_widget)
        }

    # --- Event Handlers ---
    def paintEvent(self, event):
        super().paintEvent(event)
        
        painter = QPainter()
        painter.begin(self)
        try:
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
                    if self.interaction_mode == InteractionMode.SPLITTING:
                        self._draw_splitting_ui(painter, pixmap_rect_unrotated)
                    elif self.interaction_mode == InteractionMode.CROPPING:
                        self._draw_cropping_ui(painter, pixmap_rect_unrotated)
                    elif self.interaction_mode == InteractionMode.PAGE_SPLITTING:
                        self._draw_page_splitting_ui(painter, pixmap_rect_unrotated)
                    elif self.interaction_mode == InteractionMode.PAGE_SPLIT_ROTATING:
                        self._draw_page_splitting_ui(painter, pixmap_rect_unrotated)
                        self._draw_page_split_rotation_ui(painter)

            if self.scan_line_animation.state() == QPropertyAnimation.Running:
                self._draw_border_animation(painter, pixmap_rect_unrotated)
        finally:
            painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reset_view()

    def wheelEvent(self, event):
        if self.pixmap.isNull() or self.interaction_mode in [InteractionMode.SPLITTING, InteractionMode.ROTATING]:
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

        if self.is_zoomed:
            # Store the current mode before entering panning mode
            self.interaction_mode_before_zoom = self.interaction_mode
            self.interaction_mode = InteractionMode.PANNING
        else:
            # When zooming out, the mode will be restored in _on_zoom_animation_finished
            pass
        
        start_zoom = self._zoom_level
        fit_zoom = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        end_zoom = fit_zoom * 1.5 if self.is_zoomed else fit_zoom

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
            elif self.interaction_mode == InteractionMode.SPLITTING:
                if self._is_at_split_handle(event.pos()):
                    self.active_handle = "split_line"
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
            elif self.interaction_mode == InteractionMode.PAGE_SPLITTING:
                self.active_handle = self._get_page_split_handle_at(event.pos())
                if not self.active_handle:
                    if self.left_rect_widget.contains(event.pos()):
                        self.active_handle = "left_move"
                    elif self.right_rect_widget.contains(event.pos()):
                        self.active_handle = "right_move"
                    else:
                        # Check for edge drag for rotation
                        if self._is_on_rect_edge(event.pos(), self.left_rect_widget):
                            self.active_handle = "left_edge_rotate"
                        elif self._is_on_rect_edge(event.pos(), self.right_rect_widget):
                            self.active_handle = "right_edge_rotate"

            elif self.interaction_mode == InteractionMode.PAGE_SPLIT_ROTATING:
                handle_rect = self._get_page_split_rotation_handle_rect()
                if handle_rect.contains(event.pos()):
                    self.active_handle = "page_split_rotate"
                    key = f"rotation_{self.rotating_page}"
                    self.rotation_on_press_page = self.current_layout_ratios.get(key, 0.0)
                    self.drag_start_pos = event.pos()

            if self.active_handle:
                self.last_mouse_pos = event.pos()
                self.crop_adjustment_started.emit()

    def mouseMoveEvent(self, event):
        if not self.active_handle:
            cursor = Qt.ArrowCursor
            if not self.is_zoomed:
                if self.interaction_mode == InteractionMode.SPLITTING:
                    if self._is_at_split_handle(event.pos()): cursor = Qt.SizeHorCursor
                elif self.interaction_mode == InteractionMode.ROTATING:
                    if self._get_rotation_handle_rect().contains(event.pos()): cursor = Qt.SizeHorCursor
                elif self.interaction_mode == InteractionMode.CROPPING:
                    handle = self._get_handle_at(event.pos())
                    if handle in ["top_left", "bottom_right"]: cursor = Qt.SizeFDiagCursor
                    elif handle in ["top_right", "bottom_left"]: cursor = Qt.SizeBDiagCursor
                    elif handle in ["top", "bottom"]: cursor = Qt.SizeVerCursor
                    elif handle in ["left", "right"]: cursor = Qt.SizeHorCursor
                elif self.interaction_mode == InteractionMode.PAGE_SPLITTING:
                    if self._is_on_rect_edge(event.pos(), self.left_rect_widget) or self._is_on_rect_edge(event.pos(), self.right_rect_widget):
                        cursor = Qt.CrossCursor # Using CrossCursor as a stand-in for a rotate cursor
                    else:
                        handle = self._get_page_split_handle_at(event.pos())
                        if handle:
                            if "top_left" in handle or "bottom_right" in handle: cursor = Qt.SizeFDiagCursor
                elif self.interaction_mode == InteractionMode.PAGE_SPLIT_ROTATING:
                    if self._get_page_split_rotation_handle_rect().contains(event.pos()):
                        cursor = Qt.SizeHorCursor
                        elif "top_right" in handle or "bottom_left" in handle: cursor = Qt.SizeBDiagCursor
                        elif "top" in handle or "bottom" in handle: cursor = Qt.SizeVerCursor
                        elif "left" in handle or "right" in handle: cursor = Qt.SizeHorCursor
                    elif self.left_rect_widget.contains(event.pos()) or self.right_rect_widget.contains(event.pos()):
                        cursor = Qt.SizeAllCursor

            self.setCursor(cursor)
            return

        delta = QPointF(event.pos() - self.last_mouse_pos)
        
        if self.active_handle == "rotate":
            sensitivity = 90.0 / self.width() 
            dx = event.pos().x() - self.drag_start_pos.x()
            self.rotation_angle = self.rotation_on_press + dx * sensitivity
            self.rotation_angle = max(-45.0, min(45.0, self.rotation_angle))
        elif self.active_handle == "page_split_rotate":
            if self.rotating_page:
                sensitivity = 90.0 / (self.width() * 0.6) # Sensitivity based on slider width
                dx = event.pos().x() - self.drag_start_pos.x()
                new_angle = self.rotation_on_press_page + dx * sensitivity
                new_angle = max(-45.0, min(45.0, new_angle))

                key = f"rotation_{self.rotating_page}"
                self.current_layout_ratios[key] = new_angle
                self.layout_changed.emit()
        elif self.active_handle in ["left_edge_rotate", "right_edge_rotate"]:
            rect = self.left_rect_widget if self.active_handle == "left_edge_rotate" else self.right_rect_widget
            center = rect.center()

            vec_start = self.last_mouse_pos - center
            vec_end = event.pos() - center

            angle_start = math.atan2(vec_start.y(), vec_start.x())
            angle_end = math.atan2(vec_end.y(), vec_end.x())

            angle_delta_rad = angle_end - angle_start
            angle_delta_deg = math.degrees(angle_delta_rad)

            key = 'rotation_left' if self.active_handle == "left_edge_rotate" else 'rotation_right'
            current_angle = self.current_layout_ratios.get(key, 0.0)
            new_angle = current_angle + angle_delta_deg
            self.current_layout_ratios[key] = new_angle
            self.layout_changed.emit()

        elif self.active_handle == "split_line":
            self.is_dragging_split_line = True
            pixmap_rect = self._get_pixmap_rect_in_widget()
            if pixmap_rect.width() > 0:
                self.split_line_x_ratio += delta.x() / pixmap_rect.width()
                self.split_line_x_ratio = max(0.0, min(1.0, self.split_line_x_ratio))
        elif self.active_handle == "pan":
            self.pan_offset += delta
            self._clamp_pan_offset()
        elif self.active_handle in self.crop_handles.keys() or self.active_handle == "move":
            self._move_crop_handle(delta)
        elif self.active_handle and ('left_' in self.active_handle or 'right_' in self.active_handle):
            self.layout_changed.emit()
            self._move_page_split_handle(self.active_handle, delta)
        
        self.last_mouse_pos = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.active_handle:
                self.crop_adjustment_finished.emit()

            if self.active_handle == "rotate":
                if abs(self.rotation_angle) > 0.1: 
                    self.rotation_finished.emit(self.image_path, self.rotation_angle)
                self.is_dragging_rotate_handle = False

            if self.active_handle == "page_split_rotate":
                self.layout_changed.emit() # Ensure final value is emitted

            if self.active_handle in ["left_edge_rotate", "right_edge_rotate"]:
                self.rotation_changed_by_drag.emit()

            if self.active_handle and ('left_' in self.active_handle or 'right_' in self.active_handle):
                 self.layout_changed.emit()

            self.active_handle = None
            self.is_dragging_split_line = False

    # --- Private Helper Methods ---
    def _initialize_default_layout(self):
        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.isEmpty():
            return

        rect_h = pixmap_rect.height() * 0.95
        rect_y = pixmap_rect.y() + (pixmap_rect.height() - rect_h) / 2

        left_w = pixmap_rect.width() * 0.46
        left_x = pixmap_rect.x() + pixmap_rect.width() * 0.02

        right_w = pixmap_rect.width() * 0.46
        right_x = pixmap_rect.x() + pixmap_rect.width() * (1.0 - 0.46 - 0.02)

        self.left_rect_widget = QRectF(left_x, rect_y, left_w, rect_h)
        self.right_rect_widget = QRectF(right_x, rect_y, right_w, rect_h)

        self._update_page_split_handles()
        self.update()

    def _update_page_split_handles(self):
        s = 12
        s2 = s // 2
        self.page_split_handles = {}

        for prefix, r in [('left', self.left_rect_widget), ('right', self.right_rect_widget)]:
            self.page_split_handles[f'{prefix}_top_left'] = QRectF(r.left() - s2, r.top() - s2, s, s)
            self.page_split_handles[f'{prefix}_top_right'] = QRectF(r.right() - s2, r.top() - s2, s, s)
            self.page_split_handles[f'{prefix}_bottom_left'] = QRectF(r.left() - s2, r.bottom() - s2, s, s)
            self.page_split_handles[f'{prefix}_bottom_right'] = QRectF(r.right() - s2, r.bottom() - s2, s, s)
            self.page_split_handles[f'{prefix}_top'] = QRectF(r.center().x() - s2, r.top() - s2, s, s)
            self.page_split_handles[f'{prefix}_bottom'] = QRectF(r.center().x() - s2, r.bottom() - s2, s, s)
            self.page_split_handles[f'{prefix}_left'] = QRectF(r.left() - s2, r.center().y() - s2, s, s)
            self.page_split_handles[f'{prefix}_right'] = QRectF(r.right() - s2, r.center().y() - s2, s, s)

    def _calculate_rotation_zoom(self):
        """Calculates the zoom factor needed to fill the viewport during rotation."""
        if self.pixmap.isNull() or self.rotation_angle == 0:
            return 1.0

        w = self.pixmap.width()
        h = self.pixmap.height()
        angle_rad = abs(math.radians(self.rotation_angle))
        
        if w <= 0 or h <= 0: return 1.0

        cosa = math.cos(angle_rad)
        sina = math.sin(angle_rad)

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
        if not self.is_zoomed:
            self.pan_offset = QPointF()
            # Restore the mode that was active before zooming in
            if self.interaction_mode_before_zoom is not None:
                self.interaction_mode = self.interaction_mode_before_zoom
                self.interaction_mode_before_zoom = None
            else:
                # Fallback to cropping if no mode was stored
                self.interaction_mode = InteractionMode.CROPPING

            # Refresh UI elements based on the restored mode
            if self.interaction_mode == InteractionMode.CROPPING:
                self._enter_cropping_mode()
            elif self.interaction_mode == InteractionMode.PAGE_SPLITTING:
                # Re-apply the last known layout instead of resetting to default
                if self.current_layout_ratios:
                    self.set_layout_ratios(self.current_layout_ratios)

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
        handle = self._get_handle_for_rect(pos, self.crop_rect_widget)
        if handle:
            return handle

        # If not on a handle but inside the rect, it's a move.
        if self.crop_rect_widget.contains(pos):
            return "move"

        return None
        
    def _is_at_split_handle(self, pos):
        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.isEmpty(): return False
        split_x = pixmap_rect.left() + pixmap_rect.width() * self.split_line_x_ratio
        
        if abs(pos.x() - split_x) < 10:
            if pixmap_rect.top() < pos.y() < pixmap_rect.bottom():
                return True
        return False

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
            
            r.setLeft(max(r.left(), pixmap_rect.left()))
            r.setRight(min(r.right(), pixmap_rect.right()))
            r.setTop(max(r.top(), pixmap_rect.top()))
            r.setBottom(min(r.bottom(), pixmap_rect.bottom()))

        if r.width() < 20:
            if "left" in self.active_handle: r.setLeft(r.right() - 20)
            else: r.setRight(r.left() + 20)
        if r.height() < 20:
            if "top" in self.active_handle: r.setTop(r.bottom() - 20)
            else: r.setBottom(r.top() + 20)

        self.crop_rect_widget = r.toRect()
        self._update_crop_handles()


    def _start_scan_line_animation(self):
        self.scan_line_animation.stop()
        self.scan_line_animation.setStartValue(0.0)
        self.scan_line_animation.setEndValue(1.0)
        self.scan_line_animation.start()
        
    def _update_loading_animation(self):
        self.loading_animation_angle = (self.loading_animation_angle + 10) % 360
        self.update()

    def _get_rotation_handle_rect(self):
        slider_width = self.width() * 0.6
        slider_x = (self.width() - slider_width) / 2
        slider_y = self.height() - 70 # Position relative to widget bottom

        handle_pos_ratio = (self.rotation_angle + 45) / 90.0
        handle_x = slider_x + slider_width * handle_pos_ratio
        
        handle_size = 24
        return QRectF(handle_x - handle_size/2, slider_y - handle_size/2, handle_size, handle_size)
        
    def _get_page_split_handle_at(self, pos):
        # Check right rect first, as it may be on top
        handle = self._get_handle_for_rect(pos, self.right_rect_widget, prefix="right_")
        if handle:
            return handle
            
        handle = self._get_handle_for_rect(pos, self.left_rect_widget, prefix="left_")
        if handle:
            return handle

        return None

    def _move_page_split_handle(self, handle, delta):
        pixmap_rect = self._get_pixmap_rect_in_widget()
        if pixmap_rect.isEmpty(): return # Safety check

        # Determine which rectangle we're working on
        rect_to_modify = self.left_rect_widget if 'left_' in handle else self.right_rect_widget

        # --- BUG FIX 1 & 2: Use adjust() and clamp delta BEFORE applying ---
        
        dx1, dy1, dx2, dy2 = 0, 0, 0, 0
        dx, dy = delta.x(), delta.y()

        if '_move' in handle:
            # --- Clamping logic for MOVE ---
            # Clamp horizontal movement
            if dx < 0: # Moving left
                dx = max(dx, pixmap_rect.left() - rect_to_modify.left())
            elif dx > 0: # Moving right
                dx = min(dx, pixmap_rect.right() - rect_to_modify.right())
            # Clamp vertical movement
            if dy < 0: # Moving up
                dy = max(dy, pixmap_rect.top() - rect_to_modify.top())
            elif dy > 0: # Moving down
                dy = min(dy, pixmap_rect.bottom() - rect_to_modify.bottom())
            
            dx1, dy1, dx2, dy2 = dx, dy, dx, dy
        else:
            # --- Clamping logic for RESIZE ---
            min_width = 20
            min_height = 20

            # Handle horizontal resize
            if "_left" in handle:
                # Clamp move left (don't go past pixmap left)
                dx = max(dx, pixmap_rect.left() - rect_to_modify.left())
                # Clamp move right (don't make width < min_width)
                dx = min(dx, rect_to_modify.width() - min_width)
                dx1 = dx
            elif "_right" in handle:
                # Clamp move right (don't go past pixmap right)
                dx = min(dx, pixmap_rect.right() - rect_to_modify.right())
                # Clamp move left (don't make width < min_width)
                dx = max(dx, min_width - rect_to_modify.width())
                dx2 = dx

            # Handle vertical resize
            if "_top" in handle:
                # Clamp move up (don't go past pixmap top)
                dy = max(dy, pixmap_rect.top() - rect_to_modify.top())
                # Clamp move down (don't make height < min_height)
                dy = min(dy, rect_to_modify.height() - min_height)
                dy1 = dy
            elif "_bottom" in handle:
                # Clamp move down (don't go past pixmap bottom)
                dy = min(dy, pixmap_rect.bottom() - rect_to_modify.bottom())
                # Clamp move up (don't make height < min_height)
                dy = max(dy, min_height - rect_to_modify.height())
                dy2 = dy
        
        # Apply the clamped adjustments
        rect_to_modify.adjust(dx1, dy1, dx2, dy2)
        
        # --- END BUG FIX ---

        # The old logic is now replaced by the pre-clamping
        self._update_page_split_handles()

    def _is_on_rect_edge(self, pos, rect):
        """Checks if a point is close to the boundary of a rectangle."""
        if rect.contains(pos):
            return False # Inside, not on edge

        path = QPainterPath()
        path.addRect(rect)

        stroker = QPainterPathStroker()
        stroker.setWidth(30) # 30px tolerance around the edge
        stroke = stroker.createStroke(path)

        return stroke.contains(pos)

    def _get_handle_for_rect(self, pos, rect, prefix=""):
        """
        Determines which handle or side of a rectangle is at a given position.
        Returns the handle name (e.g., 'top_left', 'left') or None.
        """
        side_tolerance = 20
        corner_tolerance = 25

        # Check corners first, as they have priority.
        is_near_top = abs(pos.y() - rect.top()) < corner_tolerance
        is_near_bottom = abs(pos.y() - rect.bottom()) < corner_tolerance
        is_near_left = abs(pos.x() - rect.left()) < corner_tolerance
        is_near_right = abs(pos.x() - rect.right()) < corner_tolerance

        if is_near_top and is_near_left: return f"{prefix}top_left"
        if is_near_top and is_near_right: return f"{prefix}top_right"
        if is_near_bottom and is_near_left: return f"{prefix}bottom_left"
        if is_near_bottom and is_near_right: return f"{prefix}bottom_right"

        # Then check for sides, but only if not at a corner.
        # This ensures that dragging the edge of the crop area is prioritized over panning.
        is_on_top_side = abs(pos.y() - rect.top()) < side_tolerance
        is_on_bottom_side = abs(pos.y() - rect.bottom()) < side_tolerance
        is_on_left_side = abs(pos.x() - rect.left()) < side_tolerance
        is_on_right_side = abs(pos.x() - rect.right()) < side_tolerance
        
        # Check that the position is within the perpendicular bounds of the side.
        in_horizontal_bounds = rect.left() - side_tolerance < pos.x() < rect.right() + side_tolerance
        in_vertical_bounds = rect.top() - side_tolerance < pos.y() < rect.bottom() + side_tolerance

        if is_on_top_side and in_horizontal_bounds: return f"{prefix}top"
        if is_on_bottom_side and in_horizontal_bounds: return f"{prefix}bottom"
        if is_on_left_side and in_vertical_bounds: return f"{prefix}left"
        if is_on_right_side and in_vertical_bounds: return f"{prefix}right"

        return None

    def _get_page_split_rotation_handle_rect(self):
        if not self.rotating_page or not self.current_layout_ratios:
            return QRectF()

        key = f"rotation_{self.rotating_page}"
        angle = self.current_layout_ratios.get(key, 0.0)

        slider_width = self.width() * 0.6
        slider_x = (self.width() - slider_width) / 2

        # Position the slider centrally below the selected rectangle
        rect_to_rotate = self.left_rect_widget if self.rotating_page == 'left' else self.right_rect_widget
        slider_y = rect_to_rotate.bottom() + 60

        handle_pos_ratio = (angle + 45) / 90.0
        handle_x = slider_x + slider_width * handle_pos_ratio

        handle_size = 24
        return QRectF(handle_x - handle_size/2, slider_y - handle_size/2, handle_size, handle_size)

    def _draw_page_split_rotation_ui(self, painter):
        if not self.rotating_page or not self.current_layout_ratios:
            return

        key = f"rotation_{self.rotating_page}"
        angle = self.current_layout_ratios.get(key, 0.0)

        rect_to_rotate = self.left_rect_widget if self.rotating_page == 'left' else self.right_rect_widget

        # Draw a highlight border around the selected crop area
        painter.setPen(QPen(self.accent_color, 4, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect_to_rotate)

        # --- Draw Slider ---
        slider_width = self.width() * 0.6
        slider_height = 4
        slider_x = (self.width() - slider_width) / 2
        slider_y = rect_to_rotate.bottom() + 60 # Position below the rectangle

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.tertiary_color).lighter(120))
        painter.drawRoundedRect(QRectF(slider_x, slider_y - slider_height/2, slider_width, slider_height), 2, 2)

        # Center marker
        painter.setBrush(QColor(self.accent_color))
        painter.drawRect(QRectF(self.width()/2 - 1, slider_y - 8, 2, 16))

        # --- Draw Handle and Text ---
        handle_rect = self._get_page_split_rotation_handle_rect()
        painter.setBrush(self.accent_color)
        painter.drawEllipse(handle_rect)

        font = painter.font(); font.setBold(True); font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(self.accent_color)
        painter.drawText(QRectF(0, handle_rect.bottom(), self.width(), 20), Qt.AlignCenter, f"{angle:.1f}°")


    # --- Drawing Methods ---
    def _draw_loading_animation(self, painter):
        side = min(self.width(), self.height())
        diameter = side * 0.2
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
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.accent_color)
        for rect in self.crop_handles.values():
            painter.drawRect(rect)

    def _draw_page_splitting_ui(self, painter, pixmap_rect):
        if self.left_rect_widget.isEmpty() or self.right_rect_widget.isEmpty() or not self.current_layout_ratios:
            return

        left_enabled = self.current_layout_ratios.get('left_enabled', True)
        right_enabled = self.current_layout_ratios.get('right_enabled', True)

        full_path = QPainterPath()
        full_path.addRect(QRectF(self.rect()))

        selection_path = QPainterPath()
        if left_enabled:
            selection_path.addRect(self.left_rect_widget)
        if right_enabled:
            selection_path.addRect(self.right_rect_widget)

        overlay_path = full_path.subtracted(selection_path)
        painter.fillPath(overlay_path, QBrush(QColor(0, 0, 0, 100)))

        # --- Left (Green) ---
        if left_enabled:
            painter.save()
            angle_left = self.current_layout_ratios.get('rotation_left', 0.0)
            center_left = self.left_rect_widget.center()
            painter.translate(center_left)
            painter.rotate(angle_left)
            painter.translate(-center_left)

            left_fill = QColor("#4EBB51"); left_fill.setAlpha(20)
            painter.fillRect(self.left_rect_widget, left_fill)
            painter.setPen(QPen(QColor("#4CAF50"), 3, Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.left_rect_widget)
            painter.restore()

        # --- Right (Red) ---
        if right_enabled:
            painter.save()
            angle_right = self.current_layout_ratios.get('rotation_right', 0.0)
            center_right = self.right_rect_widget.center()
            painter.translate(center_right)
            painter.rotate(angle_right)
            painter.translate(-center_right)

            right_fill = QColor("#F44336"); right_fill.setAlpha(20)
            painter.fillRect(self.right_rect_widget, right_fill)
            painter.setPen(QPen(QColor("#F44336"), 3, Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.right_rect_widget)
            painter.restore()

        # --- Handles ---
        painter.setPen(Qt.NoPen)
        for handle_name, handle_rect in self.page_split_handles.items():
            if 'left_' in handle_name and left_enabled:
                painter.setBrush(QColor("#4CAF50"))
                painter.drawEllipse(handle_rect)
            elif 'right_' in handle_name and right_enabled:
                painter.setBrush(QColor("#F44336"))
                painter.drawEllipse(handle_rect)

    def _draw_splitting_ui(self, painter, pixmap_rect):
        split_x = pixmap_rect.left() + pixmap_rect.width() * self.split_line_x_ratio
        right_part_rect = QRectF(split_x, pixmap_rect.top(), pixmap_rect.right() - split_x, pixmap_rect.height())
        overlay_color = QColor(self.tertiary_color)
        overlay_color.setAlpha(50)
        painter.fillRect(right_part_rect, overlay_color)
        pen = QPen(self.accent_color, 3)
        pen.setStyle(Qt.DotLine if self.is_dragging_split_line else Qt.SolidLine)
        painter.setPen(pen)
        painter.drawLine(int(split_x), int(pixmap_rect.top()), int(split_x), int(pixmap_rect.bottom()))
        handle_rect = QRectF(split_x - 5, pixmap_rect.center().y() - 20, 10, 40)
        handle_color = QColor(self.accent_color)
        handle_color.setAlpha(200)
        painter.setPen(Qt.NoPen)
        painter.setBrush(handle_color)
        painter.drawRoundedRect(handle_rect, 4, 4)

    def _draw_rotation_ui(self, painter, pixmap_rect_unrotated):
        if pixmap_rect_unrotated.isEmpty(): return

        painter.setPen(QPen(self.tertiary_color, 2, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(pixmap_rect_unrotated)

        slider_width = self.width() * 0.6
        slider_height = 4 
        slider_x = (self.width() - slider_width) / 2
        slider_y = self.height() - 70 # Adjusted position for static toolbar
        
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
