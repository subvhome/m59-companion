import os
import time
import json
import pymem
import win32gui
import win32process
import tempfile

# Configuration Path
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except:
        return {"process": {"target_name": "Meridian.exe"}}

def get_lock_dir():
    """Returns the directory used for PID locks to support multi-instance isolation."""
    lock_dir = os.path.join(tempfile.gettempdir(), "m59_companion_locks")
    if not os.path.exists(lock_dir):
        os.makedirs(lock_dir)
    return lock_dir

def cleanup_stale_locks():
    """Removes lock files ONLY if we are 100% sure the companion or game is dead."""
    lock_dir = get_lock_dir()
    for filename in os.listdir(lock_dir):
        if filename.endswith(".lock"):
            lock_path = os.path.join(lock_dir, filename)
            try:
                game_pid = int(filename.replace(".lock", ""))
                
                # Try to read the companion PID. If we can't (busy file), SKIP it.
                try:
                    with open(lock_path, "r") as f:
                        content = f.read().strip()
                        if not content:
                            continue 
                        companion_pid = int(content)
                except (IOError, ValueError):
                    # File might be locked by another process or being written.
                    # Do NOT delete it.
                    continue
                
                # Check if Game is still running
                import psutil
                game_alive = psutil.pid_exists(game_pid)
                companion_alive = psutil.pid_exists(companion_pid)
                
                # Only remove if one of them is definitively gone
                if not game_alive:
                    print(f"DEBUG: Removing lock for Game PID {game_pid} (Game closed)")
                    os.remove(lock_path)
                elif not companion_alive:
                    print(f"DEBUG: Removing lock for Game PID {game_pid} (Companion closed)")
                    os.remove(lock_path)
                    
            except Exception as e:
                # General error, skip this file to be safe
                pass

def release_pid(game_pid):
    """Manually removes a lock file, but only if it belongs to us."""
    lock_file = os.path.join(get_lock_dir(), f"{game_pid}.lock")
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                owner_pid = int(f.read().strip())
            if owner_pid == os.getpid():
                os.remove(lock_file)
        except:
            pass

def is_pid_locked(pid):
    """Checks if a PID is already claimed by another companion instance."""
    lock_file = os.path.join(get_lock_dir(), f"{pid}.lock")
    return os.path.exists(lock_file)

def claim_pid(pid):
    """Atomic exclusive creation of a lock file."""
    lock_file = os.path.join(get_lock_dir(), f"{pid}.lock")
    try:
        # 'x' mode = Create only if not exists (Atomic on most OS)
        with open(lock_file, "x") as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        return False
    except Exception as e:
        print(f"DEBUG: Lock error for {pid}: {e}")
        return False

def get_unclaimed_instances(target_name="Meridian.exe"):
    """
    Returns a list of dictionaries containing {pid, title, hwnd, char_name} 
    for all game instances that are not currently locked by another companion.
    """
    cleanup_stale_locks()
    all_instances = []
    
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if "Meridian 59" in text:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                # Check if it's actually the right process name
                try:
                    import psutil
                    if psutil.Process(pid).name().lower() == target_name.lower():
                        all_instances.append({"pid": pid, "title": text, "hwnd": hwnd})
                except:
                    pass
    
    win32gui.EnumWindows(callback, None)
    
    # Filter only unclaimed ones and try to peek at character names
    from m59_scraper import capture_identity
    unclaimed = []
    for i in all_instances:
        if not is_pid_locked(i["pid"]):
            # Try to peek at character name without claiming
            try:
                # We use capture_identity but note that this requires the window to be accessible
                cname = capture_identity(i["hwnd"], i["pid"]) or "Unknown"
                i["char_name"] = cname
            except:
                i["char_name"] = "Unknown"
            unclaimed.append(i)
            
    return unclaimed

def find_available_instance(target_name):
    """Legacy wrapper for compatibility: Returns the first unclaimed PID found."""
    instances = get_unclaimed_instances(target_name)
    if instances:
        pid = instances[0]["pid"]
        if claim_pid(pid):
            return pid
    return None

def establish_bridge():
    config = load_config()
    target = config["process"]["target_name"]
    
    print(f"--- M59 Bridge: Searching for {target} ---")
    
    while True:
        pid = find_available_instance(target)
        if pid:
            try:
                pm = pymem.Pymem(pid)
                print(f"SUCCESS: Attached to {target} (PID: {pid})")
                return pm, pid
            except Exception as e:
                print(f"ERROR: Could not attach to PID {pid}: {e}")
        
        time.sleep(2) # Wait and retry

if __name__ == "__main__":
    pm = None
    pid = None
    try:
        pm, pid = establish_bridge()
        print("Bridge established. Holding connection...")
        while True:
            # Test connection
            pm.read_int(pm.base_address)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nUser requested exit.")
    except Exception as e:
        print(f"\nConnection lost or error: {e}")
    finally:
        if pid:
            print(f"Releasing lock for PID {pid}...")
            release_pid(pid)
        print("Cleanup complete.")
