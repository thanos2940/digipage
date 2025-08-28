# --- UI Style Configuration ---
THEMES = {
    "Neutral Grey": {
        "BG_COLOR": "#2b2b2b", "FG_COLOR": "#bbbbbb", "TEXT_SECONDARY_COLOR": "#888888",
        "BTN_BG": "#3c3f41", "BTN_FG": "#f0f0f0",
        "ACCENT_COLOR": "#8A8F94", "FRAME_BG": "#333333", "FRAME_BORDER": "#444444",
        "TOOLTIP_BG": "#252526", "TOOLTIP_FG": "#ffffff",
        # Special buttons
        "SUCCESS_COLOR": "#28a745", "DESTRUCTIVE_COLOR": "#dc3545", "WARNING_COLOR": "#ffc107",
        "JUMP_BTN_BREATHE_COLOR": "#6495ED", "TRANSFER_BTN_COLOR": "#ff8c00", "CROP_BTN_COLOR": "#007bff",
    },
    "Blue": {
        "BG_COLOR": "#262D3F", "FG_COLOR": "#D0D5E8", "TEXT_SECONDARY_COLOR": "#8993B3",
        "BTN_BG": "#3A435E", "BTN_FG": "#E1E6F5",
        "ACCENT_COLOR": "#6C95FF", "FRAME_BG": "#2C354D", "FRAME_BORDER": "#3E486B",
        "TOOLTIP_BG": "#202533", "TOOLTIP_FG": "#ffffff",
        # Special buttons
        "SUCCESS_COLOR": "#33B579", "DESTRUCTIVE_COLOR": "#FF6B6B", "WARNING_COLOR": "#FFD166",
        "JUMP_BTN_BREATHE_COLOR": "#FFD166", "TRANSFER_BTN_COLOR": "#EF9595", "CROP_BTN_COLOR": "#4DB6AC",
    },
    "Pink": {
        "BG_COLOR": "#3D2A32", "FG_COLOR": "#F5DDE7", "TEXT_SECONDARY_COLOR": "#A8939D",
        "BTN_BG": "#5C3F4A", "BTN_FG": "#FCEAF1",
        "ACCENT_COLOR": "#FF80AB", "FRAME_BG": "#4A333D", "FRAME_BORDER": "#664553",
        "TOOLTIP_BG": "#302228", "TOOLTIP_FG": "#ffffff",
        # Special buttons
        "SUCCESS_COLOR": "#50C878", "DESTRUCTIVE_COLOR": "#FF6961", "WARNING_COLOR": "#FFD700",
        "JUMP_BTN_BREATHE_COLOR": "#6495ED", "TRANSFER_BTN_COLOR": "#87CEEB", "CROP_BTN_COLOR": "#9370DB",
    }
}

# --- App Configuration ---
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}
BACKUP_DIR = "scan_viewer_backups"
CONFIG_FILE = "scan_viewer_config.json"
BOOKS_COMPLETE_LOG_FILE = "books_complete_log.json"
DEFAULT_IMAGE_LOAD_TIMEOUT_MS = 2000
PERFORMANCE_WINDOW_SECONDS = 20 # Window for live performance calculation
