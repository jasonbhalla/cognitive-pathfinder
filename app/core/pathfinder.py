import networkx as nx
import osmnx as ox

def find_shortest_path(graph, start_coords, end_coords):
    """
    Finds the shortest path between two (lat, lon) tuples using 
    NetworkX's shortest_path algorithm.
    Returns: (path_node_ids, total_length_meters)
    """
    print("Finding nearest nodes in the graph...")
    
    # 1. For the starting and ending coordinates, find the closest graph nodes
    # OSMnx nearest_nodes expects (X, Y) which translates to (Longitude, Latitude)
    # start_coords is (latitude, longitude), which is why we access [1] then [0]
    orig_node = ox.distance.nearest_nodes(graph, start_coords[1], start_coords[0])
    dest_node = ox.distance.nearest_nodes(graph, end_coords[1], end_coords[0])

    print(f"Start Node ID: {orig_node}")
    print(f"End Node ID: {dest_node}")
    
    print("Calculating shortest path...")
    # Dijkstra's Algorithm (or unweighted BFS if weight is None, but here we use length)
    try:
        # 2. Run Dijkstra's Algorithm
        # Returns a list of Node IDs
        path_nodes = nx.shortest_path(graph, source=orig_node, target=dest_node, weight='length')
        
        # 3. Calculate distance (in meters)
        length = nx.path_weight(graph, path_nodes, weight='length')
            
        return path_nodes, length
    except nx.NetworkXNoPath:
        print("No path found between these nodes!")
        return None, 0
    
def get_path_coords(graph, path_nodes):
    """
    Converts a list of Node IDs into a list of [Latitude, Longitude] for plotting.
    """
    coords = []
    for node_id in path_nodes:
        node = graph.nodes[node_id]
        coords.append((node['y'], node['x'])) # Leaflet expects (Lat, Lon)
    return coords
    
    