import win32gui
import win32con
import win32api
import array

WM_USER = 0x0400
GRPH_POSGET = WM_USER + 1005 

def find_game_window():
    hwnds = []
    win32gui.EnumWindows(lambda hwnd, l: hwnds.append(hwnd) 
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).startswith("Meridian 59") 
        else None, None)
    return hwnds[0] if hwnds else None

def get_text_from_hwnd(hwnd):
    length = win32gui.SendMessage(hwnd, win32con.WM_GETTEXTLENGTH, 0, 0)
    if length > 0:
        buffer = array.array('u', '\x00' * (length + 1))
        win32gui.SendMessage(hwnd, win32con.WM_GETTEXT, length + 1, buffer)
        return buffer.tounicode().rstrip('\x00')
    return ""

def get_stats(game_hwnd):
    graphs = []
    win32gui.EnumChildWindows(game_hwnd, lambda h, l: graphs.append((h, win32gui.GetWindowRect(h)[1])) 
                              if win32gui.GetClassName(h) == "BlakGraph" else None, None)
    graphs.sort(key=lambda x: x[1]) 
    if len(graphs) >= 3:
        h = win32gui.SendMessage(graphs[0][0], GRPH_POSGET, 0, 0)
        m = win32gui.SendMessage(graphs[1][0], GRPH_POSGET, 0, 0)
        v = win32gui.SendMessage(graphs[2][0], GRPH_POSGET, 0, 0)
        return h, m, v
    return None

def find_skill_listbox(game_hwnd):
    """Searches the game for the active ListBox ID automatically."""
    found_id = [None]
    
    def callback(hwnd, extra):
        # We look for a window that is a 'ListBox' and is currently visible
        if win32gui.GetClassName(hwnd) == "ListBox" and win32gui.IsWindowVisible(hwnd):
            found_id[0] = hwnd
            
    win32gui.EnumChildWindows(game_hwnd, callback, None)
    return found_id[0]
