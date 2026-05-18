import os
import json
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class SchoolCalculator:
    def __init__(self, data_path=None, config_path=None):
        if data_path is None:
            data_path = resource_path("m59_data.json")
        if config_path is None:
            config_path = resource_path("config.json")
            
        self.data_path = data_path
        self.config_path = config_path
        self.schools = self._load_data()
        self.config = self._load_config()

    def _load_data(self):
        try:
            with open(self.data_path, "r") as f:
                data = json.load(f)
                return data.get("Schools", data)
        except Exception as e:
            print(f"CALC ERROR: Could not load data: {e}")
            return {}

    def _load_config(self):
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except:
            # Default fallback if config is missing
            return {
                "server": {"max_points": 25, "points_slope": 6},
                "character": {"intellect": 20}
            }

    def get_school_status(self, live_data, levels):
        """Determines the player's current level and internal point weight (iPoints) for a school."""
        current_lvl = 0
        total_pts = 0
        # Global iPoint System: L1,2 = 1pt, L3,4,5,6 = 2pts
        point_values = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 2}
        
        for i in range(1, 7):
            lvl_key = f"Level_{i}"
            if lvl_key not in levels: continue
            
            skills = [s.lower() for s in levels[lvl_key] if s.lower() != "blink"]
            # If the player knows any skill in this level, they are considered that level
            if skills and any(s in live_data for s in skills):
                current_lvl = i
                total_pts += point_values.get(i, 0)
                
        return current_lvl, total_pts

    def calculate_progression(self, knowledge_cache, intellect=None):
        """
        The CORE ENGINE: Replicates the original calibrated progression formula.
        """
        # Use provided intellect or fall back to config
        if intellect is None:
            intellect = self.config.get("character", {}).get("intellect", 20)
            
        max_points = self.config.get("server", {}).get("max_points", 25)
        points_slope = self.config.get("server", {}).get("points_slope", 6)
        
        # --- 1. Identify Active Schools ---
        known_schools = []
        for name, levels in self.schools.items():
            all_skills = [s.lower() for lvl in levels.values() for s in lvl]
            known_count = sum(1 for s in all_skills if s in knowledge_cache)
            
            if name == "Riija" and known_count <= 1: continue
            if known_count > 0: known_schools.append(name)
        
        # --- 2. Calculate Global Knowledge (Total iPoints) ---
        total_base_points = 0
        for name in known_schools:
            _, pts = self.get_school_status(knowledge_cache, self.schools[name])
            total_base_points += pts
            
        # --- 3. Predict Next Level Requirements ---
        results = []
        point_values = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 2}

        for name in known_schools:
            school_data = self.schools[name]
            target_lvl = None
            target_lvl_data = None
            
            for i in range(1, 6):
                # Calculate required sum for level i -> i+1
                next_lvl_points = point_values.get(i + 1, 2)
                pts_in_formula = total_base_points + next_lvl_points
                
                # THE CALIBRATED FORMULA
                t_sum = (pts_in_formula * points_slope) + \
                        (297 - (max_points * points_slope)) - \
                        ((intellect * 2.0 * points_slope) / 5.0)
                
                # Check current sum of top 3 for level i
                lvl_skills = [s.lower() for s in school_data.get(f"Level_{i}", [])]
                percents = sorted([knowledge_cache.get(s, 0) for s in lvl_skills], reverse=True)
                c_sum = sum(percents[:3])
                
                if c_sum < t_sum:
                    target_lvl = i
                    target_lvl_data = (c_sum, t_sum)
                    break
            
            if target_lvl:
                c_sum, t_sum = target_lvl_data
                results.append({
                    'name': name,
                    'current_lvl': target_lvl,
                    'current_sum': int(c_sum),
                    'target_sum': int(t_sum),
                    'needed': max(0, int(t_sum - c_sum))
                })
        
        return results

def test_calculator():
    # REAL DATA from recent scraper
    real_knowledge = {
        "axe wielding": 52, "blink": 9, "block": 99, "brawling": 42,
        "dodge": 99, "fencing": 19, "glow": 19, "hammer wielding": 34,
        "mace fighting": 65, "punch": 73, "short sword fighting": 43,
        "slash": 65, "super strength": 29
    }
    
    calc = SchoolCalculator()
    print("--- M59 Calculator: Calibrated Formula Test ---")
    print(f"Using Intellect: {calc.config['character']['intellect']}")
    print(f"Server Config: MaxPoints={calc.config['server']['max_points']}, Slope={calc.config['server']['points_slope']}")
    print("-" * 50)
    
    progression = calc.calculate_progression(real_knowledge)
    
    for res in progression:
        status = f"L{res['current_lvl']} ({res['current_sum']}/{res['target_sum']}%)"
        needed = f"Next: {res['needed']}% needed"
        print(f" - {res['name']:<15}: {status:<15} | {needed}")

if __name__ == "__main__":
    test_calculator()
