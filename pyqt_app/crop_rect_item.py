from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PyQt6.QtGui import QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QRectF, QPointF

class CropRectItem(QGraphicsRectItem):
    def __init__(self, parent=None, boundary_rect=None):
        super().__init__(parent)
        self.setPen(QPen(QColor(0, 123, 255, 200), 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(0, 123, 255, 50)))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        self.boundary_rect = boundary_rect
        self.handles = {}
        self.handle_size = 20.0  # Increased for better usability
        self.selected_handle = None
        self._create_handles()
        self.update_handles_pos()

    def _create_handles(self):
        """Create resize handles for the crop rectangle."""
        positions = {
            'tl': (0.0, 0.0), 't': (0.5, 0.0), 'tr': (1.0, 0.0),
            'l': (0.0, 0.5), 'r': (1.0, 0.5),
            'bl': (0.0, 1.0), 'b': (0.5, 1.0), 'br': (1.0, 1.0)
        }
        for key, pos in positions.items():
            handle = QGraphicsRectItem(self)
            handle.setBrush(QBrush(QColor("#007BFF")))
            handle.setPen(QPen(QColor("white"), 1))
            handle.setData(0, key) # Store the handle's key
            handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.handles[key] = handle

    def update_handles_pos(self):
        """Update positions of the resize handles based on the main rectangle's geometry."""
        rect = self.rect()
        hs = self.handle_size
        hsh = hs / 2 # half handle size

        self.handles['tl'].setRect(QRectF(rect.left() - hsh, rect.top() - hsh, hs, hs))
        self.handles['t'].setRect(QRectF(rect.center().x() - hsh, rect.top() - hsh, hs, hs))
        self.handles['tr'].setRect(QRectF(rect.right() - hsh, rect.top() - hsh, hs, hs))
        self.handles['l'].setRect(QRectF(rect.left() - hsh, rect.center().y() - hsh, hs, hs))
        self.handles['r'].setRect(QRectF(rect.right() - hsh, rect.center().y() - hsh, hs, hs))
        self.handles['bl'].setRect(QRectF(rect.left() - hsh, rect.bottom() - hsh, hs, hs))
        self.handles['b'].setRect(QRectF(rect.center().x() - hsh, rect.bottom() - hsh, hs, hs))
        self.handles['br'].setRect(QRectF(rect.right() - hsh, rect.bottom() - hsh, hs, hs))

    def hoverMoveEvent(self, event):
        """Change cursor shape when hovering over handles."""
        handle_cursors = {
            'tl': Qt.CursorShape.SizeFDiagCursor, 'tr': Qt.CursorShape.SizeBDiagCursor,
            'bl': Qt.CursorShape.SizeBDiagCursor, 'br': Qt.CursorShape.SizeFDiagCursor,
            't': Qt.CursorShape.SizeVerCursor, 'b': Qt.CursorShape.SizeVerCursor,
            'l': Qt.CursorShape.SizeHorCursor, 'r': Qt.CursorShape.SizeHorCursor,
        }
        for key, handle in self.handles.items():
            if handle.isUnderMouse():
                self.setCursor(handle_cursors[key])
                return
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        """Check if a handle is selected."""
        self.selected_handle = None
        for key, handle in self.handles.items():
            if handle.isUnderMouse():
                self.selected_handle = key
                self.press_pos = event.pos()
                self.press_rect = self.rect()
                break
        if not self.selected_handle:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Move or resize the rectangle."""
        if self.selected_handle:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

            new_rect = QRectF(self.press_rect)
            delta = event.pos() - self.press_pos

            # Adjust rect based on which handle is selected
            if 'l' in self.selected_handle: new_rect.setLeft(self.press_rect.left() + delta.x())
            if 'r' in self.selected_handle: new_rect.setRight(self.press_rect.right() + delta.x())
            if 't' in self.selected_handle: new_rect.setTop(self.press_rect.top() + delta.y())
            if 'b' in self.selected_handle: new_rect.setBottom(self.press_rect.bottom() + delta.y())

            # Constrain the new rect within the boundary
            if self.boundary_rect:
                if new_rect.left() < self.boundary_rect.left(): new_rect.setLeft(self.boundary_rect.left())
                if new_rect.right() > self.boundary_rect.right(): new_rect.setRight(self.boundary_rect.right())
                if new_rect.top() < self.boundary_rect.top(): new_rect.setTop(self.boundary_rect.top())
                if new_rect.bottom() > self.boundary_rect.bottom(): new_rect.setBottom(self.boundary_rect.bottom())

            self.prepareGeometryChange()
            self.setRect(new_rect.normalized()) # normalized to fix inverted rect
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.selected_handle = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        """Constrain movement of the entire rectangle."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            if self.boundary_rect:
                # The value is the new top-left position of the item in parent coords
                new_rect = self.rect()
                new_rect.moveTo(new_pos)

                if new_rect.left() < self.boundary_rect.left(): new_pos.setX(self.boundary_rect.left())
                if new_rect.top() < self.boundary_rect.top(): new_pos.setY(self.boundary_rect.top())
                if new_rect.right() > self.boundary_rect.right(): new_pos.setX(self.boundary_rect.right() - new_rect.width())
                if new_rect.bottom() > self.boundary_rect.bottom(): new_pos.setY(self.boundary_rect.bottom() - new_rect.height())
            return new_pos
        return super().itemChange(change, value)

    def setRect(self, rect):
        super().setRect(rect)
        self.update_handles_pos()

    def get_crop_coords_in_pixmap(self, pixmap_item):
        """
        Translates the crop rectangle's scene coordinates to the pixmap's local pixel coordinates.
        """
        crop_rect_in_scene = self.mapToScene(self.rect()).boundingRect()
        crop_rect_in_pixmap_item = pixmap_item.mapFromScene(crop_rect_in_scene).boundingRect()
        return crop_rect_in_pixmap_item
