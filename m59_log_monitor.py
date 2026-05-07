import os
import time
import re
import logging

logger = logging.getLogger("m59.monitor")

class LogMonitor:
    def __init__(self, log_path):
        self.log_path = log_path
        # Pattern: [Timestamp] You have improved in the art of [Skill].
        self.pattern = re.compile(r'^\[.*?\] You have improved in the art of (.*?)\.$')
        print(f"DEBUG: Monitor Initialized for {self.log_path}")

    def process_line(self, line):
        clean_line = line.strip()
        
        # New logic: Just look for the phrase anywhere in the line 
        # as long as it starts with a timestamp [ ]
        if "You have improved in the art of" in clean_line:
            # Check if it's a system message (starts with timestamp)
            if clean_line.startswith("["):
                try:
                    # Split the line at "art of " and take the right side
                    parts = clean_line.split("art of ", 1)
                    if len(parts) > 1:
                        skill_part = parts[1]
                        # Remove the trailing period if it exists
                        if skill_part.endswith("."):
                            skill_part = skill_part[:-1]
                        
                        skill_name = skill_part.strip()
                        print(f"!!! MATCH FOUND: {skill_name} !!!")
                        return skill_name
                except Exception as e:
                    print(f"Error parsing line: {e}")
        return None

    def watch(self, callback):
        print("DEBUG: Monitor Thread is now WATCHING...")
        
        # Ensure file exists
        while not os.path.exists(self.log_path):
            time.sleep(0.5)

        with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
            # IMPORTANT: We start at 0 to read the whole file 
            # in case the 'Slash' is already there from a previous run.
            f.seek(0)
            
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                
                skill = self.process_line(line)
                if skill:
                    print(f"DEBUG: Monitor Found Skill: {skill}")
                    callback(skill)
