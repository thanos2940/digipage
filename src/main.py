import sys
import os
from PySide6.QtWidgets import QApplication

# Add the 'src' directory to sys.path so we can import modules relative to it
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from core.config_service import ConfigService
from ui.main_window import MainWindow
from ui.dialogs.settings_dialog import SettingsDialog

def main():
    app = QApplication(sys.argv)

    config_service = ConfigService()

    # Apply Stylesheet
    stylesheet = config_service.generate_stylesheet()
    app.setStyleSheet(stylesheet)

    config = config_service.get_config()
    is_configured = config.get("scan_folder") and config.get("todays_books_folder")

    if not is_configured:
        print("Configuration not found, launching Settings Dialog.")
        dlg = SettingsDialog()
        if dlg.exec():
            print("Settings saved. Launching Main Window.")
            win = MainWindow()
            win.showMaximized()
            sys.exit(app.exec())
        else:
            sys.exit(0)
    else:
        win = MainWindow()
        win.showMaximized()
        sys.exit(app.exec())

if __name__ == "__main__":
    main()
