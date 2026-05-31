import os
import json
import time
import collections
import logging
import heapq
from datetime import datetime

logger = logging.getLogger("dashboard")

class GPSManager:
    def __init__(self, map_path="logs/travel_times.json", dataset_path="meridian_rooms_dataset.json"):
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
        self.last_known_from_rid = None

    def load_map_data(self):
        """Loads the discovered travel time data from JSON."""
        # Ensure logs directory exists
        os.makedirs("logs", exist_ok=True)
        
        # Handle migration from old m59_map.json if it exists
        old_path = "m59_map.json"
        if os.path.exists(old_path) and not os.path.exists(self.map_path):
            try:
                os.rename(old_path, self.map_path)
                logger.info(f"GPS: Migrated {old_path} to {self.map_path}")
            except: pass

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
                    data = json.load(f)
                    logger.info(f"GPS: Loaded world dataset with {len(data)} rooms from {self.dataset_path}")
                    return data
            except Exception as e:
                logger.error(f"GPS: Failed to parse dataset: {e}")
                return {}
        else:
            logger.error(f"GPS: World dataset NOT FOUND at {self.dataset_path}")
        return {}

    def save_map_data(self):
        """Saves travel time data to JSON."""
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
        """Finds the shortest path based on travel time using Dijkstra's algorithm."""
        if not self.dataset or start_rid not in self.dataset or end_rid not in self.dataset:
            return None
            
        # priority queue stores (total_time, tie_breaker, current_rid, current_path)
        # default weight for unknown edges is 10 seconds
        DEFAULT_WEIGHT = 10.0
        
        count = 0 # Tie-breaker counter
        pq = [(0, count, start_rid, [])]
        visited = {} # rid: total_time
        
        while pq:
            curr_time, _, curr_rid, path = heapq.heappop(pq)
            
            if curr_rid == end_rid:
                return path
                
            if curr_rid in visited and visited[curr_rid] <= curr_time:
                continue
            visited[curr_rid] = curr_time
            
            for exit_info in self.dataset[curr_rid].get('exits', []):
                to_rid = exit_info['to_rid']
                
                # Get weight from measured data
                weight = DEFAULT_WEIGHT
                if curr_rid in self.m59_map:
                    conn_key = f"Unknown:{to_rid}"
                    weight = self.m59_map[curr_rid].get("connections", {}).get(conn_key, DEFAULT_WEIGHT)
                
                new_time = curr_time + weight
                if to_rid not in visited or new_time < visited[to_rid]:
                    count += 1
                    heapq.heappush(pq, (new_time, count, to_rid, path + [(curr_rid, exit_info)]))
                    
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
        """Attempts to find the most likely RID for a given room name and updates last_known_rid."""
        if not self.dataset: return None
        matches = [rid for rid, info in self.dataset.items() if info['name'].lower() == name.lower()]
        if not matches: return None
        
        resolved_rid = matches[0]
        
        # If we have multiple matches, prioritize one connected to our last_known_rid
        if len(matches) > 1 and self.last_known_rid and self.last_known_rid in self.dataset:
            for exit_info in self.dataset[self.last_known_rid].get('exits', []):
                if exit_info['to_rid'] in matches:
                    resolved_rid = exit_info['to_rid']
                    break
                    
        self.last_known_rid = resolved_rid
        return resolved_rid

    def record_transition(self, from_rid, to_rid, duration):
        """Updates the map data with a new RID-to-RID connection and time."""
        if from_rid not in self.m59_map:
            self.m59_map[from_rid] = {"connections": {}}
        
        conn_key = f"Unknown:{to_rid}" 
        existing_time = self.m59_map[from_rid]["connections"].get(conn_key)
        
        updated = False
        if existing_time is None or duration < existing_time:
            self.m59_map[from_rid]["connections"][conn_key] = duration
            updated = True
            self.save_map_data()
            
        return updated, duration, existing_time

    def process_room_update(self, current_room):
        """Detects changes and records data based on RIDs. Returns (was_transition, log_msg)"""
        if current_room == "Unknown Location":
            return False, None

        now = time.time()
        was_transition = False
        log_msg = None
        
        # Resolve current RID
        current_rid = self.resolve_name_to_rid(current_room)

        if current_room != self.last_room:
            if self.last_room is not None and hasattr(self, 'last_known_from_rid') and self.last_known_from_rid:
                duration = round(now - self.transition_start_time, 2)
                # Only record if it's a plausible transition (under 2 minutes)
                if duration < 120:
                    improved, dur, old = self.record_transition(self.last_known_from_rid, current_rid, duration)
                    if improved:
                        log_msg = f"New Record! {self.last_room} -> {current_room} in {dur}s"
                    else:
                        log_msg = f"Transition: {self.last_room} -> {current_room} in {dur}s (Best: {old}s)"
                    was_transition = True
            else:
                log_msg = f"GPS Tracking active at: {current_room}"
            
            self.last_room = current_room
            self.last_known_from_rid = current_rid # Store for next update
            self.transition_start_time = now
            
        return was_transition, log_msg
