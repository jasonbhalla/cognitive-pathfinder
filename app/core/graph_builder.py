import os
import re
import osmnx as ox
import networkx as nx
from scipy.spatial import cKDTree
import pandas as pd
import traceback
from shapely import wkt
from app.core.gtfs_loader import GTFSLoader

def get_fused_graph(city_name):
    # 1. Filenames
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', city_name.lower())
    filename = f"data/processed/{safe_name}_fused.graphml"
    os.makedirs("data/processed", exist_ok=True)
    
    G = None

    # --- LOAD CACHED GRAPH ---
    if os.path.exists(filename):
        print(f"[Graph] Loading cached fused graph: {filename}")
        try:
            # Load with string IDs
            G = nx.read_graphml(filename, node_type=str)
        except Exception as e:
            print(f"[Graph] Cache load failed ({e}). Rebuilding.")
            G = None

    # --- BUILD NEW GRAPH (If cache failed or missing) ---
    if G is None:
        print(f"[Graph] Cache missing. Downloading OSM Walk Graph for '{city_name}'...")
        try:
            G = ox.graph_from_place(city_name, network_type='walk')
            
            # Normalize OSM IDs to strings immediately (FIXED: Removed extra parenthesis)
            mapping = {n: str(n) for n in G.nodes()}
            G = nx.relabel_nodes(G, mapping)
            
            print(f"[Graph] OSM Download Complete. Nodes: {len(G.nodes)}, Edges: {len(G.edges)}")
            
            # Tag defaults
            for u, v, k, data in G.edges(keys=True, data=True):
                data['mode'] = 'walking'
                data['color'] = '#3388ff'

            # --- GTFS FUSION ---
            print(f"[Graph] Attempting GTFS Fusion for '{city_name}'...")
            try:
                loader = GTFSLoader(city_name)
                loader.load_data()
                
                transit_edges = loader.get_transit_edges()
                stops = loader.stops
                
                # A. Add Transit Nodes
                stops['node_id'] = stops['stop_id'].apply(lambda x: f"transit_{x}")
                existing_nodes = set(G.nodes)
                
                added_stops = 0
                for _, stop in stops.iterrows():
                    if stop['node_id'] not in existing_nodes:
                        G.add_node(
                            stop['node_id'],
                            x=float(stop['lon']), 
                            y=float(stop['lat']), 
                            type='station',
                            mode='transit'
                        )
                        added_stops += 1
                print(f"[Fusion] Added {added_stops} Transit Stop Nodes.")

                # B. Add Transit Edges
                added_edges = 0
                for edge in transit_edges:
                    u = f"transit_{edge['stop_id']}"
                    v = f"transit_{edge['next_stop_id']}"
                    if u in G.nodes and v in G.nodes:
                        G.add_edge(u, v, key=0, length=0, time=edge['duration'], mode='transit', color='#ff3333') 
                        added_edges += 1
                print(f"[Fusion] Added {added_edges} Transit Schedules (Edges).")

                # C. Stitching
                print("[Fusion] Stitching Transit Nodes to Street Network...")
                osm_nodes_df = pd.DataFrame([
                    {'id': n, 'x': float(data['x']), 'y': float(data['y'])} 
                    for n, data in G.nodes(data=True) 
                    if data.get('mode') != 'transit'
                ])
                
                stitched_count = 0
                if not osm_nodes_df.empty:
                    tree = cKDTree(osm_nodes_df[['x', 'y']].values)
                    stops_locs = stops[['lon', 'lat']].astype(float).values
                    dists, idxs = tree.query(stops_locs, k=1)
                    
                    for i, (dist, idx) in enumerate(zip(dists, idxs)):
                        if dist < 0.003: 
                            transit_node = stops.iloc[i]['node_id']
                            street_node = str(osm_nodes_df.iloc[idx]['id'])
                            
                            G.add_edge(street_node, transit_node, key=0, time=2.0, mode='transfer', color='#000000')
                            G.add_edge(transit_node, street_node, key=0, time=2.0, mode='transfer', color='#000000')
                            stitched_count += 1
                            
                print(f"[Fusion] Stitched {stitched_count} stops to nearby streets.")
                
            except FileNotFoundError:
                print("[Fusion] No GTFS data found. Skipping fusion.")
            except Exception as e:
                print(f"[Fusion] CRITICAL FAILURE during fusion: {e}")
                traceback.print_exc()
                
            print(f"[Graph] Saving to {filename}...")
            ox.save_graphml(G, filename)
            
        except Exception as e:
            print(f"[Graph] CRITICAL BUILD FAILED: {e}")
            raise e

    # --- FINAL SANITIZATION ---
    print("[Graph] Sanitizing data types (Nodes=Float, Edges=WKT/Float)...")
    
    # 1. Force Node Coords to Float
    for n, data in G.nodes(data=True):
        try:
            if 'x' in data: data['x'] = float(data['x'])
            if 'y' in data: data['y'] = float(data['y'])
        except Exception:
            pass 

    # 2. Force Edge Geometries AND Weights
    for u, v, data in G.edges(data=True):
        # A. Hydrate WKT Geometries
        if 'geometry' in data and isinstance(data['geometry'], str):
            try:
                data['geometry'] = wkt.loads(data['geometry'])
            except Exception:
                pass
        
        # B. Hydrate Numeric Weights (The fix for your crash)
        if 'length' in data:
            try:
                data['length'] = float(data['length'])
            except (ValueError, TypeError):
                data['length'] = 0.0
        
        if 'time' in data:
            try:
                data['time'] = float(data['time'])
            except (ValueError, TypeError):
                data['time'] = 0.0

    return G