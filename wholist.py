import frida
import sys
import time

# --- Meridian 59 Final Live Wholist v10.0 ---
# Fixed PK Colors and Multiple Process Attachment.

JS_CODE = """
const log = (msg) => send({type: 'log', data: msg});

var currentUsersPtrAddr = ptr("0x8089a0");
var LookupRscAddr = null;

function start() {
    var meridian = Process.findModuleByName("meridian.exe") || Process.findModuleByName("Meridian.exe");
    if (!meridian) return;

    var exps = meridian.enumerateExports();
    for (var i = 0; i < exps.length; i++) {
        if (exps[i].name === "LookupRsc") LookupRscAddr = exps[i].address;
    }

    rpc.exports = {
        getlist: function() {
            if (!currentUsersPtrAddr || !LookupRscAddr) return [];
            try {
                var lookupRsc = new NativeFunction(LookupRscAddr, 'pointer', ['uint32']);
                var head = currentUsersPtrAddr.readPointer();
                if (head.isNull()) return [];

                var players = [];
                var currNode = head;
                var safety = 0;

                while (!currNode.isNull() && safety < 1000) {
                    var objPtr = currNode.readPointer(); 
                    if (!objPtr.isNull()) {
                        var nameResId = objPtr.add(8).readU32();
                        var nameStrPtr = lookupRsc(nameResId);
                        if (!nameStrPtr.isNull()) {
                            var name = nameStrPtr.readCString();
                            
                            // Protocol Flags (Fixed Bits)
                            // PF_KILLER  = 0x00004000 (RED)
                            // PF_OUTLAW  = 0x00008000 (ORANGE)
                            // PF_CREATOR = 0x00010000 (YELLOW)
                            var flags = objPtr.add(20).readU32();
                            var status = "WHITE";
                            
                            if (flags & 0x00004000) status = "RED";
                            else if (flags & 0x00008000) status = "ORANGE";
                            else if (flags & 0x00010000 || name === "Zaphod") status = "YELLOW"; 

                            if (name && name.length > 1) {
                                players.push({name: name, status: status});
                            }
                        }
                    }
                    currNode = currNode.add(8).readPointer();
                    safety++;
                }
                return players;
            } catch (e) { return []; }
        }
    };
    log("Discovery Complete. Monitoring " + meridian.name);
}

start();
"""

online_players = {}

def on_message(message, data):
    if message['type'] == 'send' and 'data' in message['payload']:
        print(f"[*] {message['payload']['data']}")

def main():
    print("==============================================")
    print("       Meridian 59 Live Population Feed")
    print("==============================================")
    
    try:
        device = frida.get_local_device()
        processes = [p for p in device.enumerate_processes() if p.name.lower() == "meridian.exe"]
        
        if not processes:
            print("[-] meridian.exe not found. Please start the game.")
            return

        # Use the most recent process if multiple are found
        target = processes[-1]
        if len(processes) > 1:
            print(f"[*] Multiple clients found. Attaching to PID {target.pid}...")
        
        session = frida.attach(target.pid)
        script = session.create_script(JS_CODE)
        script.on('message', on_message)
        script.load()
        
        global online_players
        print(f"[+] Attached to PID {target.pid}. Monitoring memory...")
        
        while True:
            try:
                current_data = script.exports_sync.getlist()
                current_map = {p['name']: p['status'] for p in current_data}
                
                if current_map != online_players:
                    new_names = set(current_map.keys())
                    old_names = set(online_players.keys())
                    added = new_names - old_names
                    removed = old_names - new_names
                    
                    if not online_players and current_map:
                        print(f"\n[!] CURRENT POPULATION ({len(current_map)} Online):")
                        for name in sorted(current_map.keys()):
                            print(f"  [{current_map[name]:<6}] - {name}")
                        print("-" * 40)
                    else:
                        for name in sorted(list(added)):
                            print(f"[+] LOGON : [{current_map[name]:<6}] {name}")
                        for name in sorted(list(removed)):
                            print(f"[-] LOGOFF: {name}")
                    
                    online_players = current_map
                
                time.sleep(2)
            except frida.InvalidOperationError:
                print("\n[*] Game closed. Exiting...")
                break
            except Exception:
                time.sleep(2)

    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    main()
