from abc import ABC, abstractmethod
import math
from PySide6.QtCore import Qt, QRect, QRectF, QPointF, Signal, QObject
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath

class InteractionHandler(QObject):
    """Abstract base class for handling mouse interactions on the canvas."""
    cursor_changed = Signal(object) # Emits a Qt.CursorShape
    
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.is_active = False

    @abstractmethod
    def on_mouse_press(self, event, image_pos):
        pass

    @abstractmethod
    def on_mouse_move(self, event, image_pos):
        pass

    @abstractmethod
    def on_mouse_release(self, event, image_pos):
        pass

    @abstractmethod
    def paint(self, painter):
        pass
    
    def reset(self):
        self.is_active = False

class PanHandler(InteractionHandler):
    """Handles image panning when zoomed in."""
    def __init__(self, canvas):
        super().__init__(canvas)
        self.last_pos = None

    def on_mouse_press(self, event, image_pos):
        if event.button() == Qt.LeftButton:
            self.last_pos = event.pos()
            self.is_active = True
            self.cursor_changed.emit(Qt.ClosedHandCursor)

    def on_mouse_move(self, event, image_pos):
        if self.is_active:
            delta = event.pos() - self.last_pos
            self.canvas.pan_offset += QPointF(delta)
            self.canvas._clamp_pan_offset()
            self.last_pos = event.pos()
            self.canvas.update()

    def on_mouse_release(self, event, image_pos):
        self.is_active = False
        self.cursor_changed.emit(Qt.OpenHandCursor)

    def paint(self, painter):
        pass # Panning doesn't draw any overlay

