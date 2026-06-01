import os
import time
import win32gui
import win32con
import win32process
import pymem
from m59_bridge import establish_bridge, release_pid
from m59_logging import get_logger

logger = get_logger("scraper")

class MemoryReader:
    def __init__(self, pm):
        self.pm = pm
    def read_skill_percent(self, base_address):
        if base_address <= 65535: return 0
        try:
            target_addr = base_address + 16
            val = self.pm.read_int(target_addr)
            return val if 0 <= val <= 100 else 0
        except Exception as e:
            logger.debug(f"Failed to read skill percent at {base_address}: {e}")
            return 0

def get_text_from_hwnd(hwnd):
    """
    Reads text from a window control. 
    Note: Meridian 59 chat controls (ID 1005) have a ~29,998 character buffer limit.
    After this limit is reached, older characters are truncated from the top.
    """
    try:
        length = win32gui.SendMessage(hwnd, win32con.WM_GETTEXTLENGTH, 0, 0)
        if length > 0:
            import array
            # Use 'H' (unsigned short) for UTF-16 characters to avoid 'u' deprecation
            buffer = array.array('H', [0] * (length + 1))
            win32gui.SendMessage(hwnd, win32con.WM_GETTEXT, length + 1, buffer)
            return buffer.tobytes().decode('utf-16le').rstrip('\x00')
    except Exception as e:
        logger.error(f"Failed to get text from HWND {hwnd}: {e}")
    return ""

def capture_identity(hwnd, target_pid):
    """
    Triggers the in-game Bio window and extracts the character name.
    """
    # 1. Verify we are looking at the main game window
    face_btn = win32gui.GetDlgItem(hwnd, 5001)
    if not face_btn or not win32gui.IsWindowVisible(face_btn):
        logger.debug("Identity: Face button not visible. UI not ready.")
        return None

    # 2. Trigger the Bio Window
    win32gui.SendMessage(face_btn, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, 0)
    win32gui.SendMessage(face_btn, win32con.WM_RBUTTONUP, 0, 0)
    
    start_time = time.time()
    while time.time() - start_time < 5.0:
        bio_hwnd = [None]
        
        def find_bio_cb(h, param):
            if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "#32770":
                _, p = win32process.GetWindowThreadProcessId(h)
                if p == target_pid:
                    try:
                        # ID 1011 is the character name field in the Bio dialog
                        if win32gui.GetDlgItem(h, 1011):
                            bio_hwnd[0] = h
                            return False
                    except:
                        pass
            return True
        
        win32gui.EnumWindows(find_bio_cb, None)
        
        if bio_hwnd[0]:
            name_hwnd = win32gui.GetDlgItem(bio_hwnd[0], 1011)
            if name_hwnd:
                name = get_text_from_hwnd(name_hwnd)
                logger.debug(f"Identity: Found window {bio_hwnd[0]}, text read: '{name}'")
                
                if name and name not in ["...", "Unknown", ""]:
                    # SUCCESS: Clean up and return
                    win32gui.PostMessage(bio_hwnd[0], win32con.WM_CLOSE, 0, 0)
                    return name
        
        time.sleep(0.5)
        
    # If we found a window but never got a valid name, close it anyway to clean up
    if bio_hwnd[0]:
        win32gui.PostMessage(bio_hwnd[0], win32con.WM_CLOSE, 0, 0)
        
    return None

# BlakGraph Constants
WM_USER = 0x0400
GRPH_POSGET = WM_USER + 1005

def get_blakgraph_stats(game_hwnd):
    """
    Retrieves HP, MP, VG and Attributes by sorting BlakGraphs vertically.
    No hard-coded coordinates used.
    """
    graphs = []
    # Only find VISIBLE BlakGraphs
    def enum_cb(h, l):
        if win32gui.GetClassName(h) == "BlakGraph" and win32gui.IsWindowVisible(h):
            graphs.append({
                "hwnd": h,
                "y": win32gui.GetWindowRect(h)[1]
            })
    win32gui.EnumChildWindows(game_hwnd, enum_cb, None)

    if not graphs:
        return {}

    # Sort all visible graphs from top to bottom
    sorted_graphs = sorted(graphs, key=lambda x: x["y"])
    
    stats = {}
    
    # The first 3 are always Core Stats (HP, MP, VG)
    if len(sorted_graphs) >= 3:
        for i, key in enumerate(["HP", "MP", "VG"]):
            val = win32gui.SendMessage(sorted_graphs[i]["hwnd"], GRPH_POSGET, 0, 0)
            if val > 0x7FFFFFFF: val -= 0x100000000
            stats[key] = val

    # If there are more than 3, the rest are Attributes (visible on Tab 3)
    if len(sorted_graphs) > 3:
        attr_labels = ["Might", "Intellect", "Stamina", "Agility", "Mysticism", "Aim", "Karma"]
        attr_graphs = sorted_graphs[3:]
        
        for i, label in enumerate(attr_labels):
            if i < len(attr_graphs):
                val = win32gui.SendMessage(attr_graphs[i]["hwnd"], GRPH_POSGET, 0, 0)
                if val > 0x7FFFFFFF: val -= 0x100000000
                stats[label] = val

    return stats

