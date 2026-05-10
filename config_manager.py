import json
import os
from utils import resource_path
class ConfigManager:
    def __init__(self):
        # We always save/load from the folder where the EXE/script is located
        # to ensure settings persist.
        self.config_path = "config.json"
        self.settings = self.load()
    def load(self):
        # Default settings
        default_settings = {
            "character": {
                "intellect": 18,
                "testing_mode": False
            }
        }
        
        # 1. Look for existing config next to the EXE
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        # 2. If not found, look for a bundled default (optional)
        bundled_config = resource_path("config.json")
        if os.path.exists(bundled_config) and bundled_config != self.config_path:
            try:
                with open(bundled_config, "r") as f:
                    return json.load(f)
            except Exception:
                pass
                
        return default_settings
    def save(self, settings):
        self.settings = settings
        try:
            with open(self.config_path, "w") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
