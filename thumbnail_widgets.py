# In thumbnail_widgets.py
from PySide6.QtWidgets import QListView, QStyledItemDelegate, QStyle
from PySide6.QtCore import Signal, Slot, QModelIndex, QSize, Qt, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor
import config

# Define custom data roles for our model
THUMBNAIL_ROLE_BASE = Qt.UserRole
ROLE_PAIR_INDEX = THUMBNAIL_ROLE_BASE + 1       # The pair index (0, 1, 2...)
ROLE_SCANNER_MODE = THUMBNAIL_ROLE_BASE + 2     # "dual_scan" or "single_split"
ROLE_IS_SELECTED = THUMBNAIL_ROLE_BASE + 3      # bool
# --- For Image 1 (Left/Source) ---
ROLE_PATH_1 = THUMBNAIL_ROLE_BASE + 4           # Full file path
ROLE_INDEX_1 = THUMBNAIL_ROLE_BASE + 5          # Original image index (e.g., 0, 2, 4...)
ROLE_PIXMAP_1 = THUMBNAIL_ROLE_BASE + 6         # The loaded QPixmap thumbnail
ROLE_IS_LOADING_1 = THUMBNAIL_ROLE_BASE + 7     # bool
# --- For Image 2 (Right) ---
ROLE_PATH_2 = THUMBNAIL_ROLE_BASE + 8           # Full file path (if dual_scan)
ROLE_INDEX_2 = THUMBNAIL_ROLE_BASE + 9          # Original image index (e.g., 1, 3, 5...)
ROLE_PIXMAP_2 = THUMBNAIL_ROLE_BASE + 10        # The loaded QPixmap thumbnail
ROLE_IS_LOADING_2 = THUMBNAIL_ROLE_BASE + 11    # bool

class ThumbnailDelegate(QStyledItemDelegate):
    THUMB_WIDTH = 90
    THUMB_HEIGHT = 110
    PAIR_HEIGHT = 120 # 110px thumb + 10px vertical margin
    SPACING = 5       # Horizontal spacing

    def __init__(self, parent=None):
        super().__init__(parent)
        app_config = config.load_config()
        theme_name = app_config.get("theme", "Material Dark")
        self.theme = config.THEMES.get(theme_name, config.THEMES["Material Dark"])

        self.color_selected = QColor(self.theme['PRIMARY'])
        self.color_frame_border = QColor(self.theme['OUTLINE'])
        self.color_thumb_bg = QColor(self.theme['SURFACE_CONTAINER'])
        self.color_thumb_text = QColor(self.theme['ON_SURFACE_VARIANT'])

    def sizeHint(self, option, index):
        """All items have a fixed size."""
        # Width accommodates 2 thumbnails + 3 spacing gaps
        width = (self.THUMB_WIDTH * 2) + (self.SPACING * 3)
        return QSize(width, self.PAIR_HEIGHT)

    def paint(self, painter, option, index):
        """This is the main drawing function."""
        painter.setRenderHint(QPainter.Antialiasing)
        # --- 1. Get Data ---
        is_selected = index.data(ROLE_IS_SELECTED)
        scanner_mode = index.data(ROLE_SCANNER_MODE)
        # --- 2. Draw Background (Selection) ---
        if is_selected:
            # Use the style's selection color
            painter.fillRect(option.rect, self.color_selected)
        # --- 3. Draw Main Frame Border ---
        # Adjust rect for our 10px vertical spacing
        frame_rect = QRect(option.rect).adjusted(0, 0, 0, -10)
        painter.setPen(self.color_frame_border)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame_rect, 8, 8)
        # --- 4. Calculate Thumbnail Positions ---
        thumb1_rect = QRect(
            frame_rect.left() + self.SPACING,
            frame_rect.top() + (frame_rect.height() - self.THUMB_HEIGHT) // 2,
            self.THUMB_WIDTH,
            self.THUMB_HEIGHT
        )
        thumb2_rect = QRect(
            thumb1_rect.right() + self.SPACING,
            thumb1_rect.top(),
            self.THUMB_WIDTH,
            self.THUMB_HEIGHT
        )
        # --- 5. Draw Thumbnails ---
        self.draw_thumbnail(painter, option, index, thumb1_rect, "left")
        # Only draw second thumb if in split-mode OR dual-scan with a valid path
        if scanner_mode == "single_split":
            self.draw_thumbnail(painter, option, index, thumb2_rect, "right")
        elif index.data(ROLE_PATH_2): # Dual-scan and path2 is not None
            self.draw_thumbnail(painter, option, index, thumb2_rect, "right")

    def draw_thumbnail(self, painter, option, index, thumb_rect, side):
        """Helper to draw a single thumbnail (or its placeholder)."""
        if side == "left":
            pixmap = index.data(ROLE_PIXMAP_1)
            role_index = ROLE_INDEX_1
            role_path = ROLE_PATH_1
            role_is_loading = ROLE_IS_LOADING_1
        else:
            pixmap = index.data(ROLE_PIXMAP_2)
            role_index = ROLE_INDEX_2
            role_path = ROLE_PATH_2
            role_is_loading = ROLE_IS_LOADING_2

        if pixmap:
            # Pixmap is loaded, draw it
            painter.drawPixmap(thumb_rect, pixmap)
        else:
            # Pixmap not loaded, draw placeholder
            painter.fillRect(thumb_rect, self.color_thumb_bg)
            # Draw text
            if index.data(ROLE_SCANNER_MODE) == "single_split":
                text = f"{index.data(ROLE_INDEX_1) + 1} {'L' if side == 'left' else 'R'}"
            else:
                text = str(index.data(role_index) + 1)
            painter.setPen(self.color_thumb_text)
            painter.drawText(thumb_rect, Qt.AlignCenter, text)
            # --- Asynchronous Load Trigger ---
            is_loading = index.data(role_is_loading)
            if not is_loading:
                # We are in paint(), so this item is visible. Request its thumbnail.
                parent_view = self.parent() # This is the ThumbnailListWidget
                path = index.data(role_path)
                if index.data(ROLE_SCANNER_MODE) == "single_split":
                    parent_view.request_split_thumbnail.emit(index, side, path)
                else:
                    parent_view.request_thumbnail.emit(index, path)
                # Mark as loading so we don't spam requests every paint event
                parent_view.model().setData(index, True, role_is_loading)


