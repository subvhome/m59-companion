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
        logger.info("SkillTracker UI initialized.")
    def parse_skill_name(self, text):
        """Extracts the skill/spell name or health gain from the chat string."""
        text = text.lower().strip()
        try:
            if "you have improved in the art of" in text:
                return text.split("the art of")[1].split(".")[0].strip().title()
            if "you suddenly feel a little tougher" in text:
                return "Hit Points"
            return None 
        except Exception:
            return None
    def add_event(self, line):
        """Processes a new, unique chat line passed from the file-logger."""
        skill_name = self.parse_skill_name(line)
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
        logger.info(f"Tracker: {skill_name} recorded.")
