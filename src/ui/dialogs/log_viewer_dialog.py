import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QScrollArea, QWidget, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QHBoxLayout,
    QDateEdit, QToolTip
)
from PySide6.QtCore import Qt, QDate, QRectF
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QTextCharFormat
from datetime import datetime, timedelta
from core.config_service import ConfigService
from core.constants import BOOKS_COMPLETE_LOG_FILE, THEMES

# A robust way to handle Greek day names without relying on system locale
GREEK_DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]

class ProductivityChart(QWidget):
    def __init__(self, theme, config_service, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.config_service = config_service
        self.setMinimumHeight(200)
        self.daily_data = []
        self.bar_rects = []
        self.hovered_bar_index = -1
        self.setMouseTracking(True)

    def set_data(self, daily_data):
        self.daily_data = sorted(daily_data, key=lambda x: x[0])
        self.hovered_bar_index = -1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.fillRect(self.rect(), QColor(self.theme.get('FRAME_BG', '#252428')))

        if not self.daily_data:
            painter.setPen(QColor(self.theme.get('ON_SURFACE_VARIANT', '#c4c6c5')))
            painter.drawText(self.rect(), Qt.AlignCenter, "Δεν υπάρχουν δεδομένα για το επιλεγμένο διάστημα.")
            return

        padding_top, padding_bottom, padding_left, padding_right = 20, 30, 40, 10
        chart_rect = self.rect().adjusted(padding_left, padding_top, -padding_right, -padding_bottom)
        max_pages = max(item[1] for item in self.daily_data) if self.daily_data else 1

        axis_pen = QPen(QColor(self.theme.get('OUTLINE', '#928f99')), 1)
        grid_pen = QPen(QColor(self.theme.get('OUTLINE', '#928f99')), 1, Qt.DotLine)
        painter.setPen(axis_pen)
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.bottomRight()) # X-Axis
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.topLeft())   # Y-Axis

        num_y_labels = 5
        for i in range(num_y_labels + 1):
            val = (max_pages / num_y_labels) * i
            y = chart_rect.bottom() - (val / max_pages) * chart_rect.height()
            painter.setPen(QColor(self.theme.get('ON_SURFACE_VARIANT', '#c4c6c5')))
            painter.drawText(QRectF(0, y - 10, padding_left - 5, 20), Qt.AlignRight | Qt.AlignVCenter, f"{int(val)}")
            if i > 0:
                painter.setPen(grid_pen)
                painter.drawLine(chart_rect.left(), y, chart_rect.right(), y)

        self.bar_rects.clear()
        bar_count = len(self.daily_data)
        total_bar_width = chart_rect.width() / bar_count
        bar_width = total_bar_width * 0.6
        spacing = total_bar_width * 0.4

        base_color = QColor(self.theme.get('PRIMARY', '#b0c6ff'))
        hover_color = QColor(self.config_service.lighten_color(self.theme.get('PRIMARY', '#b0c6ff'), 0.2))

        for i, (qdate, pages) in enumerate(self.daily_data):
            bar_height = (pages / max_pages) * chart_rect.height()
            x = chart_rect.left() + i * total_bar_width + spacing / 2
            bar_rect = QRectF(x, chart_rect.bottom() - bar_height, bar_width, bar_height)
            self.bar_rects.append({'rect': bar_rect, 'date': qdate, 'pages': pages})

            painter.setBrush(hover_color if i == self.hovered_bar_index else base_color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(bar_rect)

            if bar_count <= 15 or i % (bar_count // 10 + 1) == 0:
                 painter.setPen(QColor(self.theme.get('ON_SURFACE_VARIANT', '#c4c6c5')))
                 date_str = qdate.toString("d/M")
                 painter.drawText(QRectF(x, chart_rect.bottom(), total_bar_width, padding_bottom), Qt.AlignCenter, date_str)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        current_hover_index = -1
        for i, bar_info in enumerate(self.bar_rects):
            if bar_info['rect'].contains(pos):
                current_hover_index = i
                break

        if current_hover_index != self.hovered_bar_index:
            self.hovered_bar_index = current_hover_index
            self.update()

        if self.hovered_bar_index != -1:
            bar_info = self.bar_rects[self.hovered_bar_index]
            day_name = GREEK_DAYS[bar_info['date'].dayOfWeek() - 1]
            date_str = f"{day_name}, {bar_info['date'].toString('d MMMM yyyy')}"
            QToolTip.showText(event.globalPos(), f"{date_str}\nΣελίδες: {bar_info['pages']}", self)
        else:
            QToolTip.hideText()


class DailyLogWidget(QFrame):
    def __init__(self, date_str, entries, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.entries = entries
        self.date_str = date_str
        self._setup_ui()
        self._populate_data()

    def _format_date(self, date_str_iso):
        try:
            dt_obj = datetime.strptime(date_str_iso, '%Y-%m-%d')
            day_name = GREEK_DAYS[dt_obj.weekday()]
            return f"{day_name}, {dt_obj.strftime('%d-%m-%Y')}"
        except ValueError:
            return date_str_iso

    def _setup_ui(self):
        self.setObjectName("DailyLogCard")
        self.setStyleSheet(f"""
            #DailyLogCard {{
                background-color: {self.theme.get('SURFACE_CONTAINER', '#36343b')};
                border-radius: 16px;
                padding: 16px;
            }}
        """)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(15)

        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(20)

        self.date_label = QLabel()
        date_font = QFont()
        date_font.setPointSize(24)
        date_font.setBold(True)
        self.date_label.setFont(date_font)
        self.date_label.setStyleSheet(f"font-size: 15pt; font-weight: bold; color: {self.theme.get('ON_SURFACE', '#e5e1e6')};")

        pages_box = QFrame()
        pages_box.setObjectName("PagesBox")
        pages_box.setFixedWidth(160)
        pages_box.setStyleSheet(f"""
            #PagesBox {{
                background-color: {self.theme.get('FRAME_BG', '#252428')};
                border: 1px solid {self.theme.get('OUTLINE', '#928f99')};
                border-radius: 12px;
                padding: 5px;
            }}
        """)
        pages_box_layout = QVBoxLayout(pages_box)
        pages_box_layout.setSpacing(2)
        pages_box_layout.setContentsMargins(5,5,5,5)

        pages_title = QLabel("ΣΥΝΟΛΙΚΕΣ ΣΕΛΙΔΕΣ")
        pages_title.setAlignment(Qt.AlignCenter)
        pages_title.setStyleSheet("font-size: 8pt; font-weight: bold; border: none; background: transparent;")

        self.pages_count_label = QLabel("0")
        self.pages_count_label.setAlignment(Qt.AlignCenter)
        self.pages_count_label.setStyleSheet(f"font-size: 24pt; font-weight: bold; color: {self.theme.get('TERTIARY', '#e2bada')}; border: none; background: transparent;")

        self.performance_label = QLabel("0.00 σελ/ώρα")
        self.performance_label.setAlignment(Qt.AlignCenter)
        self.performance_label.setStyleSheet(f"""
            font-size: 9pt; color: {self.theme.get('ON_SURFACE_VARIANT', '#c4c6c5')};
            border: none; background: transparent; padding-top: 2px;
        """)

        pages_box_layout.addWidget(pages_title)
        pages_box_layout.addWidget(self.pages_count_label)
        pages_box_layout.addWidget(self.performance_label)

        header_layout.addWidget(self.date_label, 1)
        header_layout.addWidget(pages_box)

        self.entries_table = QTableWidget()
        self.entries_table.setColumnCount(2)
        self.entries_table.setHorizontalHeaderLabels(["Όνομα Βιβλίου", "Σελίδες"])
        self.entries_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.entries_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.entries_table.setFocusPolicy(Qt.NoFocus)
        self.entries_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        header = self.entries_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self.entries_table.setStyleSheet(f"""
            QTableWidget {{ background-color: transparent; border: none; gridline-color: {self.theme.get('OUTLINE', '#444444')}; }}
            QHeaderView::section {{ background-color: transparent; color: {self.theme.get('ON_SURFACE_VARIANT', '#c4c6c5')}; padding: 6px; border-bottom: 2px solid {self.theme.get('PRIMARY', '#b0c6ff')}; font-weight: bold; }}
            QTableWidget::item {{ padding: 8px; }}
        """)

        self.main_layout.addWidget(header_frame)
        self.main_layout.addWidget(self.entries_table)

    def _populate_data(self):
        self.date_label.setText(self._format_date(self.date_str))

        total_pages = sum(entry.get("pages", 0) for entry in self.entries)
        self.pages_count_label.setText(str(total_pages))

        avg_performance = total_pages / 8.0 if total_pages > 0 else 0.0
        self.performance_label.setText(f"{avg_performance:.2f} σελ/ώρα")

        self.entries_table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            name = entry.get("name", "Άγνωστο Όνομα")
            pages = str(entry.get("pages", "N/A"))
            self.entries_table.setItem(row, 0, QTableWidgetItem(name))
            self.entries_table.setItem(row, 1, QTableWidgetItem(pages))

        table_height = self.entries_table.horizontalHeader().height() + self.entries_table.rowHeight(0) * self.entries_table.rowCount()
        self.entries_table.setFixedHeight(table_height)

class LogViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_service = ConfigService()
        self.setWindowTitle("Αρχείο Καταγραφής & Στατιστικά Απόδοσης")
        self.setMinimumSize(950, 800)

        theme_name = self.config_service.get("theme", "Material Dark")
        self.theme = THEMES.get(theme_name, THEMES["Material Dark"])

        self.setStyleSheet(f"background-color: {self.theme.get('BG_COLOR', '#1c1b1f')}; color: {self.theme.get('ON_SURFACE', '#e5e1e6')};")

        self.full_log_data = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(20)

        top_section_frame = QFrame()
        top_section_frame.setObjectName("TopFrame")
        top_section_frame.setStyleSheet(f"#TopFrame {{ background-color: {self.theme.get('FRAME_BG', '#252428')}; border-radius: 16px; }}")
        top_section_layout = QVBoxLayout(top_section_frame)
        top_section_layout.setSpacing(10)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Εμφάνιση από:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        controls_layout.addWidget(self.start_date_edit)

        controls_layout.addSpacing(20)
        controls_layout.addWidget(QLabel("έως:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        controls_layout.addWidget(self.end_date_edit)
        controls_layout.addStretch()

        weekend_format = QTextCharFormat()
        weekend_format.setForeground(QColor(self.theme.get('ON_SURFACE', '#e5e1e6')))

        for date_edit in [self.start_date_edit, self.end_date_edit]:
            calendar = date_edit.calendarWidget()
            calendar.setWeekdayTextFormat(Qt.Saturday, weekend_format)
            calendar.setWeekdayTextFormat(Qt.Sunday, weekend_format)
            calendar.setStyleSheet(f"""
                QCalendarWidget QWidget {{ alternate-background-color: {self.theme.get('SURFACE_CONTAINER', '#36343b')}; }}
                QCalendarWidget QToolButton {{ color: {self.theme.get('ON_SURFACE', '#e5e1e6')}; }}
            """)

        self.chart = ProductivityChart(self.theme, self.config_service)

        top_section_layout.addLayout(controls_layout)
        top_section_layout.addWidget(self.chart)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_content_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content_widget)
        self.scroll_layout.setSpacing(20)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        scroll_area.setWidget(self.scroll_content_widget)

        self.status_label = QLabel("Φόρτωση αρχείου καταγραφής...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.scroll_layout.addWidget(self.status_label)

        main_layout.addWidget(top_section_frame)
        main_layout.addWidget(scroll_area)

        self.load_and_process_logs()

    def load_and_process_logs(self):
        try:
            with open(BOOKS_COMPLETE_LOG_FILE, 'r', encoding='utf-8') as f:
                raw_log_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.status_label.setText("Σφάλμα: Το αρχείο καταγραφής δεν βρέθηκε ή είναι κατεστραμμένο.")
            self.chart.set_data([])
            return

        if not raw_log_data:
            self.status_label.setText("Το αρχείο καταγραφής είναι κενό.")
            self.chart.set_data([])
            return

        self.full_log_data = {
            datetime.strptime(date_str, '%Y-%m-%d').date(): entries
            for date_str, entries in raw_log_data.items()
        }
        self.setup_controls_and_initial_view()

    def setup_controls_and_initial_view(self):
        if not self.full_log_data:
            return

        all_dates = sorted(self.full_log_data.keys())
        min_date, max_date = all_dates[0], all_dates[-1]

        self.start_date_edit.setDateRange(QDate(min_date), QDate(max_date))
        self.end_date_edit.setDateRange(QDate(min_date), QDate(max_date))

        start_date = max(min_date, max_date - timedelta(days=30))
        self.start_date_edit.setDate(QDate(start_date))
        self.end_date_edit.setDate(QDate(max_date))

        self.start_date_edit.dateChanged.connect(self.update_filtered_view)
        self.end_date_edit.dateChanged.connect(self.update_filtered_view)

        self.update_filtered_view()

    def update_filtered_view(self):
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()

        if start_date > end_date:
            self.chart.set_data([])
            status_label = QLabel("Η ημερομηνία έναρξης πρέπει να είναι πριν την ημερομηνία λήξης.")
            self.scroll_layout.addWidget(status_label)
            return

        filtered_dates = sorted([d for d in self.full_log_data if start_date <= d <= end_date], reverse=True)

        if not filtered_dates:
            self.chart.set_data([])
            status_label = QLabel("Δεν υπάρχουν εγγραφές για το επιλεγμένο διάστημα.")
            self.scroll_layout.addWidget(status_label)
            return

        chart_data = []
        for date_obj in filtered_dates:
            entries = self.full_log_data[date_obj]
            total_pages = sum(e.get('pages', 0) for e in entries)
            chart_data.append((QDate(date_obj), total_pages))

        self.chart.set_data(chart_data)

        for date_obj in filtered_dates:
            entries = self.full_log_data[date_obj]
            date_str_iso = date_obj.strftime('%Y-%m-%d')
            daily_widget = DailyLogWidget(date_str_iso, entries, self.theme)
            self.scroll_layout.addWidget(daily_widget)
