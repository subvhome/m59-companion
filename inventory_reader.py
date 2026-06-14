import frida
import sys
import time

# --- Meridian 59 Inventory Reader ---

JS_CODE = """
const log = (msg) => send({type: 'log', data: msg});

// Use absolute addresses found in diagnostic
const GET_PLAYER_INFO_ADDR = ptr("0x643a10");
const LOOKUP_RSC_ADDR = ptr("0x617cd0");

var getPlayerInfo = null;
var lookupRsc = null;

function init() {
    try {
        // Try without 'new' as a fallback for some environments
        getPlayerInfo = new NativeFunction(GET_PLAYER_INFO_ADDR, 'pointer', []);
        lookupRsc = new NativeFunction(LOOKUP_RSC_ADDR, 'pointer', ['uint32']);
        
        log("[+] Functions initialized with absolute addresses");
        return true;
    } catch (e) {
        log("[-] Initialization error: " + e.message);
        return false;
    }
}

rpc.exports = {
    getinventory: function() {
        if (!getPlayerInfo || !lookupRsc) {
            if (!init()) return {error: "Initialization failed"};
        }

        try {
            var playerPtr = getPlayerInfo();
            if (playerPtr.isNull()) return {error: "Player pointer is null"};

            // DEBUG: Dump first 80 bytes of player structure to see if offset 68 looks like a pointer
            // log("Player Struct Dump: " + hexdump(playerPtr, {length: 80}));

            // Offset 68 for inventory list pointer
            var inventoryListPtr = playerPtr.add(68).readPointer();
            if (inventoryListPtr.isNull()) return {items: [], msg: "Inventory pointer at 68 is null"};

            var items = [];
            var currNode = inventoryListPtr;
            var safety = 0;
            
            while (!currNode.isNull() && safety < 100) {
                var objPtr = currNode.readPointer(); 
                if (!objPtr.isNull()) {
                    var id = objPtr.readU32();
                    var nameResId = objPtr.add(8).readU32();
                    var amount = objPtr.add(12).readU32();
                    
                    var name = "Unknown";
                    if (nameResId !== 0) {
                        try {
                            var nameStrPtr = lookupRsc(nameResId);
                            if (!nameStrPtr.isNull()) {
                                name = nameStrPtr.readCString();
                            }
                        } catch(e) { name = "ErrorRsc"; }
                    }
                    
                    // Determine if this is a quantity object (high nibble is 1)
                    var isQuantity = (id & 0x10000000) !== 0;
                    var displayAmount = isQuantity ? amount : 1;
                    
                    items.push({
                        id: id,
                        name: name,
                        amount: displayAmount,
                        isQuantity: isQuantity
                    });
                }
                
                currNode = currNode.add(8).readPointer();
                safety++;
            }
            
            // Sort by name
            items.sort((a, b) => a.name.localeCompare(b.name));
            
            return {items: items};
        } catch (e) {
            return {error: "Exception: " + e.message};
        }
    }
};

log("[+] Inventory Reader Loaded");
"""

def on_message(message, data):
    if message['type'] == 'send':
        print(f"[*] {message['payload']['data']}")
    elif message['type'] == 'error':
        print(f"[-] Frida Error: {message['description']}")

def main():
    try:
        session = frida.attach("meridian.exe")
        script = session.create_script(JS_CODE)
        script.on('message', on_message)
        script.load()
        
        print("[+] Attached to meridian.exe. Press Ctrl+C to stop.")
        
        while True:
            try:
                result = script.exports_sync.getinventory()
                if 'error' in result:
                    print(f"[-] {result['error']}")
                else:
                    items = result['items']
                    if not items:
                        print("\n--- Inventory is empty ---")
                    else:
                        print(f"\n--- Inventory ({len(items)} items) ---")
                        for item in items:
                            print(f"  [{item['id']:08X}] {item['name']} (x{item['amount']})")
            except Exception as e:
                print(f"[-] RPC Error: {e}")
            
            time.sleep(5)
            
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    main()
