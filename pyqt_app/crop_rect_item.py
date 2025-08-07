from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PyQt6.QtGui import QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QRectF

class CropRectItem(QGraphicsRectItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPen(QPen(QColor(0, 123, 255, 200), 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(0, 123, 255, 50)))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.handles = []
        self.handle_size = 10.0
        self._create_handles()
        self.update_handles_pos()

    def _create_handles(self):
        """Create resize handles for the crop rectangle."""
        positions = [
            (0.0, 0.0), (0.5, 0.0), (1.0, 0.0), # Top
            (0.0, 0.5),             (1.0, 0.5), # Middle
            (0.0, 1.0), (0.5, 1.0), (1.0, 1.0)  # Bottom
        ]
        for pos in positions:
            handle = QGraphicsRectItem(self)
            handle.setBrush(QBrush(QColor("blue")))
            handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            # Custom data to identify handle position
            handle.setData(0, pos)
            self.handles.append(handle)

    def itemChange(self, change, value):
        """Ensure handles stay attached when the main rect is moved."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            self.update_handles_pos()
        return super().itemChange(change, value)

    def update_handles_pos(self):
        """Update positions of the resize handles."""
        rect = self.rect()
        for handle in self.handles:
            pos_ratio = handle.data(0)
            x = rect.x() + rect.width() * pos_ratio[0] - self.handle_size / 2
            y = rect.y() + rect.height() * pos_ratio[1] - self.handle_size / 2
            handle.setRect(x, y, self.handle_size, self.handle_size)

    def setRect(self, rect):
        super().setRect(rect)
        self.update_handles_pos()

    def get_crop_coords_in_pixmap(self, pixmap_item):
        """
        Translates the crop rectangle's scene coordinates to the pixmap's local pixel coordinates.
        """
        # Map the crop rectangle's bounds from its own coordinate system to the scene
        crop_rect_in_scene = self.mapToScene(self.rect()).boundingRect()

        # Map the scene rectangle to the pixmap item's coordinate system
        crop_rect_in_pixmap_item = pixmap_item.mapFromScene(crop_rect_in_scene).boundingRect()

        return crop_rect_in_pixmap_item
