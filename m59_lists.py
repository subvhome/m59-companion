import win32gui
import win32con
import array
import time
from m59_memory import MemoryReader

mem = MemoryReader()

def get_raw_skill_dict(hwnd, min_items=1):
    print(f">>> [MODULE] Stabilizing listbox for HWND {hwnd} (Expecting min: {min_items})")
    
    skill_map = {}
    start_time = time.time()
    
    # Loop for up to 4 seconds to reach stabilization AND minimum threshold
    while time.time() - start_time < 4.0:
        current_count = win32gui.SendMessage(hwnd, win32con.LB_GETCOUNT, 0, 0)
        
        # If we have at least min_items and the count is stable, proceed
        if current_count >= min_items:
            time.sleep(0.3) # Final settling breath
            if win32gui.SendMessage(hwnd, win32con.LB_GETCOUNT, 0, 0) == current_count:
                break
        time.sleep(0.3)

    final_count = win32gui.SendMessage(hwnd, win32con.LB_GETCOUNT, 0, 0)
    for i in range(final_count):
        length = win32gui.SendMessage(hwnd, win32con.LB_GETTEXTLEN, i, 0)
        if length > 0:
            buffer = array.array('u', '\x00' * (length + 1))
            win32gui.SendMessage(hwnd, win32con.LB_GETTEXT, i, buffer)
            label = buffer.tounicode().rstrip('\x00').lower()
            
            base_addr = win32gui.SendMessage(hwnd, win32con.LB_GETITEMDATA, i, 0)
            percent = mem.read_skill_percent(base_addr)
            skill_map[label] = int(percent)
            
    return skill_map
