import json
import os

class SchoolCalculator:
    def __init__(self, config_obj, data_path="m59_data.json"):
        # Store the config object to access live settings
        self.config = config_obj 
        self.data_path = data_path

    def load_data(self):
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r") as f:
                    return json.load(f).get("Schools", {})
            except Exception as e:
                print(f">>> [ERROR] Failed to load {self.data_path}: {e}")
        return {}

    def get_school_status(self, live_data, school_name, levels):
        current_lvl = 0
        total_pts = 0
        point_values = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 2}

        for i in range(1, 7):
            lvl_key = f"Level_{i}"
            if lvl_key not in levels:
                continue
            
            skills = [s.lower() for s in levels[lvl_key] if s.lower() != "blink"]
            
            if skills and any(s in live_data for s in skills):
                current_lvl = i
                total_pts += point_values.get(i, 0)
                
        return current_lvl, total_pts

    def calculate_all_unlocks(self, live_data):
        schools = self.load_data()
        results = []
        
        # Pull live calibration values from the config manager
        intellect = self.config.settings["character"]["intellect"]
        max_points = self.config.settings["server"]["max_points"]
        points_slope = self.config.settings["server"]["points_slope"]

        # --- 1. SCHOOL DETECTION ---
        known_schools = []
        for name, levels in schools.items():
            all_skills = [s.lower() for lvl in levels.values() for s in lvl]
            known_count = sum(1 for s in all_skills if s in live_data)
            
            if name == "Riija" and known_count <= 1:
                continue
                
            if known_count > 0:
                known_schools.append(name)

        # --- 2. CALCULATE GLOBAL KNOWLEDGE (iPoints) ---
        total_base_points = 0
        school_lvls = {}
        for name in known_schools:
            lvl, pts = self.get_school_status(live_data, name, schools[name])
            total_base_points += pts
            school_lvls[name] = lvl

        # --- 3. PREDICT NEXT LEVEL REQUIREMENTS ---
        for name in known_schools:
            curr_lvl = school_lvls[name]
            if curr_lvl >= 6: 
                continue
            
            next_lvl = curr_lvl + 1
            point_values = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 2}
            next_lvl_points = point_values.get(next_lvl, 2)
            
            pts_in_formula = total_base_points + next_lvl_points
            
            # CORE FORMULA using config variables
            target_sum = (pts_in_formula * points_slope) + \
                         (297 - (max_points * points_slope)) - \
                         ((intellect * 2 * points_slope) // 5)
            
            if target_sum > 297:
                results.append(f"{name} L{next_lvl}: [Locked - Cap Exceeded]")
                continue

            current_lvl_skills = [s.lower() for s in schools[name].get(f"Level_{curr_lvl}", [])]
            percents = sorted([live_data.get(s, 0) for s in current_lvl_skills], reverse=True)
            
            current_sum = sum(percents[:3])
            needed = max(0, target_sum - current_sum)
            
            results.append(f"{name} L{curr_lvl}: {int(needed)}% total needed for L{next_lvl}")
            
        return results
