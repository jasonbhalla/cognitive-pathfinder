// 1. Initialize Map
var map = L.map('map', {
    renderer: L.canvas() // IMPORTANT: Use Canvas for performance with many lines
}).setView([40.745, -74.03], 15);

// 2. Layers
// The Standard Map Tiles
var tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
}).addTo(map);

// Layer Groups for Graph visualization
var graphEdgesLayer = L.layerGroup();
var graphNodesLayer = L.layerGroup();
var routeLayer = L.layerGroup().addTo(map); // Route always shows

var startMarker = null;
var endMarker = null;
var selectionMode = 'start';
var graphLoaded = false; // Flag to check if we already fetched graph data

// 3. Toggle Logic
async function toggleGraphView() {
    var isGraphMode = document.getElementById('graphToggle').checked;
    
    if (isGraphMode) {
        // Switch to Graph Mode
        document.getElementById('body').classList.add('graph-mode');
        map.removeLayer(tileLayer); // Hide tiles
        
        if (!graphLoaded) {
            await loadGraphData();
        }
        
        map.addLayer(graphEdgesLayer);
        map.addLayer(graphNodesLayer);
        
    } else {
        // Switch to Map Mode
        document.getElementById('body').classList.remove('graph-mode');
        map.addLayer(tileLayer); // Show tiles
        map.removeLayer(graphEdgesLayer);
        map.removeLayer(graphNodesLayer);
    }
}

async function loadGraphData() {
    var city = document.getElementById('cityInput').value;
    document.getElementById('loading').innerText = "Downloading full graph geometry...";
    document.getElementById('loading').style.display = 'block';

    try {
        const response = await fetch('/api/graph-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ city: city })
        });
        const data = await response.json();

        // Draw Edges (Grey Lines)
        // Using a light grey color so it looks like a wireframe on black background
        data.edges.forEach(segment => {
            L.polyline(segment, {
                color: '#555', // Dark Grey
                weight: 1,
                opacity: 0.5,
                interactive: false // Disable clicking on generic edges for speed
            }).addTo(graphEdgesLayer);
        });

        // Draw Nodes (Small Dots)
        data.nodes.forEach(coords => {
            L.circleMarker(coords, {
                radius: 1, // Very small dot
                color: '#888',
                fillColor: '#fff',
                fillOpacity: 0.8,
                interactive: false
            }).addTo(graphNodesLayer);
        });

        graphLoaded = true;
    } catch (e) {
        alert("Error loading graph visual: " + e);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

// 4. Interaction Logic (Markers)
map.on('click', function(e) {
    var lat = e.latlng.lat;
    var lng = e.latlng.lng;

    if (selectionMode === 'start') {
        if (startMarker) map.removeLayer(startMarker);
        startMarker = L.marker([lat, lng], {color: 'green'}).addTo(map).bindPopup("Start").openPopup();
        document.getElementById('startInput').value = lat.toFixed(5) + ", " + lng.toFixed(5);
        selectionMode = 'end';
    } else {
        if (endMarker) map.removeLayer(endMarker);
        endMarker = L.marker([lat, lng], {icon: getRedIcon()}).addTo(map).bindPopup("End").openPopup();
        document.getElementById('endInput').value = lat.toFixed(5) + ", " + lng.toFixed(5);
        selectionMode = 'start';
    }
});

function getRedIcon() {
    return new L.Icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    });
}

// 5. Routing Logic
async function findRoute() {
    var city = document.getElementById('cityInput').value;
    var startVal = document.getElementById('startInput').value;
    var endVal = document.getElementById('endInput').value;

    if (!city || !startVal || !endVal) { alert("Please select start/end points"); return; }
    
    // Check if city changed, if so, invalidate graph cache
    // (Simplification: for now we assume city doesn't change mid-session for the visualizer)

    var [startLat, startLon] = startVal.split(',').map(s => parseFloat(s));
    var [endLat, endLon] = endVal.split(',').map(s => parseFloat(s));

    document.getElementById('loading').innerText = "Calculating path...";
    document.getElementById('loading').style.display = 'block';
    routeLayer.clearLayers();

    try {
        const response = await fetch('/api/route', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ city, start_lat: startLat, start_lon: startLon, end_lat: endLat, end_lon: endLon })
        });
        const data = await response.json();

        if (response.ok) {
            // Draw Route (Neon Cyan for visibility on both maps)
            var polyline = L.polyline(data.path, {
                color: '#00FFFF', // Cyan/Neon Blue
                weight: 5,
                opacity: 0.9
            }).addTo(routeLayer);
            
            map.fitBounds(polyline.getBounds());
            
            document.getElementById('distVal').innerText = data.distance;
            document.getElementById('nodesVal').innerText = data.node_count;
            document.getElementById('stats').style.display = 'block';
        } else {
            alert(data.detail);
        }
    } catch (e) {
        console.error(e);
        alert("Server Error");
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}