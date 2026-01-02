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
from typing import Optional, List
from app.core.graph_builder import get_fused_graph
from app.core.pathfinder import find_shortest_path, get_path_segments

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

# --- 1. THE LOG BUFFER ---
LOG_BUFFER = collections.deque(maxlen=100)

# --- 2. THE PRINT HIJACKER ---
original_print = builtins.print

def custom_print(*args, **kwargs):
    """
    Replacer for the standard print() function.
    1. Sends output to the real terminal.
    2. Captures output for the UI.
    """
    # 1. Print to actual terminal
    original_print(*args, **kwargs)
    
    # 2. Capture for UI
    try:
        msg = " ".join(map(str, args))
        if not msg.strip(): return

        # Add timestamp if missing
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
    print(formatted_msg) # Triggers custom_print

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

class GraphRequest(BaseModel):
    city: str
    gtfs_file: Optional[str] = None

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
    """Reads logs. Keeps 'async' because reading memory is fast."""
    return {"logs": list(LOG_BUFFER)}

@app.post("/api/graph-data")
def get_graph_geometry(request: GraphRequest):
    """
    REMOVED 'async': Now runs in a threadpool. 
    This allows /api/logs to answer WHILE this function is downloading/processing.
    """
    log_event(f"GRAPH REQUEST: {request.city}")
    try:
        graph = get_fused_graph(request.city)
        edges = []
        nodes = []
        
        limit = 5000 
        count = 0
        
        for u, v, data in graph.edges(data=True):
            if count > limit: break
            
            coords = []
            if 'geometry' in data:
                coords = [(c[1], c[0]) for c in data['geometry'].coords]
            else:
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                coords = [(n1['y'], n1['x']), (n2['y'], n2['x'])]
            
            edges.append({
                "coords": coords,
                "color": data.get('color', '#999')
            })
            count += 1

        node_limit = 2000
        node_count = 0
        for n, data in graph.nodes(data=True):
            if node_count > node_limit: break
            nodes.append([data['y'], data['x']])
            node_count += 1

        response_data = {"edges": edges, "nodes": nodes}
        log_event(f"Sending {len(edges)} edges and {len(nodes)} nodes to frontend.")
        return sanitize_json(response_data)

    except Exception as e:
        log_event(f"Graph Data Failed: {e}", "ERROR")
        raise e

@app.post("/api/route")
def calculate_route(request: RouteRequest):
    """
    REMOVED 'async': Now runs in a threadpool. 
    Allows real-time logging during heavy pathfinding.
    """
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