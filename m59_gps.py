import os
import json
import time
import collections
import logging
import heapq
import math
from datetime import datetime

logger = logging.getLogger("dashboard")

class GPSManager:
    def __init__(self, dataset_path="settings/meridian_rooms_dataset.json"):
        self.dataset_path = dataset_path
        self.dataset = self.load_dataset()
        self.last_room = None
        self.transition_start_time = 0
        
        # Navigation state
        self.current_destination_rid = None
        self.current_path = [] # List of (rid, exit_info)
        self.current_step_index = 0
        self.last_known_rid = None
        self.last_known_from_rid = None

    def load_dataset(self):
        """Loads the comprehensive room connectivity dataset."""
        if os.path.exists(self.dataset_path):
            try:
                with open(self.dataset_path, "r") as f:
                    data = json.load(f)
                    logger.info(f"GPS: Loaded world dataset with {len(data)} rooms from {self.dataset_path}")
                    return data
            except Exception as e:
                logger.error(f"GPS: Failed to parse dataset: {e}")
                return {}
        else:
            logger.error(f"GPS: World dataset NOT FOUND at {self.dataset_path}")
        return {}

    def save_dataset(self):
        """Saves the world dataset, including learned travel times."""
        try:
            with open(self.dataset_path, "w") as f:
                json.dump(self.dataset, f, indent=4)
        except Exception as e:
            logger.error(f"GPS: Failed to save dataset: {e}")

    def get_room_options(self):
        """Returns a list of all unique room names with 'Nearby' hints for duplicates."""
        if not self.dataset:
            return []

        name_map = collections.defaultdict(list)
        for rid, info in self.dataset.items():
            name_map[info['name']].append(rid)

        options = []
        for name, rids in name_map.items():
            if len(rids) == 1:
                options.append({"name": name, "rid": rids[0], "display": name})
            else:
                for rid in rids:
                    # Find a neighbor to help distinguish
                    neighbor = "Unknown"
                    exits = self.dataset[rid].get('exits', [])
                    for e in exits:
                        n_name = self.dataset.get(e['to_rid'], {}).get('name')
                        if n_name and n_name != name:
                            neighbor = n_name
                            break
                    options.append({"name": name, "rid": rid, "display": f"{name} (Near: {neighbor})"})
        return sorted(options, key=lambda x: x['display'])

    def get_8point_direction(self, start_pos, end_pos, grid_dims):
        """Calculates high-precision direction with Cardinal Dominance logic."""
        if not start_pos or not end_pos or None in start_pos or None in end_pos:
            return "CENTER •"
            
        r1, c1 = start_pos
        r2, c2 = end_pos
        
        dr = r2 - r1
        dc = c2 - c1
        
        # Base thresholds (to avoid "Center" loops)
        row_threshold = max(1, grid_dims[1] * 0.03)
        col_threshold = max(1, grid_dims[0] * 0.03)

        v, h = "", ""
        if abs(dr) > row_threshold:
            v = "NORTH" if dr < 0 else "SOUTH"
        if abs(dc) > col_threshold:
            h = "WEST" if dc < 0 else "EAST"

        # CARDINAL DOMINANCE Logic
        # If one axis is much stronger than the other, lock to it (ignore minor diagonal drift)
        if v and h:
            ratio = abs(dc) / abs(dr)
            if ratio < 0.45: # Primarily vertical
                h = ""
            elif ratio > 2.2: # Primarily horizontal
                v = ""

        mapping = {
            "NORTH": "↑", "SOUTH": "↓", "EAST": "→", "WEST": "←",
            "NORTH-EAST": "↗", "SOUTH-EAST": "↘", "SOUTH-WEST": "↙", "NORTH-WEST": "↖",
            "CENTER": "•"
        }
        
        dir_name = f"{v}-{h}".strip("-") if v or h else "CENTER"
        arrow = mapping.get(dir_name, "•")
        
        return f"{dir_name} {arrow}"

    def get_friendly_instruction(self, from_rid, exit_info, step=None, total=None, arrival_pos=None):
        """Creates a high-signal 3-liner HUD instruction with Relative Perspective."""
        if not self.dataset: return "No Data\nMove to destination"
        
        exit_from = exit_info.get('from', [None, None])
        to_rid = exit_info['to_rid']
        dest_name = self.dataset.get(to_rid, {}).get('name', "another area")
        
        # Progress Tracker Prefix
        prefix = f"[{step}/{total}]" if step is not None and total is not None else ""

        # Default arrival_pos to room's teleport point if not provided
        if arrival_pos is None:
            arrival_pos = self.dataset.get(from_rid, {}).get('teleport', [32, 32])

        # Direction calculation
        grid_dims = self.dataset.get(from_rid, {}).get('grid', [64, 64])
        dir_hud = self.get_8point_direction(arrival_pos, exit_from, grid_dims)

        # EDGE TRANSITION Logic: Always trust the code's intended wall
        if exit_info['type'] == 'edge' and 'direction' in exit_info:
            code_dir = exit_info['direction'].replace('LEAVE_', '')
            mapping = {"NORTH": "↑", "SOUTH": "↓", "EAST": "→", "WEST": "←"}
            dir_hud = f"{code_dir} {mapping.get(code_dir, '•')}"

        # Action detection
        action = "Path"
        obj_name = exit_info.get('object', '').lower()
        if exit_info['type'] == 'point':
            action = "Door"
            if "hole" in obj_name or "pit" in obj_name or "nest" in from_rid.lower() or "cave" in from_rid.lower():
                action = "Hole"
            elif "tree" in obj_name:
                action = "Tree"
            elif obj_name:
                action = obj_name.title()
        
        if exit_info['type'] == 'manual' and not exit_from[0]:
            return f"{prefix}\nGO FIND\n➔ {dest_name}"

        line1 = f"{prefix}"
        line2 = f"GO {dir_hud}"
        line3 = f"{action} to {dest_name}"
        
        return f"{line1}\n{line2}\n{line3}"

    def find_path(self, start_rid, end_rid):
        """Finds the shortest path based on learned travel times (Dijkstra) with Proximity Logic."""
        if not self.dataset or start_rid not in self.dataset or end_rid not in self.dataset:
            return None
            
        # Default weight for untimed transitions
        DEFAULT_TRANSITION_TIME = 10.0 
        
        # Start at the room's teleport point
        start_tele = self.dataset[start_rid].get('teleport', [32, 32])
        
        count = 0
        pq = [(0, count, start_rid, [], start_tele)] # (total_time, tie_breaker, current_rid, path, arrival_pos)
        visited = {} # (rid, tuple(arrival_pos)): total_time
        
        while pq:
            curr_time, _, curr_rid, path, arrival_pos = heapq.heappop(pq)
            
            if curr_rid == end_rid:
                return path
                
            state = (curr_rid, tuple(arrival_pos))
            if state in visited and visited[state] <= curr_time:
                continue
            visited[state] = curr_time
            
            # Group exits by to_rid to pick the physically closest option if destinations are identical
            destination_map = {}
            for exit_info in self.dataset[curr_rid].get('exits', []):
                to_rid = exit_info['to_rid']
                if to_rid not in self.dataset: continue
                
                # Calculate distance for THIS specific exit option from current arrival_pos
                exit_from = exit_info.get('from')
                if not exit_from or exit_from[0] is None:
                    grid = self.dataset[curr_rid].get('grid', [64, 64])
                    exit_from = [grid[1]//2, grid[0]//2]
                
                this_dist = math.sqrt((exit_from[0] - arrival_pos[0])**2 + (exit_from[1] - arrival_pos[1])**2)
                
                if to_rid not in destination_map:
                    destination_map[to_rid] = (exit_info, this_dist)
                else:
                    existing_info, existing_dist = destination_map[to_rid]
                    # Priority: 1. Type (Point > Edge > Manual), 2. Proximity (Dist)
                    better = False
                    if exit_info['type'] == 'point' and existing_info['type'] != 'point':
                        better = True
                    elif exit_info['type'] == existing_info['type'] and this_dist < existing_dist:
                        better = True
                    elif exit_info['type'] == 'edge' and existing_info['type'] == 'manual':
                        better = True
                    if better:
                        destination_map[to_rid] = (exit_info, this_dist)

            for to_rid, (exit_info, dist) in destination_map.items():
                # Get weight from learned travel times
                weight = exit_info.get('travel_time', DEFAULT_TRANSITION_TIME)
                
                # Destination Arrival Point
                to_pos = exit_info.get('to_pos')
                if not to_pos or to_pos[0] is None:
                    to_pos = self.dataset[to_rid].get('teleport', [32, 32])

                new_time = curr_time + weight
                new_state = (to_rid, tuple(to_pos))
                if new_state not in visited or new_time < visited[new_state]:
                    count += 1
                    heapq.heappush(pq, (new_time, count, to_rid, path + [(curr_rid, exit_info)], to_pos))
                    
        return None

    def resolve_name_to_rid(self, name):
        """Attempts to find the most likely RID for a given room name."""
        if not self.dataset: return None
        matches = [rid for rid, info in self.dataset.items() if info['name'].lower() == name.lower()]
        if not matches: return None
        
        resolved_rid = matches[0]
        if len(matches) > 1 and self.last_known_from_rid:
            for exit_info in self.dataset.get(self.last_known_from_rid, {}).get('exits', []):
                if exit_info['to_rid'] in matches:
                    resolved_rid = exit_info['to_rid']
                    break
                    
        return resolved_rid

    def record_transition(self, from_rid, to_rid, duration):
        """Updates travel history. Always saves first time, then only if faster."""
        if not self.dataset or from_rid not in self.dataset:
            return False, duration, None
            
        exits = self.dataset[from_rid].get('exits', [])
        updated = False
        existing_time = None
        
        for exit_info in exits:
            if exit_info.get('to_rid') == to_rid:
                existing_time = exit_info.get('travel_time')
                if existing_time is None or duration < existing_time:
                    exit_info['travel_time'] = duration
                    updated = True
        
        if updated:
            self.save_dataset()
            logger.info(f"GPS: Learned faster path {from_rid}->{to_rid}: {duration}s")
            
        return updated, duration, existing_time

    def process_room_update(self, current_room):
        """Updates navigation status based on current room string."""
        if current_room == "Unknown Location": return False, None
        now = time.time()
        was_transition = False
        log_msg = None
        
        current_rid = self.resolve_name_to_rid(current_room)
        
        if current_room != self.last_room:
            if self.last_room is not None and self.last_known_from_rid and current_rid:
                duration = round(now - self.transition_start_time, 2)
                # Cap extremely long durations to 1 hour just for sanity, 
                # but basically follow the "always save delta" rule
                if duration < 3600:
                    improved, dur, old = self.record_transition(self.last_known_from_rid, current_rid, duration)
                    log_msg = f"Transition: {self.last_room} -> {current_room} in {dur}s"
                    if improved: log_msg += " (New Personal Best!)"
                    was_transition = True
            
            self.last_room = current_room
            self.last_known_from_rid = current_rid
            self.transition_start_time = now
            
        return was_transition, log_msg
