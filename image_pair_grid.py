from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QHBoxLayout, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize, QObject
from PySide6.QtGui import QPixmap

class ImageThumbnailWidget(QWidget):
    """A widget to display a single image thumbnail and its number."""
    def __init__(self, image_path, image_number, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.image_number = image_number
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.image_label = QLabel()
        self.image_label.setFixedSize(100, 100)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #333; border-radius: 4px;")

        self.number_label = QLabel(str(self.image_number))
        self.number_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.image_label)
        layout.addWidget(self.number_label)

    def set_pixmap(self, pixmap):
        if not pixmap.isNull():
            self.image_label.setPixmap(pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

class ImagePairThumbnailWidget(QFrame):
    """A widget to display a pair of thumbnails."""
    pair_selected = Signal(int)

    def __init__(self, index, image1_path, image2_path, image1_number, image2_number, parent=None):
        super().__init__(parent)
        self.index = index
        self.image1_path = image1_path
        self.image2_path = image2_path
        self.image1_number = image1_number
        self.image2_number = image2_number

        self.setObjectName("ImagePairThumbnailFrame")
        self.set_selected(False) # Initial style
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.thumb1 = ImageThumbnailWidget(self.image1_path, self.image1_number)
        layout.addWidget(self.thumb1)

        if self.image2_path:
            self.thumb2 = ImageThumbnailWidget(self.image2_path, self.image2_number)
            layout.addWidget(self.thumb2)
        else:
            # Add a placeholder if there is no second image
            placeholder = QWidget()
            placeholder.setFixedSize(100, 115) # Match size of ImageThumbnailWidget
            layout.addWidget(placeholder)
            self.thumb2 = None

    def set_pixmaps(self, pixmap1, pixmap2):
        if self.thumb1:
            self.thumb1.set_pixmap(pixmap1)
        if self.thumb2 and pixmap2:
            self.thumb2.set_pixmap(pixmap2)

    def mousePressEvent(self, event):
        self.pair_selected.emit(self.index)
        super().mousePressEvent(event)

    def set_selected(self, selected):
        if selected:
            self.setStyleSheet("#ImagePairThumbnailFrame { border: 2px solid #007bff; border-radius: 5px; }")
        else:
            self.setStyleSheet("#ImagePairThumbnailFrame { border: 2px solid transparent; border-radius: 5px; }")


class ImagePairGridWidget(QWidget):
    """A scrollable grid of image pair thumbnails."""
    thumbnail_selected = Signal(int)
    load_thumbnail_requested = Signal(str, QObject)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.thumbnails = []

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(self.scroll_area)

        self.scroll_content = QWidget()
        self.grid_layout = QVBoxLayout(self.scroll_content)
        self.grid_layout.setSpacing(5)
        self.grid_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

    def populate_grid(self, image_files):
        # Clear existing thumbnails
        for thumbnail in self.thumbnails:
            thumbnail.setParent(None)
            thumbnail.deleteLater()
        self.thumbnails = []

        # Create new thumbnails
        for i in range(0, len(image_files), 2):
            image1_path = image_files[i]
            image2_path = image_files[i+1] if i + 1 < len(image_files) else None

            thumb = ImagePairThumbnailWidget(i, image1_path, image2_path, i + 1, i + 2)
            thumb.pair_selected.connect(self.thumbnail_selected)

            self.grid_layout.addWidget(thumb)
            self.thumbnails.append(thumb)

            self.load_thumbnail_requested.emit(image1_path, thumb.thumb1)
            if image2_path:
                self.load_thumbnail_requested.emit(image2_path, thumb.thumb2)

    def set_current_index(self, index):
        for i, thumbnail in enumerate(self.thumbnails):
            is_selected = (i == index // 2)
            thumbnail.set_selected(is_selected)
            if is_selected:
                self.scroll_area.ensureWidgetVisible(thumbnail, 50, 50)
