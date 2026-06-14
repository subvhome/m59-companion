import frida
import sys
import time
import json
import os

# --- Meridian 59 Unified Inventory Manager ---
# Combines item listing and weight/bulk calculation.

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] Error loading items.json: {e}")
        return None

CONFIG = load_config()

JS_CODE = """
const log = (msg) => send({type: 'log', data: msg});

const GET_PLAYER_INFO_ADDR = ptr("0x643a10");
const LOOKUP_RSC_ADDR = ptr("0x617cd0");

var getPlayerInfo = new NativeFunction(GET_PLAYER_INFO_ADDR, 'pointer', []);
var lookupRsc = new NativeFunction(LOOKUP_RSC_ADDR, 'pointer', ['uint32']);

rpc.exports = {
    getinventory: function() {
        try {
            var playerPtr = getPlayerInfo();
            if (playerPtr.isNull()) return {error: "Player pointer is null"};

            var inventoryListPtr = playerPtr.add(68).readPointer();
            if (inventoryListPtr.isNull()) return {items: []};

            var items = [];
            var currNode = inventoryListPtr;
            var safety = 0;
            
            while (!currNode.isNull() && safety < 500) {
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
    item_db = CONFIG.get("items", {})
    defaults = CONFIG.get("settings", {"default_weight": 10, "default_bulk": 10})
    
    total_weight = 0
    total_bulk = 0
    detailed_items = []
    unknowns = []

    for item in items:
        name = item['name']
        name_lower = name.lower()
        qty = item['amount']
        
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
            "id": item['id'],
            "name": name,
            "qty": qty,
            "weight": w * qty,
            "bulk": b * qty
        })
        
    # Sort alphabetically
    detailed_items.sort(key=lambda x: x['name'])
    
    return total_weight, total_bulk, detailed_items, list(set(unknowns))

def main():
    if not CONFIG:
        return

    try:
        session = frida.attach("meridian.exe")
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
