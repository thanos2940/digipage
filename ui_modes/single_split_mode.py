from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class SingleSplitModeWidget(QWidget):
    """
    A placeholder widget for the 'single_split' mode.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel("Single Split Mode - Not Yet Implemented")
        label.setAlignment(Qt.AlignCenter)

        layout.addWidget(label)

        self.setLayout(layout)