import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import queue
import logging
import time
import win32gui
import win32con
import os
from datetime import datetime

# Import modular helper files
from m59_bridge import find_game_window, get_stats, find_skill_listbox, mem, get_text_from_hwnd
from m59_identity import capture_character_name
from m59_tracker import SkillTracker
from m59_lists import get_raw_skill_dict
from m59_calculator import SchoolCalculator
from config_manager import ConfigManager # Matches your filename

# Global Log Setup
logger = logging.getLogger("m59")

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record))

class CompanionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("M59 Companion")
        self.root.attributes("-topmost", True)
        
        # Initialize Managers
        self.config = ConfigManager()
        self.calc = SchoolCalculator(self.config)
        
        # State Variables
        self.is_syncing = False 
        self.char_name = None 
        self.knowledge_cache = {} 
        self.log_queue = queue.Queue()
        self.last_line_count = 0
        self.current_log_path = None
        
        # Ensure logs directory exists
        if not os.path.exists("logs"):
            os.makedirs("logs")
        
        self.setup_logging_infrastructure()
        self.setup_menu()
        self.setup_ui_main() 
        self.tracker = SkillTracker(root) 
        self.setup_ui_logs() 
        
        self.update_loop() 
        logger.info("Application started with Session Logic and Line Counter.")

    def setup_logging_infrastructure(self):
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
        handler = QueueHandler(self.log_queue)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def start_new_log_session(self):
        """Creates a fresh timestamped file in the /logs folder."""
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.current_log_path = os.path.join("logs", f"session_{ts}.txt")
        with open(self.current_log_path, "w") as f:
            f.write(f"--- Meridian 59 Session Started: {datetime.now()} ---\n")
        logger.info(f"Started new session log: {self.current_log_path}")

    def update_loop(self):
        # 1. Update UI Logs from Queue
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_display.config(state="normal")
            self.log_display.insert(tk.END, msg + "\n")
            self.log_display.see(tk.END)
            self.log_display.config(state="disabled")

        hwnd = find_game_window()
        if hwnd and not self.is_syncing:
            if not mem.process_handle: mem.attach()
            
            # 2. Stats Polling (HP/MP/VG)
            if mem.process_handle:
                s = get_stats(hwnd)
                if s: self.stats_label.config(text=f"HP: {s[0]} | MP: {s[1]} | VG: {s[2]}")
            
            # 3. Line Counter Difference Engine
            chat_hwnd = win32gui.GetDlgItem(hwnd, 1005)
            if chat_hwnd:
                current_text = get_text_from_hwnd(chat_hwnd)
                if current_text:
                    lines = [l.strip() for l in current_text.splitlines() if l.strip()]
                    
                    # Detect if buffer cleared or game restarted
                    if len(lines) < self.last_line_count:
                        self.last_line_count = 0
                    
                    # Slice only the brand new lines
                    new_lines = lines[self.last_line_count:]
                    self.last_line_count = len(lines)

                    if new_lines:
                        is_test = self.config.settings["character"].get("testing_mode", False)
                        
                        for line in new_lines:
                            # Check for Session Reset (Welcome Message)
                            if "welcome to the world of meridian 59" in line.lower():
                                self.tracker.clear_session()
                                self.start_new_log_session()
                            
                            # Check for Imps/Toughers
                            is_gain = self.tracker.parse_skill_name(line, is_test)
                            if is_gain:
                                self.tracker.add_event(line, is_test)
                                # Log specifically to the session file
                                if self.current_log_path:
                                    with open(self.current_log_path, "a") as f:
                                        ts = datetime.now().strftime("[%H:%M:%S]")
                                        f.write(f"{ts} {line}\n")
        
        self.root.after(1000, self.update_loop)

    def setup_ui_main(self):
        """Builds the main character info and progression display."""
        self.name_label = tk.Label(self.root, text="Character Name", font=("Arial", 10, "bold"))
        self.name_label.pack(pady=5)
        self.status_label = tk.Label(self.root, text="System Ready", font=("Arial", 9, "italic"), fg="#555")
        self.status_label.pack(pady=2)
        self.stats_label = tk.Label(self.root, text="HP: -- | MP: -- | VG: --", font=("Arial", 10))
        self.stats_label.pack(pady=5)
        
        self.unlock_frame = tk.LabelFrame(self.root, text="School Progression", bg="#C0C0C0")
        self.unlock_frame.pack(fill="x", pady=5, padx=5)
        self.unlock_label = tk.Label(self.unlock_frame, text="Waiting for data...", font=("Courier", 9), bg="#C0C0C0")
        self.unlock_label.pack(padx=5, pady=5)
        
        self.list_frame = tk.LabelFrame(self.root, text="Character Knowledge", bg="#C0C0C0")
        self.list_frame.pack(fill="both", expand=True, pady=5, padx=5)
        self.list_display = tk.Text(self.list_frame, height=6, font=("Arial", 8), state="disabled")
        self.list_display.pack(fill="both", expand=True)

    def setup_ui_logs(self):
        """Builds the collapsible system log window."""
        self.log_container = tk.Frame(self.root)
        self.log_container.pack(fill="x", side="bottom")
        self.toggle_btn = tk.Button(self.log_container, text="▲ Show System Logs", command=self.toggle_logs)
        self.toggle_btn.pack(fill="x")
        self.log_frame = tk.LabelFrame(self.log_container, text="System Logs", bg="#F0F0F0")
        self.log_display = scrolledtext.ScrolledText(self.log_frame, height=5, font=("Consolas", 8), state="disabled")
        self.log_display.pack(fill="both", expand=True)
        self.logs_visible = False

    def toggle_logs(self):
        if self.logs_visible:
            self.log_frame.pack_forget()
            self.toggle_btn.config(text="▲ Show System Logs")
            self.logs_visible = False
        else:
            self.log_frame.pack(fill="both", expand=True, padx=5, pady=5)
            self.toggle_btn.config(text="▼ Hide System Logs")
            self.logs_visible = True

    def setup_menu(self):
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
        logger.setLevel(logging.DEBUG if self.debug_var.get() else logging.INFO)

    def clear_logs(self):
        self.log_display.config(state="normal")
        self.log_display.delete("1.0", tk.END)
        self.log_display.config(state="disabled")

    def open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.geometry("250x220")
        settings_win.attributes("-topmost", True)
        
        tk.Label(settings_win, text="Intellect:").pack(pady=5)
        int_ent = tk.Entry(settings_win)
        int_ent.insert(0, str(self.config.settings["character"]["intellect"]))
        int_ent.pack()
        
        test_var = tk.BooleanVar(value=self.config.settings["character"].get("testing_mode", True))
        tk.Checkbutton(settings_win, text="Enable Testing Mode (Relaxed Filter)", variable=test_var).pack(pady=5)

        def save():
            try:
                self.config.settings["character"]["intellect"] = int(int_ent.get())
                self.config.settings["character"]["testing_mode"] = test_var.get()
                self.config.save(self.config.settings)
                logger.info("Settings updated. Log in again or restart to see filter changes.")
                settings_win.destroy()
            except ValueError:
                messagebox.showerror("Error", "Intellect must be a number.")
        tk.Button(settings_win, text="Save", command=save).pack(pady=10)

    def sync_all_data(self):
        if self.is_syncing: return
        self.is_syncing = True
        logger.info("Manual Sync Started: Tab Cycling Sequence.")
        
        try:
            if not mem.attach(): 
                self.is_syncing = False
                return
            
            hwnd = find_game_window()
            if not hwnd: 
                self.is_syncing = False
                return

            # --- PHASE 1: TAB CYCLING (THE HANDSHAKE) ---
            tab_handles = []
            win32gui.EnumChildWindows(hwnd, lambda h, l: tab_handles.append(h) if win32gui.GetDlgCtrlID(h) == 1029 else None, None)
            
            if len(tab_handles) >= 3:
                logger.info("Cycling tabs to force engine redraw...")
                # Sequence: Spells -> Skills -> Spells
                win32gui.SendMessage(tab_handles[1], win32con.BM_CLICK, 0, 0)
                time.sleep(0.3)
                win32gui.SendMessage(tab_handles[2], win32con.BM_CLICK, 0, 0)
                time.sleep(0.3)
                win32gui.SendMessage(tab_handles[1], win32con.BM_CLICK, 0, 0)
                
                # --- PHASE 2: READ SPELLS ---
                # Wait for Spells list to populate after the cycle
                target_lb = None
                start_wait = time.time()
                while time.time() - start_wait < 2.0:
                    lb_id = find_skill_listbox(hwnd)
                    if lb_id:
                        count = win32gui.SendMessage(lb_id, win32con.LB_GETCOUNT, 0, 0)
                        if count > 0:
                            target_lb = lb_id
                            break
                    time.sleep(0.1)
                
                if target_lb:
                    data = get_raw_skill_dict(target_lb, 3) # 3 = Spells
                    self.knowledge_cache.update(data)
                    logger.info(f"Sync: Read {len(data)} Spells.")
                
                # --- PHASE 3: READ SKILLS ---
                win32gui.SendMessage(tab_handles[2], win32con.BM_CLICK, 0, 0)
                time.sleep(0.5) # Give it a moment to switch back
                lb_id = find_skill_listbox(hwnd)
                if lb_id:
                    data = get_raw_skill_dict(lb_id, 5) # 5 = Skills
                    self.knowledge_cache.update(data)
                    logger.info(f"Sync: Read {len(data)} Skills.")

            # --- PHASE 4: IDENTITY CAPTURE (FINAL) ---
            if not self.char_name:
                name = capture_character_name(hwnd)
                bio_hwnd = win32gui.FindWindowEx(hwnd, 0, "#32770", "Player Description")
                if name:
                    self.char_name = name
                    self.name_label.config(text=f"Identity: {name}")
                if bio_hwnd:
                    win32gui.PostMessage(bio_hwnd, win32con.WM_CLOSE, 0, 0)

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

if __name__ == "__main__":
    root = tk.Tk()
    app = CompanionApp(root)
    root.mainloop()
