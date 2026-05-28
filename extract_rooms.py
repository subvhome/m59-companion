import os
import re
import json

def extract_room_data(base_path):
    rid_map = {}
    rooms = {}

    # 1. Load RID mapping from blakston.khd
    khd_path = os.path.join(base_path, "kod/include/blakston.khd")
    if os.path.exists(khd_path):
        with open(khd_path, 'r') as f:
            content = f.read()
            # Match RID_NAME = NUMBER
            matches = re.findall(r'(RID_[A-Z0-9_]+)\s*=\s*(\d+)', content)
            for name, value in matches:
                rid_map[name] = int(value)
    
    # 2. Iterate through all .kod files in the room directory
    room_dir = os.path.join(base_path, "kod/object/active/holder/room")
    for root, dirs, files in os.walk(room_dir):
        for file in files:
            if file.endswith(".kod"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', errors='ignore') as f:
                        content = f.read()

                        # Extract class name (e.g., Tos is TosRoom)
                        class_match = re.search(r'^([a-zA-Z0-9]+)\s+is\s+', content, re.MULTILINE)
                        if not class_match:
                            continue
                        class_name = class_match.group(1)

                        # 1. Extract RID from piRoom_num (Essential for real rooms)
                        rid_match = re.search(r'piRoom_num\s*=\s*(RID_[A-Z0-9_]+)', content)
                        rid_sym = rid_match.group(1) if rid_match else None
                        
                        # Filter out non-rooms (base classes/templates)
                        if not rid_sym:
                            continue

                        rid_num = rid_map.get(rid_sym) if rid_sym else None

                        # 2. Robust Name Extraction
                        # A. Look for vrName in classvars
                        vr_name_match = re.search(r'classvars:.*?vrName\s*=\s*([a-zA-Z0-9_]+)', content, re.DOTALL)
                        room_name = None
                        if vr_name_match:
                            res_id = vr_name_match.group(1)
                            # B. Resolve resource identifier
                            res_match = re.search(rf'{res_id}\s*=\s*"([^"]+)"', content)
                            if res_match:
                                room_name = res_match.group(1)
                        
                        # C. Fallback to existing logic if vrName resolution failed
                        if not room_name:
                            name_match = re.search(r'(?:room_name_[a-z0-9_]+|name_[a-zA-Z0-9_]+)\s*=\s*"([^"]+)"', content)
                            room_name = name_match.group(1) if name_match else class_name

                        # Extract Teleport coordinates
                        tele_row_match = re.search(r'viTeleport_[Rr]ow\s*=\s*(\d+)', content)
                        tele_col_match = re.search(r'viTeleport_[Cc]ol\s*=\s*(\d+)', content)
                        tele_row = int(tele_row_match.group(1)) if tele_row_match else None
                        tele_col = int(tele_col_match.group(1)) if tele_col_match else None
                        
                        exits = []
                        
                        # 3. Standard Exit Extraction
                        # Extract plExits (Standard Point Exits)
                        exit_matches = re.findall(r'plExits\s*=\s*Cons\(\s*\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(RID_[A-Z0-9_]+)\s*,\s*(\d+)\s*,\s*(\d+)', content)
                        for row, col, dest_rid, d_row, d_col in exit_matches:
                            exits.append({
                                "type": "point",
                                "from": [int(row), int(col)],
                                "to_rid": dest_rid,
                                "to_pos": [int(d_row), int(d_col)]
                            })

                        # Extract plEdge_Exits
                        edge_matches = re.findall(r'plEdge_Exits\s*=\s*Cons\(\s*\[\s*(LEAVE_[A-Z]+)\s*,\s*(RID_[A-Z0-9_]+)\s*,\s*(\d+)\s*,\s*(\d+)', content)
                        for direction, dest_rid, d_row, d_col in edge_matches:
                            exits.append({
                                "type": "edge",
                                "direction": direction,
                                "to_rid": dest_rid,
                                "to_pos": [int(d_row), int(d_col)]
                            })

                        # 4. Manual Exit Extraction (e.g. SomethingMoved logic)
                        # Look for RID_ assignments to variables or #where parameters
                        manual_matches = re.findall(r'(?:#where\s*=\s*Send\(SYS,@FindRoomByNum,#num=|(?:#where|where|dest_room)\s*=\s*|RID_DEST\s*=\s*)(RID_[A-Z0-9_]+)', content)
                        # Also look for the simpler FindRoomByNum pattern
                        manual_matches += re.findall(r'FindRoomByNum\(#num=(RID_[A-Z0-9_]+)\)', content)
                        
                        for dest_rid in set(manual_matches):
                            # Avoid duplicates if already found in plExits
                            if not any(e['to_rid'] == dest_rid for e in exits):
                                exits.append({
                                    "type": "manual",
                                    "to_rid": dest_rid,
                                    "to_pos": [None, None]
                                })

                        # Filter out rooms with 0 exits (Decommissioned/Ghost rooms)
                        if not exits:
                            continue

                        rooms[rid_sym] = {
                            "name": room_name,
                            "rid_num": rid_num,
                            "file": os.path.relpath(file_path, base_path),
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
