import sys
from PySide6.QtWidgets import QApplication

from .core import config
from .ui.dialogs.settings_dialog import SettingsDialog
from .ui.main_window import MainWindow

def main():
    """The main entry point for the DigiPage Scanner application."""
    app = QApplication(sys.argv)

    # Load configuration and apply the theme stylesheet globally
    app_config = config.load_config()
    stylesheet = config.generate_stylesheet(app_config.get("theme", "Neutral Grey"))
    app.setStyleSheet(stylesheet)

    # Check if essential paths are configured
    is_configured = app_config.get("scan_folder") and app_config.get("todays_books_folder")

    if not is_configured:
        # If the app is not configured, we must show the settings dialog first.
        print("Configuration not found, launching Settings Dialog.")
        settings_dialog = SettingsDialog()
        # .exec() shows the dialog modally. The application will wait here.
        if settings_dialog.exec():
            # The user clicked "Save". The dialog has saved the new config.
            # We can now proceed to launch the main window.
            print("Settings saved. Launching Main Window.")
            main_win = MainWindow()
            main_win.showMaximized() # Show maximized for a better user experience
            sys.exit(app.exec())
        else:
            # The user clicked "Cancel" or closed the dialog. Exit the application.
            print("Settings cancelled. Exiting application.")
            sys.exit(0)
    else:
        # Configuration is valid, launch the main window directly.
        print("Configuration found. Launching Main Window.")
        main_win = MainWindow()
        main_win.showMaximized() # Show maximized for a better user experience
        sys.exit(app.exec())

if __name__ == "__main__":
    main()
