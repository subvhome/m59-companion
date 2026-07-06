import os
import struct

def extract_existing_annotations(map_file, unique_rooms):
    annotations_by_room = {} # key: roo_name
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
                                # Map security to roo_name if possible
                                if security in unique_rooms:
                                    _, roo_name = unique_rooms[security]
                                    annotations_by_room[roo_name] = annos

    except Exception as e:
        print(f"Error extracting existing annotations: {e}")

    return annotations_by_room
