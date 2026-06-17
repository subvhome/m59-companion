import frida
import sys
import time
import json
import os

# --- Meridian 59 Inventory Weight/Bulk Calculator ---

def load_config():
    # Load items.json from the same directory as the script
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

const GET_PLAYER_INFO_ADDR = Module.findExportByName(null, "GetPlayerInfo");
const LOOKUP_RSC_ADDR = Module.findExportByName(null, "LookupNameRsc");

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
                        name: name,
                        amount: isQuantity ? amount : 1
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

def calculate_totals(items):
    total_weight = 0
    total_bulk = 0
    unknown_items = []
    
    item_db = CONFIG.get("items", {})
    defaults = CONFIG.get("settings", {"default_weight": 10, "default_bulk": 10})
    
    for item in items:
        name = item['name'].lower()
        amount = item['amount']
        
        # Check for direct match or partial match in our JSON database
        found_data = None
        if name in item_db:
            found_data = item_db[name]
        else:
            for key, data in item_db.items():
                if key in name:
                    found_data = data
                    break
        
        if found_data:
            w = found_data.get("weight", defaults["default_weight"])
            b = found_data.get("bulk", defaults["default_bulk"])
        else:
            if name != "unknown":
                unknown_items.append(name)
            w = defaults["default_weight"]
            b = defaults["default_bulk"]
            
        total_weight += (w * amount)
        total_bulk += (b * amount)
        
    return total_weight, total_bulk, unknown_items

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
        print(f"[+] Calculated Max Capacity: {max_cap}")
        print("[+] Monitoring inventory load. Press Ctrl+C to stop.\n")
        
        while True:
            try:
                result = script.exports_sync.getinventory()
                if 'error' in result:
                    print(f"[-] {result['error']}")
                else:
                    items = result['items']
                    weight, bulk, unknowns = calculate_totals(items)
                    
                    w_perc = (weight / max_cap) * 100
                    b_perc = (bulk / max_cap) * 100
                    
                    print(f"--- Inventory Load ---")
                    print(f"  Weight: {weight:>6} / {max_cap} ({w_perc:5.1f}%)")
                    print(f"  Bulk:   {bulk:>6} / {max_cap} ({b_perc:5.1f}%)")
                    
                    if unknowns:
                        unique_unknowns = list(set(unknowns))
                        print(f"  Note: Unmapped items: {', '.join(unique_unknowns[:3])}...")
                    
                    print(f"  (Total Items: {len(items)})")
                    print("-" * 25)
            except Exception as e:
                print(f"[-] RPC Error: {e}")
            
            time.sleep(5)
            
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    main()
