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

def get_friendly_action(exit_info, data):
    """Creates a human-readable instruction based on exit type and location."""
    dest_name = data.get(exit_info['to_rid'], {}).get('name', "another area")
    
    if exit_info['type'] == 'point':
        direction_hint = get_compass_direction(exit_info['from'])
        return f"Walk to the {direction_hint} and enter the door/gate to reach {dest_name}."
    
    if exit_info['type'] == 'edge':
        direction = exit_info['direction'].replace('LEAVE_', '').title()
        return f"Follow the path out the {direction} side of the room to {dest_name}."
    
    if exit_info['type'] == 'manual':
        # These are the "hidden" ones like the tree hole
        return f"Look for a special entrance (like a hole or a hidden path) to reach {dest_name}."

    return f"Move to {dest_name}."

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
        print("\n--- NEW TRIP ---")
        start_query = input("Where are you now? ").lower().strip()
        if not start_query: break
        
        # Simple name matcher
        start_rid = next((ids[0] for name, ids in name_to_ids.items() if start_query in name), None)
        
        end_query = input("Where do you want to go? ").lower().strip()
        if not end_query: break
        end_rid = next((ids[0] for name, ids in name_to_ids.items() if end_query in name), None)
        
        if not start_rid or not end_rid:
            print("Sorry, I couldn't find those rooms. Try names like 'Tos' or 'Castle Victoria'.")
            continue
            
        print(f"\nGUIDE: Getting you from {data[start_rid]['name']} to {data[end_rid]['name']}...")
        path = find_path(start_rid, end_rid, adj)
        
        if path:
            for i, (rid, exit_info) in enumerate(path):
                print(f"\nSTEP {i+1}: In {data[rid]['name']}...")
                print(f"  -> {get_friendly_action(exit_info, data)}")
            print(f"\nSUCCESS: You have arrived at {data[end_rid]['name']}!")
        else:
            print("\nI'm sorry, I couldn't find a walking path between those places.")

if __name__ == "__main__":
    main()
