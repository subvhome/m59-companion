import json
import os
import logging

logger = logging.getLogger("m59.config")

class ConfigManager:
    def __init__(self, filepath="config.json"):
        self.filepath = os.path.join(os.getcwd(), filepath)
        self.defaults = {
            "server": {"points_slope": 7.0, "max_points": 16.0, "min_needed_floor": 225},
            "character": {
                "intellect": 25, 
                "chat_log_enabled": False,
                "testing_mode": True  # Toggle this to False for production
            }
        }
        self.settings = self.defaults.copy()
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    self.settings = json.load(f)
                    # Merge defaults for any missing keys
                    for k, v in self.defaults["character"].items():
                        if k not in self.settings["character"]:
                            self.settings["character"][k] = v
            except Exception as e:
                logger.error(f"Failed to parse {self.filepath}: {e}")
                self.settings = self.defaults.copy()
        else:
            self.save(self.defaults)

    def save(self, new_settings):
        self.settings = new_settings
        try:
            with open(self.filepath, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
