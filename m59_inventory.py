import ctypes
import ctypes.wintypes
import struct
import logging
from m59_utils import resource_path

logger = logging.getLogger("m59.inventory")

class InventoryScraper:
    def __init__(self, pm):
        self.pm = pm
        self.h_proc = pm.process_handle
        self.base_addr = pm.base_address
        self.player_addr = None
        self.table_ptr_addr = None
        self.calibrate()

    def _read_mem(self, address, size):
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        if ctypes.windll.kernel32.ReadProcessMemory(self.h_proc, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytes_read)):
            return buffer.raw
        return None

    def _read_u32(self, address):
        data = self._read_mem(address, 4)
        return struct.unpack("<I", data)[0] if data else 0

    def find_export_addr(self, export_name):
        """Parses PE header to find export addresses dynamically."""
        try:
            dos_header = self._read_mem(self.base_addr, 64)
            lfanew = struct.unpack("<I", dos_header[0x3C:0x40])[0]
            nt_headers = self._read_mem(self.base_addr + lfanew, 256)
            export_table_rva = struct.unpack("<I", nt_headers[24+96:24+100])[0]
            if export_table_rva == 0: return None
            
            export_dir = self._read_mem(self.base_addr + export_table_rva, 40)
            n_names = struct.unpack("<I", export_dir[24:28])[0]
            addr_functions = struct.unpack("<I", export_dir[28:32])[0]
            addr_names = struct.unpack("<I", export_dir[32:36])[0]
            addr_ordinals = struct.unpack("<I", export_dir[36:40])[0]
            
            for i in range(n_names):
                name_rva = struct.unpack("<I", self._read_mem(self.base_addr + addr_names + i*4, 4))[0]
                name = self._read_mem(self.base_addr + name_rva, 64).split(b'\0')[0].decode('ascii', errors='ignore')
                if name == export_name:
                    ordinal = struct.unpack("<H", self._read_mem(self.base_addr + addr_ordinals + i*2, 2))[0]
                    func_rva = struct.unpack("<I", self._read_mem(self.base_addr + addr_functions + ordinal*4, 4))[0]
                    return self.base_addr + func_rva
        except Exception as e:
            logger.error(f"Export discovery error: {e}")
        return None

    def calibrate(self):
        """Calibrates addresses via game exports."""
        # Find 'player' address
        api_player = self.find_export_addr("GetPlayerInfo")
        if api_player:
            code = self._read_mem(api_player, 5)
            if code and code[0] == 0xB8: # mov eax, imm32
                self.player_addr = struct.unpack("<I", code[1:5])[0]

        # Find 'resource table' address
        api_rsc = self.find_export_addr("LookupNameRsc")
        if api_rsc:
            code_rsc = self._read_mem(api_rsc, 64)
            for i in range(len(code_rsc)-6):
                if code_rsc[i] == 0xFF and code_rsc[i+1] == 0x35:
                    self.table_ptr_addr = struct.unpack("<I", code_rsc[i+2:i+6])[0]
                    break
        
        if self.player_addr and self.table_ptr_addr:
            logger.info(f"Inventory Scraper Calibrated: Player={hex(self.player_addr)}, Table={hex(self.table_ptr_addr)}")
        else:
            logger.warning("Scraper calibration failed.")

    def lookup_item_name(self, res_id):
        """Resolves a Resource ID to a human-readable name using the game's table."""
        t_addr = self._read_u32(self.table_ptr_addr)
        if not t_addr: return f"ID:{res_id}"
        
        size = self._read_u32(t_addr)
        entries = self._read_u32(t_addr + 4)
        if not entries: return f"ID:{res_id}"
        
        node = self._read_u32(entries + (res_id % size) * 4)
        while node:
            data_ptr = self._read_u32(node)
            if data_ptr and self._read_u32(data_ptr) == res_id:
                str_ptr = self._read_u32(data_ptr + 4)
                raw_str = self._read_mem(str_ptr, 128)
                if raw_str:
                    return raw_str.split(b'\0')[0].decode('ascii', errors='ignore').strip()
            node = self._read_u32(node + 8)
        return f"ID:{res_id}"

    def get_max_weight(self, might):
        """Calculates total weight capacity based on Might (1.6.0 formula)."""
        # Formula from player.kod: viWeight_hold_max (1700) + (Might * 20)
        try:
            return 1700 + (int(might) * 20)
        except (ValueError, TypeError):
            return 1700

    def scan_inventory(self):
        """Traverses the inventory linked list."""
        if not self.player_addr: self.calibrate()
        if not self.player_addr: return []

        inventory_head = self._read_u32(self.player_addr + 68)
        if not inventory_head: return []

        items = []
        curr, visited = inventory_head, set()
        while curr and curr not in visited and len(items) < 500:
            visited.add(curr)
            data_ptr = self._read_u32(curr)
            if data_ptr:
                res_id = self._read_u32(data_ptr + 8)
                qty = self._read_u32(data_ptr + 12)
                name = self.lookup_item_name(res_id)
                
                # Format for display: Quantity only if > 0
                display_qty = str(qty) if qty > 0 else ""
                
                items.append({
                    "name": name,
                    "qty": qty,
                    "display_qty": display_qty
                })
            curr = self._read_u32(curr + 8)
        
        return items

if __name__ == "__main__":
    import pymem
    import win32process
    import win32gui
    
    hwnd = win32gui.FindWindow(None, "Meridian 59")
    if hwnd:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        pm = pymem.Pymem(pid)
        scraper = InventoryScraper(pm)
        items = scraper.scan_inventory()
        for i in items:
            q = f" ({i['qty']})" if i['qty'] > 0 else ""
            print(f"- {i['name']}{q}")
    else:
        print("Game not found.")
