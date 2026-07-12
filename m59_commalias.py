import tkinter as tk
from tkinter import ttk, messagebox
import os
import getpass
import json
import keyboard
import threading
import time
import win32gui
import win32api
import win32con

from m59_map import detect_installation
from m59_vault import send_chat_command

ALIAS_SETTINGS_FILE = "settings/commalias.json"

def get_config_path():
    try:
        resource_path, map_file, is_running = detect_installation()
        if map_file:
            base_dir = os.path.dirname(os.path.dirname(map_file))
            config_path = os.path.join(base_dir, "config.ini")
            if os.path.exists(config_path):
                return config_path
    except Exception:
        pass
    
    local_app_data = os.environ.get('LOCALAPPDATA', f"C:\\Users\\{getpass.getuser()}\\AppData\\Local")
    path1 = os.path.join(local_app_data, "Meridian 59", "config.ini")
    if os.path.exists(path1):
        return path1
    return None

def parse_config_ini():
    config_path = get_config_path()
    used_keys = set()
    if not config_path or not os.path.exists(config_path):
        return used_keys
    
    in_keys_section = False
    with open(config_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip().lower()
            if line == '[keys]':
                in_keys_section = True
                continue
            if line.startswith('[') and in_keys_section:
                in_keys_section = False
                continue
            if in_keys_section and '=' in line:
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key_part = parts[1].strip()
                    if key_part:
                        used_keys.add(key_part)
    return used_keys

class AliasFloatBtn(tk.Toplevel):
    def __init__(self, parent, main_hwnd, alias_name, command1, x_offset=0, y_offset=0):
        super().__init__(parent)
        self.main_hwnd = main_hwnd
        self.command1 = command1
        self.title(alias_name)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#222222")
        self.geometry(f"100x30+{100+x_offset}+{100+y_offset}")
        
        self.x = 0
        self.y = 0
        self.offset_x = x_offset
        self.offset_y = y_offset
        self.docked = True
        
        # Grip
        self.grip = tk.Label(self, text="::", bg="#444444", fg="white", cursor="fleur", width=2)
        self.grip.pack(side="left", fill="y")
        self.grip.bind("<ButtonPress-1>", self.start_move)
        self.grip.bind("<B1-Motion>", self.do_move)
        
        self.btn = tk.Button(self, text=alias_name, bg="#555555", fg="white", relief="flat", command=self.execute_alias)
        self.btn.pack(side="left", padx=2, pady=2, fill="both", expand=True)
        
        self.after(100, self.set_owner)
        self.after(200, self.init_docking)
        self.after(300, self.check_docking)

    def init_docking(self):
        if self.main_hwnd:
            try:
                self.update_idletasks()
                rect = win32gui.GetWindowRect(self.main_hwnd)
                self.offset_x = self.winfo_x() - rect[0]
                self.offset_y = self.winfo_y() - rect[1]
            except:
                pass

    def set_owner(self):
        if self.main_hwnd:
            try:
                hwnd = self.winfo_id()
                parent = win32gui.GetParent(hwnd)
                target = parent if parent else hwnd
                win32gui.SetWindowLong(target, win32con.GWL_HWNDPARENT, self.main_hwnd)
                self.attributes("-topmost", False)
            except Exception:
                pass

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        new_x = self.winfo_x() + deltax
        new_y = self.winfo_y() + deltay
        self.geometry(f"+{new_x}+{new_y}")
        
        if self.main_hwnd:
            try:
                rect = win32gui.GetWindowRect(self.main_hwnd)
                self.offset_x = new_x - rect[0]
                self.offset_y = new_y - rect[1]
            except:
                pass

    def check_docking(self):
        if self.main_hwnd:
            if not win32gui.IsWindow(self.main_hwnd):
                self.destroy()
                return
            if self.docked:
                try:
                    rect = win32gui.GetWindowRect(self.main_hwnd)
                    target_x = rect[0] + self.offset_x
                    target_y = rect[1] + self.offset_y
                    if self.winfo_x() != target_x or self.winfo_y() != target_y:
                        self.geometry(f"+{target_x}+{target_y}")
                except:
                    pass
        self.after(100, self.check_docking)

    def execute_alias(self):
        if not self.main_hwnd:
            return
        def _run():
            try:
                if self.command1:
                    send_chat_command(self.main_hwnd, self.command1)

            except Exception as e:
                print(f"Failed alias execution: {e}")
        threading.Thread(target=_run, daemon=True).start()

class CommaliasManager:
    def __init__(self, dashboard):
        self.dashboard = dashboard
        self.aliases = []
        self.float_btns = []
        self.load_aliases()
        self.register_hotkeys()
        
    def load_aliases(self):
        if os.path.exists(ALIAS_SETTINGS_FILE):
            try:
                with open(ALIAS_SETTINGS_FILE, "r") as f:
                    self.aliases = json.load(f)
            except:
                self.aliases = []

    def save_aliases(self):
        os.makedirs(os.path.dirname(ALIAS_SETTINGS_FILE), exist_ok=True)
        with open(ALIAS_SETTINGS_FILE, "w") as f:
            json.dump(self.aliases, f, indent=4)
            
    def _translate_hotkey_for_keyboard(self, key_str):
        # Format from config.ini: 'w+ctrl', '1+alt', 'mouse1'
        # We need to map it to what the 'keyboard' module expects.
        key_str = key_str.lower()
        parts = key_str.split('+')
        modifiers = []
        main_key = None
        for p in parts:
            if p in ('ctrl', 'alt', 'shift'):
                modifiers.append(p)
            else:
                main_key = p
        if not main_key:
            return None
        
        # keyboard module prefers 'ctrl+w' rather than 'w+ctrl'
        if modifiers:
            return "+".join(modifiers) + "+" + main_key
        return main_key

    def register_hotkeys(self):
        try:
            keyboard.unhook_all()
        except:
            pass
            
        for alias in self.aliases:
            if not alias.get('enabled', True):
                continue
            hotkey = alias.get('hotkey')
            if hotkey:
                k_hotkey = self._translate_hotkey_for_keyboard(hotkey)
                if k_hotkey:
                    try:
                        keyboard.add_hotkey(k_hotkey, self.on_hotkey, args=(alias,))
                    except Exception as e:
                        print(f"Failed to register hotkey {k_hotkey}: {e}")

    def on_hotkey(self, alias):
        # Only execute if the target game window is active
        hwnd = self.dashboard.main_hwnd
        if not hwnd:
            return
        
        # Check if the active window is the game
        active_hwnd = win32gui.GetForegroundWindow()
        if active_hwnd != hwnd:
            return
            
        def _run():
            cmd1 = alias.get('command1')
            try:
                if cmd1:
                    send_chat_command(hwnd, cmd1)

            except Exception as e:
                print(f"Failed alias execution: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def update_float_buttons(self):
        for btn in self.float_btns:
            try:
                btn.destroy()
            except:
                pass
        self.float_btns.clear()
        
        if not self.dashboard.main_hwnd:
            return
            
        x_offset = 0
        for alias in self.aliases:
            if alias.get('show_float', False):
                btn = AliasFloatBtn(
                    self.dashboard, 
                    self.dashboard.main_hwnd, 
                    alias.get('name', 'Alias'),
                    alias.get('command1', ''),

                    x_offset=x_offset,
                    y_offset=0
                )
                self.float_btns.append(btn)
                x_offset += 105

class CommaliasTab(tk.Frame):
    def __init__(self, parent, dashboard):
        super().__init__(parent, bg="#f0f0f0")
        self.dashboard = dashboard
        self.manager = CommaliasManager(dashboard)
        self.used_keys = parse_config_ini()
        
        self.build_ui()
        
    def refresh_used_keys(self):
        self.used_keys = parse_config_ini()

    def build_ui(self):
        for widget in self.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(self, bg="#f0f0f0")
        top_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(top_frame, text="Command Aliases & Hotkeys", font=("Arial", 14, "bold"), bg="#f0f0f0").pack(side="left")
        
        # Elude Button Move
        tk.Label(top_frame, text="  |  ", bg="#f0f0f0", fg="#888888").pack(side="left")
        self.elude_btn = tk.Button(top_frame, text="Launch Elude Menu", bg="#8e44ad", fg="white", font=("Arial", 9, "bold"), command=self.dashboard.launch_elusion_menu)
        self.elude_btn.pack(side="left", padx=10)

        # List Frame
        list_frame = tk.Frame(self, bg="#ffffff", bd=1, relief="solid")
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        columns = ("name", "hotkey", "cmd1", "float")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="Alias Name")
        self.tree.heading("hotkey", text="Hotkey")
        self.tree.heading("cmd1", text="Command")
        self.tree.heading("float", text="Floating Button")
        
        self.tree.column("name", width=100)
        self.tree.column("hotkey", width=80)
        self.tree.column("cmd1", width=150)
        self.tree.column("float", width=100)
        
        self.tree.bind("<Double-1>", self.on_tree_click)
        
        self.tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        for idx, alias in enumerate(self.manager.aliases):
            self.tree.insert("", "end", iid=str(idx), values=(
                alias.get("name", ""),
                alias.get("hotkey", ""),
                alias.get("command1", ""),
                "Yes" if alias.get("show_float", False) else "No"
            ))
            
        btn_frame = tk.Frame(self, bg="#f0f0f0")
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Button(btn_frame, text="Add New Alias", command=self.open_edit_window).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Edit Selected", command=self.edit_selected).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Delete Selected", command=self.delete_selected).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Refresh M59 Config", command=self.refresh_used_keys).pack(side="right", padx=5)
        
    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
            
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
            
        col_index = int(col[1:]) - 1
        idx = int(row_id)
        alias = self.manager.aliases[idx]
        
        if col_index == 3: # Float
            alias["show_float"] = not alias.get("show_float", False)
            self.manager.save_aliases()
            self.manager.update_float_buttons()
            self.build_ui()
            return
            
        if col_index == 1: # Hotkey
            self.capture_inline_hotkey(idx, row_id, col)
            return
            
        self.edit_inline_text(idx, row_id, col, col_index)

    def capture_inline_hotkey(self, idx, row_id, col):
        x, y, width, height = self.tree.bbox(row_id, col)
        
        entry = tk.Entry(self.tree, justify="center")
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, "Press keys...")
        entry.config(state="readonly")
        
        alias = self.manager.aliases[idx]
        
        def on_key_event(e):
            name = e.name
            if name in ('ctrl', 'alt', 'shift', 'left ctrl', 'right ctrl', 'left alt', 'right alt', 'left shift', 'right shift'):
                return
            
            if e.event_type == 'up':
                mods = []
                if keyboard.is_pressed('ctrl'): mods.append('ctrl')
                if keyboard.is_pressed('alt'): mods.append('alt')
                if keyboard.is_pressed('shift'): mods.append('shift')
                
                config_hk_str = name
                if mods:
                    config_hk_str = name + "+" + "+".join(mods)
                    
                keyboard.unhook_all()
                
                def finish_capture():
                    if config_hk_str in self.used_keys and config_hk_str != alias.get("hotkey"):
                        messagebox.showerror("Error", f"Hotkey {config_hk_str} is already used in M59 config.ini!")
                    else:
                        alias["hotkey"] = config_hk_str
                        self.manager.save_aliases()
                        self.manager.register_hotkeys()
                        self.manager.update_float_buttons()
                        self.tree.set(row_id, column=col, value=config_hk_str)
                    entry.destroy()
                
                self.after(0, finish_capture)
        
        try:
            keyboard.unhook_all()
            keyboard.hook(on_key_event)
        except Exception as ex:
            messagebox.showerror("Error", f"Failed to hook keyboard: {ex}")
            entry.destroy()
            self.manager.register_hotkeys()

    def edit_inline_text(self, idx, row_id, col, col_index):
        x, y, width, height = self.tree.bbox(row_id, col)
        val = self.tree.set(row_id, column=col)
        
        entry = tk.Entry(self.tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, val)
        entry.focus()
        
        def save_edit(event=None):
            new_val = entry.get()
            alias = self.manager.aliases[idx]
            if col_index == 0:
                alias["name"] = new_val
            elif col_index == 2:
                alias["command1"] = new_val
                
            self.manager.save_aliases()
            self.manager.update_float_buttons()
            self.tree.set(row_id, column=col, value=new_val)
            entry.destroy()
            
        def cancel_edit(event=None):
            entry.destroy()
            
        entry.bind("<Return>", save_edit)
        entry.bind("<Escape>", cancel_edit)
        entry.bind("<FocusOut>", save_edit)

    def edit_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select an alias to edit.")
            return
        idx = int(sel[0])
        self.open_edit_window(idx)

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        del self.manager.aliases[idx]
        self.manager.save_aliases()
        self.manager.register_hotkeys()
        self.manager.update_float_buttons()
        self.build_ui()

    def open_edit_window(self, idx=None):
        win = tk.Toplevel(self)
        win.title("Edit Alias")
        win.geometry("450x550")
        win.configure(bg="#f0f0f0")
        win.grab_set()
        
        alias = {}
        if idx is not None:
            alias = self.manager.aliases[idx]
            
        tk.Label(win, text="Name:", bg="#f0f0f0").pack(anchor="w", padx=10, pady=(10, 0))
        name_var = tk.StringVar(value=alias.get("name", ""))
        tk.Entry(win, textvariable=name_var).pack(fill="x", padx=10, pady=2)
        
        tk.Label(win, text="Capture Hotkey:", bg="#f0f0f0").pack(anchor="w", padx=10, pady=(10, 0))
        hotkey_var = tk.StringVar(value=alias.get("hotkey", ""))
        
        capture_frame = tk.Frame(win, bg="#f0f0f0")
        capture_frame.pack(fill="x", padx=10, pady=2)
        hk_entry = tk.Entry(capture_frame, textvariable=hotkey_var, state="readonly", width=25)
        hk_entry.pack(side="left")
        
        def start_capture():
            hk_entry.config(state="normal")
            hotkey_var.set("Press keys...")
            hk_entry.config(state="readonly")
            
            def on_key_event(e):
                name = e.name
                if name in ('ctrl', 'alt', 'shift', 'left ctrl', 'right ctrl', 'left alt', 'right alt', 'left shift', 'right shift'):
                    return # just modifier
                
                # wait for key up to finalize
                if e.event_type == 'up':
                    mods = []
                    if keyboard.is_pressed('ctrl'): mods.append('ctrl')
                    if keyboard.is_pressed('alt'): mods.append('alt')
                    if keyboard.is_pressed('shift'): mods.append('shift')
                    
                    hk_str = "+".join(mods + [name]) if mods else name
                    
                    # Convert to config.ini format 'key[+modifier]' like '1+ctrl'
                    config_hk_str = name
                    if mods:
                        config_hk_str = name + "+" + "+".join(mods)
                        
                    keyboard.unhook_all()
                    
                    # Validate against config.ini
                    if config_hk_str in self.used_keys:
                        win.after(0, lambda: messagebox.showerror("Error", f"Hotkey {config_hk_str} is already used in M59 config.ini!"))
                        win.after(0, lambda: hotkey_var.set(""))
                    else:
                        win.after(0, lambda: hotkey_var.set(config_hk_str))
            
            try:
                keyboard.unhook_all()
                keyboard.hook(on_key_event)
            except Exception as ex:
                messagebox.showerror("Error", f"Failed to hook keyboard: {ex}\nTry running as administrator.")
        
        tk.Button(capture_frame, text="Capture", command=start_capture).pack(side="left", padx=5)
        
        tk.Label(win, text="Command 1 (e.g. cast blink):", bg="#f0f0f0").pack(anchor="w", padx=10, pady=(10, 0))
        cmd1_var = tk.StringVar(value=alias.get("command1", ""))
        tk.Entry(win, textvariable=cmd1_var).pack(fill="x", padx=10, pady=2)
        

        
        show_float_var = tk.BooleanVar(value=alias.get("show_float", False))
        tk.Checkbutton(win, text="Create floating button tied to game window", variable=show_float_var, bg="#f0f0f0").pack(anchor="w", padx=10, pady=10)
        
        def save():
            try:
                keyboard.unhook_all()
                self.manager.register_hotkeys()
            except:
                pass
                
            new_alias = {
                "name": name_var.get().strip(),
                "hotkey": hotkey_var.get(),
                "command1": cmd1_var.get().strip(),
                "show_float": show_float_var.get(),
                "enabled": True
            }
            if not new_alias["name"]:
                messagebox.showerror("Error", "Name cannot be empty.")
                return
                
            if idx is not None:
                self.manager.aliases[idx] = new_alias
            else:
                self.manager.aliases.append(new_alias)
                
            self.manager.save_aliases()
            self.manager.register_hotkeys()
            self.manager.update_float_buttons()
            self.build_ui()
            win.destroy()
            
        def cancel():
            try:
                keyboard.unhook_all()
                self.manager.register_hotkeys()
            except:
                pass
            win.destroy()
            
        tk.Button(win, text="Save", command=save, bg="#27ae60", fg="white", width=15).pack(pady=10)
        tk.Button(win, text="Cancel", command=cancel, width=15).pack()

