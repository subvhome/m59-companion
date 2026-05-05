import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import queue
import logging
import time
import win32gui
import win32con
import json
import os
from datetime import datetime
# Import modular helper files
from m59_bridge import find_game_window, get_stats, find_skill_listbox, mem, get_text_from_hwnd
from m59_identity import capture_character_name
from m59_tracker import SkillTracker
from m59_lists import get_raw_skill_dict
from m59_calculator import SchoolCalculator
# Global Log Setup
logger = logging.getLogger("m59")
class QueueHandler(logging.Handler):
    """Custom logging handler to send logs to a Tkinter text widget via a queue."""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record))
class ConfigManager:
    def __init__(self, filepath="config.json"):
        self.filepath = os.path.join(os.getcwd(), filepath)
        self.defaults = {
            "server": {"points_slope": 7.0, "max_points": 16.0, "min_needed_floor": 225},
            "character": {"intellect": 25, "chat_log_enabled": False}
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
        self.log_queue = queue.Queue()
        
        # Buffer for the Difference Engine
        self.last_buffer = [] 
        self.log_file = "chat_history.txt"
        
        self.setup_logging_infrastructure()
        self.setup_menu()
        self.setup_ui()
        
        self.tracker = SkillTracker(root)
        self.update_loop() 
        logger.info("Application started and ready.")
    def setup_logging_infrastructure(self):
        """Initializes the logging system with a queue for UI updates."""
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%H:%M:%S')
        
        handler = QueueHandler(self.log_queue)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    def setup_menu(self):
        """Replaces buttons with a top-level menu bar."""
        menubar = tk.Menu(self.root)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Sync Now", command=self.sync_all_data)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="System", menu=file_menu)
        
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="App Settings", command=self.open_settings)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        
        self.debug_var = tk.BooleanVar(value=False)
        log_menu = tk.Menu(menubar, tearoff=0)
        log_menu.add_checkbutton(label="Enable Debug Logs", variable=self.debug_var, command=self.toggle_debug)
        log_menu.add_command(label="Clear Log Window", command=self.clear_logs)
        menubar.add_cascade(label="Logging", menu=log_menu)
        
        self.root.config(menu=menubar)
    def toggle_debug(self):
        if self.debug_var.get():
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
    def setup_ui(self):
        """Builds the main interface components."""
        self.name_label = tk.Label(self.root, text="Character Name", font=("Arial", 10, "bold"))
        self.name_label.pack(pady=5)
        
        self.status_label = tk.Label(self.root, text="System Ready", font=("Arial", 9, "italic"), fg="#555")
        self.status_label.pack(pady=2)
        
        self.stats_label = tk.Label(self.root, text="HP: -- | MP: -- | VG: --", font=("Arial", 10))
        self.stats_label.pack(pady=5)
        
        self.unlock_frame = tk.LabelFrame(self.root, text="School Progression", bg="#C0C0C0")
        self.unlock_frame.pack(fill="both", expand=False, pady=5)
        self.unlock_label = tk.Label(self.unlock_frame, text="Waiting for data...", 
                                     font=("Courier", 9), justify="left", bg="#C0C0C0")
        self.unlock_label.pack(padx=5, pady=5)
        self.list_frame = tk.LabelFrame(self.root, text="Character Knowledge", bg="#C0C0C0")
        self.list_frame.pack(fill="both", expand=True, pady=5)
        self.list_display = tk.Text(self.list_frame, height=8, font=("Arial", 8), state="disabled")
        self.list_display.pack(fill="both", expand=True)
        log_frame = tk.LabelFrame(self.root, text="System Logs", bg="#F0F0F0")
        log_frame.pack(fill="both", expand=True, pady=5)
        self.log_display = scrolledtext.ScrolledText(log_frame, height=5, font=("Consolas", 8), state="disabled")
        self.log_display.pack(fill="both", expand=True)
    def clear_logs(self):
        self.log_display.config(state="normal")
        self.log_display.delete("1.0", tk.END)
        self.log_display.config(state="disabled")
    def open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.geometry("250x200")
        settings_win.attributes("-topmost", True)
        
        tk.Label(settings_win, text="Intellect:").pack(pady=5)
        int_ent = tk.Entry(settings_win)
        int_ent.insert(0, str(self.config.settings["character"]["intellect"]))
        int_ent.pack()
        log_var = tk.BooleanVar(value=self.config.settings["character"].get("chat_log_enabled", False))
        tk.Checkbutton(settings_win, text="Enable Full Chat Logging", variable=log_var).pack(pady=10)
        def save():
            try:
                self.config.settings["character"]["intellect"] = int(int_ent.get())
                self.config.settings["character"]["chat_log_enabled"] = log_var.get()
                self.config.save(self.config.settings)
                logger.info("Settings updated.")
                settings_win.destroy()
            except ValueError:
                messagebox.showerror("Error", "Intellect must be a number.")
        
        tk.Button(settings_win, text="Save", command=save).pack(pady=10)
    def sync_all_data(self):
        if self.is_syncing: return
        self.is_syncing = True
        logger.info("Manual Sync Triggered.")
        
        try:
            if not mem.attach():
                self.update_status("Error: Memory attachment failed.")
                return
            
            hwnd = find_game_window()
            if not hwnd: return
            if not self.char_name:
                name = capture_character_name(hwnd)
                if name:
                    self.char_name = name
                    self.name_label.config(text=f"Identity: {name}")
            
            tab_handles = []
            win32gui.EnumChildWindows(hwnd, lambda h, l: 
                tab_handles.append(h) if win32gui.GetDlgCtrlID(h) == 1029 else None, None)
            
            if len(tab_handles) >= 3:
                # Spells Sync
                win32gui.SendMessage(tab_handles[1], win32con.BM_CLICK, 0, 0)
                time.sleep(1)
                lb_id = find_skill_listbox(hwnd)
                if lb_id: self.knowledge_cache.update(get_raw_skill_dict(lb_id, 3))
                
                # Skills Sync
                win32gui.SendMessage(tab_handles[2], win32con.BM_CLICK, 0, 0)
                time.sleep(1)
                lb_id = find_skill_listbox(hwnd)
                if lb_id: self.knowledge_cache.update(get_raw_skill_dict(lb_id, 5))
                
                self.refresh_ui_display()
                logger.info("Knowledge Sync Complete.")
        except Exception as e:
            logger.error(f"Sync error: {e}")
        finally:
            self.is_syncing = False
    def refresh_ui_display(self):
        self.list_display.config(state="normal")
        self.list_display.delete("1.0", tk.END)
        for n in sorted(self.knowledge_cache.keys()):
            self.list_display.insert(tk.END, f"{n.title()}: {self.knowledge_cache[n]}%\n")
        self.list_display.config(state="disabled")
        
        res = self.calc.calculate_all_unlocks(self.knowledge_cache)
        self.unlock_label.config(text="\n".join(res) if res else "No unlocks available.")
    def update_loop(self):
        """Main background logic for stats, logging, and tracking."""
        # 1. Update UI Logs
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_display.config(state="normal")
            self.log_display.insert(tk.END, msg + "\n")
            self.log_display.see(tk.END)
            self.log_display.config(state="disabled")
        hwnd = find_game_window()
        if hwnd and not self.is_syncing:
            if not mem.process_handle: mem.attach()
            
            # 2. Stats Polling
            if mem.process_handle:
                s = get_stats(hwnd)
                if s: self.stats_label.config(text=f"HP: {s[0]} | MP: {s[1]} | VG: {s[2]}")
            
            # 3. Difference Engine for Chat (RICHEDIT ID 1005)
            chat_hwnd = win32gui.GetDlgItem(hwnd, 1005)
            if chat_hwnd:
                current_text = get_text_from_hwnd(chat_hwnd)
                if current_text:
                    current_lines = [l.strip() for l in current_text.splitlines() if l.strip()]
                    
                    new_lines = []
                    if not self.last_buffer:
                        new_lines = current_lines
                    else:
                        try:
                            last_msg = self.last_buffer[-1]
                            if last_msg in current_lines:
                                # Find the last occurrence to handle duplicate lines in chat
                                last_idx = len(current_lines) - 1 - current_lines[::-1].index(last_msg)
                                new_lines = current_lines[last_idx + 1:]
                            else:
                                new_lines = current_lines # Buffer cleared or msg scrolled off
                        except (ValueError, IndexError):
                            new_lines = current_lines
                    if new_lines:
                        self.last_buffer = current_lines
                        with open(self.log_file, "a") as f:
                            ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                            for line in new_lines:
                                is_gain = self.tracker.parse_skill_name(line) is not None
                                log_on = self.config.settings["character"].get("chat_log_enabled", False)
                                
                                # Write to file if full log is on OR it's a gain
                                if log_on or is_gain:
                                    f.write(f"{ts} {line}\n")
                                
                                # Process through tracker UI
                                self.tracker.add_event(line)
        
        self.root.after(1000, self.update_loop)
if __name__ == "__main__":
    root = tk.Tk()
    app = CompanionApp(root)
    root.mainloop()
