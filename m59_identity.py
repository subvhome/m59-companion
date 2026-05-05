import win32gui
import win32con
import win32api
import time
import logging
from m59_bridge import get_text_from_hwnd
# Setup module-level logger
logger = logging.getLogger("m59.identity")
def capture_character_name(game_hwnd):
    """
    Automates right-clicking the character face to extract the player name.
    """
    logger.info("Attempting to capture character identity...")
    
    # ID 5001 is the standard 'Face' button in the Meridian 59 client
    face_btn = win32gui.GetDlgItem(game_hwnd, 5001)
    if not face_btn: 
        logger.error("Could not find Face Button (ID 5001). Is the game in a logged-in state?")
        return None
    
    # Trigger the Bio window via Right-Click simulation
    logger.debug("Sending Right-Click to face button...")
    win32gui.SendMessage(face_btn, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, 0)
    win32gui.SendMessage(face_btn, win32con.WM_RBUTTONUP, 0, 0)
    
    # Verification Loop: Wait up to 5 seconds for the name to populate
    start_time = time.time()
    logger.debug("Waiting for 'Player Description' window to appear...")
    
    while time.time() - start_time < 5.0:
        # #32770 is the standard Windows class for dialog boxes
        bio_hwnd = win32gui.FindWindow("#32770", "Player Description")
        
        if bio_hwnd:
            logger.debug(f"Bio window found (HWND: {bio_hwnd}). Checking name field...")
            name_hwnd = win32gui.GetDlgItem(bio_hwnd, 1011)
            name = get_text_from_hwnd(name_hwnd)
            
            # Ensure we didn't just grab the "..." placeholder
            if name and name != "...":
                logger.info(f"Identity Verified: {name}")
                
                # Close the window automatically to clean up the UI
                win32api.PostMessage(bio_hwnd, win32con.WM_CLOSE, 0, 0)
                return name
            else:
                logger.debug("Name field still shows placeholder '...'. Retrying...")
        
        time.sleep(0.5)
    
    logger.warning("Name capture timed out after 5.0 seconds. The Bio window may not have opened.")
    return None
