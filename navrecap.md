# Meridian 59 Navigator - Project Recap

This document outlines the architecture, scripts, and logic used for the Meridian 59 Pathfinder and Navigator system.

## 1. Room Extraction (`extract_rooms.py`)
This script parses the `.kod` source files to build a navigational graph.
- **Directory Traversal:** Uses `os.walk` to recursively scan all subdirectories in `kod/object/active/holder/room/`.
- **Filtering:** 
    - Excludes rooms without a defined `RID_...` (filters out template/base classes).
    - Excludes rooms that result in 0 total exits (ghost/inaccessible rooms).
- **Naming Logic:** 
    - Prioritizes `vrName` from `classvars` and resolves the corresponding resource string.
    - Falls back to existing regex patterns, then the class name.
- **Exit Extraction:**
    - **Standard Exits:** Parses `plExits` and `plEdge_Exits`.
    - **Manual Exit Extraction:**
        - Uses regex to find `FindRoomByNum` calls within `SomethingMoved` and other methods. Handles coordinate triggers (`new_row`, `new_col`) and range checks (`if row < 32`).
        - **Multiple Manual Exits:** Now supports extracting multiple distinct manual exits to the same destination if they have different start coordinates (e.g., the two holes in Spider Nest).
        - **One-Way Overrides:** Implemented a blacklist in `extract_rooms.py` to remove technically existing but player-impossible transitions (e.g., the direct "low area" entrance to Winding Caverns from Cragged Mountains).
        - **Puzzle Transitions:** Manually injected transitions for complex puzzles (e.g., the Lever Puzzle in `RID_G9`) to enable one-way paths that require specific player actions.
        - **Object Teleporters:** Detects `Create(&SpiderTree)` and `Create(&Portal)` objects and links them to their destination RIDs.

        ## 2. Dataset (`meridian_rooms_dataset.json`)
        The output of `extract_rooms.py`, containing:
        - **`name`:** Player-friendly room name.
        - **`rid_num`:** Integer ID from `blakston.khd`.
        - **`exits`:** A list of transitions (type `point`, `edge`, or `manual`).

        ## 3. Pathfinder (`m59_pathfinder.py`)
        - Used for finding the shortest path (in terms of number of rooms).
        - **Graph Building:** Deduplicates exits to the same destination to prevent redundant, coordinate-based path options.
        - **Algorithm:** Standard BFS (Breadth-First Search).

        ## 4. Navigator (`m59_navigator.py`)
        - **Player-Friendly Output:** Translates `[Row, Col]` coordinates into relative compass directions (e.g., "North-West area").
        - **Action Descriptions:** Translates technical code (e.g., `Walk to [47, 14]`) into player instructions (e.g., "Find the Web Covered Tree in the South-West area").
        - **Custom Instructions:** Supports hardcoded descriptive overrides for complex transitions (e.g., "Trigger the lever puzzle to raise the platform, allowing you to reach the ledge and enter Winding Caverns").
        - **Selection Logic:** Prompts the user to select from a list of matches when the input is ambiguous (e.g., "Tos" matches multiple locations).

        ## 5. Current State of Brax Navigation
        - **Resolved:** The "Decaying City of Brax" pathfinding issue is solved. The navigator now correctly routes players through the `RID_G9` puzzle to reach the ledge in `RID_G8`. 
        - **One-Way Paths:** The system correctly handles one-way drops in `Cragged Mountains`, `Ukgoth`, and the `Spider Nest`.

