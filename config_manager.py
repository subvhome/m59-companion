import json
import os
import logging
# Use the standardized logger name for the config module
logger = logging.getLogger("m59.config")
class ConfigManager:
    def __init__(self, filepath="config.json"):
        self.filepath = os.path.join(os.getcwd(), filepath)
        self.defaults = {
            "server": {"points_slope": 7.0, "max_points": 16.0, "min_needed_floor": 225},
            "character": {"intellect": 25}
        }
        self.settings = self.defaults.copy()
        # Log the path during initialization for easier troubleshooting
        logger.debug(f"ConfigManager initialized. Path: {self.filepath}")
        self.load()
    def load(self):
        """Loads settings from config.json or falls back to defaults."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    self.settings = json.load(f)
                    logger.info(f"Configuration successfully loaded from {self.filepath}")
            except Exception as e:
                logger.error(f"Failed to parse {self.filepath}: {e}")
                self.settings = self.defaults.copy()
        else:
            logger.warning(f"Config file not found at {self.filepath}. Using defaults.")
    def save(self, new_settings):
        """Saves the current settings dictionary to the config.json file."""
        self.settings = new_settings
        try:
            with open(self.filepath, 'w') as f:
                json.dump(self.settings, f, indent=4)
                logger.info("Configuration saved to disk.")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
