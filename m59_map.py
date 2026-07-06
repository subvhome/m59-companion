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

def generate_map(map_file, unique_rooms, debug=False, preserve_annotations=False, existing_annotations=None):
    if existing_annotations is None: existing_annotations = {}
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
                    RID_TO_ROO_MAP = {'RID_BADLAND2': 'badland2', 'RID_BAZMANS_ROOM': 'bizmans', 'RID_JUNGLE_BOWMAKER_HUT': 'bowmaker', 'RID_CASTLE1C': 'castle1c', 'RID_CASTLE2A': 'castle2a', 'RID_CASTLE2D': 'castle2d', 'RID_CASTLE2E': 'castle2e', 'RID_cave3': 'cave3', 'RID_DUKE1': 'duke1', 'RID_DUKE2': 'duke2', 'RID_DUKE3': 'duke3', 'RID_DUNGEON': 'greeny', 'RID_FIELD1': 'field1', 'RID_GALLERY': 'univ', 'RID_GODROOM': 'zndramas', 'RID_GUEST1': 'guest1', 'RID_GUEST2': 'guest2', 'RID_guest3': 'guest3', 'RID_guest4': 'guest4', 'RID_guest5': 'guest5', 'RID_guest7': 'guest7', 'RID_guest8': 'guest8', 'RID_HERMITHUT': 'hermhut', 'RID_MOCKERS_ROOM': 'mockers', 'RID_BRAX_ARENA': 'necarena', 'RID_OUTOFGRACE': 'outgrace', 'RID_PROFILE': 'tos', 'RID_TEMPLE_KRAANAN': 'tempkra', 'RID_TEMPLE': 'temple', 'RID_TEMPLE_QOR': 'tempqor', 'RID_TEMPLE_RIIJA': 'ke1', 'RID_JUNGLE_TRADING_POST': 'tpost1', 'RID_JUNGLE_TRADING_POST_CELLAR': 'tpost2', 'RID_UNIVERSITY': 'univ', 'RID_ASSHQ': 'asshq', 'RID_BAR_APOTH': 'barapoth', 'RID_BAR_COURT': 'barcourt', 'RID_BAR_HALL': 'barhall', 'RID_BAR_INN': 'barinn', 'RID_BAR_JAIL': 'barjail', 'RID_BAR_NORTH': 'barln', 'RID_BAR_PORT': 'barlport', 'RID_BAR_SOUTH': 'barls', 'RID_BAR_MERCHANT': 'barmerch', 'RID_BAR_SMITHY': 'barsmith', 'RID_BAR_VAULT': 'barvault', 'RID_GM_HALL': 'gmhall', 'RID_COR_UNIV': 'coruniv', 'RID_COR_GROCER': 'corgroc', 'RID_COR_HALL': 'corhall', 'RID_COR_INN': 'corinn', 'RID_CORNOTH': 'cornoth', 'RID_COR_TAILOR': 'cortail', 'RID_COR_WEAPONSMASTER': 'weaponsm', 'RID_FORGOTTEN_TOO': 'bizmans', 'RID_GUILDH1': 'guildh1', 'RID_GUILDH10': 'guildh10', 'RID_GUILDH11': 'guildh11', 'RID_GUILDH12': 'guildh12', 'RID_GUILDH13': 'guildh13', 'RID_GUILDH14': 'guildh14', 'RID_guildh15': 'guildh15', 'RID_GUILDH2': 'guildh2', 'RID_GUILDH3': 'guildh3', 'RID_GUILDH4': 'guildh4', 'RID_GUILDH5': 'guildh5', 'RID_GUILDH6': 'guildh6', 'RID_GUILDH7': 'guildh7', 'RID_GUILDH8': 'guildh8', 'RID_GUILDH9': 'guildh9', 'RID_JAS_AB1': 'jasab1', 'RID_JAS_AB10': 'jasab10', 'RID_JAS_AB11': 'jasab11', 'RID_JAS_AB12': 'jasab12', 'RID_JAS_AB13': 'jasab13', 'RID_JAS_AB14': 'jasab14', 'RID_JAS_AB2': 'jasab2', 'RID_JAS_AB3': 'jasab3', 'RID_JAS_AB4': 'jasab4', 'RID_JAS_AB5': 'jasab5', 'RID_JAS_AB6': 'jasab6', 'RID_JAS_AB7': 'jasab7', 'RID_JAS_AB8': 'jasab8', 'RID_JAS_AB9': 'jasab9', 'RID_JAS_BANK': 'jasbank', 'RID_JAS_ELDER_HUT': 'jaselder', 'RID_JAS_HALL': 'jashall', 'RID_JAS_INN': 'jasinn', 'RID_JASPER': 'jas-east', 'RID_JAS_SMITHY': 'jassmith', 'RID_JAS_STORE': 'jasstore', 'RID_JAS_TAVERN': 'jastavrn', 'RID_JASWEST': 'jas-west', 'RID_KOC_APOTH': 'kocapoth', 'RID_KOCATAN': 'settle1', 'RID_KOC_BANK': 'kocbank', 'RID_KOC_SMITHY': 'kocblack', 'RID_KOC_HALL_OF_HEROES': 'kochoh', 'RID_KOC_HALL_OF_HEROES_A': 'kochoha', 'RID_KOC_HALL_OF_HEROES_B': 'kochohb', 'RID_KOC_INN': 'kocinn', 'RID_KOC_SOUTH': 'settle2', 'RID_KOC_STORE': 'kocstore', 'RID_KOC_TAILOR': 'koctail', 'RID_KOC_TAVERN': 'koctav', 'RID_KOC_GUARDTOWER_EAST': 'koctower', 'RID_MAR_HALL': 'marhall', 'RID_MAR_HEALER_SHOP': 'marheal', 'RID_MARION': 'marion', 'RID_A5': 'a5', 'RID_A6': 'a6', 'RID_BADLAND1': 'badland1', 'RID_BAR_SEWER': 'barlsew', 'RID_BAR_SEWER2': 'barlsew2', 'RID_BAR_SEWER3': 'barlsew3', 'RID_C4': 'c4', 'RID_C6': 'c6', 'RID_CASTLE1B': 'castle1b', 'RID_CASTLE2B': 'castle2b', 'RID_CASTLE2C': 'castle2c', 'RID_D4': 'd4', 'RID_D5': 'd5', 'RID_D6': 'd6', 'RID_D7': 'd7', 'RID_E2': 'e2', 'RID_E4': 'e4', 'RID_E5': 'e5', 'RID_E7': 'e7', 'RID_F2': 'f2', 'RID_F3': 'f3', 'RID_F4': 'f4', 'RID_F6': 'f6', 'RID_F7': 'f7', 'RID_F8': 'f8', 'RID_FOREST2': 'forest2', 'RID_FOREST3': 'forest3', 'RID_FOREST4': 'forest4', 'RID_G4': 'g4', 'RID_G5': 'g5', 'RID_G6': 'g6', 'RID_G8': 'g8', 'RID_G9': 'g9', 'RID_guest6': 'guest6', 'RID_H3': 'h3', 'RID_H5': 'h5', 'RID_H6': 'h6', 'RID_H7': 'h7', 'RID_I3': 'i3', 'RID_I6': 'i6', 'RID_I7': 'i7', 'RID_I8': 'i8', 'RID_I9': 'i9', 'RID_J3': 'j3', 'RID_JAS_SEWER1': 'jassew1', 'RID_JAS_SEWER2': 'jassew2', 'RID_JAS_SEWER3': 'jassew3', 'RID_KOC_SEWER1': 'kocsew1', 'RID_KOC_SEWER2': 'kocsew2', 'RID_LICH_MAZE': 'lichmaze', 'RID_MAR_CRYPT3A': 'res00001', 'RID_MAR_CRYPT1': 'mardun01', 'RID_MAR_CRYPT2': 'mardun02', 'RID_NECROAREA3a': 'nec3a', 'RID_NECROAREA3b': 'nec3b', 'RID_NECROAREA1': 'necarea1', 'RID_NECROAREA2': 'necarea2', 'RID_NECROAREA3': 'necarea3', 'RID_NECROAREA4': 'necarea4', 'RID_NECROAREA5': 'necarea5', 'RID_NEST1': 'nest1', 'RID_OLD_BAR_NORTH': 'obarln', 'RID_OLD_BAR_SOUTH': 'obarls', 'RID_OLD_JASPER': 'ojas', 'RID_OLD_MARION': 'omar', 'RID_ORC_CAVE1_EXT': 'oc1a', 'RID_ORC_CAVE5_EXT': 'oc5b', 'RID_ORC_CAVE1': 'oc01', 'RID_ORC_CAVE2': 'oc02', 'RID_ORC_CAVE3': 'oc03', 'RID_ORC_CAVE4': 'oc04', 'RID_ORC_CAVE5': 'oc05', 'RID_ORC_CAVE6': 'oc06', 'RID_ORC_PIT_A': 'ocpa', 'RID_ORC_PIT_B': 'ocpb', 'RID_THRONE1': 'throne1', 'RID_TOS_CRYPT': 'toscrypt', 'RID_TOS_GRAVEYARD': 'tosgrave', 'RID_UNDERWORLD': 'uworld', 'RID_ORC_PIT': 'ocp1', 'RID_SEWER_KING': 'sewking', 'RID_A1': 'a1', 'RID_B1': 'b1', 'RID_B2': 'b2', 'RID_C1': 'c1', 'RID_C2': 'c2', 'RID_C3': 'c3', 'RID_D1': 'd1', 'RID_D2': 'd2', 'RID_KA0': 'ka0', 'RID_KA1': 'ka1', 'RID_KA2': 'ka2', 'RID_KA3': 'ka3', 'RID_KA4': 'ka4', 'RID_KA5': 'ka5', 'RID_KB1': 'kb1', 'RID_KB2': 'kb2', 'RID_KB3': 'kb3', 'RID_KB4': 'kb4', 'RID_KB5': 'kb5', 'RID_KC1': 'kc1', 'RID_KC2': 'kc2', 'RID_KC3': 'kc3', 'RID_KC4': 'kc4', 'RID_KC5': 'kc5', 'RID_KD1': 'kd1', 'RID_KD2': 'kd2', 'RID_KD3': 'kd3', 'RID_KD4': 'kd4', 'RID_KE2': 'ke2', 'RID_KE4': 'ke4', 'RID_MAD_SCIENTIST_HUT': 'kc5a', 'RID_B6': 'b6', 'RID_BAR_BAR': 'barlbar1', 'RID_C5': 'c5', 'RID_C7': 'c7', 'RID_CANYON1': 'canyons', 'RID_CANYON2': 'canyons2', 'RID_CASTLE1': 'castle1', 'RID_CAVE2': 'cave2', 'RID_DUKE4': 'duke4', 'RID_DUKE5': 'duke5', 'RID_E6': 'e6', 'RID_FOREST1': 'forest1', 'RID_FOREST5': 'forest5', 'RID_H4': 'h4', 'RID_H9': 'h9', 'RID_ICE_CAVE1': 'icecave1', 'RID_K5': 'k5', 'RID_MAR_ELDER_HUT': 'marelder', 'RID_MAR_INN': 'marinn', 'RID_MAR_SMITHY': 'marsmith', 'RID_TOS_INN': 'tosinn', 'RID_EAST_TOS': 'easttos', 'RID_TOS': 'tos', 'RID_TOS_APOTH': 'tosapoth', 'RID_TOS_ARENA2': 'tosaren2', 'RID_TOS_ARENA': 'tosarena', 'RID_TOS_BANK': 'tosbank', 'RID_TOS_INN_CELLAR': 'toscellar', 'RID_TOS_FORGET': 'kochoh', 'RID_TOS_GREY': 'tosgrey', 'RID_TOS_HALL': 'toshall', 'RID_TOS_SECRET_PASSAGE': 'toshidden', 'RID_TOS_FORGOTTEN': 'tosforgt', 'RID_TOS_SMITHY': 'tossmith', 'RID_TOS_TAN': 'tostan', 'RID_TOS_OLD_TAVERN': 'tostavern'}
                    
                    fallback = RID_TO_ROO_MAP.get(k, k.replace("RID_", "").lower().replace("_", ""))
                    r_name = v.get("roo_filename", fallback)
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
            if debug:
                print("\n[DEBUG] Annotation mapping loaded:")
                for r_name, annos in list(room_annotations.items())[:5]:
                    print(f"  {r_name}: {len(annos)} annotations")
                print("  ...\n")
        except Exception as e:
            print(f"Failed to load dataset: {e}")

    if preserve_annotations:
        room_annotations = existing_annotations
        print(f"Preserving {len(room_annotations)} existing room annotations.")

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
                        if debug:
                            print(f"[DEBUG] Found {len(annotation_data)} annotations for room: {roo_name}")
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
                        if debug:
                            print(f"[DEBUG] No annotations found for room: {roo_name}")
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
    
    debug_mode = "--debug" in sys.argv
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
    generate_map(map_file, unique_rooms, debug=debug_mode)
    
    # 4. Show new analysis
    analyze_map(map_file, unique_rooms)
    
    input("\nPress Enter to exit...")

