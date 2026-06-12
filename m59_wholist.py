import threading
import logging
import time

# --- Meridian 59 Improved Wholist Engine (ASLR-Safe) ---
# Based on wholist-perfect.py (Direct Memory Polling with Relative Offsets)

FRIDA_JS_CODE = """
const log = (msg) => send({type: 'log', data: msg});

function start() {
    var meridian = Process.findModuleByName("meridian.exe") || Process.findModuleByName("Meridian.exe");
    if (!meridian) {
        log("ERROR: Target module 'meridian.exe' not found.");
        return;
    }

    // ASLR-Safe Offset: current_users pointer is at this distance from module base
    var offset = 0x2A89A0; 
    var currentUsersPtrAddr = meridian.base.add(offset);
    
    var LookupRscAddr = null;
    var exps = meridian.enumerateExports();
    for (var i = 0; i < exps.length; i++) {
        if (exps[i].name === "LookupRsc") LookupRscAddr = exps[i].address;
    }

    if (!LookupRscAddr) {
        log("ERROR: LookupRsc export not found.");
    }

    rpc.exports = {
        getlist: function() {
            if (!LookupRscAddr) return [];
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
                            // PF_KILLER  = 0x4000
                            // PF_OUTLAW  = 0x8000
                            // PF_CREATOR = 0x10000
                            var flags = objPtr.add(20).readU32();
                            var status = "WHITE";
                            
                            if (flags & 0x4000) status = "RED";
                            else if (flags & 0x8000) status = "ORANGE";
                            else if (flags & 0xC000) status = "BLUE";
                            else if (flags & 0x10000 || name === "Zaphod") status = "YELLOW"; 

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
    log("Discovery Complete. ASLR-safe monitoring active.");
}

start();
"""

logger = logging.getLogger("m59.wholist")

class WhoListMonitor:
    def __init__(self, target_pid, on_update_callback):
        self.target_pid = target_pid
        self.on_update_callback = on_update_callback
        self.frida_session = None
        self.frida_script = None
        self.running = False
        self.players = {} # {name: status}

    def start(self):
        """Initializes the monitor in a background thread."""
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._run_frida, daemon=True).start()

    def stop(self):
        """Stops the monitor and detaches Frida."""
        self.running = False
        if self.frida_script:
            try: self.frida_script.unload()
            except: pass
        if self.frida_session:
            try: self.frida_session.detach()
            except: pass
        self.frida_script = None
        self.frida_session = None

    def _run_frida(self):
        try:
            import frida
            logger.info(f"WhoList: Attaching to PID {self.target_pid}...")
            session = frida.attach(self.target_pid)
            self.frida_session = session
            
            script = session.create_script(FRIDA_JS_CODE)
            self.frida_script = script
            
            def on_message(message, data):
                if message['type'] == 'send':
                    payload = message['payload']
                    if isinstance(payload, dict) and payload.get('type') == 'log':
                        logger.debug(f"FridaLog: {payload.get('data')}")
            
            script.on('message', on_message)
            script.load()
            logger.info("WhoList: ASLR-safe Memory Polling active.")

            # Polling Loop
            while self.running and self.frida_script:
                try:
                    current_data = script.exports_sync.getlist()
                    
                    # Map colors to Dashboard status tags
                    status_map = {
                        "WHITE": "INNOCENT",
                        "ORANGE": "OUTLAW",
                        "RED": "MURDERER",
                        "BLUE": "STAFF",
                        "YELLOW": "STAFF"
                    }
                    
                    new_players = {}
                    for p in current_data:
                        raw_status = p['status']
                        new_players[p['name']] = status_map.get(raw_status, "INNOCENT")

                    if new_players != self.players:
                        self.players = new_players
                        if self.on_update_callback:
                            self.on_update_callback(self.players)
                            
                except Exception as e:
                    logger.debug(f"WhoList: Polling error: {e}")
                
                time.sleep(2)
            
        except Exception as e:
            logger.error(f"WhoList: Frida Error: {e}")
            self.running = False

    def trigger_silent_update(self):
        """Manual update requested - polling is already active."""
        logger.debug("WhoList: Manual update requested (Polling is already active).")