def cycle_tabs_and_scrape(hwnd, mem):
    """Sequence: Click Spells -> Click Skills -> Click Stats -> pull data."""
    all_tabs = []
    win32gui.EnumChildWindows(hwnd, lambda h, l: all_tabs.append({
        "hwnd": h, 
        "x": win32gui.GetWindowRect(h)[0]
    }) if win32gui.GetDlgCtrlID(h) == 1029 else None, None)
    
    # Sort horizontally to ensure Spells=1, Skills=2, Stats=3
    sorted_tabs = sorted(all_tabs, key=lambda x: x["x"])
    tab_handles = [t["hwnd"] for t in sorted_tabs]
    
    if len(tab_handles) < 4:
        print(f"ERROR: Only found {len(tab_handles)} tab buttons. Need at least 4.")
        return {}, {}

    # Sequence: Spells (1) -> Skills (2) -> Stats (3) -> Spells (1)
    print("Cycling tabs to refresh UI buffer and stats...")
    for idx in [1, 2, 3, 1]:
        win32gui.SendMessage(tab_handles[idx], win32con.BM_CLICK, 0, 0)
        time.sleep(0.5)

    knowledge = {}
    
    # 1. Scrape Skill/Spell ListBoxes
    for tab_name, tab_idx in [("Spells", 1), ("Skills", 2)]:
        win32gui.SendMessage(tab_handles[tab_idx], win32con.BM_CLICK, 0, 0)
        time.sleep(0.6) # Slightly longer wait for refresh
        
        lb_hwnd = None
        def find_lb(h, l):
            nonlocal lb_hwnd
            if win32gui.GetClassName(h) == "ListBox" and win32gui.IsWindowVisible(h):
                lb_hwnd = h
        win32gui.EnumChildWindows(hwnd, find_lb, None)
        
        if lb_hwnd:
            count = win32gui.SendMessage(lb_hwnd, win32con.LB_GETCOUNT, 0, 0)
            for i in range(count):
                t_len = win32gui.SendMessage(lb_hwnd, win32con.LB_GETTEXTLEN, i, 0)
                import array
                buf = array.array('H', [0] * (t_len + 1))
                win32gui.SendMessage(lb_hwnd, win32con.LB_GETTEXT, i, buf)
                label = buf.tobytes().decode('utf-16le').rstrip('\x00').lower()
                base_addr = win32gui.SendMessage(lb_hwnd, win32con.LB_GETITEMDATA, i, 0)
                percent = mem.read_skill_percent(base_addr)
                knowledge[label] = percent
    
    # 2. Scrape Stats Tab
    print("Scraping Attributes (Tab 3)...")
    win32gui.SendMessage(tab_handles[3], win32con.BM_CLICK, 0, 0)
    time.sleep(0.6)
    stats = get_blakgraph_stats(hwnd)
    
    # Return to Spells
    win32gui.SendMessage(tab_handles[1], win32con.BM_CLICK, 0, 0)
    
    return knowledge, stats

def run_scraper():
    pm = None
    pid = None
    try:
        pm_obj, pid = establish_bridge()
        mem = MemoryReader(pm_obj)
        
        def get_hwnd_cb(h, l):
            _, p = win32process.GetWindowThreadProcessId(h)
            if p == pid and win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h).startswith("Meridian 59"):
                l.append(h)
        
        hwnds = []
        win32gui.EnumWindows(get_hwnd_cb, hwnds)
        if not hwnds: 
            print("ERROR: Could not find HWND.")
            return
        hwnd = hwnds[0]

        name = capture_identity(hwnd, pid)
        if name:
            print(f"IDENTITY VERIFIED: {name}")
        
        knowledge, stats = cycle_tabs_and_scrape(hwnd, mem)
        
        if stats:
            print("\n--- CORE STATS & ATTRIBUTES ---")
            for k in ["HP", "MP", "VG"]:
                if k in stats: print(f" {k:<10}: {stats[k]}")
            print("-" * 30)
            for k in ["Might", "Intellect", "Stamina", "Agility", "Mysticism", "Aim", "Karma"]:
                if k in stats: print(f" {k:<10}: {stats[k]}")

        if knowledge:
            print(f"\nSUCCESS: Scraped {len(knowledge)} total skills/spells:")
            for k in sorted(knowledge.keys()):
                print(f" - {k.title()}: {knowledge[k]}%")
        else:
            print("\nSCRAPER: No knowledge data found.")

        print("\n--- HOLDING LOCK FOR TESTING ---")
        print("Keep this window open to keep the lock engaged.")
        print("Open another terminal to test the second instance.")
        while True:
            # Periodically check if the game is still there
            pm_obj.read_int(pm_obj.base_address)
            time.sleep(5)

    except Exception as e:
        print(f"\nScraper Error or Game Closed: {e}")
    finally:
        if pid: 
            print(f"Releasing lock for PID {pid}...")
            release_pid(pid)

if __name__ == "__main__":
    try: 
        run_scraper()
    except KeyboardInterrupt: 
        print("\nExiting...")
