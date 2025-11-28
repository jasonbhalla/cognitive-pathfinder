import os
import re
import osmnx as ox

def get_graph(place_name):
    """
    Downloads graph for a place_name and caches it.
    Generates a filename automatically from the place name.
    """
    # Create a safe filename (e.g., "New York, NY" -> "new_york_ny.graphml")
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', place_name.lower())
    filename = f"{safe_name}.graphml"
    folder = "data/processed"
    filepath = os.path.join(folder, filename)

    # Ensure folder exists
    os.makedirs(folder, exist_ok=True)

    if os.path.exists(filepath):
        print(f"Loading cached graph for {place_name}...")
        return ox.load_graphml(filepath)
    else:
        print(f"Downloading graph for {place_name} (this may take time)...")
        # Simplify=True removes curvy geometry nodes to make the graph smaller/faster
        graph = ox.graph_from_place(place_name, network_type='walk')
        print(f"Saving to {filepath}...")
        ox.save_graphml(graph, filepath)
        return graph