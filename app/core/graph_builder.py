import os
import osmnx as ox

def get_graph(place_name, filepath):
    """
    Checks if a graph file exists. If yes, loads it.
    If no, downloads it from OSM, saves it, and returns it.
    """
    if os.path.exists(filepath):
        print(f"Loading graph from {filepath}...")
        # Load the graph from the GraphML file
        graph = ox.load_graphml(filepath)
    else:
        print(f"Graph file not found. Downloading {place_name} from OSM...")
        # Download the walking network (streets + paths)
        graph = ox.graph_from_place(place_name, network_type='walk')
        
        print(f"Saving graph to {filepath}...")
        ox.save_graphml(graph, filepath)
        
    return graph