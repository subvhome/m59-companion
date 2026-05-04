import tkinter as tk
from tkinter import ttk, scrolledtext
import queue
import logging
import time
import win32gui
import win32con
import json
import os

# Import modular helper files
from m59_bridge import find_game_window, get_stats, get_text_from_hwnd, find_skill_listbox
from m59_identity import capture_character_name
from m59_tracker import SkillTracker
from m59_lists import get_raw_skill_dict
from m59_calculator import SchoolCalculator

class ConfigManager:
    def __init__(self, filepath="config.json"):
        self.filepath = os.path.join(os.getcwd(), filepath)
        self.defaults = {
            "server": {"points_slope": 7.0, "max_points": 16.0, "min_needed_floor": 225},
            "character": {"intellect": 25}
        }
        self.settings = self.defaults.copy()
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    self.settings = json.load(f)
            except Exception:
                self.settings = self.defaults.copy()

    def save(self, new_settings):
        self.settings = new_settings
        try:
            with open(self.filepath, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception:
            pass

class CompanionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("M59 Modular Companion")
        self.root.attributes("-topmost", True)
        
        self.config = ConfigManager()
        self.calc = SchoolCalculator(self.config)
        
        self.is_syncing = False 
        self.char_name = None
        self.knowledge_cache = {} 
        self.auto_refresh_var = tk.BooleanVar(value=False)
        
        self.log_queue = queue.Queue()
        self.setup_logging()
        
        # UI Elements
        self.name_label = tk.Label(root, text="Name: Scanning...", font=("Arial", 10, "bold"))
        self.name_label.pack(pady=5)
        self.stats_label = tk.Label(root, text="HP: -- | MP: -- | VG: --", font=("Arial", 10))
        self.stats_label.pack(pady=5)

        self.unlock_frame = tk.LabelFrame(root, text="School Progression", bg="#C0C0C0")
        self.unlock_frame.pack(fill="both", expand=False, pady=5)
        self.unlock_label = tk.Label(self.unlock_frame, text="Waiting for data...", 
                                     font=("Courier", 9), justify="left", bg="#C0C0C0")
        self.unlock_label.pack(padx=5, pady=5)

        self.control_frame = tk.Frame(root)
        self.control_frame.pack(fill="x", padx=5)
        tk.Button(self.control_frame, text="Refresh", command=self.refresh_lists).pack(side="left", padx=5)
        tk.Button(self.control_frame, text="Full Sync", command=self.sync_all_data).pack(side="left", padx=5)
        tk.Button(self.control_frame, text="Settings", command=self.open_settings).pack(side="right", padx=5)

        self.list_frame = tk.LabelFrame(root, text="Character Knowledge", bg="#C0C0C0")
        self.list_frame.pack(fill="both", expand=True, pady=5)
        self.list_display = tk.Text(self.list_frame, height=8, font=("Arial", 8), state="disabled")
        self.list_display.pack(fill="both", expand=True)
        
        self.tracker = SkillTracker(root)
        self.update_loop() 

    def open_settings(self):
        # Simplified settings window that just updates the config
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Settings")
        tk.Label(settings_win, text="Intellect:").pack()
        int_ent = tk.Entry(settings_win)
        int_ent.insert(0, str(self.config.settings["character"]["intellect"]))
        int_ent.pack()

        def save():
            self.config.settings["character"]["intellect"] = int(int_ent.get())
            self.config.save(self.config.settings)
            settings_win.destroy()
        tk.Button(settings_win, text="Save", command=save).pack()

    def sync_all_data(self):
        print(">>> [ACTION] Full Sync button pressed.")
        if self.is_syncing: return
        self.is_syncing = True
        
        try:
            hwnd = find_game_window()
            if not hwnd: return

            # 1. Identity Capture
            name = capture_character_name(hwnd)
            if name:
                self.char_name = name
                self.name_label.config(text=f"Identity: {name}")

            # 2. Tab Switching
            tab_handles = []
            win32gui.EnumChildWindows(hwnd, lambda h, l: 
                tab_handles.append(h) if win32gui.GetDlgCtrlID(h) == 1029 else None, None)

            if len(tab_handles) >= 3:
                # Click Spells Tab
                print(">>> [STEP 3] Clicking Spells Tab...")
                win32gui.SendMessage(tab_handles[1], win32con.BM_CLICK, 0, 0)
                time.sleep(1.5)  # Increased delay for Wine UI rendering
                self.refresh_lists()

                # Click Skills Tab
                print(">>> [STEP 4] Clicking Skills Tab...")
                win32gui.SendMessage(tab_handles[2], win32con.BM_CLICK, 0, 0)
                time.sleep(1.5)  # Increased delay for Wine UI rendering
                self.refresh_lists()
        finally:
            self.is_syncing = False

    def refresh_lists(self):
        hwnd = find_game_window()
        lb_id = find_skill_listbox(hwnd)
        if lb_id:
            raw_data = get_raw_skill_dict(lb_id)
            self.knowledge_cache.update(raw_data)
            
            self.list_display.config(state="normal")
            self.list_display.delete("1.0", tk.END)
            for n in sorted(self.knowledge_cache.keys()):
                self.list_display.insert(tk.END, f"{n.title()}: {self.knowledge_cache[n]}%\n")
            self.list_display.config(state="disabled")

            res = self.calc.calculate_all_unlocks(self.knowledge_cache)
            self.unlock_label.config(text="\n".join(res) if res else "No unlocks available.")

    def setup_logging(self):
        logging.basicConfig(level=logging.INFO)

    def update_loop(self):
        hwnd = find_game_window()
        if hwnd and not self.is_syncing:
            s = get_stats(hwnd)
            if s: self.stats_label.config(text=f"HP: {s[0]} | MP: {s[1]} | VG: {s[2]}")
        self.root.after(1000, self.update_loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = CompanionApp(root)
    root.mainloop()
