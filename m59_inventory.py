import os
import sys
import re
import json
import time
import struct
import ctypes
import ctypes.wintypes
import logging
from m59_utils import resource_path

# --- Meridian 59 Unified Inventory Manager ---
# Combines live memory scraping (Pymem-style direct memory read & Frida instrumentation) 
# and weight/bulk calculation logic.

logger = logging.getLogger("m59.inventory")

def load_config():
    config_path = resource_path("settings/items.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] Error loading items.json: {e}")
        return None

CONFIG = load_config()

# --- Frida Instrumentation Standalone Logic ---
JS_CODE = """
const log = (msg) => send({type: 'log', data: msg});

const GET_PLAYER_INFO_ADDR = Module.findExportByName(null, "GetPlayerInfo");
const LOOKUP_RSC_ADDR = Module.findExportByName(null, "LookupNameRsc");

var getPlayerInfo = new NativeFunction(GET_PLAYER_INFO_ADDR, 'pointer', []);
var lookupRsc = new NativeFunction(LOOKUP_RSC_ADDR, 'pointer', ['uint32']);

var bestOffset = null;
const INVENTORY_KEYWORDS = [
    "robe", "shirt", "scroll", "potion", "sword", "shield", "shilling", 
    "gem", "emerald", "ruby", "sapphire", "diamond", "mushroom", "wand", 
    "leather", "plate", "scale", "armor", "fife", "reagent", "herb", 
    "tooth", "pie", "meat", "bread", "apple", "scimitar", "dagger", "hammer"
];

function findInventoryOffset(playerPtr) {
    var best_offset = 68;
    var best_score = -1000;
    
    for (var offset = 0; offset <= 1024; offset += 4) {
        try {
            var listHeadPtr = playerPtr.add(offset).readPointer();
            if (listHeadPtr.isNull()) continue;
            
            var currNode = listHeadPtr;
            var visited = {};
            var safety = 0;
            var isValid = true;
            var score = 0;
            var count = 0;
            
            while (!currNode.isNull() && safety < 100) {
                var nodeAddrStr = currNode.toString();
                if (visited[nodeAddrStr]) break;
                visited[nodeAddrStr] = true;
                
                var objPtr = currNode.readPointer();
                if (objPtr.isNull()) {
                    isValid = false;
                    break;
                }
                
                var id = objPtr.readU32();
                var nameResId = objPtr.add(8).readU32();
                var amount = objPtr.add(12).readU32();
                
                if (nameResId > 0 && nameResId < 150000) {
                    var nameStrPtr = lookupRsc(nameResId);
                    if (!nameStrPtr.isNull()) {
                        var name = nameStrPtr.readCString();
                        if (name && name.length >= 2 && name.length <= 64 && /^[A-Za-z0-9'\\\\- ]+$/.test(name)) {
                            count++;
                            var lowerName = name.toLowerCase();
                            if (lowerName === "sun" || lowerName === "moon") {
                                score -= 150;
                            } else {
                                score += 10;
                                for (var k = 0; k < INVENTORY_KEYWORDS.length; k++) {
                                    if (lowerName.indexOf(INVENTORY_KEYWORDS[k]) !== -1) {
                                        score += 50;
                                        break;
                                    }
                                }
                            }
                        } else {
                            isValid = false;
                            break;
                        }
                    } else {
                        isValid = false;
                        break;
                    }
                } else {
                    isValid = false;
                    break;
                }
                
                currNode = currNode.add(8).readPointer();
                safety++;
            }
            
            if (isValid && count > 0) {
                if (score > best_score) {
                    best_score = score;
                    best_offset = offset;
                }
            }
        } catch (e) {}
    }
    return best_offset;
}

rpc.exports = {
    getinventory: function() {
        try {
            var playerPtr = getPlayerInfo();
            if (playerPtr.isNull()) return {error: "Player pointer is null"};

            if (bestOffset === null) {
                bestOffset = findInventoryOffset(playerPtr);
            }

            var inventoryListPtr = playerPtr.add(bestOffset).readPointer();
            if (inventoryListPtr.isNull()) return {items: []};

            var items = [];
            var currNode = inventoryListPtr;
            var safety = 0;
            var visited = {};
            
            while (!currNode.isNull() && safety < 500) {
                var nodeAddrStr = currNode.toString();
                if (visited[nodeAddrStr]) break;
                visited[nodeAddrStr] = true;

                var objPtr = currNode.readPointer(); 
                if (!objPtr.isNull()) {
                    var id = objPtr.readU32();
                    var nameResId = objPtr.add(8).readU32();
                    var amount = objPtr.add(12).readU32();
                    
                    var name = "Unknown";
                    if (nameResId !== 0) {
                        var nameStrPtr = lookupRsc(nameResId);
                        if (!nameStrPtr.isNull()) {
                            name = nameStrPtr.readCString();
                        }
                    }
                    
                    var isQuantity = (id & 0x10000000) !== 0;
                    items.push({
                        id: id.toString(16).toUpperCase(),
                        name: name,
                        amount: isQuantity ? amount : 1,
                        isQuantity: isQuantity
                    });
                }
                currNode = currNode.add(8).readPointer();
                safety++;
            }
            return {items: items};
        } catch (e) {
            return {error: e.message};
        }
    }
};
"""

