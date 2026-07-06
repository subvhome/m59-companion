import os
import struct
import sys
import glob
import shutil
import subprocess
import getpass

def detect_installation():
    """Detects Meridian 59 installation, returns (rooms_dir, map_file, is_running)."""
    # 1. Check if it's currently running
    try:
        output = subprocess.check_output('wmic process where name="meridian.exe" get executablepath', shell=True, text=True)
        lines = [line.strip() for line in output.split('\n') if line.strip() and "ExecutablePath" not in line]
        if lines:
            exe_path = lines[0]
            if "Steam" in exe_path:
                print("Detected Steam version running.")
                base_dir = os.path.dirname(exe_path)
                return os.path.join(base_dir, "resource"), os.path.join(base_dir, "mail", "game.map"), True
            else:
                print("Detected Webclient/Non-Steam version running.")
                local_app_data = os.environ.get('LOCALAPPDATA', f"C:\\Users\\{getpass.getuser()}\\AppData\\Local")
                base_dir = os.path.join(local_app_data, "Meridian 59")
                return os.path.join(base_dir, "resource"), os.path.join(base_dir, "mail", "game.map"), True
    except Exception:
        pass # wmic failed or not running

    # 2. Check common paths if not running
    local_app_data = os.environ.get('LOCALAPPDATA', f"C:\\Users\\{getpass.getuser()}\\AppData\\Local")
    non_steam_base = os.path.join(local_app_data, "Meridian 59")
    non_steam_map = os.path.join(non_steam_base, "mail", "game.map")
    
    steam_base = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Meridian 59"
    steam_map = os.path.join(steam_base, "mail", "game.map")
    
    if os.path.exists(non_steam_map) or os.path.exists(os.path.join(non_steam_base, "resource", "rooms")):
        print("Detected Webclient/Non-Steam installation (not running).")
        return os.path.join(non_steam_base, "resource", "rooms"), non_steam_map, False
    elif os.path.exists(steam_map) or os.path.exists(os.path.join(steam_base, "resource", "rooms")):
        print("Detected Steam installation (not running).")
        return os.path.join(steam_base, "resource", "rooms"), steam_map, False
        
    return None, None, False

def get_room_info(roo_path):
    try:
        with open(roo_path, 'rb') as f:
            # Offset 8 is room->security
            f.seek(8)
            sec = struct.unpack('<i', f.read(4))[0]
            
            # Offset 12 is 'temp', pointer to main info
            temp = struct.unpack('<I', f.read(4))[0]
            
            # Seek to main info
            f.seek(temp)
            # Skip width (4 bytes) and height (4 bytes)
            f.read(8)
            
            # Read pointers to nodes and walls
            node_pos = struct.unpack('<I', f.read(4))[0]
            wall_pos = struct.unpack('<I', f.read(4))[0]
            
            # Seek to walls section
            f.seek(wall_pos)
            # First 2 bytes of walls section is num_walls
            num_walls = struct.unpack('<H', f.read(2))[0]
            
            roo_name = os.path.splitext(os.path.basename(roo_path))[0].lower()
            return sec, num_walls, roo_name
    except Exception as e:
        print(f"Error reading {roo_path}: {e}")
        return None

def analyze_map(map_file, unique_rooms):
    if not os.path.exists(map_file):
        print(f"Map file '{map_file}' not found. 0% unlocked.")
        return 0.0

    try:
        with open(map_file, 'rb') as f:
            f.seek(8)
            top_table_data = f.read(400)
            if len(top_table_data) < 400:
                print("Existing map file is too small to analyze.")
                return 0.0
            
            top_table = struct.unpack('<100I', top_table_data)
            
            total_unlocked_walls = 0
            rooms_in_map = 0

            for top_offset in top_table:
                if top_offset == 0:
                    continue
                f.seek(top_offset)
                f.read(4) # next table
                lower_table_data = f.read(800)
                if len(lower_table_data) < 800:
                    continue
                
                lower_table = struct.unpack('<200i', lower_table_data)
                
                for i in range(100):
                    security = lower_table[i*2]
                    offset = lower_table[i*2+1]
                    
                    if security == 0 or offset <= 0:
                        continue
                        
                    f.seek(offset)
                    num_walls_data = f.read(4)
                    if len(num_walls_data) < 4:
                        continue
                    num_walls = struct.unpack('<I', num_walls_data)[0]
                    
                    if num_walls <= 0:
                        continue
                        
                    full_bytes = num_walls // 8
                    remainder = num_walls % 8
                    
                    wall_bytes = f.read(full_bytes + (1 if remainder > 0 else 0))
                    
                    # Count bits exactly up to num_walls
                    walls_processed = 0
                    for byte in wall_bytes:
                        for bit in range(8):
                            if walls_processed < num_walls:
                                if (byte & (1 << bit)) != 0:
                                    total_unlocked_walls += 1
                                walls_processed += 1
                                
                    rooms_in_map += 1
                    
        total_possible_walls = sum(walls for walls, _ in unique_rooms.values())
        if total_possible_walls == 0:
            print("No rooms to analyze.")
            return 0.0

        percent = (total_unlocked_walls / total_possible_walls) * 100
        print(f"\n--- Current Map Analysis ---")
        print(f"Rooms visited: {rooms_in_map} / {len(unique_rooms)}")
        print(f"Walls unlocked: {total_unlocked_walls} / {total_possible_walls}")
        print(f"Total Map Completion: {percent:.2f}%\n")
        return percent
        
    except Exception as e:
        print(f"Error analyzing existing map file: {e}\n")
        return 0.0

