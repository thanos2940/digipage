import os
from .utils import lighten_color, darken_color

# --- Modern Dark Theme Definition ---
MODERN_THEME = {
    # Backgrounds
    "BG_MAIN": "#121212",           # Main app background (very dark grey)
    "BG_SIDEBAR": "#1E1E1E",        # Sidebar background
    "BG_CARD": "#2C2C2C",           # Card/Panel background
    "BG_INPUT": "#383838",          # Input fields
    "BG_HOVER": "#404040",          # Hover states

    # Primary / Accents
    "PRIMARY": "#3B82F6",           # Bright Blue (Tailwind Blue-500 approx)
    "PRIMARY_HOVER": "#2563EB",     # Darker Blue
    "PRIMARY_TEXT": "#FFFFFF",      # Text on primary

    # Status
    "SUCCESS": "#10B981",           # Green
    "WARNING": "#F59E0B",           # Amber
    "DANGER": "#EF4444",            # Red

    # Text
    "TEXT_MAIN": "#E5E5E5",         # High emphasis
    "TEXT_SECONDARY": "#A3A3A3",    # Medium emphasis
    "TEXT_DISABLED": "#525252",     # Low emphasis

    # Borders / Dividers
    "BORDER": "#404040",

    # Radii
    "RADIUS_SM": "4px",
    "RADIUS_MD": "8px",
    "RADIUS_LG": "12px",
}

def get_stylesheet():
    t = MODERN_THEME

    qss = f"""
    /* --- Global Reset --- */
    * {{
        font-family: "Segoe UI", "Roboto", "Helvetica Neue", Arial, sans-serif;
        font-size: 10pt;
        color: {t['TEXT_MAIN']};
        border: none;
        outline: none;
    }}

    /* --- Main Container --- */
    QMainWindow, QWidget#MainContainer {{
        background-color: {t['BG_MAIN']};
    }}

    /* --- Sidebar --- */
    QWidget#Sidebar {{
        background-color: {t['BG_SIDEBAR']};
        border-left: 1px solid {t['BORDER']};
    }}

    /* --- Cards & Panels --- */
    QFrame#Card, QGroupBox {{
        background-color: {t['BG_CARD']};
        border-radius: {t['RADIUS_MD']};
        border: 1px solid {t['BORDER']};
    }}

    QGroupBox {{
        margin-top: 1em;
        padding-top: 10px;
        font-weight: bold;
        color: {t['TEXT_SECONDARY']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        left: 10px;
    }}

    /* --- Inputs --- */
    QLineEdit {{
        background-color: {t['BG_INPUT']};
        border: 1px solid {t['BORDER']};
        border-radius: {t['RADIUS_SM']};
        padding: 8px;
        color: {t['TEXT_MAIN']};
        selection-background-color: {t['PRIMARY']};
    }}
    QLineEdit:focus {{
        border: 1px solid {t['PRIMARY']};
    }}

    /* --- Scrollbars --- */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: {t['BG_MAIN']};
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {t['BG_HOVER']};
        min-height: 20px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t['TEXT_DISABLED']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    /* --- Buttons --- */
    QPushButton {{
        background-color: {t['BG_CARD']};
        color: {t['TEXT_MAIN']};
        border: 1px solid {t['BORDER']};
        border-radius: {t['RADIUS_MD']};
        padding: 8px 16px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {t['BG_HOVER']};
        border-color: {t['TEXT_SECONDARY']};
    }}
    QPushButton:pressed {{
        background-color: {darken_color(t['BG_HOVER'], 0.1)};
    }}
    QPushButton:disabled {{
        color: {t['TEXT_DISABLED']};
        background-color: {t['BG_MAIN']};
        border-color: {t['BG_HOVER']};
    }}

    /* Primary Action Button */
    QPushButton[class~="primary"] {{
        background-color: {t['PRIMARY']};
        color: {t['PRIMARY_TEXT']};
        border: 1px solid {t['PRIMARY']};
    }}
    QPushButton[class~="primary"]:hover {{
        background-color: {t['PRIMARY_HOVER']};
        border-color: {t['PRIMARY_HOVER']};
    }}
    QPushButton[class~="primary"]:pressed {{
        background-color: {darken_color(t['PRIMARY_HOVER'], 0.1)};
    }}

    /* Destructive Action Button */
    QPushButton[class~="danger"] {{
        background-color: {t['BG_CARD']};
        color: {t['DANGER']};
        border: 1px solid {t['BORDER']};
    }}
    QPushButton[class~="danger"]:hover {{
        background-color: {t['DANGER']};
        color: white;
        border-color: {t['DANGER']};
    }}

    /* Icon/Tool Buttons */
    QToolButton {{
        background-color: transparent;
        border: none;
        border-radius: {t['RADIUS_SM']};
        padding: 6px;
    }}
    QToolButton:hover {{
        background-color: {t['BG_HOVER']};
    }}

    /* --- Labels --- */
    QLabel#H1 {{
        font-size: 18pt;
        font-weight: bold;
        color: {t['TEXT_MAIN']};
    }}
    QLabel#H2 {{
        font-size: 14pt;
        font-weight: 600;
        color: {t['TEXT_MAIN']};
    }}
    QLabel#H3 {{
        font-size: 11pt;
        font-weight: 600;
        color: {t['TEXT_SECONDARY']};
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    QLabel#Dim {{
        color: {t['TEXT_DISABLED']};
    }}

    /* --- Toast --- */
    QWidget#Toast {{
        background-color: {t['BG_CARD']};
        border: 1px solid {t['PRIMARY']};
        border-radius: {t['RADIUS_MD']};
    }}
    """
    return qss
