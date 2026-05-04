import win32gui
import win32con
import array
import time
from m59_memory import MemoryReader

mem = MemoryReader()

def get_raw_skill_dict(hwnd):
    # Short internal delay to ensure list items are ready
    time.sleep(0.2) 
    print(f">>> [MODULE] Reading skills for HWND {hwnd}")
    
    skill_map = {}
    count = win32gui.SendMessage(hwnd, win32con.LB_GETCOUNT, 0, 0)
    
    if count <= 0:
        print(">>> [WARN] Listbox is empty or not ready.")
        return {}

    for i in range(count):
        length = win32gui.SendMessage(hwnd, win32con.LB_GETTEXTLEN, i, 0)
        if length > 0:
            buffer = array.array('u', '\x00' * (length + 1))
            win32gui.SendMessage(hwnd, win32con.LB_GETTEXT, i, buffer)
            label = buffer.tounicode().rstrip('\x00').lower()
            
            base_addr = win32gui.SendMessage(hwnd, win32con.LB_GETITEMDATA, i, 0)
            percent = mem.read_skill_percent(base_addr)
            skill_map[label] = int(percent)
            
    print(f">>> [SUCCESS] Grabbed {len(skill_map)} items from listbox.")
    return skill_map
