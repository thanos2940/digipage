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
    "theme": "Neutral Grey",
    "image_load_timeout_ms": 2000,
}

# --- Helper functions for color manipulation (from scanner2.py) ---
def lighten_color(hex_color, factor=0.1):
    """Increases the lightness of a hex color."""
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = min(1.0, hls[1] + factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

def darken_color(hex_color, factor=0.1):
    """Decreases the lightness of a hex color."""
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = max(0.0, hls[1] - factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))


# --- UI Style Configuration (from scanner2.py) ---
THEMES = {
    "Neutral Grey": {
        "BG_COLOR": "#2b2b2b", "FG_COLOR": "#bbbbbb", "TEXT_SECONDARY_COLOR": "#888888",
        "BTN_BG": "#3c3f41", "BTN_FG": "#f0f0f0",
        "ACCENT_COLOR": "#8A8F94", "FRAME_BG": "#333333", "FRAME_BORDER": "#444444",
        "TOOLTIP_BG": "#252526", "TOOLTIP_FG": "#ffffff",
        "SUCCESS_COLOR": "#28a745", "DESTRUCTIVE_COLOR": "#dc3545", "WARNING_COLOR": "#ffc107",
        "JUMP_BTN_BREATHE_COLOR": "#6495ED", "TRANSFER_BTN_COLOR": "#ff8c00", "CROP_BTN_COLOR": "#007bff",
    },
    "Blue": {
        "BG_COLOR": "#262D3F", "FG_COLOR": "#D0D5E8", "TEXT_SECONDARY_COLOR": "#8993B3",
        "BTN_BG": "#3A435E", "BTN_FG": "#E1E6F5",
        "ACCENT_COLOR": "#6C95FF", "FRAME_BG": "#2C354D", "FRAME_BORDER": "#3E486B",
        "TOOLTIP_BG": "#202533", "TOOLTIP_FG": "#ffffff",
        "SUCCESS_COLOR": "#33B579", "DESTRUCTIVE_COLOR": "#FF6B6B", "WARNING_COLOR": "#FFD166",
        "JUMP_BTN_BREATHE_COLOR": "#FFD166", "TRANSFER_BTN_COLOR": "#EF9595", "CROP_BTN_COLOR": "#4DB6AC",
    },
    "Pink": {
        "BG_COLOR": "#3D2A32", "FG_COLOR": "#F5DDE7", "TEXT_SECONDARY_COLOR": "#A8939D",
        "BTN_BG": "#5C3F4A", "BTN_FG": "#FCEAF1",
        "ACCENT_COLOR": "#FF80AB", "FRAME_BG": "#4A333D", "FRAME_BORDER": "#664553",
        "TOOLTIP_BG": "#302228", "TOOLTIP_FG": "#ffffff",
        "SUCCESS_COLOR": "#50C878", "DESTRUCTIVE_COLOR": "#FF6961", "WARNING_COLOR": "#FFD700",
        "JUMP_BTN_BREATHE_COLOR": "#6495ED", "TRANSFER_BTN_COLOR": "#87CEEB", "CROP_BTN_COLOR": "#9370DB",
    }
}

