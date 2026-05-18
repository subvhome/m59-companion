import os
import time
import win32gui
import win32con
import win32process
from datetime import datetime
from m59_bridge import establish_bridge, release_pid
from m59_scraper import get_text_from_hwnd, capture_identity
from m59_tracker import SessionTracker
from m59_combat import CombatMonitor

def manage_rotation(char_name, log_path):
    """Handles 24-hour rotation with unique timestamps."""
    if not os.path.exists(log_path):
        return
    
    creation_time = os.path.getctime(log_path)
    if time.time() - creation_time > 86400: # 24 hours
        log_dir = os.path.dirname(log_path)
        safe_name = char_name.replace(" ", "_")
        now_ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        rotated_path = os.path.join(log_dir, f"{safe_name}_chat_{now_ts}.log")
        
        counter = 1
        base_rotated = rotated_path
        while os.path.exists(rotated_path):
            rotated_path = base_rotated.replace(".log", f"_{counter}.log")
            counter += 1

        try:
            os.rename(log_path, rotated_path)
            print(f"ROTATION: Moved old log to {os.path.basename(rotated_path)}")
        except Exception as e:
            print(f"ROTATION ERROR: {e}")

def run_logger():
    pm = None
    pid = None
    try:
        # 1. Attach to Game
        pm_obj, pid = establish_bridge()
        
        # 2. Find Window
        def get_hwnd_cb(h, l):
            _, p = win32process.GetWindowThreadProcessId(h)
            if p == pid and win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h).startswith("Meridian 59"):
                l.append(h)
        hwnds = []
        win32gui.EnumWindows(get_hwnd_cb, hwnds)
        if not hwnds: return
        hwnd = hwnds[0]

        # 3. Identity
        char_name = capture_identity(hwnd, pid)
        if not char_name:
            print("IDENTITY: Failed to capture name. Logging as 'Unknown'.")
            char_name = "Unknown"
        else:
            print(f"IDENTITY: Logging for {char_name}")

        # 4. Setup File
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        safe_name = char_name.replace(" ", "_")
        log_path = os.path.join(log_dir, f"{safe_name}_chat.log")
        
        # 5. Initialization (Take snapshot of current buffer)
        chat_hwnd = win32gui.GetDlgItem(hwnd, 1005)
        if not chat_hwnd:
            print("ERROR: Chat control (ID 1005) not found.")
            return

        print("Initializing buffer snapshot...")
        current_text = get_text_from_hwnd(chat_hwnd)
        all_lines = [l.strip() for l in current_text.splitlines() if l.strip()]
        
        # Initialize Tracker
        tracker = SessionTracker()
        # Initialize Combat Monitor
        combat = CombatMonitor(char_name)
        
        # We track a 'tail' of the last 50 lines to create a unique fingerprint.
        # This virtually eliminates false positives during combat spam.
        last_tail = all_lines[-50:] if all_lines else []
        
        print(f"Monitoring chat for {char_name}... (Ctrl+C to stop)")
        
        # 6. Main Monitoring Loop
        while True:
            # Handle Rotation
            manage_rotation(char_name, log_path)
            
            # Read Buffer
            current_text = get_text_from_hwnd(chat_hwnd)
            all_lines = [l.strip() for l in current_text.splitlines() if l.strip()]
            
            new_lines = []
            if not last_tail:
                new_lines = all_lines
            else:
                # --- OPTIMIZED SLIDING WINDOW FINGERPRINT MATCH ---
                found_idx = -1
                temp_tail = list(last_tail)
                
                # We try to find our tail in the current buffer.
                # We search from the bottom of the buffer up, as that's where new data is.
                while temp_tail:
                    tail_len = len(temp_tail)
                    # Optimization: Only search the last 100 lines for the tail first
                    # as it's unlikely to have scrolled further in 1 second.
                    search_range = all_lines[-100-tail_len:] if len(all_lines) > 100 else all_lines
                    range_offset = len(all_lines) - len(search_range)
                    
                    for i in range(len(search_range) - tail_len, -1, -1):
                        if search_range[i:i+tail_len] == temp_tail:
                            found_idx = range_offset + i + tail_len
                            break
                    
                    if found_idx != -1:
                        break
                    temp_tail.pop(0) # Shrink and try again
                
                if found_idx != -1:
                    new_lines = all_lines[found_idx:]
                else:
                    # Buffer reset (Logout/Login)
                    if len(all_lines) > 0:
                        print("DEBUG: Buffer reset detected (Fingerprint lost). Re-syncing snapshot...")
                        last_tail = all_lines[-50:]
                        new_lines = []
                    else:
                        new_lines = []

            if new_lines:
                ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        for line in new_lines:
                            # 1. Write to history file (Always)
                            f.write(f"{ts} {line}\n")
                            
                            # 2. Print line to console (Always, for context)
                            print(f"{ts} {line}")

                            # 3. Process for live gains
                            gain = tracker.process_line(line)
                            if gain:
                                print(f" *** [GAIN] {gain['name']} #{gain['count']} (Delta: {gain['delta']}) ***")
                            
                            # 4. Process for combat events (Kills/PK Attacks)
                            combat_res = combat.process_line(line)
                            if combat_res:
                                if combat_res["type"] == "KILL":
                                    cat = combat_res["category"].upper()
                                    print(f" >>> [{cat} KILL] {combat_res['name']} | Total: {combat_res['total']} <<<")
                                elif combat_res["type"] == "PK_ALERT":
                                    print(f" !!! [PK ALERT] {combat_res['name']} is ATTACKING YOU! !!!")
                        f.flush()
                except Exception as e:
                    print(f"FILE ERROR: {e}")

                # Update Tail (Keep last 50)
                for line in new_lines:
                    last_tail.append(line)
                last_tail = last_tail[-50:]

            time.sleep(1)
            
            # Heartbeat check
            pm_obj.read_int(pm_obj.base_address)

    except KeyboardInterrupt:
        print("\nLogger stopped by user.")
    except Exception as e:
        print(f"\nLogger Error: {e}")
    finally:
        if pid: release_pid(pid)

if __name__ == "__main__":
    run_logger()
