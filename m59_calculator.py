import json
import os
import logging
# Setup module-level logger
logger = logging.getLogger("m59.calculator")
class SchoolCalculator:
    def __init__(self, config_obj, data_path="m59_data.json"):
        # Store the config object to access live settings
        self.config = config_obj 
        self.data_path = data_path
        logger.info(f"SchoolCalculator initialized with data: {self.data_path}")
    def load_data(self):
        """Loads the school/skill definitions from the JSON data file."""
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r") as f:
                    data = json.load(f).get("Schools", {})
                    logger.debug(f"Loaded {len(data)} schools from {self.data_path}")
                    return data
            except Exception as e:
                logger.error(f"Failed to load {self.data_path}: {e}")
        else:
            logger.warning(f"Data file {self.data_path} not found.")
        return {}
    def get_school_status(self, live_data, school_name, levels):
        """Determines the player's current level and internal point weight for a school."""
        current_lvl = 0
        total_pts = 0
        point_values = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 2}
        for i in range(1, 7):
            lvl_key = f"Level_{i}"
            if lvl_key not in levels:
                continue
            
            skills = [s.lower() for s in levels[lvl_key] if s.lower() != "blink"]
            
            # If the player knows any skill in this level, they are considered that level
            if skills and any(s in live_data for s in skills):
                current_lvl = i
                total_pts += point_values.get(i, 0)
                
        logger.debug(f"Status for {school_name}: Level {current_lvl}, Base Points: {total_pts}")
        return current_lvl, total_pts
    def calculate_all_unlocks(self, live_data):
        """The core engine: predicts how much training is needed for the next level."""
        schools = self.load_data()
        results = []
        
        # Pull live calibration values from the config manager
        intellect = self.config.settings["character"]["intellect"]
        max_points = self.config.settings["server"]["max_points"]
        points_slope = self.config.settings["server"]["points_slope"]
        
        logger.debug(f"Calc Context: Intellect={intellect}, MaxPts={max_points}, Slope={points_slope}")
        # --- 1. SCHOOL DETECTION ---
        known_schools = []
        for name, levels in schools.items():
            all_skills = [s.lower() for lvl in levels.values() for s in lvl]
            known_count = sum(1 for s in all_skills if s in live_data)
            
            # Riija logic: Needs more than 1 skill to be considered 'active' (to ignore Blink)
            if name == "Riija" and known_count <= 1:
                continue
                
            if known_count > 0:
                known_schools.append(name)
        
        logger.info(f"Active schools detected: {known_schools}")
        # --- 2. CALCULATE GLOBAL KNOWLEDGE (iPoints) ---
        total_base_points = 0
        school_lvls = {}
        for name in known_schools:
            lvl, pts = self.get_school_status(live_data, name, schools[name])
            total_base_points += pts
            school_lvls[name] = lvl
        logger.debug(f"Total global base points calculated: {total_base_points}")
        # --- 3. PREDICT NEXT LEVEL REQUIREMENTS ---
        for name in known_schools:
            curr_lvl = school_lvls[name]
            if curr_lvl >= 6: 
                logger.debug(f"{name} is already max level (6). Skipping.")
                continue
            
            next_lvl = curr_lvl + 1
            point_values = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 2}
            next_lvl_points = point_values.get(next_lvl, 2)
            
            # Predict the iPoint total if the player gained the next level
            pts_in_formula = total_base_points + next_lvl_points
            
            # CORE FORMULA: Calculates the required sum of the top 3 skills
            target_sum = (pts_in_formula * points_slope) + \
                         (297 - (max_points * points_slope)) - \
                         ((intellect * 2 * points_slope) // 5)
            
            logger.debug(f"{name} L{next_lvl} calculation: TargetSum={target_sum} based on {pts_in_formula} projected iPoints")
            
            if target_sum > 297:
                logger.warning(f"{name} L{next_lvl} is unreachable: TargetSum {target_sum} > 297")
                results.append(f"{name} L{next_lvl}: [Locked - Cap Exceeded]")
                continue
            # Check current percentages of skills in the current level
            current_lvl_skills = [s.lower() for s in schools[name].get(f"Level_{curr_lvl}", [])]
            percents = sorted([live_data.get(s, 0) for s in current_lvl_skills], reverse=True)
            
            # Sum the top 3 highest skills in that level
            current_sum = sum(percents[:3])
            needed = max(0, target_sum - current_sum)
            
            logger.debug(f"{name} Progress: Top3 Sum={current_sum}, Goal={target_sum}, Remaining={needed}")
            results.append({
                'name': name,
                'current_lvl': curr_lvl,
                'current_sum': current_sum,
                'target_sum': target_sum,
                'needed': needed
            })
            
        return results
