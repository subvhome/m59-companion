import os
import time
import re
import logging

logger = logging.getLogger("m59.monitor")

class LogMonitor:
    def __init__(self, log_path):
        self.log_path = log_path
        # Pattern looks for: [Timestamp] You have improved in the art of [Skill].
        # It ensures the line STARTS with the timestamp and doesn't have 
        # extra text before the "You have improved" (to ignore player chat).
        self.pattern = re.compile(r'^\[.*?\] You have improved in the art of (.*?)\.$')

    def process_line(self, line):
        """Extracts the skill name if the line is a valid system improve message."""
        match = self.pattern.match(line.strip())
        if match:
            skill_name = match.group(1)
            # This will catch "dodge", "Anti-Magic Aura", "Shal'ille Bane", etc.
            return skill_name
        return None

    def watch(self, callback):
        """Actively tails the log file and sends found skills to a callback function."""
        # Wait a moment for the file to be ready
        timeout = 5
        while not os.path.exists(self.log_path) and timeout > 0:
            time.sleep(0.5)
            timeout -= 0.5

        if not os.path.exists(self.log_path):
            logger.error(f"Monitor could not find log file: {self.log_path}")
            return

        with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
            # Start at the beginning to catch anything that happened in the first second
            f.seek(0)
            
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1) # Wait for the next line to be written
                    continue
                
                skill = self.process_line(line)
                if skill:
                    # We found one! Send it to the UI
                    callback(skill)