class ThumbnailListWidget(QListView):
    """
    A virtualized list view for displaying thumbnail pairs.
    Replaces the QScrollArea implementation for performance.
    """
    # Emits the *pair index*
    pair_selected = Signal(int)
    # Signals to request thumbnails from the worker
    # We pass the QModelIndex as a stable reference to the item
    request_thumbnail = Signal(QModelIndex, str) # index, path (for dual_scan)
    request_split_thumbnail = Signal(QModelIndex, str, str) # index, "left"|"right", source_path

    def __init__(self, parent=None):
        super().__init__(parent)
        app_config = config.load_config()
        theme_name = app_config.get("theme", "Material Dark")
        theme = config.THEMES.get(theme_name, config.THEMES["Material Dark"])

        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setResizeMode(QListView.ResizeMode.Adjust) # Adjusts to width
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True) # CRITICAL for performance
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSpacing(10) # Space between pairs
        self.setStyleSheet(f"background-color: {theme['FRAME_BG']}; border: none; padding: 10px;")
        # Set the custom delegate (defined in Part 3)
        self.delegate = ThumbnailDelegate(self)
        self.setItemDelegate(self.delegate)
        self.clicked.connect(self.on_item_clicked)

    @Slot(QModelIndex)
    def on_item_clicked(self, index):
        """Internal slot to translate QListView's signal to our custom one."""
        pair_index = index.data(ROLE_PAIR_INDEX)
        self.pair_selected.emit(pair_index)

    def set_current_index(self, image_index):
        """Finds and selects the pair matching the current image index."""
        if not self.model():
            return
        for row in range(self.model().rowCount()):
            index = self.model().index(row, 0)
            idx1 = index.data(ROLE_INDEX_1)
            idx2 = index.data(ROLE_INDEX_2)
            is_match = (idx1 == image_index) or (idx2 == image_index and idx2 is not None)
            if is_match:
                self.setCurrentIndex(index)
                # Ensure it's visible, scroll to center
                self.scrollTo(index, QListView.ScrollHint.PositionAtCenter)
                break

    @Slot(QModelIndex, str, QPixmap)
    def on_thumbnail_loaded(self, index, side, pixmap):
        """
        Public slot to receive a loaded thumbnail from the worker
        and update the model.
        """
        if not index.isValid() or not self.model():
            return
        if side == "left":
            self.model().setData(index, pixmap, ROLE_PIXMAP_1)
            self.model().setData(index, False, ROLE_IS_LOADING_1)
        elif side == "right":
            self.model().setData(index, pixmap, ROLE_PIXMAP_2)
            self.model().setData(index, False, ROLE_IS_LOADING_2)
