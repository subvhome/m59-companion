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
            data_path = resource_path("settings/m59_data.json")
        if config_path is None:
            config_path = resource_path("settings/config.json")
            
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
                config = json.load(f)
                # Ensure we use the correct game defaults if not specified or incorrect
                if config.get("server", {}).get("points_slope") != 7:
                    config.setdefault("server", {})["points_slope"] = 7
                if config.get("server", {}).get("max_points") != 16:
                    config.setdefault("server", {})["max_points"] = 16
                return config
        except:
            # Default fallback matching Meridian 59 1.6.0 source
            return {
                "server": {"max_points": 16, "points_slope": 7},
                "character": {"intellect": 25}
            }

    def _riija_blink_only(self, knowledge_cache, school_data):
        """Riija is excluded from progress when Blink is the only known spell."""
        known = {
            s.lower()
            for lvl in range(1, 7)
            for s in school_data.get(f"Level_{lvl}", [])
            if s.lower() in knowledge_cache
        }
        return known == {"blink"}

    def _level_skills(self, school_data, level, school_name=None):
        skills = [s.lower() for s in school_data.get(f"Level_{level}", [])]
        if school_name == "Riija":
            skills = [s for s in skills if s != "blink"]
        return skills

    def get_school_status(self, school_name, knowledge_cache, levels):
        """Returns (max_level_reached, points_for_max_level)"""
        # Based on system.kod vlLevelPoints = [1, 2, 4, 6, 8, 10]
        point_values = {0: 0, 1: 1, 2: 2, 3: 4, 4: 6, 5: 8, 6: 10}
        if school_name == "Riija" and self._riija_blink_only(knowledge_cache, levels):
            return 0, 0

        max_lvl = 0
        for i in range(6, 0, -1):
            lvl_key = f"Level_{i}"
            if lvl_key not in levels:
                continue

            skills = self._level_skills(levels, i, school_name)
            if any(s in knowledge_cache for s in skills):
                max_lvl = i
                break

        return max_lvl, point_values.get(max_lvl, 0)

    def calculate_progression(self, knowledge_cache, intellect=None):
        """
        The CORE ENGINE: Replicates the original Meridian 59 PlayerCanLearn logic.
        
        FORMULA REFERENCE (DO NOT CHANGE):
        ----------------------------------
        Target Sum (t_sum) is determined by:
        1. iPoints = (Sum of points from all other schools) + (Points for target level of this school)
           Points mapping: L1=1, L2=2, L3=4, L4=6, L5=8, L6=10
        
        2. Base Formula:
           t_sum = (iPoints * points_slope) + (297 - (max_points * points_slope)) - ((intellect * 2.0 * points_slope) / 5.0)
        
        3. Scarcity Adjustment:
           - If target school has only 1 skill in previous level: t_sum = t_sum / 3.0
           - If target school has only 2 skills in previous level: t_sum = (t_sum * 2.0) / 3.0
        
        4. Minimum Cap: t_sum is always at least 75%.
        ----------------------------------
        """
        if intellect is None:
            intellect = self.config.get("character", {}).get("intellect", 25)
            
        max_points = self.config.get("server", {}).get("max_points", 16)
        points_slope = self.config.get("server", {}).get("points_slope", 7)
        
        # --- 1. Identify Active Schools and Calculate Base iPoints ---
        school_stats = {}
        total_base_points = 0
        for name, levels in self.schools.items():
            max_lvl, pts = self.get_school_status(name, knowledge_cache, levels)
            if max_lvl > 0:
                school_stats[name] = max_lvl
                total_base_points += pts

        # --- 2. Calculate Progression for Each School ---
        results = []
        point_values = {0: 0, 1: 1, 2: 2, 3: 4, 4: 6, 5: 8, 6: 10}

        for name, school_data in self.schools.items():
            current_lvl = school_stats.get(name, 0)
            if current_lvl == 0: continue # Skip schools with no progress

            # Handle Mastered Schools (Level 6)
            if current_lvl == 6:
                results.append({
                    'name': name,
                    'current_lvl': 6,
                    'target_lvl': 6,
                    'current_sum': 0,
                    'target_sum': 0,
                    'needed': 0,
                    'mastered': True
                })
                continue

            # Determine the target level we are working towards
            skills_at_lvl = self._level_skills(school_data, current_lvl, name)
            known_at_lvl = sum(1 for s in skills_at_lvl if s in knowledge_cache)

            # Rule: Level > 2 or 2+ skills known means you've "passed" this level.
            # A single L1 spell still means you're at level 1, working toward level 2.
            if current_lvl > 2 or known_at_lvl >= 2:
                target_lvl = current_lvl + 1
            elif current_lvl == 1:
                target_lvl = 2
            else:
                target_lvl = current_lvl

            if target_lvl > 6:
                target_lvl = 6 # Cap at 6

            # --- Calculate iNeed for target_lvl ---
            # iPoints calculation: Sum of other schools' max points + target level's points
            i_points = total_base_points - point_values.get(current_lvl, 0) + point_values.get(target_lvl, 0)
            
            # The Formula from player.kod
            t_sum = (i_points * points_slope) + \
                    (297 - (max_points * points_slope)) - \
                    ((intellect * 2.0 * points_slope) / 5.0)
            
            t_sum = max(75, t_sum)
            
            # Scarcity adjustment
            if target_lvl > 1:
                prev_lvl_skills = self._level_skills(school_data, target_lvl - 1, name)
                num_in_prev = len(prev_lvl_skills)
                if num_in_prev == 1:
                    t_sum = t_sum / 3.0
                elif num_in_prev == 2:
                    t_sum = (t_sum * 2.0) / 3.0
            else:
                t_sum = 297
            
            # --- Calculate iHave (Sum of top 3 of target_lvl - 1) ---
            if target_lvl == 1:
                c_sum = 297
            else:
                prev_lvl_skills = self._level_skills(school_data, target_lvl - 1, name)
                percents = sorted([knowledge_cache.get(s, 0) for s in prev_lvl_skills], reverse=True)
                c_sum = sum(percents[:3])
            
            display_lvl = current_lvl
            if target_lvl <= current_lvl:
                display_lvl = current_lvl - 1

            results.append({
                'name': name,
                'current_lvl': display_lvl,
                'target_lvl': target_lvl,
                'current_sum': int(c_sum),
                'target_sum': int(t_sum),
                'needed': max(0, int(t_sum - c_sum)),
                'mastered': False
            })
        
        return results
        
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
    print("--- M59 Calculator: Source-Synced Logic Test ---")
    print(f"Using Intellect: {calc.config['character']['intellect']}")
    print(f"Server Config: MaxPoints={calc.config['server']['max_points']}, Slope={calc.config['server']['points_slope']}")
    print("-" * 60)
    
    progression = calc.calculate_progression(real_knowledge)
    
    for res in progression:
        if res['needed'] > 0:
            status = f"Current Level: {res['current_lvl']}"
            target = f"Goal: Level {res['target_lvl']}"
            progress = f"Progress: {res['current_sum']}/{res['target_sum']}%"
            needed = f"NEED: {res['needed']}% more"
            print(f" - {res['name']:<15} | {status:<18} | {target:<15} | {progress:<15} | {needed}")
        else:
            print(f" - {res['name']:<15} | Current Level: {res['current_lvl']} (Ready for Level {res['target_lvl']})")

if __name__ == "__main__":
    test_calculator()
