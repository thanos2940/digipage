import json
import os

# Define the path for the configuration file
CONFIG_FILE = 'config.json'

# --- THEME DEFINITIONS ---
THEMES = {
    "Neutral Grey": {
        "BACKGROUND_PRIMARY": "#2E2E2E",
        "BACKGROUND_SECONDARY": "#3C3C3C",
        "BACKGROUND_TERTIARY": "#252525",
        "TEXT_PRIMARY": "#E0E0E0",
        "TEXT_SECONDARY": "#A0A0A0",
        "ACCENT_PRIMARY": "#5A9BD5",
        "ACCENT_SECONDARY": "#4A80B2",
        "BORDER_PRIMARY": "#4A4A4A",
        "SUCCESS": "#77DD77",
        "WARNING": "#FFB74D",
        "ERROR": "#FF5252",
    },
    "Blue": {
        "BACKGROUND_PRIMARY": "#2C3E50",
        "BACKGROUND_SECONDARY": "#34495E",
        "BACKGROUND_TERTIARY": "#233140",
        "TEXT_PRIMARY": "#ECF0F1",
        "TEXT_SECONDARY": "#BDC3C7",
        "ACCENT_PRIMARY": "#3498DB",
        "ACCENT_SECONDARY": "#2980B9",
        "BORDER_PRIMARY": "#2C3E50",
        "SUCCESS": "#2ECC71",
        "WARNING": "#F39C12",
        "ERROR": "#E74C3C",
    },
    "Pink": {
        "BACKGROUND_PRIMARY": "#3B2E3C",
        "BACKGROUND_SECONDARY": "#4A3A4B",
        "BACKGROUND_TERTIARY": "#312632",
        "TEXT_PRIMARY": "#F5E6F6",
        "TEXT_SECONDARY": "#D1C4D3",
        "ACCENT_PRIMARY": "#E574E8",
        "ACCENT_SECONDARY": "#D950DD",
        "BORDER_PRIMARY": "#4A3A4B",
        "SUCCESS": "#A1E874",
        "WARNING": "#E8D174",
        "ERROR": "#E87474",
    }
}

