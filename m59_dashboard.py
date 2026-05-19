import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import time
import os
import psutil
import win32gui
import win32process
import win32con
import win32api
import logging
import sys
import json
import winsound
from datetime import datetime

# Configure Terminal Debug Logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("m59.dashboard")

# Import FROZEN modules
from m59_bridge import establish_bridge, release_pid, find_available_instance, claim_pid
from m59_scraper import capture_identity, get_blakgraph_stats, cycle_tabs_and_scrape, get_text_from_hwnd, MemoryReader
from m59_tracker import SessionTracker
from m59_combat import CombatMonitor
from m59_calculator import SchoolCalculator
from m59_vault import perform_vault_scan
from m59_updater import check_for_updates

SETTINGS_FILE = "gui_settings.json"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class PKFrame(tk.Toplevel):
    """Refined Strategy: 4 separate windows that form a frame around the GAME window."""
    def __init__(self, parent, target_hwnd):
        super().__init__(parent)
        self.target_hwnd = target_hwnd
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        self.bars = []
        for _ in range(4):
            b = tk.Toplevel(self)
            b.overrideredirect(True)
            b.attributes("-topmost", True)
            b.config(bg="red")
            b.withdraw()
            self.bars.append(b)

    def flash(self, duration=5):
        try:
            rect = win32gui.GetWindowRect(self.target_hwnd)
            x, y, x2, y2 = rect
            w, h = x2 - x, y2 - y
            t = 10 # Thickness
            self.bars[0].geometry(f"{w}x{t}+{x}+{y}") # Top
            self.bars[1].geometry(f"{w}x{t}+{x}+{y2-t}") # Bottom
            self.bars[2].geometry(f"{t}x{h}+{x}+{y}") # Left
            self.bars[3].geometry(f"{t}x{h}+{x2-t}+{y}") # Right
            for b in self.bars: b.deiconify()
            def hide():
                for b in self.bars: b.withdraw()
            self.after(duration * 1000, hide)
        except: pass

