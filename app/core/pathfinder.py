import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

def get_nearest_node(graph, point, layer='walking'):
    """
    Finds the nearest node in a specific layer using a KDTree.
    Bypasses osmnx to avoid integer casting errors with hybrid IDs.
    
    :param graph: The graph
    :param point: Tuple (lat, lon)
    :param layer: 'walking' or 'transit'
    """
    lat, lon = point
    
    # 1. Extract Candidate Nodes (Filter by layer)
    # We only want to snap the user to the STREET grid, not the subway tracks.
    candidates = [
        (n, data['x'], data['y']) 
        for n, data in graph.nodes(data=True) 
        if data.get('layer') == layer
    ]
    
    if not candidates:
        raise Exception(f"No nodes found in layer '{layer}'")

    # 2. Build Spatial Index (KDTree)
    node_ids, xs, ys = zip(*candidates)
    
    # Stack coordinates for the tree (x=lon, y=lat)
    tree_data = np.column_stack((xs, ys))
    tree = cKDTree(tree_data)
    
    # 3. Query Nearest Point
    # k=1 returns (distance, index)
    dist, idx = tree.query([lon, lat], k=1)
    
    # 4. Return the ID
    return node_ids[idx]


def find_shortest_path(graph, start_coords, end_coords):
    """
    Calculates the shortest path using Dijkstra's algorithm.
    :param graph: The MultiDiGraph (fused).
    :param start_coords: (lat, lon) tuple.
    :param end_coords: (lat, lon) tuple.
    :return: List of node IDs representing the path, Total Time (minutes).
    """
    try:
        # 1. Find nearest WALKING nodes using our robust function
        orig = get_nearest_node(graph, start_coords, layer='walking')
        dest = get_nearest_node(graph, end_coords, layer='walking')
        
        # 2. Run Dijkstra
        path_nodes = nx.shortest_path(graph, orig, dest, weight=get_weight)
        
        # 3. Calculate Total Time
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
    mode = data.get('layer', 'walking') # Use 'layer' as mode fallback
    
    # 1. Transit Edge (Time is pre-calculated in GTFS)
    if mode == 'transit':
        return float(data.get('time', 0))
    
    # 2. Transfer Edge (Fixed penalty for now)
    if mode == 'connector':
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
                # Fallback if geometry is still a string
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                coords = [(n1['y'], n1['x']), (n2['y'], n2['x'])]
        else:
            # Straight line for synthetic edges
            n1 = graph.nodes[u]
            n2 = graph.nodes[v]
            coords = [(n1['y'], n1['x']), (n2['y'], n2['x'])]
            
        # Color coding based on layer
        color = '#3388ff' # Default Walk
        layer = data.get('layer', 'walking')
        
        if layer == 'transit': color = '#ff3333'
        elif layer == 'connector': color = '#000000'
            
        segments.append({
            "coords": coords,
            "color": color,
            "mode": layer
        })
        
    return segments