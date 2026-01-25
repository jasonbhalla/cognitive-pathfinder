import sys
import json
import math
import traceback
import logging
import collections
import builtins
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict
from app.core.graph_builder import get_fused_graph
from app.core.pathfinder import find_shortest_path, get_path_segments

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

# --- LOGGING SETUP ---
LOG_BUFFER = collections.deque(maxlen=100)
original_print = builtins.print

def custom_print(*args, **kwargs):
    original_print(*args, **kwargs)
    try:
        msg = " ".join(map(str, args))
        if not msg.strip(): return
        if not msg.startswith(tuple(str(i) for i in range(10))):
            timestamp = datetime.now().strftime("%H:%M:%S")
            msg = f"{timestamp} - {msg}"
        LOG_BUFFER.append(msg)
    except: pass

builtins.print = custom_print

def log_event(message: str, level: str = "INFO"):
    print(f"{datetime.now().strftime('%H:%M:%S')} - [{level}] - {message}")

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/api/logs") == -1

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# --- DATA MODELS ---
class BoundingBox(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

class LayerRequest(BaseModel):
    city: str
    bounds: Optional[BoundingBox] = None

class RouteRequest(BaseModel):
    city: str
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float

def sanitize_json(data):
    if isinstance(data, dict): return {k: sanitize_json(v) for k, v in data.items()}
    elif isinstance(data, list): return [sanitize_json(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data): return None
    return data

# --- ENDPOINTS ---

@app.get("/api/logs")
async def get_logs():
    return {"logs": list(LOG_BUFFER)}

@app.post("/api/layers/transit")
def get_transit_layer(request: LayerRequest):
    """
    Returns the COMPLETE Transit Layer.
    We do NOT filter this by bounds. The user needs to see the whole system.
    """
    log_event(f"FETCH TRANSIT LAYER: {request.city}")
    try:
        graph = get_fused_graph(request.city)
        edges = []
        nodes = []
        
        # Iterate ENTIRE graph, pick out only Transit & Connectors
        for u, v, data in graph.edges(data=True):
            layer = data.get('layer', 'walking')
            
            # We want Transit lines AND the connectors to the street
            if layer in ['transit', 'connector']:
                coords = []
                if 'geometry' in data:
                    try: coords = [(p[1], p[0]) for p in data['geometry'].coords]
                    except: pass
                
                if not coords:
                    n1 = graph.nodes[u]
                    n2 = graph.nodes[v]
                    coords = [(n1['y'], n1['x']), (n2['y'], n2['x'])]
                
                edges.append({"coords": coords, "color": data.get('color', '#000')})
                
                # Add associated nodes
                for node_id in [u, v]:
                    n = graph.nodes[node_id]
                    nodes.append([n['y'], n['x']])

        log_event(f"Sending TRANSIT Layer: {len(edges)} edges.")
        return sanitize_json({"edges": edges, "nodes": nodes})
    except Exception as e:
        log_event(f"Transit Layer Failed: {e}", "ERROR")
        raise e

@app.post("/api/layers/walking")
def get_walking_layer(request: LayerRequest):
    """
    Returns the Walking Layer, strictly filtered by current VIEWPORT.
    We return EVERYTHING in the viewport. No arbitrary limits.
    """
    if not request.bounds:
        return {"edges": [], "nodes": []} # Don't load walking data without bounds

    log_event(f"FETCH WALKING LAYER: {request.city}")
    try:
        graph = get_fused_graph(request.city)
        edges = []
        nodes = []
        
        # Buffer bounds by 10%
        b = request.bounds
        lat_buf = (b.max_lat - b.min_lat) * 0.1
        lon_buf = (b.max_lon - b.min_lon) * 0.1
        min_lat, max_lat = b.min_lat - lat_buf, b.max_lat + lat_buf
        min_lon, max_lon = b.min_lon - lon_buf, b.max_lon + lon_buf
        
        # 1. Fast Node Filter
        visible_nodes = set()
        for n, data in graph.nodes(data=True):
            if data.get('layer') == 'walking':
                if min_lat < data['y'] < max_lat and min_lon < data['x'] < max_lon:
                    visible_nodes.add(n)
        
        if not visible_nodes:
            return {"edges": [], "nodes": []}

        # 2. Extract Subgraph
        # This gets ALL edges connecting these nodes.
        subgraph = graph.subgraph(visible_nodes)
        
        # 3. Serialize
        SAFETY_LIMIT = 40000 
        
        for u, v, data in subgraph.edges(data=True):
            if len(edges) >= SAFETY_LIMIT: break
            
            coords = []
            if 'geometry' in data:
                try: coords = [(p[1], p[0]) for p in data['geometry'].coords]
                except: pass
            
            if not coords:
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                coords = [(n1['y'], n1['x']), (n2['y'], n2['x'])]
            
            edges.append({"coords": coords, "color": data.get('color', '#3388ff')})

        # Add nodes for visual dots
        for n in subgraph.nodes():
            if len(nodes) >= 10000: break
            d = graph.nodes[n]
            nodes.append([d['y'], d['x']])

        log_event(f"Sending WALKING Layer: {len(edges)} edges.")
        return sanitize_json({"edges": edges, "nodes": nodes})
        
    except Exception as e:
        log_event(f"Walking Layer Failed: {e}", "ERROR")
        raise e

@app.post("/api/route")
def calculate_route(request: RouteRequest):
    log_event(f"ROUTE REQUEST: {request.start_lat},{request.start_lon} -> {request.end_lat},{request.end_lon}")
    try:
        graph = get_fused_graph(request.city)
        start = (request.start_lat, request.start_lon)
        end = (request.end_lat, request.end_lon)
        
        path, time = find_shortest_path(graph, start, end)
        
        if not path:
            log_event("No path found.", "WARNING")
            raise HTTPException(status_code=404, detail="No path found.")
            
        segments = get_path_segments(graph, path)
        return sanitize_json({"segments": segments, "time_minutes": time, "node_count": len(path)})

    except Exception as e:
        log_event(f"Route Failed: {e}", "ERROR")
        traceback.print_exc()
        raise e