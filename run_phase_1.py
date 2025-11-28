from app.core.graph_builder import get_graph
from app.core.pathfinder import find_shortest_path

# Configuration
PLACE_NAME = "Hoboken, New Jersey, USA"
GRAPH_FILE = "data/processed/hoboken.graphml"

# Test Coordinates (Latitude, Longitude)
# Point A: Hoboken Terminal
START_COORDS = (40.73492, -74.02864)
# Point B: Stevens Institute of Technology
END_COORDS = (40.74328, -74.02761)

def main():
    print("--- Phase 1: The Walking Skeleton ---")
    
    # 1. Load or Download Graph
    graph = get_graph(PLACE_NAME, GRAPH_FILE)
    print(f"Graph successfully loaded with {len(graph.nodes)} nodes and {len(graph.edges)} edges.")
    
    # 2. Run Pathfinder
    path, length = find_shortest_path(graph, START_COORDS, END_COORDS)
    
    # 3. Output Results
    if path:
        print("\n--- Success! ---")
        print(f"Path found involving {len(path)} distinct intersections.")
        print(f"Total Walking Distance: {int(length)} meters")
        print("Route Node IDs:", path)
    else:
        print("Failed to find path.")

if __name__ == "__main__":
    main()