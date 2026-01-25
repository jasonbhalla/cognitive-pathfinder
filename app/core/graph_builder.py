import os
import re
import osmnx as ox
import networkx as nx
from scipy.spatial import cKDTree
import pandas as pd
import traceback
from shapely import wkt
from app.core.gtfs_loader import GTFSLoader

# --- CONFIGURATION ---
WALK_COLOR = '#3388ff'
TRANSIT_COLOR = '#ff3333'
TRANSFER_COLOR = '#000000'

def get_fused_graph(city_name):
    # 1. Filenames
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', city_name.lower())
    filename = f"data/processed/{safe_name}_fused.graphml"
    os.makedirs("data/processed", exist_ok=True)
    
    G = None

    # --- ATTEMPT CACHE LOAD ---
    if os.path.exists(filename):
        print(f"[Graph] Loading cached fused graph: {filename}")
        try:
            G = nx.read_graphml(filename, node_type=str)
        except Exception as e:
            print(f"[Graph] Cache corrupted ({e}). Rebuilding fresh.")
            G = None

    # --- BUILD FROM SCRATCH ---
    if G is None:
        print(f"[Graph] Cache missing. Building Layers for '{city_name}'...")
        
        # === LAYER 1: WALKING (OSM) ===
        try:
            print("[Layer: Walk] Downloading Street Network...")
            G = ox.graph_from_place(city_name, network_type='walk')
            
            # Standardize IDs to strings
            mapping = {n: str(n) for n in G.nodes()}
            G = nx.relabel_nodes(G, mapping)
            
            # STAMP THE LAYER
            nx.set_node_attributes(G, 'walking', 'layer')
            nx.set_edge_attributes(G, 'walking', 'layer')
            nx.set_edge_attributes(G, WALK_COLOR, 'color')
            
            print(f"[Layer: Walk] Built. Nodes: {len(G.nodes)}, Edges: {len(G.edges)}")
        except Exception as e:
            raise Exception(f"Failed to build Walking Layer: {e}")

        # === LAYER 2: TRANSIT (GTFS) ===
        print("[Layer: Transit] Integrating Public Transit...")
        try:
            loader = GTFSLoader(city_name)
            loader.load_data()
            stops = loader.stops
            transit_edges = loader.get_transit_edges()
            
            # 1. Add Transit Nodes (Stations)
            transit_nodes_added = 0
            stops['node_id'] = stops['stop_id'].apply(lambda x: f"transit_{x}")
            
            # Use a dict for fast lookups during edge creation
            stop_lookup = {} 
            
            for _, stop in stops.iterrows():
                node_id = stop['node_id']
                if node_id not in G:
                    G.add_node(
                        node_id,
                        x=float(stop['lon']),
                        y=float(stop['lat']),
                        layer='transit',
                        type='station'
                    )
                    transit_nodes_added += 1
                stop_lookup[stop['stop_id']] = node_id
            
            print(f"[Layer: Transit] Added {transit_nodes_added} Station Nodes.")

            # 2. Add Transit Edges (Tracks)
            transit_edges_added = 0
            for edge in transit_edges:
                u = stop_lookup.get(edge['stop_id'])
                v = stop_lookup.get(edge['next_stop_id'])
                
                if u and v and u in G and v in G:
                    G.add_edge(
                        u, v,
                        key=0,
                        layer='transit',
                        time=float(edge['duration']),
                        color=TRANSIT_COLOR
                    )
                    transit_edges_added += 1
            
            print(f"[Layer: Transit] Added {transit_edges_added} Transit Connections.")

            # === LAYER 3: CONNECTORS (FUSION) ===
            # Connect Layer 1 (Walk) to Layer 2 (Transit)
            print("[Layer: Fusion] Stitching layers...")
            
            # Get Walking Nodes (Target)
            walk_nodes = [
                {'id': n, 'x': float(d['x']), 'y': float(d['y'])}
                for n, d in G.nodes(data=True)
                if d.get('layer') == 'walking'
            ]
            walk_df = pd.DataFrame(walk_nodes)
            
            # Get Transit Nodes (Source)
            transit_node_list = [
                {'id': n, 'x': float(d['x']), 'y': float(d['y'])}
                for n, d in G.nodes(data=True)
                if d.get('layer') == 'transit'
            ]
            
            connections_made = 0
            if not walk_df.empty and transit_node_list:
                # Spatial Index for fast lookup
                tree = cKDTree(walk_df[['x', 'y']].values)
                
                for t_node in transit_node_list:
                    # Find nearest street node within 100 meters (approx 0.001 deg)
                    dist, idx = tree.query([t_node['x'], t_node['y']], k=1)
                    
                    # 0.002 degrees is roughly ~200 meters. 
                    # We want to be generous to ensure connectivity.
                    if dist < 0.002: 
                        w_node_id = walk_df.iloc[idx]['id']
                        t_node_id = t_node['id']
                        
                        # Add Bi-Directional Transfer Edge
                        G.add_edge(w_node_id, t_node_id, layer='connector', time=2.0, color=TRANSFER_COLOR)
                        G.add_edge(t_node_id, w_node_id, layer='connector', time=2.0, color=TRANSFER_COLOR)
                        connections_made += 1

            print(f"[Layer: Fusion] Created {connections_made} Transfer Connections.")

        except FileNotFoundError:
            print("[Layer: Transit] No GTFS data found. Skipping layer.")
        except Exception as e:
            print(f"[Layer: Transit] Failed to integrate: {e}")
            traceback.print_exc()

        # Save to disk
        print(f"[Graph] Serialization... Saving to {filename}")
        ox.save_graphml(G, filename)

    # --- FINAL SANITIZATION ---
    # We run this on EVERY load (cache or fresh) to ensure types are perfect.
    print("[Graph] Validating Data Types...")
    
    # 1. Nodes: Coords must be floats
    for n, data in G.nodes(data=True):
        try:
            data['x'] = float(data['x'])
            data['y'] = float(data['y'])
        except: pass

    # 2. Edges: Geometry must be Object, weights must be floats
    for u, v, data in G.edges(data=True):
        # Fix weights
        for weight_key in ['time', 'length']:
            if weight_key in data:
                try:
                    data[weight_key] = float(data[weight_key])
                except:
                    data[weight_key] = 0.0
        
        # Fix geometry (WKT String -> Object)
        if 'geometry' in data and isinstance(data['geometry'], str):
            try:
                data['geometry'] = wkt.loads(data['geometry'])
            except: pass

    return G