# cognitive-pathfinder
A multimodal routing engine providing a personalized pathfinding algorithm based on subjective, user-specific costs. It fuses static data with real-time transit and traffic APIs to build a dynamic, weighted graph. The system finds the optimal route that minimizes a user's perceived frustration rather than just the raw travel time. Intersections are stored as vertices and edges between intersections correspond to some path between them via some mode of transportation. Based on the user's preferences (e.g., some people dislike transit but still would rather take transit to downtown specifically because they really hate finding parking downtown, some people really despise transit lines and delays so they would rather walk for longer compared to transit for shorter, some people would rather take transit even if it takes twice as long as walking but only if the walk contains a hill, etc.), edge weights are adjusted and dynamic calculations for the total user cost are performed. The UI provides both an interface to use the program, and also a visualization of the graph and the mathematical breakdown of the performance.

## Run the app

1) Install dependencies from `requirements.txt`:
    ```
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
2) Start the server:
    ```
    uvicorn app.main:app --reload
3) Open in your browser:

    http://127.0.0.1:8000/static/index.html