def generate_map(map_file, unique_rooms):
    # Load dataset
    import json
    dataset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings', 'meridian_rooms_dataset.json')
    room_annotations = {}
    if os.path.exists(dataset_path):
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # First pass: map RIDs to names
                room_names = {}
                for k, v in data.items():
                    room_names[k] = v.get("name", k)
                
                # Second pass: build annotations for exits
                for k, v in data.items():
                    r_name = v.get("roo_filename", k.replace("RID_", "").lower())
                    annotations = []
                    for ex in v.get("exits", []):
                        if ex.get("from") and ex.get("to_rid") and ex["from"][0] is not None and ex["from"][1] is not None:
                            target_name = room_names.get(ex["to_rid"], ex["to_rid"])
                            if target_name.startswith("RID_"):
                                target_name = target_name.replace("RID_", "").replace("_", " ").title()
                            
                            # Determine x and y in FINENESS units (grid coords * 1024 + 512)
                            # from[0] is row (Y), from[1] is col (X)
                            row, col = ex["from"]
                            x = int(col) * 1024 + 512
                            y = int(row) * 1024 + 512
                            
                            text = target_name
                            
                            # Deduplicate/cluster close exits to the same destination
                            is_duplicate = False
                            for existing in annotations:
                                if existing["text"] == text:
                                    # If within ~10 grid squares, consider it part of the same exit/edge
                                    dist_sq = (existing["x"] - x)**2 + (existing["y"] - y)**2
                                    if dist_sq < (10 * 1024)**2:
                                        is_duplicate = True
                                        break
                            
                            if not is_duplicate:
                                annotations.append({
                                    "text": text,
                                    "x": x,
                                    "y": y
                                })
                    room_annotations[r_name] = annotations[:20]
            print(f"Loaded exit annotations for {len(room_annotations)} rooms from dataset.")
        except Exception as e:
            print(f"Failed to load dataset: {e}")

    # Backup existing map
    if os.path.exists(map_file):
        backup_path = map_file + ".backup"
        if not os.path.exists(backup_path):
            try:
                shutil.copy2(map_file, backup_path)
                print(f"Backed up existing game.map to: {backup_path}")
            except Exception as e:
                print(f"Failed to create backup: {e}")

    # Ensure the directory for map_file exists
    os.makedirs(os.path.dirname(os.path.abspath(map_file)), exist_ok=True)

    # Group into 100 hash buckets
    buckets = [[] for _ in range(100)]
    for sec, (num_walls, roo_name) in unique_rooms.items():
        bucket_idx = abs(sec) % 100
        buckets[bucket_idx].append((sec, num_walls, roo_name))

    print(f"Generating fully unlocked map file at: {map_file}")
    
    try:
        with open(map_file, 'wb') as f:
            # Header Magic and Version
            f.write(struct.pack('<4B', 0x4D, 0x41, 0x50, 0x0F))
            f.write(struct.pack('<I', 2)) # MAPFILE_VERSION

            # Top table placeholder
            f.write(b'\x00' * 400)

            top_table_offsets = [0] * 100
            
            # Write lower tables
            for i in range(100):
                if not buckets[i]:
                    continue
                top_table_offsets[i] = f.tell()
                f.write(struct.pack('<I', 0)) # next_table
                f.write(b'\x00' * 800) # 100 entries placeholder
            
            end_of_lower_tables = f.tell()
            
            # Go back and write top table
            f.seek(8)
            f.write(struct.pack('<100I', *top_table_offsets))

            # Write actual room data
            f.seek(end_of_lower_tables)
            rooms_added = 0
            
            for i in range(100):
                if not buckets[i]:
                    continue
                
                lower_table_pos = top_table_offsets[i] + 4
                
                for j, (sec, num_walls, roo_name) in enumerate(buckets[i]):
                    if j >= 100:
                        print(f"Warning: Bucket {i} overflowed! Max 100 rooms.")
                        break
                        
                    room_offset = f.tell()
                    
                    # Update lower table
                    f.seek(lower_table_pos + j * 8)
                    f.write(struct.pack('<ii', sec, room_offset))
                    
                    # Write room data
                    f.seek(room_offset)
                    f.write(struct.pack('<I', num_walls))
                    
                    full_bytes = num_walls // 8
                    remainder = num_walls % 8
                    
                    # Set all bits to 1 to reveal the walls
                    wall_data = bytearray(b'\xff' * full_bytes)
                    if remainder > 0:
                        wall_data.append((1 << remainder) - 1)
                        
                    f.write(wall_data)
                    
                    # Handle annotations
                    annotation_data = room_annotations.get(roo_name)
                    if annotation_data:
                        # Offset where annotation block will start (immediately after this field)
                        annotations_offset = f.tell() + 4
                        f.write(struct.pack('<I', annotations_offset))
                        
                        f.write(struct.pack('<I', 20)) # num_annotations = MAX_ANNOTATIONS (20)
                        
                        for i in range(20):
                            if i < len(annotation_data):
                                anno = annotation_data[i]
                                text_bytes = anno["text"].encode('utf-8', 'ignore')[:99]
                                text_bytes += b'\x00' * (100 - len(text_bytes))
                                f.write(struct.pack('<ii', anno["x"], anno["y"]))
                                f.write(text_bytes)
                            else:
                                empty_anno = struct.pack('<ii', 0, 0) + (b'\x00' * 100)
                                f.write(empty_anno)
                    else:
                        # 0 annotations offset
                        f.write(struct.pack('<I', 0)) 
                    
                    rooms_added += 1

        print(f"\nSUCCESS! {rooms_added} rooms have been fully revealed.")
        print("Enjoy your completed map! Make sure to start the game now.")
        print("\nNOTE: If a room still appears locked when you enter it, it means your")
        print("local .roo file was out-of-date. When you entered the room, the game")
        print("downloaded the new version, which has a different security ID. To fix")
        print("this, simply run this generator again now that the room is updated!")
    except Exception as e:
        print(f"Error writing map file: {e}")

