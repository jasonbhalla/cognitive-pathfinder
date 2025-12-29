import networkx as nx
import osmnx as ox
import logging

logger = logging.getLogger(__name__)

def find_shortest_path(graph, start_coords, end_coords):
    logger.info(f"Snapping coords {start_coords} -> {end_coords}")
    
    # 1. Snap Lat/Lon
    # Note: ox.distance.nearest_nodes might return an int or numpy.int64
    orig_raw = ox.distance.nearest_nodes(graph, start_coords[1], start_coords[0])
    dest_raw = ox.distance.nearest_nodes(graph, end_coords[1], end_coords[0])
    
    # CRITICAL FIX: Cast to string immediately to match Graph keys
    orig_node = str(orig_raw)
    dest_node = str(dest_raw)
    
    logger.info(f"Snapped to Nodes: {orig_node} -> {dest_node}")

    # FIX: Validate nodes exist before routing
    if orig_node not in graph:
        # Fallback: try looking it up as int just in case, but usually string is safer now
        raise ValueError(f"Start Node {orig_node} not found in graph keys.")
    if dest_node not in graph:
        raise ValueError(f"End Node {dest_node} not found in graph keys.")

    # 2. Define Weight Function
    def get_weight(u, v, data):
        mode = data.get('mode', 'walking')
        if mode == 'walking':
            length = data.get('length', 0)
            return length / (1.4 * 60) # ~1.4 m/s walking speed
        elif mode == 'transit':
            return data.get('time', 0)
        elif mode == 'transfer':
            return data.get('time', 2.0)
        return 1.0

    try:
        # 3. Run Dijkstra
        path_nodes = nx.shortest_path(graph, source=orig_node, target=dest_node, weight=get_weight)
        
        # 4. Calculate Time Manually
        total_time = 0.0
        for i in range(len(path_nodes) - 1):
            u = path_nodes[i]
            v = path_nodes[i+1]
            edges_data = graph.get_edge_data(u, v)
            
            # Find the best edge (lowest time) among parallel edges
            best_time = float('inf')
            if edges_data:
                for key in edges_data:
                    time = get_weight(u, v, edges_data[key])
                    if time < best_time: best_time = time
                total_time += best_time
        
        return path_nodes, total_time

    except nx.NetworkXNoPath:
        logger.warning("NetworkX found no path.")
        return None, 0
    except Exception as e:
        logger.error(f"Pathfinding critical failure: {e}")
        raise e

def get_path_segments(graph, path_nodes):
    segments = []
    try:
        for i in range(len(path_nodes) - 1):
            u = path_nodes[i]
            v = path_nodes[i+1]
            
            all_edges = graph.get_edge_data(u, v)
            if not all_edges: continue 
            
            # Just take the first available key's data
            edge_data = list(all_edges.values())[0]
            
            u_node = graph.nodes[u]
            v_node = graph.nodes[v]
            
            coords = []
            if 'geometry' in edge_data:
                coords = [(p[1], p[0]) for p in edge_data['geometry'].coords]
            else:
                coords = [(u_node['y'], u_node['x']), (v_node['y'], v_node['x'])]
                
            segments.append({
                "coords": coords,
                "mode": edge_data.get('mode', 'walking'),
                "color": edge_data.get('color', '#3388ff')
            })
    except Exception as e:
        logger.error(f"Error generating path segments: {e}")
    
    return segments