import win32gui
import win32con
import win32api
import time
from m59_bridge import get_text_from_hwnd

def capture_character_name(game_hwnd):
    print(">>> [MODULE] Entering m59_identity: capture_character_name")
    face_btn = win32gui.GetDlgItem(game_hwnd, 5001)
    if not face_btn: 
        print(">>> [DEBUG] Face button 5001 not found.")
        return None
    
    print(">>> [DEBUG] Sending right-click to face button...")
    win32gui.SendMessage(face_btn, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, 0)
    win32gui.SendMessage(face_btn, win32con.WM_RBUTTONUP, 0, 0)
    
    time.sleep(2.5) 
    
    bio_hwnd = win32gui.FindWindow("#32770", "Player Description")
    if bio_hwnd:
        print(">>> [DEBUG] Found Player Description window.")
        time.sleep(0.1) 
        name_hwnd = win32gui.GetDlgItem(bio_hwnd, 1011)
        name = get_text_from_hwnd(name_hwnd)
        print(f">>> [DEBUG] Raw name captured: {name}")
        
        win32api.PostMessage(bio_hwnd, win32con.WM_CLOSE, 0, 0)
        return name if name and name != "..." else None
    
    print(">>> [DEBUG] Player Description window NOT found.")
    return None
