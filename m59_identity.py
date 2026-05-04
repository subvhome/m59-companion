import win32gui
import win32con
import win32api
import time
from m59_bridge import get_text_from_hwnd

def capture_character_name(game_hwnd):
    print(">>> [MODULE] Entering m59_identity: capture_character_name")
    face_btn = win32gui.GetDlgItem(game_hwnd, 5001)
    if not face_btn: 
        return None
    
    # Trigger the Bio window
    win32gui.SendMessage(face_btn, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, 0)
    win32gui.SendMessage(face_btn, win32con.WM_RBUTTONUP, 0, 0)
    
    # Verification Loop: Wait up to 5 seconds for the name to populate
    start_time = time.time()
    while time.time() - start_time < 5.0:
        bio_hwnd = win32gui.FindWindow("#32770", "Player Description")
        if bio_hwnd:
            name_hwnd = win32gui.GetDlgItem(bio_hwnd, 1011)
            name = get_text_from_hwnd(name_hwnd)
            
            # Ensure we didn't just grab the "..." placeholder
            if name and name != "...":
                print(f">>> [DEBUG] Identity Verified: {name}")
                win32api.PostMessage(bio_hwnd, win32con.WM_CLOSE, 0, 0)
                return name
        time.sleep(0.5)
    
    print(">>> [ERROR] Name capture timed out.")
    return None
