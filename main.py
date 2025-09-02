import sys
from PySide6.QtWidgets import QApplication

# Import configuration and main UI components
import config
from main_window import MainWindow
from settings_dialog import SettingsDialog

class DigiPageScannerApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = None
        self.settings_dialog = None

        # Load configuration
        self.config_data = config.load_config()

        # Apply the theme
        self.apply_theme()

    def run(self):
        """
        Runs the application. It shows the main window if the configuration
        is valid, otherwise it shows the settings dialog.
        """
        if config.is_config_valid(self.config_data):
            self.show_main_window()
        else:
            self.show_settings_dialog(is_initial_setup=True)

        sys.exit(self.app.exec())

    def apply_theme(self):
        """Applies the current theme from config."""
        stylesheet = config.generate_stylesheet(self.config_data.get("current_theme"))
        self.app.setStyleSheet(stylesheet)

    def show_main_window(self):
        """Creates and shows the main application window."""
        self.window = MainWindow()
        self.window.show()

    def show_settings_dialog(self, is_initial_setup=False):
        """
        Creates and shows the settings dialog.
        If it's the initial setup, closing the dialog will exit the app
        unless the config is saved and made valid.
        """
        # Pass the main window as parent if it exists
        parent = self.window if self.window else None
        self.settings_dialog = SettingsDialog(parent) # This will be properly implemented later

        # We'll need a way to relaunch the main window if settings are saved.
        self.settings_dialog.settings_saved.connect(self.on_settings_saved)
        self.settings_dialog.exec() # Use exec for a modal dialog

    def on_settings_saved(self):
        """Called when settings are saved. Tries to launch the main window."""
        self.config_data = config.load_config() # Reload config
        self.apply_theme() # Re-apply theme in case it changed
        if config.is_config_valid(self.config_data):
            # If the main window doesn't exist, create it.
            if not self.window:
                self.show_main_window()
            # The settings dialog will close itself, so we just need to make sure the main window is visible.
            self.window.show()
            self.window.activateWindow()


if __name__ == '__main__':
    # To ensure high-DPI scaling is handled correctly
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        "PassThrough"
    )
    app_instance = DigiPageScannerApp()
    app_instance.run()
