import pymem
import logging
# We set up a named logger for this specific module
logger = logging.getLogger("m59.memory")
class MemoryReader:
    def __init__(self, process_name="Meridian.exe"):
        self.process_name = process_name
        self.pm = None
        self.process_handle = None
        logger.info(f"MemoryReader initialized for {self.process_name}")
        self.attach()
        
    def attach(self):
        """Attempts to find the process and update the handle."""
        # 1. Check if we have a healthy handle already
        if self.pm and self.process_handle:
            try:
                # Test the handle; if it fails, the process likely restarted
                self.pm.read_int(self.pm.base_address)
                return True
            except Exception:
                logger.warning("Existing handle is stale. Clearing for re-attachment.")
                self.pm = None
                self.process_handle = None
        # 2. Attempt a fresh attachment
        try:
            self.pm = pymem.Pymem(self.process_name)
            self.process_handle = self.pm.process_handle
            logger.info(f"Successfully attached to {self.process_name} (Handle: {self.process_handle})")
            return True
        except Exception:
            # Silently fail here; the update_loop will try again in 1 second
            self.pm = None
            self.process_handle = None
            return False
            
    def read_skill_percent(self, base_address):
        """Reads a skill percentage from memory with validation and logging."""
        # 1. Verification of handle
        if not self.pm or not self.process_handle:
            logger.debug(f"Read aborted: No valid handle for address {hex(base_address)}")
            return 0
            
        # 2. Validation of pointer address
        if base_address <= 65535:
            logger.debug(f"Read aborted: {hex(base_address)} is a Null or invalid pointer.")
            return 0
            
        try:
            # The percentage is located 16 bytes past the base address
            target_addr = base_address + 16
            val = self.pm.read_int(target_addr)
            
            # 3. Logic validation
            if 0 <= val <= 100:
                logger.debug(f"Memory Read Success: {hex(target_addr)} -> {val}%")
                return val
            else:
                logger.warning(f"Junk data detected at {hex(target_addr)}: {val}. Defaulting to 0.")
                return 0
                
        except Exception as e:
            logger.error(f"Critical Memory Read Error at {hex(base_address)}: {e}")
            return 0
