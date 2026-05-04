import pymem

class MemoryReader:
    def __init__(self, process_name="Meridian.exe"):
        try:
            self.pm = pymem.Pymem(process_name)
            print(f">>> [DEBUG] Successfully attached to {process_name}")
        except Exception as e:
            print(f">>> [ERROR] Could not find game: {e}")
            self.pm = None

    def read_skill_percent(self, base_address):
        # If the address is 0 or extremely low (0xFFFF), it's a null pointer.
        # Reading this will crash the game. We return 0 and skip it.
        if not self.pm or base_address <= 65535: 
            return 0
            
        try:
            if self.pm.process_handle:
                # The percentage is located 16 bytes past the base address
                target_addr = base_address + 16
                val = self.pm.read_int(target_addr)
                
                # Logic check: Skills are always 0-100%
                if 0 <= val <= 100:
                    return val
                else:
                    print(f">>> [WARN] Junk data at {hex(target_addr)}: {val}")
                    return 0
        except Exception as e:
            print(f">>> [CRITICAL] Memory Read Error at {hex(base_address)}: {e}")
            return 0
        return 0
