import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog
import threading
import time
import os
import psutil
import win32gui
import win32process
import win32con
import win32api
import pywintypes
import logging
import sys
import json
import winsound
import re
import ctypes
from ctypes import wintypes
import webbrowser
from datetime import datetime

# --- Windows AppBar API Definitions ---
class RECT(ctypes.Structure):
    _fields_ = [
        ('left', wintypes.LONG),
        ('top', wintypes.LONG),
        ('right', wintypes.LONG),
        ('bottom', wintypes.LONG)
    ]

class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('hWnd', wintypes.HWND),
        ('uCallbackMessage', wintypes.UINT),
        ('uEdge', wintypes.UINT),
        ('rc', RECT),
        ('lParam', wintypes.LPARAM)
    ]

ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003
ABM_GETSTATE = 0x00000004
ABM_GETTASKBARPOS = 0x00000005
ABM_ACTIVATE = 0x00000006
ABM_GETAUTOHIDEBAR = 0x00000007
ABM_SETAUTOHIDEBAR = 0x00000008
ABM_WINDOWPOSCHANGED = 0x00000009
ABM_SETSTATE = 0x0000000a

ABE_LEFT = 0
ABE_TOP = 1
ABE_RIGHT = 2
ABE_BOTTOM = 3

Shell32 = ctypes.windll.shell32
# --------------------------------------

# Import centralized logging
from m59_logging import setup_logging, get_logger
logger = get_logger("dashboard")

# Import modules
from m59_utils import (
    resource_path, get_safe_name, find_game_hwnd, 
    GAME_EXE, GAME_TITLE_BASE, LOGIN_MARKER,
    RE_SPEECH, RE_BANK_TOTAL, RE_BANK_WITHDRAW
)
from m59_bridge import establish_bridge, release_pid, find_available_instance, claim_pid, get_unclaimed_instances
from m59_scraper import capture_identity, get_blakgraph_stats, cycle_tabs_and_scrape, get_text_from_hwnd, MemoryReader
from m59_tracker import SessionTracker
from m59_combat import CombatMonitor
from m59_calculator import SchoolCalculator
from m59_vault import perform_vault_scan, find_nested_control
from m59_updater import check_for_updates
from m59_gps import GPSManager
from m59_bank import BankManager
from m59_lifecycle import InstanceManager
from m59_inventory import InventoryScraper
from m59_wholist import WhoListMonitor
from m59_time import get_game_time, format_game_time
import m59_inventory as inventory
import m59_bgf
import m59_map
import m59_commalias

SETTINGS_FILE = "settings/gui_settings.json"

class DraggableNotebook(ttk.Notebook):
    """A ttk.Notebook with drag-and-drop tab reordering."""
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.bind("<Button-1>", self.on_start_drag, add=True)
        self.bind("<B1-Motion>", self.on_drag_motion, add=True)

    def on_start_drag(self, event):
        try:
            index = self.index(f"@{event.x},{event.y}")
            self._drag_index = index
        except:
            self._drag_index = None

    def on_drag_motion(self, event):
        if self._drag_index is None: return
        try:
            index = self.index(f"@{event.x},{event.y}")
            if index != self._drag_index:
                dragged_widget = self.nametowidget(self.tabs()[self._drag_index])
                self.insert(index, dragged_widget)
                self._drag_index = index
        except: pass

class PKFrame(tk.Toplevel):
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
            t = 10
            self.bars[0].geometry(f"{w}x{t}+{x}+{y}") # Top
            self.bars[1].geometry(f"{w}x{t}+{x}+{y2-t}") # Bottom
            self.bars[2].geometry(f"{t}x{h}+{x}+{y}") # Left
            self.bars[3].geometry(f"{t}x{h}+{x2-t}+{y}") # Right
            for b in self.bars:
                b.deiconify()
            self.after(duration * 1000, self.hide_bars)
        except:
            pass

    def hide_bars(self):
        for b in self.bars:
            b.withdraw()

