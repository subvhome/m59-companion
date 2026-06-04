import os
import re
import json
import struct

def extract_roo_grid(roo_path):
    """Extracts [width, height] from a .roo file's server grid."""
    try:
        with open(roo_path, 'rb') as f:
            magic = f.read(4)
            if magic != b'ROO\xb1': return None
            f.seek(16) # Skip main_pos
            server_pos = struct.unpack('<I', f.read(4))[0]
            f.seek(server_pos)
            rows = struct.unpack('<I', f.read(4))[0]
            cols = struct.unpack('<I', f.read(4))[0]
            return [cols, rows]
    except:
        return None

def extract_room_data(base_path):
    rid_map = {}
    rooms = {}
    
    roo_dir = os.path.join(base_path, "resource/rooms")

    # 1. Load RID mapping
    khd_path = os.path.join(base_path, "kod/include/blakston.khd")
    if os.path.exists(khd_path):
        with open(khd_path, 'r') as f:
            content = f.read()
            matches = re.findall(r'(RID_[a-zA-Z0-9_]+)\s*=\s*(\d+)', content)
            for name, value in matches:
                rid_map[name.upper()] = int(value)
    
    # 2. Pass 1: Extraction
    room_dir = os.path.join(base_path, "kod/object/active/holder/room")
    for root, dirs, files in os.walk(room_dir):
        for file in files:
            if file.endswith(".kod"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', errors='ignore') as f:
                        content = f.read()
                        
                        class_match = re.search(r'^([a-zA-Z0-9]+)\s+is\s+', content, re.MULTILINE)
                        if not class_match: continue
                        class_name = class_match.group(1)

                        rid_match = re.search(r'piRoom_num\s*=\s*(RID_[a-zA-Z0-9_]+)', content, re.IGNORECASE)
                        rid_sym = rid_match.group(1).upper() if rid_match else None
                        if not rid_sym: continue

                        rid_num = rid_map.get(rid_sym)

                        # Resolve Name
                        vr_name_match = re.search(r'classvars:.*?vrName\s*=\s*([a-zA-Z0-9_]+)', content, re.DOTALL)
                        room_name = None
                        if vr_name_match:
                            res_id = vr_name_match.group(1)
                            res_match = re.search(rf'{res_id}\s*=\s*"([^"]+)"', content)
                            if res_match: room_name = res_match.group(1)
                        if not room_name:
                            name_match = re.search(r'(?:room_name_[a-z0-9_]+|name_[a-zA-Z0-9_]+)\s*=\s*"([^"]+)"', content, re.IGNORECASE)
                            room_name = name_match.group(1) if name_match else class_name

                        # Grid
                        roo_filename = file.replace(".kod", ".roo")
                        roo_path = os.path.join(roo_dir, roo_filename)
                        grid = extract_roo_grid(roo_path)
                        
                        # Default Teleport (Arrival point)
                        tele_row_match = re.search(r'viTeleport_[Rr]ow\s*=\s*(\d+)', content)
                        tele_col_match = re.search(r'viTeleport_[Cc]ol\s*=\s*(\d+)', content)
                        teleport = [int(tele_row_match.group(1)) if tele_row_match else 32, 
                                    int(tele_col_match.group(1)) if tele_col_match else 32]

                        exits = []
                        # Point Exits: [src_row, src_col, target_rid, dest_row, dest_col]
                        # Use finditer + DOTALL to capture multi-line definitions
                        point_matches = re.finditer(r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(RID_[a-zA-Z0-9_]+)\s*,\s*(\d+)\s*,\s*(\d+)', content, re.IGNORECASE | re.DOTALL)
                        for m in point_matches:
                            r1, c1, drid, r2, c2 = m.groups()
                            exits.append({
                                "type": "point",
                                "from": [int(r1), int(c1)],
                                "to_rid": drid.upper(),
                                "to_pos": [int(r2), int(c2)]
                            })

                        # Edge Exits: [LEAVE_DIR, target_rid, dest_row, dest_col]
                        edge_matches = re.finditer(r'\[\s*(LEAVE_[A-Z]+)\s*,\s*(RID_[a-zA-Z0-9_]+)\s*,\s*(\d+)\s*,\s*(\d+)', content, re.IGNORECASE | re.DOTALL)
                        for m in edge_matches:
                            direct, drid, r2, c2 = m.groups()
                            exits.append({
                                "type": "edge",
                                "direction": direct.upper(),
                                "to_rid": drid.upper(),
                                "to_pos": [int(r2), int(c2)],
                                "from": None # To be filled in Pass 2
                            })

                        # Manual / Special Exits (e.g. SomethingMoved, SpiderTree)
                        # 1. Parse coordinate-based if blocks
                        if_blocks = re.finditer(r'if\s*\((.*?)\)\s*\{(.*?)\}', content, re.DOTALL | re.IGNORECASE)
                        for m in if_blocks:
                            condition, body = m.groups()
                            if "FindRoomByNum" in body or "UtilGoNearSquare" in body:
                                rids = re.findall(r'RID_[A-Z0-9_]+', body, re.IGNORECASE)
                                for dest_rid in rids:
                                    dest_rid = dest_rid.upper()
                                    if dest_rid == rid_sym: continue
                                    
                                    # Extract trigger coords
                                    row_m = re.search(r'(?:new_row|row)\s*[=><]+\s*(\d+)', condition, re.IGNORECASE)
                                    col_m = re.search(r'(?:new_col|col)\s*[=><]+\s*(\d+)', condition, re.IGNORECASE)
                                    row = int(row_m.group(1)) if row_m else None
                                    col = int(col_m.group(1)) if col_m else None
                                    
                                    # Extract arrival coords
                                    ar_row_m = re.search(r'#new_row\s*=\s*(\d+)', body, re.IGNORECASE)
                                    ar_col_m = re.search(r'#new_col\s*=\s*(\d+)', body, re.IGNORECASE)
                                    ar_row = int(ar_row_m.group(1)) if ar_row_m else None
                                    ar_col = int(ar_col_m.group(1)) if ar_col_m else None

                                    if not any(e['to_rid'] == dest_rid and e.get('from') == [row, col] for e in exits):
                                        exits.append({
                                            "type": "point" if row and col else "manual",
                                            "from": [row, col],
                                            "to_rid": dest_rid,
                                            "to_pos": [ar_row, ar_col]
                                        })

                        # 2. SpiderTree detection (H7 -> Nest)
                        if "SpiderTree" in content:
                            # Search for creation coordinates
                            # Send(self,@NewHold,#what=Create(&SpiderTree),#new_row=45,#new_col=8);
                            tree_matches = re.finditer(r'Create\(&SpiderTree\).*?#new_row\s*=\s*(\d+)\s*,#new_col\s*=\s*(\d+)', content, re.DOTALL | re.IGNORECASE)
                            for m in tree_matches:
                                r1, c1 = m.groups()
                                exits.append({
                                    "type": "point",
                                    "from": [int(r1), int(c1)],
                                    "to_rid": "RID_NEST1",
                                    "to_pos": [4, 17],
                                    "object": "SpiderTree"
                                })
                        rooms[rid_sym] = {
                            "name": room_name,
                            "grid": grid or [64, 64],
                            "teleport": teleport,
                            "exits": exits
                        }
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

    # 3. Pass 2: Neighbor Sync (Link edge exits to the physical arrival point in Room B)
    for rid, info in rooms.items():
        for exit_info in info['exits']:
            if exit_info['type'] == 'edge' and exit_info['from'] is None:
                target_rid = exit_info['to_rid']
                if target_rid in rooms:
                    # Search target room for any transition leading BACK to this room
                    for return_exit in rooms[target_rid]['exits']:
                        if return_exit['to_rid'] == rid and return_exit.get('to_pos'):
                            # The coordinate where you arrive in Room B is the "Road Point" in Room A
                            exit_info['from'] = return_exit['to_pos']
                            break
                    
                    # Fallback to map center of the appropriate wall if no back-link exists
                    if exit_info['from'] is None:
                        w, h = info['grid']
                        if "NORTH" in exit_info.get('direction', ""): exit_info['from'] = [1, w//2]
                        elif "SOUTH" in exit_info.get('direction', ""): exit_info['from'] = [h-1, w//2]
                        elif "WEST" in exit_info.get('direction', ""): exit_info['from'] = [h//2, 1]
                        elif "EAST" in exit_info.get('direction', ""): exit_info['from'] = [h//2, w-1]

    return rooms

if __name__ == "__main__":
    base = "prev-code/Meridian59-1.6.0"
    data = extract_room_data(base)
    with open("meridian_rooms_dataset.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Extracted {len(data)} rooms with Advanced Neighbor Sync to meridian_rooms_dataset.json")
