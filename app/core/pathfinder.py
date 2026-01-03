import networkx as nx
import osmnx as ox

def find_shortest_path(graph, start_coords, end_coords):
    """
    Calculates the shortest path using Dijkstra's algorithm.
    :param graph: The MultiDiGraph (fused).
    :param start_coords: (lat, lon) tuple.
    :param end_coords: (lat, lon) tuple.
    :return: List of node IDs representing the path, Total Time (minutes).
    """
    try:
        # 1. Find nearest nodes (returns Integer IDs from spatial index)
        #    Note: ox.nearest_nodes expects (X, Y) which is (Lon, Lat)
        orig_raw = ox.distance.nearest_nodes(graph, start_coords[1], start_coords[0])
        dest_raw = ox.distance.nearest_nodes(graph, end_coords[1], end_coords[0])
        
        # 2. CRITICAL FIX: Cast to String to match Graph keys
        orig = str(orig_raw)
        dest = str(dest_raw)
        
        # 3. Run Dijkstra
        path_nodes = nx.shortest_path(graph, orig, dest, weight=get_weight)
        
        # 4. Calculate Total Time
        total_time = 0
        for i in range(len(path_nodes) - 1):
            u = path_nodes[i]
            v = path_nodes[i+1]
            edges = graph.get_edge_data(u, v)
            
            # Find the edge used (lowest weight)
            best_edge = min(edges.values(), key=lambda x: get_weight(u, v, x))
            total_time += get_weight(u, v, best_edge)
            
        return path_nodes, total_time

    except nx.NetworkXNoPath:
        return None, 0
    except Exception as e:
        print(f"Pathfinding critical failure: {e}")
        raise e

def get_weight(u, v, data):
    """
    Custom weight function for Dijkstra.
    Returns TIME in minutes.
    """
    mode = data.get('mode', 'walking')
    
    # 1. Transit Edge (Time is pre-calculated in GTFS)
    if mode == 'transit':
        return float(data.get('time', 0))
    
    # 2. Transfer Edge (Fixed penalty)
    if mode == 'transfer':
        return float(data.get('time', 2.0))
        
    # 3. Walking Edge (Calculate time based on length)
    try:
        length = float(data.get('length', 0))
    except (ValueError, TypeError):
        length = 0.0
    
    # Walking speed: ~1.4 m/s (approx 5 km/h or 3.1 mph)
    # Time (min) = Length (m) / Speed (m/min)
    # Speed (m/min) = 1.4 * 60 = 84 meters/min
    return length / 84.0

def get_path_segments(graph, path_nodes):
    """
    Converts a list of Node IDs into coordinate segments for the frontend.
    """
    segments = []
    
    for i in range(len(path_nodes) - 1):
        u = path_nodes[i]
        v = path_nodes[i+1]
        
        # Get edge data
        edges = graph.get_edge_data(u, v)
        # Grab the best edge (min weight)
        data = min(edges.values(), key=lambda x: get_weight(u, v, x))
        
        coords = []
        if 'geometry' in data:
            # Use real street geometry if available
            try:
                coords = [(p[1], p[0]) for p in data['geometry'].coords]
            except AttributeError:
                # Fallback if geometry is still a string (shouldn't happen with sanitizer)
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                coords = [(n1['y'], n1['x']), (n2['y'], n2['x'])]
        else:
            # Straight line for synthetic edges
            n1 = graph.nodes[u]
            n2 = graph.nodes[v]
            coords = [(n1['y'], n1['x']), (n2['y'], n2['x'])]
            
        segments.append({
            "coords": coords,
            "color": data.get('color', '#3388ff'),
            "mode": data.get('mode', 'walking')
        })
        
    return segments