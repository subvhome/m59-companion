import tkinter as tk
from tkinter import ttk
import win32gui
import win32api
import win32con
import threading
import time

LOCATIONS = [
    "The Streets of Tos",
    "Marion",
    "South Barloque",
    "Cor Noth",
    "East Jasper",
    "The Aerie Guest House",
    "Guild Hall"
]

class ElusionMenu(tk.Toplevel):
    def __init__(self, parent, target_hwnd=None):
        super().__init__(parent)
        self.dashboard = parent
        self.target_hwnd = target_hwnd
        self.title("Elude")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#222222")
        geom = "320x35+100+100"
        if hasattr(self, 'dashboard') and hasattr(self.dashboard, 'elusion_geometry'):
            saved_geom = self.dashboard.elusion_geometry.get()
            if saved_geom:
                geom = saved_geom
        self.geometry(geom)
        
        self.x = 0
        self.y = 0
        
        # Grip for dragging
        self.grip = tk.Label(self, text="::", bg="#444444", fg="white", cursor="fleur", width=2)
        self.grip.pack(side="left", fill="y")
        self.grip.bind("<ButtonPress-1>", self.start_move)
        self.grip.bind("<B1-Motion>", self.do_move)
        
        locations = list(LOCATIONS)
        if hasattr(self, 'dashboard') and hasattr(self.dashboard, 'guildhall_name'):
            gh = self.dashboard.guildhall_name.get().strip()
            if gh and gh not in locations:
                locations.append(gh)
                
        self.combo = ttk.Combobox(self, values=locations, width=12)
        self.combo.set("Select Location")
        self.combo.pack(side="left", padx=4, pady=4, fill="both", expand=True)
        
        self.btn = tk.Button(self, text="Cast", bg="#555555", fg="white", relief="flat", command=self.do_elude)
        self.btn.pack(side="left", padx=4, pady=4)
        
        self.close_btn = tk.Button(self, text="X", bg="#882222", fg="white", relief="flat", command=self.destroy)
        self.close_btn.pack(side="left", padx=2, pady=4)
        
        self.docked = True
        self.offset_x = 0
        self.offset_y = 0
        
        self.after(100, self.set_owner)
        self.after(200, self.init_docking)
        self.after(300, self.check_docking)

    def init_docking(self):
        if self.target_hwnd:
            try:
                self.update_idletasks()
                rect = win32gui.GetWindowRect(self.target_hwnd)
                self.offset_x = self.winfo_x() - rect[0]
                self.offset_y = self.winfo_y() - rect[1]
            except:
                pass

    def set_owner(self):
        if self.target_hwnd:
            try:
                hwnd = self.winfo_id()
                parent = win32gui.GetParent(hwnd)
                target = parent if parent else hwnd
                win32gui.SetWindowLong(target, win32con.GWL_HWNDPARENT, self.target_hwnd)
                # When owned, it naturally stays on top of the owner, so we can disable global topmost
                self.attributes("-topmost", False)
            except Exception as e:
                print(f"Failed to set window owner: {e}")

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def update_saved_geometry(self):
        if hasattr(self, 'dashboard') and hasattr(self.dashboard, 'elusion_geometry'):
            self.dashboard.elusion_geometry.set(self.geometry())

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        new_x = self.winfo_x() + deltax
        new_y = self.winfo_y() + deltay
        self.geometry(f"+{new_x}+{new_y}")
        self.update_saved_geometry()
        
        if self.target_hwnd:
            try:
                rect = win32gui.GetWindowRect(self.target_hwnd)
                self.offset_x = new_x - rect[0]
                self.offset_y = new_y - rect[1]
            except:
                pass

    def check_docking(self):
        if self.target_hwnd:
            if not win32gui.IsWindow(self.target_hwnd):
                self.destroy()
                return
                
        if self.docked and self.target_hwnd:
            try:
                rect = win32gui.GetWindowRect(self.target_hwnd)
                target_x = rect[0] + self.offset_x
                target_y = rect[1] + self.offset_y
                if self.winfo_x() != target_x or self.winfo_y() != target_y:
                    self.geometry(f"+{target_x}+{target_y}")
                    self.update_saved_geometry()
            except:
                pass
        self.after(100, self.check_docking)

    def send_string_to_hwnd(self, hwnd, s):
        for c in s:
            win32api.SendMessage(hwnd, win32con.WM_CHAR, ord(c), 0)
            time.sleep(0.01)
            
    def press_key(self, hwnd, key):
        win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, key, 0)
        time.sleep(0.01)
        win32api.SendMessage(hwnd, win32con.WM_KEYUP, key, 0)
        
    def _execute_macro(self, loc):
        if not self.target_hwnd:
            return
            
        hwnd = self.target_hwnd
        
        try:
            from m59_vault import send_chat_command
            
            # Cast elusion
            send_chat_command(hwnd, 'cast "elusion"')
            
            # Wait for spell to cast and trance to start
            time.sleep(1.5)
            
            # Send location
            phrase = "I wish to travel to {loc}."
            if hasattr(self, 'dashboard') and hasattr(self.dashboard, 'elusion_phrase'):
                phrase = self.dashboard.elusion_phrase.get()
                
            formatted_phrase = phrase.replace('{loc}', loc)
            send_chat_command(hwnd, formatted_phrase)
            
        except Exception as e:
            print(f"Failed to cast elusion: {e}")

    def do_elude(self):
        loc = self.combo.get()
        if loc in ["Select Location", ""]:
            return
        threading.Thread(target=self._execute_macro, args=(loc,), daemon=True).start()

