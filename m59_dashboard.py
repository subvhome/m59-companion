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
from datetime import datetime

# Import centralized logging
from m59_logging import setup_logging, get_logger
logger = get_logger("dashboard")

# Import modules
from m59_bridge import establish_bridge, release_pid, find_available_instance, claim_pid, get_unclaimed_instances
from m59_scraper import capture_identity, get_blakgraph_stats, cycle_tabs_and_scrape, get_text_from_hwnd, MemoryReader
from m59_tracker import SessionTracker
from m59_combat import CombatMonitor
from m59_calculator import SchoolCalculator
from m59_vault import perform_vault_scan, find_nested_control
from m59_updater import check_for_updates
from m59_gps import GPSManager
from m59_lifecycle import InstanceManager

SETTINGS_FILE = "gui_settings.json"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

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
        self.version = "0.00"
        try:
            v_p = resource_path("VERSION")
            if os.path.exists(v_p):
                with open(v_p, "r") as f:
                    self.version = f.read().strip()
        except:
            pass
        
        self.title(f"M59 Companion v{self.version}")
        self.geometry("1100x850")
        
        # --- Settings ---
        self.pk_alert_enabled = tk.BooleanVar(value=True)
        self.pk_sound_enabled = tk.BooleanVar(value=True)
        self.pk_frame_enabled = tk.BooleanVar(value=True)
        self.pk_sound_path = tk.StringVar(value="SystemExclamation")
        self.debug_enabled = tk.BooleanVar(value=False)
        self.debug_enabled.trace_add("write", lambda *a: setup_logging(self.debug_enabled.get()))
        self.gps_discovery_enabled = tk.BooleanVar(value=False)
        
        # --- Who List State ---
        self.who_list_enabled = tk.BooleanVar(value=True)
        self.who_list_side = tk.StringVar(value="Right")
        self.who_list_players = {} # Dict of {name: status}
        self.frida_session = None
        self.frida_script = None
        
        # --- Chat Filtering State ---
        self.static_filters = {
            "Combat": tk.BooleanVar(value=True),
            "Kills": tk.BooleanVar(value=True),
            "Spells": tk.BooleanVar(value=True),
            "Social": tk.BooleanVar(value=True),
            "Private": tk.BooleanVar(value=True),
            "Broadcasts": tk.BooleanVar(value=True),
            "Improves": tk.BooleanVar(value=True),
            "System": tk.BooleanVar(value=True)
        }
        self.custom_filters = [] # List of dicts: {"label": str, "keywords": list, "var": BooleanVar}
        
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
        self.all_lines = [] # Master list for live filtering
        self.history_buffer = [] # Buffer for historical log filtering
        self.comms_mode = "live" # 'live' or 'history'
        self.gps_manager = GPSManager()
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
        import re
        self.re_speech = re.compile(r'^(.*?) (?:broadcasts?|tells?|says?|yells?|sends?), "(.*)"$', re.I)
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
            "blocks", "dodges", "parries", "avoids", "nicks", "fails to damage"
        }

        self.session_kills = {"monsters": {}, "players": {}}
        self.all_time_kills = {"monsters": {}, "players": {}}
        self.last_tail = []
        self.refresh_counter = 10
        self.knowledge_cache = {}
        self.current_attributes = {}
        self.vault_data = {"barloque": [], "hungry": []}
        self.calculator = SchoolCalculator()
        self.sync_in_progress = False

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
        tabs = [("Dashboard", "dash"), ("Communications", "comms"), ("GPS", "gps"), ("Progression", "prog"), ("Vault", "vault"), ("Kill Book", "book"), ("Settings", "settings")]
        for name, key in tabs:
            f = tk.Frame(self.notebook, bg="#f0f0f0")
            setattr(self, f"tab_{key}", f)
            self.notebook.add(f, text=f" {name} ")
        
        self.setup_tab_dashboard()
        self.setup_tab_communications()
        self.setup_tab_gps()
        self.setup_tab_progression()
        self.setup_tab_vault()
        self.setup_tab_book()
        self.setup_tab_settings()
        
        # Apply initial side panel state
        self.update_who_list_visibility()
        
        self.minsize(400, 300)
        self.after(100, self.background_update_check)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def is_combat_line(self, line):
        l = line.lower()
        for verb in self.combat_verbs:
            if f" {verb} " in l or l.endswith(f" {verb}."):
                return True
        if l.startswith("you ") and any(v in l for v in ["block", "dodge", "parry", "avoid"]):
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
                    self.debug_enabled.set(s.get("debug_enabled", False))
                    self.gps_discovery_enabled.set(s.get("gps_discovery_enabled", False))
                    self.who_list_enabled.set(s.get("who_list_enabled", True))
                    self.who_list_side.set(s.get("who_list_side", "Right"))
                    
                    # Restore Static Filters
                    sf = s.get("static_filters", {})
                    for name, val in sf.items():
                        if name in self.static_filters:
                            self.static_filters[name].set(val)
                            
                    # Restore Custom Filters
                    cf = s.get("custom_filters", [])
                    self.custom_filters = []
                    for f in cf:
                        self.custom_filters.append({
                            "label": f["label"],
                            "keywords": f["keywords"],
                            "var": tk.BooleanVar(value=f.get("enabled", True))
                        })
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")

    def save_settings(self):
        try:
            # Prepare Custom Filters for JSON
            cf_save = []
            for f in self.custom_filters:
                cf_save.append({
                    "label": f["label"],
                    "keywords": f["keywords"],
                    "enabled": f["var"].get()
                })
                
            # Prepare Static Filters for JSON
            sf_save = {name: var.get() for name, var in self.static_filters.items()}

            with open(SETTINGS_FILE, "w") as f:
                json.dump({
                    "geometry": self.geometry(),
                    "pk_alert_enabled": self.pk_alert_enabled.get(),
                    "pk_sound_enabled": self.pk_sound_enabled.get(),
                    "pk_frame_enabled": self.pk_frame_enabled.get(),
                    "pk_sound_path": self.pk_sound_path.get(),
                    "debug_enabled": self.debug_enabled.get(),
                    "gps_discovery_enabled": self.gps_discovery_enabled.get(),
                    "who_list_enabled": self.who_list_enabled.get(),
                    "who_list_side": self.who_list_side.get(),
                    "static_filters": sf_save,
                    "custom_filters": cf_save
                }, f)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def debug_log(self, category, message):
        """Wrapper for centralized logging, keeping the legacy category-based signature."""
        logger.debug(f"[{category}] {message}")

    def gps_log(self, message):
        if self.debug_enabled.get() or self.gps_discovery_enabled.get():
            self.debug_log("GPS", message)

    def setup_who_list_panel(self):
        # Premium dark slate themed container
        self.who_list_panel = tk.Frame(self.main_container, bg="#2b2d31", bd=1, relief=tk.SOLID)
        
        # Polished Title Header (not all caps)
        self.who_list_header = tk.Label(
            self.who_list_panel, text="Online Players", font=("Segoe UI", 10, "bold"), 
            bg="#1e1f22", fg="#4CAF50", pady=7, bd=0
        )
        self.who_list_header.pack(fill="x")
        
        # Bottom Count Label
        self.who_list_count_lbl = tk.Label(
            self.who_list_panel, text="0 Online", font=("Segoe UI", 9, "bold"), 
            bg="#1e1f22", fg="#888", pady=5, bd=0
        )
        self.who_list_count_lbl.pack(side="bottom", fill="x")
        
        # Main text view with Discord-style dark background
        self.who_list_text = tk.Text(
            self.who_list_panel, bg="#2b2d31", fg="#e0e0e0", 
            font=("Consolas", 10), state="disabled", 
            width=25, bd=0, padx=8, pady=5, wrap="none"
        )
        self.who_list_text.pack(side="left", fill="both", expand=True)
        
        # Styled scrollbar
        sb = ttk.Scrollbar(self.who_list_panel, orient="vertical", command=self.who_list_text.yview)
        sb.pack(side="right", fill="y")
        self.who_list_text.config(yscrollcommand=sb.set)
        
        # High-legibility foreground tags tailored for the dark slate background
        self.who_list_text.tag_config("INNOCENT", foreground="#e0e0e0")
        self.who_list_text.tag_config("OUTLAW", foreground="#ff9f43")    # Rich Orange
        self.who_list_text.tag_config("MURDERER", foreground="#ff6b6b")  # Soft bright Red
        self.who_list_text.tag_config("STAFF", foreground="#48dbfb")     # Sky Blue

    def update_who_list_visibility(self):
        self.who_list_panel.pack_forget()
        self.notebook.pack_forget()
        if self.who_list_enabled.get():
            side = self.who_list_side.get().lower()
            self.who_list_panel.pack(side=side, fill="y", padx=2)
            if self.target_pid:
                self.start_who_list_monitor()
        self.notebook.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    def safe_refresh_who_list(self):
        """Sends a /who command to the game safely using Windows messages."""
        if not self.main_hwnd or not self.who_list_enabled.get():
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
        """Initializes Frida hook for real-time population tracking using safe, passive interception."""
        if not self.target_pid or not self.who_list_enabled.get():
            return
            
        if self.frida_session:
            return 
            
        def run_frida():
            try:
                import frida
                logger.info(f"WhoList: Attaching Passive Listener to PID {self.target_pid}...")
                session = frida.attach(self.target_pid)
                self.frida_session = session
                
                # Dynamic ASLR-resilient interception + Safe RPC trigger (Robust Engine v1.6).
                js_code = """
                let baseAddress = null;
                let moduleNameActual = "";

                // Dynamically find the primary game module regardless of string casing
                const modules = Process.enumerateModules();
                for (let i = 0; i < modules.length; i++) {
                    const nameLower = modules[i].name.toLowerCase();
                    if (nameLower === "meridian.exe") {
                        baseAddress = modules[i].base;
                        moduleNameActual = modules[i].name;
                        break;
                    }
                }

                // Ultimate Fallback: if enumeration fails to filter, pick the first loaded module
                if (!baseAddress && modules.length > 0) {
                    baseAddress = modules[0].base;
                    moduleNameActual = modules[0].name;
                }

                if (!baseAddress) {
                    send({type: 'log', message: 'ERROR: Unable to determine target module base address.'});
                } else {
                    send({type: 'log', message: 'Target Module Found: ' + moduleNameActual + ' @ ' + baseAddress});
                    
                    // Offsets: LookupMessage = 0x277d0, ToServer = 0x74e0
                    const addrLookup = baseAddress.add(0x277d0);
                    const addrToServer = baseAddress.add(0x74e0);
                    
                    const PF_MASK = 0x0000C000;
                    let playerCache = {}; 

                    function getStatus(flags) {
                        const playerFlags = flags & PF_MASK;
                        if (playerFlags === 0xC000) return "STAFF";
                        if (playerFlags === 0x8000) return "OUTLAW";
                        if (playerFlags === 0x4000) return "MURDERER";
                        return "INNOCENT";
                    }

                    try {
                        Interceptor.attach(addrLookup, {
                            onEnter: function (args) {
                                try {
                                    const buffer = args[0];
                                    if (buffer.isNull()) return;
                                    const packetType = buffer.readU8();

                                    if (packetType === 136) { // Population List
                                        const count = buffer.add(1).readU16();
                                        let pos = buffer.add(3);
                                        let players = [];
                                        for (let i = 0; i < count; i++) {
                                            try {
                                                const objId = pos.readU32();
                                                const nameLen = pos.add(8).readU16();
                                                const name = pos.add(10).readUtf8String(nameLen);
                                                const flags = pos.add(10 + nameLen).readU32();
                                                const status = getStatus(flags);
                                                if (name) {
                                                    playerCache[objId] = { name: name, status: status };
                                                    players.push({ name: name, status: status });
                                                }
                                                pos = pos.add(14 + nameLen);
                                            } catch (e) { break; }
                                        }
                                        send({type: 'list', data: players});
                                    } 
                                    else if (packetType === 137) { // Logon
                                        try {
                                            const objId = buffer.add(1).readU32();
                                            const nameLen = buffer.add(9).readU16();
                                            const name = buffer.add(11).readUtf8String(nameLen);
                                            const flags = buffer.add(11 + nameLen).readU32();
                                            const status = getStatus(flags);
                                            if (name) {
                                                playerCache[objId] = { name: name, status: status };
                                                send({type: 'logon', name: name, status: status});
                                            }
                                        } catch (e) {}
                                    }
                                    else if (packetType === 138) { // Logoff
                                        try {
                                            const objId = buffer.add(1).readU32();
                                            if (playerCache[objId]) {
                                                const p = playerCache[objId];
                                                send({type: 'logoff', name: p.name});
                                                delete playerCache[objId];
                                            }
                                        } catch (e) {}
                                    }
                                } catch (e) {}
                            }
                        });
                        send({type: 'log', message: 'LookupMessage Interceptor hook active.'});
                    } catch (err) {
                        send({type: 'log', message: 'ERROR: Hooking LookupMessage failed: ' + err.message});
                    }
                    
                    // Expose safe trigger via RPC (defined on the global scope)
                    rpc.exports = {
                        triggerupdate: function() {
                            try {
                                const fnToServer = new NativeFunction(addrToServer, 'void', ['uint8', 'pointer'], 'default');
                                fnToServer(44, ptr(0));
                                return true;
                            } catch (e) {
                                return false;
                            }
                        }
                    };
                }
                """
                
                script = session.create_script(js_code)
                self.frida_script = script
                
                def on_message(message, data):
                    if message['type'] == 'send':
                        payload = message['payload']
                        if isinstance(payload, dict) and payload.get('type') == 'log':
                            logger.error(f"FridaLog: {payload.get('message')}")
                        else:
                            self.after(0, lambda: self.process_who_list_message(payload))
                            
                script.on('message', on_message)
                script.load()
                logger.info("WhoList: Passive Listener active and RPC exported.")
                
                # Check if we are already logged in when the script finishes loading
                if self.char_name != "Unknown":
                    self.after(1500, self.trigger_silent_who_update)
                
            except Exception as e:
                logger.error(f"WhoList: Frida Error: {e}")
                self.frida_session = None

        threading.Thread(target=run_frida, daemon=True).start()

    def process_who_list_message(self, payload):
        if not isinstance(payload, dict): return
        
        ptype = payload.get('type')
        if ptype == 'list':
            self.who_list_players = {p['name']: p['status'] for p in payload['data']}
        elif ptype == 'logon':
            self.who_list_players[payload['name']] = payload['status']
        elif ptype == 'logoff':
            self.who_list_players.pop(payload['name'], None)
            
        self.refresh_who_list_ui()

    def trigger_silent_who_update(self):
        """Triggers the silent population update via Frida RPC."""
        if not self.who_list_enabled.get() or not self.frida_script:
            return
            
        if getattr(self, "sync_in_progress", False):
            logger.info("WhoList: Tab Dance Sync is running, deferring silent population update...")
            self.after(1500, self.trigger_silent_who_update)
            return
            
        def run():
            try:
                logger.info("WhoList: Sending safe native trigger for population update...")
                self.frida_script.exports.triggerupdate()
            except Exception as e:
                logger.error(f"WhoList: Failed to invoke silent update: {e}")
                
        threading.Thread(target=run, daemon=True).start()

    def refresh_who_list_ui(self):
        if not self.who_list_enabled.get(): return
        self.who_list_text.config(state="normal")
        self.who_list_text.delete("1.0", tk.END)
        
        # Sort alphabetically case-insensitively
        sorted_names = sorted(self.who_list_players.keys(), key=str.lower)
        
        # Calculate dynamic width to prevent wrapping (min 15, max 40)
        max_len = 15
        for name in sorted_names:
            max_len = max(max_len, len(name) + 3) # Name + leading space + padding
            
        max_len = min(40, max_len)
        self.who_list_text.config(width=max_len)
        
        for name in sorted_names:
            status = self.who_list_players[name]
            self.who_list_text.insert(tk.END, f" {name}\n", status)
            
        self.who_list_text.config(state="disabled")
        
        # Update dynamic player count at the bottom
        count = len(sorted_names)
        self.who_list_count_lbl.config(text=f"{count} Online", fg="#4CAF50" if count > 0 else "#888")

    def setup_tab_communications(self):
        paned = ttk.PanedWindow(self.tab_comms, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        sidebar = tk.Frame(paned, bg="#f0f0f0")
        paned.add(sidebar, weight=1)
        
        # --- Static Filters Section ---
        tk.Label(sidebar, text=" CHAT FILTERS ", font=("Arial", 9, "bold"), bg="#ddd").pack(fill="x", pady=(0, 5))
        f_scroll_f = tk.Frame(sidebar, bg="#f0f0f0")
        f_scroll_f.pack(fill="x")
        
        static_f = tk.Frame(f_scroll_f, bg="#f0f0f0")
        static_f.pack(fill="x", padx=5)
        
        for name, var in self.static_filters.items():
            cb = tk.Checkbutton(static_f, text=name, variable=var, bg="#f0f0f0", anchor="w", 
                                command=self.refresh_comms_view)
            cb.pack(fill="x")
            
        # --- Custom Filters Section ---
        tk.Label(sidebar, text=" CUSTOM KEYWORDS ", font=("Arial", 9, "bold"), bg="#ddd").pack(fill="x", pady=(15, 5))
        self.custom_filters_frame = tk.Frame(sidebar, bg="#f0f0f0")
        self.custom_filters_frame.pack(fill="x", padx=5)
        self.rebuild_custom_filters_ui()
        
        # --- Add Filter Input ---
        add_f = tk.Frame(sidebar, bg="#f0f0f0")
        add_f.pack(fill="x", padx=5, pady=5)
        
        row1 = tk.Frame(add_f, bg="#f0f0f0")
        row1.pack(fill="x")
        self.new_filter_entry = tk.Entry(row1, font=("Arial", 9))
        self.new_filter_entry.pack(side="left", fill="x", expand=True)
        tk.Button(row1, text=" + ", command=self.add_custom_filter, bg="#4CAF50", fg="white", font=("Arial", 9, "bold")).pack(side="left", padx=2)
        tk.Button(row1, text=" ⓘ ", command=self.show_filter_info, font=("Arial", 9)).pack(side="left")

        # --- Historical Logs ---
        tk.Label(sidebar, text=" LOG BROWSER ", font=("Arial", 9, "bold"), bg="#ddd").pack(fill="x", pady=(15, 5))
        
        # Return to Live Button
        self.live_feed_btn = tk.Button(sidebar, text=" 🟢 RETURN TO LIVE FEED ", command=self.return_to_live,
                                       bg="#E8F5E9", font=("Arial", 8, "bold"), pady=5)
        self.live_feed_btn.pack(fill="x", padx=5, pady=5)

        # Scrollable Listbox for logs
        list_f = tk.Frame(sidebar, bg="#f0f0f0")
        list_f.pack(fill="both", expand=True, padx=5)
        
        self.log_file_list = tk.Listbox(list_f, font=("Arial", 8), height=10)
        self.log_file_list.pack(side="left", fill="both", expand=True)
        self.log_file_list.bind("<<ListboxSelect>>", self.load_historical_log)
        
        sb = ttk.Scrollbar(list_f, orient="vertical", command=self.log_file_list.yview)
        sb.pack(side="right", fill="y")
        self.log_file_list.config(yscrollcommand=sb.set)
        
        btn_row = tk.Frame(sidebar, bg="#f0f0f0")
        btn_row.pack(fill="x", padx=5, pady=5)
        tk.Button(btn_row, text="Refresh List", command=self.refresh_log_list, font=("Arial", 7)).pack(side="left", fill="x", expand=True)
        tk.Button(btn_row, text="Open Folder", command=lambda: os.startfile(os.path.abspath("logs")),
                  font=("Arial", 7)).pack(side="left", fill="x", expand=True, padx=2)
        
        right = tk.Frame(paned, bg="#f0f0f0")
        paned.add(right, weight=4)
        self.comms_header_lbl = tk.Label(right, text="🟢 LIVE STREAM", font=("Arial", 11, "bold"), fg="#2E7D32", bg="#f0f0f0")
        self.comms_header_lbl.pack(pady=5)
        
        self.comms_view = scrolledtext.ScrolledText(right, bg="black", fg="#00FFFF", font=("Consolas", 10), state="disabled")
        self.comms_view.pack(fill="both", expand=True, padx=5, pady=5)

    def return_to_live(self):
        self.comms_mode = "live"
        self.comms_header_lbl.config(text="🟢 LIVE STREAM", fg="#2E7D32")
        self.live_feed_btn.config(bg="#E8F5E9") # Subtle green
        self.refresh_comms_view()

    def rebuild_custom_filters_ui(self):
        """Redraws the custom filters list in the sidebar."""
        for widget in self.custom_filters_frame.winfo_children():
            widget.destroy()
            
        for i, f in enumerate(self.custom_filters):
            row = tk.Frame(self.custom_filters_frame, bg="#f0f0f0")
            row.pack(fill="x", pady=1)
            tk.Checkbutton(row, text=f["label"], variable=f["var"], bg="#f0f0f0", anchor="w",
                           command=self.refresh_comms_view).pack(side="left", fill="x", expand=True)
            tk.Button(row, text="✕", command=lambda idx=i: self.remove_custom_filter(idx),
                      fg="red", bg="#f0f0f0", bd=0, font=("Arial", 8, "bold")).pack(side="right", padx=5)

    def add_custom_filter(self):
        raw = self.new_filter_entry.get().strip()
        if not raw: return
        
        label = simpledialog.askstring("Filter Label", "Enter a name for this filter:", parent=self)
        if not label: return
        
        # Parse keywords: handle quotes and commas
        import re
        keywords = [val.lower() for val in [m[0] or m[1] for m in re.findall(r'"([^"]*)"|([^,]+)', raw)] if val.strip()]
            
        if not keywords: return
        
        self.custom_filters.append({
            "label": label,
            "keywords": keywords,
            "var": tk.BooleanVar(value=True)
        })
        self.new_filter_entry.delete(0, tk.END)
        self.rebuild_custom_filters_ui()
        self.refresh_comms_view()
        self.save_settings()

    def remove_custom_filter(self, index):
        if 0 <= index < len(self.custom_filters):
            self.custom_filters.pop(index)
            self.rebuild_custom_filters_ui()
            self.refresh_comms_view()
            self.save_settings()

    def show_filter_info(self):
        msg = ("Filter Formatting Guide:\n\n"
               "• Single words: gold\n"
               "• Multiple words (OR): loot, gold, gems\n"
               "• Specific phrases: \"you find\"\n"
               "• Combinations: loot, \"the master\", gems\n\n"
               "Note: Filters match ANY of your terms (OR logic) and are case-insensitive.")
        messagebox.showinfo("Filter Info", msg)

    def refresh_comms_view(self):
        """Clears and repopulates the comms view based on current mode and filters."""
        self.comms_view.config(state="normal")
        self.comms_view.delete("1.0", tk.END)
        
        # Determine data source based on current mode
        source = self.all_lines if self.comms_mode == "live" else self.history_buffer
        
        # For performance, we limit display to last 2000 lines when filtering
        for ts, line in source[-2000:]:
            if self.should_show_line(line):
                self.comms_view.insert(tk.END, f"{ts} {line}\n")
                
        self.comms_view.see(tk.END)
        self.comms_view.config(state="disabled")

    def should_show_line(self, line):
        """Core logic to determine if a line matches ANY enabled filter."""
        l = line.lower()
        
        # 1. Combat & Kills
        if self.static_filters["Combat"].get() and self.is_combat_line(line): return True
        if self.static_filters["Kills"].get() and "you killed" in l: return True
        
        # 2. Spells (Include 3rd person emotes like 'murmurs' or 'makes a mystical')
        if self.static_filters["Spells"].get():
            if any(x in l for x in ["you cast", "spell fails", "mana", "murmur", "mystical gesture"]):
                return True
        
        # 3. Social (Broadened to catch all speech variations)
        if self.static_filters["Social"].get():
            # Catch "Name says," "You say," "Name yells," etc.
            if any(x in l for x in [" say", " says", " yell", " yells", " yelling", " whisper", " shouting"]):
                return True
            # Catch standard emotes and 3rd person actions
            if any(x in l for x in [" smiles ", " waves ", " bows ", " laughs ", " at you.", " to you.", " nods."]):
                return True
            
        # 4. Comms
        if self.static_filters["Private"].get() and ("tells you" in l or "you tell" in l or "sends," in l): return True
        if self.static_filters["Broadcasts"].get() and ("broadcasts," in l or "broadcasts:" in l or "shouts," in l or "shouting," in l): return True
        
        # 5. Progression
        if self.static_filters["Improves"].get() and "improved" in l: return True
        
        # 6. System (Catch-all for everything else)
        if self.static_filters["System"].get():
            # If System is on, we show everything that wasn't already caught or excluded
            return True

        # 7. Check Custom Filters
        for f in self.custom_filters:
            if f["var"].get():
                for kw in f["keywords"]:
                    if kw in l: return True
        
        return False

    def load_historical_log(self, event=None):
        selection = self.log_file_list.curselection()
        if not selection: return
        
        fn = self.log_file_list.get(selection[0])
        self.comms_mode = "history"
        self.comms_header_lbl.config(text=f"📂 HISTORY: {fn}", fg="#1565C0")
        self.live_feed_btn.config(bg="#f0f0f0") # Dim the live button
        
        path = os.path.join("logs", fn)
        try:
            self.history_buffer = []
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    # Parse timestamp if it exists [YYYY-MM-DD HH:MM:SS]
                    if line.startswith("[") and "]" in line:
                        parts = line.split("]", 1)
                        ts = parts[0] + "]"
                        msg = parts[1].strip()
                        self.history_buffer.append((ts, msg))
                    else:
                        self.history_buffer.append(("", line))
            
            self.refresh_comms_view()
        except Exception as e:
            logger.error(f"Failed to load historical log {fn}: {e}")

    def append_comms_line(self, line):
        ts = f"[{datetime.now().strftime('%H:%M:%S')}]"
        
        if self.debug_enabled.get():
            logger.debug(f"Comms: Received raw line: {line[:60]}...")

        # Save to master list
        self.all_lines.append((ts, line))
        if len(self.all_lines) > 5000:
            self.all_lines.pop(0)
        
        # Only update live view auto-scrolling if we are currently IN live mode
        if self.comms_mode == "live" and self.should_show_line(line):
            self.comms_view.config(state="normal")
            self.comms_view.insert(tk.END, f"{ts} {line}\n")
            self.comms_view.see(tk.END)
            self.comms_view.config(state="disabled")

    def refresh_log_list(self):
        if not os.path.exists("logs"):
            os.makedirs("logs", exist_ok=True)
        files = [f for f in os.listdir("logs") if f.endswith(".log") and "debug" not in f.lower()]
        files.sort(key=lambda x: os.path.getmtime(os.path.join("logs", x)), reverse=True)
        
        self.log_file_list.delete(0, tk.END)
        for f in files:
            self.log_file_list.insert(tk.END, f)

    def setup_tab_gps(self):
        """Creates the GPS Discovery tab."""
        header = tk.Frame(self.tab_gps, bg="#f0f0f0")
        header.pack(fill="x", padx=10, pady=5)
        tk.Label(header, text="World Map & GPS Discovery", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(side="left")
        
        # --- Under Construction Banner ---
        banner = tk.Frame(self.tab_gps, bg="#FFF9C4", bd=1, relief=tk.SOLID)
        banner.pack(fill="x", padx=10, pady=5)
        tk.Label(banner, text=" ⚠ FEATURE UNDER CONSTRUCTION ⚠ ", font=("Arial", 12, "bold"), bg="#FFF9C4", fg="#F57F17").pack(pady=5)
        tk.Label(banner, text="This module is currently in development and is not yet ready for public testing.", 
                 font=("Arial", 8, "italic"), bg="#FFF9C4", fg="#F57F17").pack(pady=(0, 5))
        
        cont = tk.Frame(self.tab_gps, bg="#f0f0f0")
        cont.pack(fill="both", expand=True, padx=5, pady=5)
        
        loc_f = tk.LabelFrame(cont, text=" Current Location ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        loc_f.pack(fill="x", padx=5, pady=5)
        self.gps_loc_lbl = tk.Label(loc_f, text="Detecting...", font=("Consolas", 14, "bold"), fg="#1565C0", bg="#f0f0f0", pady=10)
        self.gps_loc_lbl.pack(fill="x")
        
        stat_f = tk.Frame(cont, bg="#f0f0f0")
        stat_f.pack(fill="both", expand=True, padx=5, pady=5)
        
        left = tk.LabelFrame(stat_f, text=" Discovered Rooms ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        left.pack(side="left", fill="both", expand=True, padx=5)
        self.gps_room_list = tk.Listbox(left, font=("Arial", 9), bg="white")
        self.gps_room_list.pack(fill="both", expand=True, padx=5, pady=5)
        
        right = tk.LabelFrame(stat_f, text=" Fast Transitions ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        right.pack(side="left", fill="both", expand=True, padx=5)
        self.gps_trans_view = scrolledtext.ScrolledText(right, font=("Consolas", 9), bg="#1e1e1e", fg="#00FF00")
        self.gps_trans_view.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.update_gps_ui()

    def update_gps_ui(self):
        """Refreshes the GPS tab with current map data."""
        self.gps_room_list.delete(0, tk.END)
        for room in sorted(self.gps_manager.m59_map.keys()):
            self.gps_room_list.insert(tk.END, room)
        
        self.gps_trans_view.config(state="normal")
        self.gps_trans_view.delete("1.0", tk.END)
        for room, data in sorted(self.gps_manager.m59_map.items()):
            for conn, dur in data.get("connections", {}).items():
                self.gps_trans_view.insert(tk.END, f"{room} -> {conn.split(':')[1]}: {dur}s\n")
        self.gps_trans_view.config(state="disabled")

    def setup_tab_dashboard(self):
        top = tk.Frame(self.tab_dash, bg="#f0f0f0")
        top.pack(fill="x", padx=10, pady=5)
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
        grid = tk.Frame(self.tab_dash, bg="#f0f0f0")
        grid.pack(fill="both", expand=True, padx=10, pady=5)
        attr_col = tk.LabelFrame(grid, text=" Attributes ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        attr_col.pack(side="left", fill="both", expand=False, padx=5)
        self.attr_labels = {}
        for a in ["Might", "Intellect", "Stamina", "Agility", "Mysticism", "Aim", "Karma"]:
            f = tk.Frame(attr_col, bg="#f0f0f0")
            f.pack(fill="x", pady=4, padx=5)
            tk.Label(f, text=f"{a}:", font=("Arial", 10), bg="#f0f0f0", width=10, anchor="w").pack(side="left")
            v = tk.Label(f, text="--", font=("Arial", 10, "bold"), bg="#f0f0f0", width=5, anchor="e")
            v.pack(side="right")
            self.attr_labels[a] = v
        gains_col = tk.LabelFrame(grid, text=" Session Improves ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        gains_col.pack(side="left", fill="both", expand=True, padx=5)
        self.gains_tree = ttk.Treeview(gains_col, columns=("Name", "Count", "Delta"), show="headings", height=10)
        for c, w in [("Name", 120), ("Count", 50), ("Delta", 80)]:
            self.gains_tree.heading(c, text=c)
            self.gains_tree.column(c, width=w, anchor="w" if c=="Name" else "center")
        self.gains_tree.pack(fill="both", expand=True)
        kills_col = tk.LabelFrame(grid, text=" Session Kills ", bg="#f0f0f0", font=("Arial", 10, "bold"))
        kills_col.pack(side="left", fill="both", expand=True, padx=5)
        self.kills_tree = ttk.Treeview(kills_col, columns=("Name", "Count"), show="headings", height=10)
        for c, w in [("Name", 120), ("Count", 60)]:
            self.kills_tree.heading(c, text=c)
            self.kills_tree.column(c, width=w, anchor="w" if c=="Name" else "center")
        self.kills_tree.pack(fill="both", expand=True)

        # --- Manual Sync Section ---
        sync_f = tk.Frame(self.tab_dash, bg="#f0f0f0")
        sync_f.pack(side="bottom", fill="x", padx=10, pady=10)
        self.manual_sync_btn = tk.Button(
            sync_f, text=" ↻ FULL SYNC ", 
            command=self.trigger_manual_sync, 
            state="disabled", font=("Arial", 13, "bold"), pady=10
        )
        self.manual_sync_btn.pack(fill="x")

    def setup_tab_progression(self):
        ctrl = tk.Frame(self.tab_prog, bg="#f0f0f0")
        ctrl.pack(fill="x", padx=10, pady=10)
        tk.Label(ctrl, text="Real-time School Progression Goals", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(side="left")
        self.sync_btn = tk.Button(ctrl, text="Sync All (Tab Dance)", command=self.trigger_sync, bg="#2196F3", fg="white", font=("Arial", 10, "bold"), padx=15)
        self.sync_btn.pack(side="right")
        self.prog_tree = ttk.Treeview(self.tab_prog, columns=("Level", "Sum", "Goal", "Needed"), show="tree headings")
        self.prog_tree.heading("#0", text="School / Ability")
        self.prog_tree.column("#0", width=220)
        for c, w in [("Level", 80), ("Sum", 100), ("Goal", 100), ("Needed", 100)]:
            self.prog_tree.heading(c, text=c)
            self.prog_tree.column(c, width=w, anchor="center")
        self.prog_tree.pack(fill="both", expand=True, padx=10, pady=5)

    def setup_tab_vault(self):
        cont = tk.Frame(self.tab_vault, bg="#f0f0f0")
        cont.pack(fill="both", expand=True, padx=5, pady=5)
        self.vault_widgets = {}
        for vt in ["barloque", "hungry"]:
            f = tk.LabelFrame(cont, text=f" {vt.title()} Vault ", bg="#f0f0f0", font=("Arial", 10, "bold"))
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
            tr.column("Name", width=150)
            tr.column("Qty", width=50, anchor="center")
            tr.pack(fill="both", expand=True, padx=5, pady=2)
            sl = tk.Label(f, text="No scan data", font=("Arial", 7, "italic"), bg="#f0f0f0", fg="gray")
            sl.pack(side="bottom", fill="x")
            self.vault_widgets[vt] = {"tree": tr, "filter_var": fv, "status_lbl": sl, "sync_btn": btn}

    def setup_tab_book(self):
        cont = tk.Frame(self.tab_book, bg="#f0f0f0")
        cont.pack(fill="both", expand=True, padx=5, pady=5)
        self.book_widgets = {}
        for kt in ["monsters", "players"]:
            f = tk.LabelFrame(cont, text=f" {kt.title()} ", bg="#f0f0f0", font=("Arial", 10, "bold"))
            f.pack(side="left", fill="both", expand=True, padx=5)
            row = tk.Frame(f, bg="#f0f0f0")
            row.pack(fill="x", padx=5, pady=5)
            fv = tk.StringVar()
            fv.trace_add("write", lambda *a, k=kt: self.update_book_tree(k))
            tk.Label(row, text="Filter:", bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
            tk.Entry(row, textvariable=fv, width=15).pack(side="left", padx=2)
            tr = ttk.Treeview(f, columns=("Name", "AllTime", "Session"), show="headings", height=15)
            tr.heading("Name", text="Victim")
            tr.heading("AllTime", text="Total")
            tr.heading("Session", text="Session")
            tr.column("Name", width=150)
            tr.column("AllTime", width=60, anchor="center")
            tr.column("Session", width=60, anchor="center")
            tr.pack(fill="both", expand=True, padx=5, pady=2)
            self.book_widgets[kt] = {"tree": tr, "filter_var": fv}

    def setup_tab_settings(self):
        c = tk.Frame(self.tab_settings, bg="#f0f0f0")
        c.pack(fill="both", expand=True, padx=20, pady=20)
        tk.Label(c, text="Companion Settings", font=("Arial", 14, "bold"), bg="#f0f0f0").pack(anchor="w", pady=(0, 20))

        pg = tk.LabelFrame(c, text=" Alerts ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        pg.pack(fill="x")
        tk.Checkbutton(pg, text="Enable PK Alerts", variable=self.pk_alert_enabled, bg="#f0f0f0").pack(anchor="w")
        
        wr_g = tk.LabelFrame(c, text=" Who List Panel ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        wr_g.pack(fill="x", pady=10)
        tk.Checkbutton(wr_g, text="Show Who List Side Panel", variable=self.who_list_enabled, 
                       command=self.update_who_list_visibility, bg="#f0f0f0").pack(anchor="w")
        
        side_f = tk.Frame(wr_g, bg="#f0f0f0")
        side_f.pack(fill="x", pady=5)
        tk.Label(side_f, text="Panel Side:", bg="#f0f0f0").pack(side="left")
        tk.Radiobutton(side_f, text="Left", variable=self.who_list_side, value="Left", 
                       command=self.update_who_list_visibility, bg="#f0f0f0").pack(side="left", padx=10)
        tk.Radiobutton(side_f, text="Right", variable=self.who_list_side, value="Right", 
                       command=self.update_who_list_visibility, bg="#f0f0f0").pack(side="left")

        gg = tk.LabelFrame(c, text=" GPS & Navigation ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        gg.pack(fill="x", pady=10)
        tk.Checkbutton(gg, text="Enable GPS Discovery", variable=self.gps_discovery_enabled, bg="#f0f0f0").pack(anchor="w")
        
        dg = tk.LabelFrame(c, text=" Diagnostics ", bg="#f0f0f0", font=("Arial", 10, "bold"), padx=15, pady=15)
        dg.pack(fill="x")
        tk.Checkbutton(dg, text="Verbose Debug Mode", variable=self.debug_enabled, bg="#f0f0f0").pack(anchor="w")
        
        tk.Button(c, text="Save Settings", command=self.save_settings, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), pady=10).pack(side="bottom", fill="x")

    def trigger_pk_alert(self):
        if not self.pk_alert_enabled.get():
            return
        self.alert_active = True
        self.debug_log("ALERT", "PVP Alert Triggered!")
        if self.pk_sound_enabled.get():
            p = self.pk_sound_path.get()
            try:
                if p == "SystemExclamation":
                    winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
                else:
                    winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                self.debug_log("ALERT", f"Sound error: {e}")
        if self.pk_frame_enabled.get() and self.pk_frame:
            self.pk_frame.flash()
        self.after(5000, self.reset_pk_alert)

    def reset_pk_alert(self):
        self.alert_active = False

    def establish_connection(self):
        self.status_var.set("Scanning for game...")
        self.debug_log("CONN", "Starting Lifecycle Monitor...")
        self.show_waiting_overlay()
        self.lifecycle.start()

    def on_game_connect(self, pm, pid):
        """Callback when InstanceManager attaches to a new game process."""
        logger.info(f"LifeCycle: New Game Instance Detected (PID {pid})")
        self.pm_obj = pm
        self.target_pid = pid
        
        # Find the HWND for this PID
        self.main_hwnd = None
        def find_hwnd(h, l):
            _, p = win32process.GetWindowThreadProcessId(h)
            if p == pid and win32gui.IsWindowVisible(h) and "Meridian 59" in win32gui.GetWindowText(h):
                self.main_hwnd = h
        win32gui.EnumWindows(find_hwnd, None)
        
        if not self.main_hwnd:
            logger.error(f"LifeCycle: Found PID {pid} but could not locate its window.")
            return

        # Transition overlay to 'Waiting for Login' state
        self.show_waiting_overlay(mode="login")
        
        # Start Who List if enabled
        if self.who_list_enabled.get():
            self.start_who_list_monitor()
            
        self.after(500, self.check_for_login)

    def check_for_login(self):
        """Polls the window title to detect when a character has entered the world."""
        if not self.main_hwnd or not self.is_running:
            return
            
        try:
            title = win32gui.GetWindowText(self.main_hwnd)
            if " --- " in title:
                logger.info(f"LifeCycle: Login detected via title: {title}")
                self.hide_waiting_overlay()
                
                # Check if this is the first initialization of the session
                is_first_init = (self.char_name == "Unknown")
                
                if is_first_init:
                    logger.info("LifeCycle: Initializing first-run handshake.")
                    self.char_name = capture_identity(self.main_hwnd, self.target_pid) or "Unknown"
                    self._finalize_connection()
                else:
                    logger.info(f"LifeCycle: Character {self.char_name} logged back in.")
                    self.status_var.set(f"Re-connected: {self.char_name} (Ready for Manual Sync)")
                    self.manual_sync_btn.config(state="normal", text=" ↻ FULL SYNC REQUIRED ")
                    self._post_connection_init(passive=True)
                
                # Trigger silent who update 1.5s after character is fully active in-game
                self.after(1500, self.trigger_silent_who_update)
            else:
                # Still at selection screen, check again in 1s
                self.after(1000, self.check_for_login)
        except Exception as e:
            logger.debug(f"LifeCycle: Error checking for login: {e}")
            self.after(2000, self.check_for_login)

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
                
                # 2. Tab Dance & Scrape
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
        
        # Stop Frida
        if self.frida_session:
            try: self.frida_session.detach()
            except: pass
            self.frida_session = None
            self.frida_script = None
            
        self.who_list_players = {}
        self.refresh_who_list_ui()
        
        self.show_waiting_overlay()
        self.status_var.set(f"Game Lost ({self.char_name}) - Searching...")
        self.title(f"M59 Companion v{self.version} - Waiting...")
        
        # Clear Vitals visually
        for v in self.hud_values.values():
            v.config(text="---")
            
        self.main_hwnd = None
        self.pm_obj = None
        self.target_pid = None
        # PK Frame might be invalid now
        if self.pk_frame:
            try: self.pk_frame.destroy()
            except: pass
            self.pk_frame = None

    def _post_connection_init(self, passive=False):
        if not self.is_running:
            return
        self.debug_log("INIT", f"Initializing profile (Passive: {passive})...")
        try:
            self.load_vault_cache()
            self.load_kill_book()
            self.refresh_log_list()
            
            if not self.pk_frame:
                self.pk_frame = PKFrame(self, self.main_hwnd)
                
            self.update_hud()
            self.start_chat_monitor()
            
            if not passive:
                self.debug_log("INIT", "Starting automatic startup sync...")
                threading.Thread(target=self.perform_sync, daemon=True).start()
        except Exception as e:
            self.debug_log("INIT", f"Post-connection error: {e}")

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
            
            elif is_logged_in:
                room = current_title.split(" --- ", 1)[1].strip()
                if "Logged Out" in self.status_var.get():
                    # STATE: User just logged back in
                    logger.info(f"Character detected back in-game at {room}.")
                    self.status_var.set(f"Re-connected: {self.char_name} (Ready for Manual Sync)")
                    self.title(f"M59 Companion v{self.version} - {self.char_name}")
                    # Enable the sync button to indicate a refresh is needed
                    self.manual_sync_btn.config(state="normal", text=" ↻ FULL SYNC REQUIRED ")
                
                self.gps_loc_lbl.config(text=room)
                if self.gps_discovery_enabled.get():
                    self.monitor_gps_discovery(room)

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

            safe_n = self.char_name.replace(" ", "_")
            log_p = os.path.join("logs", f"{safe_n}_chat.log")
            
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
                            current_log_p = os.path.join("logs", f"{current_safe_n}_chat.log")
                            
                            with open(current_log_p, "a", encoding="utf-8") as f:
                                for l in new:
                                    f.write(f"{ts} {l}\n")
                                    self.after(0, lambda ln=l: self.append_comms_line(ln))
                                    try:
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
        if self.gains_tree.exists(g['name']):
            self.gains_tree.item(g['name'], values=(g['name'], g['count'], g['delta']))
        else:
            self.gains_tree.insert("", "end", iid=g['name'], values=(g['name'], g['count'], "---"))

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
        if self.target_pid:
            release_pid(self.target_pid)
        self.destroy()

    def show_instance_selection_ui(self, instances):
        """Displays a modal popup when multiple unclaimed games are found."""
        logger.info(f"UI: Prompting user for instance selection from {len(instances)} options.")
        
        popup = tk.Toplevel(self)
        popup.title("Select Game Instance")
        popup.geometry("500x350")
        popup.attributes("-topmost", True)
        popup.grab_set() # Modal
        
        tk.Label(popup, text="Multiple unclaimed games detected.", font=("Arial", 11, "bold"), pady=10).pack()
        tk.Label(popup, text="Please select the instance you want this Companion to control:", font=("Arial", 9)).pack(pady=(0, 10))
        
        frame = tk.Frame(popup)
        frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        # Treeview for selection
        tree = ttk.Treeview(frame, columns=("PID", "Character", "Location"), show="headings", height=8)
        tree.heading("PID", text="PID")
        tree.heading("Character", text="Character")
        tree.heading("Location", text="Location")
        tree.column("PID", width=70, anchor="center")
        tree.column("Character", width=150, anchor="w")
        tree.column("Location", width=250, anchor="w")
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
        
        btn_f = tk.Frame(popup)
        btn_f.pack(fill="x", pady=20)
        
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
        if rm.get(vt) and rm[vt].lower() not in cur.lower():
            messagebox.showwarning("Location", f"Sync Blocked: Must be in '{rm[vt]}'.\nCurrent: '{cur}'")
            return
        if not messagebox.askyesno("Scan", f"Scan {vt} vault?"):
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
        sn = self.char_name.replace(" ", "_")
        for vt in ["barloque", "hungry"]:
            p = next((x for x in [f"logs/{sn}_vault_{vt}.json", f"logs/{self.char_name}_vault_{vt}.json"] if os.path.exists(x)), None)
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
        p = f"logs/{self.char_name.replace(' ', '_')}_kills.json"
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
            u, rv = check_for_updates(self.version)
            if not u: 
                self.after(0, self.establish_connection)
                return
            def show_prompt():
                choice = messagebox.askquestion("Update", f"v{rv} available. Update?", icon="info", type="yesnocancel")
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
                    if psutil.Process(p).name().lower() == "meridian.exe":
                        insts.append({"pid": p, "title": win32gui.GetWindowText(h), "hwnd": h})
                except:
                    pass
        win32gui.EnumWindows(cb, None)
        return insts

    def browse_sound(self):
        p = filedialog.askopenfilename(filetypes=[("Wave files", "*.wav")])
        if p:
            self.pk_sound_path.set(p)

    def test_sound(self):
        p = self.pk_sound_path.get()
        try:
            if p == "SystemExclamation":
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
            else:
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except:
            pass

    def show_waiting_overlay(self, mode="searching"):
        """Displays a non-blocking splash window when searching for game or waiting for login."""
        if self.waiting_overlay and self.waiting_overlay.winfo_exists():
            # Update existing overlay text
            if mode == "login":
                self.waiting_title_lbl.config(text=" ↻ WAITING FOR LOGIN... ", fg="#2196F3")
                self.waiting_msg_lbl.config(text="Please select a character and enter the world.")
                self.waiting_frame.config(highlightbackground="#2196F3")
            else:
                self.waiting_title_lbl.config(text=" ↻ SCANNING FOR GAME... ", fg="#4CAF50")
                self.waiting_msg_lbl.config(text="Please launch Meridian 59 to continue.")
                self.waiting_frame.config(highlightbackground="#4CAF50")
            return
            
        logger.info(f"UI: Displaying 'Waiting' overlay (Mode: {mode}).")
        overlay = tk.Toplevel(self)
        overlay.title("Connecting...")
        overlay.geometry("450x200")
        overlay.resizable(False, False)
        overlay.attributes("-topmost", True)
        
        # Center over main window
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 225
        y = self.winfo_y() + (self.winfo_height() // 2) - 100
        overlay.geometry(f"+{max(0, x)}+{max(0, y)}")
        overlay.overrideredirect(True)
        
        self.waiting_frame = tk.Frame(overlay, bg="#333333", highlightthickness=2)
        self.waiting_frame.config(highlightbackground="#4CAF50" if mode == "searching" else "#2196F3")
        self.waiting_frame.pack(fill="both", expand=True)
        
        title_text = " ↻ SCANNING FOR GAME... " if mode == "searching" else " ↻ WAITING FOR LOGIN... "
        title_color = "#4CAF50" if mode == "searching" else "#2196F3"
        msg_text = "Please launch Meridian 59." if mode == "searching" else "Please enter the world."
        
        self.waiting_title_lbl = tk.Label(self.waiting_frame, text=title_text, font=("Arial", 16, "bold"), fg=title_color, bg="#333333", pady=20)
        self.waiting_title_lbl.pack()
        self.waiting_msg_lbl = tk.Label(self.waiting_frame, text=msg_text, font=("Arial", 11), fg="white", bg="#333333")
        self.waiting_msg_lbl.pack()
        tk.Label(self.waiting_frame, text="The Companion will automatically connect once ready.", font=("Arial", 9, "italic"), fg="#aaaaaa", bg="#333333", pady=15).pack()
        
        self.waiting_overlay = overlay

    def hide_waiting_overlay(self):
        """Destroys the waiting overlay if it exists."""
        if self.waiting_overlay:
            try:
                if self.waiting_overlay.winfo_exists():
                    logger.info("UI: Hiding 'Waiting for Game' overlay.")
                    self.waiting_overlay.destroy()
            except:
                pass
            self.waiting_overlay = None

if __name__ == "__main__":
    app = M59Dashboard()
    app.mainloop()
