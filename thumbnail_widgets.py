# In thumbnail_widgets.py
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot, QSize, QEvent, QTimer # <-- ADD QTimer HERE
from PySide6.QtGui import QPixmap, QPainter, QColor


class ThumbnailPairWidget(QFrame):
    """
    A widget to display a pair of thumbnails (or a single one).
    It handles selection styling and emits a signal when clicked.
    """
    clicked = Signal(int)

    def __init__(self, index1, path1, index2=None, path2=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setLineWidth(2)
        self.setObjectName("ThumbnailPairFrame")
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.index1 = index1
        self.path1 = path1
        self.index2 = index2
        self.path2 = path2
        self.is_selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.thumb_label1 = QLabel()
        self.thumb_label1.setObjectName("ThumbnailLabel")
        self.thumb_label1.setAlignment(Qt.AlignCenter)
        self.thumb_label1.setFixedSize(90, 110)
        self.thumb_label1.setText(str(self.index1 + 1))
        layout.addWidget(self.thumb_label1)

        if self.index2 is not None:
            self.thumb_label2 = QLabel()
            self.thumb_label2.setObjectName("ThumbnailLabel")
            self.thumb_label2.setAlignment(Qt.AlignCenter)
            self.thumb_label2.setFixedSize(90, 110)
            self.thumb_label2.setText(str(self.index2 + 1))
            layout.addWidget(self.thumb_label2)
        else:
            self.thumb_label2 = None

    def set_pixmap1(self, pixmap):
        # The pixmap is now pre-scaled by the worker. Just set it.
        self.thumb_label1.setPixmap(pixmap)

    def set_pixmap2(self, pixmap):
        if self.thumb_label2:
            # The pixmap is now pre-scaled by the worker. Just set it.
            self.thumb_label2.setPixmap(pixmap)

    def set_selected(self, selected):
        self.is_selected = selected
        # This property is used by the stylesheet selector QFrame#ThumbnailPairFrame:selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit(self.index1)
        super().mousePressEvent(event)


class ThumbnailListWidget(QScrollArea):
    """
    A scrollable list of thumbnail pairs that intelligently updates
    without rebuilding the entire list from scratch on every change.
    """
    pair_selected = Signal(int)
    request_thumbnail = Signal(int, str) # index, path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setAlignment(Qt.AlignTop)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        self.setWidget(self.scroll_content)

        self.pair_widgets = {} # Using a dict {index: widget} for faster lookups
        self.current_selected_index = -1
        self._stretch_item = self.main_layout.addStretch()

    def sync(self, image_files):
        """
        Synchronizes the thumbnail list with the provided list of image files,
        only adding, removing, or updating widgets as necessary.
        This version is optimized to be robust and visually seamless.
        """
        # --- Remove stretch item temporarily ---
        if self._stretch_item:
            self.main_layout.removeItem(self._stretch_item)

        # Rebuilding is visually seamless due to thumbnail caching and is far
        # more robust than complex patching logic. It avoids potential bugs with
        # pairing logic when items are deleted from the middle of the list.
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.pair_widgets.clear()
        
        # --- Re-Pairing Logic ---
        i = 0
        is_odd = len(image_files) % 2 != 0
        if is_odd and i < len(image_files):
            path = image_files[i]
            pair_widget = ThumbnailPairWidget(i, path)
            pair_widget.clicked.connect(self.on_pair_clicked)
            self.main_layout.addWidget(pair_widget)
            self.pair_widgets[i] = pair_widget
            self.request_thumbnail.emit(i, path)
            i += 1
        
        while i < len(image_files) - 1:
            idx1, path1 = i, image_files[i]
            idx2, path2 = i + 1, image_files[i + 1]
            pair_widget = ThumbnailPairWidget(idx1, path1, idx2, path2)
            pair_widget.clicked.connect(self.on_pair_clicked)
            self.main_layout.addWidget(pair_widget)
            self.pair_widgets[idx1] = pair_widget
            
            self.request_thumbnail.emit(idx1, path1)
            self.request_thumbnail.emit(idx2, path2)
            i += 2
            
        # --- Re-add stretch item ---
        self._stretch_item = self.main_layout.addStretch()
        # Re-apply selection to the newly created widgets
        self.set_current_index(self.current_selected_index)

    @Slot(int, str, QPixmap)
    def on_thumbnail_loaded(self, index, path, pixmap):
        if pixmap.isNull(): return
        
        # Find the correct widget to update.
        # This logic correctly finds the widget whether the thumbnail
        # is the first or second image in its pair.
        widget_to_update = None
        if index in self.pair_widgets:
            widget_to_update = self.pair_widgets[index]
        elif (index > 0) and (index % 2 != 0) and ((index - 1) in self.pair_widgets):
             # This handles the second image in a pair
            widget_to_update = self.pair_widgets[index - 1]

        if widget_to_update:
            if widget_to_update.index1 == index:
                widget_to_update.set_pixmap1(pixmap)
            elif widget_to_update.index2 == index:
                widget_to_update.set_pixmap2(pixmap)

    @Slot(int)
    def on_pair_clicked(self, index):
        self.set_current_index(index)
        self.pair_selected.emit(index)

    def set_current_index(self, index):
        if not self.pair_widgets: return
        
        self.current_selected_index = index
        selected_widget = None
        
        for key_index, pair_widget in self.pair_widgets.items():
            is_part_of_pair = (
                pair_widget.index1 == index or 
                (pair_widget.index2 is not None and pair_widget.index2 == index)
            )
            pair_widget.set_selected(is_part_of_pair)
            if is_part_of_pair:
                selected_widget = pair_widget
        
        if selected_widget:
            # Use a QTimer to ensure scrolling happens after the UI has updated,
            # which is more reliable.
            QTimer.singleShot(50, lambda: self.ensureWidgetVisible(selected_widget, 50, 50))

