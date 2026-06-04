import json
import collections
import sys
from m59_gps import GPSManager

def get_room_selection(query, gps):
    """Handles ambiguous room names by prompting the user for selection."""
    query = query.lower().strip()
    if not gps.dataset: return None
    
    matches = []
    for rid, info in gps.dataset.items():
        if query in info['name'].lower():
            matches.append(rid)
            
    if not matches:
        return None
        
    if len(matches) == 1:
        return matches[0]
        
    print(f"\nMultiple matches for '{query}':")
    for i, rid in enumerate(matches):
        print(f"  {i+1}. {gps.dataset[rid]['name']} ({rid})")
        
    choice = input("Select number (or Enter to cancel): ")
    try:
        return matches[int(choice)-1]
    except:
        return None

def main():
    print("==================================================")
    print("      MERIDIAN 59 GPS CLI (m59_gps-cli)          ")
    print("==================================================")
    
    gps = GPSManager()
    
    while True:
        print("\n" + "="*40)
        start_query = input("Where are you now? ")
        if not start_query: break
        start_rid = get_room_selection(start_query, gps)
        if not start_rid:
            print("Sorry, I couldn't find that room.")
            continue
            
        end_query = input("Where do you want to go? ")
        if not end_query: break
        end_rid = get_room_selection(end_query, gps)
        if not end_rid:
            print("Sorry, I couldn't find that room.")
            continue
            
        print(f"\nGUIDE: Getting you from {gps.dataset[start_rid]['name']} to {gps.dataset[end_rid]['name']}...")
        path = gps.find_path(start_rid, end_rid)
        
        if path:
            total_steps = len(path)
            arrival_pos = gps.dataset.get(start_rid, {}).get('teleport')
            
            for i, (rid, exit_info) in enumerate(path):
                print(f"\nSTEP {i+1}: In {gps.dataset[rid]['name']}...")
                print(f"  -> {gps.get_friendly_instruction(rid, exit_info, step=i+1, total=total_steps, arrival_pos=arrival_pos)}")
                # Next room's arrival point
                arrival_pos = exit_info.get('to_pos')
            print(f"\nSUCCESS: You have arrived at {gps.dataset[end_rid]['name']}!")
        else:
            print("\nI'm sorry, I couldn't find a walking path between those places.")

if __name__ == "__main__":
    main()
