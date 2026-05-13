import win32gui
import win32con
import win32process
import pymem
import array
import time

def get_all_game_instances():
    instances = []
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if text.startswith("Meridian 59"):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                instances.append({
                    "hwnd": hwnd,
                    "pid": pid,
                    "title": text
                })
    win32gui.EnumWindows(callback, None)
    return instances

def find_listbox(game_hwnd):
    found_id = [None]
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            cls = win32gui.GetClassName(hwnd)
            if cls == "ListBox":
                found_id[0] = hwnd
    win32gui.EnumChildWindows(game_hwnd, callback, None)
    return found_id[0]

def spy():
    print("--- M59 Memory Spy Tool ---")
    instances = get_all_game_instances()
    if not instances:
        print("No Meridian 59 windows found.")
        return

    for inst in instances:
        print(f"\nTarget: {inst['title']} (PID: {inst['pid']}, HWND: {inst['hwnd']})")
        
        try:
            pm = pymem.Pymem(inst['pid'])
        except Exception as e:
            print(f"  Error: Could not attach to PID {inst['pid']}: {e}")
            continue

        lb_hwnd = find_listbox(inst['hwnd'])
        if not lb_hwnd:
            print("  Warning: No visible ListBox found in this window. (Is the Skills tab open?)")
            continue

        count = win32gui.SendMessage(lb_hwnd, win32con.LB_GETCOUNT, 0, 0)
        print(f"  ListBox Items: {count}")

        for i in range(count):
            # 1. Get Text
            length = win32gui.SendMessage(lb_hwnd, win32con.LB_GETTEXTLEN, i, 0)
            label = "Unknown"
            if length > 0:
                buffer = array.array('u', '\x00' * (length + 1))
                win32gui.SendMessage(lb_hwnd, win32con.LB_GETTEXT, i, buffer)
                label = buffer.tounicode().rstrip('\x00')

            # 2. Get Item Data (Pointer)
            base_addr = win32gui.SendMessage(lb_hwnd, win32con.LB_GETITEMDATA, i, 0)
            
            # 3. Spy on memory
            if base_addr > 65535:
                try:
                    # Read percentage at offset 16
                    perc_val = pm.read_int(base_addr + 16)
                    
                    # Also let's peek at the first 32 bytes of the structure for context
                    raw_hex = " ".join([f"{b:02x}" for b in pm.read_bytes(base_addr, 32)])
                    
                    print(f"  [{i:02}] {label.ljust(15)} | Pointer: {hex(base_addr)} | % (+16): {perc_val}")
                    print(f"       Raw (32 bytes): {raw_hex}")
                except Exception as e:
                    print(f"  [{i:02}] {label.ljust(15)} | Pointer: {hex(base_addr)} | Error: {e}")
            else:
                print(f"  [{i:02}] {label.ljust(15)} | Pointer: {hex(base_addr)} (Invalid)")

if __name__ == "__main__":
    spy()
