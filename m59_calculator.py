import json
import os
import logging
from utils import resource_path

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
        res_data_path = resource_path(self.data_path)
        if os.path.exists(res_data_path):
            try:
                with open(res_data_path, "r") as f:
                    data = json.load(f).get("Schools", {})
                    logger.debug(f"Loaded {len(data)} schools from {res_data_path}")
                    return data
            except Exception as e:
                logger.error(f"Failed to load {res_data_path}: {e}")
        else:
            logger.warning(f"Data file {res_data_path} not found.")
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
            school_data = schools[name]
            # Find the lowest level that doesn't meet its target sum yet
            # This handles characters who skip levels during creation
            target_lvl = None
            target_lvl_data = None
            
            for i in range(1, 6):
                # Calculate target sum for level i -> i+1
                point_values = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 2}
                next_lvl_points = point_values.get(i + 1, 2)
                pts_in_formula = total_base_points + next_lvl_points
                
                # Check how much iPoints we currently have for THIS specific school detection
                # We use the current level for total_base_points, but if we haven't reached i,
                # we adjust the calculation to be based on the jump TO i+1.
                
                t_sum = (pts_in_formula * points_slope) + \
                        (297 - (max_points * points_slope)) - \
                        ((intellect * 2 * points_slope) // 5)
                
                # Check current sum of top 3 for level i
                lvl_skills = [s.lower() for s in school_data.get(f"Level_{i}", [])]
                percents = sorted([live_data.get(s, 0) for s in lvl_skills], reverse=True)
                c_sum = sum(percents[:3])
                
                if c_sum < t_sum:
                    target_lvl = i
                    target_lvl_data = (c_sum, t_sum)
                    break
            
            if target_lvl:
                c_sum, t_sum = target_lvl_data
                needed = max(0, t_sum - c_sum)
                
                logger.debug(f"{name} L{target_lvl}->L{target_lvl+1} Progress: Top3 Sum={c_sum}, Goal={t_sum}, Remaining={needed}")
                results.append({
                    'name': name,
                    'current_lvl': target_lvl,
                    'current_sum': c_sum,
                    'target_sum': t_sum,
                    'needed': needed
                })
            else:
                logger.debug(f"{name} is fully trained or at max level. Skipping.")
            
        return results
