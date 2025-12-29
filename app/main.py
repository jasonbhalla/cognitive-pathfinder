import sys
import json
import math
import traceback
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from app.core.graph_builder import get_fused_graph
from app.core.pathfinder import find_shortest_path, get_path_segments

# --- CONFIGURING DEEP LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

# --- EXCEPTION HANDLERS ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    logger.error(f"Validation Error on {request.url}")
    logger.error(f"Body: {body.decode()}")
    logger.error(f"Details: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Server Crash: {str(exc)}")
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": str(exc)})

# --- DATA MODELS ---

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

# --- NAN CLEANER ---
def sanitize_json(data):
    if isinstance(data, dict):
        return {k: sanitize_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_json(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
    return data

# --- ENDPOINTS ---

@app.post("/api/graph-data")
async def get_graph_geometry(request: GraphRequest):
    logger.info(f"GRAPH REQUEST: {request.dict()}")
    try:
        graph = get_fused_graph(request.city)
        edges = []
        nodes = []
        
        # Limit for browser performance
        limit = 5000 
        count = 0
        
        # 1. Collect Edges
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

        # 2. Collect Nodes (Vertices)
        # We limit these too to avoid crashing the browser with 5000+ circles
        node_limit = 2000
        node_count = 0
        for n, data in graph.nodes(data=True):
            if node_count > node_limit: break
            nodes.append([data['y'], data['x']])
            node_count += 1

        response_data = {"edges": edges, "nodes": nodes}
        logger.info(f"Sending {len(edges)} edges and {len(nodes)} nodes to frontend.")
        return sanitize_json(response_data)

    except Exception as e:
        logger.error(f"Graph Data Failed: {e}")
        raise e

@app.post("/api/route")
async def calculate_route(request: RouteRequest):
    logger.info(f"ROUTE REQUEST: {request.dict()}")
    try:
        graph = get_fused_graph(request.city)
        
        start_coords = (request.start_lat, request.start_lon)
        end_coords = (request.end_lat, request.end_lon)
        
        path_nodes, total_time = find_shortest_path(graph, start_coords, end_coords)
        
        if not path_nodes:
            logger.warning("Pathfinder returned None (No path found).")
            raise HTTPException(status_code=404, detail="No path found between these points.")
            
        segments = get_path_segments(graph, path_nodes)
        
        response_data = {
            "segments": segments,
            "time_minutes": total_time,
            "node_count": len(path_nodes)
        }
        
        safe_response = sanitize_json(response_data)
        logger.info(f"ROUTE SUCCESS. Sending response.")
        
        return safe_response

    except Exception as e:
        logger.error(f"Route Calculation Failed: {e}")
        traceback.print_exc()
        raise e