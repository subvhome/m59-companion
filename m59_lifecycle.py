import time
import threading
from m59_logging import get_logger
from m59_bridge import get_unclaimed_instances, release_pid, is_pid_locked, claim_pid

logger = get_logger("lifecycle")

def cleanup_stale_locks():
    """
    Cleans up stale lock files from the m59_companion_locks temp directory
    if the corresponding PID is not running, or is not an instance of Meridian.exe.
    """
    import os
    import tempfile
    import pymem
    from m59_bridge import release_pid

    lock_dir = os.path.join(tempfile.gettempdir(), "m59_companion_locks")
    if not os.path.exists(lock_dir):
        return

    logger.info("Lifecycle: Scanning for stale lock files in temp directory...")
    try:
        for filename in os.listdir(lock_dir):
            if filename.endswith(".lock"):
                pid_str = filename.split(".")[0]
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue

                # Verify if this PID is still a running Meridian.exe process
                is_stale = False
                try:
                    # Try attaching with Pymem to see if it exists
                    pm = pymem.Pymem(pid)
                    # Check if the process name is Meridian.exe (case-insensitive)
                    if pm.process_name.lower() != "meridian.exe":
                        is_stale = True
                except Exception:
                    # If Pymem cannot open it (ProcessNotFound or AccessDenied), it's not a running game process we can monitor
                    is_stale = True

                if is_stale:
                    logger.info(f"Lifecycle: Releasing stale lock for PID {pid} (process not running or not Meridian.exe)")
                    try:
                        release_pid(pid)
                    except Exception as e:
                        logger.error(f"Lifecycle: Failed to release PID {pid} via release_pid: {e}")
                    
                    # Direct file cleanup as a robust fallback
                    lock_file_path = os.path.join(lock_dir, filename)
                    if os.path.exists(lock_file_path):
                        try:
                            os.remove(lock_file_path)
                        except Exception:
                            pass
    except Exception as e:
        logger.error(f"Lifecycle: Error during stale locks cleanup: {e}")

class InstanceManager:
    """
    Modular manager to handle the 'Always-On' state for game instances.
    Monitors if the game process dies and automatically searches for a replacement.
    """
    def __init__(self, target_name="Meridian.exe", on_connect_cb=None, on_disconnect_cb=None, on_multiple_found=None):
        self.target_name = target_name
        self.on_connect = on_connect_cb
        self.on_disconnect = on_disconnect_cb
        self.on_multiple_found = on_multiple_found
        
        self.current_pid = None
        self.pm_obj = None
        self.is_monitoring = False
        self.pause_auto_attach = False
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Starts the background monitor thread."""
        if self._thread and self._thread.is_alive():
            return
        
        # Clean up stale lock files on startup
        try:
            cleanup_stale_locks()
        except Exception as e:
            logger.error(f"Lifecycle: Failed to run startup locks cleanup: {e}")
        
        self._stop_event.clear()
        self.is_monitoring = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Lifecycle Monitor started.")

    def stop(self):
        """Stops the background monitor thread."""
        self.is_monitoring = False
        self._stop_event.set()
        if self.current_pid:
            release_pid(self.current_pid)
        logger.info("Lifecycle Monitor stopped.")

    def assign_instance(self, pid):
        """Manually assigns a PID to the manager (used after UI selection)."""
        if is_pid_locked(pid):
            logger.error(f"Lifecycle: Cannot assign PID {pid}, it is already locked.")
            return False
        
        if claim_pid(pid):
            try:
                import pymem
                self.pm_obj = pymem.Pymem(pid)
                self.current_pid = pid
                self.pause_auto_attach = False
                logger.info(f"Lifecycle: Manually assigned to PID {pid}")
                if self.on_connect:
                    self.on_connect(self.pm_obj, pid)
                return True
            except Exception as e:
                logger.error(f"Lifecycle: Failed to attach to manually assigned PID {pid}: {e}")
                release_pid(pid)
        return False

    def _monitor_loop(self):
        while not self._stop_event.is_set():
            if self.current_pid is None:
                if self.pause_auto_attach:
                    time.sleep(2)
                    continue

                # STATE: Searching for game
                unclaimed = get_unclaimed_instances(self.target_name)
                
                if len(unclaimed) > 1 and self.on_multiple_found:
                    logger.info(f"Lifecycle: Found {len(unclaimed)} unclaimed instances. Triggering UI selection.")
                    self.pause_auto_attach = True
                    self.on_multiple_found(unclaimed)
                elif len(unclaimed) == 1:
                    new_pid = unclaimed[0]["pid"]
                    if claim_pid(new_pid):
                        try:
                            import pymem
                            self.pm_obj = pymem.Pymem(new_pid)
                            self.current_pid = new_pid
                            logger.info(f"Auto-Reconnect: Attached to single PID {new_pid}")
                            
                            if self.on_connect:
                                self.on_connect(self.pm_obj, new_pid)
                        except Exception as e:
                            logger.error(f"Auto-Reconnect: Failed to attach to PID {new_pid}: {e}")
                            release_pid(new_pid)
                            self.current_pid = None
            else:
                # STATE: Monitoring active game
                try:
                    # Heartbeat check
                    self.pm_obj.read_int(self.pm_obj.base_address)
                except Exception:
                    logger.warn(f"Auto-Reconnect: Connection to PID {self.current_pid} lost.")
                    old_pid = self.current_pid
                    self.current_pid = None
                    self.pm_obj = None
                    
                    # Clean up the lock so we can re-find the game if it restarts
                    release_pid(old_pid)
                    
                    if self.on_disconnect:
                        self.on_disconnect(old_pid)
            
            # Polling interval
            time.sleep(2)

def test_lifecycle():
    def connected(pm, pid):
        print(f"CONNECTED TO: {pid}")
    def disconnected(pid):
        print(f"DISCONNECTED FROM: {pid}")
        
    mgr = InstanceManager(on_connect_cb=connected, on_disconnect_cb=disconnected)
    mgr.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        mgr.stop()

if __name__ == "__main__":
    test_lifecycle()
