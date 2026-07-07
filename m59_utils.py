import os
import sys
import re
import win32gui
import win32process
import win32con
import logging
import json
import shutil

logger = logging.getLogger("m59.utils")

def migrate_settings():
    old_locations = ["logs", "."]
    settings_dir = "settings"
    
    if not os.path.exists(settings_dir):
        os.makedirs(settings_dir, exist_ok=True)
        
    for loc in old_locations:
        if not os.path.exists(loc):
            continue
        for f in os.listdir(loc):
            if f.endswith(".json"):
                if f in ["config.json", "gui_settings.json", "m59_filters.json", "m59_data.json", "items.json", "meridian_rooms_dataset.json", "travel_times.json"]:
                    if loc != "settings":
                        old_path = os.path.join(loc, f)
                        new_path = os.path.join(settings_dir, f)
                        try:
                            if not os.path.exists(new_path):
                                shutil.move(old_path, new_path)
                                logger.info(f"MIGRATION: Moved {f} from {loc} to {settings_dir}")
                        except Exception as e:
                            logger.error(f"MIGRATION ERROR: Failed to move {f}: {e}")
                else:
                    old_path = os.path.join(loc, f)
                    new_path = os.path.join(settings_dir, f)
                    try:
                        if not os.path.exists(new_path):
                            shutil.move(old_path, new_path)
                            logger.info(f"MIGRATION: Moved {f} from {loc} to {settings_dir}")
                    except Exception as e:
                        logger.error(f"MIGRATION ERROR: Failed to move {f}: {e}")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_safe_name(name):
    """Sanitizes character names for file paths and persistence."""
    if not name or name == "Unknown":
        return "Unknown"
    return name.replace(" ", "_")

def find_game_hwnd(pid):
    """Finds the main game window handle for a given PID using robust enumeration."""
    found = [None]
    def cb(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if "Meridian 59" in text:
                try:
                    _, p = win32process.GetWindowThreadProcessId(hwnd)
                    if p == pid:
                        found[0] = hwnd
                        return False
                except:
                    pass
        return True
    
    try:
        win32gui.EnumWindows(cb, None)
    except:
        pass
    return found[0]

# --- Global Constants ---
import json
import os

GAME_EXE = "Meridian.exe"
try:
    with open("settings/config.json", "r") as f:
        c = json.load(f)
        GAME_EXE = c.get("process", {}).get("target_name", "Meridian.exe")
except:
    pass
GAME_TITLE_BASE = "Meridian 59"
LOGIN_MARKER = " --- "
UI_REFRESH_RATE = 1000 # ms
RECALCULATE_DELAY = 2.0 # seconds

# --- Shared Regex Patterns ---
# Standard Speech: [Char] says, "..."
RE_SPEECH = re.compile(r'^(.*?) (?:broadcasts?|tells?|says?|yells?|sends?), "(.*)"$', re.I)

# Banking
# Harmonized to support both Deposit and direct balance queries
RE_BANK_TOTAL = re.compile(r'(.*?) tells you, ".*?(?:You have|You now have) (\d+) shillings in your account\."', re.I)
RE_BANK_WITHDRAW = re.compile(r'(.*?) tells you, "Here are your (\d+) shillings\. Thank you for your business\."', re.I)

# --- Combat
RE_KILL = re.compile(r"^You killed (?:the )?(.*)\.$", re.I)
RE_HIT = re.compile(r"^(.*?) \w+ you with (?:his|her|its|their) .*\.$", re.I)
RE_MISS = re.compile(r"^You \w+ (.*?)'s attack\.$", re.I)

if __name__ == "__main__":
    # Quick sanity check for regexes
    test_line = "Skivlat tells you, \"You now have 5000 shillings in your account.\""
    m = RE_BANK_TOTAL.search(test_line)
    if m:
        print(f"Regex Test Success: Found {m.group(2)} shillings")
    else:
        print("Regex Test Failed")
