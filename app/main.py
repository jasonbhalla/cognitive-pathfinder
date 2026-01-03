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
from typing import Optional, List, Set
from app.core.graph_builder import get_fused_graph
from app.core.pathfinder import find_shortest_path, get_path_segments

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

# --- 1. THE LOG BUFFER ---
LOG_BUFFER = collections.deque(maxlen=100)

# --- 2. THE PRINT HIJACKER ---
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
    except Exception:
        pass

builtins.print = custom_print

def log_event(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"{timestamp} - [{level}] - {message}"
    print(formatted_msg)

# --- 3. SILENCE UVICORN SPAM ---
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/api/logs") == -1

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# --- 4. EXCEPTION HANDLERS ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    error_msg = f"Validation Error on {request.url}: {exc.errors()}"
    log_event(error_msg, "ERROR")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    error_msg = f"Server Crash: {str(exc)}"
    log_event(error_msg, "CRITICAL")
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": str(exc)})

# --- 5. DATA MODELS ---
class BoundingBox(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

class GraphRequest(BaseModel):
    city: str
    gtfs_file: Optional[str] = None
    bounds: Optional[BoundingBox] = None 

class RouteRequest(BaseModel):
    city: str
    gtfs_file: Optional[str] = None
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float

# --- 6. NAN CLEANER ---
def sanitize_json(data):
    if isinstance(data, dict):
        return {k: sanitize_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_json(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
    return data

# --- 7. ENDPOINTS ---
@app.get("/api/logs")
async def get_logs():
    return {"logs": list(LOG_BUFFER)}

@app.post("/api/graph-data")
def get_graph_geometry(request: GraphRequest):
    log_event(f"GRAPH REQUEST: {request.city}")
    try:
        graph = get_fused_graph(request.city)
        edges = []
        nodes = []
        
        # 1. Calculate Buffered Bounds
        if request.bounds:
            lat_span = request.bounds.max_lat - request.bounds.min_lat
            lon_span = request.bounds.max_lon - request.bounds.min_lon
            buffer_lat = lat_span * 0.2
            buffer_lon = lon_span * 0.2
            
            min_lat = request.bounds.min_lat - buffer_lat
            max_lat = request.bounds.max_lat + buffer_lat
            min_lon = request.bounds.min_lon - buffer_lon
            max_lon = request.bounds.max_lon + buffer_lon
        else:
            min_lat, max_lat, min_lon, max_lon = -90, 90, -180, 180

        active_node_ids = set()
        
        # 2. Filter Edges (Hard limit is okay here to prevent browser crash)
        edge_limit = 20000 
        count = 0

        for u, v, data in graph.edges(data=True):
            if count > edge_limit: break
            
            # Get coordinates
            try:
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                y1, x1 = float(n1.get('y', 0)), float(n1.get('x', 0))
                y2, x2 = float(n2.get('y', 0)), float(n2.get('x', 0))
            except KeyError:
                continue 
                
            # Visibility Check
            u_visible = (min_lat < y1 < max_lat) and (min_lon < x1 < max_lon)
            v_visible = (min_lat < y2 < max_lat) and (min_lon < x2 < max_lon)
            
            if not (u_visible or v_visible):
                continue

            # Add endpoints to active set
            active_node_ids.add(u)
            active_node_ids.add(v)

            coords = []
            if 'geometry' in data:
                try:
                    coords = [(p[1], p[0]) for p in data['geometry'].coords]
                except AttributeError:
                    coords = [(y1, x1), (y2, x2)]
            else:
                coords = [(y1, x1), (y2, x2)]
            
            edges.append({
                "coords": coords,
                "color": data.get('color', '#999')
            })
            count += 1
        
        # 3. Fetch Nodes (NO LIMIT)
        # FIX: We removed the limit here. If an edge is shown, its nodes MUST be shown.
        for node_id in active_node_ids:
            n_data = graph.nodes[node_id]
            nodes.append([float(n_data.get('y')), float(n_data.get('x'))])

        response_data = {"edges": edges, "nodes": nodes}
        log_event(f"Sending {len(edges)} visible edges and {len(nodes)} connected nodes.")
        return sanitize_json(response_data)

    except Exception as e:
        log_event(f"Graph Data Failed: {e}", "ERROR")
        raise e

@app.post("/api/route")
def calculate_route(request: RouteRequest):
    log_event(f"ROUTE REQUEST: {request.start_lat},{request.start_lon} -> {request.end_lat},{request.end_lon}")
    try:
        graph = get_fused_graph(request.city)
        
        start_coords = (request.start_lat, request.start_lon)
        end_coords = (request.end_lat, request.end_lon)
        
        path_nodes, total_time = find_shortest_path(graph, start_coords, end_coords)
        
        if not path_nodes:
            log_event("Pathfinder returned None (No path found).", "WARNING")
            raise HTTPException(status_code=404, detail="No path found between these points.")
            
        segments = get_path_segments(graph, path_nodes)
        
        response_data = {
            "segments": segments,
            "time_minutes": total_time,
            "node_count": len(path_nodes)
        }
        
        safe_response = sanitize_json(response_data)
        log_event(f"ROUTE SUCCESS. Sending response.")
        return safe_response

    except Exception as e:
        log_event(f"Route Calculation Failed: {e}", "ERROR")
        traceback.print_exc()
        raise e