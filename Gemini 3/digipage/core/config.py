import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any

# --- Constants ---
CONFIG_FILE = "config.json"
BOOKS_COMPLETE_LOG_FILE = "books_complete_log.json"
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}
BACKUP_DIR = "scan_viewer_backups"

@dataclass
class AppConfig:
    """
    Typed data container for application configuration.
    Allows access via dot notation (e.g., config.theme).
    """
    scan_folder: str = ""
    todays_books_folder: str = ""
    city_paths: Dict[str, str] = field(default_factory=dict)
    lighting_standard_folder: str = ""
    lighting_standard_metrics: Optional[Dict[str, Any]] = None
    auto_lighting_correction_enabled: bool = False
    auto_color_correction_enabled: bool = False
    auto_sharpening_enabled: bool = False
    theme: str = "Material Dark"
    image_load_timeout_ms: int = 4000
    caching_enabled: bool = True
    scanner_mode: str = "dual_scan"

class ConfigManager:
    """
    Handles loading and saving the configuration to JSON, 
    converting between dictionaries and the AppConfig dataclass.
    """
    
    @staticmethod
    def load() -> AppConfig:
        """Loads the config from file, filling missing keys with defaults."""
        if not os.path.exists(CONFIG_FILE):
            return AppConfig()
        
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Filter data to only include keys that exist in AppConfig fields
            # This prevents crashes if the JSON has stale/unknown keys
            valid_keys = AppConfig.__annotations__.keys()
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}
            
            return AppConfig(**filtered_data)
        except (IOError, json.JSONDecodeError):
            print("Error loading config file. Using defaults.")
            return AppConfig()

    @staticmethod
    def save(config: AppConfig):
        """Saves the AppConfig object to the JSON file."""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(asdict(config), f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving config: {e}")