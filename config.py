import json
import os
import colorsys

# --- Configuration File ---
CONFIG_FILE = "config.json"
BOOKS_COMPLETE_LOG_FILE = "books_complete_log.json"
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}
BACKUP_DIR = "scan_viewer_backups"
DEFAULT_CONFIG = {
    "scan_folder": "",
    "todays_books_folder": "",
    "city_paths": {},
    "lighting_standard_folder": "",
    "lighting_standard_metrics": None,
    "auto_lighting_correction_enabled": False,
    "auto_color_correction_enabled": False,
    "auto_sharpening_enabled": False,
    "theme": "Material Dark",
    "image_load_timeout_ms": 4000,
    "caching_enabled": True,
}

# --- Helper functions for color manipulation ---
def lighten_color(hex_color, factor=0.1):
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = min(1.0, hls[1] + factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

def darken_color(hex_color, factor=0.1):
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = max(0.0, hls[1] - factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))


# --- UI Style Configuration ---
THEMES = {
    "Material Dark": {
        "BG_COLOR": "#1c1b1f",
        "FRAME_BG": "#252428",
        "SURFACE_CONTAINER": "#36343b",
        "PRIMARY": "#b0c6ff",
        "ON_PRIMARY": "#1c305f",
        "SECONDARY": "#c3c5dd",
        "ON_SECONDARY": "#2e3042",
        "TERTIARY": "#e2bada",
        "ON_TERTIARY": "#462640",
        "SURFACE": "#1c1b1f",
        "ON_SURFACE": "#e5e1e6",
        "ON_SURFACE_VARIANT": "#c8c5d0",
        "OUTLINE": "#928f99",
        "SUCCESS": "#73d983",
        "DESTRUCTIVE": "#bb3223",
        "WARNING": "#ffd965",
        "ON_DESTRUCTIVE": "#690005",
        "ON_SUCCESS": "#003916",
        "ON_WARNING": "#251a00",
    },
    "Neutral Grey": {
        "BG_COLOR": "#2b2b2b",
        "FRAME_BG": "#313335",
        "SURFACE_CONTAINER": "#3c3f41",
        "PRIMARY": "#4e81ee",
        "ON_PRIMARY": "#ffffff",
        "SECONDARY": "#8A8F94",
        "ON_SECONDARY": "#ffffff",
        "TERTIARY": "#c4730a",
        "ON_TERTIARY": "#000000",
        "SURFACE": "#2b2b2b",
        "ON_SURFACE": "#dcdcdc",
        "ON_SURFACE_VARIANT": "#888888",
        "OUTLINE": "#444444",
        "SUCCESS": "#28a745",
        "DESTRUCTIVE": "#b62d3b",
        "WARNING": "#ffc107",
        "ON_DESTRUCTIVE": "#ffffff",
        "ON_SUCCESS": "#ffffff",
        "ON_WARNING": "#000000",
    },
    "Blue": {
        "BG_COLOR": "#262D3F",
        "FRAME_BG": "#2C354D",
        "SURFACE_CONTAINER": "#3A435E",
        "PRIMARY": "#6C95FF",
        "ON_PRIMARY": "#ffffff", # Changed from dark blue for high contrast
        "SECONDARY": "#8993B3",
        "ON_SECONDARY": "#E1E6F5",
        "TERTIARY": "#CA6E04",
        "ON_TERTIARY": "#000000",
        "SURFACE": "#262D3F",
        "ON_SURFACE": "#D0D5E8",
        "ON_SURFACE_VARIANT": "#8993B3",
        "OUTLINE": "#3E486B",
        "SUCCESS": "#33B579",
        "DESTRUCTIVE": "#C44646",
        "WARNING": "#FFD166",
        "ON_DESTRUCTIVE": "#ffffff",
        "ON_SUCCESS": "#ffffff", # Changed from black for high contrast
        "ON_WARNING": "#000000",
    }
}

def generate_stylesheet(theme_name="Material Dark"):
    theme = THEMES.get(theme_name, THEMES["Material Dark"])

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
            color: {lighten_color(theme['PRIMARY'],0.2)};
            border: none;
            padding: 8px 16px;
            border-radius: 16px;
            font-weight: bold;
        }}
        QPushButton:hover, QToolButton:hover {{
            background-color: {lighten_color(theme['SURFACE_CONTAINER'], 0.1)};
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background-color: {darken_color(theme['SURFACE_CONTAINER'], 0.2)};
        }}
        QPushButton:disabled, QToolButton:disabled {{
            background-color: {darken_color(theme['SURFACE_CONTAINER'], 0.2)};
            color: {theme['ON_SURFACE_VARIANT']};
            border-color: {darken_color(theme['OUTLINE'], 0.2)};
        }}

        /* Filled Buttons for primary, high-emphasis actions */
        QPushButton[class~="filled"] {{
            background-color: {theme['PRIMARY']};
            color: {theme['ON_PRIMARY']};
        }}
        QPushButton[class~="filled"]:hover {{
            background-color: {lighten_color(theme['PRIMARY'], 0.1)};
        }}

        /* Destructive Buttons */
        QPushButton[class~="destructive"] {{
            background-color: {theme['DESTRUCTIVE']};
            color: {theme['ON_DESTRUCTIVE']};
        }}
        QPushButton[class~="destructive"]:hover {{
            background-color: {lighten_color(theme['DESTRUCTIVE'], 0.1)};
        }}

        /* Success Buttons */
        QPushButton[class~="success"] {{
            background-color: {theme['SUCCESS']};
            color: {theme['ON_SUCCESS']};
        }}
        QPushButton[class~="success"]:hover {{
            background-color: {lighten_color(theme['SUCCESS'], 0.1)};
        }}
        
        /* --- Static Toolbar --- */
        QFrame#StaticToolbar {{
            background-color: {theme['FRAME_BG']};
            border-top: 1px solid {theme['OUTLINE']};
            border-radius: 0px;
        }}
        QFrame#StaticToolbar QToolButton {{
            background-color: {theme['SURFACE_CONTAINER']};
            color: {lighten_color(theme['PRIMARY'], 0.2)};
            padding: 6px 12px;
            border-radius: 14px;
            font-size: 11pt;
        }}
        QFrame#StaticToolbar QToolButton:hover {{
            background-color: {lighten_color(theme['SURFACE_CONTAINER'], 0.1)};
        }}

        /* Colored toolbar buttons use background color for emphasis */
        QToolButton#crop_button {{
            background-color: {theme['SUCCESS']};
            color: {theme['ON_SUCCESS']};
        }}
        QToolButton#crop_button:hover {{ background-color: {lighten_color(theme['SUCCESS'], 0.1)}; }}

        QToolButton#delete_button {{
            background-color: {theme['DESTRUCTIVE']};
            color: {theme['ON_DESTRUCTIVE']};
        }}
        QToolButton#delete_button:hover {{ background-color: {lighten_color(theme['DESTRUCTIVE'], 0.1)}; }}

        QToolButton#restore_button {{
            background-color: {theme['WARNING']};
            color: {theme['ON_WARNING']};
        }}
        QToolButton#restore_button:hover {{ background-color: {lighten_color(theme['WARNING'], 0.1)}; }}


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

# --- Config Management ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        for key, value in DEFAULT_CONFIG.items():
            config_data.setdefault(key, value)
        return config_data
    except (IOError, json.JSONDecodeError):
        return DEFAULT_CONFIG

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving config: {e}")