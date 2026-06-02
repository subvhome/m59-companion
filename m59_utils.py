import os
import sys
import re
import win32gui
import win32process
import win32con
import logging

logger = logging.getLogger("dashboard")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Global Constants ---
GAME_EXE = "Meridian.exe"
GAME_TITLE_BASE = "Meridian 59"
LOGIN_MARKER = " --- "
UI_REFRESH_RATE = 1000 # ms
RECALCULATE_DELAY = 2.0 # seconds

# --- Shared Regex Patterns ---
# Standard Speech: [Char] says, "..."
RE_SPEECH = re.compile(r'^(.*?) (?:broadcasts?|tells?|says?|yells?|sends?), "(.*)"$', re.I)

# Banking
RE_BANK_TOTAL = re.compile(r'(.*?) tells you, "(?:Thank you for your deposit\.\s+)?You (?:now )?have (\d+) shillings in your account\."', re.I)
RE_BANK_WITHDRAW = re.compile(r'(.*?) tells you, "Here are your (\d+) shillings\. Thank you for your business\."', re.I)

# --- Combat
RE_KILL = re.compile(r"^You killed (?:the )?(.*)\.$", re.I)
RE_HIT = re.compile(r"^(.*?) \w+ you with (?:his|her|its|their) .*\.$", re.I)
RE_MISS = re.compile(r"^You \w+ (.*?)'s attack\.$", re.I)

