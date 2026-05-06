import tkinter as tk
from tkinter import ttk
from datetime import datetime
import logging

logger = logging.getLogger("m59.tracker")

class SkillTracker:
    def __init__(self, parent):
        self.frame = tk.LabelFrame(parent, text="Live Skill Tracking", bg="#C0C0C0", padx=5, pady=5)
        self.frame.pack(fill="both", expand=True, pady=5)
        
        self.skills = {} 
        self.tree = ttk.Treeview(self.frame, columns=("Count", "Last", "Delta"), height=6)
        self.tree.heading("#0", text="Skill/Event")
        self.tree.heading("Count", text="Gains")
        self.tree.heading("Last", text="Last Time")
        self.tree.heading("Delta", text="Time Since")
        
        self.tree.column("#0", width=120)
        self.tree.column("Count", width=50, anchor="center")
        self.tree.column("Last", width=80, anchor="center")
        self.tree.column("Delta", width=80, anchor="center")
        self.tree.pack(fill="both", expand=True)

    def clear_session(self):
        """Wipes the UI for a fresh session reset."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.skills = {}
        logger.info("Tracker UI cleared for new session.")

    def parse_skill_name(self, text, testing_mode=False):
        """Fixed parser to prevent 'S' bug and improve detection."""
        t_original = text.strip()
        t_lower = t_original.lower()
        
        # KEYWORDS - lowercase for reliable comparison
        tougher_phrase = "you suddenly feel a little tougher"
        improved_phrase = "you have improved in the art of"

        if testing_mode:
            # RELAXED: Check if the line CONTAINS the phrase (for tells/broadcasts)
            if tougher_phrase in t_lower:
                return "Hit Points"
            
            if improved_phrase in t_lower:
                try:
                    # Split at the phrase and take everything after it
                    parts = t_lower.split(improved_phrase)
                    # Clean up quotes, periods, and extra spaces
                    skill_raw = parts[1].replace('"', '').replace("'", "").split('.')[0].strip()
                    return skill_raw.title()
                except Exception as e:
                    logger.error(f"Test Mode split error: {e}")
                    return None
        else:
            # PRODUCTION: Must match the system string EXACTLY (no names or tells before it)
            # System messages usually end with a period.
            if t_original == "You suddenly feel a little tougher.":
                return "Hit Points"
            
            if t_original.startswith("You have improved in the art of "):
                try:
                    # Extract skill name between 'art of ' and the trailing '.'
                    skill_name = t_original.split("the art of ")[1].split(".")[0].strip()
                    return skill_name.title()
                except Exception as e:
                    logger.error(f"Production split error: {e}")
                    return None
                    
        return None

    def add_event(self, line, testing_mode=False):
        """Records a valid gain and updates the UI scoreboard."""
        skill_name = self.parse_skill_name(line, testing_mode)
        if not skill_name:
            return

        now = datetime.now()
        if skill_name not in self.skills:
            self.skills[skill_name] = {"count": 0, "last_time": now}
            self.tree.insert("", "end", iid=skill_name, text=skill_name)
        
        stats = self.skills[skill_name]
        diff = now - stats["last_time"]
        delta_str = f"{int(diff.total_seconds() // 60)}m {int(diff.total_seconds() % 60)}s"
        
        stats["count"] += 1
        stats["last_time"] = now
        
        self.tree.item(skill_name, values=(
            stats["count"], 
            now.strftime("%H:%M:%S"), 
            delta_str if stats["count"] > 1 else "First Gain"
        ))