def on_message(message, data):
    if message['type'] == 'send':
        print(f"[*] {message['payload']['data']}")

def process_inventory(items):
    """Calculates cumulative weight, bulk, lists items, and returns unmapped/unknown items."""
    item_db = {}
    defaults = {"default_weight": 10, "default_bulk": 10}
    if CONFIG:
        item_db = CONFIG.get("items", {})
        defaults = CONFIG.get("settings", {"default_weight": 10, "default_bulk": 10})
    
    total_weight = 0
    total_bulk = 0
    detailed_items = []
    unknowns = []

    for item in items:
        name = item.get('name', 'Unknown')
        name_lower = name.lower()
        qty = item.get('amount', item.get('qty', 1))
        if qty == 0:
            qty = 1 # Safe fallback for items with quantity 0 (representing single items)
        
        # Determine weight/bulk for this item
        item_data = None
        if name_lower in item_db:
            item_data = item_db[name_lower]
        else:
            # Try partial match
            for key, data in item_db.items():
                if key in name_lower:
                    item_data = data
                    break
        
        if item_data:
            w = item_data.get("weight", defaults["default_weight"])
            b = item_data.get("bulk", defaults["default_bulk"])
        else:
            if name_lower != "unknown":
                unknowns.append(name)
            w = defaults["default_weight"]
            b = defaults["default_bulk"]
            
        # Add to totals
        total_weight += (w * qty)
        total_bulk += (b * qty)
        
        # Add to detailed list for display
        detailed_items.append({
            "id": item.get('id', '0'),
            "name": name,
            "qty": qty,
            "weight": w * qty,
            "bulk": b * qty
        })
        
    # Sort alphabetically
    detailed_items.sort(key=lambda x: x['name'])
    
    return total_weight, total_bulk, detailed_items, list(set(unknowns))

