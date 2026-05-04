import json
import os

class ConfigManager:
    def __init__(self, filepath="config.json"):
        self.filepath = filepath
        # Default values based on standard server logic
        self.defaults = {
            "server": {
                "points_slope": 7.0,
                "max_points": 16.0,
                "min_needed_floor": 225
            },
            "character": {
                "intellect": 25
            }
        }
        self.settings = self.defaults.copy()
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    self.settings = json.load(f)
            except:
                self.settings = self.defaults.copy()

    def save(self, new_settings):
        self.settings = new_settings
        with open(self.filepath, 'w') as f:
            json.dump(self.settings, f, indent=4)
