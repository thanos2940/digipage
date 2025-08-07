import sys
from PyQt6.QtWidgets import QApplication
from pyqt_app.settings_dialog import SettingsDialog
from pyqt_app.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    # Show settings dialog first
    settings_dialog = SettingsDialog()
    if not settings_dialog.exec():
        sys.exit(0) # Exit if user cancels settings

    settings = settings_dialog.get_settings()

    # If settings are accepted, show the main window
    main_window = MainWindow(settings)
    main_window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
