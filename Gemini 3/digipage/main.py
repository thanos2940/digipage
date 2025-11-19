import sys
import os

# Ensure the root directory is in python path so imports work cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from digipage.core.config import ConfigManager
from digipage.core.theme import generate_stylesheet
# Assuming SettingsDialog and MainWindow will be moved to ui.dialogs and ui.main_window
# For now, we assume they are being refactored into the 'ui' package.
from digipage.ui.dialogs.settings import SettingsDialog
from digipage.ui.main_window import MainWindow 

def main():
    """The main entry point for the DigiPage Scanner application."""
    app = QApplication(sys.argv)

    # Load typed configuration
    app_config = ConfigManager.load()
    
    # Apply theme globally
    app.setStyleSheet(generate_stylesheet(app_config.theme))

    # Check configuration validity
    is_configured = bool(app_config.scan_folder and app_config.todays_books_folder)

    if not is_configured:
        print("Configuration not found, launching Settings Dialog.")
        settings_dialog = SettingsDialog()
        if settings_dialog.exec():
            print("Settings saved. Launching Main Window.")
            # Reload config in case it changed
            app_config = ConfigManager.load()
            main_win = MainWindow(app_config)
            main_win.showMaximized()
            sys.exit(app.exec())
        else:
            print("Settings cancelled. Exiting.")
            sys.exit(0)
    else:
        print("Configuration found. Launching Main Window.")
        main_win = MainWindow(app_config)
        main_win.showMaximized()
        sys.exit(app.exec())

if __name__ == "__main__":
    main()