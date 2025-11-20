import os
import json
import colorsys

# --- File Paths ---
CONFIG_FILE = "config.json"
BOOKS_COMPLETE_LOG_FILE = "books_complete_log.json"
BACKUP_DIR = "scan_viewer_backups"

# --- Constants ---
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}

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
    "scanner_mode": "dual_scan",
}

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
        "ON_PRIMARY": "#ffffff",
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
        "ON_SUCCESS": "#ffffff",
        "ON_WARNING": "#000000",
    }
}