def generate_stylesheet(theme_name="Neutral Grey"):
    """Generates a full QSS stylesheet from a theme dictionary."""
    theme = THEMES.get(theme_name, THEMES["Neutral Grey"])

    # Derived colors
    btn_hover_bg = lighten_color(theme["BTN_BG"], 0.1)
    btn_press_bg = darken_color(theme["BTN_BG"], 0.1)

    qss = f"""
        /* --- Global --- */
        QWidget {{
            background-color: {theme['BG_COLOR']};
            color: {theme['FG_COLOR']};
            font-family: Segoe UI, Arial, sans-serif;
            font-size: 10pt;
        }}

        /* --- Main Window & Dialogs --- */
        QMainWindow, QDialog {{
            background-color: {theme['BG_COLOR']};
        }}

        /* --- Labels --- */
        QLabel {{
            background-color: transparent;
            color: {theme['FG_COLOR']};
        }}

        /* --- Buttons --- */
        QPushButton {{
            background-color: {theme['BTN_BG']};
            color: {theme['BTN_FG']};
            border: 1px solid {theme['FRAME_BORDER']};
            padding: 8px 16px;
            border-radius: 4px;
        }}
        QPushButton:hover {{
            background-color: {btn_hover_bg};
        }}
        QPushButton:pressed {{
            background-color: {btn_press_bg};
        }}
        QPushButton:disabled {{
            background-color: {darken_color(theme['BTN_BG'], 0.2)};
            color: {theme['TEXT_SECONDARY_COLOR']};
        }}

        /* --- LineEdits --- */
        QLineEdit {{
            background-color: {darken_color(theme['BG_COLOR'], 0.1)};
            border: 1px solid {theme['FRAME_BORDER']};
            border-radius: 4px;
            padding: 5px;
            color: {theme['FG_COLOR']};
        }}
        QLineEdit:focus {{
            border: 1px solid {theme['ACCENT_COLOR']};
        }}
        QLineEdit:readonly {{
            background-color: {theme['FRAME_BG']};
        }}

        /* --- List Widgets --- */
        QListWidget {{
            background-color: {darken_color(theme['BG_COLOR'], 0.1)};
            border: 1px solid {theme['FRAME_BORDER']};
            border-radius: 4px;
        }}
        QListWidget::item {{
            padding: 8px;
        }}
        QListWidget::item:selected {{
            background-color: {theme['ACCENT_COLOR']};
            color: {theme['BTN_FG']};
        }}
        QListWidget::item:hover:!selected {{
            background-color: {theme['FRAME_BG']};
        }}

        /* --- Tab Widgets --- */
        QTabWidget::pane {{
            border: 1px solid {theme['FRAME_BORDER']};
            border-radius: 4px;
            padding: 10px;
        }}
        QTabBar::tab {{
            background-color: {theme['BTN_BG']};
            color: {theme['BTN_FG']};
            padding: 10px 20px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            border: 1px solid {theme['FRAME_BORDER']};
            border-bottom: none;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {theme['ACCENT_COLOR']};
            color: #ffffff;
        }}
        QTabBar::tab:!selected:hover {{
            background-color: {btn_hover_bg};
        }}

        /* --- Checkboxes --- */
        QCheckBox {{
            spacing: 10px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {theme['FRAME_BORDER']};
            border-radius: 3px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {theme['ACCENT_COLOR']};
            image: url(placeholder.png); /* Will need a checkmark icon */
        }}
        QCheckBox::indicator:unchecked:hover {{
            border: 1px solid {theme['ACCENT_COLOR']};
        }}

        /* --- Sliders --- */
        QSlider::groove:horizontal {{
            border: 1px solid {theme['FRAME_BORDER']};
            height: 4px;
            background: {darken_color(theme['BG_COLOR'], 0.2)};
            margin: 2px 0;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {theme['ACCENT_COLOR']};
            border: 1px solid {theme['ACCENT_COLOR']};
            width: 16px;
            height: 16px;
            margin: -7px 0;
            border-radius: 8px;
        }}

        /* --- Dock Widgets --- */
        QDockWidget {{
            titlebar-close-icon: url(placeholder.png);
            titlebar-normal-icon: url(placeholder.png);
        }}
        QDockWidget::title {{
            background-color: {theme['FRAME_BG']};
            text-align: left;
            padding: 8px;
        }}

        /* --- Scrollbars --- */
        QScrollBar:vertical {{
            border: none;
            background: {theme['FRAME_BG']};
            width: 12px;
            margin: 0px 0px 0px 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {theme['BTN_BG']};
            min-height: 20px;
            border-radius: 6px;
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
    """Loads the configuration from config.json, or returns defaults."""
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            # Ensure all keys from default are present
            for key, value in DEFAULT_CONFIG.items():
                config.setdefault(key, value)
            return config
    except (IOError, json.JSONDecodeError):
        return DEFAULT_CONFIG

def save_config(config_data):
    """Saves the configuration data to config.json."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
    except IOError as e:
        print(f"Error saving config: {e}")