if __name__ == '__main__':
    print("==========================================")
    print(" Meridian 59 AutoMap Generator & Unlocker ")
    print("==========================================")
    print("This script reads your local .roo files to generate a perfectly")
    print("matched, 100% completed game.map for your specific client.\n")
    
    rooms_dir, map_file, is_running = detect_installation()
    
    if not rooms_dir or not map_file:
        print("Could not auto-detect Meridian 59 installation.")
        rooms_dir = input("Enter path to 'rooms' directory (e.g. C:\\Meridian59\\resource\\rooms):\n> ").strip()
        map_file = input("Enter path to save 'game.map' (e.g. C:\\Meridian59\\mail\\game.map):\n> ").strip()
        
    if not os.path.isdir(rooms_dir):
        print(f"Error: Directory '{rooms_dir}' not found.")
        sys.exit(1)

    print(f"\nScanning for .roo files in: {rooms_dir}")
    roo_files = glob.glob(os.path.join(rooms_dir, '*.roo'))
    if not roo_files:
        print("No .roo files found. Make sure you selected the correct 'resource/rooms' directory.")
        sys.exit(1)
        
    print(f"Found {len(roo_files)} room files. Extracting map data...")
    
    unique_rooms = {}
    for roo in roo_files:
        info = get_room_info(roo)
        if info:
            sec, num_walls, roo_name = info
            unique_rooms[sec] = (num_walls, roo_name)

    if not unique_rooms:
        print("No valid room data extracted.")
        sys.exit(1)
        
    # 1. Analyze existing map
    percent = analyze_map(map_file, unique_rooms)
    
    if percent >= 100.0:
        print("Your map is already 100% complete!")
        ans = input("Do you want to regenerate it anyway? (y/n): ").strip().lower()
        if ans != 'y':
            sys.exit(0)
    else:
        ans = input("Do you want to update and unlock your game map? (y/n): ").strip().lower()
        if ans != 'y':
            print("Operation cancelled.")
            sys.exit(0)

    # 2. Handle running game
    if is_running:
        print("\nMeridian 59 is currently running. The game must be closed to update the map file safely.")
        close_ans = input("Close Meridian 59 now? (y/n): ").strip().lower()
        if close_ans == 'y':
            try:
                subprocess.run(['taskkill', '/F', '/IM', 'meridian.exe'], capture_output=True)
                print("Closed Meridian 59.")
            except Exception as e:
                print(f"Failed to close Meridian 59: {e}")
                print("Please close it manually before continuing.")
                input("Press Enter once Meridian 59 is closed...")
        else:
            print("Please close Meridian 59 manually before continuing.")
            input("Press Enter once Meridian 59 is closed...")

    # 3. Generate Map
    generate_map(map_file, unique_rooms)
    
    # 4. Show new analysis
    analyze_map(map_file, unique_rooms)
    
    input("\nPress Enter to exit...")
