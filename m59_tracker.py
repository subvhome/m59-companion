import tkinter as tk
from tkinter import ttk
from datetime import datetime

class SkillTracker:
    def __init__(self, parent):
        self.frame = tk.LabelFrame(parent, text="Live Skill Tracking", bg="#C0C0C0", padx=5, pady=5)
        self.frame.pack(fill="both", expand=True, pady=5)
        
        # Internal data storage
        self.skills = {} # Format: {"Fencing": {"count": 0, "last_time": datetime}}

        # Setup Table (Treeview)
        self.tree = ttk.Treeview(self.frame, columns=("Count", "Last", "Delta"), height=6)
        self.tree.heading("#0", text="Skill/Event")
        self.tree.heading("Count", text="Gains")
        self.tree.heading("Last", text="Last Time")
        self.tree.heading("Delta", text="Time Since")
        
        # Column widths
        self.tree.column("#0", width=120)
        self.tree.column("Count", width=50, anchor="center")
        self.tree.column("Last", width=80, anchor="center")
        self.tree.column("Delta", width=80, anchor="center")
        
        self.tree.pack(fill="both", expand=True)

    def parse_skill_name(self, text):
        """Extracts the skill name from the chat string."""
        text = text.lower()
        try:
            if "art of " in text:
                return text.split("art of ")[1].split(".")[0].strip().title()
            if "improved in " in text:
                return text.split("improved in ")[1].split(".")[0].strip().title()
            return "General"
        except:
            return "General"

    def add_event(self, category, line):
        now = datetime.now()
        skill_name = self.parse_skill_name(line)
        
        if skill_name not in self.skills:
            self.skills[skill_name] = {"count": 0, "last_time": now}
            self.tree.insert("", "end", iid=skill_name, text=skill_name)

        # Calculate time since last gain
        stats = self.skills[skill_name]
        diff = now - stats["last_time"]
        delta_str = f"{int(diff.total_seconds() // 60)}m {int(diff.total_seconds() % 60)}s"
        
        # Update data
        stats["count"] += 1
        stats["last_time"] = now
        
        # Update UI Table
        self.tree.item(skill_name, values=(
            stats["count"], 
            now.strftime("%H:%M:%S"), 
            delta_str if stats["count"] > 1 else "First Gain"
        ))
