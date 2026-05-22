import os
import time
import json
import win32api
import win32con
import win32gui
import win32process
import array
from m59_logging import get_logger

logger = get_logger("vault")

# Vault Specific Constants
CHAT_CONTROL_ID = 1001
DIALOG_CLASS = "#32770"
DIALOG_TEXT = "Withdraw Items"
ID_ITEM_LIST = 1002
ID_QTY_LIST = 1076

def find_nested_control(parent_hwnd, target_id):
    """Deep search for a specific control ID within a parent window."""
    found_hwnd = [None]
    def enum_cb(h, l):
        if win32gui.GetDlgCtrlID(h) == target_id:
            found_hwnd[0] = h
            return False
        return True
    try: 
        win32gui.EnumChildWindows(parent_hwnd, enum_cb, None)
    except Exception as e: 
        logger.debug(f"EnumChildWindows failed for parent {parent_hwnd}: {e}")
    return found_hwnd[0]

def send_chat_command(main_hwnd, text):
    """Sends a raw text command to the game's chat input."""
    edit_hwnd = find_nested_control(main_hwnd, CHAT_CONTROL_ID)
    if not edit_hwnd: return False
    
    win32gui.SendMessage(edit_hwnd, win32con.WM_SETTEXT, 0, "")
    for char in text:
        win32gui.SendMessage(edit_hwnd, win32con.WM_CHAR, ord(char), 0)
    
    win32gui.SendMessage(edit_hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
    win32gui.SendMessage(edit_hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
    return True

def get_listbox_row(lb_hwnd, index):
    """Reads text from a specific ListBox row using modern array decoding."""
    length = win32gui.SendMessage(lb_hwnd, win32con.LB_GETTEXTLEN, index, 0)
    if length > 0:
        buffer = array.array('H', [0] * (length + 1))
        win32gui.SendMessage(lb_hwnd, win32con.LB_GETTEXT, index, buffer)
        return buffer.tobytes().decode('utf-16le').rstrip('\x00')
    return ""

def perform_vault_scan(main_hwnd, char_name, vault_type="barloque", progress_cb=None):
    """
    Core scanning logic. 
    vault_type: "barloque" or "hungry"
    progress_cb(current, total, item_name, qty)
    Returns list of {"item": name, "quantity": qty}
    """
    command = "withdraw" # Default for Barloque
    if vault_type == "hungry":
        command = "withdraw" # User said they will configure, so keeping same for now
        
    logger.info(f"Starting {vault_type} vault scan for {char_name}...")
    if not send_chat_command(main_hwnd, command):
        logger.error("Could not find chat input.")
        return None

    # Wait for Popup
    dialog_hwnd = None
    for _ in range(20):
        dialog_hwnd = win32gui.FindWindow(DIALOG_CLASS, DIALOG_TEXT)
        if dialog_hwnd and win32gui.IsWindowVisible(dialog_hwnd): break
        time.sleep(0.2)

    if not dialog_hwnd:
        logger.error(f"{vault_type.title()} Vault window did not appear.")
        return None

    time.sleep(0.6)

    # Map ListBoxes
    hwnd_items = find_nested_control(dialog_hwnd, ID_ITEM_LIST)
    hwnd_qtys = find_nested_control(dialog_hwnd, ID_QTY_LIST)
    
    if not hwnd_items or not hwnd_qtys:
        logger.error("Failed to map vault UI components.")
        return None

    total_rows = win32gui.SendMessage(hwnd_items, win32con.LB_GETCOUNT, 0, 0)
    row_height = win32gui.SendMessage(hwnd_items, win32con.LB_GETITEMHEIGHT, 0, 0)
    if row_height <= 0: row_height = 19

    inventory = []
    for i in range(total_rows):
        item_name = get_listbox_row(hwnd_items, i)
        
        # Click row to trigger server update for quantity
        click_param = win32api.MAKELONG(15, (i * row_height) + (row_height // 2))
        win32gui.PostMessage(hwnd_items, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, click_param)
        win32gui.PostMessage(hwnd_items, win32con.WM_LBUTTONUP, 0, click_param)
        
        time.sleep(0.5) # Wait for server update
        qty = get_listbox_row(hwnd_qtys, i)
        
        item_data = {"item": item_name, "quantity": qty.strip() or "0"}
        inventory.append(item_data)
        if progress_cb:
            progress_cb(i + 1, total_rows, item_name, qty)

    # Save Persistence
    safe_name = char_name.replace(" ", "_")
    save_path = f"logs/{safe_name}_vault_{vault_type}.json"
    if not os.path.exists("logs"): os.makedirs("logs")
    with open(save_path, "w") as f:
        json.dump({"timestamp": time.time(), "items": inventory}, f, indent=4)

    win32gui.PostMessage(dialog_hwnd, win32con.WM_CLOSE, 0, 0)
    return inventory

def run_standalone():
    from m59_bridge import establish_bridge, release_pid
    from m59_scraper import capture_identity
    pid = None
    try:
        pm, pid = establish_bridge()
        def get_hwnd_cb(h, l):
            _, p = win32process.GetWindowThreadProcessId(h)
            if p == pid and win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h).startswith("Meridian 59"):
                l.append(h)
        hwnds = []
        win32gui.EnumWindows(get_hwnd_cb, hwnds)
        if not hwnds: return
        main_hwnd = hwnds[0]
        char_name = capture_identity(main_hwnd, pid) or "Unknown"
        
        inventory = perform_vault_scan(main_hwnd, char_name, lambda c, t, i, q: print(f"[{c}/{t}] {i} | {q}"))
        if inventory:
            print(f"Success: Scanned {len(inventory)} items.")
    finally:
        if pid: release_pid(pid)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_standalone()
