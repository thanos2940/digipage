import sys
import traceback
from PyQt6.QtWidgets import QApplication
from pyqt_app.settings_dialog import SettingsDialog
from pyqt_app.main_window import MainWindow

def main():
    try:
        app = QApplication(sys.argv)

        settings_dialog = SettingsDialog()
        if not settings_dialog.exec():
            sys.exit(0)

        settings = settings_dialog.get_settings()

        main_window = MainWindow(settings)
        main_window.show()

        sys.exit(app.exec())
    except Exception as e:
        # Still keep the crash logger just in case
        with open("crash_log.txt", "w") as f:
            f.write(f"Unhandled exception: {e}\\n")
            f.write(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()
