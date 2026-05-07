import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import queue
import logging
import time
import win32gui
import win32con
import os
from datetime import datetime
from m59_log_monitor import LogMonitor
import threading

# Import modular helper files
from m59_bridge import find_game_window, get_stats, find_skill_listbox, mem, get_text_from_hwnd
from m59_identity import capture_character_name
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
        self.current_log_path = None # Will hold our .log file path
        self.session_improves = {} # New storage for the grid data
        
        # Ensure logs directory exists
        if not os.path.exists("logs"):
            os.makedirs("logs")
        
        self.setup_logging_infrastructure()
        self.setup_menu()
        self.setup_ui_main() 
        self.setup_ui_logs() 
        
        # Start the first session immediately
        self.start_new_log_session()
        
        self.update_loop() 
        logger.info("Application started. Chat Logger is Active.")
        
    def setup_logging_infrastructure(self):
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
        handler = QueueHandler(self.log_queue)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def update_loop(self):
        # 1. Internal System Log UI Update
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_display.config(state="normal")
            self.log_display.insert(tk.END, msg + "\n")
            self.log_display.see(tk.END)
            self.log_display.config(state="disabled")

        hwnd = find_game_window()
        if hwnd and not self.is_syncing:
            if not mem.process_handle: mem.attach()
            
            # 2. Update Core Stats (Untouched)
            if mem.process_handle:
                s = get_stats(hwnd)
                if s: self.stats_label.config(text=f"HP: {s[0]} | MP: {s[1]} | VG: {s[2]}")
            
            # 3. Enhanced Chat Logger Logic
            chat_hwnd = win32gui.GetDlgItem(hwnd, 1005)
            if chat_hwnd:
                current_text = get_text_from_hwnd(chat_hwnd)
                if current_text:
                    all_lines = [l.strip() for l in current_text.splitlines() if l.strip()]
                    
                    # If game buffer wrapped or cleared, reset our pointer
                    if len(all_lines) < self.last_line_count:
                        self.last_line_count = 0
                    
                    new_lines = all_lines[self.last_line_count:]
                    
                    if new_lines:
                        # Update the pointer by how many lines we just processed
                        self.last_line_count = len(all_lines)
                        
                        try:
                            with open(self.current_log_path, "a", encoding="utf-8") as f:
                                for line in new_lines:
                                    log_ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                                    f.write(f"{log_ts} {line}\n")
                                f.flush() 
                        except Exception as e:
                            logger.error(f"Error writing to chat log: {e}")
        
        self.root.after(1000, self.update_loop)

    def setup_ui_main(self):
        """Creates the full UI with the correct names for the Sync function."""
        
        # 1. TOP STATS BAR
        self.stats_frame = tk.Frame(self.root, bg="#C0C0C0")
        self.stats_frame.pack(fill="x", side="top")
        
        self.stats_label = tk.Label(
            self.stats_frame, 
            text="HP: -- | MP: -- | VG: --", 
            font=("Arial", 10, "bold"), 
            bg="#C0C0C0"
        )
        self.stats_label.pack(side="left", padx=5)
        
        self.status_label = tk.Label(
            self.stats_frame, 
            text="System Ready", 
            font=("Arial", 9, "italic"), 
            bg="#C0C0C0",
            fg="#555"
        )
        self.status_label.pack(side="left", padx=20)
        
        self.name_label = tk.Label(self.stats_frame, text="Identity: Unknown", bg="#C0C0C0")
        self.name_label.pack(side="right", padx=5)

        # 2. MIDDLE CONTAINER (Split View)
        self.mid_container = tk.Frame(self.root, bg="#C0C0C0")
        self.mid_container.pack(fill="both", expand=True, padx=5, pady=5)

        # LEFT: Character Knowledge
        self.know_frame = tk.LabelFrame(self.mid_container, text="Character Knowledge", bg="#C0C0C0")
        self.know_frame.pack(side="left", fill="both", expand=True, padx=(0, 2))
        
        self.list_display = scrolledtext.ScrolledText(self.know_frame, height=10, width=25, state="disabled", font=("Arial", 9))
        self.list_display.pack(fill="both", expand=True)

        # RIGHT: Improves Tracker
        self.imp_frame = tk.LabelFrame(self.mid_container, text="Live Improves", bg="#C0C0C0")
        self.imp_frame.pack(side="right", fill="both", expand=True, padx=(2, 0))

        columns = ("Imps", "Latest", "Delta")
        self.imp_tree = ttk.Treeview(self.imp_frame, columns=columns, height=10)
        self.imp_tree.heading("#0", text="Skill/Spell")
        self.imp_tree.heading("Imps", text="Imps")
        self.imp_tree.heading("Latest", text="Latest")
        self.imp_tree.heading("Delta", text="Delta")
        self.imp_tree.column("#0", width=120)
        self.imp_tree.column("Imps", width=40, anchor="center")
        self.imp_tree.column("Latest", width=80, anchor="center")
        self.imp_tree.column("Delta", width=80, anchor="center")
        self.imp_tree.pack(fill="both", expand=True)

        # 3. BOTTOM SECTION: School Progression Table
        self.prog_frame = tk.LabelFrame(self.root, text="School Progression", bg="#C0C0C0")
        self.prog_frame.pack(fill="both", expand=True, padx=5, pady=5)

        cols = ("Level", "Progress", "Remaining")
        self.unlock_label = ttk.Treeview(self.prog_frame, columns=cols, height=5)
        
        self.unlock_label.heading("#0", text="School")
        self.unlock_label.heading("Level", text="Current Lvl")
        self.unlock_label.heading("Progress", text="Sum of Top 3")
        self.unlock_label.heading("Remaining", text="Points Needed")

        self.unlock_label.column("#0", width=120)
        self.unlock_label.column("Level", width=80, anchor="center")
        self.unlock_label.column("Progress", width=80, anchor="center")
        self.unlock_label.column("Remaining", width=100, anchor="center")
        
        self.unlock_label.pack(fill="both", expand=True)
        
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
        self.status_label.config(text="Syncing Knowledge...", fg="blue")
        logger.info("Manual Sync Started: Tab Cycling Sequence.")
        
        try:
            if not mem.attach(): 
                self.is_syncing = False
                return
            
            hwnd = find_game_window()
            if not hwnd: 
                self.is_syncing = False
                return

            # --- PHASE 1: TAB CYCLING ---
            tab_handles = []
            win32gui.EnumChildWindows(hwnd, lambda h, l: tab_handles.append(h) if win32gui.GetDlgCtrlID(h) == 1029 else None, None)
            
            if len(tab_handles) >= 3:
                # Sequence: Spells -> Skills -> Spells
                win32gui.SendMessage(tab_handles[1], win32con.BM_CLICK, 0, 0)
                time.sleep(0.3)
                win32gui.SendMessage(tab_handles[2], win32con.BM_CLICK, 0, 0)
                time.sleep(0.3)
                win32gui.SendMessage(tab_handles[1], win32con.BM_CLICK, 0, 0)
                
                # --- PHASE 2: READ SPELLS ---
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
                    data = get_raw_skill_dict(target_lb, 3) 
                    self.knowledge_cache.update(data)
                
                # --- PHASE 3: READ SKILLS ---
                win32gui.SendMessage(tab_handles[2], win32con.BM_CLICK, 0, 0)
                time.sleep(0.5) 
                lb_id = find_skill_listbox(hwnd)
                if lb_id:
                    data = get_raw_skill_dict(lb_id, 5) 
                    self.knowledge_cache.update(data)

            # --- PHASE 4: IDENTITY ---
            if not self.char_name:
                name = capture_character_name(hwnd)
                if name:
                    self.char_name = name
                    self.name_label.config(text=f"Identity: {name}")

            self.refresh_ui_display()
            self.status_label.config(text="System Ready", fg="#555")
            logger.info("Knowledge Sync Complete.")
                
        except Exception as e:
            logger.error(f"Sync error: {e}")
            self.status_label.config(text="Sync Error", fg="red")
        finally:
            self.is_syncing = False

    def refresh_ui_display(self):
        """Updates the Knowledge list and the School Progression table."""
        # 1. Update Knowledge List (Left Side)
        self.list_display.config(state="normal")
        self.list_display.delete("1.0", tk.END)
        for n in sorted(self.knowledge_cache.keys()):
            self.list_display.insert(tk.END, f"{n.title()}: {self.knowledge_cache[n]}%\n")
        self.list_display.config(state="disabled")

        # 2. Clear and Refill the School Progression Table (Bottom)
        for item in self.unlock_label.get_children():
            self.unlock_label.delete(item)

        results = self.calc.calculate_all_unlocks(self.knowledge_cache)
        
        for res in results:
            if isinstance(res, dict):
                # Get the raw number (e.g., 56)
                top_3_raw = int(res.get('current_sum', 0))
                
                # We add the '%' symbol right here in the values tuple
                self.unlock_label.insert("", "end", text=res['name'], values=(
                    f"L{res['current_lvl']}",
                    f"{top_3_raw}%",          # Added the % here
                    f"{int(res['needed'])}%"    # Points needed
                ))
            else:
                self.unlock_label.insert("", "end", text="Info", values=("---", "---", str(res)))
        
    def start_new_log_session(self):
        """Creates a fresh log and starts the real-time string monitor."""
        if not os.path.exists("logs"):
            os.makedirs("logs")

        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.current_log_path = os.path.abspath(os.path.join("logs", f"session_{ts}.log"))
        
        try:
            # 1. Physically create the file first
            with open(self.current_log_path, "w", encoding="utf-8") as f:
                f.write(f"--- Session Started: {datetime.now()} ---\n")
            
            logger.info(f"Log file created: {self.current_log_path}")

            # 2. Start the monitor with the ABSOLUTE path to avoid confusion
            self.monitor = LogMonitor(self.current_log_path)
            monitor_thread = threading.Thread(
                target=self.monitor.watch, 
                args=(self.handle_detected_improve,), 
                daemon=True
            )
            monitor_thread.start()
            
        except Exception as e:
            logger.error(f"Failed to initialize log session/monitor: {e}")
    
    def handle_detected_improve(self, skill_name):
        """Updates the UI grid whenever a new improve is detected in the logs."""
        name = skill_name.title()
        now = datetime.now()
        
        # 1. Update the internal data
        if name not in self.session_improves:
            self.session_improves[name] = {
                "count": 0,
                "first_time": now,
                "last_time": now
            }
        
        stats = self.session_improves[name]
        stats["count"] += 1
        
        # Calculate Delta (Time since last improve)
        diff = now - stats["last_time"]
        delta_str = f"{int(diff.total_seconds() // 60)}m {int(diff.total_seconds() % 60)}s"
        
        # Update timestamp for next time
        stats["last_time"] = now
        latest_str = now.strftime("%H:%M:%S")

        # 2. Update the UI Grid (Thread-safe)
        def update_ui():
            # If the skill is already in the list, update it. Otherwise, add new row.
            if self.imp_tree.exists(name):
                self.imp_tree.item(name, values=(stats["count"], latest_str, delta_str))
            else:
                self.imp_tree.insert("", "end", iid=name, text=name, 
                                     values=(stats["count"], latest_str, "---"))
        
        self.root.after(0, update_ui)
        logger.info(f"✨ UI Updated for Gain: {name}")

if __name__ == "__main__":
    root = tk.Tk()
    app = CompanionApp(root)
    root.mainloop()
