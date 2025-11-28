from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.core.graph_builder import get_graph
from app.core.pathfinder import find_shortest_path, get_path_coords
import networkx as nx

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

class RouteRequest(BaseModel):
    city: str
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float

# --- NEW: Request model for getting the full graph ---
class GraphRequest(BaseModel):
    city: str

@app.post("/api/graph-data")
async def get_graph_geometry(request: GraphRequest):
    """
    Returns all edges and nodes for visualization.
    WARNING: Can be large for big cities.
    """
    try:
        graph = get_graph(request.city)
        
        edges = []
        nodes = []
        
        # Extract Edges (LineSegments)
        # u, v are node IDs, data is the attribute dict
        for u, v, data in graph.edges(data=True):
            if 'geometry' in data:
                # If the edge is curvy, use the geometry
                coords = list(data['geometry'].coords)
                # Flip to (Lat, Lon) for Leaflet
                edges.append([(c[1], c[0]) for c in coords])
            else:
                # Straight line between nodes
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                edges.append([(n1['y'], n1['x']), (n2['y'], n2['x'])])

        # Extract Nodes (Points)
        for n_id, data in graph.nodes(data=True):
            nodes.append((data['y'], data['x']))

        return {"edges": edges, "nodes": nodes}

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/route")
async def calculate_route(request: RouteRequest):
    try:
        graph = get_graph(request.city)
        path_nodes, distance = find_shortest_path(graph, (request.start_lat, request.start_lon), (request.end_lat, request.end_lon))
        
        if not path_nodes:
            raise HTTPException(status_code=404, detail="No path found.")
            
        path_coords = get_path_coords(graph, path_nodes)
        
        return {
            "path": path_coords,
            "distance": round(distance, 2),
            "node_count": len(path_nodes)
        }
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))