import win32gui
import win32con
import array
import time
import logging
# We import the shared memory object from bridge to ensure we always target the correct PID
from m59_bridge import mem

# Setup module-level logger
logger = logging.getLogger("m59.lists")
def get_raw_skill_dict(hwnd, min_items=1):
    """
    Scrapes the game ListBox and correlates it with memory addresses.
    Includes stabilization logic to wait for the UI to populate.
    """
    logger.info(f"Starting skill scrape for HWND {hwnd} (Min items expected: {min_items})")
    
    skill_map = {}
    start_time = time.time()
    stable_count = 0
    
    # --- STABILIZATION LOOP ---
    # Loop for up to 4 seconds to reach stabilization AND minimum threshold
    while time.time() - start_time < 4.0:
        current_count = win32gui.SendMessage(hwnd, win32con.LB_GETCOUNT, 0, 0)
        logger.debug(f"Stabilization check: Found {current_count} items...")
        
        # If we have at least min_items and the count is stable, proceed
        if current_count >= min_items:
            time.sleep(0.3) # Final settling breath
            check_count = win32gui.SendMessage(hwnd, win32con.LB_GETCOUNT, 0, 0)
            if check_count == current_count:
                logger.info(f"ListBox stabilized at {current_count} items after {time.time() - start_time:.2f}s")
                stable_count = current_count
                break
        time.sleep(0.3)
    final_count = win32gui.SendMessage(hwnd, win32con.LB_GETCOUNT, 0, 0)
    if final_count < min_items:
        logger.warning(f"Scrape proceeding with sub-optimal count: {final_count}/{min_items}")
    
    # --- DATA EXTRACTION ---
    for i in range(final_count):
        # 1. Get the text label (e.g., "Fencing")
        length = win32gui.SendMessage(hwnd, win32con.LB_GETTEXTLEN, i, 0)
        if length > 0:
            buffer = array.array('u', '\x00' * (length + 1))
            win32gui.SendMessage(hwnd, win32con.LB_GETTEXT, i, buffer)
            label = buffer.tounicode().rstrip('\x00').lower()
            
            # 2. Get the internal pointer associated with this list item
            base_addr = win32gui.SendMessage(hwnd, win32con.LB_GETITEMDATA, i, 0)
            
            # 3. Read the actual percentage from memory via the pointer
            percent = mem.read_skill_percent(base_addr)
            
            skill_map[label] = int(percent)
            logger.debug(f"Scraped: [{label}] at {hex(base_addr)} -> {percent}%")
            
    logger.info(f"Successfully scraped {len(skill_map)} unique skills/spells.")
    return skill_map