class CropHandler(InteractionHandler):
    """Handles defining a crop rectangle."""
    crop_changed = Signal(QRect) # Emits rect in image coordinates

    def __init__(self, canvas):
        super().__init__(canvas)
        self.crop_rect = QRect() # In Image Coordinates
        self.active_handle = None
        self.start_pos = None # For moving the whole rect
        self.handles = {}
        self.HANDLE_SIZE = 20

    def reset(self):
        super().reset()
        if not self.canvas.pixmap.isNull():
            # Default to full image
            self.crop_rect = self.canvas.pixmap.rect()

    def _get_widget_rect(self):
        return self.canvas.map_rect_to_widget(self.crop_rect)

    def _update_handles(self, rect: QRectF):
        s = 10
        s2 = s // 2
        self.handles = {
            "tl": QRectF(rect.left()-s2, rect.top()-s2, s, s),
            "tr": QRectF(rect.right()-s2, rect.top()-s2, s, s),
            "bl": QRectF(rect.left()-s2, rect.bottom()-s2, s, s),
            "br": QRectF(rect.right()-s2, rect.bottom()-s2, s, s),
            # Sides
            "l": QRectF(rect.left()-s2, rect.center().y()-s2, s, s),
            "r": QRectF(rect.right()-s2, rect.center().y()-s2, s, s),
            "t": QRectF(rect.center().x()-s2, rect.top()-s2, s, s),
            "b": QRectF(rect.center().x()-s2, rect.bottom()-s2, s, s),
        }

    def on_mouse_press(self, event, image_pos):
        if event.button() != Qt.LeftButton: return
        
        widget_pos = event.pos()
        widget_rect = self._get_widget_rect()
        self._update_handles(widget_rect)
        
        # Check handles first
        for name, rect in self.handles.items():
            if rect.contains(widget_pos):
                self.active_handle = name
                self.is_active = True
                return

        # Check inside rect for moving
        if widget_rect.contains(widget_pos):
            self.active_handle = "move"
            self.start_pos = image_pos
            self.is_active = True

    def on_mouse_move(self, event, image_pos):
        # Update Cursor
        widget_rect = self._get_widget_rect()
        self._update_handles(widget_rect)
        
        if not self.is_active:
            # Hover logic
            cursor = Qt.ArrowCursor
            for name, rect in self.handles.items():
                if rect.contains(event.pos()):
                    if name in ['tl', 'br']: cursor = Qt.SizeFDiagCursor
                    elif name in ['tr', 'bl']: cursor = Qt.SizeBDiagCursor
                    elif name in ['l', 'r']: cursor = Qt.SizeHorCursor
                    elif name in ['t', 'b']: cursor = Qt.SizeVerCursor
            if cursor == Qt.ArrowCursor and widget_rect.contains(event.pos()):
                cursor = Qt.SizeAllCursor
            self.cursor_changed.emit(cursor)
            return

        # Drag logic (in Image Coordinates)
        rect = self.crop_rect
        
        if self.active_handle == "move":
            delta = image_pos - self.start_pos
            rect.translate(delta.toPoint())
            self.start_pos = image_pos
        else:
            # Simple resizing logic
            if 'l' in self.active_handle: rect.setLeft(image_pos.x())
            if 'r' in self.active_handle: rect.setRight(image_pos.x())
            if 't' in self.active_handle: rect.setTop(image_pos.y())
            if 'b' in self.active_handle: rect.setBottom(image_pos.y())
        
        # Normalize and clamp
        rect = rect.normalized()
        rect = rect.intersected(self.canvas.pixmap.rect())
        self.crop_rect = rect
        self.canvas.update()

    def on_mouse_release(self, event, image_pos):
        self.is_active = False
        self.active_handle = None
        self.crop_changed.emit(self.crop_rect)

    def paint(self, painter):
        widget_rect = self._get_widget_rect()
        
        # Draw dim background
        path = QPainterPath()
        path.addRect(QRectF(self.canvas.rect()))
        path.addRect(widget_rect)
        painter.fillPath(path, QBrush(QColor(0, 0, 0, 128)))

        # Draw Selection Border
        painter.setPen(QPen(self.canvas.accent_color, 2, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(widget_rect)
        
        # Draw Handles
        self._update_handles(widget_rect)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.canvas.accent_color)
        for rect in self.handles.values():
            painter.drawRect(rect)

class RotateHandler(InteractionHandler):
    """Handles Rotation via a slider-like UI."""
    angle_changed = Signal(float)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.angle = 0.0
        self.drag_start_pos = None
        self.angle_on_press = 0.0

    def on_mouse_press(self, event, image_pos):
        handle_rect = self._get_handle_rect()
        if handle_rect.contains(event.pos()):
            self.is_active = True
            self.drag_start_pos = event.pos()
            self.angle_on_press = self.angle
            self.cursor_changed.emit(Qt.ClosedHandCursor)

    def on_mouse_move(self, event, image_pos):
        if not self.is_active:
            handle_rect = self._get_handle_rect()
            if handle_rect.contains(event.pos()):
                self.cursor_changed.emit(Qt.OpenHandCursor)
            else:
                self.cursor_changed.emit(Qt.ArrowCursor)
            return

        sensitivity = 90.0 / self.canvas.width()
        dx = event.pos().x() - self.drag_start_pos.x()
        self.angle = self.angle_on_press + dx * sensitivity
        self.angle = max(-45.0, min(45.0, self.angle))
        self.canvas.rotation_angle = self.angle # Update canvas directly for visualization
        self.canvas.update()

    def on_mouse_release(self, event, image_pos):
        if self.is_active:
            self.is_active = False
            self.cursor_changed.emit(Qt.OpenHandCursor)
            self.angle_changed.emit(self.angle)

    def _get_handle_rect(self):
        slider_width = self.canvas.width() * 0.6
        slider_x = (self.canvas.width() - slider_width) / 2
        slider_y = self.canvas.height() - 50
        
        # Map -45..45 to 0..1
        ratio = (self.angle + 45) / 90.0
        handle_x = slider_x + slider_width * ratio
        return QRectF(handle_x - 10, slider_y - 10, 20, 20)

    def paint(self, painter):
        # Draw slider track
        slider_width = self.canvas.width() * 0.6
        slider_x = (self.canvas.width() - slider_width) / 2
        slider_y = self.canvas.height() - 50
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(200, 200, 200, 100))
        painter.drawRoundedRect(QRectF(slider_x, slider_y - 2, slider_width, 4), 2, 2)
        
        # Draw Center tick
        painter.setBrush(self.canvas.accent_color)
        painter.drawRect(QRectF(self.canvas.width()/2 - 1, slider_y - 6, 2, 12))
        
        # Draw Handle
        handle_rect = self._get_handle_rect()
        painter.setBrush(self.canvas.accent_color)
        painter.drawEllipse(handle_rect)
        
        # Draw Text
        painter.setPen(self.canvas.accent_color)
        painter.drawText(QRectF(0, slider_y + 15, self.canvas.width(), 20), Qt.AlignCenter, f"{self.angle:.1f}°")