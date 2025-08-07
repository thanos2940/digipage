import sys
import traceback
from PyQt6.QtWidgets import QApplication
from pyqt_app.settings_dialog import SettingsDialog
from pyqt_app.main_window import MainWindow

def main():
    try:
        print("[main] Application starting.")
        app = QApplication(sys.argv)
        print("[main] QApplication instance created.")

        print("[main] Creating SettingsDialog.")
        settings_dialog = SettingsDialog()
        print("[main] Showing SettingsDialog.")

        if not settings_dialog.exec():
            print("[main] SettingsDialog cancelled by user. Exiting.")
            sys.exit(0)

        print("[main] SettingsDialog accepted.")
        settings = settings_dialog.get_settings()
        print(f"[main] Settings loaded: {settings}")

        print("[main] Creating MainWindow.")
        main_window = MainWindow(settings)
        print("[main] Showing MainWindow.")
        main_window.show()

        print("[main] Starting application event loop.")
        sys.exit(app.exec())
    except Exception as e:
        print(f"FATAL: An unexpected error occurred: {e}")
        with open("crash_log.txt", "w") as f:
            f.write(f"Unhandled exception: {e}\\n")
            f.write(traceback.format_exc())
        print("FATAL: A crash log has been written to crash_log.txt")
        sys.exit(1)


if __name__ == '__main__':
    main()
