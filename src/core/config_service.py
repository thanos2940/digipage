import json
import os
import colorsys
from .constants import CONFIG_FILE, DEFAULT_CONFIG, THEMES

class ConfigService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigService, cls).__new__(cls)
            cls._instance._config = cls.load_config()
        return cls._instance

    @staticmethod
    def load_config():
        if not os.path.exists(CONFIG_FILE):
            return DEFAULT_CONFIG.copy()
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            # Ensure defaults
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(config_data)
            return merged_config
        except (IOError, json.JSONDecodeError):
            return DEFAULT_CONFIG.copy()

    def get_config(self):
        return self._config

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value
        self.save_config()

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving config: {e}")

    # --- Theme Helper functions ---
    @staticmethod
    def lighten_color(hex_color, factor=0.1):
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
        new_l = min(1.0, hls[1] + factor)
        new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
        return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

    @staticmethod
    def darken_color(hex_color, factor=0.1):
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
        new_l = max(0.0, hls[1] - factor)
        new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
        return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

    def generate_stylesheet(self):
        theme_name = self.get("theme", "Material Dark")
        theme = THEMES.get(theme_name, THEMES["Material Dark"])

        # Using static methods for color manipulation
        lighten = self.lighten_color
        darken = self.darken_color

        qss = f"""
            * {{
                font-family: "Segoe UI", Arial, sans-serif;
            }}
            /* --- Global --- */
            QWidget {{
                background-color: {theme['BG_COLOR']};
                color: {theme['ON_SURFACE']};
                font-size: 10pt;
            }}
            QMainWindow {{ background-color: {theme['BG_COLOR']}; }}

            QDialog {{ background-color: {theme['SURFACE']}; }}

            /* --- Labels --- */
            QLabel {{ background-color: transparent; padding: 2px; }}

            /* --- Buttons --- */
            /* Default button is the 'tonal' style for secondary actions */
            QPushButton, QToolButton {{
                background-color: {theme['SURFACE_CONTAINER']};
                color: {lighten(theme['PRIMARY'],0.2)};
                border: none;
                padding: 8px 16px;
                border-radius: 16px;
                font-weight: bold;
            }}
            QPushButton:hover, QToolButton:hover {{
                background-color: {lighten(theme['SURFACE_CONTAINER'], 0.1)};
            }}
            QPushButton:pressed, QToolButton:pressed {{
                background-color: {darken(theme['SURFACE_CONTAINER'], 0.2)};
            }}
            QPushButton:disabled, QToolButton:disabled {{
                background-color: {darken(theme['SURFACE_CONTAINER'], 0.2)};
                color: {theme['ON_SURFACE_VARIANT']};
                border-color: {darken(theme['OUTLINE'], 0.2)};
            }}

            /* Filled Buttons for primary, high-emphasis actions */
            QPushButton[class~="filled"] {{
                background-color: {theme['PRIMARY']};
                color: {theme['ON_PRIMARY']};
            }}
            QPushButton[class~="filled"]:hover {{
                background-color: {lighten(theme['PRIMARY'], 0.1)};
            }}

            /* Destructive Buttons */
            QPushButton[class~="destructive"] {{
                background-color: {theme['DESTRUCTIVE']};
                color: {theme['ON_DESTRUCTIVE']};
            }}
            QPushButton[class~="destructive"]:hover {{
                background-color: {lighten(theme['DESTRUCTIVE'], 0.1)};
            }}

            /* Success Buttons */
            QPushButton[class~="success"] {{
                background-color: {theme['SUCCESS']};
                color: {theme['ON_SUCCESS']};
            }}
            QPushButton[class~="success"]:hover {{
                background-color: {lighten(theme['SUCCESS'], 0.1)};
            }}

            /* --- Static Toolbar --- */
            QFrame#StaticToolbar {{
                background-color: {theme['FRAME_BG']};
                border-top: 1px solid {theme['OUTLINE']};
                border-radius: 0px;
            }}
            QFrame#StaticToolbar QToolButton {{
                background-color: {theme['SURFACE_CONTAINER']};
                color: {lighten(theme['PRIMARY'], 0.2)};
                padding: 6px 12px;
                border-radius: 14px;
                font-size: 11pt;
            }}
            QFrame#StaticToolbar QToolButton:hover {{
                background-color: {lighten(theme['SURFACE_CONTAINER'], 0.1)};
            }}

            /* Colored toolbar buttons use background color for emphasis */
            QToolButton#crop_button {{
                background-color: {theme['SUCCESS']};
                color: {theme['ON_SUCCESS']};
            }}
            QToolButton#crop_button:hover {{ background-color: {lighten(theme['SUCCESS'], 0.1)}; }}

            QToolButton#delete_button {{
                background-color: {theme['DESTRUCTIVE']};
                color: {theme['ON_DESTRUCTIVE']};
            }}
            QToolButton#delete_button:hover {{ background-color: {lighten(theme['DESTRUCTIVE'], 0.1)}; }}

            QToolButton#restore_button {{
                background-color: {theme['WARNING']};
                color: {theme['ON_WARNING']};
            }}
            QToolButton#restore_button:hover {{ background-color: {lighten(theme['WARNING'], 0.1)}; }}


            /* --- LineEdits --- */
            QLineEdit {{
                background-color: {theme['SURFACE_CONTAINER']};
                border: 1px solid {theme['OUTLINE']};
                border-radius: 8px;
                padding: 8px;
            }}
            QLineEdit:focus {{ border: 2px solid {theme['PRIMARY']}; }}

            /* --- Group Boxes & Frames --- */
            QGroupBox {{
                background-color: {theme['FRAME_BG']};
                border: 1px solid {theme['OUTLINE']};
                border-radius: 12px;
                margin-top: 10px; padding: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px; left: 12px;
                color: {theme['ON_SURFACE_VARIANT']};
            }}
            QFrame#ViewerFrame {{
                background-color: transparent;
                border: 1px solid {theme['OUTLINE']};
                border-radius: 12px;
            }}
            QFrame#BottomBar {{
                background-color: {theme['FRAME_BG']};
                border-top: 1px solid {theme['OUTLINE']};
            }}

            /* --- Dock & Status Bar --- */
            QDockWidget {{ border: none; }}
            QDockWidget::title {{
                background-color: {theme['BG_COLOR']};
                text-align: left; padding: 8px; font-weight: bold;
                border-bottom: 1px solid {theme['OUTLINE']};
            }}

            /* --- List Widgets --- */
            QScrollArea {{
                border: none;
            }}

            QScrollBar:vertical {{
                border: none;
                background: {theme['FRAME_BG']};
                width: 8px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme['SURFACE_CONTAINER']};
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """
        return qss
