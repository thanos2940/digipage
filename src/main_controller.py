import os
import json
import tkinter as tk

from style import Style
from config import CONFIG_FILE
from settings_frame import SettingsFrame
from image_scanner_app import ImageScannerApp

class App(tk.Tk):
    # Initializes the main application window
    def __init__(self):
        super().__init__()
        self.title("DigiPage Scanner")
        self.load_config_and_apply_theme()
        self.configure(bg=Style.BG_COLOR)
        self._frame = None
        self.is_fullscreen = False
        self.bind("<F11>", self.toggle_fullscreen)
        self.show_frame(SettingsFrame)

    def load_config_and_apply_theme(self):
        theme_name = "Neutral Grey" # Default
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    settings = json.load(f)
                    theme_name = settings.get("theme", "Neutral Grey")
        except (IOError, json.JSONDecodeError):
            pass # Stick to default if config is bad

        Style.load_theme(theme_name)

    def update_theme(self):
        """Recursively updates the theme for the entire application."""
        self.configure(bg=Style.BG_COLOR)
        if self._frame and hasattr(self._frame, 'update_theme'):
            self._frame.update_theme()

    # Toggles fullscreen mode
    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)
        return "break"

    # Centers the settings window on the screen.
    def center_settings_window(self):
        self.update_idletasks()
        width, height = 800, 700 # Adjusted height
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    # Sets the size for the main application window.
    def set_main_window_size(self):
        self.update_idletasks()
        width, height = 1600, 900
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        # Make sure window is not bigger than screen
        width = min(width, screen_width)
        height = min(height, screen_height)
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    # Displays a new frame in the window
    def show_frame(self, frame_class, settings=None):
        if self._frame: self._frame.destroy()

        self._frame = frame_class(self, self, settings) if settings else frame_class(self, self)
        self._frame.grid(row=0, column=0, sticky='nsew')
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        if frame_class == SettingsFrame:
            self.overrideredirect(False)
            self.title("DigiPage Scanner - Ρυθμίσεις")
            self.center_settings_window()
        elif frame_class == ImageScannerApp:
            self.title("DigiPage Scanner")
            self.set_main_window_size()