# --- STYLESHEET GENERATION ---
def generate_stylesheet(theme_name: str) -> str:
    """Generates a full Qt stylesheet from a theme name."""
    if theme_name not in THEMES:
        theme_name = "Neutral Grey"
    colors = THEMES[theme_name]

    return f"""
        QWidget {{
            background-color: {colors["BACKGROUND_SECONDARY"]};
            color: {colors["TEXT_PRIMARY"]};
            font-family: "Segoe UI", "Cantarell", "sans-serif";
            font-size: 10pt;
        }}
        QMainWindow, QDialog {{
            background-color: {colors["BACKGROUND_PRIMARY"]};
        }}
        QDockWidget {{
            titlebar-close-icon: none;
            titlebar-float-icon: none;
        }}
        QGroupBox {{
            background-color: {colors["BACKGROUND_SECONDARY"]};
            border: 1px solid {colors["BORDER_PRIMARY"]};
            border-radius: 5px;
            margin-top: 1ex; /* leave space at the top for the title */
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left; /* position at the top left */
            padding: 0 3px;
            left: 10px;
            background-color: {colors["BACKGROUND_SECONDARY"]};
            color: {colors["ACCENT_PRIMARY"]};
        }}
        QLineEdit, QTextEdit, QSpinBox {{
            background-color: {colors["BACKGROUND_TERTIARY"]};
            border: 1px solid {colors["BORDER_PRIMARY"]};
            border-radius: 4px;
            padding: 5px;
            color: {colors["TEXT_PRIMARY"]};
        }}
        QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {{
            border-color: {colors["ACCENT_PRIMARY"]};
        }}
        QPushButton {{
            background-color: {colors["ACCENT_PRIMARY"]};
            color: {colors["BACKGROUND_PRIMARY"]};
            border: none;
            border-radius: 4px;
            padding: 8px 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {colors["ACCENT_SECONDARY"]};
        }}
        QPushButton:pressed {{
            background-color: {colors["BACKGROUND_TERTIARY"]};
        }}
        QPushButton:disabled {{
            background-color: {colors["BACKGROUND_TERTIARY"]};
            color: {colors["TEXT_SECONDARY"]};
        }}
        QListWidget {{
            background-color: {colors["BACKGROUND_TERTIARY"]};
            border: 1px solid {colors["BORDER_PRIMARY"]};
            border-radius: 4px;
            padding: 2px;
        }}
        QListWidget::item {{
            padding: 5px;
        }}
        QListWidget::item:hover {{
            background-color: {colors["BACKGROUND_PRIMARY"]};
        }}
        QListWidget::item:selected {{
            background-color: {colors["ACCENT_PRIMARY"]};
            color: {colors["BACKGROUND_PRIMARY"]};
        }}
        QTabWidget::pane {{
            border: 1px solid {colors["BORDER_PRIMARY"]};
            border-top: none;
        }}
        QTabBar::tab {{
            background: {colors["BACKGROUND_SECONDARY"]};
            color: {colors["TEXT_SECONDARY"]};
            padding: 8px 20px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            border: 1px solid {colors["BORDER_PRIMARY"]};
            border-bottom: none;
        }}
        QTabBar::tab:selected {{
            background: {colors["BACKGROUND_PRIMARY"]};
            color: {colors["TEXT_PRIMARY"]};
        }}
        QTabBar::tab:!selected:hover {{
            background: {colors["ACCENT_SECONDARY"]};
            color: {colors["TEXT_PRIMARY"]};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
        }}
        QSlider::groove:horizontal {{
            border: 1px solid {colors["BORDER_PRIMARY"]};
            height: 4px;
            background: {colors["BACKGROUND_TERTIARY"]};
            margin: 2px 0;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {colors["ACCENT_PRIMARY"]};
            border: 1px solid {colors["ACCENT_PRIMARY"]};
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        QLabel#StatusLabel {{
            color: {colors["TEXT_SECONDARY"]};
            font-style: italic;
        }}
        QLabel#ErrorLabel {{
            color: {colors["ERROR"]};
            font-weight: bold;
        }}
    """

# --- CONFIGURATION MANAGEMENT ---
def get_default_config():
    """Returns a dictionary with the default configuration."""
    return {
        "scan_folder": "",
        "today_books_folder": "",
        "city_data_paths": {},  # e.g., {"001": "/path/to/city/001"}
        "reference_images_folder": "",
        "reference_template_path": "",
        "auto_adjust_lighting": True,
        "auto_correct_color": True,
        "apply_sharpening": True,
        "current_theme": "Neutral Grey",
    }

def save_config(data: dict):
    """Saves the configuration dictionary to the JSON file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        print(f"Error saving configuration: {e}")

def load_config() -> dict:
    """
    Loads the configuration from the JSON file.
    If the file doesn't exist, it creates it with default values.
    """
    if not os.path.exists(CONFIG_FILE):
        print("Configuration file not found. Creating with default values.")
        default_config = get_default_config()
        save_config(default_config)
        return default_config

    try:
        with open(CONFIG_FILE, 'r') as f:
            # First, load defaults, then overwrite with saved values
            # This makes the app robust to new config keys being added
            config = get_default_config()
            config.update(json.load(f))
            return config
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading or parsing configuration file: {e}. Loading defaults.")
        return get_default_config()

def is_config_valid(config: dict) -> bool:
    """
    Checks if the essential configuration paths are set.
    """
    scan_folder = config.get("scan_folder")
    today_folder = config.get("today_books_folder")

    if not scan_folder or not os.path.isdir(scan_folder):
        return False
    if not today_folder or not os.path.isdir(today_folder):
        return False

    return True
