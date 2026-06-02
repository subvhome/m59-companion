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

    # 1. Load RID mapping from blakston.khd
    khd_path = os.path.join(base_path, "kod/include/blakston.khd")
    if os.path.exists(khd_path):
        with open(khd_path, 'r') as f:
            content = f.read()
            # Match RID_NAME = NUMBER
            matches = re.findall(r'(RID_[a-zA-Z0-9_]+)\s*=\s*(\d+)', content)
            for name, value in matches:
                rid_map[name.upper()] = int(value)
    
    # 2. Iterate through all .kod files
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

                        # Match RID (case-insensitive)
                        rid_match = re.search(r'piRoom_num\s*=\s*(RID_[a-zA-Z0-9_]+)', content, re.IGNORECASE)
                        rid_sym = rid_match.group(1).upper() if rid_match else None
                        if not rid_sym: continue

                        rid_num = rid_map.get(rid_sym)

                        # Resolve Room Name
                        vr_name_match = re.search(r'classvars:.*?vrName\s*=\s*([a-zA-Z0-9_]+)', content, re.DOTALL)
                        room_name = None
                        if vr_name_match:
                            res_id = vr_name_match.group(1)
                            res_match = re.search(rf'{res_id}\s*=\s*"([^"]+)"', content)
                            if res_match: room_name = res_match.group(1)
                        
                        if not room_name:
                            name_match = re.search(r'(?:room_name_[a-z0-9_]+|name_[a-zA-Z0-9_]+)\s*=\s*"([^"]+)"', content, re.IGNORECASE)
                            room_name = name_match.group(1) if name_match else class_name

                        # Teleport coords
                        tele_row_match = re.search(r'viTeleport_[Rr]ow\s*=\s*(\d+)', content)
                        tele_col_match = re.search(r'viTeleport_[Cc]ol\s*=\s*(\d+)', content)
                        tele_row = int(tele_row_match.group(1)) if tele_row_match else None
                        tele_col = int(tele_col_match.group(1)) if tele_col_match else None
                        
                        # .roo Grid Dimensions
                        roo_filename = file.replace(".kod", ".roo")
                        roo_path = os.path.join(roo_dir, roo_filename)
                        grid = extract_roo_grid(roo_path)
                        
                        exits = []
                        # Point Exits - more flexible regex
                        exit_matches = re.findall(r'plExits\s*=\s*Cons\(\s*\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(RID_[a-zA-Z0-9_]+)', content, re.IGNORECASE)
                        for row, col, dest_rid in exit_matches:
                            # Try to find target row/col in the remainder of the Cons call
                            # (Regex only captures up to RID for simplicity/robustness)
                            exits.append({"type": "point", "from": [int(row), int(col)], "to_rid": dest_rid.upper(), "to_pos": [None, None]})

                        # Edge Exits
                        edge_matches = re.findall(r'plEdge_Exits\s*=\s*Cons\(\s*\[\s*(LEAVE_[A-Z]+)\s*,\s*(RID_[a-zA-Z0-9_]+)', content, re.IGNORECASE)
                        for direction, dest_rid in edge_matches:
                            exits.append({"type": "edge", "direction": direction.upper(), "to_rid": dest_rid.upper(), "to_pos": [None, None]})

                        # Manual / Special Exits (e.g. SomethingMoved, SomethingTryGo)
                        # Look for RID_ references in messages
                        body_matches = re.finditer(r'RID_[a-zA-Z0-9_]+', content, re.IGNORECASE)
                        for m in body_matches:
                            dest_rid = m.group(0).upper()
                            if dest_rid == rid_sym: continue
                            if not any(e['to_rid'] == dest_rid for e in exits):
                                # Check if it's likely an exit trigger
                                context = content[max(0, m.start()-100):min(len(content), m.end()+100)]
                                if any(kw in context.lower() for kw in ["found", "findroom", "gonear", "move", "teleport", "exit", "destination"]):
                                    exits.append({"type": "manual", "to_rid": dest_rid, "to_pos": [None, None]})

                        if not exits: continue

                        rooms[rid_sym] = {
                            "name": room_name,
                            "rid_num": rid_num,
                            "file": os.path.relpath(file_path, base_path),
                            "grid": grid or [64, 64],
                            "teleport": [tele_row, tele_col],
                            "exits": exits
                        }
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

    return rooms

if __name__ == "__main__":
    base = "prev-code/Meridian59-1.6.0"
    data = extract_room_data(base)
    with open("meridian_rooms_dataset.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Extracted {len(data)} rooms to meridian_rooms_dataset.json")
