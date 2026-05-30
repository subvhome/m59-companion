import json
import collections

def load_data(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def get_compass_direction(pos):
    """Translates [Row, Col] into a player-friendly compass direction."""
    row, col = pos
    if row is None or col is None:
        return "somewhere in the room"
    
    # Assuming standard 64x64 room size for hint logic
    vertical = ""
    if row < 22: vertical = "North"
    elif row > 42: vertical = "South"
    
    horizontal = ""
    if col < 22: horizontal = "West"
    elif col > 42: horizontal = "East"
    
    direction = f"{vertical}-{horizontal}".strip("-")
    if not direction:
        return "the Center"
    return f"the {direction} area"

def get_friendly_action(from_rid, exit_info, data):
    """Creates a human-readable instruction based on exit type and location."""
    from_pos = exit_info.get('from', [None, None])
    to_rid = exit_info['to_rid']
    dest_name = data.get(to_rid, {}).get('name', "another area")
    
    # Custom Overrides for complex/hidden paths
    # Key: (From_RID, To_RID, Row, Col)
    CUSTOM_INSTRUCTIONS = {
        ("RID_NEST1", "RID_CAVE2", 2, 19): "Walk to the Northern point, move slightly East and fall into the hole to reach A Deep, Dark, Spooky, Icky Cave.",
        ("RID_NEST1", "RID_CAVE2", 26, 14): "Find the hole in the West area and drop down to reach A Deep, Dark, Spooky, Icky Cave.",
        ("RID_G9", "RID_NECROAREA1", None, None): "Trigger the lever puzzle to raise the platform, allowing you to reach the ledge and enter Winding Caverns.",
    }

    # Search for a custom override
    row, col = from_pos
    if (from_rid, to_rid, row, col) in CUSTOM_INSTRUCTIONS:
        return CUSTOM_INSTRUCTIONS[(from_rid, to_rid, row, col)]

    direction_hint = get_compass_direction(from_pos)
    obj_name = exit_info.get('object', 'entrance')
    if obj_name == 'SpiderTree': obj_name = 'Web Covered Tree'
    elif obj_name == 'Portal': obj_name = 'Portal'

    if exit_info['type'] == 'point':
        return f"Walk to the {direction_hint} and enter the {obj_name} to reach {dest_name}."
    
    if exit_info['type'] == 'edge':
        direction = exit_info['direction'].replace('LEAVE_', '').title()
        return f"Follow the path out the {direction} side of the room to {dest_name}."
    
    if exit_info['type'] == 'manual':
        # These are the "hidden" ones like the tree hole or region triggers
        if exit_info.get('from'):
             # If it's a manual exit with coordinates but no object, 
             # it's likely a region trigger (like walking off a map edge).
             if obj_name == 'entrance':
                 return f"Walk to the {direction_hint} to reach {dest_name}."
             return f"Find the hidden {obj_name} in the {direction_hint} area and enter to reach {dest_name}."
        return f"Look for a special entrance (like a hole or a hidden path) to reach {dest_name}."

    return f"Move to {dest_name}."

def get_room_selection(query, name_to_ids, data):
    """Handles ambiguous room names by prompting the user for selection."""
    query = query.lower().strip()
    matches = []
    for name in name_to_ids:
        if query in name:
            matches.append(name)
            
    if not matches:
        return None
        
    options = []
    for m in matches:
        for rid in name_to_ids[m]:
            options.append(rid)
            
    if len(options) == 1:
        return options[0]
        
    print(f"\nMultiple matches for '{query}':")
    for i, rid in enumerate(options):
        print(f"  {i+1}. {data[rid]['name']} ({rid})")
        
    choice = input("Select number (or Enter to cancel): ")
    try:
        return options[int(choice)-1]
    except:
        return None

def build_graph(data):
    adj = collections.defaultdict(list)
    name_to_ids = collections.defaultdict(list)
    for rid, info in data.items():
        name_to_ids[info['name'].lower()].append(rid)
        seen = set()
        for exit in info['exits']:
            if exit['to_rid'] not in seen:
                adj[rid].append(exit)
                seen.add(exit['to_rid'])
    return adj, name_to_ids

def find_path(start_rid, end_rid, adj):
    queue = collections.deque([(start_rid, [])])
    visited = {start_rid}
    while queue:
        curr, path = queue.popleft()
        if curr == end_rid:
            return path
        for exit in adj.get(curr, []):
            if exit['to_rid'] not in visited:
                visited.add(exit['to_rid'])
                queue.append((exit['to_rid'], path + [(curr, exit)]))
    return None

def main():
    print("==================================================")
    print("      MERIDIAN 59 PLAYER NAVIGATOR (BETA)        ")
    print("==================================================")
    
    data = load_data("meridian_rooms_dataset.json")
    adj, name_to_ids = build_graph(data)
    
    while True:
        print("\n" + "="*40)
        start_query = input("Where are you now? ")
        if not start_query: break
        start_rid = get_room_selection(start_query, name_to_ids, data)
        if not start_rid:
            print("Sorry, I couldn't find that room.")
            continue
            
        end_query = input("Where do you want to go? ")
        if not end_query: break
        end_rid = get_room_selection(end_query, name_to_ids, data)
        if not end_rid:
            print("Sorry, I couldn't find that room.")
            continue
            
        print(f"\nGUIDE: Getting you from {data[start_rid]['name']} to {data[end_rid]['name']}...")
        path = find_path(start_rid, end_rid, adj)
        
        if path:
            for i, (rid, exit_info) in enumerate(path):
                print(f"\nSTEP {i+1}: In {data[rid]['name']}...")
                print(f"  -> {get_friendly_action(rid, exit_info, data)}")
            print(f"\nSUCCESS: You have arrived at {data[end_rid]['name']}!")
        else:
            print("\nI'm sorry, I couldn't find a walking path between those places.")

if __name__ == "__main__":
    main()
