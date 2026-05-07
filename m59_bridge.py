import win32gui
import win32con
import win32api
import array
import logging
from m59_memory import MemoryReader
# Setup module-level logger
logger = logging.getLogger("m59.bridge")
WM_USER = 0x0400
GRPH_POSGET = WM_USER + 1005 
def find_game_window():
    """Locates the Meridian 59 window and logs the process."""
    #logger.debug("Searching for Meridian 59 game window...")
    hwnds = []
    win32gui.EnumWindows(lambda hwnd, l: hwnds.append(hwnd) 
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).startswith("Meridian 59") 
        else None, None)
    
    if hwnds:
        #logger.debug(f"Found game window: {win32gui.GetWindowText(hwnds[0])} (HWND: {hwnds[0]})")
        return hwnds[0]
    
    logger.warning("Game window 'Meridian 59' not found.")
    return None
def get_text_from_hwnd(hwnd):
    """Dynamically allocated extraction for large chat buffers."""
    try:
        # Ask the window how many characters it currently holds
        text_length = win32gui.SendMessage(hwnd, win32con.WM_GETTEXTLENGTH, 0, 0)
        
        if text_length <= 0:
            return ""

        # Create a buffer large enough to hold everything + a safety margin
        buffer_size = text_length + 1
        buffer = array.array('u', '\x00' * buffer_size)
        
        # Pull the full content
        win32gui.SendMessage(hwnd, win32con.WM_GETTEXT, buffer_size, buffer)
        
        # Clean up the text and return it
        return buffer.tounicode().rstrip('\x00')
    except Exception as e:
        logger.error(f"Failed to get text from HWND: {e}")
        return ""
def get_stats(game_hwnd):
    """Retrieves HP, Mana, and Vigor stats from BlakGraph components."""
    #logger.debug(f"Enumerating stat graphs for HWND {game_hwnd}...")
    graphs = []
    win32gui.EnumChildWindows(game_hwnd, lambda h, l: graphs.append((h, win32gui.GetWindowRect(h)[1])) 
                              if win32gui.GetClassName(h) == "BlakGraph" else None, None)
    
    # Sort by vertical position to identify HP vs MP vs VG
    graphs.sort(key=lambda x: x[1]) 
    
    if len(graphs) >= 3:
        h = win32gui.SendMessage(graphs[0][0], GRPH_POSGET, 0, 0)
        m = win32gui.SendMessage(graphs[1][0], GRPH_POSGET, 0, 0)
        v = win32gui.SendMessage(graphs[2][0], GRPH_POSGET, 0, 0)
        #logger.debug(f"Stats retrieved - HP: {h}, MP: {m}, VG: {v}")
        return h, m, v
    
    logger.error(f"Failed to find all 3 stat graphs. Found: {len(graphs)}")
    return None
def find_skill_listbox(game_hwnd):
    """Searches the game for the active ListBox ID automatically."""
    logger.debug(f"Scanning for active skill ListBox in HWND {game_hwnd}...")
    found_id = [None]
    
    def callback(hwnd, extra):
        if win32gui.GetClassName(hwnd) == "ListBox" and win32gui.IsWindowVisible(hwnd):
            found_id[0] = hwnd
            
    win32gui.EnumChildWindows(game_hwnd, callback, None)
    
    if found_id[0]:
        logger.info(f"Active ListBox identified: HWND {found_id[0]}")
    else:
        logger.debug("No visible ListBox found in current window state.")
        
    return found_id[0]
# Initialize the global memory object
# Note: The MemoryReader handles its own internal attachment logging
logger.info("Initializing global MemoryReader instance 'mem' in bridge.")
mem = MemoryReader()
