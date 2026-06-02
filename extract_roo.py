import struct
import sys
import os

def extract_roo_info(file_path):
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(4)
            if magic != b'ROO\xb1':
                return f"Error: {file_path} is not a valid .roo file"

            f.seek(12)
            main_pos = struct.unpack('<I', f.read(4))[0]
            server_pos = struct.unpack('<I', f.read(4))[0]

            # Server Grid Dimensions
            f.seek(server_pos)
            rows = struct.unpack('<I', f.read(4))[0]
            cols = struct.unpack('<I', f.read(4))[0]

            # Thing-based Dimensions
            f.seek(main_pos + 28)
            thing_pos = struct.unpack('<I', f.read(4))[0]
            f.seek(thing_pos)
            num_things = struct.unpack('<H', f.read(2))[0]
            
            thing_dims = "N/A"
            player_boxes = []
            if num_things >= 2:
                if num_things <= 2: # Old format
                    for _ in range(2):
                        player_boxes.append(struct.unpack('<ii', f.read(8)))
                else: # New format
                    for _ in range(2):
                        data = f.read(96)
                        player_boxes.append(struct.unpack('<ii', data[8:16]))
                
                width = abs(player_boxes[1][0] - player_boxes[0][0])
                height = abs(player_boxes[1][1] - player_boxes[0][1])
                thing_dims = f"{width // 64}x{height // 64}"

            return {
                "num_things": num_things,
                "grid": f"{cols}x{rows}",
                "derived": thing_dims,
                "box1": player_boxes[0] if player_boxes else None,
                "box2": player_boxes[1] if player_boxes else None
            }
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_roo.py <file.roo>")
    else:
        res = extract_roo_info(sys.argv[1])
        if isinstance(res, dict):
            print(f"File: {os.path.basename(sys.argv[1])}")
            print(f"Num Things: {res['num_things']}")
            print(f"Server Grid: {res['grid']}")
            print(f"Thing Dimensions: {res['derived']}")
            print(f"Corner 1 (Editor): {res['box1']}")
            print(f"Corner 2 (Editor): {res['box2']}")
            if res['box1'] and res['box2']:
                x0, y0 = res['box1']
                x1, y1 = res['box2']
                left, top = min(x0, x1), max(y0, y1)
                print(f"Server Coords: (1,1) to ({1 + abs(x1-x0)//64}, {1 + abs(y1-y0)//64})")
        else:
            print(res)
