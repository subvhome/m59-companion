import time
from datetime import datetime

class SessionTracker:
    def __init__(self):
        # Format: {"Skill Name": {"count": 0, "last_time": timestamp}}
        self.stats = {}
        self.improve_phrase = "You have improved in the art of "
        self.hp_phrase = "You suddenly feel a little tougher."

    def process_line(self, line):
        """
        Analyzes a single line for gains. 
        Only matches lines that START with the specific system phrases.
        """
        # 1. Check for Skill Improve
        if line.startswith(self.improve_phrase):
            # Extract name: Remove phrase from start and period from end
            skill_raw = line[len(self.improve_phrase):].rstrip('.')
            skill_name = skill_raw.strip().title()
            return self._update_stat(skill_name)

        # 2. Check for HP Gain
        if line.strip() == self.hp_phrase:
            return self._update_stat("Hit Points")

        return None

    def _update_stat(self, name):
        now = time.time()
        
        if name not in self.stats:
            self.stats[name] = {
                "count": 0,
                "last_time": now
            }
        
        entry = self.stats[name]
        entry["count"] += 1
        
        # Calculate Delta
        delta_seconds = now - entry["last_time"]
        entry["last_time"] = now
        
        # Format Delta string (e.g., "1m 30s")
        if entry["count"] == 1:
            delta_str = "---" # First gain of the session
        else:
            m, s = divmod(int(delta_seconds), 60)
            delta_str = f"{m}m {s}s"
            
        return {
            "name": name,
            "count": entry["count"],
            "delta": delta_str,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }

def test_tracker():
    tracker = SessionTracker()
    print("--- M59 Session Tracker Test ---")
    
    test_lines = [
        "You suddenly feel a little tougher.",
        "You say, \"You suddenly feel a little tougher.\"", # Should be ignored
        "You have improved in the art of axe wielding.",
        "A mutant ant nips you with its attack.", # Should be ignored
        "You have improved in the art of axe wielding.", # Test Delta
    ]
    
    for i, line in enumerate(test_lines):
        print(f"Input: {line}")
        # Add a small sleep to simulate real-time for delta test
        if i == 4: time.sleep(2) 
        
        result = tracker.process_line(line)
        if result:
            print(f" >> [GAIN] {result['name']} | Total: {result['count']} | Delta: {result['delta']} | at {result['timestamp']}")
        else:
            print(" >> [SKIP] No gain detected.")
        print("-" * 30)

if __name__ == "__main__":
    test_tracker()
