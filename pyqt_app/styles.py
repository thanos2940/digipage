# styles.py

DARK_STYLE_SHEET = """
    QWidget {
        background-color: #2b2b2b;
        color: #bbbbbb;
        font-family: Segoe UI, Calibri, Helvetica, Arial;
    }
    QMainWindow {
        background-color: #2b2b2b;
    }
    QDialog {
        background-color: #2b2b2b;
    }
    QLabel {
        color: #bbbbbb;
        font-size: 10pt;
    }
    QLineEdit {
        background-color: #3c3f41;
        color: #f0f0f0;
        border: 1px solid #444444;
        border-radius: 4px;
        padding: 5px;
    }
    QPushButton {
        background-color: #3c3f41;
        color: #f0f0f0;
        border: 1px solid #444444;
        padding: 8px 15px;
        border-radius: 4px;
        font-size: 10pt;
    }
    QPushButton:hover {
        background-color: #4a4e50;
    }
    QPushButton:pressed {
        background-color: #585c5e;
    }
    QGroupBox {
        background-color: #333333;
        border: 1px solid #444444;
        border-radius: 5px;
        margin-top: 1ex;
        font-size: 11pt;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 3px;
        color: #888888;
    }
    QListWidget {
        background-color: #3c3f41;
        border: 1px solid #444444;
        border-radius: 4px;
    }
    QListWidget::item:selected {
        background-color: #007bff;
        color: white;
    }
    QSlider::groove:horizontal {
        border: 1px solid #444;
        height: 8px;
        background: #3c3f41;
        margin: 2px 0;
        border-radius: 4px;
    }
    QSlider::handle:horizontal {
        background: #bbbbbb;
        border: 1px solid #888888;
        width: 18px;
        margin: -2px 0;
        border-radius: 9px;
    }
    QGraphicsView {
        border: 1px solid #444444;
        background-color: #2b2b2b;
    }
"""
SUCCESS_COLOR = "#28a745"
DESTRUCTIVE_COLOR = "#dc3545"
WARNING_COLOR = "#ffc107"
ACCENT_COLOR = "#007bff"
