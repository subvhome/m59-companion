import struct
import zlib
import os
import urllib.request
from PIL import Image, ImageTk

class BGFManager:
    def __init__(self, resource_dir=None):
        self.resource_dir = resource_dir
        self.palette = self._load_palette()
        self._cache = {}  # filepath -> ImageTk.PhotoImage

    def _load_palette(self):
        palette = []
        pal_path = "blakston.pal"
        
        if not os.path.exists(pal_path):
            try:
                url = "https://raw.githubusercontent.com/Meridian59/Meridian59/master/blakston.pal"
                urllib.request.urlretrieve(url, pal_path)
            except Exception as e:
                print("Failed to download blakston.pal:", e)
                
        try:
            with open(pal_path, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                        palette.extend([r, g, b])
        except Exception as e:
            for i in range(256):
                palette.extend([i, i, i])
                
        if len(palette) < 768:
            palette.extend([0] * (768 - len(palette)))
        elif len(palette) > 768:
            palette = palette[:768]
            
        return palette

    def _load_raw_frames(self, filepath):
        if not os.path.exists(filepath): return None
        try:
            frames = []
            with open(filepath, "rb") as f:
                magic = f.read(4)
                if magic != b"BGF\x11": return None
                
                version = struct.unpack("<I", f.read(4))[0]
                name = f.read(32).decode("ascii", "ignore").strip('\x00')
                num_bitmaps = struct.unpack("<I", f.read(4))[0]
                num_groups = struct.unpack("<I", f.read(4))[0]
                max_indices = struct.unpack("<I", f.read(4))[0]
                shrink = struct.unpack("<I", f.read(4))[0]
                
                if num_bitmaps == 0: return None

                for i in range(num_bitmaps):
                    width, height = struct.unpack("<II", f.read(8))
                    x_off, y_off = struct.unpack("<ii", f.read(8))
                    
                    num_hotspots = struct.unpack("B", f.read(1))[0]
                    for _ in range(num_hotspots): f.read(9)
                        
                    is_comp = struct.unpack("B", f.read(1))[0]
                    if is_comp == 1:
                        comp_len = struct.unpack("<I", f.read(4))[0]
                        comp_data = f.read(comp_len)
                        try: data = zlib.decompress(comp_data)
                        except: data = b'\x00' * (width * height)
                    else:
                        _ = struct.unpack("<I", f.read(4))[0]
                        data = f.read(width * height)
                        
                    img = Image.new("P", (width, height))
                    img.putpalette(self.palette)
                    img.frombytes(data[:width*height])
                    
                    rgba_img = img.convert("RGBA")
                    datas = rgba_img.getdata()
                    trans_color = tuple(self.palette[254*3:254*3+3])
                    
                    new_data = []
                    for item in datas:
                        if item[0] == trans_color[0] and item[1] == trans_color[1] and item[2] == trans_color[2]:
                            new_data.append((255, 255, 255, 0))
                        else:
                            new_data.append(item)
                    rgba_img.putdata(new_data)
                    
                    frames.append({
                        "image": rgba_img,
                        "x_off": x_off,
                        "y_off": y_off
                    })
            return frames
        except Exception as e:
            print(f"Error loading BGF {filepath}: {e}")
            return None

    def load_bgf_frames(self, filepath):
        if filepath in self._cache:
            return self._cache[filepath]
        
        paths = filepath.split("|")
        all_layers_frames = []
        for p in paths:
            frames = self._load_raw_frames(p)
            if frames:
                all_layers_frames.append(frames)
                
        if not all_layers_frames:
            return None
            
        base_frames = all_layers_frames[0]
        num_frames = len(base_frames)
        final_photos = []
        cw, ch = 400, 400
        cx, cy = 200, 300
        
        for i in range(num_frames):
            comp_img = Image.new("RGBA", (cw, ch), (255, 255, 255, 0))
            for layer_frames in all_layers_frames:
                f = layer_frames[i % len(layer_frames)]
                comp_img.paste(f['image'], (cx + f['x_off'], cy + f['y_off']), f['image'])
            bbox = comp_img.getbbox()
            if bbox:
                comp_img = comp_img.crop(bbox)
            final_photos.append(comp_img)
            
        self._cache[filepath] = final_photos
        return final_photos

    def load_bgf_first_frame(self, filepath):
        if filepath in self._cache:
            return self._cache[filepath]

        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "rb") as f:
                magic = f.read(4)
                if magic != b"BGF\x11":
                    return None
                    
                version = struct.unpack("<I", f.read(4))[0]
                name = f.read(32).decode("ascii", "ignore").strip('\x00')
                num_bitmaps = struct.unpack("<I", f.read(4))[0]
                num_groups = struct.unpack("<I", f.read(4))[0]
                max_indices = struct.unpack("<I", f.read(4))[0]
                shrink = struct.unpack("<I", f.read(4))[0]
                
                if num_bitmaps == 0:
                    return None

                # Read first bitmap
                width, height = struct.unpack("<II", f.read(8))
                x_off, y_off = struct.unpack("<ii", f.read(8))
                
                num_hotspots = struct.unpack("B", f.read(1))[0]
                for _ in range(num_hotspots):
                    f.read(9) # skip hotspots
                    
                is_comp = struct.unpack("B", f.read(1))[0]
                if is_comp == 1:
                    comp_len = struct.unpack("<I", f.read(4))[0]
                    comp_data = f.read(comp_len)
                    data = zlib.decompress(comp_data)
                else:
                    _ = struct.unpack("<I", f.read(4))[0] # padding
                    data = f.read(width * height)
                    
                img = Image.new("P", (width, height))
                img.putpalette(self.palette)
                img.frombytes(data[:width*height])
                
                rgba_img = img.convert("RGBA")
                datas = rgba_img.getdata()
                trans_color = tuple(self.palette[254*3:254*3+3])
                
                new_data = []
                for item in datas:
                    if item[0] == trans_color[0] and item[1] == trans_color[1] and item[2] == trans_color[2]:
                        new_data.append((255, 255, 255, 0))
                    else:
                        new_data.append(item)
                rgba_img.putdata(new_data)
                
                # Resize if too big for a list icon (e.g., max 32x32)
                rgba_img.thumbnail((32, 32), Image.LANCZOS)
                
                photo = ImageTk.PhotoImage(rgba_img)
                self._cache[filepath] = photo
                return photo
        except Exception as e:
            print(f"Error loading BGF {filepath}: {e}")
            return None

    def find_bgf_for_monster(self, class_name):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"BGF: Searching for {class_name} in resource_dir={self.resource_dir}")
        if not self.resource_dir:
            logger.warning("BGF: resource_dir is None!")
            return None
            
        if "|" in class_name:
            paths = []
            for part in class_name.split("|"):
                p = self._find_single_bgf(part)
                if p:
                    paths.append(p)
            if paths:
                return "|".join(paths)
            return None
        return self._find_single_bgf(class_name)

    def _find_single_bgf(self, class_name):
        import logging
        logger = logging.getLogger(__name__)
        search_dirs = [self.resource_dir, os.path.join(self.resource_dir, "graphics")]
        
        if class_name.lower().endswith('.bgf'):
            candidates = [class_name, class_name.lower(), class_name.upper()]
        else:
            candidates = [f"{class_name}.bgf", f"{class_name.lower()}.bgf", f"{class_name[:8]}.bgf", f"{class_name[:8].lower()}.bgf"]
        
        for d in search_dirs:
            if not os.path.exists(d): continue
            for c in candidates:
                p = os.path.join(d, c)
                if os.path.exists(p):
                    return p
            try:
                files = os.listdir(d)
                for f in files:
                    if f.lower() in [c.lower() for c in candidates]:
                        return os.path.join(d, f)
            except:
                pass
        return None

    def load_mob_mapping(self, csv_path):
        mapping = {}
        if os.path.exists(csv_path):
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split(",")
                        if len(parts) >= 2 and " is Monster" in parts[0]:
                            internal_name = parts[0].split(" is Monster")[0].strip()
                            display_name = parts[1].strip().lower().rstrip('"')
                            cleaned_name = ''.join(c for c in display_name if c.isalnum() or c.isspace() or c == "'" or c == "-")
                            
                            bgf_name = parts[2].strip() if len(parts) > 2 else ""
                            target_name = bgf_name if bgf_name else internal_name
                            
                            if cleaned_name:
                                mapping[cleaned_name] = target_name
                                if cleaned_name.startswith("the "):
                                    mapping[cleaned_name[4:]] = target_name
                                if cleaned_name.startswith("a "):
                                    mapping[cleaned_name[2:]] = target_name
            except Exception as e:
                print(f"BGF ERROR: Could not read moblist: {e}")
        self.mob_mapping = mapping
        return mapping