class M59Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.version = "0.00"
        try:
            v_path = resource_path("VERSION")
            if os.path.exists(v_path):
                with open(v_path, "r") as f: self.version = f.read().strip()
        except: pass
        
        self.title(f"M59 Companion v{self.version}")
        self.geometry("1100x850")
        
        # --- Persistent Settings ---
        self.pk_alert_enabled = tk.BooleanVar(value=True)
        self.pk_sound_enabled = tk.BooleanVar(value=True)
        self.pk_frame_enabled = tk.BooleanVar(value=True)
        self.pk_sound_path = tk.StringVar(value="SystemExclamation")
        self.load_settings()
        
        # --- Internal State ---
        self.target_pid = None
        self.pm_obj = None
        self.char_name = "Unknown"
        self.main_hwnd = None
        self.is_running = True
        self.pk_frame = None
        
        # Tracking State
        self.session_kills = {"monsters": {}, "players": {}}
        self.all_time_kills = {"monsters": {}, "players": {}}
        self.last_tail = []
        self.refresh_counter = 10
        self.knowledge_cache = {}
        self.current_attributes = {}
        self.vault_data = {"barloque": [], "hungry": []}
        self.calculator = SchoolCalculator()
        self.alert_active = False

        # --- UI Layout ---
        self.status_var = tk.StringVar(value="Initializing...")
        # Pack the status frame FIRST with side=BOTTOM to ensure it claims its space
        self.status_frame = tk.Frame(self, bd=1, relief=tk.SUNKEN)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_bar = tk.Label(self.status_frame, textvariable=self.status_var, anchor=tk.W, padx=5)
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.tab_dash = tk.Frame(self.notebook, bg="#f0f0f0")
        self.tab_prog = tk.Frame(self.notebook, bg="#f0f0f0")
        self.tab_vault = tk.Frame(self.notebook, bg="#f0f0f0")
        self.tab_book = tk.Frame(self.notebook, bg="#f0f0f0") 
        self.tab_logs = tk.Frame(self.notebook, bg="#f0f0f0")
        self.tab_settings = tk.Frame(self.notebook, bg="#f0f0f0")
        
        self.notebook.add(self.tab_dash, text=" Dashboard ")
        self.notebook.add(self.tab_prog, text=" Progression ")
        self.notebook.add(self.tab_vault, text=" Vault ")
        self.notebook.add(self.tab_book, text=" Kill Book ")
        self.notebook.add(self.tab_logs, text=" Logs & History ")
        self.notebook.add(self.tab_settings, text=" Settings ")
        
        self.setup_tab_dashboard()
        self.setup_tab_progression()
        self.setup_tab_vault()
        self.setup_tab_book()
        self.setup_tab_logs()
        self.setup_tab_settings()
        
        # Set a more permissive minimum size
        self.minsize(400, 300)
        
        self.after(100, self.establish_connection)
        self.after(2000, self.background_update_check)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    s = json.load(f)
                    geo = s.get("geometry")
                    if geo: self.geometry(geo)
                    self.pk_alert_enabled.set(s.get("pk_alert_enabled", True))
                    self.pk_sound_enabled.set(s.get("pk_sound_enabled", True))
                    self.pk_frame_enabled.set(s.get("pk_frame_enabled", True))
                    self.pk_sound_path.set(s.get("pk_sound_path", "SystemExclamation"))
            except: pass

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump({
                    "geometry": self.geometry(),
                    "pk_alert_enabled": self.pk_alert_enabled.get(),
                    "pk_sound_enabled": self.pk_sound_enabled.get(),
                    "pk_frame_enabled": self.pk_frame_enabled.get(),
                    "pk_sound_path": self.pk_sound_path.get()
                }, f)
        except: pass

    def setup_tab_book(self):
        """Creates the Kill Book tab."""
        header = tk.Frame(self.tab_book, bg="#f0f0f0"); header.pack(fill="x", padx=10, pady=5)
        tk.Label(header, text="The Eternal Kill Book", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(side="left")
        cont = tk.Frame(self.tab_book, bg="#f0f0f0"); cont.pack(fill="both", expand=True, padx=5, pady=5)
        self.book_widgets = {}
        for kt in ["monsters", "players"]:
            title = " Monsters Slain " if kt == "monsters" else " Players & Notables "
            f = tk.LabelFrame(cont, text=f" {title} ", bg="#f0f0f0", font=("Arial", 10, "bold"))
            f.pack(side="left", fill="both", expand=True, padx=5)
            row = tk.Frame(f, bg="#f0f0f0"); row.pack(fill="x", padx=5, pady=5)
            tk.Label(row, text="Filter:", bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
            fv = tk.StringVar(); fv.trace_add("write", lambda *a, k=kt: self.update_book_tree(k))
            tk.Entry(row, textvariable=fv, width=15).pack(side="left", padx=2)
            tr = ttk.Treeview(f, columns=("Name", "AllTime", "Session"), show="headings", height=15)
            tr.heading("Name", text="Victim"); tr.heading("AllTime", text="Total"); tr.heading("Session", text="Session")
            tr.column("Name", width=150); tr.column("AllTime", width=60, anchor="center"); tr.column("Session", width=60, anchor="center")
            tr.pack(fill="both", expand=True, padx=5, pady=2)
            self.book_widgets[kt] = {"tree": tr, "filter_var": fv}

    def update_book_tree(self, ktype):
        w = self.book_widgets[ktype]; tr = w["tree"]; fv = w["filter_var"]
        for i in tr.get_children(): tr.delete(i)
        ft = fv.get().lower()
        victims = set(self.all_time_kills[ktype].keys()) | set(self.session_kills[ktype].keys())
        for v in sorted(list(victims)):
            if ft in v.lower():
                at = self.all_time_kills[ktype].get(v, 0); se = self.session_kills[ktype].get(v, 0)
                tr.insert("", "end", values=(v, max(at, se), f"+{se}" if se > 0 else ""))

    def load_kill_book(self):
        if self.char_name == "Unknown": return
        p = f"logs/{self.char_name.replace(' ', '_')}_kills.json"
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    d = json.load(f); from m59_combat import CombatMonitor; tm = CombatMonitor(self.char_name)
                    self.all_time_kills = {"monsters": {}, "players": {}}
                    for cat in ["monsters", "players"]:
                        for v, c in d.get(cat, {}).items():
                            l = v.lower(); is_m = l in tm.mob_set or (l.startswith("the ") and l[4:] in tm.mob_set) or (l.startswith("a ") and l[2:] in tm.mob_set)
                            nc = "monsters" if is_m else "players"; self.all_time_kills[nc][v] = self.all_time_kills[nc].get(v, 0) + c
                self.update_book_tree("monsters"); self.update_book_tree("players")
            except: pass

    def setup_tab_settings(self):
        container = tk.Frame(self.tab_settings, bg="#f0f0f0"); container.pack(fill="both", expand=True, padx=20, pady=20)
        tk.Label(container, text="Companion Settings", font=("Arial", 14, "bold"), bg="#f0f0f0").pack(anchor="w", pady=(0, 20))
        pk_group = tk.LabelFrame(container, text=" Player Killer (PK) Alerts ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15); pk_group.pack(fill="x")
        tk.Checkbutton(pk_group, text="Enable Global PK Alerts", variable=self.pk_alert_enabled, bg="#f0f0f0", font=("Arial", 10)).pack(anchor="w")
        sub = tk.Frame(pk_group, bg="#f0f0f0", padx=20); sub.pack(fill="x", pady=10)
        tk.Checkbutton(sub, text="Play Alert Sound", variable=self.pk_sound_enabled, bg="#f0f0f0").grid(row=0, column=0, sticky="w")
        sbf = tk.Frame(sub, bg="#f0f0f0"); sbf.grid(row=0, column=1, padx=20)
        tk.Entry(sbf, textvariable=self.pk_sound_path, width=40, state="readonly").pack(side="left")
        tk.Button(sbf, text="Browse...", command=self.browse_sound).pack(side="left", padx=5); tk.Button(sbf, text="▶", command=self.test_sound).pack(side="left")
        tk.Checkbutton(sub, text="Show In-Game Red Frame (Visual)", variable=self.pk_frame_enabled, bg="#f0f0f0").grid(row=1, column=0, sticky="w", pady=5)
        tk.Button(container, text="Save Settings", command=self.save_settings, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), pady=10).pack(side="bottom", fill="x")

    def browse_sound(self):
        p = filedialog.askopenfilename(filetypes=[("Wave files", "*.wav")])
        if p: self.pk_sound_path.set(p)

    def test_sound(self):
        p = self.pk_sound_path.get()
        try:
            if p == "SystemExclamation": winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
            else: winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except: messagebox.showerror("Error", "Could not play sound.")

    def setup_tab_dashboard(self):
        top = tk.Frame(self.tab_dash, bg="#f0f0f0"); top.pack(fill="x", padx=10, pady=5)
        self.hud_values = {}
        for s in ["HP", "MP", "VG"]:
            f = tk.Frame(top, bg="#f0f0f0"); f.pack(side="left", padx=20)
            tk.Label(f, text=f"{s}:", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(side="left")
            val = tk.Label(f, text="---", font=("Arial", 12), bg="#f0f0f0", width=4, anchor="w")
            val.pack(side="left", padx=5); self.hud_values[s] = val
        self.countdown_lbl = tk.Label(top, text="10s", font=("Arial", 8), bg="#f0f0f0", fg="gray"); self.countdown_lbl.pack(side="right", padx=10)
        grid = tk.Frame(self.tab_dash, bg="#f0f0f0"); grid.pack(fill="both", expand=True, padx=10, pady=5)
        attr_col = tk.LabelFrame(grid, text=" Attributes ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        attr_col.pack(side="left", fill="both", expand=False, padx=5)
        self.attr_labels = {}
        for a in ["Might", "Intellect", "Stamina", "Agility", "Mysticism", "Aim", "Karma"]:
            f = tk.Frame(attr_col, bg="#f0f0f0"); f.pack(fill="x", pady=4, padx=5)
            tk.Label(f, text=f"{a}:", font=("Arial", 10), bg="#f0f0f0", width=10, anchor="w").pack(side="left")
            v = tk.Label(f, text="--", font=("Arial", 10, "bold"), bg="#f0f0f0", width=5, anchor="e")
            v.pack(side="right"); self.attr_labels[a] = v
        gains_col = tk.LabelFrame(grid, text=" Session Improves ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        gains_col.pack(side="left", fill="both", expand=True, padx=5)
        self.gains_tree = ttk.Treeview(gains_col, columns=("Name", "Count", "Delta"), show="headings", height=10)
        for c, w in [("Name", 120), ("Count", 50), ("Delta", 80)]:
            self.gains_tree.heading(c, text=c); self.gains_tree.column(c, width=w, anchor="w" if c=="Name" else "center")
        self.gains_tree.pack(fill="both", expand=True)
        kills_col = tk.LabelFrame(grid, text=" Session Kills ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        kills_col.pack(side="left", fill="both", expand=True, padx=5)
        self.kills_tree = ttk.Treeview(kills_col, columns=("Name", "Count"), show="headings", height=10)
        for c, w in [("Name", 120), ("Count", 60)]:
            self.kills_tree.heading(c, text=c); self.kills_tree.column(c, width=w, anchor="w" if c=="Name" else "center")
        self.kills_tree.pack(fill="both", expand=True)

    def setup_tab_progression(self):
        ctrl = tk.Frame(self.tab_prog, bg="#f0f0f0"); ctrl.pack(fill="x", padx=10, pady=10)
        tk.Label(ctrl, text="Real-time School Progression Goals", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(side="left")
        self.sync_btn = tk.Button(ctrl, text="Sync All (Tab Dance)", command=self.trigger_sync, bg="#2196F3", fg="white", font=("Arial", 10, "bold"), padx=15); self.sync_btn.pack(side="right")
        
        # Use a treeview that supports expansion (show="tree headings")
        # Column #0 will be the "School / Ability" column
        self.prog_tree = ttk.Treeview(self.tab_prog, columns=("Level", "Sum", "Goal", "Needed"), show="tree headings")
        self.prog_tree.heading("#0", text="School / Ability")
        self.prog_tree.column("#0", width=220)
        
        for c, w in [("Level", 80), ("Sum", 100), ("Goal", 100), ("Needed", 100)]:
            self.prog_tree.heading(c, text=c)
            self.prog_tree.column(c, width=w, anchor="center")
            
        self.prog_tree.pack(fill="both", expand=True, padx=10, pady=5)

    def setup_tab_vault(self):
        header = tk.Frame(self.tab_vault, bg="#f0f0f0"); header.pack(fill="x", padx=10, pady=5)
        tk.Label(header, text="Vault Inventory Tracker", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(side="left")
        cont = tk.Frame(self.tab_vault, bg="#f0f0f0"); cont.pack(fill="both", expand=True, padx=5, pady=5)
        self.vault_widgets = {}
        for vt in ["barloque", "hungry"]:
            f = tk.LabelFrame(cont, text=f" {vt.title()} Vault ", bg="#f0f0f0", font=("Arial", 10, "bold")); f.pack(side="left", fill="both", expand=True, padx=5)
            row = tk.Frame(f, bg="#f0f0f0"); row.pack(fill="x", padx=5, pady=5)
            tk.Label(row, text="Filter:", bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
            fv = tk.StringVar(); fv.trace_add("write", lambda *a, v=vt: self.update_vault_tree(v))
            tk.Entry(row, textvariable=fv, width=15).pack(side="left", padx=2)
            btn = tk.Button(row, text="↻", command=lambda v=vt: self.trigger_vault_scan(v), bg="#FF9800" if vt=="barloque" else "#607D8B", fg="white", font=("Arial", 10, "bold"), padx=5)
            btn.pack(side="right")
            if vt == "hungry":
                btn.config(state="disabled")
            tr = ttk.Treeview(f, columns=("Name", "Qty"), show="headings", height=15)
            tr.heading("Name", text="Item"); tr.heading("Qty", text="Qty"); tr.column("Name", width=150); tr.column("Qty", width=50, anchor="center")
            tr.pack(fill="both", expand=True, padx=5, pady=2)
            sl = tk.Label(f, text="No scan data", font=("Arial", 7, "italic"), bg="#f0f0f0", fg="gray"); sl.pack(side="bottom", fill="x")
            self.vault_widgets[vt] = {"tree": tr, "filter_var": fv, "status_lbl": sl, "sync_btn": btn}

    def setup_tab_logs(self):
        paned = ttk.PanedWindow(self.tab_logs, orient=tk.HORIZONTAL); paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Left Side: Live Chat Mirror
        cf = tk.LabelFrame(paned, text=" Live Chat Mirror ", bg="#f0f0f0", font=("Arial", 10, "bold")); paned.add(cf, weight=3)
        self.chat_view = scrolledtext.ScrolledText(cf, bg="black", fg="#00FF00", font=("Consolas", 10), state="disabled"); self.chat_view.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Right Side: Historical Log Viewer
        rp = tk.Frame(paned, bg="#f0f0f0"); paned.add(rp, weight=2)
        
        hf = tk.LabelFrame(rp, text=" Historical Log Viewer ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        hf.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        
        # File selection list
        list_frame = tk.Frame(hf, bg="#f0f0f0")
        list_frame.pack(fill="x", padx=5, pady=5)
        tk.Label(list_frame, text="Select Log File:", bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
        self.log_file_list = ttk.Combobox(list_frame, state="readonly")
        self.log_file_list.pack(side="left", fill="x", expand=True, padx=5)
        self.log_file_list.bind("<<ComboboxSelected>>", self.load_historical_log)
        tk.Button(list_frame, text="↻", command=self.refresh_log_list, bg="#f0f0f0").pack(side="left")
        
        # History content area
        self.history_view = scrolledtext.ScrolledText(hf, bg="#1e1e1e", fg="#cccccc", font=("Consolas", 9), state="disabled")
        self.history_view.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Bottom: Utilities
        bf = tk.LabelFrame(rp, text=" Log Utilities ", bg="#f0f0f0", font=("Arial", 10, "bold")); bf.pack(fill="x", padx=5, pady=5)
        tk.Button(bf, text="Open Logs Folder", command=lambda: os.startfile(os.path.abspath("logs")), bg="#607D8B", fg="white", pady=5).pack(fill="x", padx=10, pady=5)
        tk.Button(bf, text="Open Latest Chat Log", command=self.open_latest_log, bg="#4CAF50", fg="white", pady=5).pack(fill="x", padx=10, pady=5)

    def refresh_log_list(self):
        """Populates the log file list from the logs directory."""
        if not os.path.exists("logs"): 
            os.makedirs("logs", exist_ok=True)
        
        files = [f for f in os.listdir("logs") if f.endswith(".log")]
        # Sort by modification time, newest first
        files.sort(key=lambda x: os.path.getmtime(os.path.join("logs", x)), reverse=True)
        self.log_file_list['values'] = files
        if files:
            self.log_file_list.current(0)
            self.load_historical_log()

    def load_historical_log(self, event=None):
        """Loads the content of the selected log file into the viewer."""
        filename = self.log_file_list.get()
        if not filename: return
        
        path = os.path.join("logs", filename)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            self.history_view.config(state="normal")
            self.history_view.delete("1.0", tk.END)
            self.history_view.insert(tk.END, content)
            self.history_view.see(tk.END) # Scroll to bottom of history
            self.history_view.config(state="disabled")
        except Exception as e:
            logger.error(f"Failed to load log {filename}: {e}")

    def trigger_pk_alert(self):
        if not self.pk_alert_enabled.get(): return
        self.alert_active = True
        if self.pk_sound_enabled.get():
            p = self.pk_sound_path.get()
            try:
                if p == "SystemExclamation": winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
                else: winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except: pass
        if self.pk_frame_enabled.get() and self.pk_frame: self.pk_frame.flash()
        self.after(5000, self.reset_pk_alert)

    def reset_pk_alert(self):
        self.alert_active = False; self.tab_dash.config(bg="#f0f0f0"); self.status_bar.config(bg="SystemButtonFace")

    def establish_connection(self):
        self.status_var.set("Scanning...")
        try:
            insts = self.find_all_instances()
            if not insts:
                if messagebox.askretrycancel("Error", "No game found."): self.establish_connection()
                else: self.destroy(); return
            if len(insts) == 1: self.pm_obj, self.target_pid = establish_bridge(); self.main_hwnd = insts[0]["hwnd"]
            else:
                from tkinter import Toplevel, Listbox
                sel_win = Toplevel(self); sel_win.title("Select Instance"); sel_win.geometry("400x300")
                lb = Listbox(sel_win, width=50); lb.pack(padx=20, pady=10, fill="both", expand=True)
                for i in insts: lb.insert("end", f"PID: {i['pid']} | {i['title']}")
                def on_sel():
                    s = lb.curselection()
                    if s:
                        self.target_pid = int(lb.get(s[0]).split("|")[0].replace("PID:", "").strip())
                        self.main_hwnd = next(x["hwnd"] for x in insts if x["pid"] == self.target_pid); sel_win.destroy()
                tk.Button(sel_win, text="Connect", command=on_sel).pack(pady=10)
                self.wait_window(sel_win)
                if not self.target_pid: self.destroy(); return
                import pymem; self.pm_obj = pymem.Pymem(self.target_pid); claim_pid(self.target_pid)
            self.char_name = capture_identity(self.main_hwnd, self.target_pid) or "Unknown"
            self.title(f"M59 Companion v{self.version} - {self.char_name}")
            self.status_var.set(f"Connected: {self.char_name}")
            self.load_vault_cache(); self.load_kill_book(); self.update_hud(); self.pk_frame = PKFrame(self, self.main_hwnd)
            self.refresh_log_list()
            threading.Thread(target=lambda: self._initial_sync(), daemon=True).start(); self.start_chat_monitor()
        except: self.destroy()

    def update_hud(self):
        if not self.main_hwnd or not self.is_running: return
        self.refresh_counter -= 1
        if self.refresh_counter <= 0:
            self.refresh_counter = 10
            try:
                st = get_blakgraph_stats(self.main_hwnd)
                if st:
                    for k, l in self.hud_values.items():
                        if k in st: l.config(text=str(st[k]))
                    for k, l in self.attr_labels.items():
                        if k in st: self.current_attributes[k] = st[k]; l.config(text=str(st[k]))
                    if self.knowledge_cache: self.update_progression_tab()
            except: pass
        self.countdown_lbl.config(text=f"{self.refresh_counter}s"); self.after(1000, self.update_hud)

    def manage_rotation(self, log_path):
        """Handles 24-hour rotation with unique timestamps."""
        if not os.path.exists(log_path): return
        creation_time = os.path.getctime(log_path)
        if time.time() - creation_time > 86400: # 24 hours
            safe_name = self.char_name.replace(" ", "_")
            now_ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            rotated_path = os.path.join("logs", f"{safe_name}_chat_{now_ts}.log")
            try:
                os.rename(log_path, rotated_path)
                logger.info(f"ROTATION: Moved old log to {os.path.basename(rotated_path)}")
                self.after(0, self.refresh_log_list)
            except: pass

    def start_chat_monitor(self):
        def loop():
            tr = SessionTracker(); co = CombatMonitor(self.char_name)
            ch = win32gui.GetDlgItem(self.main_hwnd, 1005)
            if not ch: return
            
            safe_name = self.char_name.replace(" ", "_")
            log_path = os.path.join("logs", f"{safe_name}_chat.log")
            
            cur = get_text_from_hwnd(ch); lines = [l.strip() for l in cur.splitlines() if l.strip()]
            self.last_tail = lines[-50:] if lines else []
            
            while self.is_running:
                try:
                    self.pm_obj.read_int(self.pm_obj.base_address)
                    self.manage_rotation(log_path)
                    
                    cur = get_text_from_hwnd(ch); lines = [l.strip() for l in cur.splitlines() if l.strip()]
                    new = []; found = -1; tail = list(self.last_tail)
                    while tail:
                        tl = len(tail); search = lines[-100-tl:] if len(lines) > 100 else lines; off = len(lines) - len(search)
                        for i in range(len(search) - tl, -1, -1):
                            if search[i:i+tl] == tail: found = off + i + tl; break
                        if found != -1: break
                        tail.pop(0)
                    if found != -1: new = lines[found:]
                    elif lines: self.last_tail = lines[-50:]
                    
                    if new:
                        ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                for l in new:
                                    f.write(f"{ts} {l}\n")
                                    self.after(0, lambda ln=l: self.append_chat_line(ln))
                                    try:
                                        g = tr.process_line(l)
                                        if g: self.after(0, lambda gn=g: self.on_gain_detected(gn))
                                        r = co.process_line(l)
                                        if r:
                                            if r["type"] == "KILL": self.after(0, lambda res=r: self.on_kill_detected(res))
                                            elif r["type"] == "PK_ALERT": self.after(0, self.trigger_pk_alert)
                                    except: pass
                                f.flush()
                        except: pass
                        for l in new: self.last_tail.append(l)
                        self.last_tail = self.last_tail[-50:]
                except:
                    try: self.pm_obj.read_int(self.pm_obj.base_address)
                    except: break
                time.sleep(1)
        threading.Thread(target=loop, daemon=True).start()

    def on_gain_detected(self, g):
        if self.gains_tree.exists(g['name']): self.gains_tree.item(g['name'], values=(g['name'], g['count'], g['delta']))
        else: self.gains_tree.insert("", "end", iid=g['name'], values=(g['name'], g['count'], "---"))

    def on_kill_detected(self, r):
        self.session_kills[r['category']][r['name']] = self.session_kills[r['category']].get(r['name'], 0) + 1
        count = self.session_kills[r['category']][r['name']]
        if self.kills_tree.exists(r['name']): self.kills_tree.item(r['name'], values=(r['name'], count))
        else: self.kills_tree.insert("", "end", iid=r['name'], values=(r['name'], count))
        self.update_book_tree(r['category'])

    def on_closing(self):
        self.is_running = False; self.save_settings()
        if self.target_pid:
            release_pid(self.target_pid)
        self.destroy()

    def append_chat_line(self, line):
        self.chat_view.config(state="normal"); self.chat_view.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n"); self.chat_view.see(tk.END); self.chat_view.config(state="disabled")
        if int(self.chat_view.index('end-1c').split('.')[0]) > 500:
            self.chat_view.config(state="normal"); self.chat_view.delete("1.0", "2.0"); self.chat_view.config(state="disabled")

    def trigger_sync(self):
        self.sync_btn.config(state="disabled"); threading.Thread(target=self.perform_sync, daemon=True).start()

    def perform_sync(self):
        try:
            mr = MemoryReader(self.pm_obj); kn, st = cycle_tabs_and_scrape(self.main_hwnd, mr)
            if kn or st: self.after(0, lambda: self._apply_sync_results(kn, st))
        except: pass
        finally: self.after(0, lambda: self.sync_btn.config(state="normal"))

    def _apply_sync_results(self, kn, st):
        if st: self._apply_initial_stats(st)
        if kn: self.knowledge_cache.update(kn)
        self.update_progression_tab()

    def update_progression_tab(self):
        if not self.knowledge_cache: return
        
        # Save which items were expanded to restore them after refresh
        expanded_schools = {self.prog_tree.item(i)['text'] for i in self.prog_tree.get_children() if self.prog_tree.item(i, 'open')}
        
        res = self.calculator.calculate_progression(self.knowledge_cache, self.current_attributes.get("Intellect", 25))
        for i in self.prog_tree.get_children(): self.prog_tree.delete(i)
        
        for r in res:
            name = r['name']
            is_open = name in expanded_schools
            parent = self.prog_tree.insert("", "end", text=name, 
                                          values=(f"Level {r['current_lvl']}", f"{r['current_sum']}%", f"{r['target_sum']}%", f"{r['needed']}%"),
                                          open=is_open)
            
            # Add child abilities for this school
            school_data = self.calculator.schools.get(name, {})
            for lvl_num in range(1, 7):
                lvl_key = f"Level_{lvl_num}"
                if lvl_key not in school_data: continue
                for skill in school_data[lvl_key]:
                    s_lower = skill.lower()
                    if s_lower in self.knowledge_cache:
                        val = self.knowledge_cache[s_lower]
                        self.prog_tree.insert(parent, "end", text=f"  {skill}", 
                                             values=(f"L{lvl_num}", f"{val}%", "", ""))

    def trigger_vault_scan(self, vt):
        if not messagebox.askyesno("Scan", f"Scan {vt} vault?"): return
        w = self.vault_widgets[vt]; w["sync_btn"].config(state="disabled"); threading.Thread(target=self.perform_vault_scan_thread, args=(vt,), daemon=True).start()

    def perform_vault_scan_thread(self, vt):
        try:
            inv = perform_vault_scan(self.main_hwnd, self.char_name, vt, lambda c, t, i, q: self.after(0, lambda: self.status_var.set(f"Scan: {c}/{t}")))
            if inv: self.after(0, lambda: self._apply_vault_results(vt, inv))
        except: pass
        finally: self.after(0, lambda: self.vault_widgets[vt]["sync_btn"].config(state="normal"))

    def _apply_vault_results(self, vt, inv):
        self.vault_data[vt] = inv; self.update_vault_tree(vt)
        self.vault_widgets[vt]["status_lbl"].config(text=f"Last Scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def update_vault_tree(self, vt):
        w = self.vault_widgets[vt]; tr = w["tree"]; fv = w["filter_var"]
        for i in tr.get_children(): tr.delete(i)
        for i in self.vault_data[vt]:
            if fv.get().lower() in i['item'].lower(): tr.insert("", "end", values=(i['item'], i['quantity']))

    def load_vault_cache(self):
        if self.char_name == "Unknown": return
        sn = self.char_name.replace(" ", "_")
        for vt in ["barloque", "hungry"]:
            p = next((x for x in [f"logs/{sn}_vault_{vt}.json", f"logs/{self.char_name}_vault_{vt}.json"] if os.path.exists(x)), None)
            if p:
                try:
                    with open(p, "r") as f:
                        d = json.load(f); self.vault_data[vt] = d.get("items", [])
                        self.update_vault_tree(vt)
                except: pass

    def _initial_sync(self):
        try:
            kn, st = cycle_tabs_and_scrape(self.main_hwnd, MemoryReader(self.pm_obj))
            if kn or st: self.after(0, lambda: self._apply_sync_results(kn, st))
        except: pass

    def _apply_initial_stats(self, st):
        for k, l in self.attr_labels.items():
            if k in st: self.current_attributes[k] = st[k]; l.config(text=str(st[k]))
        for k, l in self.hud_values.items():
            if k in st: l.config(text=str(st[k]))

    def background_update_check(self):
        def check():
            u, rv = check_for_updates(self.version)
            if not u: return
            
            def show_prompt():
                msg = f"A new version (v{rv}) is available!\n\n" \
                      "Options:\n" \
                      "1. 'Auto-Update' (Recommended): Downloads and swaps files automatically.\n" \
                      "2. 'Open Browser': Opens the GitHub page for manual download.\n\n" \
                      "Note: Auto-update may trigger a Windows SmartScreen warning. " \
                      "If it does, click 'More Info' -> 'Run Anyway'."
                
                choice = messagebox.askquestion("Update Available", msg, icon="info", 
                                               type="yesnocancel", # Yes=Auto, No=Browser, Cancel=Later
                                               default="yes")
                
                if choice == "yes": # Auto-Update
                    self.status_var.set("Downloading update...")
                    from m59_updater import download_update, apply_update
                    new_path = download_update()
                    if new_path:
                        apply_update(new_path)
                    else:
                        messagebox.showerror("Error", "Download failed.")
                        self.status_var.set("Update failed.")
                elif choice == "no": # Browser
                    from m59_updater import open_browser
                    open_browser()
            
            self.after(0, show_prompt)
        threading.Thread(target=check, daemon=True).start()

    def find_all_instances(self):
        insts = []
        def cb(h, e):
            if win32gui.IsWindowVisible(h) and "Meridian 59" in win32gui.GetWindowText(h):
                _, p = win32process.GetWindowThreadProcessId(h)
                try:
                    if psutil.Process(p).name().lower() == "meridian.exe": insts.append({"pid": p, "title": win32gui.GetWindowText(h), "hwnd": h})
                except: pass
        win32gui.EnumWindows(cb, None); return insts

    def open_latest_log(self):
        if self.char_name == "Unknown": return
        p = f"logs/{self.char_name.replace(' ', '_')}_chat.log"
        if os.path.exists(p): os.startfile(os.path.abspath(p))

if __name__ == "__main__":
    app = M59Dashboard(); app.mainloop()
