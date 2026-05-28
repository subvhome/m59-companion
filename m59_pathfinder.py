import json
import collections
import sys
import heapq

def load_data(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def build_graph(data):
    adj = collections.defaultdict(list)
    name_to_ids = collections.defaultdict(list)
    
    for rid, info in data.items():
        name_to_ids[info['name'].lower()].append(rid)
        
        # Deduplicate exits to the same destination room
        # This prevents redundant "Option 1, 2, 3" that only differ by which coordinate of a wide door you hit.
        seen_destinations = set()
        for exit in info['exits']:
            dest_rid = exit['to_rid']
            if dest_rid not in seen_destinations:
                adj[rid].append(exit)
                seen_destinations.add(dest_rid)
            
    return adj, name_to_ids

def find_k_shortest_paths(start_rid, end_rid, adj, k=3):
    """
    Finds up to k shortest paths using a modified BFS/Dijkstra approach.
    Since all edges have weight 1, BFS finds the shortest, but we want multiple.
    """
    # paths will store list of (current_rid, path_list)
    # path_list is a list of (rid, exit)
    queue = collections.deque([(start_rid, [])])
    
    results = []
    # Track how many times we've visited each node to allow for multiple paths
    # but avoid infinite loops
    visit_counts = collections.defaultdict(int)
    
    while queue and len(results) < k:
        current_rid, path = queue.popleft()
        
        # If we reached the destination, record this path
        if current_rid == end_rid:
            results.append(path)
            continue
            
        # Limit visits to prevent explosion, but allow enough for alternatives
        if visit_counts[current_rid] >= k:
            continue
        visit_counts[current_rid] += 1
            
        for exit in adj.get(current_rid, []):
            dest_rid = exit['to_rid']
            
            # Avoid simple backtracking in the current path
            if any(p[0] == dest_rid for p in path):
                continue
                
            new_path = path + [(current_rid, exit)]
            queue.append((dest_rid, new_path))
                
    return results

def get_room_id(query, name_to_ids, data):
    query = query.lower().strip()
    
    if query in name_to_ids:
        ids = name_to_ids[query]
        if len(ids) == 1:
            return ids[0]
        else:
            print(f"Multiple rooms found for '{query}':")
            for i, rid in enumerate(ids):
                print(f"  {i+1}. {rid} ({data[rid]['file']})")
            choice = input("Select number: ")
            try:
                return ids[int(choice)-1]
            except:
                return None
                
    matches = []
    for name in name_to_ids:
        if query in name:
            matches.append(name)
            
    if not matches:
        if query.upper() in data:
            return query.upper()
        return None
        
    if len(matches) == 1:
        return name_to_ids[matches[0]][0]
    
    print(f"Multiple matches for '{query}':")
    options = []
    for m in matches:
        for rid in name_to_ids[m]:
            options.append(rid)
            
    for i, rid in enumerate(options):
        print(f"  {i+1}. {data[rid]['name']} ({rid})")
        
    choice = input("Select number (or Enter to cancel): ")
    try:
        return options[int(choice)-1]
    except:
        return None

def display_path(path, data, end_rid):
    for i, (rid, exit) in enumerate(path):
        current_name = data[rid]['name']
        dest_rid = exit['to_rid']
        dest_name = data.get(dest_rid, {}).get('name', dest_rid)
        
        if exit['type'] == 'point':
            method = f"Walk to coordinates {exit['from']} and enter."
        elif exit['type'] == 'edge':
            method = f"Leave via {exit['direction'].replace('LEAVE_', '').title()} edge."
        else:
            method = "Find the exit (Manual/Special)."
            
        print(f"   {i+1}. {current_name} -> {dest_name}")
        print(f"      Action: {method}")
    
    print(f"   Arrived at: {data[end_rid]['name']}")

def main():
    print("--- Meridian 59 Pathfinding Tool (Multi-Route) ---")
    dataset_file = "meridian_rooms_dataset.json"
    
    try:
        data = load_data(dataset_file)
    except FileNotFoundError:
        print(f"Error: {dataset_file} not found.")
        return

    adj, name_to_ids = build_graph(data)
    
    while True:
        print("\n" + "="*40)
        start_query = input("Enter Starting Room: ")
        if not start_query: break
        start_rid = get_room_id(start_query, name_to_ids, data)
        if not start_rid:
            print("Room not found.")
            continue
            
        end_query = input("Enter Destination Room: ")
        if not end_query: break
        end_rid = get_room_id(end_query, name_to_ids, data)
        if not end_rid:
            print("Room not found.")
            continue
            
        print(f"\nSearching for paths from {data[start_rid]['name']} to {data[end_rid]['name']}...")
        paths = find_k_shortest_paths(start_rid, end_rid, adj, k=3)
        
        if paths:
            print(f"\nFound {len(paths)} suggested route(s):")
            for idx, path in enumerate(paths):
                print(f"\n[OPTION {idx+1}] - {len(path)} transitions")
                display_path(path, data, end_rid)
        else:
            print("No path found between these rooms.")

if __name__ == "__main__":
    main()
