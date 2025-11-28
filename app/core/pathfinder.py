import networkx as nx
import osmnx as ox

def find_shortest_path(graph, start_coords, end_coords):
    """
    Finds the shortest path between two (lat, lon) tuples using 
    NetworkX's shortest_path algorithm.
    """
    print("Finding nearest nodes in the graph...")
    
    # OSMnx nearest_nodes expects (X, Y) which translates to (Longitude, Latitude)
    # start_coords is (latitude, longitude), which is why we access [1] then [0]
    orig_node = ox.distance.nearest_nodes(graph, start_coords[1], start_coords[0])
    dest_node = ox.distance.nearest_nodes(graph, end_coords[1], end_coords[0])

    print(f"Start Node ID: {orig_node}")
    print(f"End Node ID: {dest_node}")
    
    print("Calculating shortest path...")
    # Dijkstra's Algorithm (or unweighted BFS if weight is None, but here we use length)
    try:
        # Returns a list of Node IDs
        path_nodes = nx.shortest_path(graph, source=orig_node, target=dest_node, weight='length')
        
        # Calculate total length (in meters)
        total_length = 0
        for u, v in zip(path_nodes[:-1], path_nodes[1:]):
            # Access the edge data between node u and v
            # Since it's a MultiDiGraph, 0 is the key for the first edge
            edge_data = graph[u][v][0] 
            total_length += edge_data.get('length', 0)
            
        return path_nodes, total_length

    except nx.NetworkXNoPath:
        print("No path found between these nodes!")
        return None, 0