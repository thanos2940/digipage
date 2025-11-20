from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from ...core.theme import MODERN_THEME

class ToastNotification(QWidget):
    """
    A non-blocking, floating notification widget.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # self.setAttribute(Qt.WA_ShowWithoutActivation)

        self._setup_ui()

        # Animation setup
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_toast)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        # Icon (Text-based for now, can be SVG)
        self.icon_label = QLabel("ℹ")
        self.icon_label.setStyleSheet(f"color: {MODERN_THEME['PRIMARY']}; font-size: 16pt; font-weight: bold;")

        self.message_label = QLabel("Notification")
        self.message_label.setStyleSheet(f"color: {MODERN_THEME['TEXT_MAIN']}; font-size: 10pt;")
        self.message_label.setWordWrap(True)

        layout.addWidget(self.icon_label)
        layout.addSpacing(10)
        layout.addWidget(self.message_label)

        self.setStyleSheet(f"""
            #Toast {{
                background-color: {MODERN_THEME['BG_CARD']};
                border: 1px solid {MODERN_THEME['BORDER']};
                border-radius: {MODERN_THEME['RADIUS_MD']};
            }}
        """)

    def show_message(self, message, type="info", duration=3000):
        self.message_label.setText(message)

        if type == "success":
            self.icon_label.setText("✓")
            self.icon_label.setStyleSheet(f"color: {MODERN_THEME['SUCCESS']}; font-size: 16pt; font-weight: bold;")
        elif type == "error":
            self.icon_label.setText("!")
            self.icon_label.setStyleSheet(f"color: {MODERN_THEME['DANGER']}; font-size: 16pt; font-weight: bold;")
        else:
            self.icon_label.setText("ℹ")
            self.icon_label.setStyleSheet(f"color: {MODERN_THEME['PRIMARY']}; font-size: 16pt; font-weight: bold;")

        self.adjustSize()
        self._position_toast()

        self.show()
        self.opacity_effect.setOpacity(0)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()

        self.timer.start(duration)

    def hide_toast(self):
        self.anim.setStartValue(1)
        self.anim.setEndValue(0)
        self.anim.finished.connect(self.close)
        self.anim.start()

    def _position_toast(self):
        if self.parent():
            parent_geo = self.parent().geometry()
            # Bottom center position, floating above bottom bar
            x = parent_geo.center().x() - self.width() // 2
            y = parent_geo.bottom() - self.height() - 80
            self.move(parent_geo.topLeft() + QPoint(x, y - parent_geo.top())) # Adjust for local coords if needed
        else:
            # Fallback if no parent
            pass
