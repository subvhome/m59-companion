import os
import json
import time
import collections
from datetime import datetime

class GPSManager:
    def __init__(self, map_path="m59_map.json", dataset_path="meridian_rooms_dataset.json"):
        self.map_path = map_path
        self.dataset_path = dataset_path
        self.m59_map = self.load_map_data()
        self.dataset = self.load_dataset()
        self.last_room = None
        self.transition_start_time = 0
        
        # Navigation state
        self.current_destination_rid = None
        self.current_path = [] # List of (rid, exit_info)
        self.current_step_index = 0
        self.last_known_rid = None

    def load_map_data(self):
        """Loads the discovered room data from JSON."""
        if os.path.exists(self.map_path):
            try:
                with open(self.map_path, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def load_dataset(self):
        """Loads the comprehensive room connectivity dataset."""
        if os.path.exists(self.dataset_path):
            try:
                with open(self.dataset_path, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_map_data(self):
        """Saves discovered room data to JSON."""
        try:
            with open(self.map_path, "w") as f:
                json.dump(self.m59_map, f, indent=4)
        except:
            pass

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

    def find_path(self, start_rid, end_rid):
        """Finds the shortest path between two RIDs using BFS."""
        if not self.dataset or start_rid not in self.dataset or end_rid not in self.dataset:
            return None
            
        queue = collections.deque([(start_rid, [])])
        visited = {start_rid}
        
        while queue:
            curr_rid, path = queue.popleft()
            if curr_rid == end_rid:
                return path
                
            for exit_info in self.dataset[curr_rid].get('exits', []):
                to_rid = exit_info['to_rid']
                if to_rid not in visited:
                    visited.add(to_rid)
                    queue.append((to_rid, path + [(curr_rid, exit_info)]))
        return None

    def get_friendly_instruction(self, from_rid, exit_info):
        """Creates a human-readable instruction based on exit type and location."""
        if not self.dataset: return "Move to destination."
        
        from_pos = exit_info.get('from', [None, None])
        to_rid = exit_info['to_rid']
        dest_name = self.dataset.get(to_rid, {}).get('name', "another area")
        
        # Compass logic
        row, col = from_pos
        direction_hint = "the Center"
        if row is not None and col is not None:
            v, h = "", ""
            if row < 22: v = "North"
            elif row > 42: v = "South"
            if col < 22: h = "West"
            elif col > 42: h = "East"
            direction_hint = f"the {v}-{h}".replace("--", "-").strip("-") + " area"
            if direction_hint == "the  area": direction_hint = "the Center"

        obj_name = exit_info.get('object', 'entrance')
        if obj_name == 'SpiderTree': obj_name = 'Web Covered Tree'

        if exit_info['type'] == 'point':
            return f"Walk to {direction_hint} and enter the {obj_name} to reach {dest_name}."
        
        if exit_info['type'] == 'edge':
            direction = exit_info['direction'].replace('LEAVE_', '').title()
            return f"Follow the path out the {direction} side of the room to reach {dest_name}."
        
        if exit_info['type'] == 'manual':
            if from_pos[0] is not None:
                return f"Walk to {direction_hint} to reach {dest_name}."
            return f"Look for a special entrance (hole or hidden path) to reach {dest_name}."

        return f"Move to {dest_name}."

    def resolve_name_to_rid(self, name):
        """Attempts to find the most likely RID for a given room name."""
        if not self.dataset: return None
        matches = [rid for rid, info in self.dataset.items() if info['name'].lower() == name.lower()]
        if not matches: return None
        if len(matches) == 1: 
            self.last_known_rid = matches[0]
            return matches[0]
        
        # If we have multiple matches, prioritize one connected to our last_known_rid
        if self.last_known_rid and self.last_known_rid in self.dataset:
            for exit_info in self.dataset[self.last_known_rid].get('exits', []):
                to_rid = exit_info['to_rid']
                if to_rid in matches:
                    self.last_known_rid = to_rid
                    return to_rid
                    
        # Fallback to first match but don't update last_known_rid as confidently
        return matches[0]

    def record_transition(self, from_room, to_room, duration):
        """Updates the map data with a new room connection and time."""
        if from_room not in self.m59_map:
            self.m59_map[from_room] = {"connections": {}}
        
        direction = "Unknown" 
        conn_key = f"{direction}:{to_room}"
        existing_time = self.m59_map[from_room]["connections"].get(conn_key)
        
        updated = False
        if existing_time is None or duration < existing_time:
            self.m59_map[from_room]["connections"][conn_key] = duration
            updated = True
            self.save_map_data()
            
        return updated, duration, existing_time

    def process_room_update(self, current_room):
        """Detects changes and records data. Returns (was_transition, log_msg)"""
        if current_room == "Unknown Location":
            return False, None

        now = time.time()
        was_transition = False
        log_msg = None

        if current_room != self.last_room:
            if self.last_room is not None:
                duration = round(now - self.transition_start_time, 2)
                improved, dur, old = self.record_transition(self.last_room, current_room, duration)
                
                if improved:
                    log_msg = f"New Record! {self.last_room} -> {current_room} in {dur}s"
                else:
                    log_msg = f"Transition: {self.last_room} -> {current_room} in {dur}s (Slower than {old}s)"
                
                was_transition = True
            else:
                log_msg = f"Starting GPS Tracking at: {current_room}"
            
            self.last_room = current_room
            self.transition_start_time = now
            
        return was_transition, log_msg
