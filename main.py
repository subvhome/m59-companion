import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import queue
import logging
import time
import win32gui
import win32con
import os
from datetime import datetime
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

import sys
from utils import resource_path

# Application Version
VERSION = "v0.51"

class CompanionApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"M59 Companion {VERSION}")
        self.root.attributes("-topmost", True)
        
        # Initialize Managers
        self.config = ConfigManager() # Note: ConfigManager might need an internal update too
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
            
            # 2. Update Core Stats
            if mem.process_handle:
                s = get_stats(hwnd)
                if s: self.stats_label.config(text=f"HP: {s[0]} | MP: {s[1]} | VG: {s[2]}")
            
            # 3. Enhanced Chat Logger Logic
            chat_hwnd = win32gui.GetDlgItem(hwnd, 1005)
            if chat_hwnd:
                current_text = get_text_from_hwnd(chat_hwnd)
                if current_text:
                    all_lines = [l.strip() for l in current_text.splitlines() if l.strip()]
                    
                    if not hasattr(self, 'chat_sync_done'):
                        import m59_bridge
                        log_dir = os.path.dirname(self.current_log_path)
                        all_logs = sorted([os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".log")], 
                                         key=os.path.getmtime)
                        
                        history_file = None
                        history_candidates = [f for f in all_logs if os.path.normpath(f) != os.path.normpath(self.current_log_path)]
                        if history_candidates:
                            history_file = history_candidates[-1]

                        fingerprint = m59_bridge.get_log_fingerprint(history_file)
                        found_at = -1
                        
                        if fingerprint and len(fingerprint) >= 10:
                            for i in range(len(all_lines) - len(fingerprint) + 1):
                                if all_lines[i:i+len(fingerprint)] == fingerprint:
                                    found_at = i + len(fingerprint)
                                    break
                        
                        with open(self.current_log_path, "a", encoding="utf-8") as f:
                            if found_at != -1:
                                self.last_line_count = found_at
                                f.write(f"--- Found match: continuing log from {os.path.basename(history_file)} ---\n")
                                logger.info("Sync Success: Found fingerprint match.")
                            else:
                                self.last_line_count = len(all_lines)
                                f.write("--- No match found / fresh log session ---\n")
                                logger.info("Sync Failed: Starting from live text.")
                            f.flush()

                        self.chat_sync_done = True

                    # --- LIVE RECORDING AND PROCESSING ---
                    if len(all_lines) < self.last_line_count:
                        self.last_line_count = 0
                    
                    new_lines = all_lines[self.last_line_count:]
                    
                    if new_lines:
                        self.last_line_count = len(all_lines)
                        try:
                            with open(self.current_log_path, "a", encoding="utf-8") as f:
                                for line in new_lines:
                                    # LIVE DETECTION (Before Timestamp)
                                    self.detect_skill_gain(line)
                                    
                                    # Write to history log
                                    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                                    f.write(f"{ts} {line}\n")
                                f.flush()
                        except Exception as e:
                            logger.error(f"Log error: {e}")
            
            # 4. Live Chat Viewer Update
            self.update_chat_view_live()
        
        self.root.after(1000, self.update_loop)

    def detect_skill_gain(self, line):
        """
        Parses raw game lines for improvements immediately as they are scraped.
        """
        improve_phrase = "You have improved in the art of "
        hp_phrase = "You suddenly feel a little tougher."

        # Get testing mode from config
        testing_mode = self.config.settings["character"].get("testing_mode", False)

        found_skill_raw = None

        # 1. Check for Skill Gain
        if testing_mode:
            # In testing mode, the phrase can be ANYWHERE in the line (e.g. inside a Tell)
            if improve_phrase in line:
                parts = line.split(improve_phrase)
                if len(parts) > 1:
                    found_skill_raw = parts[1].strip()
        else:
            # In normal mode, it MUST be a system message starting with the phrase
            if line.startswith(improve_phrase):
                found_skill_raw = line[len(improve_phrase):].strip()

        if found_skill_raw:
            # Clean up trailing punctuation: . or ." or ". or "
            # This handles both system messages and captured chat messages
            clean_name = found_skill_raw
            for _ in range(2): # Strip up to two trailing punctuation marks (e.g. .")
                if clean_name and clean_name[-1] in ['.', '"', "'", '!']:
                    clean_name = clean_name[:-1].strip()

            # Format: Hunter's Aim, Hand-To-Hand
            words = clean_name.split(' ')
            formatted_words = []
            for word in words:
                sub_words = word.split('-')
                formatted_sub = "-".join([sw.capitalize() for sw in sub_words])
                formatted_words.append(formatted_sub)

            found_skill = " ".join(formatted_words).replace("'S", "'s")
            logger.info(f"Skill Detected: {found_skill} (Testing: {testing_mode})")
            self.handle_detected_improve(found_skill)
            return

        # 2. Check for HP Gain
        if testing_mode:
            if hp_phrase in line:
                logger.info("HP Gain Detected (Test)")
                self.handle_detected_improve("Hit Points")
        else:
            if line.startswith(hp_phrase):
                logger.info("HP Gain Detected")
                self.handle_detected_improve("Hit Points")
    def setup_ui_main(self):
        """Creates the full UI using tabs."""
        # Create Notebook (Tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # 1. DASHBOARD TAB
        self.dash_tab = tk.Frame(self.notebook, bg="#C0C0C0")
        self.notebook.add(self.dash_tab, text=" Dashboard ")

        # --- Dashboard Content ---
        # TOP STATS BAR
        self.stats_frame = tk.Frame(self.dash_tab, bg="#C0C0C0")
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

        # MIDDLE CONTAINER (Split View)
        self.mid_container = tk.Frame(self.dash_tab, bg="#C0C0C0")
        self.mid_container.pack(fill="both", expand=True, padx=5, pady=5)

        # LEFT: Character Knowledge
        self.know_frame = tk.LabelFrame(self.mid_container, text="Character Knowledge", bg="#C0C0C0")
        self.know_frame.pack(side="left", fill="both", expand=True, padx=(0, 2))
        
        self.list_display = scrolledtext.ScrolledText(self.know_frame, height=10, width=25, state="disabled", font=("Arial", 9))
        self.list_display.pack(fill="both", expand=True)

        # RIGHT: Improves Tracker
        self.imp_frame = tk.LabelFrame(self.mid_container, text="Live Improves", bg="#C0C0C0")
        self.imp_frame.pack(side="right", fill="both", expand=True, padx=(2, 0))

        columns = ("Imp Count", "Delta")
        self.imp_tree = ttk.Treeview(self.imp_frame, columns=columns, height=10)
        self.imp_tree.heading("#0", text="Skill/Spell")
        self.imp_tree.heading("Imp Count", text="Imp Count")
        self.imp_tree.heading("Delta", text="Delta")
        self.imp_tree.column("#0", width=120)
        self.imp_tree.column("Imp Count", width=80, anchor="center")
        self.imp_tree.column("Delta", width=100, anchor="center")
        self.imp_tree.pack(fill="both", expand=True)

        # BOTTOM SECTION: School Progression Table
        self.prog_frame = tk.LabelFrame(self.dash_tab, text="School Progression", bg="#C0C0C0")
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

        # 2. CHAT LOGS TAB
        self.chat_logs_tab = tk.Frame(self.notebook, bg="#C0C0C0")
        self.notebook.add(self.chat_logs_tab, text=" Chat Logs ")
        
        # Split Window for Chat Logs
        self.log_paned = tk.PanedWindow(self.chat_logs_tab, orient="horizontal", bg="#C0C0C0")
        self.log_paned.pack(fill="both", expand=True)

        # Left: List of Logs
        self.log_list_frame = tk.Frame(self.log_paned, width=150, bg="#C0C0C0")
        self.log_paned.add(self.log_list_frame)
        
        tk.Label(self.log_list_frame, text="Available Logs", bg="#C0C0C0", font=("Arial", 9, "bold")).pack(fill="x")
        
        # Switch to Treeview for better Wine/Linux compatibility
        self.log_list = ttk.Treeview(self.log_list_frame, show="tree", selectmode="browse")
        self.log_list.pack(fill="both", expand=True)
        
        # Configure Tags for colors and bolding
        # Note: Bolding in Treeview often requires a font object or specific font string
        self.log_list.tag_configure("active", foreground="darkgreen", font=("Arial", 9, "bold"))
        self.log_list.tag_configure("history", foreground="#666666", font=("Arial", 9))
        
        self.log_list.bind("<<TreeviewSelect>>", self.on_log_select)
        
        # Bind Tab change to refresh the list automatically
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        tk.Button(self.log_list_frame, text="Refresh List", command=self.refresh_log_list).pack(fill="x")

        # Right: Log Viewer
        self.log_view_frame = tk.Frame(self.log_paned, bg="#C0C0C0")
        self.log_paned.add(self.log_view_frame)
        
        self.log_view_header = tk.Label(self.log_view_frame, text="Select a log to view", bg="#C0C0C0", anchor="w", padx=5)
        self.log_view_header.pack(fill="x")
        
        self.chat_view = scrolledtext.ScrolledText(self.log_view_frame, font=("Arial", 10), state="disabled", bg="white")
        self.chat_view.pack(fill="both", expand=True)
        
        self.live_view_var = tk.BooleanVar(value=True)
        self.live_check = tk.Checkbutton(self.log_view_frame, text="Live Scroll", variable=self.live_view_var, bg="#C0C0C0")
        self.live_check.pack(side="right")

        # 3. CONSOLE TAB
        self.console_tab = tk.Frame(self.notebook, bg="#F0F0F0")
        self.notebook.add(self.console_tab, text=" Console ")
        
        self.log_display = scrolledtext.ScrolledText(self.console_tab, font=("Consolas", 9), state="disabled", bg="black", fg="#00FF00")
        self.log_display.pack(fill="both", expand=True, padx=2, pady=2)

        self.current_viewing_file = None
        self.last_view_size = 0
        self.setup_log_context_menu()
        self.refresh_log_list()
        
        # Select the current session log by default
        if self.current_log_path:
            filename = os.path.basename(self.current_log_path)
            if self.log_list.exists(filename):
                self.log_list.selection_set(filename)
                self.on_log_select(None)

    def on_tab_changed(self, event):
        """Refreshes the log list whenever the user switches to the Chat Logs tab."""
        selected_tab = self.notebook.select()
        tab_text = self.notebook.tab(selected_tab, "text").strip()
        
        if tab_text == "Chat Logs":
            current_sel = self.log_list.selection()
            self.refresh_log_list()
            
            # If nothing was selected before, or we want to ensure live is picked
            if not current_sel and self.current_log_path:
                filename = os.path.basename(self.current_log_path)
                if self.log_list.exists(filename):
                    self.log_list.selection_set(filename)
            elif current_sel:
                # Try to restore previous selection
                if self.log_list.exists(current_sel[0]):
                    self.log_list.selection_set(current_sel[0])

    def refresh_log_list(self):
        """Populates the treeview with log files and status indicators."""
        for item in self.log_list.get_children():
            self.log_list.delete(item)
            
        if not os.path.exists("logs"):
            return

        files = sorted([f for f in os.listdir("logs") if f.endswith(".log")], 
                      key=lambda x: os.path.getmtime(os.path.join("logs", x)), 
                      reverse=True)
        
        max_width = 15
        for f in files:
            is_active = (self.current_log_path and os.path.basename(self.current_log_path) == f)
            
            if is_active:
                display_name = f"[LIVE] {f}"
                self.log_list.insert("", tk.END, iid=f, text=display_name, tags=("active",))
            else:
                display_name = f"[HIST] {f}"
                self.log_list.insert("", tk.END, iid=f, text=display_name, tags=("history",))
            
            max_width = max(max_width, len(display_name))

        # Adjust left panel width based on longest filename
        self.log_paned.paneconfigure(self.log_list_frame, width=max_width * 7 + 25)

    def setup_log_context_menu(self):
        """Adds a right-click menu to the log list."""
        self.log_menu = tk.Menu(self.root, tearoff=0)
        self.log_menu.add_command(label="Delete Log", command=self.delete_selected_log)
        self.log_list.bind("<Button-3>", self.show_log_context_menu)

    def show_log_context_menu(self, event):
        try:
            # Select the item under the mouse
            item = self.log_list.identify_row(event.y)
            if item:
                self.log_list.selection_set(item)
                self.log_menu.post(event.x_root, event.y_root)
        except Exception:
            pass

    def delete_selected_log(self):
        selection = self.log_list.selection()
        if not selection: return
        
        filename = selection[0]
        
        if self.current_log_path and filename == os.path.basename(self.current_log_path):
            messagebox.showwarning("Warning", "Cannot delete the active session log.")
            return

        if messagebox.askyesno("Delete", f"Are you sure you want to delete {filename}?"):
            try:
                os.remove(os.path.join("logs", filename))
                self.refresh_log_list()
                self.chat_view.config(state="normal")
                self.chat_view.delete("1.0", tk.END)
                self.chat_view.config(state="disabled")
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete: {e}")

    def on_log_select(self, event):
        """Handles selecting a log file from the treeview."""
        selection = self.log_list.selection()
        if not selection:
            return
        
        filename = selection[0]
        filepath = os.path.join("logs", filename)
        
        self.current_viewing_file = filepath
        self.last_view_size = 0
        self.log_view_header.config(text=f"Viewing: {filename}")
        
        # Load file content
        self.chat_view.config(state="normal")
        self.chat_view.delete("1.0", tk.END)
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                self.chat_view.insert(tk.END, content)
                self.last_view_size = os.path.getsize(filepath)
        except Exception as e:
            self.chat_view.insert(tk.END, f"Error loading log: {e}")
        
        self.chat_view.see(tk.END)
        self.chat_view.config(state="disabled")

    def update_chat_view_live(self):
        """If viewing the current log and live scroll is on, append new data."""
        if not self.current_viewing_file or not self.live_view_var.get():
            return
        
        # Only live-update if the file we are viewing is the active session log
        if os.path.normpath(self.current_viewing_file) != os.path.normpath(self.current_log_path):
            return

        try:
            curr_size = os.path.getsize(self.current_viewing_file)
            if curr_size > self.last_view_size:
                with open(self.current_viewing_file, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(self.last_view_size)
                    new_data = f.read()
                    if new_data:
                        self.chat_view.config(state="normal")
                        self.chat_view.insert(tk.END, new_data)
                        self.chat_view.see(tk.END)
                        self.chat_view.config(state="disabled")
                self.last_view_size = curr_size
        except Exception as e:
            pass

    def setup_ui_logs(self):
        """No longer needed as logs are in a tab."""
        pass

    def toggle_logs(self):
        """Redundant in tabbed view."""
        pass

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
        
    def test_simulate_gain(self):
        """Debug function to test the capture and UI logic."""
        test_line = "You have improved in the art of axe wielding."
        logger.info("Simulating test gain...")
        self.detect_skill_gain(test_line)

    def start_new_log_session(self):
        """Creates a fresh log file for history. Real-time detection is now handled in update_loop."""
        if not os.path.exists("logs"):
            os.makedirs("logs")

        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.current_log_path = os.path.join("logs", f"session_{ts}.log")
        
        with open(self.current_log_path, "w", encoding="utf-8") as f:
            f.write(f"--- Session Started: {datetime.now()} ---\n")
        
        logger.info(f"Logging history to: {os.path.basename(self.current_log_path)}")
    
    def handle_detected_improve(self, name):
        """
        Triggered by the LogMonitor when a new gain is found in the logs.
        Updates the UI table with counts and timers.
        """
        now = datetime.now()
        
        # If this is a new skill for this session, set up the data
        if name not in self.session_improves:
            self.session_improves[name] = {
                "count": 0,
                "first_time": now,
                "last_time": now
            }
        
        stats = self.session_improves[name]
        stats["count"] += 1
        
        # Calculate Delta (Time since the LAST gain of this specific skill)
        diff = now - stats["last_time"]
        
        # If it's the first gain, we show "---", otherwise show minutes/seconds
        if stats["count"] == 1:
            delta_str = "---"
        else:
            m, s = divmod(int(diff.total_seconds()), 60)
            delta_str = f"{m}m {s}s"
            
        # Update the 'last_time' for the next calculation
        stats["last_time"] = now

        def update_ui():
            try:
                # Check if the skill is already in the visual list (the Treeview)
                if self.imp_tree.exists(name):
                    # Update existing row
                    self.imp_tree.item(name, values=(stats["count"], delta_str))
                else:
                    # Add new row
                    # iid=name allows us to find it later using the skill name
                    self.imp_tree.insert("", "end", iid=name, text=name, 
                                         values=(stats["count"], "---"))
                
                # Make the new/updated entry visible
                self.imp_tree.see(name)
                self.root.update_idletasks()
            except Exception as e:
                print(f"UI Update Error: {e}")
        
        # This tells Python to run the UI update on the main thread safely
        self.root.after(0, update_ui)

if __name__ == "__main__":
    root = tk.Tk()
    app = CompanionApp(root)
    root.mainloop()