# --- Direct Windows API Memory-Scraping Logic (used by GUI Dashboard) ---
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
        """Calibrates addresses via game exports and dynamically scans for the inventory list offset."""
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
        
        self.inventory_offset = 68  # default fallback
        if self.player_addr and self.table_ptr_addr:
            logger.info(f"Inventory Scraper Calibrated: Player={hex(self.player_addr)}, Table={hex(self.table_ptr_addr)}")
            
            # Dynamically scan player structure (offsets 0 to 1024) to locate real inventory list
            INVENTORY_KEYWORDS = [
                "robe", "shirt", "scroll", "potion", "sword", "shield", "shilling", 
                "gem", "emerald", "ruby", "sapphire", "diamond", "mushroom", "wand", 
                "leather", "plate", "scale", "armor", "fife", "reagent", "herb", 
                "tooth", "pie", "meat", "bread", "apple", "scimitar", "dagger", "hammer"
            ]
            
            best_offset = None
            best_score = -1000
            
            for offset in range(0, 1025, 4):
                try:
                    list_head = self._read_u32(self.player_addr + offset)
                    if not list_head:
                        continue
                        
                    curr = list_head
                    visited = set()
                    safety = 0
                    is_valid = True
                    score = 0
                    items_count = 0
                    
                    while curr and curr not in visited and safety < 200:
                        visited.add(curr)
                        data_ptr = self._read_u32(curr)
                        if not data_ptr:
                            is_valid = False
                            break
                            
                        res_id = self._read_u32(data_ptr + 8)
                        qty = self._read_u32(data_ptr + 12)
                        
                        if 0 < res_id < 150000:
                            name = self.lookup_item_name(res_id)
                            # Basic sanitization
                            if name and len(name) >= 2 and len(name) <= 64 and re.match(r"^[A-Za-z0-9'\- ]+$", name):
                                items_count += 1
                                name_lower = name.toLowerCase() if hasattr(name, 'toLowerCase') else name.lower()
                                if name_lower in ["sun", "moon"]:
                                    score -= 150
                                else:
                                    score += 10
                                    for kw in INVENTORY_KEYWORDS:
                                        if kw in name_lower:
                                            score += 50
                                            break
                            else:
                                is_valid = False
                                break
                        else:
                            is_valid = False
                            break
                            
                        curr = self._read_u32(curr + 8)
                        safety += 1
                        
                    if is_valid and items_count > 0:
                        if score > best_score:
                            best_score = score
                            best_offset = offset
                except Exception:
                    pass
                    
            if best_offset is not None:
                self.inventory_offset = best_offset
                logger.info(f"Dynamic scan identified active player inventory offset: {best_offset} (0x{best_offset:02X}) with score: {best_score}")
            else:
                logger.warning("Dynamic scan did not find a strong candidate list. Using default offset fallback 68")
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
        """Calculates total weight capacity based on Might."""
        try:
            return 1700 + (int(might) * 20)
        except (ValueError, TypeError):
            return 1700

    def scan_inventory(self):
        """Traverses the inventory linked list in the target process."""
        if not self.player_addr: self.calibrate()
        if not self.player_addr: return []

        inventory_head = self._read_u32(self.player_addr + self.inventory_offset)
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

def main():
    """Standalone mode: Runs Frida instrumentation of the inventory list."""
    import frida
    if not CONFIG:
        print("[-] items.json config is required for calculations.")
        return

    try:
        import json
        exe_name = "meridian.exe"
        try:
            with open(config_path, "r") as f:
                c = json.load(f)
                exe_name = c.get("process", {}).get("target_name", "meridian.exe")
        except: pass
        session = frida.attach(exe_name)
        script = session.create_script(JS_CODE)
        script.on('message', on_message)
        script.load()
        
        char = CONFIG["character"]
        max_cap = char["base_capacity"] + (char["might"] * char["might_factor"])
        
        print(f"[+] Character Might: {char['might']}")
        print(f"[+] Max Capacity: {max_cap}")
        print("[+] Unified Inventory Manager Active. Press Ctrl+C to stop.\n")
        
        while True:
            try:
                result = script.exports_sync.getinventory()
                if 'error' in result:
                    print(f"[-] {result['error']}")
                else:
                    items = result['items']
                    weight, bulk, detailed, unknowns = process_inventory(items)
                    
                    # 1. Print Capacity Summary
                    w_perc = (weight / max_cap) * 100
                    b_perc = (bulk / max_cap) * 100
                    
                    print("=" * 45)
                    print(f" CAPACITY STATUS")
                    print(f" Weight: {weight:>6} / {max_cap} [{w_perc:5.1f}%]")
                    print(f" Bulk:   {bulk:>6} / {max_cap} [{b_perc:5.1f}%]")
                    print("-" * 45)
                    
                    # 2. Print Detailed Item List
                    print(f" ITEMS ({len(detailed)})")
                    for item in detailed:
                        qty_str = f"x{item['qty']}" if item['qty'] > 1 or item['qty'] == 0 else "  "
                        print(f" [{item['id']:>8}] {item['name'][:25]:<25} {qty_str:>5} (W:{item['weight']:>3}, B:{item['bulk']:>3})")
                    
                    if unknowns:
                        print(f"\n [!] Unmapped: {', '.join(unknowns[:5])}")
                    
                    print("=" * 45 + "\n")
                    
            except Exception as e:
                print(f"[-] RPC Error: {e}")
            
            time.sleep(10)
            
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    main()
