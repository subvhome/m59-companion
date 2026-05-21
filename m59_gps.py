import os
import json
import time
from datetime import datetime

class GPSManager:
    def __init__(self, map_path="m59_map.json"):
        self.map_path = map_path
        self.m59_map = self.load_map_data()
        self.last_room = None
        self.transition_start_time = 0

    def load_map_data(self):
        """Loads the discovered room data from JSON."""
        if os.path.exists(self.map_path):
            try:
                with open(self.map_path, "r") as f:
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

    def record_transition(self, from_room, to_room, duration):
        """Updates the map data with a new room connection and time."""
        if from_room not in self.m59_map:
            self.m59_map[from_room] = {"connections": {}}
        
        # Default direction until advanced detection is added
        direction = "Unknown" 
        
        # Use a consistent key format for the connection
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
