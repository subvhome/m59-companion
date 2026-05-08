import os
import time
import logging
import re

logger = logging.getLogger("m59.monitor")

class LogMonitor:
    def __init__(self, log_path):
        self.log_path = log_path
        self.improve_phrase = "You have improved in the art of "
        self.hp_phrase = "You suddenly feel a little tougher."
        self.running = True 
        print(f"DEBUG: Monitor Initialized for {self.log_path}")

    def stop(self):
        """Safely stops the monitor and closes file handles."""
        self.running = False

    def process_line(self, line):
        clean_line = line.strip()
        if not clean_line:
            return None

        # Regex to match: [Timestamp] You have improved in the art of {skill}
        # Use greedy match (.*) to get everything until the end, then strip the period
        improve_pattern = r"^\[.*?\] " + re.escape(self.improve_phrase) + r"(.*)$"
        improve_match = re.search(improve_pattern, clean_line, re.IGNORECASE)
        
        if improve_match:
            skill_raw = improve_match.group(1).strip()
            if not skill_raw:
                return None
                
            # Strip trailing period if present
            if skill_raw.endswith("."):
                skill_raw = skill_raw[:-1].strip()
            
            print(f"DEBUG: MATCH! Found skill raw: '{skill_raw}'")
            
            # Format skill name: Hunter's Aim, Hand-To-Hand, Fireball
            words = skill_raw.split(' ')
            formatted_words = []
            for word in words:
                sub_words = word.split('-')
                formatted_sub = "-".join([sw.capitalize() for sw in sub_words])
                formatted_words.append(formatted_sub)
            
            found_skill = " ".join(formatted_words)
            found_skill = found_skill.replace("'S", "'s")
            
            return found_skill

        # Check for Hit Points
        hp_pattern = r"^\[.*?\] " + re.escape(self.hp_phrase)
        if re.search(hp_pattern, clean_line, re.IGNORECASE):
            return "Hit Points"

        return None

    def watch(self, callback):
        abs_path = os.path.abspath(self.log_path)
        print(f"DEBUG: Monitor Thread started. Watching: {abs_path}")
        
        # Wait for file to exist
        while not os.path.exists(self.log_path) and self.running:
            time.sleep(0.5)

        # Initial state: Get current size to only see NEW data
        last_size = os.path.getsize(self.log_path)
        print(f"DEBUG: Initial file size: {last_size} bytes. Waiting for new data...")

        try:
            while self.running:
                if not os.path.exists(self.log_path):
                    time.sleep(1)
                    continue
                    
                curr_size = os.path.getsize(self.log_path)
                
                if curr_size > last_size:
                    print(f"DEBUG: File grew from {last_size} to {curr_size} ({curr_size - last_size} new bytes)")
                    
                    with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(last_size)
                        new_content = f.read()
                        
                        if new_content:
                            lines = new_content.splitlines()
                            for line in lines:
                                if not line.strip(): continue
                                print(f"DEBUG: NEW_LINE_DETECTED: '{line.strip()}'")
                                skill = self.process_line(line)
                                if skill:
                                    print(f"DEBUG: TRIGGERING UI for: {skill}")
                                    callback(skill)
                        else:
                            print("DEBUG: File grew but read returned nothing (buffering?).")
                    
                    # Update pointer
                    last_size = curr_size
                elif curr_size < last_size:
                    print(f"DEBUG: File size decreased ({last_size} -> {curr_size}), resetting pointer.")
                    last_size = curr_size
                
                time.sleep(0.5)
        except Exception as e:
            print(f"Monitor Loop Error: {e}")
        finally:
            print("DEBUG: Monitor Thread Stopped.")