class M59Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        
        try:
            self.withdraw()
            self.attributes("-alpha", 0.0)
        except: pass
        
        # --- UI Scaling & DPI Setup ---
        # Calculate scaling factor based on system DPI
        # Standard DPI is 96. winfo_fpixels('1i') returns the number of pixels in one inch.
        try:
            dpi = self.winfo_fpixels('1i')
            self.scaling_factor = dpi / 96.0
            # Apply Tkinter internal scaling
            self.tk.call('tk', 'scaling', dpi / 72.0)
        except:
            self.scaling_factor = 1.0
            
        logger.info(f"UI: Initializing with scaling factor {self.scaling_factor:.2f}")

        self.version = "0.00"
        try:
            v_p = resource_path("VERSION")
            if os.path.exists(v_p):
                with open(v_p, "r") as f:
                    self.version = f.read().strip().split("\n")[0]
        except:
            pass
        
        self.title(f"M59 Companion v{self.version}")
        
        # Scale initial window geometry
        base_w, base_h = 1100, 850
        self.geometry(f"{int(base_w * self.scaling_factor)}x{int(base_h * self.scaling_factor)}")
        
        # Initialize styles
        self.style = ttk.Style()
        self.apply_ui_scaling()

        # --- Settings ---
        self.pk_alert_enabled = tk.BooleanVar(value=True)
        self.pk_sound_enabled = tk.BooleanVar(value=True)
        self.pk_frame_enabled = tk.BooleanVar(value=True)
        self.pk_sound_path = tk.StringVar(value="SystemExclamation")
        self.tell_sound_enabled = tk.BooleanVar(value=True)
        self.tell_sound_path = tk.StringVar(value="sound/dm_chime.wav")
        self.elusion_phrase = tk.StringVar(value='say "I wish to travel to {loc}."')
        self.elusion_geometry = tk.StringVar(value="320x35+100+100")
        self.guildhall_name = tk.StringVar(value="")
        self.custom_elusion_phrases = []
        self.debug_enabled = tk.BooleanVar(value=False)
        self.debug_enabled.trace_add("write", lambda *a: setup_logging(self.debug_enabled.get()))
        
        
        # --- Who List State ---
        
        self.who_list_docked = tk.BooleanVar(value=False)
        self.who_list_side = tk.StringVar(value="Right")
        self.who_list_width = tk.IntVar(value=250)
        self.who_list_players = {} # Dict of {name: status}
        self.who_dock_window = None
        self.who_list_monitor = None
        self.game_time_mode_24h = tk.BooleanVar(value=True)
        
        # --- Chat Filtering State ---
        self.filters_enabled = tk.BooleanVar(value=True)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh_comms_view())
        self.filter_data = {}    # {Category: [keywords]}
        self.filter_vars = {}    # {Category: BooleanVar}
        self.pill_buttons = {}   # {Category: Button}
        self.load_filters()

        self.load_settings()
        
        # Initialize centralized logging with user preference
        setup_logging(self.debug_enabled.get())
        
        # --- State ---
        self.target_pid = None
        self.pm_obj = None
        self.char_name = "Unknown"
        self.main_hwnd = None
        self.is_running = True
        self.pk_frame = None
        self.alert_active = False
        self.comms_mode = "live" # 'live' or 'history'
        # Initialize GPS with fallback logic
        dataset_p = resource_path("settings/meridian_rooms_dataset.json")
        self.gps_manager = GPSManager(dataset_path=dataset_p)
        self.waiting_overlay = None
        
        # --- Lifecycle State ---
        self.initial_sync_done = False
        
        # --- Lifecycle Manager ---
        self.lifecycle = InstanceManager(
            on_connect_cb=self.on_game_connect,
            on_disconnect_cb=self.on_game_disconnect,
            on_multiple_found=self.show_instance_selection_ui
        )
        
        # Patterns & Subtraction List
        self.re_speech = RE_SPEECH
        self.re_bank_total = RE_BANK_TOTAL
        self.re_bank_withdraw = RE_BANK_WITHDRAW
        self.combat_verbs = {
            "wounds", "damages", "slays", "burns", "sears", "disfigures", "dissolves",
            "incinerates", "scorches", "chars", "singes", "electrocutes", "fries",
            "shocks", "jolts", "freezes", "frosts", "chills", "cools", "purifies",
            "mortifies", "cleanses", "infuses", "corrupts", "appalls", "pollutes",
            "maligns", "flattens", "slams", "buffets", "shakes", "devours", "gnaws",
            "bites", "nips", "shreds", "rends", "rakes", "claws", "impales", "pricks",
            "stings", "irritates", "thrashes", "mangles", "pummels", "slaps", "cleaves",
            "maims", "slashes", "cuts", "brutalizes", "smashes", "crushes", "bashes",
            "runs through", "stabs", "pokes", "fells", "lacerates", "pierces", "grazes",
            "blocks", "dodges", "parries", "avoids", "nicks", "fails to damage", 
            "killed", "attacks", "misses"
        }

        self.session_kills = {"monsters": {}, "players": {}}
        self.all_time_kills = {"monsters": {}, "players": {}}
        self.last_tail = []
        self.refresh_counter = 10
        self.knowledge_cache = {}
        self.current_attributes = {}
        self.vault_data = {"barloque": [], "hungry": []}
        self.calculator = SchoolCalculator()
        self.bank_manager = BankManager()
        self.inventory_scraper = None
        self.inventory_items = []
        self.sync_in_progress = False

        # --- Session Tracking Stats ---
        self.total_improves = 0
        self.who_footer_labels = {}

        # --- Layout ---
        self.status_var = tk.StringVar(value="Initializing...")
        self.status_frame = tk.Frame(self, bd=1, relief=tk.SUNKEN)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar = tk.Label(self.status_frame, textvariable=self.status_var, anchor=tk.W, padx=5)
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Container for Side Panel + Notebook
        self.main_container = tk.Frame(self)
        self.main_container.pack(fill="both", expand=True)

        self.setup_who_list_panel()

        self.notebook = DraggableNotebook(self.main_container)
        self.notebook.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        # Tab Creation
        tabs = [("Dashboard", "dash"), ("Shortcuts", "shortcuts"), ("Inventory", "inv"), ("Communications", "comms"), ("GPS", "gps"), ("Progression", "prog"), ("Vault", "vault"), ("Kill Book", "book"), ("Settings", "settings")]
        for name, key in tabs:
            f = tk.Frame(self.notebook, bg="#f0f0f0")
            setattr(self, f"tab_{key}", f)
            self.notebook.add(f, text=f" {name} ")
        
        self.setup_tab_dashboard()
        self.setup_tab_shortcuts()
        self.setup_tab_inventory()
        self.setup_tab_communications()
        self.setup_tab_gps()
        self.setup_tab_progression()
        self.setup_tab_vault()

        # Init BGF Manager
        try:
            rooms_dir, _, _ = m59_map.detect_installation()
            self.bgf_manager = m59_bgf.BGFManager(rooms_dir)
            self.bgf_manager.load_mob_mapping(resource_path("settings/moblist.csv"))
        except:
            self.bgf_manager = None
            
        self.setup_tab_book()
        self.setup_tab_settings()
        
        # Apply initial side panel state
        self.update_who_list_visibility()
        
        # Start Live Tail Polling
        self.poll_chat_log()

        self.minsize(400, 300)
        self.after(100, self.background_update_check)
        self.after(100, self.update_game_time)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def scale_px(self, px):
        """Helper to scale pixel values by the current scaling factor."""
        return int(px * self.scaling_factor)

    def hide_tooltip(self):
        """Destroys the active hover tooltip, if any."""
        tip = getattr(self, "tooltip", None)
        if tip is None:
            return
        try:
            tip.destroy()
        except tk.TclError:
            pass
        self.tooltip = None

    def set_tooltip(self, widget, text):
        """Adds a simple hover tooltip to a widget."""
        def enter(event):
            self.hide_tooltip()
            tip = tk.Toplevel(widget.winfo_toplevel())
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)

            x = event.x_root + 20
            y = event.y_root + 10
            tip.geometry(f"+{x}+{y}")

            label = tk.Label(tip, text=text, bg="#ffffca", fg="#333",
                             font=("Arial", 9), relief=tk.SOLID, borderwidth=1, padx=5, pady=2)
            label.pack()
            self.tooltip = tip

        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", lambda e: self.hide_tooltip(), add="+")
        widget.bind("<Button-1>", lambda e: self.hide_tooltip(), add="+")
        widget.bind("<Destroy>", lambda e: self.hide_tooltip(), add="+")

    def apply_ui_scaling(self):
        """Configures ttk styles for correct scaling (especially rowheight)."""
        # Rowheight is in pixels, so it MUST be scaled manually.
        # 25px is a good base for 10pt fonts at 96 DPI.
        row_h = self.scale_px(25)
        
        # Font sizes in points (positive) are auto-scaled by Tkinter internally 
        # when 'tk scaling' is set. Manual scaling here causes "double-scaling".
        header_font = ("Arial", 10, "bold")
        cell_font = ("Arial", 10)
        
        self.style.configure("Treeview", rowheight=row_h, font=cell_font)
        self.style.configure("Treeview.Heading", font=header_font)
        
        logger.debug(f"UI: Applied Treeview scaling (rowheight={row_h}, font=10pt)")

    def load_filters(self):
        """Loads filter definitions from m59_filters.json and initializes Show All."""
        # Ensure 'Show All' is always the primary state
        self.filter_vars["Show All"] = tk.BooleanVar(value=True)
        
        # Check local directory first, then fallback to bundled assets
        p = "settings/m59_filters.json"
        if not os.path.exists(p):
            p = resource_path("settings/m59_filters.json")

        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    self.filter_data = json.load(f)
                    for cat in self.filter_data:
                        if cat != "Show All":
                            # Default specific categories to False
                            self.filter_vars[cat] = tk.BooleanVar(value=False)
            except Exception as e:
                logger.error(f"Failed to load filters: {e}")

    def setup_tab_shortcuts(self):
        self.commalias_tab = m59_commalias.CommaliasTab(self.tab_shortcuts, self)
        self.commalias_tab.pack(fill="both", expand=True)

    def setup_tab_inventory(self):
        """Creates the real-time Inventory list tab with Weight and Bulk metrics."""
        cont = tk.Frame(self.tab_inv, bg="#f0f0f0")
        cont.pack(fill="both", expand=True, padx=10, pady=10)

        # --- TOP SECTION: Primary Saturation Meter ---
        sat_frame = tk.Frame(cont, bg="#f0f0f0")
        sat_frame.pack(fill="x", pady=(0, 5))
        tk.Label(sat_frame, text="TOTAL INVENTORY SATURATION", font=("Arial", 10, "bold"), bg="#f0f0f0", fg="#333").pack(anchor="w")
        self.sat_bar_canvas = tk.Canvas(sat_frame, height=self.scale_px(18), bg="#ddd", highlightthickness=0)
        self.sat_bar_canvas.pack(fill="x", pady=2)
        self.sat_lbl = tk.Label(sat_frame, text="Current Load: 0%", font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#555")
        self.sat_lbl.pack(anchor="w")

        # --- MIDDLE SECTION: Detailed Metrics ---
        metrics_frame = tk.Frame(cont, bg="#f0f0f0")
        metrics_frame.pack(fill="x", pady=(10, 10))
        
        # Weight Metric (Left)
        w_frame = tk.Frame(metrics_frame, bg="#f0f0f0")
        w_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tk.Label(w_frame, text="Weight Load", font=("Arial", 8, "bold"), bg="#f0f0f0", fg="#666").pack(anchor="w")
        self.weight_bar_canvas = tk.Canvas(w_frame, height=self.scale_px(8), bg="#eee", highlightthickness=0)
        self.weight_bar_canvas.pack(fill="x", pady=1)
        self.weight_lbl = tk.Label(w_frame, text="0 / 0", font=("Arial", 8), bg="#f0f0f0", fg="#777")
        self.weight_lbl.pack(anchor="w")

        # Bulk Metric (Right)
        b_frame = tk.Frame(metrics_frame, bg="#f0f0f0")
        b_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        tk.Label(b_frame, text="Bulk Volume", font=("Arial", 8, "bold"), bg="#f0f0f0", fg="#666").pack(anchor="w")
        self.bulk_bar_canvas = tk.Canvas(b_frame, height=self.scale_px(8), bg="#eee", highlightthickness=0)
        self.bulk_bar_canvas.pack(fill="x", pady=1)
        self.bulk_lbl = tk.Label(b_frame, text="0 / 0", font=("Arial", 8), bg="#f0f0f0", fg="#777")
        self.bulk_lbl.pack(anchor="w")

        # --- BOTTOM SECTION: Item List ---
        list_label = tk.Label(cont, text="CARRIED ITEMS", font=("Arial", 9, "bold"), bg="#f0f0f0", fg="#333")
        list_label.pack(anchor="w", pady=(10, 5))

        # Treeview for Inventory with W/B columns
        self.inv_tree = ttk.Treeview(cont, columns=("Name", "Qty", "W", "B"), show="headings", height=15)
        self.inv_tree.heading("Name", text="Item Name")
        self.inv_tree.heading("Qty", text="Qty")
        self.inv_tree.heading("W", text="W")
        self.inv_tree.heading("B", text="B")

        self.inv_tree.column("Name", width=self.scale_px(250), anchor="w")
        self.inv_tree.column("Qty", width=self.scale_px(60), anchor="center")
        self.inv_tree.column("W", width=self.scale_px(40), anchor="center")
        self.inv_tree.column("B", width=self.scale_px(40), anchor="center")

        self.inv_tree.pack(fill="both", expand=True)

        # Scrollbar
        sb = ttk.Scrollbar(cont, orient="vertical", command=self.inv_tree.yview)
        sb.pack(side="right", fill="y")
        self.inv_tree.configure(yscrollcommand=sb.set)

    def update_inventory_ui(self, weight, bulk, w_perc, b_perc, max_cap, detailed_items):
        """Updates the metrics bars and the item list."""
        def draw_bar(canvas, perc, h_override=None):
            canvas.update_idletasks()
            w = canvas.winfo_width()
            h = h_override if h_override else canvas.winfo_height()
            canvas.delete("all")

            # Colors: Green -> Yellow (80%) -> Red (95%)
            color = "#4CAF50"
            if perc > 95: color = "#F44336"
            elif perc > 80: color = "#FFC107"

            fill_w = (min(100, perc) / 100.0) * w
            canvas.create_rectangle(0, 0, fill_w, h, fill=color, outline="")

        # 1. Primary Saturation (the dominant limit)
        sat_perc = max(w_perc, b_perc)
        draw_bar(self.sat_bar_canvas, sat_perc)
        self.sat_lbl.config(text=f"Current Load: {sat_perc:.1f}%")
        
        # Update Dock Footer Saturation
        if hasattr(self, 'dock_inv_lbl'):
            self.dock_inv_lbl.config(text=f"{sat_perc:.1f}%")
        if hasattr(self, 'dock_inv_canvas'):
            draw_bar(self.dock_inv_canvas, sat_perc, h_override=self.scale_px(4))

        # 2. Detailed Bars
        draw_bar(self.weight_bar_canvas, w_perc)
        draw_bar(self.bulk_bar_canvas, b_perc)
        self.weight_lbl.config(text=f"{int(weight):,} / {max_cap:,} ({w_perc:.1f}%)")
        self.bulk_lbl.config(text=f"{int(bulk):,} / {max_cap:,} ({b_perc:.1f}%)")

        # 3. Update Tree
        for i in self.inv_tree.get_children():
            self.inv_tree.delete(i)

        for item in detailed_items:
            # handle 'qty' key from inventory.process_inventory
            q = item.get('qty', 1)
            qty_disp = f"x{q}" if q > 1 or q == 0 else ""
            self.inv_tree.insert("", "end", values=(item['name'], qty_disp, item['weight'], item['bulk']))

    def poll_inventory(self):
        """Background thread to poll inventory every 3 seconds using inventory.py logic."""
        if not self.is_running: return

        if self.inventory_scraper and self.target_pid:
            try:
                # 1. Get raw items using the robust pymem scraper
                raw_items = self.inventory_scraper.scan_inventory()
                if raw_items is not None:
                    # 2. Map for inventory.process_inventory
                    # Needs 'id', 'name', 'amount'
                    # Fix: If qty is 0, it means it's a single item (non-stackable). Treat as 1.
                    calc_items = []
                    for i in raw_items:
                        qty = i['qty'] if i['qty'] > 0 else 1
                        calc_items.append({'id': '0', 'name': i['name'], 'amount': qty})
                    
                    # 3. Process using logic from inventory.py
                    weight, bulk, detailed, unknowns = inventory.process_inventory(calc_items)
                    
                    # 4. Calculate Max Capacity based on Live Might stat
                    # Formula: 1700 (Base) + (Might * 20)
                    might = self.current_attributes.get("Might", 25)
                    max_cap = 1700 + (int(might) * 20)
                    
                    # 5. Percentages
                    w_perc = (weight / max_cap) * 100 if max_cap > 0 else 0
                    b_perc = (bulk / max_cap) * 100 if max_cap > 0 else 0
                    
                    # Update UI
                    self.after(0, lambda: self.update_inventory_ui(weight, bulk, w_perc, b_perc, max_cap, detailed))
            except Exception as e:
                logger.error(f"Inventory poll error: {e}")


        # Poll every 3 seconds
        self.after(3000, self.poll_inventory)


    def setup_tab_communications(self):
        paned = ttk.PanedWindow(self.tab_comms, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        sidebar = tk.Frame(paned, bg="#f0f0f0")
        paned.add(sidebar, weight=1)
        
        # --- Sidebar Header ---
        tk.Label(sidebar, text=" CHAT LOGS ", font=("Arial", 9, "bold"), bg="#ddd").pack(fill="x", pady=(0, 5))
        
        # Return to Live Button
        self.live_feed_btn = tk.Button(sidebar, text=" 🟢 LIVE STREAM ", command=self.return_to_live,
                                       bg="#E8F5E9", font=("Arial", 8, "bold"), pady=8)
        self.live_feed_btn.pack(fill="x", padx=5, pady=5)

        # Scrollable Listbox for logs
        list_f = tk.Frame(sidebar, bg="#f0f0f0")
        list_f.pack(fill="both", expand=True, padx=5, pady=(10, 0))
        
        self.log_file_list = tk.Listbox(list_f, font=("Arial", 9), height=15)
        self.log_file_list.pack(side="left", fill="both", expand=True)
        self.log_file_list.bind("<<ListboxSelect>>", self.load_historical_log)
        
        sb = ttk.Scrollbar(list_f, orient="vertical", command=self.log_file_list.yview)
        sb.pack(side="right", fill="y")
        self.log_file_list.config(yscrollcommand=sb.set)
        
        btn_row = tk.Frame(sidebar, bg="#f0f0f0")
        btn_row.pack(fill="x", padx=5, pady=5)
        tk.Button(btn_row, text="Refresh", command=self.refresh_log_list, font=("Arial", 8)).pack(side="left", fill="x", expand=True)
        tk.Button(btn_row, text="Folder", command=lambda: os.startfile(os.path.abspath("settings")),
                  font=("Arial", 8)).pack(side="left", fill="x", expand=True, padx=2)
        
        right_frame = tk.Frame(paned, bg="#f0f0f0")
        paned.add(right_frame, weight=4)

        # --- SMART CHAT RIBBON ---
        self.ribbon_frame = tk.Frame(right_frame, bg="#e0e0e0", pady=2)
        self.ribbon_frame.pack(fill="x", padx=5, pady=(0, 5))
        
        self.pills_container = tk.Frame(self.ribbon_frame, bg="#e0e0e0")
        self.pills_container.pack(side="left", fill="x", expand=True)
        
        self.render_ribbon_pills()
        
        # Add Filter Button
        tk.Button(self.ribbon_frame, text=" + ", font=("Arial", 9, "bold"), bg="#4CAF50", fg="white", 
                  relief=tk.FLAT, command=self.show_add_filter_dialog).pack(side="left", padx=5)

        # Quick Search
        search_f = tk.Frame(self.ribbon_frame, bg="#e0e0e0")
        search_f.pack(side="right", padx=10)
        tk.Label(search_f, text="🔍", bg="#e0e0e0").pack(side="left")
        tk.Entry(search_f, textvariable=self.search_var, width=20).pack(side="left", padx=5)

        self.comms_header_lbl = tk.Label(right_frame, text="🟢 LIVE STREAM", font=("Arial", 11, "bold"), fg="#2E7D32", bg="#f0f0f0")
        self.comms_header_lbl.pack(pady=2)
        
        self.comms_view = scrolledtext.ScrolledText(right_frame, bg="black", fg="#00FFFF", font=("Consolas", 10), state="disabled")
        self.comms_view.pack(fill="both", expand=True, padx=5, pady=5)

    def render_ribbon_pills(self):
        """Dynamic rendering of toggleable pills in the ribbon."""
        for widget in self.pills_container.winfo_children():
            widget.destroy()
        
        self.pill_buttons = {}
        
        # 1. THE "ALL" PILL
        all_state = self.filter_vars.get("Show All")
        btn = tk.Button(self.pills_container, text=" ALL ", font=("Arial", 8, "bold"),
                        relief=tk.FLAT, padx=10,
                        command=lambda: self.toggle_filter_pill("Show All"))
        btn.pack(side="left", padx=2)
        self.pill_buttons["Show All"] = btn
        
        # 2. DYNAMIC CATEGORY PILLS
        for cat in sorted(self.filter_data.keys()):
            if cat == "Show All": continue
            
            p_frame = tk.Frame(self.pills_container, bg="#e0e0e0")
            p_frame.pack(side="left", padx=2)
            
            btn = tk.Button(p_frame, text=f" {cat} ", font=("Arial", 8),
                            relief=tk.FLAT, padx=8,
                            command=lambda c=cat: self.toggle_filter_pill(c))
            btn.pack(side="left")
            self.pill_buttons[cat] = btn
            
            # Delete button for custom filters
            del_btn = tk.Button(p_frame, text="×", font=("Arial", 8, "bold"),
                                fg="#888", bg="#e0e0e0", relief=tk.FLAT, bd=0,
                                command=lambda c=cat: self.delete_filter_category(c))
            del_btn.pack(side="left")

        self.update_pill_visuals()

    def toggle_filter_pill(self, cat):
        """Smart toggle logic for pills."""
        if cat == "Show All":
            # Reset everything
            self.filter_vars["Show All"].set(True)
            for c, var in self.filter_vars.items():
                if c != "Show All": var.set(False)
        else:
            # Unset ALL if a specific category is picked
            self.filter_vars["Show All"].set(False)
            current = self.filter_vars[cat].get()
            self.filter_vars[cat].set(not current)
            
            # If nothing is selected now, return to ALL
            any_active = any(v.get() for k, v in self.filter_vars.items() if k != "Show All")
            if not any_active:
                self.filter_vars["Show All"].set(True)

        self.update_pill_visuals()
        self.refresh_comms_view()

    def update_pill_visuals(self):
        """Applies coloring to pills based on active state."""
        for cat, btn in self.pill_buttons.items():
            if self.filter_vars[cat].get():
                btn.config(bg="#2196F3", fg="white") # Active Blue
            else:
                btn.config(bg="#ccc", fg="#333")    # Inactive Grey

    def show_add_filter_dialog(self):
        """Popup with multi-line rule entry."""
        popup = tk.Toplevel(self)
        popup.title("Add Chat Filter")
        popup.geometry("400x450")
        popup.attributes("-topmost", True)
        popup.grab_set()

        tk.Label(popup, text="Filter Name:", font=("Arial", 9, "bold")).pack(pady=(10, 0))
        name_entry = tk.Entry(popup, width=30)
        name_entry.pack(pady=5)
        name_entry.focus_set()

        tk.Label(popup, text="Keywords / Rules (One per line):", font=("Arial", 9, "bold")).pack(pady=(10, 0))
        rules_text = tk.Text(popup, width=40, height=15)
        rules_text.pack(padx=20, pady=5)
        tk.Label(popup, text="Matches are case-insensitive. Use {*} for wildcards.", font=("Arial", 8, "italic"), fg="#888").pack()

        def save():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Error", "Please provide a name.", parent=popup)
                return
            
            raw_rules = rules_text.get("1.0", tk.END).splitlines()
            rules = [r.strip() for r in raw_rules if r.strip()]
            
            if not rules:
                messagebox.showerror("Error", "Please provide at least one rule.", parent=popup)
                return

            self.filter_data[name] = rules
            self.filter_vars[name] = tk.BooleanVar(value=True)
            # Switch to the new filter immediately
            self.toggle_filter_pill(name)
            
            # Persist and refresh UI
            self.save_filters_to_disk()
            self.render_ribbon_pills()
            popup.destroy()

        btn_f = tk.Frame(popup)
        btn_f.pack(fill="x", pady=20)
        tk.Button(btn_f, text=" CANCEL ", command=popup.destroy).pack(side="left", padx=40)
        tk.Button(btn_f, text=" SAVE FILTER ", bg="#4CAF50", fg="white", font=("Arial", 9, "bold"), command=save).pack(side="right", padx=40)

    def delete_filter_category(self, cat):
        if messagebox.askyesno("Delete", f"Permanently delete filter '{cat}'?"):
            self.filter_data.pop(cat, None)
            self.filter_vars.pop(cat, None)
            self.pill_buttons.pop(cat, None)
            
            # Default back to ALL if we deleted an active filter
            if not any(v.get() for k, v in self.filter_vars.items()):
                self.filter_vars["Show All"].set(True)

            self.save_filters_to_disk()
            self.render_ribbon_pills()
            self.refresh_comms_view()

    def save_filters_to_disk(self):
        """Saves dynamic filters back to m59_filters.json."""
        try:
            with open("settings/m59_filters.json", "w") as f:
                json.dump(self.filter_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save filters: {e}")

    def is_line_filtered(self, line):
        """Returns True if the line should be shown based on inclusive OR logic + Search."""
        if not self.filters_enabled.get():
            return False

        line_lower = line.lower()
        
        # 1. Check Search Bar (Global constraint)
        search_term = self.search_var.get().lower()
        if search_term and search_term not in line_lower:
            return False

        # 2. Check "Show All" override
        if self.filter_vars.get("Show All") and self.filter_vars["Show All"].get():
            return True
        
        # 3. Check active categories (Inclusive OR)
        for cat, var in self.filter_vars.items():
            if cat == "Show All": continue
            if var.get():
                keywords = self.filter_data.get(cat, [])
                for kw in keywords:
                    kw_lower = kw.lower()
                    if "{*}" in kw_lower:
                        # Convert wildcard to regex: escape specials, then replace {*} with .*?
                        pattern = re.escape(kw_lower).replace(r"\{\*\}", ".*?")
                        if re.search(pattern, line_lower):
                            return True
                    elif kw_lower in line_lower:
                        # Fast literal match
                        return True
        
        return False

    def refresh_comms_view(self):
        """Instant UI re-render triggered by filter toggles. High-performance batch insertion."""
        # Determine target file
        if self.comms_mode == "live":
            if self.char_name == "Unknown": return
            safe_n = get_safe_name(self.char_name)
            path = os.path.join("settings", f"{safe_n}_chat.log")
        else:
            selection = self.log_file_list.curselection()
            if not selection: return
            path = os.path.join("settings", self.log_file_list.get(selection[0]))

        if not os.path.exists(path): return

        try:
            # Optimized read: grab last ~2000 lines for instant feedback
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                # Read large block from end for speed
                f.seek(0, os.SEEK_END)
                size = f.tell()
                # Read up to 256KB or entire file
                read_size = min(size, 256 * 1024)
                f.seek(size - read_size)
                lines = f.readlines()
                # If we read a partial first line, drop it
                if len(lines) > 1 and size > read_size:
                    lines = lines[1:]

            # Filter lines in memory
            to_insert = [l for l in lines if self.is_line_filtered(l)]

            # Batch update UI
            self.comms_view.config(state="normal")
            self.comms_view.delete("1.0", tk.END)
            self.comms_view.insert(tk.END, "".join(to_insert))
            self.comms_view.see(tk.END)
            self.comms_view.config(state="disabled")
            
            # Reset the live pointer to the end of the file so tailing continues correctly
            if self.comms_mode == "live":
                self._log_ptr = size

        except Exception as e:
            logger.error(f"Refresh Error: {e}")
    def is_combat_line(self, line):
        """Internal helper for combat tracking; separate from UI filtering."""
        l = line.lower()
        
        # 1. Explicit Kill Check (Highest Priority)
        if l.startswith("you killed "):
            return True
            
        # 2. Verb-based combat detection
        for verb in self.combat_verbs:
            if f" {verb} " in l or l.endswith(f" {verb}."):
                return True
        
        # 3. Defensive/Miss detection
        if l.startswith("you ") and any(v in l for v in ["block", "dodge", "parry", "avoid", "resist", "evade"]):
            return True
        
        # 4. Incoming hit/miss pattern support
        if " you with " in l or "'s attack" in l:
            return True
            
        return False

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    s = json.load(f)
                    if s.get("geometry"):
                        self.geometry(s["geometry"])
                    self.pk_alert_enabled.set(s.get("pk_alert_enabled", True))
                    self.pk_sound_enabled.set(s.get("pk_sound_enabled", True))
                    self.pk_frame_enabled.set(s.get("pk_frame_enabled", True))
                    self.pk_sound_path.set(s.get("pk_sound_path", "SystemExclamation"))
                    self.tell_sound_enabled.set(s.get("tell_sound_enabled", True))
                    self.tell_sound_path.set(s.get("tell_sound_path", "sound/dm_chime.wav"))
                    self.elusion_phrase.set(s.get("elusion_phrase", 'say "I wish to travel to {loc}."'))
                    self.elusion_geometry.set(s.get("elusion_geometry", "320x35+100+100"))
                    self.guildhall_name.set(s.get("guildhall_name", ""))
                    self.custom_elusion_phrases = s.get("custom_elusion_phrases", [])
                    self.debug_enabled.set(s.get("debug_enabled", False))
                    self.who_list_side.set(s.get("who_list_side", "Right"))
                    self.who_list_width.set(s.get("who_list_width", 250))
                    self.game_time_mode_24h.set(s.get("game_time_mode_24h", True))
                    
                    # Force Who List to be in-app on startup (don't remember desktop dock)
                    self.who_list_docked.set(False)
                    
                    # Restore Filters Enabled State
                    self.filters_enabled.set(s.get("filters_enabled", True))
                    
                    # Restore Filter Category States
                    fs = s.get("filter_states", {})
                    for cat, val in fs.items():
                        if cat in self.filter_vars:
                            self.filter_vars[cat].set(val)
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")

    def save_settings(self):
        try:
            # Prepare filter states for JSON
            fs_save = {cat: var.get() for cat, var in self.filter_vars.items()}
            
            with open(SETTINGS_FILE, "w") as f:
                json.dump({
                    "geometry": self.geometry(),
                    "pk_alert_enabled": self.pk_alert_enabled.get(),
                    "pk_sound_enabled": self.pk_sound_enabled.get(),
                    "pk_frame_enabled": self.pk_frame_enabled.get(),
                    "pk_sound_path": self.pk_sound_path.get(),
                    "tell_sound_enabled": self.tell_sound_enabled.get(),
                    "tell_sound_path": self.tell_sound_path.get(),
                    "elusion_phrase": self.elusion_phrase.get(),
                    "elusion_geometry": self.elusion_geometry.get(),
                    "guildhall_name": self.guildhall_name.get(),
                    "custom_elusion_phrases": self.custom_elusion_phrases,
                    "debug_enabled": self.debug_enabled.get(),
                    "who_list_docked": self.who_list_docked.get(),
                    "who_list_side": self.who_list_side.get(),
                    "game_time_mode_24h": self.game_time_mode_24h.get(),
                    "filters_enabled": self.filters_enabled.get(),
                    "filter_states": fs_save
                }, f)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def debug_log(self, category, message):
        """Wrapper for centralized logging, keeping the legacy category-based signature."""
        logger.debug(f"[{category}] {message}")

    def gps_log(self, message):
        if self.debug_enabled.get():
            self.debug_log("GPS", message)

    def setup_who_list_panel(self, parent=None):
        # Cleanup existing panel if it exists
        self.hide_tooltip()
        if hasattr(self, "who_list_panel") and self.who_list_panel:
            try: self.who_list_panel.destroy()
            except: pass

        # Use main_container if no parent is provided
        target_parent = parent if parent else self.main_container
        
        # Outer container to hold the resize handle and the content
        self.who_list_outer = tk.Frame(target_parent, bg="#1e1f22", bd=0)
        if parent:
            self.who_list_outer.pack(fill="both", expand=True)

        # RESIZE HANDLE (Draggable line)
        if self.who_list_docked.get():
            self.resize_handle = tk.Frame(self.who_list_outer, bg="#323338", width=4, cursor="sb_h_double_arrow")
            self.resize_handle.pack(side="left", fill="y")
            
            def start_resize(event):
                self._drag_start_x = event.x_root
                self._start_width = self.who_list_width.get()

            def perform_resize(event):
                dx = self._drag_start_x - event.x_root
                new_w = self._start_width + dx
                new_w = max(180, min(600, new_w)) # Hard limits
                self.who_list_width.set(new_w)
                self.update_appbar_pos(new_w)
                
            self.resize_handle.bind("<Button-1>", start_resize)
            self.resize_handle.bind("<B1-Motion>", perform_resize)
            self.resize_handle.bind("<ButtonRelease-1>", lambda e: self.save_settings())

        # Premium dark slate themed container
        self.who_list_panel = tk.Frame(self.who_list_outer, bg="#2b2d31", bd=1, relief=tk.SOLID)
        self.who_list_panel.pack(side="left", fill="both", expand=True)
        
        # Polished Title Header
        self.who_list_header = tk.Frame(self.who_list_panel, bg="#1e1f22")
        self.who_list_header.pack(fill="x", side="top")
        
        tk.Label(
            self.who_list_header, text="M59 Companion", font=("Segoe UI", 10, "bold"), 
            bg="#1e1f22", fg="#4CAF50", pady=7, bd=0
        ).pack(side="left", padx=10)
        
        # Game Time Row
        self.time_frame = tk.Frame(self.who_list_panel, bg="#1e1f22")
        self.time_frame.pack(fill="x", side="top")
        
        self.game_time_lbl = tk.Label(
            self.time_frame, text="Game Time: --:--:--", font=("Segoe UI", 9),
            bg="#1e1f22", fg="#e0e0e0"
        )
        self.game_time_lbl.pack(side="left", padx=10, pady=2)
        
        self.game_time_toggle_btn = tk.Button(
            self.time_frame, text="12/24", font=("Segoe UI", 8, "bold"),
            bg="#323338", fg="#fff", activebackground="#2b2d31", activeforeground="#fff",
            bd=0, padx=5, pady=1, cursor="hand2", command=self.toggle_game_time_mode
        )
        self.game_time_toggle_btn.pack(side="right", padx=10, pady=2)

        # Separator under Game Time
        tk.Frame(self.who_list_panel, height=1, bg="#323338").pack(fill="x", side="top")

        # Who's Online Label
        tk.Label(
            self.who_list_panel, text="[Who's Online]", font=("Segoe UI", 9, "bold"),
            bg="#2b2d31", fg="#888", anchor="w"
        ).pack(fill="x", side="top", padx=10, pady=(5, 0))
        
        # Dock/Toggle Button
        dock_text = "↙" if self.who_list_docked.get() else "↗"
        self.who_dock_btn = tk.Button(
            self.who_list_header, text=dock_text, font=("Segoe UI", 12, "bold"),
            bg="#1e1f22", fg="#888", activebackground="#323338", activeforeground="#fff",
            bd=0, padx=10, cursor="hand2", command=self.toggle_who_list_dock
        )
        self.who_dock_btn.pack(side="right")
        self.who_dock_btn.bind("<Enter>", lambda e: self.who_dock_btn.config(bg="#323338", fg="#fff"), add="+")
        self.who_dock_btn.bind("<Leave>", lambda e: self.who_dock_btn.config(bg="#1e1f22", fg="#888"), add="+")
        
        tip_text = "Return to Application" if self.who_list_docked.get() else "Pop out to Desktop Dock"
        self.set_tooltip(self.who_dock_btn, tip_text)

        # 1. BOTTOM SECTION (Pack these first to pin to bottom)
        self.who_list_count_lbl = tk.Label(
            self.who_list_panel, text="0 Online", font=("Segoe UI", 9, "bold"), 
            bg="#1e1f22", fg="#888", pady=5, bd=0
        )
        self.who_list_count_lbl.pack(side="bottom", fill="x")

        # Separator above dynamic player count
        tk.Frame(self.who_list_panel, height=1, bg="#323338").pack(side="bottom", fill="x")

        # Status Footer
        footer_bg = "#1e1f22"
        self.who_footer = tk.Frame(self.who_list_panel, bg=footer_bg, bd=0)
        self.who_footer.pack(side="bottom", fill="x")
        
        # 1. GPS Header Row (Centered)
        gps_header = tk.Label(
            self.who_footer, text="🧭 GPS NAVIGATION", font=("Segoe UI", 8, "bold"), 
            bg=footer_bg, fg="#888", pady=5
        )
        gps_header.pack(fill="x")
        
        wrap = self.who_list_width.get() - self.scale_px(40)

        # 2. CURRENT LOCATION (Dynamic)
        self.gps_who_loc_lbl = tk.Label(
            self.who_footer, text="Unknown Location", font=("Segoe UI", 9, "bold"),
            bg=footer_bg, fg="#4CAF50", wraplength=wrap, justify="center"
        )
        self.gps_who_loc_lbl.pack(fill="x", pady=(0, 2))
        
        # 3. PVP Status Placeholder
        self.pvp_status_lbl = tk.Label(
            self.who_footer, text="Standard PVP", font=("Segoe UI", 8),
            bg=footer_bg, fg="#555555"
        )
        self.pvp_status_lbl.pack(fill="x", pady=(0, 5))
        self.set_tooltip(self.pvp_status_lbl, "Standard PVP")
        
        # 4. GPS Route instruction (No active route)
        self.gps_dock_lbl = tk.Label(
            self.who_footer, text="No active route", font=("Segoe UI", 8, "bold"), 
            bg=footer_bg, fg="#fff", wraplength=wrap, justify="center"
        )
        self.gps_dock_lbl.pack(fill="x", padx=10, pady=(0, 5))
        self.who_footer_labels["gps"] = self.gps_dock_lbl
        
        # Subtle Divider
        tk.Frame(self.who_footer, height=1, bg="#323338").pack(fill="x", pady=5)

        # Helper to add remaining status rows
        def add_status_row(parent, label_text, key, icon="", justify="right"):
            row = tk.Frame(parent, bg=footer_bg)
            row.pack(fill="x", padx=10, pady=2)
            tk.Label(row, text=f"{icon} {label_text}", font=("Segoe UI", 8), bg=footer_bg, fg="#888").pack(side="left")
            
            # Use current width for initial wrap
            wrap = self.who_list_width.get() - self.scale_px(80)
            val = tk.Label(row, text="---", font=("Segoe UI", 8, "bold"), bg=footer_bg, fg="#fff", wraplength=wrap, justify=justify)
            val.pack(side="right" if justify == "right" else "left", padx=(10 if justify == "left" else 0))
            self.who_footer_labels[key] = val

        add_status_row(self.who_footer, "IMPROVES:", "improves", "📈")
        add_status_row(self.who_footer, "BANK (M):", "bank_m", "💰")
        add_status_row(self.who_footer, "BANK (I):", "bank_i", "🌴")
        
        # Subtle Divider
        tk.Frame(self.who_footer, height=1, bg="#323338").pack(fill="x", pady=5)

        # 4. Inventory Saturation Row (Most Bottom)
        inv_row = tk.Frame(self.who_footer, bg=footer_bg)
        inv_row.pack(fill="x", padx=10, pady=(2, 10))
        tk.Label(inv_row, text="🎒 BAG SPACE:", font=("Segoe UI", 8), bg=footer_bg, fg="#888").pack(side="left")
        
        self.dock_inv_lbl = tk.Label(inv_row, text="0%", font=("Segoe UI", 8, "bold"), bg=footer_bg, fg="#fff")
        self.dock_inv_lbl.pack(side="right")
        self.who_footer_labels["bag"] = self.dock_inv_lbl

        self.dock_inv_canvas = tk.Canvas(self.who_footer, height=self.scale_px(4), bg="#323338", highlightthickness=0)
        self.dock_inv_canvas.pack(fill="x", padx=10, pady=(0, 10))
        
        tk.Frame(self.who_list_panel, height=1, bg="#323338").pack(side="bottom", fill="x")

        # 2. MIDDLE SECTION (Scrollable list container)
        list_frame = tk.Frame(self.who_list_panel, bg="#2b2d31")
        list_frame.pack(side="top", fill="both", expand=True)

        self.who_list_text = tk.Text(
            list_frame, bg="#2b2d31", fg="#e0e0e0", 
            font=("Consolas", 10), state="disabled", 
            width=25, bd=0, padx=8, pady=5, wrap="none"
        )
        self.who_list_text.pack(side="left", fill="both", expand=True)
        
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.who_list_text.yview)
        sb.pack(side="right", fill="y")
        self.who_list_text.config(yscrollcommand=sb.set)
        
        # High-legibility foreground tags
        self.who_list_text.tag_config("INNOCENT", foreground="#e0e0e0")
        self.who_list_text.tag_config("OUTLAW", foreground="#ff9f43")
        self.who_list_text.tag_config("MURDERER", foreground="#ff6b6b")
        self.who_list_text.tag_config("STAFF", foreground="#48dbfb")
        self.who_list_text.tag_config("CREATOR", foreground="#ffd32a")
        
        if self.who_list_players:
            self.refresh_who_list_ui()
        
        # If we have players, populate the UI immediately
        if self.who_list_players:
            self.refresh_who_list_ui()

    def update_who_list_visibility(self):
        if hasattr(self, "who_list_outer"):
            self.who_list_outer.pack_forget()
        self.notebook.pack_forget()
        
        # If docked, it shouldn't be in the main window at all
        if self.who_list_docked.get():
            self.notebook.pack(side="left", fill="both", expand=True, padx=5, pady=5)
            return

        if hasattr(self, "who_list_outer"):
            side = self.who_list_side.get().lower()
            self.who_list_outer.pack(side=side, fill="y", padx=2)
            if self.target_pid:
                self.start_who_list_monitor()
        self.notebook.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    def toggle_who_list_dock(self):
        """Toggles the Who List between an integrated panel and a desktop-docked AppBar."""
        self.hide_tooltip()
        if self.who_list_docked.get():
            # Undock
            self.unregister_appbar()
            self.who_list_docked.set(False)
            self.setup_who_list_panel() # Rebuild in main container
            self.update_who_list_visibility()
        else:
            # Dock
            self.who_list_docked.set(True)
            self.update_who_list_visibility() # Remove from main window
            self.register_appbar()

    def register_appbar(self):
        """Creates a Toplevel window and registers it as a Windows AppBar."""
        if self.who_dock_window:
            return

        logger.info("AppBar: Registering Who List as Desktop Dock...")
        
        # 1. Create the Dock Window
        dock = tk.Toplevel(self)
        dock.title("M59 Who List Dock")
        dock.overrideredirect(True)
        dock.attributes("-topmost", True)
        dock.config(bg="#2b2d31") # Match the dark theme
        self.who_dock_window = dock
        
        # 2. Add Content
        self.setup_who_list_panel(parent=dock)
        
        # 3. Ensure the window is mapped and has a valid HWND
        dock.update()
        
        # 4. Windows API Registration
        hwnd = dock.winfo_id()
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        abd.uCallbackMessage = win32con.WM_USER + 101 # Custom callback
        
        # ABM_NEW: Register the AppBar
        Shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
        
        # ABM_QUERYPOS & ABM_SETPOS: Reserve space
        # Use win32api to get physical screen size, adjusted for potential scaling issues
        screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        
        dock_w = self.who_list_width.get()
        
        abd.uEdge = ABE_RIGHT
        abd.rc.left = screen_w - dock_w
        abd.rc.right = screen_w
        abd.rc.top = 0
        abd.rc.bottom = screen_h
        
        logger.debug(f"AppBar: Requesting Right edge: L={abd.rc.left}, R={abd.rc.right}, T={abd.rc.top}, B={abd.rc.bottom} (Screen: {screen_w}x{screen_h})")

        # Ask Windows for the position
        Shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        
        # Actually set the position
        Shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        
        # Apply the final geometry to the Tkinter window
        final_w = abd.rc.right - abd.rc.left
        final_h = abd.rc.bottom - abd.rc.top
        
        # Log the final values Windows gave us
        logger.info(f"AppBar: System Reserved: L={abd.rc.left}, R={abd.rc.right}, T={abd.rc.top}, B={abd.rc.bottom} (W={final_w})")
        
        dock.geometry(f"{final_w}x{final_h}+{abd.rc.left}+{abd.rc.top}")
        
        # Force a refresh of the UI inside the dock
        self.refresh_who_list_ui()

    def unregister_appbar(self):
        """Unregisters the AppBar and cleans up the dock window."""
        if not self.who_dock_window:
            return
            
        logger.info("AppBar: Unregistering Desktop Dock...")
        hwnd = self.who_dock_window.winfo_id()
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        
        # ABM_REMOVE: Release desktop space
        Shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
        
        self.who_dock_window.destroy()
        self.who_dock_window = None

    def safe_refresh_who_list(self):
        """Sends a /who command to the game safely using Windows messages."""
        if not self.main_hwnd:
            return
            
        logger.debug("WhoList: Triggering safe refresh via /who command.")
        edit_hwnd = find_nested_control(self.main_hwnd, 1001)
        if not edit_hwnd:
            logger.debug("WhoList: Chat edit control (1001) not found.")
            return
        
        cmd = "/who\r"
        for char in cmd:
            win32gui.SendMessage(edit_hwnd, win32con.WM_CHAR, ord(char), 0)

    def start_who_list_monitor(self):
        """Initializes WhoList monitor using the modular WhoListMonitor class."""
        if not self.target_pid:
            return
            
        if self.who_list_monitor:
            return 
            
        self.who_list_monitor = WhoListMonitor(
            target_pid=self.target_pid,
            on_update_callback=self.on_who_list_update
        )
        self.who_list_monitor.start()
        
        # Trigger an update after a short delay to populate initial list
        if self.char_name != "Unknown":
            self.after(1500, self.trigger_silent_who_update)

    def on_who_list_update(self, players):
        """Callback from WhoListMonitor when player list changes."""
        self.who_list_players = players
        self.after(0, self.refresh_who_list_ui)

    def trigger_silent_who_update(self):
        """Triggers the silent population update via the monitor's RPC wrapper."""
        if getattr(self, "sync_in_progress", False):
            logger.info("WhoList: Tab Dance Sync is running, deferring silent population update...")
            self.after(1500, self.trigger_silent_who_update)
            return
            
        if self.who_list_monitor:
            self.who_list_monitor.trigger_silent_update()

    def refresh_who_list_ui(self):
        self.who_list_text.config(state="normal")
        self.who_list_text.delete("1.0", tk.END)
        
        # Sort alphabetically case-insensitively
        sorted_names = sorted(self.who_list_players.keys(), key=str.lower)
        
        # 1. Text UI Update
        for name in sorted_names:
            status = self.who_list_players[name]
            self.who_list_text.insert(tk.END, f" {name}\n", status)
        self.who_list_text.config(state="disabled")
        
        # 2. Update Footer & Wraplength
        # Use current static width for wraplength
        current_w = self.who_list_width.get()
        for lbl in self.who_footer_labels.values():
            lbl.config(wraplength=current_w - self.scale_px(40))
        if hasattr(self, "gps_who_loc_lbl") and self.gps_who_loc_lbl:
            self.gps_who_loc_lbl.config(wraplength=current_w - self.scale_px(40))
            
        self.refresh_who_footer()

        # Update dynamic player count at the bottom
        count = len(sorted_names)
        self.who_list_count_lbl.config(text=f"{count} Online", fg="#4CAF50" if count > 0 else "#888")

    def refresh_who_footer(self):
        """Updates the status footer labels with the latest session data."""
        if not self.who_footer_labels:
            return

        if hasattr(self, "gps_who_loc_lbl") and hasattr(self, "gps_current_loc_lbl"):
            loc_val = self.gps_current_loc_lbl.cget("text")
            self.gps_who_loc_lbl.config(text=loc_val)
            
            if hasattr(self, "pvp_status_lbl"):
                if loc_val == "Unknown Location":
                    self.pvp_status_lbl.config(text="Unknown Location", fg="#555555")
                    self.set_tooltip(self.pvp_status_lbl, "Location not known")
                else:
                    rid = self.gps_manager.resolve_name_to_rid(loc_val)
                    pvp_status = self.gps_manager.dataset.get(rid, {}).get("pvp_status", "Standard PVP") if rid else "Standard PVP"
                    
                    if pvp_status == "Safe (No PVP)":
                        color = "#4CAF50" # green
                    elif pvp_status == "Arena (No Death Penalty)":
                        color = "#FF9800" # orange
                    else:
                        color = "#f44336" # red
                        
                    raw_flags = self.gps_manager.dataset.get(rid, {}).get("raw_flags", "") if rid else ""
                    if "ROOM_SAFELOGOFF" in raw_flags:
                        display_text = f"{pvp_status} (Safe Logoff)"
                    else:
                        display_text = f"{pvp_status} (Unsafe Logoff)"
                        
                    self.pvp_status_lbl.config(text=display_text, fg=color)
                    tooltip_text = f"Flags: {raw_flags}" if raw_flags else pvp_status
                    self.set_tooltip(self.pvp_status_lbl, tooltip_text)

        # GPS Status
        gps_text = "No active route"
        if self.gps_manager.current_path and self.gps_manager.current_destination_rid:
            step_idx = self.gps_manager.current_step_index
            total_steps = len(self.gps_manager.current_path)
            if step_idx < total_steps:
                from_rid, exit_info = self.gps_manager.current_path[step_idx]
                
                # Get the arrival point for THIS room to calculate relative direction
                arrival_pos = None
                if step_idx == 0:
                    # First room, use its teleport point as baseline
                    arrival_pos = self.gps_manager.dataset.get(from_rid, {}).get('teleport')
                else:
                    # Previous step's destination is our current entry point
                    prev_rid, prev_exit = self.gps_manager.current_path[step_idx-1]
                    arrival_pos = prev_exit.get('to_pos')

                gps_text = self.gps_manager.get_friendly_instruction(
                    from_rid, exit_info, step=step_idx+1, total=total_steps, arrival_pos=arrival_pos
                )
        
        self.who_footer_labels["gps"].config(text=gps_text)
        self.who_footer_labels["improves"].config(text=str(self.total_improves))
        
        # Bank Balances (Direct from BankManager)
        m = self.bank_manager.balances['mainland']
        i = self.bank_manager.balances['island']
        self.who_footer_labels["bank_m"].config(text=f"{m:,}s")
        self.who_footer_labels["bank_i"].config(text=f"{i:,}s")

    def update_appbar_pos(self, new_width):
        """Resizes the AppBar reservation and the dock window."""
        if not self.who_dock_window: return
        
        hwnd = self.who_dock_window.winfo_id()
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        
        screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        
        abd.uEdge = ABE_RIGHT
        abd.rc.left = screen_w - new_width
        abd.rc.right = screen_w
        abd.rc.top = 0
        abd.rc.bottom = screen_h
        
        # Query and Set
        Shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        Shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        
        final_w = abd.rc.right - abd.rc.left
        final_h = abd.rc.bottom - abd.rc.top
        self.who_dock_window.geometry(f"{final_w}x{final_h}+{abd.rc.left}+{abd.rc.top}")

    def return_to_live(self):
        self.comms_mode = "live"
        self.comms_header_lbl.config(text="🟢 LIVE STREAM", fg="#2E7D32")
        self.live_feed_btn.config(bg="#E8F5E9") # Subtle green
        self.comms_view.config(state="normal")
        self.comms_view.delete("1.0", tk.END)
        self.comms_view.config(state="disabled")
        # Polling loop will pick up and fill current log content

    def poll_chat_log(self):
        """High-performance tail of the current chat log file."""
        if not self.is_running: return
        
        if self.comms_mode == "live" and self.char_name != "Unknown":
            safe_n = get_safe_name(self.char_name)
            log_p = os.path.join("settings", f"{safe_n}_chat.log")
            
            if os.path.exists(log_p):
                try:
                    # Initialize pointer if not set
                    if not hasattr(self, "_log_ptr"):
                        self._log_ptr = 0
                        self._last_log_p = ""

                    # Reset pointer if file changed or shrunk
                    file_size = os.path.getsize(log_p)
                    if log_p != self._last_log_p or file_size < self._log_ptr:
                        self._log_ptr = 0
                        self._last_log_p = log_p
                        self.comms_view.config(state="normal")
                        self.comms_view.delete("1.0", tk.END)
                        self.comms_view.config(state="disabled")

                    if file_size > self._log_ptr:
                        with open(log_p, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(self._log_ptr)
                            new_data = f.read()
                            if new_data:
                                self.comms_view.config(state="normal")
                                for line in new_data.splitlines():
                                    if self.is_line_filtered(line):
                                        self.comms_view.insert(tk.END, line + "\n")
                                        
                                    # Trigger alert for incoming DMs
                                    if self.tell_sound_enabled.get():
                                        if ' tells you, "' in line or ' sends, "' in line:
                                            self.play_tell_alert()
                                            
                                self.comms_view.see(tk.END)
                                self.comms_view.config(state="disabled")
                                self._log_ptr = f.tell()
                except Exception as e:
                    logger.debug(f"Tail error: {e}")
        
        # Poll every 250ms for near-instant updates
        self.after(250, self.poll_chat_log)

    def load_historical_log(self, event=None):
        selection = self.log_file_list.curselection()
        if not selection: return
        
        fn = self.log_file_list.get(selection[0])
        self.comms_mode = "history"
        self.comms_header_lbl.config(text=f"📂 HISTORY: {fn}", fg="#1565C0")
        self.live_feed_btn.config(bg="#f0f0f0") # Dim the live button
        
        path = os.path.join("settings", fn)
        try:
            self.comms_view.config(state="normal")
            self.comms_view.delete("1.0", tk.END)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if self.is_line_filtered(line):
                        self.comms_view.insert(tk.END, line)
            self.comms_view.see(tk.END)
            self.comms_view.config(state="disabled")
        except Exception as e:
            logger.error(f"Failed to load historical log {fn}: {e}")

    def append_comms_line(self, line):
        """Legacy helper for tracking; UI updates are now handled by poll_chat_log."""
        ts = f"[{datetime.now().strftime('%H:%M:%S')}]"
        if self.debug_enabled.get():
            logger.debug(f"Comms: {line[:60]}...")
        # Tracker/PKAlert still use the synchronous feed provided by the chat monitor

    def refresh_log_list(self):
        if not os.path.exists("settings"):
            os.makedirs("settings", exist_ok=True)
        files = [f for f in os.listdir("settings") if f.endswith(".log") and "debug" not in f.lower()]
        files.sort(key=lambda x: os.path.getmtime(os.path.join("settings", x)), reverse=True)
        
        self.log_file_list.delete(0, tk.END)
        for f in files:
            self.log_file_list.insert(tk.END, f)

    def setup_tab_gps(self):
        """Creates the enhanced GPS Navigation & Discovery tab."""
        # Main container with two columns
        main_cont = tk.Frame(self.tab_gps, bg="#f0f0f0")
        main_cont.pack(fill="both", expand=True)

        # --- LEFT COLUMN: Destination & Search ---
        left_col = tk.Frame(main_cont, bg="#f0f0f0", width=300)
        left_col.pack(side="left", fill="both", padx=10, pady=10)
        left_col.pack_propagate(False)

        tk.Label(left_col, text="🔍 Destination", font=("Arial", 11, "bold"), bg="#f0f0f0").pack(anchor="w")
        
        self.gps_search_var = tk.StringVar()
        self.gps_search_var.trace_add("write", lambda *a: self.filter_gps_destinations())
        search_ent = tk.Entry(left_col, textvariable=self.gps_search_var, font=("Arial", 10))
        search_ent.pack(fill="x", pady=5)
        search_ent.bind("<Return>", lambda e: self.start_navigation())
        
        # Current Location Display
        self.gps_loc_f = tk.Frame(left_col, bg="#E3F2FD", padx=5, pady=5, bd=1, relief=tk.SOLID)
        self.gps_loc_f.pack(fill="x", pady=(5, 10))
        tk.Label(self.gps_loc_f, text="📍 YOU ARE HERE:", font=("Arial", 8, "bold"), bg="#E3F2FD", fg="#1976D2").pack(anchor="w")
        self.gps_current_loc_lbl = tk.Label(self.gps_loc_f, text="Unknown", font=("Arial", 10, "bold"), bg="#E3F2FD", fg="#0D47A1", wraplength=250)
        self.gps_current_loc_lbl.pack(anchor="w")
        self.gps_loc_f.bind("<Configure>", self.on_gps_loc_resize)

        # Results List
        self.gps_dest_list = tk.Listbox(left_col, font=("Arial", 9), bg="white", selectmode="single")
        self.gps_dest_list.pack(fill="both", expand=True, pady=5)
        self.gps_dest_list.bind("<<ListboxSelect>>", self.on_gps_dest_select)
        
        btn_f = tk.Frame(left_col, bg="#f0f0f0")
        btn_f.pack(fill="x")
        
        self.gps_start_btn = tk.Button(btn_f, text="START GPS", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), 
                                       command=self.start_navigation, state="disabled")
        self.gps_start_btn.pack(side="left", fill="x", expand=True, padx=(0,2))
        
        self.gps_stop_btn = tk.Button(btn_f, text="STOP", bg="#f44336", fg="white", font=("Arial", 10, "bold"), 
                                      command=self.stop_navigation, state="disabled")
        self.gps_stop_btn.pack(side="left", fill="x", expand=True, padx=(2,0))

        # --- RIGHT COLUMN: Directions & Map ---
        right_col = tk.Frame(main_cont, bg="#f0f0f0")
        right_col.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # Current Step Banner
        step_f = tk.LabelFrame(right_col, text=" NEXT STEP ", bg="#f0f0f0", font=("Arial", 10, "bold"), fg="#1565C0")
        step_f.pack(fill="x", pady=(0, 10))
        
        self.gps_instruction_lbl = tk.Label(step_f, text="Select a destination to begin...", 
                                            font=("Arial", 14, "bold"), fg="#212121", bg="white", 
                                            wraplength=600, justify="center", height=3)
        self.gps_instruction_lbl.pack(fill="x", padx=10, pady=10)

        # Route Preview
        route_f = tk.LabelFrame(right_col, text=" Route Preview ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        route_f.pack(fill="both", expand=True)
        
        self.gps_route_view = scrolledtext.ScrolledText(route_f, font=("Consolas", 10), bg="#1e1e1e", fg="#00FF00")
        self.gps_route_view.pack(fill="both", expand=True, padx=5, pady=5)

        # --- FOOTER: Beta Disclaimer ---
        footer = tk.Frame(self.tab_gps, bg="#FFF9C4", bd=1, relief=tk.SOLID)
        footer.pack(fill="x", side="bottom", padx=10, pady=5)
        
        tk.Label(footer, text=" ⚠ BETA: GPS Navigation is under development. Map data may be incomplete.", 
                 font=("Arial", 9, "bold"), bg="#FFF9C4", fg="#F57F17").pack(side="left", padx=10, pady=5)
        
        import webbrowser
        btn = tk.Button(footer, text="Report Issue on GitHub", font=("Arial", 8, "underline"), 
                        fg="#1565C0", bg="#FFF9C4", bd=0, cursor="hand2",
                        command=lambda: webbrowser.open("https://github.com/subvhome/m59-companion/issues/new"))
        btn.pack(side="right", padx=10)

        # Initial data load
        self.gps_all_options = self.gps_manager.get_room_options()
        self.filter_gps_destinations()

    def filter_gps_destinations(self):
        """Updates the destination listbox based on search query."""
        query = self.gps_search_var.get().lower()
        self.gps_dest_list.delete(0, tk.END)
        self.gps_current_matches = []
        
        for opt in self.gps_all_options:
            if query in opt['display'].lower():
                self.gps_dest_list.insert(tk.END, opt['display'])
                self.gps_current_matches.append(opt)

    def on_gps_dest_select(self, event):
        """Handles selection of a destination from the list."""
        idx = self.gps_dest_list.curselection()
        if idx:
            self.gps_start_btn.config(state="normal")

    def start_navigation(self, target_rid=None):
        """Calculates and starts a new navigation route."""
        if target_rid is None:
            idx = self.gps_dest_list.curselection()
            if not idx: return
            target = self.gps_current_matches[idx[0]]
            target_rid = target['rid']
        
        self.gps_manager.current_destination_rid = target_rid
        
        # Resolve current location RID
        cur_name = self.get_current_room()
        start_rid = self.gps_manager.resolve_name_to_rid(cur_name)
        
        if not start_rid:
            self.gps_log(f"Error: Cannot resolve current location RID for '{cur_name}'")
            return
            
        path = self.gps_manager.find_path(start_rid, target_rid)
        if path is not None:
            self.gps_manager.current_path = path
            self.gps_manager.current_step_index = 0
            self.gps_start_btn.config(text="START GPS", state="disabled")
            self.gps_stop_btn.config(state="normal")
            self.update_gps_navigation_ui()
            logger.info(f"GPS: Started navigation to RID {target_rid}")
        else:
            self.gps_instruction_lbl.config(text="NO PATH FOUND", fg="#f44336")
            logger.error(f"GPS: No path found from {start_rid} to {target_rid}")

    def stop_navigation(self):
        """Clears navigation state."""
        self.gps_manager.current_destination_rid = None
        self.gps_manager.current_path = []
        self.gps_instruction_lbl.config(text="Select a destination to begin...", fg="#212121")
        self.gps_route_view.config(state="normal")
        self.gps_route_view.delete("1.0", tk.END)
        self.gps_route_view.config(state="disabled")
        self.gps_stop_btn.config(state="disabled")
        self.gps_start_btn.config(text="START GPS", state="normal")

    def update_gps_navigation_ui(self):
        """Updates the labels and path preview for active navigation."""
        path = self.gps_manager.current_path
        step_idx = self.gps_manager.current_step_index
        
        self.gps_route_view.config(state="normal")
        self.gps_route_view.delete("1.0", tk.END)
        
        if not path:
            msg = "ARRIVED!\nYou have reached your destination."
            self.gps_instruction_lbl.config(text=msg, fg="#4CAF50")
            self.gps_route_view.insert(tk.END, "--- Destination Reached ---")
            self.gps_route_view.config(state="disabled")
            
            # Reset button state
            self.gps_start_btn.config(text="START GPS", state="normal")
            self.gps_stop_btn.config(state="disabled")
            
            # Update Dock with success message
            if "gps" in self.who_footer_labels:
                self.who_footer_labels["gps"].config(text="🏁 ARRIVED!", fg="#4CAF50")
            return

        # Reset button if it was in 'Recalculating' mode
        self.gps_start_btn.config(text="START GPS", state="disabled")
        self.gps_stop_btn.config(state="normal")
        if "gps" in self.who_footer_labels:
            self.who_footer_labels["gps"].config(fg="#fff") # Restore normal color

        # Current instruction
        from_rid, exit_info = path[step_idx]
        total_steps = len(path)
        
        # Calculate relative arrival_pos for the instruction label
        arrival_pos = None
        if step_idx == 0:
            arrival_pos = self.gps_manager.dataset.get(from_rid, {}).get('teleport')
        else:
            _, prev_exit = path[step_idx-1]
            arrival_pos = prev_exit.get('to_pos')

        instr = self.gps_manager.get_friendly_instruction(
            from_rid, exit_info, step=step_idx+1, total=total_steps, arrival_pos=arrival_pos
        )
        self.gps_instruction_lbl.config(text=instr, fg="#1565C0")
        
        # Full path preview
        for i, (rid, info) in enumerate(path):
            prefix = " >> " if i == step_idx else "    "
            room_name = self.gps_manager.dataset.get(rid, {}).get('name', 'Unknown')
            dest_name = self.gps_manager.dataset.get(info['to_rid'], {}).get('name', 'Unknown')
            self.gps_route_view.insert(tk.END, f"{prefix}{i+1}. {room_name} -> {dest_name}\n")
            
        self.gps_route_view.config(state="disabled")
        self.refresh_who_footer()

    def monitor_gps_navigation(self, current_room_name):
        """Handles path advancement and automatic recalculation."""
        # Update current location display
        self.gps_current_loc_lbl.config(text=current_room_name)
        
        if not self.gps_manager.current_destination_rid:
            return

        # If we reached the destination (path is empty) and move to a DIFFERENT room, clear the state
        if not self.gps_manager.current_path:
            dest_rid = self.gps_manager.current_destination_rid
            dest_name = self.gps_manager.dataset.get(dest_rid, {}).get('name', '')
            if current_room_name.lower() != dest_name.lower():
                logger.info("GPS: Moved away from destination, clearing state.")
                self.stop_navigation()
            return

        # Always update RID tracking

        path = self.gps_manager.current_path
        step_idx = self.gps_manager.current_step_index
        
        # Check if we arrived at the NEXT room in the sequence
        next_room_rid = path[step_idx][1]['to_rid']
        next_room_name = self.gps_manager.dataset.get(next_room_rid, {}).get('name')
        
        if current_room_name.lower() == next_room_name.lower():
            # Advance step
            self.gps_manager.current_step_index += 1
            if self.gps_manager.current_step_index >= len(path):
                # Arrived!
                self.gps_manager.current_path = []
                logger.info("GPS: Arrived at destination.")
            else:
                logger.info(f"GPS: Advanced to step {self.gps_manager.current_step_index + 1}")
            self.update_gps_navigation_ui()
            return

        # Check if we moved to a room that IS in the current room list (the 'from' of this step)
        curr_step_from_rid = path[step_idx][0]
        curr_step_from_name = self.gps_manager.dataset.get(curr_step_from_rid, {}).get('name')
        
        if current_room_name.lower() == curr_step_from_name.lower():
            # We are still in the correct starting room for this step
            return

        # If we are in a room that is neither the current step's 'from' nor 'to', we might be off-track
        # Check if we jumped ahead in the path (shortcuts)
        for i in range(step_idx + 1, len(path)):
            check_rid = path[i][1]['to_rid']
            if current_room_name.lower() == self.gps_manager.dataset.get(check_rid, {}).get('name', '').lower():
                self.gps_manager.current_step_index = i + 1
                if self.gps_manager.current_step_index >= len(path):
                    self.gps_manager.current_path = []
                self.update_gps_navigation_ui()
                logger.info(f"GPS: Detected shortcut to step {i+1}")
                return

        # Truly off-track. Wait 2 seconds before recalculating to avoid noise
        if not hasattr(self, 'gps_off_track_time'):
            self.gps_off_track_time = time.time()
            
        if time.time() - self.gps_off_track_time > 2.0:
            logger.info(f"GPS: Off-track detected ({current_room_name}). Recalculating...")
            self.start_navigation(target_rid=self.gps_manager.current_destination_rid)
            delattr(self, 'gps_off_track_time')

    def setup_tab_dashboard(self):
        # ... (rest of dashboard setup)
        # --- 1. Top HUD (Vitals) ---
        top = tk.Frame(self.tab_dash, bg="#f0f0f0")
        top.pack(side="top", fill="x", padx=10, pady=5)
        self.hud_values = {}
        for s in ["HP", "MP", "VG"]:
            f = tk.Frame(top, bg="#f0f0f0")
            f.pack(side="left", padx=20)
            tk.Label(f, text=f"{s}:", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(side="left")
            val = tk.Label(f, text="---", font=("Arial", 12), bg="#f0f0f0", width=4, anchor="w")
            val.pack(side="left", padx=5)
            self.hud_values[s] = val
        self.countdown_lbl = tk.Label(top, text="10s", font=("Arial", 8), bg="#f0f0f0", fg="gray")
        self.countdown_lbl.pack(side="right", padx=10)
        
        # --- 2. Bottom Sync Section (Pack first to keep pinned) ---
        sync_f = tk.Frame(self.tab_dash, bg="#f0f0f0")
        sync_f.pack(side="bottom", fill="x", padx=10, pady=10)
        self.manual_sync_btn = tk.Button(
            sync_f, text=" ↻ FULL SYNC ", 
            command=self.trigger_manual_sync, 
            state="disabled", font=("Arial", 13, "bold"), pady=10
        )
        self.manual_sync_btn.pack(fill="x")

        # --- 3. Expanding Middle Grid ---
        grid = tk.Frame(self.tab_dash, bg="#f0f0f0")
        grid.pack(side="top", fill="both", expand=True, padx=10, pady=5)
        grid.columnconfigure(1, weight=1) # Gains list
        grid.columnconfigure(2, weight=1) # Kills list
        grid.rowconfigure(0, weight=1)    # Vertical expansion
        
        attr_col = tk.LabelFrame(grid, text=" Attributes ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        attr_col.grid(row=0, column=0, sticky="nsw", padx=5)
        self.attr_labels = {}
        for a in ["Might", "Intellect", "Stamina", "Agility", "Mysticism", "Aim", "Karma"]:
            f = tk.Frame(attr_col, bg="#f0f0f0")
            f.pack(fill="x", pady=4, padx=5)
            tk.Label(f, text=f"{a}:", font=("Arial", 10), bg="#f0f0f0", width=10, anchor="w").pack(side="left")
            v = tk.Label(f, text="--", font=("Arial", 10, "bold"), bg="#f0f0f0", width=5, anchor="e")
            v.pack(side="right")
            self.attr_labels[a] = v

        gains_col = tk.LabelFrame(grid, text=" Session Improves ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        gains_col.grid(row=0, column=1, sticky="nsew", padx=5)
        self.gains_tree = ttk.Treeview(gains_col, columns=("Name", "Count", "Delta"), show="headings", height=5)
        for c, w in [("Name", self.scale_px(120)), ("Count", self.scale_px(50)), ("Delta", self.scale_px(80))]:
            self.gains_tree.heading(c, text=c)
            self.gains_tree.column(c, width=w, anchor="w" if c=="Name" else "center")
        self.gains_tree.pack(fill="both", expand=True)
        
        kills_col = tk.LabelFrame(grid, text=" Session Kills ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        kills_col.grid(row=0, column=2, sticky="nsew", padx=5)
        self.kills_tree = ttk.Treeview(kills_col, columns=("Name", "Count"), show="headings", height=5)
        for c, w in [("Name", self.scale_px(120)), ("Count", self.scale_px(60))]:
            self.kills_tree.heading(c, text=c)
            self.kills_tree.column(c, width=w, anchor="w" if c=="Name" else "center")
        self.kills_tree.pack(fill="both", expand=True)

    def launch_elusion_menu(self):
        try:
            from m59_elude import ElusionMenu
            if hasattr(self, 'elusion_menu') and self.elusion_menu.winfo_exists():
                self.elusion_menu.focus_set()
                return
            hwnd = self.main_hwnd if hasattr(self, 'main_hwnd') and self.main_hwnd else None
            self.elusion_menu = ElusionMenu(self, target_hwnd=hwnd)
        except Exception as e:
            logger.error(f"Failed to launch Elusion menu: {e}")

    def on_gps_loc_resize(self, event):
        """Dynamically adjusts text wrapping for the current location label."""
        self.gps_current_loc_lbl.config(wraplength=event.width - 20)

    def setup_tab_progression(self):
        ctrl = tk.Frame(self.tab_prog, bg="#f0f0f0")
        ctrl.pack(fill="x", padx=10, pady=10)
        tk.Label(ctrl, text="Real-time School Progression Goals", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(side="left")
        self.sync_btn = tk.Button(ctrl, text="Sync All (Tab Dance)", command=self.trigger_sync, bg="#2196F3", fg="white", font=("Arial", 10, "bold"), padx=15)
        self.sync_btn.pack(side="right")
        self.prog_tree = ttk.Treeview(self.tab_prog, columns=("Level", "Sum", "Goal", "Needed"), show="tree headings")
        self.prog_tree.heading("#0", text="School / Ability")
        self.prog_tree.column("#0", width=self.scale_px(220))
        for c, w in [("Level", self.scale_px(80)), ("Sum", self.scale_px(100)), ("Goal", self.scale_px(100)), ("Needed", self.scale_px(100))]:
            self.prog_tree.heading(c, text=c)
            self.prog_tree.column(c, width=w, anchor="center")
        self.prog_tree.pack(fill="both", expand=True, padx=10, pady=5)

    def update_vault_ui(self):
        """Updates the bank balance displays in the Vault tab."""
        if hasattr(self, 'bank_currency_lbl'):
            m = self.bank_manager.balances['mainland']
            i = self.bank_manager.balances['island']
            self.bank_currency_lbl.config(text=f" Mainland: {m:,}s   |   Island: {i:,}s ")

    def setup_tab_vault(self):
        cont = tk.Frame(self.tab_vault, bg="#f0f0f0")
        cont.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- Bank Accounts Header ---
        bank_f = tk.Frame(cont, bg="#E8F5E9", bd=1, relief=tk.SOLID)
        bank_f.pack(fill="x", padx=5, pady=(0, 10))
        tk.Label(bank_f, text="💰 BANK ACCOUNTS:", font=("Arial", 9, "bold"), bg="#E8F5E9", fg="#2E7D32").pack(side="left", padx=10, pady=10)
        self.bank_currency_lbl = tk.Label(bank_f, text=" Mainland: 0s   |   Island: 0s ", font=("Consolas", 11, "bold"), bg="#E8F5E9", fg="#1B5E20")
        self.bank_currency_lbl.pack(side="left", padx=10)
        
        vaults_cont = tk.Frame(cont, bg="#f0f0f0")
        vaults_cont.pack(fill="both", expand=True)

        self.vault_widgets = {}
        for vt in ["barloque", "hungry"]:
            f = tk.LabelFrame(vaults_cont, text=f" {vt.title()} Vault ", bg="#f0f0f0", font=("Arial", 10, "bold"))
            f.pack(side="left", fill="both", expand=True, padx=5)
            row = tk.Frame(f, bg="#f0f0f0")
            row.pack(fill="x", padx=5, pady=5)
            tk.Label(row, text="Filter:", bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
            fv = tk.StringVar()
            fv.trace_add("write", lambda *a, v=vt: self.update_vault_tree(v))
            tk.Entry(row, textvariable=fv, width=15).pack(side="left", padx=2)
            btn = tk.Button(row, text="Scan Vault", command=lambda v=vt: self.trigger_vault_scan(v), bg="#2E7D32" if vt=="barloque" else "#1565C0", fg="white", font=("Arial", 8, "bold"), padx=10)
            btn.pack(side="right")
            tr = ttk.Treeview(f, columns=("Name", "Qty"), show="headings", height=15)
            tr.heading("Name", text="Item")
            tr.heading("Qty", text="Qty")
            tr.column("Name", width=self.scale_px(150))
            tr.column("Qty", width=self.scale_px(50), anchor="center")
            tr.pack(fill="both", expand=True, padx=5, pady=2)
            sl = tk.Label(f, text="No scan data", font=("Arial", 7, "italic"), bg="#f0f0f0", fg="gray")
            sl.pack(side="bottom", fill="x")
            self.vault_widgets[vt] = {"tree": tr, "filter_var": fv, "status_lbl": sl, "sync_btn": btn}
        
        self.update_vault_ui()

    def setup_tab_book(self):
        # Main vertical paned window or frames
        main_pane = tk.PanedWindow(self.tab_book, orient=tk.VERTICAL, bg="#e0e0e0", sashwidth=4, sashrelief=tk.RAISED)
        main_pane.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Top Frame (Lists)
        top_frame = tk.Frame(main_pane, bg="#f0f0f0")
        main_pane.add(top_frame, stretch="always", minsize=150)
        
        # Bottom Frame (Image)
        bottom_frame = tk.Frame(main_pane, bg="#333333")
        main_pane.add(bottom_frame, stretch="always", minsize=150)
        
        # --- Top Half: Lists ---
        self.book_widgets = {}
        for kt in ["monsters", "players"]:
            f = tk.LabelFrame(top_frame, text=f" {kt.title()} ", bg="#f0f0f0", font=("Arial", 10, "bold"))
            f.pack(side="left", fill="both", expand=True, padx=5)
            
            row = tk.Frame(f, bg="#f0f0f0")
            row.pack(fill="x", padx=5, pady=5)
            
            fv = tk.StringVar()
            fv.trace_add("write", lambda *a, k=kt: self.update_book_tree(k))
            
            tk.Label(row, text="Filter:", bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
            tk.Entry(row, textvariable=fv, width=15).pack(side="left", padx=2)
            
            tr = ttk.Treeview(f, columns=("Name", "AllTime", "Session"), show="headings", height=8)
            tr.heading("Name", text="Victim")
            tr.heading("AllTime", text="Total")
            tr.heading("Session", text="Session")
            tr.column("Name", width=self.scale_px(150))
            tr.column("AllTime", width=self.scale_px(60), anchor="center")
            tr.column("Session", width=self.scale_px(60), anchor="center")
            tr.pack(fill="both", expand=True, padx=5, pady=2)
            
            self.book_widgets[kt] = {"tree": tr, "filter_var": fv}
            
            # Bind selection for Monsters to update image
            if kt == "monsters":
                tr.bind("<<TreeviewSelect>>", self.on_monster_select)

        # --- Bottom Half: Image Viewer ---
        # Sliders for Angle and Pose (Pack FIRST at bottom)
        sliders_frame = tk.Frame(bottom_frame, bg="#333333")
        sliders_frame.pack(side="bottom", fill="x", padx=20, pady=5)
        
        tk.Label(sliders_frame, text="Pose:", bg="#333333", fg="white").pack(side="left")
        self.bgf_pose_slider = tk.Scale(sliders_frame, from_=0, to=0, orient=tk.HORIZONTAL, bg="#333333", fg="white", highlightthickness=0, command=self.on_bgf_slider_move)
        self.bgf_pose_slider.pack(side="left", fill="x", expand=True, padx=(5, 10))
        
        tk.Label(sliders_frame, text="Angle:", bg="#333333", fg="white").pack(side="left")
        self.bgf_angle_slider = tk.Scale(sliders_frame, from_=0, to=5, orient=tk.HORIZONTAL, bg="#333333", fg="white", highlightthickness=0, command=self.on_bgf_slider_move)
        self.bgf_angle_slider.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # Canvas (Pack SECOND to fill remaining top space)
        self.bgf_canvas = tk.Canvas(bottom_frame, bg="#333333", highlightthickness=0)
        self.bgf_canvas.pack(side="top", fill="both", expand=True, pady=(5,0))
        
        self.current_bgf_frames = []
        self.current_bgf_image_on_canvas = None
        self.bgf_empty_text = self.bgf_canvas.create_text(
            self.winfo_width()//2, 100, text="Select a monster to view", fill="gray", font=("Arial", 12, "italic")
        )
        # Handle canvas resize
        self.bgf_canvas.bind("<Configure>", self.center_bgf_image)

    def center_bgf_image(self, event=None):
        if self.bgf_empty_text:
            self.bgf_canvas.coords(self.bgf_empty_text, self.bgf_canvas.winfo_width()//2, self.bgf_canvas.winfo_height()//2)
        if getattr(self, "current_bgf_frames", None) and self.current_bgf_image_on_canvas:
            pose = int(self.bgf_pose_slider.get())
            angle = int(self.bgf_angle_slider.get())
            index = pose * 6 + angle
            self.show_bgf_frame(index)

    def on_monster_select(self, event):
        selection = event.widget.selection()
        if not selection: return
        item = event.widget.item(selection[0])
        monster_name = item['values'][0]
        
        logger.info(f"Killbook: Monster selected: {monster_name}")
        
        self.bgf_canvas.delete("all")
        self.current_bgf_frames = []
        self.bgf_pose_slider.config(to=0, state="disabled")
        self.bgf_angle_slider.config(state="disabled")
        
        if getattr(self, "bgf_manager", None):
            cleaned_sel = ''.join(c for c in monster_name.lower() if c.isalnum() or c.isspace() or c == "'" or c == "-")
            internal_name = self.bgf_manager.mob_mapping.get(cleaned_sel)
            if not internal_name:
                internal_name = self.bgf_manager.mob_mapping.get(cleaned_sel.replace(" ", ""))
            if not internal_name:
                internal_name = self.bgf_manager.mob_mapping.get(monster_name.lower())
                
            logger.info(f"Killbook: Internal name for '{monster_name.lower()}' is '{internal_name}'")
            if internal_name:
                bgf_path = self.bgf_manager.find_bgf_for_monster(internal_name)
                logger.info(f"Killbook: Found BGF path: {bgf_path}")
                if bgf_path:
                    frames = self.bgf_manager.load_bgf_frames(bgf_path)
                    logger.info(f"Killbook: Loaded {len(frames) if frames else 0} frames")
                    if frames:
                        self.current_bgf_frames = frames
                        max_pose = max(0, (len(frames) // 6) - 1) if len(frames) >= 6 else max(0, len(frames)-1)
                        self.bgf_pose_slider.config(to=max_pose, state="normal")
                        self.bgf_pose_slider.set(0)
                        self.bgf_angle_slider.config(to=5 if len(frames) >= 6 else 0, state="normal")
                        self.bgf_angle_slider.set(0)
                        self.show_bgf_frame(0)
                        return
            else:
                logger.warning(f"Killbook: No internal name mapping found for '{monster_name.lower()}'")
                        
        self.bgf_empty_text = self.bgf_canvas.create_text(
            self.bgf_canvas.winfo_width()//2, self.bgf_canvas.winfo_height()//2, 
            text="No image available", fill="gray", font=("Arial", 12, "italic")
        )
        self.current_bgf_image_on_canvas = None

    def on_bgf_slider_move(self, val=None):
        pose = int(self.bgf_pose_slider.get())
        angle = int(self.bgf_angle_slider.get())
        index = pose * 6 + angle
        self.show_bgf_frame(index)
        
    def show_bgf_frame(self, index):
        if not self.current_bgf_frames: return
        if index < 0 or index >= len(self.current_bgf_frames): return
        
        from PIL import ImageTk, Image
        raw_img = self.current_bgf_frames[index]
        
        cw = max(10, self.bgf_canvas.winfo_width())
        ch = max(10, self.bgf_canvas.winfo_height())
        
        # Calculate scale to fit
        iw, ih = raw_img.size
        scale = min(cw/iw, ch/ih) * 0.9 # 90% of canvas
        if scale > 0:
            new_w, new_h = int(iw * scale), int(ih * scale)
            # Crop bounding box of non-transparent area? For now just resize the whole 400x400
            resized = raw_img.resize((new_w, new_h), Image.LANCZOS)
        else:
            resized = raw_img
            
        self._current_tk_bgf = ImageTk.PhotoImage(resized)
        
        self.bgf_canvas.delete("all")
        self.bgf_empty_text = None
        
        self.current_bgf_image_on_canvas = self.bgf_canvas.create_image(
            cw//2, ch//2, 
            image=self._current_tk_bgf, anchor="center"
        )
    def setup_tab_settings(self):
        c = tk.Frame(self.tab_settings, bg="#f0f0f0")
        c.pack(fill="both", expand=True, padx=20, pady=20)
        
        tk.Label(c, text="Companion Settings", font=("Arial", 14, "bold"), bg="#f0f0f0").pack(anchor="w", pady=(0, 20))
        
        pg = tk.LabelFrame(c, text=" Alerts ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        pg.pack(fill="x")
        
        # PK Alerts
        pk_frame = tk.Frame(pg, bg="#f0f0f0")
        pk_frame.pack(fill="x", pady=(0, 5))
        tk.Checkbutton(pk_frame, text="Enable PK Alerts", variable=self.pk_alert_enabled, bg="#f0f0f0").pack(side="left")
        tk.Label(pk_frame, text="Sound:", bg="#f0f0f0").pack(side="left", padx=(10, 2))
        ttk.Combobox(pk_frame, textvariable=self.pk_sound_path, values=["SystemExclamation", "SystemAsterisk", "SystemHand", "SystemQuestion"], width=20).pack(side="left")
        tk.Button(pk_frame, text="Browse...", command=self.browse_pk_sound, padx=5).pack(side="left", padx=5)
        tk.Button(pk_frame, text="Test", command=self.test_pk_sound, padx=5).pack(side="left")
        
        # Tell Alerts
        tell_frame = tk.Frame(pg, bg="#f0f0f0")
        tell_frame.pack(fill="x")
        tk.Checkbutton(tell_frame, text="Enable Direct Message (Tell) Alerts", variable=self.tell_sound_enabled, bg="#f0f0f0").pack(side="left")
        tk.Label(tell_frame, text="Sound:", bg="#f0f0f0").pack(side="left", padx=(10, 2))
        ttk.Combobox(tell_frame, textvariable=self.tell_sound_path, values=["SystemAsterisk", "SystemExclamation", "SystemHand", "SystemQuestion", "sound/dm_chime.wav"], width=20).pack(side="left")
        tk.Button(tell_frame, text="Browse...", command=self.browse_tell_sound, padx=5).pack(side="left", padx=5)
        tk.Button(tell_frame, text="Test", command=self.test_tell_sound, padx=5).pack(side="left")
        
        elude_g = tk.LabelFrame(c, text=" Elusion Settings ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        elude_g.pack(fill="x", pady=10)
        
        gh_frame = tk.Frame(elude_g, bg="#f0f0f0")
        gh_frame.pack(fill="x", pady=(0, 10))
        tk.Label(gh_frame, text="Your Guildhall Name:", bg="#f0f0f0").pack(side="left")
        ttk.Entry(gh_frame, textvariable=self.guildhall_name, width=40).pack(side="left", padx=5)

        tk.Label(elude_g, text="Elusion Phrase (Start with 'say' or 'emote', use {loc} for location):", bg="#f0f0f0").pack(anchor="w")
        
        base_phrases = [
            'say "I wish to travel to {loc}."',
            'say "By the grace of the High Council, I demand passage to {loc}!"',
            "emote separates the earths and forms a path to {loc}",
            "emote traces a rune in the air, opening a rift to {loc}",
            "emote bends the fabric of space with Riija's chaotic magic, stepping towards {loc}"
        ]
        
        all_phrases = list(dict.fromkeys(base_phrases + self.custom_elusion_phrases))
        
        phrase_frame = tk.Frame(elude_g, bg="#f0f0f0")
        phrase_frame.pack(fill="x", pady=5)
        
        phrase_combo = ttk.Combobox(phrase_frame, textvariable=self.elusion_phrase, values=all_phrases, width=60)
        phrase_combo.pack(side="left")
        
        def add_phrase():
            current = self.elusion_phrase.get()
            if current and current not in all_phrases:
                self.custom_elusion_phrases.append(current)
                all_phrases.append(current)
                phrase_combo.configure(values=all_phrases)
                self.save_settings()
                
        tk.Button(phrase_frame, text="Add", command=add_phrase, bg="#4CAF50", fg="white", relief="flat", padx=10).pack(side="left", padx=5)
        
        wr_g = tk.LabelFrame(c, text=" Status Dock Side Panel ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        wr_g.pack(fill="x", pady=10)
        
        side_f = tk.Frame(wr_g, bg="#f0f0f0")
        side_f.pack(fill="x", pady=5)
        tk.Label(side_f, text="Panel Side:", bg="#f0f0f0").pack(side="left")
        tk.Radiobutton(side_f, text="Left", variable=self.who_list_side, value="Left",
                        command=self.update_who_list_visibility, bg="#f0f0f0").pack(side="left", padx=10)
        tk.Radiobutton(side_f, text="Right", variable=self.who_list_side, value="Right",
                        command=self.update_who_list_visibility, bg="#f0f0f0").pack(side="left")
        
        dg = tk.LabelFrame(c, text=" Diagnostics ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        dg.pack(fill="x")
        tk.Checkbutton(dg, text="Verbose Debug Mode", variable=self.debug_enabled, bg="#f0f0f0").pack(anchor="w")
        
        map_g = tk.LabelFrame(c, text=" Game.map Tools ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        map_g.pack(fill="x", pady=10)
        
        def restore_map():
            import m59_map
            import shutil
            import os
            
            def show_styled_msg(title, msg, icon="✅"):
                pop = tk.Toplevel(self)
                pop.title("M59 Companion")
                pop.overrideredirect(True)
                pop.attributes("-topmost", True)
                try: pop.attributes("-alpha", 0.95)
                except: pass
                pop.configure(bg="#0F0F0F")
                inner_pop = tk.Frame(pop, bg="#181818", highlightthickness=1, highlightbackground="#333333")
                inner_pop.pack(expand=True, fill="both", padx=2, pady=2)
                
                color = "#FF5252" if "Error" in title else "#81C784" if "Success" in title else "#FFCA28"
                tk.Label(inner_pop, text=f" {icon}  {title.upper()} ", font=("Consolas", 14, "bold"), fg=color, bg="#181818").pack(pady=(30, 10))
                tk.Label(inner_pop, text=msg, font=("Arial", 11), fg="#FFFFFF", bg="#181818", justify="center", wraplength=540).pack(pady=(10, 20))
                tk.Button(inner_pop, text=" OK ", bg="#424242", fg="white", font=("Arial", 10, "bold"), command=pop.destroy).pack(pady=(0, 20))

                pop.update_idletasks()
                w = 580
                h = max(260, pop.winfo_reqheight())
                pop.geometry(f"{w}x{h}+{int(self.winfo_screenwidth()/2 - w/2)}+{int(self.winfo_screenheight()/2 - h/2)}")

            rooms_dir, map_file, is_running = m59_map.detect_installation()
            if map_file and os.path.exists(map_file + ".backup"):
                try:
                    shutil.copy2(map_file + ".backup", map_file)
                    show_styled_msg("Success", "Restored game.map from backup!", "✅")
                except Exception as e:
                    show_styled_msg("Error", f"Failed to restore: {e}", "❌")
            else:
                show_styled_msg("Not Found", "No backup found.", "⚠️")

        tk.Button(map_g, text="Restore game.map from Backup", command=restore_map, font=("Arial", 9)).pack(anchor="w")
        
        tk.Button(c, text="Save Settings", command=self.save_settings, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), pady=10).pack(side="bottom", fill="x")

    def trigger_pk_alert(self):
        if not self.pk_alert_enabled.get():
            return
        self.alert_active = True
        self.debug_log("ALERT", "PVP Alert Triggered!")
        if self.pk_sound_enabled.get():
            p = self.pk_sound_path.get()
            try:
                if p.startswith("System"):
                    winsound.PlaySound(p, winsound.SND_ALIAS | winsound.SND_ASYNC)
                else:
                    # Resolve path if relative
                    if not os.path.isabs(p):
                        p = resource_path(p)
                    winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                self.debug_log("ALERT", f"Sound error: {e}")
        if self.pk_frame_enabled.get() and self.pk_frame:
            self.pk_frame.flash()
        self.after(5000, self.reset_pk_alert)

    def play_tell_alert(self):
        if not self.tell_sound_enabled.get(): return
        p = self.tell_sound_path.get()
        try:
            if p.startswith("System"):
                winsound.PlaySound(p, winsound.SND_ALIAS | winsound.SND_ASYNC)
            else:
                if not os.path.isabs(p):
                    p = resource_path(p)
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            logger.debug(f"Tell sound error: {e}")

    def reset_pk_alert(self):
        self.alert_active = False




    def map_initialization_check(self, pid, callback):
        import m59_map
        import os
        import threading
        import subprocess
        import time
        from tkinter import messagebox
        
        rooms_dir, map_file, is_running = m59_map.detect_installation()
        if not rooms_dir or not map_file or not os.path.isdir(rooms_dir):
            callback()
            return

        unique_rooms = m59_map.get_unique_rooms(rooms_dir)
        if not unique_rooms:
            callback()
            return
            
        percent = m59_map.analyze_map(map_file, unique_rooms)
        if percent >= 100.0:
            callback()
            return

        def show_styled_map_prompt():
            overlay = tk.Toplevel(self)
            overlay.title("M59 Companion - Map Update")
            
            # Center the splash screen on the screen
            window_width = 580
            window_height = 260
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            center_x = int(screen_width/2 - window_width / 2)
            center_y = int(screen_height/2 - window_height / 2)
            
            overlay.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")
            overlay.resizable(False, False)
            overlay.overrideredirect(True)
            overlay.attributes("-topmost", True)
            try: overlay.attributes("-alpha", 0.95)
            except: pass
            
            overlay.configure(bg="#0F0F0F")
            
            inner = tk.Frame(overlay, bg="#181818", highlightthickness=1, highlightbackground="#333333")
            inner.pack(expand=True, fill="both", padx=2, pady=2)
            
            tk.Label(inner, text=" 🗺️  MAP UPDATE AVAILABLE ", font=("Consolas", 14, "bold"), fg="#FFCA28", bg="#181818").pack(pady=(20, 10))
            tk.Label(inner, text=f"Your game.map file is {percent:.1f}% complete.", font=("Arial", 11), fg="#FFFFFF", bg="#181818").pack()
            tk.Label(inner, text="Do you want to update and unlock your map to 100%?", font=("Arial", 10), fg="#CCCCCC", bg="#181818").pack(pady=(5, 15))
            
            def on_no():
                overlay.destroy()
                callback()
                
            def on_yes():
                for widget in inner.winfo_children():
                    widget.destroy()
                    
                tk.Label(inner, text=" 📍  AUTO-ANNOTATIONS ", font=("Consolas", 14, "bold"), fg="#64B5F6", bg="#181818").pack(pady=(20, 10))
                tk.Label(inner, text="Automatically add map annotations for all exits/doors?", font=("Arial", 10), fg="#FFFFFF", bg="#181818").pack()
                tk.Label(inner, text="Warning: YES overwrites custom annotations.\nNO preserves your existing custom annotations.", font=("Arial", 9, "italic"), fg="#FF5252", bg="#181818", justify="center", wraplength=550).pack(pady=(10, 15))
                
                def proceed_with_update(anno_choice):
                    overlay.destroy()

                    def do_map_update():
                        try:
                            def _ui_closing():
                                if self.waiting_overlay and self.waiting_overlay.winfo_exists():
                                    self.waiting_title_lbl.config(text=" 🗺️  UPDATING MAP ", fg="#FFCA28")
                                    self.waiting_msg_lbl.config(text="Closing game to release file locks...")
                                self.status_var.set("Closing game for map update...")
                            self.after(0, _ui_closing)
                            
                            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                            time.sleep(1)

                            def _ui_updating():
                                if self.waiting_overlay and self.waiting_overlay.winfo_exists():
                                    self.waiting_msg_lbl.config(text="Generating game.map file...")
                                self.status_var.set("Updating game.map...")
                            self.after(0, _ui_updating)
                            
                            existing_annos = {}
                            if not anno_choice:
                                existing_annos = m59_map.extract_existing_annotations(map_file, unique_rooms)
                            
                            m59_map.generate_map(map_file, unique_rooms, debug=False, preserve_annotations=not anno_choice, existing_annotations=existing_annos)
                            
                            def show_success():
                                pop = tk.Toplevel(self)
                                pop.title("M59 Companion")
                                pop.overrideredirect(True)
                                pop.attributes("-topmost", True)
                                try: pop.attributes("-alpha", 0.95)
                                except: pass
                                pop.configure(bg="#0F0F0F")
                                inner_pop = tk.Frame(pop, bg="#181818", highlightthickness=1, highlightbackground="#333333")
                                inner_pop.pack(expand=True, fill="both", padx=2, pady=2)
                                tk.Label(inner_pop, text=" ✅  MAP UPDATED ", font=("Consolas", 14, "bold"), fg="#81C784", bg="#181818").pack(pady=(30, 10))
                                tk.Label(inner_pop, text="Map update complete! A backup was saved in your mail folder.\nYou can safely restart Meridian 59 now.", font=("Arial", 11), fg="#FFFFFF", bg="#181818", justify="center", wraplength=540).pack(pady=(10, 20))
                                tk.Button(inner_pop, text=" OK ", bg="#2e7d32", fg="white", font=("Arial", 10, "bold"), command=pop.destroy).pack(pady=(0, 20))
                                
                                pop.update_idletasks()
                                w = 580
                                h = max(260, pop.winfo_reqheight())
                                pop.geometry(f"{w}x{h}+{int(self.winfo_screenwidth()/2 - w/2)}+{int(self.winfo_screenheight()/2 - h/2)}")
                                
                            self.after(0, show_success)
                        except Exception as e:
                            def show_error(err=e):
                                pop = tk.Toplevel(self)
                                pop.title("M59 Companion")
                                pop.overrideredirect(True)
                                pop.attributes("-topmost", True)
                                try: pop.attributes("-alpha", 0.95)
                                except: pass
                                pop.configure(bg="#0F0F0F")
                                inner_pop = tk.Frame(pop, bg="#181818", highlightthickness=1, highlightbackground="#333333")
                                inner_pop.pack(expand=True, fill="both", padx=2, pady=2)
                                tk.Label(inner_pop, text=" ❌  MAP ERROR ", font=("Consolas", 14, "bold"), fg="#FF5252", bg="#181818").pack(pady=(30, 10))
                                tk.Label(inner_pop, text=f"Failed to update map: {err}", font=("Arial", 11), fg="#FFFFFF", bg="#181818", justify="center", wraplength=550).pack(pady=(10, 20))
                                tk.Button(inner_pop, text=" OK ", bg="#424242", fg="white", font=("Arial", 10, "bold"), command=pop.destroy).pack(pady=(0, 20))
                                
                                pop.update_idletasks()
                                w = 580
                                h = max(260, pop.winfo_reqheight())
                                pop.geometry(f"{w}x{h}+{int(self.winfo_screenwidth()/2 - w/2)}+{int(self.winfo_screenheight()/2 - h/2)}")
                            self.after(0, show_error)
                        finally:
                            def _ui_waiting():
                                if self.waiting_overlay and self.waiting_overlay.winfo_exists():
                                    self.waiting_title_lbl.config(text=" ↻  SCANNING FOR GAME ", fg="#81C784")
                                    self.waiting_msg_lbl.config(text="Please launch Meridian 59 to continue")
                                self.status_var.set("Waiting for Game...")
                            self.after(0, _ui_waiting)

                    def show_close_prompt():
                        close_overlay = tk.Toplevel(self)
                        close_overlay.title("M59 Companion")
                        
                        close_overlay.resizable(False, False)
                        close_overlay.overrideredirect(True)
                        close_overlay.attributes("-topmost", True)
                        try: close_overlay.attributes("-alpha", 0.95)
                        except: pass
                        close_overlay.configure(bg="#0F0F0F")
                        
                        inner_close = tk.Frame(close_overlay, bg="#181818", highlightthickness=1, highlightbackground="#333333")
                        inner_close.pack(expand=True, fill="both", padx=2, pady=2)
                        
                        tk.Label(inner_close, text=" ⚠️  CLOSE GAME REQUIRED ", font=("Consolas", 14, "bold"), fg="#FFCA28", bg="#181818").pack(pady=(30, 10))
                        tk.Label(inner_close, text="Meridian 59 must be closed to safely update the map file.\n\nClick YES to automatically close the game and apply the update.\nYou can restart it afterwards.", font=("Arial", 11), fg="#FFFFFF", bg="#181818", justify="center", wraplength=540).pack(pady=(10, 20))
                        
                        def on_close_cancel():
                            close_overlay.destroy()
                            callback()
                            
                        def on_close_ok():
                            close_overlay.destroy()
                            threading.Thread(target=do_map_update, daemon=True).start()

                        btn_f_close = tk.Frame(inner_close, bg="#181818")
                        btn_f_close.pack(pady=(0, 20))
                        tk.Button(btn_f_close, text=" YES (Close Game) ", bg="#2e7d32", fg="white", font=("Arial", 10, "bold"), command=on_close_ok).pack(side="left", padx=10)
                        tk.Button(btn_f_close, text=" CANCEL ", bg="#424242", fg="white", font=("Arial", 10, "bold"), command=on_close_cancel).pack(side="left", padx=10)

                        close_overlay.update_idletasks()
                        w = 580
                        h = max(260, close_overlay.winfo_reqheight())
                        close_overlay.geometry(f"{w}x{h}+{int(self.winfo_screenwidth()/2 - w/2)}+{int(self.winfo_screenheight()/2 - h/2)}")

                    show_close_prompt()
                
                btn_f2 = tk.Frame(inner, bg="#181818")
                btn_f2.pack(pady=10)
                tk.Button(btn_f2, text=" YES (Overwrite) ", bg="#2e7d32", fg="white", font=("Arial", 10, "bold"), command=lambda: proceed_with_update(True)).pack(side="left", padx=10)
                tk.Button(btn_f2, text=" NO (Preserve) ", bg="#424242", fg="white", font=("Arial", 10, "bold"), command=lambda: proceed_with_update(False)).pack(side="left", padx=10)

            btn_f = tk.Frame(inner, bg="#181818")
            btn_f.pack(pady=10)
            tk.Button(btn_f, text=" YES ", bg="#2e7d32", fg="white", font=("Arial", 10, "bold"), command=on_yes, width=10).pack(side="left", padx=10)
            tk.Button(btn_f, text=" NO ", bg="#424242", fg="white", font=("Arial", 10, "bold"), command=on_no, width=10).pack(side="left", padx=10)
            
        self.after(0, show_styled_map_prompt)
    def establish_connection(self):
        self.status_var.set("Scanning for game...")
        self.debug_log("CONN", "Starting Lifecycle Monitor...")
        self.show_waiting_overlay()
        self.lifecycle.start()

    def on_game_connect(self, pm, pid):
        """Callback when InstanceManager attaches to a new game process."""
        logger.info(f"LifeCycle: New Game Instance Detected (PID {pid})")
        
        def _continue_init():
            self.pm_obj = pm
            self.target_pid = pid

            # Initialize Scraper
            self.inventory_scraper = InventoryScraper(pm)

            # Find the HWND for this PID
            def _wait_for_hwnd(retries=10):
                self.main_hwnd = find_game_hwnd(pid)
                if not self.main_hwnd:
                    if retries > 0:
                        self.after(500, lambda: _wait_for_hwnd(retries - 1))
                    else:
                        logger.error(f"LifeCycle: Found PID {pid} but could not locate its window after waiting.")
                    return

                # Transition overlay to appropriate state based on current login status
                try:
                    import win32gui
                    title = win32gui.GetWindowText(self.main_hwnd)
                    if " --- " in title:
                        self.show_waiting_overlay(mode="initializing")
                    else:
                        self.show_waiting_overlay(mode="login")
                except:
                    self.show_waiting_overlay(mode="login")
                    
                # Start Who List if enabled
                self.start_who_list_monitor()
                
                if hasattr(self, 'commalias_tab'):
                    self.commalias_tab.manager.update_float_buttons()
                
                # Start Inventory Polling
                self.after(2000, self.poll_inventory)
                self.after(500, self.check_for_login)

            _wait_for_hwnd()

        if not getattr(self, "has_checked_map", False):
            self.has_checked_map = True
            # Transition to a generic connecting overlay first
            self.show_waiting_overlay(mode="searching")
            self.after(500, lambda: self.map_initialization_check(pid, _continue_init))
        else:
            _continue_init()

    def check_for_login(self):
        """Polls the window title to detect when a character has entered the world."""
        if not self.main_hwnd or not self.is_running:
            return
            
        try:
            title = win32gui.GetWindowText(self.main_hwnd)
            if " --- " in title:
                logger.info(f"LifeCycle: Login detected via title: {title}")
                self.show_waiting_overlay(mode="initializing")
                # overlay will be hidden after initial sync
                
                # Start the intelligent identity capture loop
                logger.info("LifeCycle: Starting character identification handshake...")
                self.after(2000, lambda: self.attempt_identity_capture(0))
                
                # Trigger silent who update 1.5s after character is fully active in-game
                self.after(3500, self.trigger_silent_who_update)
            else:
                # Still at selection screen, check again in 1s
                self.after(1000, self.check_for_login)
        except Exception as e:
            logger.debug(f"LifeCycle: Error checking for login: {e}")
            self.after(2000, self.check_for_login)

    def attempt_identity_capture(self, count):
        """Intelligently retries character identification with adaptive delays and UI feedback."""
        # Update status bar with progress
        self.status_var.set(f"Finalizing Identity... (Attempt {count + 1}/10)")
        
        if hasattr(self, 'pre_scanned_names') and self.target_pid in self.pre_scanned_names:
            name = self.pre_scanned_names[self.target_pid]
            # remove it so it can be rescanned later if needed
            del self.pre_scanned_names[self.target_pid]
        else:
            name = capture_identity(self.main_hwnd, self.target_pid)
        
        if name:
            logger.info(f"LifeCycle: Identity verified as '{name}' on attempt {count + 1}.")
            self.char_name = name
            self._finalize_connection()
            return

        if count < 9: # Total 10 attempts
            # Adaptive delay: Start fast, slow down to allow for server lag
            delay = 1000 if count < 3 else 2000
            logger.info(f"LifeCycle: Identity not ready (Attempt {count + 1}/10). Retrying in {delay/1000}s...")
            self.after(delay, lambda: self.attempt_identity_capture(count + 1))
        else:
            logger.warn("LifeCycle: Identity capture failed after 10 attempts. Falling back to Unknown.")
            self.char_name = "Unknown"
            self._finalize_connection()

    def trigger_manual_sync(self):
        """Action for the manual sync button on the Dashboard."""
        if not self.main_hwnd:
            messagebox.showwarning("Sync", "No active game process found to sync.")
            return
            
        self.manual_sync_btn.config(state="disabled", text=" ↻ SYNCING... PLEASE WAIT ")
        self.status_var.set("Performing Manual Identity & Full Sync...")
        
        def run_sync():
            try:
                # Mark as initially synced now
                self.initial_sync_done = True
                
                # 1. Identity
                logger.info("Sync: Performing manual identity capture...")
                new_name = capture_identity(self.main_hwnd, self.target_pid)
                if new_name:
                    self.char_name = new_name
                    self.after(0, lambda: self.title(f"M59 Companion v{self.version} - {self.char_name}"))
                
                # 2. Bank Balances
                self.bank_manager.load_balances(self.char_name)
                self.after(0, self.refresh_who_footer)
                self.after(0, self.update_vault_ui)

                # 3. Tab Dance & Scrape
                logger.info("Sync: Starting Tab Dance & Scrape...")
                mr = MemoryReader(self.pm_obj)
                kn, st = cycle_tabs_and_scrape(self.main_hwnd, mr)
                if kn or st:
                    self.after(0, lambda: self._apply_sync_results(kn, st))
                
                self.after(0, lambda: self.status_var.set(f"Sync Complete: {self.char_name}"))
                logger.info("Sync: Manual sync complete.")
            except Exception as e:
                logger.error(f"Manual sync error: {e}")
                self.after(0, lambda: self.status_var.set("Manual Sync Failed."))
            finally:
                # Disable the button and reset text until the next login/reconnect event
                self.after(0, lambda: self.manual_sync_btn.config(state="disabled", text=" ↻ FULL SYNC "))
        
        threading.Thread(target=run_sync, daemon=True).start()

    def _finalize_connection(self):
        self.title(f"M59 Companion v{self.version} - {self.char_name}")
        self.status_var.set(f"Connected: {self.char_name}")
        self._post_connection_init()

    def on_game_disconnect(self, pid):
        """Callback when InstanceManager loses connection to a game process."""
        logger.info(f"LifeCycle: Game Instance Lost (PID {pid}). Entering search mode...")
        
        # Stop WhoList Monitor
        if self.who_list_monitor:
            self.who_list_monitor.stop()
            self.who_list_monitor = None
            
        self.who_list_players = {}
        self.inventory_items = []
        self.inventory_scraper = None
        self.main_hwnd = None
        self.pm_obj = None
        self.target_pid = None
        
        if hasattr(self, 'commalias_tab'):
            self.commalias_tab.manager.update_float_buttons()
        
        def safe_ui_reset():
            self.refresh_who_list_ui()
            # self.update_inventory_tree() # REMOVED: Fake name cause error
            self.show_waiting_overlay()
            self.status_var.set(f"Game Lost ({self.char_name}) - Searching...")
            self.title(f"M59 Companion v{self.version} - Waiting...")
            for v in self.hud_values.values():
                v.config(text="---")
            if self.pk_frame:
                try: self.pk_frame.destroy()
                except: pass
                self.pk_frame = None

        self.after(0, safe_ui_reset)

    def _post_connection_init(self, passive=False):
        if not self.is_running:
            return
        self.debug_log("INIT", f"Initializing profile (Passive: {passive})...")
        try:
            self.load_vault_cache()
            self.load_kill_book()
            self.refresh_log_list()
            
            # Initialize Bank Manager for this character
            self.bank_manager.load_balances(self.char_name)
            self.refresh_who_footer()
            self.update_vault_ui()
            
            if not self.pk_frame:
                self.pk_frame = PKFrame(self, self.main_hwnd)
                
            self.update_hud()
            self.start_chat_monitor()
            
            if not passive:
                self.debug_log("INIT", "Starting automatic startup sync...")
                threading.Thread(target=self.perform_sync, daemon=True).start()
        except Exception as e:
            self.debug_log("INIT", f"Post-connection error: {e}")

    def toggle_game_time_mode(self):
        self.game_time_mode_24h.set(not self.game_time_mode_24h.get())
        self.update_game_time()
        self.save_settings()

    def update_game_time(self):
        if hasattr(self, "game_time_lbl") and self.game_time_lbl:
            try:
                info = get_game_time()
                time_str = format_game_time(info, use_24h=self.game_time_mode_24h.get())
                self.game_time_lbl.config(text=f"Game Time: {time_str}")
            except Exception as e:
                logger.debug(f"Clock update error: {e}")
        self.after(1000, self.update_game_time)

    def update_hud(self):
        if not self.main_hwnd or not self.is_running:
            return
        self.refresh_counter -= 1
        
        # --- Title-based Login/Logout Detection ---
        try:
            current_title = win32gui.GetWindowText(self.main_hwnd)
            is_logged_in = " --- " in current_title
            
            if not is_logged_in and self.initial_sync_done:
                # STATE: User just logged out (window still open)
                if "Logged Out" not in self.status_var.get():
                    logger.info(f"Character {self.char_name} logged out (Select Screen).")
                    self.status_var.set(f"Logged Out ({self.char_name})")
                    self.title(f"M59 Companion v{self.version} - Logged Out")
                    # Clear Who List on logout
                    self.who_list_players = {}
                    self.refresh_who_list_ui()
                    if hasattr(self, "gps_who_loc_lbl") and self.gps_who_loc_lbl:
                        self.gps_who_loc_lbl.config(text="Unknown Location")
            
            elif is_logged_in:
                room = current_title.split(" --- ", 1)[1].strip()
                if "Logged Out" in self.status_var.get():
                    # STATE: User just logged back in
                    logger.info(f"Character detected back in-game at {room}.")
                    self.status_var.set(f"Re-connected: {self.char_name} (Ready for Manual Sync)")
                    self.title(f"M59 Companion v{self.version} - {self.char_name}")
                    # Enable the sync button to indicate a refresh is needed
                    self.manual_sync_btn.config(state="normal", text=" ↻ FULL SYNC REQUIRED ")
                
                self.gps_current_loc_lbl.config(text=room)
                if hasattr(self, "gps_who_loc_lbl") and self.gps_who_loc_lbl:
                    self.gps_who_loc_lbl.config(text=room)
                self.monitor_gps_navigation(room)
                
                # Refresh footer to ensure PVP status and GPS labels update correctly on room change
                self.refresh_who_footer()
                
                # Always track travel times in background (Weighted Pathfinding)
                was_t, msg = self.gps_manager.process_room_update(room)
                if msg:
                    # Log to console/debug only if debug is on or discovery is on
                    if self.debug_enabled.get():
                        self.gps_log(msg)

        except Exception as e:
            logger.debug(f"Title tracking error: {e}")

        if self.refresh_counter <= 0:
            self.refresh_counter = 10
            try:
                st = get_blakgraph_stats(self.main_hwnd)
                if st:
                    # Log raw stats in high debug
                    self.debug_log("DATA", f"Raw stats from memory: {list(st.keys())}")
                    for k, v in st.items():
                        if k in self.hud_values:
                            self.hud_values[k].config(text=str(v))
                        if k in self.attr_labels:
                            self.current_attributes[k] = v
                            self.attr_labels[k].config(text=str(v))
            except Exception as e:
                self.debug_log("HUD", f"Update error: {e}")
        self.countdown_lbl.config(text=f"{self.refresh_counter}s")
        self.after(1000, self.update_hud)

    def monitor_gps_discovery(self, cur):
        if cur == "Unknown Location":
            return
        was_t, msg = self.gps_manager.process_room_update(cur)
        if msg:
            self.gps_log(msg)
            self.update_gps_ui()

    def start_chat_monitor(self):
        def loop():
            tr = SessionTracker()
            co = CombatMonitor(self.char_name)
            logger.info("ChatMonitor: Thread started.")
            
            # Initial handle grab - wrap in try/except to handle case where user isn't logged in yet
            try:
                ch = win32gui.GetDlgItem(self.main_hwnd, 1005)
                if not ch:
                    logger.info("ChatMonitor: Chat control (1005) not found yet.")
                else:
                    logger.info(f"ChatMonitor: Initialized with HWND {ch}")
            except pywintypes.error as e:
                if e.winerror == 1421:
                    logger.info("ChatMonitor: Chat control (1005) not found yet. Waiting...")
                    ch = None
                else:
                    raise

            safe_n = get_safe_name(self.char_name)
            log_p = os.path.join("settings", f"{safe_n}_chat.log")
            
            # Initial baseline
            cur_text = get_text_from_hwnd(ch) if ch else ""
            lines = [l.strip() for l in cur_text.splitlines() if l.strip()]
            self.last_tail = lines[-50:] if lines else []
            logger.info(f"ChatMonitor: Baseline set with {len(self.last_tail)} lines.")

            last_heartbeat_log = 0

            while self.is_running:
                try:
                    # 1. Process Heartbeat
                    self.pm_obj.read_int(self.pm_obj.base_address)
                    
                    # Log heartbeat every 60 seconds for debugging
                    if time.time() - last_heartbeat_log > 60:
                        logger.debug("ChatMonitor: Heartbeat OK.")
                        last_heartbeat_log = time.time()

                    # 2. Control Handle Validation
                    try:
                        c_c = win32gui.GetDlgItem(self.main_hwnd, 1005)
                        if c_c and c_c != ch:
                            logger.info(f"ChatMonitor: Game control changed. Re-binding HWND {ch} -> {c_c}")
                            ch = c_c
                    except pywintypes.error as e:
                        # Error 1421 = Control ID not found (User is likely at select screen)
                        if e.winerror == 1421:
                            if ch:
                                logger.info("ChatMonitor: Chat control disappeared (Logout). Waiting...")
                                ch = None
                            time.sleep(2)
                            continue
                        raise # Re-raise other win32 errors to be caught by the outer loop
                    
                    if not ch:
                        time.sleep(1)
                        continue

                    # 3. Read and Process
                    cur_text = get_text_from_hwnd(ch)
                    lines = [l.strip() for l in cur_text.splitlines() if l.strip()]
                    
                    if not lines:
                        # Chat was likely cleared (Logout)
                        if self.last_tail:
                            logger.info("ChatMonitor: Chat buffer appears empty. Resetting fingerprint.")
                            self.last_tail = []
                        time.sleep(1)
                        continue

                    new = []
                    found = -1
                    tail = list(self.last_tail)
                    
                    while tail:
                        tl = len(tail)
                        search = lines[-100-tl:] if len(lines) > 100 else lines
                        off = len(lines) - len(search)
                        for i in range(len(search) - tl, -1, -1):
                            if search[i:i+tl] == tail:
                                found = off + i + tl
                                break
                        if found != -1:
                            break
                        tail.pop(0)

                    if found != -1:
                        new = lines[found:]
                    else:
                        # Fingerprint not found - buffer was likely cleared and refilled (Relog)
                        if self.last_tail:
                            logger.info(f"ChatMonitor: Fingerprint not found in {len(lines)} lines. Assuming buffer reset.")
                        new = lines # Capture everything in the "new" buffer
                        # Ensure combat monitor has latest name
                        co.char_name = self.char_name

                    if new:
                        ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                        try:
                            # Use char_name for logging path in case it changed
                            current_safe_n = self.char_name.replace(" ", "_")
                            current_log_p = os.path.join("settings", f"{current_safe_n}_chat.log")
                            if not os.path.exists("settings"):
                                os.makedirs("settings", exist_ok=True)
                            
                            with open(current_log_p, "a", encoding="utf-8") as f:
                                for l in new:
                                    f.write(f"{ts} {l}\n")
                                    self.after(0, lambda ln=l: self.append_comms_line(ln))
                                    try:
                                        # 1. Bank Balance Tracking
                                        if self.bank_manager.process_line(l):
                                            self.after(0, self.refresh_who_footer)
                                            self.after(0, self.update_vault_ui)

                                        # 2. Skill Improvement Tracking
                                        g = tr.process_line(l)
                                        if g:
                                            logger.info(f"ChatMonitor: Skill improvement: {g['name']}")
                                            self.after(0, lambda gn=g: self.on_gain_detected(gn))
                                        if self.is_combat_line(l):
                                            r = co.process_line(l)
                                            if r:
                                                if r["type"] == "KILL":
                                                    logger.info(f"ChatMonitor: Kill Detected: {r['name']}")
                                                    self.after(0, lambda res=r: self.on_kill_detected(res))
                                                elif r["type"] == "PK_ALERT":
                                                    logger.info("ChatMonitor: PK ALERT TRIGGERED!")
                                                    self.after(0, self.trigger_pk_alert)
                                    except:
                                        pass
                                f.flush()
                        except Exception as e:
                            logger.error(f"ChatMonitor: Failed to write to log file: {e}")
                        
                        # Update fingerprint
                        for l in new:
                            self.last_tail.append(l)
                        self.last_tail = self.last_tail[-50:]

                except Exception as e:
                    # Handle temporary access issues during login transitions
                    if "Access is denied" in str(e) or "The handle is invalid" in str(e) or (isinstance(e, pywintypes.error) and e.winerror == 1421):
                        logger.warn(f"ChatMonitor: Game state transition ({e}). Waiting...")
                        time.sleep(2)
                    else:
                        logger.error(f"ChatMonitor: Critical loop error: {e}")
                        break
                
                time.sleep(1)
            
            logger.info("ChatMonitor: Thread exiting.")
            
        threading.Thread(target=loop, daemon=True).start()

    def on_gain_detected(self, g):
        # 1. Update Dashboard List
        if self.gains_tree.exists(g['name']):
            self.gains_tree.item(g['name'], values=(g['name'], g['count'], g['delta']))
        else:
            self.gains_tree.insert("", "end", iid=g['name'], values=(g['name'], g['count'], "---"))
            
        # 2. Update Session-wide Stats
        self.total_improves += 1
        self.refresh_who_footer()

    def on_kill_detected(self, r):
        cat = r['category']
        name = r['name']
        self.session_kills[cat][name] = self.session_kills[cat].get(name, 0) + 1
        count = self.session_kills[cat][name]
        if self.kills_tree.exists(name):
            self.kills_tree.item(name, values=(name, count))
        else:
            self.kills_tree.insert("", "end", iid=name, values=(name, count))
        self.update_book_tree(cat)

    def update_book_tree(self, ktype):
        w = self.book_widgets[ktype]
        tr = w["tree"]
        fv = w["filter_var"]
        ft = fv.get().lower()
        for i in tr.get_children():
            tr.delete(i)
        vics = set(self.all_time_kills[ktype].keys()) | set(self.session_kills[ktype].keys())
        for v in sorted(list(vics)):
            if ft in v.lower():
                at = self.all_time_kills[ktype].get(v, 0)
                se = self.session_kills[ktype].get(v, 0)
                
                tr.insert("", "end", values=(v, max(at, se), f"+{se}" if se > 0 else ""))

    def on_closing(self):
        self.is_running = False
        self.save_settings()
        if self.who_list_docked.get():
            self.unregister_appbar()
        if self.who_list_monitor:
            self.who_list_monitor.stop()
        if self.target_pid:
            release_pid(self.target_pid)
        self.destroy()

    def show_instance_selection_ui(self, instances):
        """Displays a modal popup when multiple unclaimed games are found."""
        logger.info(f"UI: Prompting user for instance selection from {len(instances)} options.")
        
        popup = tk.Toplevel(self)
        popup.title("Select Game Instance")
        
        # Scale window geometry for DPI
        w, h = self.scale_px(550), self.scale_px(450)
        popup.geometry(f"{w}x{h}")
        popup.minsize(w, h)
        popup.attributes("-topmost", True)
        popup.grab_set() # Modal
        
        tk.Label(popup, text="Multiple unclaimed games detected.", font=("Arial", 11, "bold"), pady=10).pack(side="top")
        tk.Label(popup, text="Please select the instance you want this Companion to control:", font=("Arial", 9)).pack(side="top", pady=(0, 10))
        
        # Bottom Button Frame (Pack this first to pin to bottom)
        btn_f = tk.Frame(popup)
        btn_f.pack(side="bottom", fill="x", pady=20)
        
        # Center Treeview Frame (Pack last with expand=True to fill middle)
        frame = tk.Frame(popup)
        frame.pack(side="top", fill="both", expand=True, padx=20, pady=5)
        
        # Treeview for selection
        tree = ttk.Treeview(frame, columns=("PID", "Character", "Location"), show="headings", height=8)
        tree.heading("PID", text="PID")
        tree.heading("Character", text="Character")
        tree.heading("Location", text="Location")
        tree.column("PID", width=self.scale_px(70), anchor="center")
        tree.column("Character", width=self.scale_px(150), anchor="w")
        tree.column("Location", width=self.scale_px(250), anchor="w")
        tree.pack(side="left", fill="both", expand=True)
        
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        sb.pack(side="right", fill="y")
        tree.configure(yscrollcommand=sb.set)
        
        for inst in instances:
            # Parse location from title if possible
            title = inst["title"]
            location = title.split(" --- ", 1)[1] if " --- " in title else "Select Screen"
            char_name = inst.get("char_name", "Unknown")
            tree.insert("", "end", iid=str(inst["pid"]), values=(inst["pid"], char_name, location))

        # NEW: Background scanner for identity
        def background_identity_scan():
            try:
                from m59_scraper import capture_identity
                for inst in instances:
                    if not popup.winfo_exists(): return

                    # Only scan if we don't already have a valid name
                    if inst.get("char_name") in ["Unscanned", "Unknown", "..."]:
                        name = capture_identity(inst["hwnd"], inst["pid"])
                        if name and popup.winfo_exists():
                            if not hasattr(self, 'pre_scanned_names'): self.pre_scanned_names = {}
                            self.pre_scanned_names[inst["pid"]] = name
                            # Update the specific row in the Treeview via the main thread
                            self.after(0, lambda p=inst["pid"], n=name: tree.set(str(p), "Character", n))
            except Exception as e:
                logger.error(f"UI: Background identity scan failed: {e}")

        threading.Thread(target=background_identity_scan, daemon=True).start()

        def on_select():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Selection", "Please select an instance from the list.", parent=popup)
                return
            
            selected_pid = int(selected[0])
            logger.info(f"UI: User selected PID {selected_pid}.")
            
            if self.lifecycle.assign_instance(selected_pid):
                popup.destroy()
            else:
                messagebox.showerror("Error", "Could not attach to that instance. It might have been claimed or closed.", parent=popup)
                # Refresh list if it failed
                unclaimed = get_unclaimed_instances()
                if not unclaimed:
                    popup.destroy()
                else:
                    for i in tree.get_children(): tree.delete(i)
                    for i in unclaimed: tree.insert("", "end", iid=str(i["pid"]), values=(i["pid"], i.get("char_name", "Unknown"), i["title"]))
        
        tk.Button(btn_f, text=" CONNECT TO SELECTED ", command=on_select, 
                  bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), padx=20, pady=5).pack()
        
        # If the popup is closed without selection, we resume auto-searching
        def on_popup_close():
            logger.info("UI: Instance selection cancelled by user.")
            self.lifecycle.pause_auto_attach = False
            popup.destroy()
            
        popup.protocol("WM_DELETE_WINDOW", on_popup_close)

    def trigger_sync(self):
        self.sync_btn.config(state="disabled")
        self.debug_log("SYNC", "Starting manual sync cycle...")
        threading.Thread(target=self.perform_sync, daemon=True).start()

    def perform_sync(self):
        self.sync_in_progress = True
        try:
            mr = MemoryReader(self.pm_obj)
            kn, st = cycle_tabs_and_scrape(self.main_hwnd, mr)
            if kn or st:
                # Mark as initially synced now that we have data
                self.initial_sync_done = True
                self.after(0, lambda: self._apply_sync_results(kn, st))
        except Exception as e:
            logger.error(f"Sync: Automatic sync error: {e}")
        finally:
            self.sync_in_progress = False
            self.after(100, self.hide_waiting_overlay)
            self.after(0, lambda: self.sync_btn.config(state="normal"))

    def _apply_sync_results(self, kn, st):
        logger.info(f"Sync: Data received - Skills: {len(kn) if kn else 0}, Stats: {len(st) if st else 0}")
        
        if st:
            # High-Verbosity Data Dump
            if self.debug_enabled.get():
                dump = ", ".join([f"{k}:{v}" for k, v in st.items()])
                self.debug_log("DATA", f"Full Stat Dump: {dump}")

            for k, v in st.items():
                # 1. Update HUD Vitals (HP/MP/VG)
                if k in self.hud_values:
                    self.hud_values[k].config(text=str(v))
                
                # 2. Update Attributes (Might/Int/etc)
                if k in self.attr_labels:
                    self.current_attributes[k] = v
                    self.attr_labels[k].config(text=str(v))

        if kn:
            self.knowledge_cache.update(kn)
        
        self.update_progression_tab()

    def update_progression_tab(self):
        if not self.knowledge_cache:
            return
        
        intellect = self.current_attributes.get("Intellect", 25)
        logger.debug(f"Calc: Processing progression (Intellect: {intellect})")
        if self.debug_enabled.get():
            self.debug_log("DATA", f"Knowledge Cache: {self.knowledge_cache}")

        exp = {self.prog_tree.item(i)['text'] for i in self.prog_tree.get_children() if self.prog_tree.item(i, 'open')}
        res = self.calculator.calculate_progression(self.knowledge_cache, intellect)
        
        for i in self.prog_tree.get_children():
            self.prog_tree.delete(i)
            
        for r in res:
            name = r['name']
            is_open = name in exp

            # Handle Mastered Display
            if r.get('mastered'):
                val_tuple = ("Level 6", "MASTERED", "---", "---")
            elif r['needed'] == 0:
                val_tuple = (f"Level {r['current_lvl']}", f"{r['current_sum']}%", f"{r['target_sum']}%", "YOU QUALIFY!")
            else:
                val_tuple = (f"Level {r['current_lvl']}", f"{r['current_sum']}%", f"{r['target_sum']}%", f"{r['needed']}%")

            p = self.prog_tree.insert("", "end", text=name, values=val_tuple, open=is_open)

            sd = self.calculator.schools.get(name, {})
            for l in range(1, 7):
                lk = f"Level_{l}"
                if lk in sd:
                    for s in sd[lk]:
                        if s.lower() in self.knowledge_cache:
                            self.prog_tree.insert(p, "end", text=f"  {s}", 
                                                 values=(f"L{l}", f"{self.knowledge_cache[s.lower()]}%", "", ""))

    def trigger_vault_scan(self, vt):
        rm = {"barloque": "Office of the Barloque Vaultman", "hungry": "The Hungry Vaults"}
        cur = self.get_current_room()
        logger.info(f"Vault: Validating location for {vt} scan. Current: {cur}")
        
        # Language-Independent relaxation:
        # If the room name doesn't match the English default, warn but allow bypass.
        if rm.get(vt) and rm[vt].lower() not in cur.lower():
            msg = f"Your current location '{cur}' does not match the expected vault room '{rm[vt]}'.\n\n"
            msg += "If you are on a non-English client or have already opened the vault window, you can 'Bypass' to attempt the scan anyway.\n\n"
            msg += "Attempt scan?"
            if not messagebox.askyesno("Vault Location Warning", msg):
                return
        elif not messagebox.askyesno("Scan", f"Scan {vt} vault?"):
            return
            
        w = self.vault_widgets[vt]
        w["sync_btn"].config(state="disabled")
        threading.Thread(target=self.perform_vault_scan_thread, args=(vt,), daemon=True).start()

    def perform_vault_scan_thread(self, vt):
        logger.info(f"Vault: Starting automated scan of {vt} vault...")
        try:
            inv = perform_vault_scan(self.main_hwnd, self.char_name, vt, lambda c, t, i, q: self.after(0, lambda: self.status_var.set(f"Scan: {c}/{t}")))
            if inv:
                logger.info(f"Vault: Scan complete. Found {len(inv)} items.")
                self.after(0, lambda: self._apply_vault_results(vt, inv))
        except Exception as e:
            logger.error(f"Vault: Scan error: {e}")
        finally:
            self.after(0, lambda: self.vault_widgets[vt]["sync_btn"].config(state="normal"))

    def _apply_vault_results(self, vt, inv):
        self.vault_data[vt] = inv
        self.update_vault_tree(vt)
        self.vault_widgets[vt]["status_lbl"].config(text=f"Last Scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def update_vault_tree(self, vt):
        w = self.vault_widgets[vt]
        tr = w["tree"]
        fv = w["filter_var"]
        for i in tr.get_children():
            tr.delete(i)
        for i in self.vault_data[vt]:
            if fv.get().lower() in i['item'].lower():
                tr.insert("", "end", values=(i['item'], i['quantity']))

    def load_vault_cache(self):
        if self.char_name == "Unknown":
            return
        sn = get_safe_name(self.char_name)
        for vt in ["barloque", "hungry"]:
            p = next((x for x in [f"settings/{sn}_vault_{vt}.json"] if os.path.exists(x)), None)
            if p:
                try:
                    with open(p, "r") as f:
                        d = json.load(f)
                        self.vault_data[vt] = d.get("items", [])
                        self.update_vault_tree(vt)
                except:
                    pass

    def load_kill_book(self):
        if self.char_name == "Unknown":
            return
        sn = get_safe_name(self.char_name)
        p = f"settings/{sn}_kills.json"
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    d = json.load(f)
                    from m59_combat import CombatMonitor
                    tm = CombatMonitor(self.char_name)
                    self.all_time_kills = {"monsters": {}, "players": {}}
                    for cat in ["monsters", "players"]:
                        for v, c in d.get(cat, {}).items():
                            l = v.lower()
                            is_m = l in tm.mob_set or (l.startswith("the ") and l[4:] in tm.mob_set) or (l.startswith("a ") and l[2:] in tm.mob_set)
                            nc = "monsters" if is_m else "players"
                            self.all_time_kills[nc][v] = self.all_time_kills[nc].get(v, 0) + c
                self.update_book_tree("monsters")
                self.update_book_tree("players")
            except:
                pass

    def get_current_room(self):
        if not self.main_hwnd:
            return "Unknown"
        t = win32gui.GetWindowText(self.main_hwnd)
        # Format: Meridian 59 --- [ROOM NAME]
        return t.split(" --- ", 1)[1].strip() if " --- " in t else "Unknown Location"

    def background_update_check(self):
        def check():
            u, rv, notes = check_for_updates(self.version)
            if not u: 
                self.after(0, self.establish_connection)
                return
            def show_prompt():
                msg = f"v{rv} available.\n\n"
                if notes:
                    msg += f"Release Notes:\n{notes}\n\n"
                msg += "Update?"
                choice = messagebox.askquestion("Update", msg, icon="info", type="yesnocancel")
                if choice == "yes":
                    self.status_var.set("Updating...")
                    from m59_updater import download_update, apply_update
                    new_path = download_update()
                    if new_path:
                        apply_update(new_path)
                    else:
                        self.after(0, self.establish_connection)
                else:
                    self.after(0, self.establish_connection)
            self.after(0, show_prompt)
        threading.Thread(target=check, daemon=True).start()

    def find_all_instances(self):
        insts = []
        def cb(h, e):
            if win32gui.IsWindowVisible(h) and "Meridian 59" in win32gui.GetWindowText(h):
                _, p = win32process.GetWindowThreadProcessId(h)
                try:
                    if psutil.Process(p).name().lower() == self.target_name.lower():
                        insts.append({"pid": p, "title": win32gui.GetWindowText(h), "hwnd": h})
                except:
                    pass
        win32gui.EnumWindows(cb, None)
        return insts

    def browse_pk_sound(self):
        p = filedialog.askopenfilename(filetypes=[("Wave files", "*.wav")])
        if p:
            # If the path is within the current working directory, make it relative
            try:
                rel_p = os.path.relpath(p, os.getcwd())
                if not rel_p.startswith(".."):
                    p = rel_p
            except:
                pass
            self.pk_sound_path.set(p)

    def test_pk_sound(self):
        p = self.pk_sound_path.get()
        try:
            if p.startswith("System"):
                winsound.PlaySound(p, winsound.SND_ALIAS | winsound.SND_ASYNC)
            else:
                # Resolve path if relative
                if not os.path.isabs(p):
                    p = resource_path(p)
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except:
            pass

    def browse_tell_sound(self):
        p = filedialog.askopenfilename(filetypes=[("Wave files", "*.wav")])
        if p:
            try:
                rel_p = os.path.relpath(p, os.getcwd())
                if not rel_p.startswith(".."):
                    p = rel_p
            except:
                pass
            self.tell_sound_path.set(p)

    def test_tell_sound(self):
        p = self.tell_sound_path.get()
        try:
            if p.startswith("System"):
                winsound.PlaySound(p, winsound.SND_ALIAS | winsound.SND_ASYNC)
            else:
                if not os.path.isabs(p):
                    p = resource_path(p)
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except:
            pass

    def show_waiting_overlay(self, mode="searching"):
        """Displays a splash screen and keeps the main UI hidden until initialization is complete."""
        try:
            # Keep main window completely invisible during initialization
            self.attributes("-alpha", 0.0)
        except: pass

        if self.waiting_overlay and self.waiting_overlay.winfo_exists():
            # Update existing overlay text
            if mode == "login":
                self.waiting_title_lbl.config(text=" ↻  WAITING FOR LOGIN ", fg="#64B5F6")
                self.waiting_msg_lbl.config(text="Please select a character and enter the world")
            elif mode == "initializing":
                self.waiting_title_lbl.config(text=" ↻  INITIALIZING ", fg="#FFCA28")
                self.waiting_msg_lbl.config(text="Synchronizing game state...")
            else:
                self.waiting_title_lbl.config(text=" ↻  SCANNING FOR GAME ", fg="#81C784")
                self.waiting_msg_lbl.config(text="Please launch Meridian 59 to continue")
            self.waiting_overlay.update_idletasks()
            return
            
        logger.info(f"UI: Displaying 'Splash' overlay (Mode: {mode}).")
        
        overlay = tk.Toplevel(self)
        overlay.title("M59 Companion - Connecting...")
        
        # Center the splash screen on the screen
        window_width = 580
        window_height = 260
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        
        overlay.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")
        overlay.resizable(False, False)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        
        try: overlay.attributes("-alpha", 0.95)
        except: pass
            
        overlay.configure(bg="#0F0F0F")
        
        # Inner padding frame
        inner = tk.Frame(overlay, bg="#181818", highlightthickness=1, highlightbackground="#333333")
        inner.pack(expand=True, fill="both", padx=2, pady=2)
        
        tk.Label(inner, text="M59 COMPANION", font=("Segoe UI", 22, "bold"), fg="#FFFFFF", bg="#181818").pack(pady=(35, 10))
        
        if mode == "initializing":
            title_text = " ↻  INITIALIZING "
            title_color = "#FFCA28"
            msg_text = "Synchronizing game state..."
        elif mode == "login":
            title_text = " ↻  WAITING FOR LOGIN "
            title_color = "#64B5F6"
            msg_text = "Please select a character and enter the world"
        else:
            title_text = " ↻  SCANNING FOR GAME "
            title_color = "#81C784"
            msg_text = "Please launch Meridian 59 to continue"
        
        self.waiting_title_lbl = tk.Label(inner, text=title_text, font=("Segoe UI", 12, "bold"), fg=title_color, bg="#181818", pady=5)
        self.waiting_title_lbl.pack()
        
        self.waiting_msg_lbl = tk.Label(inner, text=msg_text, font=("Segoe UI", 10), fg="#B0B0B0", bg="#181818")
        self.waiting_msg_lbl.pack(pady=(5, 15))
        
        self.waiting_overlay = overlay

    def hide_waiting_overlay(self):
        """Materializes the main UI and destroys the splash screen."""
        if getattr(self, "_is_materializing", False):
            return
            
        if self.waiting_overlay:
            try:
                if self.waiting_overlay.winfo_exists():
                    logger.info("UI: Materializing main interface...")
                    self._is_materializing = True
                    try: self.deiconify()
                    except: pass
                    self._materialize_ui(self.waiting_overlay, 0.0)
                    return
            except:
                pass
            self.waiting_overlay = None
            
        # Fallback if no overlay
        try:
            self.deiconify()
            self.attributes("-alpha", 1.0)
        except: pass

    def _materialize_ui(self, overlay, main_alpha):
        if main_alpha < 1.0:
            main_alpha += 0.05  # Slower fade
            if main_alpha > 1.0:
                main_alpha = 1.0
            
            try:
                self.attributes("-alpha", main_alpha)
                
                # Keep splash fully opaque until main UI is partially visible to avoid black flashes
                splash_alpha = 1.0
                if main_alpha > 0.3:
                    splash_alpha = 1.0 - ((main_alpha - 0.3) / 0.7)
                
                if splash_alpha < 0: splash_alpha = 0.0
                overlay.attributes("-alpha", splash_alpha)
                
                self.after(30, self._materialize_ui, overlay, main_alpha)
            except Exception as e:
                logger.error(f"UI Fade Error: {e}")
                self.attributes("-alpha", 1.0)
                try: overlay.destroy()
                except: pass
                self.waiting_overlay = None
                self._is_materializing = False
        else:
            try:
                overlay.destroy()
            except:
                pass
            self.attributes("-alpha", 1.0)
            self.waiting_overlay = None
            self._is_materializing = False
            logger.info("UI: Interface completely materialized.")

if __name__ == "__main__":
    # Enable High DPI awareness to fix scaling issues with AppBar and screen coordinates
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        # PROCESS_SYSTEM_DPI_AWARE = 1
        # Try per-monitor awareness first
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except:
        try:
            # Fallback to system-level awareness
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            try:
                # Legacy fallback
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass
            
    app = M59Dashboard()
    app.mainloop()