def extract_existing_annotations(map_file, unique_rooms):
    annotations_by_room = {}
    import os, struct
    if not os.path.exists(map_file):
        return annotations_by_room

    try:
        with open(map_file, 'rb') as f:
            f.seek(8)
            top_table_data = f.read(400)
            if len(top_table_data) < 400: return annotations_by_room
            top_table = struct.unpack('<100I', top_table_data)

            for top_offset in top_table:
                if top_offset == 0: continue
                f.seek(top_offset)
                f.read(4)
                lower_table_data = f.read(800)
                if len(lower_table_data) < 800: continue
                lower_table = struct.unpack('<200i', lower_table_data)

                for i in range(100):
                    security = lower_table[i*2]
                    offset = lower_table[i*2+1]
                    if security == 0 or offset <= 0: continue

                    f.seek(offset)
                    num_walls_data = f.read(4)
                    if len(num_walls_data) < 4: continue
                    num_walls = struct.unpack('<I', num_walls_data)[0]

                    full_bytes = num_walls // 8
                    remainder = num_walls % 8
                    wall_bytes_len = full_bytes + (1 if remainder > 0 else 0)
                    f.seek(wall_bytes_len, os.SEEK_CUR)
                    
                    anno_offset_data = f.read(4)
                    if len(anno_offset_data) < 4: continue
                    anno_offset = struct.unpack('<I', anno_offset_data)[0]
                    
                    if anno_offset > 0:
                        f.seek(anno_offset)
                        num_annos_data = f.read(4)
                        if len(num_annos_data) == 4:
                            num_annos = struct.unpack('<I', num_annos_data)[0]
                            num_annos = min(num_annos, 20)
                            
                            annos = []
                            for _ in range(num_annos):
                                anno_data = f.read(108)
                                if len(anno_data) < 108: break
                                x, y = struct.unpack('<ii', anno_data[:8])
                                text = anno_data[8:].split(b'\x00')[0].decode('utf-8', 'ignore')
                                if text:
                                    annos.append({"x": x, "y": y, "text": text})
                            
                            if annos:
                                if security in unique_rooms:
                                    _, roo_name = unique_rooms[security]
                                    annotations_by_room[roo_name] = annos

    except Exception as e:
        print(f"Error extracting existing annotations: {e}")

    return annotations_by_room

def get_unique_rooms(rooms_dir):
    import os, glob
    roo_files = glob.glob(os.path.join(rooms_dir, '*.roo'))
    unique_rooms = {}
    for roo in roo_files:
        info = get_room_info(roo)
        if info:
            sec, num_walls, roo_name = info
            unique_rooms[sec] = (num_walls, roo_name)
    return unique_rooms
