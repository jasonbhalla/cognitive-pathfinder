var map = L.map('map', { renderer: L.canvas() }).setView([40.735, -74.03], 14);
var tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

var graphLayer = L.layerGroup();
var routeLayer = L.layerGroup().addTo(map);
var startMarker = null, endMarker = null, selectionMode = 'start', graphLoaded = false;

// --- VISUALIZATION LOGIC ---
async function toggleGraphView() {
    var isGraphMode = document.getElementById('graphToggle').checked;
    
    if (isGraphMode) {
        document.getElementById('body').classList.add('graph-mode');
        
        // Load data if not already present
        if (!graphLoaded) await loadGraphData();
        
        map.addLayer(graphLayer);
        
        // Dim the tile layer instead of removing it
        tileLayer.setOpacity(0.1); 
        
    } else {
        document.getElementById('body').classList.remove('graph-mode');
        map.removeLayer(graphLayer);
        tileLayer.setOpacity(1.0);
    }
}

async function loadGraphData() {
    var city = document.getElementById('cityInput').value;
    document.getElementById('loading').innerText = "Fetching graph visual...";
    document.getElementById('loading').style.display = 'block';

    try {
        const response = await fetch('/api/graph-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ city: city })
        });
        
        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`Server Error ${response.status}: ${errText}`);
        }

        const data = await response.json();
        
        // Draw Edges
        if (data.edges) {
            data.edges.forEach(segment => {
                L.polyline(segment.coords, { 
                    color: segment.color, 
                    weight: 1, 
                    opacity: 0.7, 
                    interactive: false 
                }).addTo(graphLayer);
            });
        }

        // Draw Nodes (Vertices)
        if (data.nodes) {
            data.nodes.forEach(coord => {
                L.circleMarker(coord, {
                    radius: 2,
                    color: '#ffffff',
                    fillColor: '#ffffff',
                    fillOpacity: 1,
                    interactive: false
                }).addTo(graphLayer);
            });
        }

        graphLoaded = true;

    } catch (e) {
        console.error(e);
        alert("Graph Visual Error: " + e.message);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

// --- CLICK HANDLER ---
map.on('click', function(e) {
    var lat = e.latlng.lat.toFixed(5);
    var lng = e.latlng.lng.toFixed(5);

    if (selectionMode === 'start') {
        if (startMarker) map.removeLayer(startMarker);
        startMarker = L.marker([lat, lng], {color: 'green'}).addTo(map).bindPopup("Start").openPopup();
        document.getElementById('startInput').value = lat + ", " + lng;
        selectionMode = 'end';
    } else {
        if (endMarker) map.removeLayer(endMarker);
        endMarker = L.marker([lat, lng], {icon: getRedIcon()}).addTo(map).bindPopup("End").openPopup();
        document.getElementById('endInput').value = lat + ", " + lng;
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

// --- FIND ROUTE ---
async function findRoute() {
    var city = document.getElementById('cityInput').value;
    var startVal = document.getElementById('startInput').value;
    var endVal = document.getElementById('endInput').value;

    if (!city || !startVal || !endVal) { alert("Please select start/end points"); return; }
    
    try {
        var [startLat, startLon] = startVal.split(',').map(s => parseFloat(s));
        var [endLat, endLon] = endVal.split(',').map(s => parseFloat(s));
    } catch (e) { alert("Invalid coordinates"); return; }

    document.getElementById('loading').innerText = "Calculating path...";
    document.getElementById('loading').style.display = 'block';
    routeLayer.clearLayers();

    try {
        const response = await fetch('/api/route', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                city, 
                start_lat: startLat, start_lon: startLon, 
                end_lat: endLat, end_lon: endLon 
            })
        });

        if (!response.ok) {
            const errText = await response.json();
            throw new Error(errText.detail || "Server Error");
        }

        const data = await response.json();

        if (data.segments) {
            data.segments.forEach(seg => {
                L.polyline(seg.coords, {
                    color: seg.color,
                    weight: 6,
                    opacity: 1.0
                }).addTo(routeLayer);
            });
            
            var allPoints = data.segments.flatMap(s => s.coords);
            if(allPoints.length > 0) map.fitBounds(L.polyline(allPoints).getBounds());
        }
        
        document.getElementById('distVal').innerText = data.time_minutes + " mins";
        document.getElementById('nodesVal').innerText = data.node_count;
        document.getElementById('stats').style.display = 'block';

    } catch (e) {
        console.error(e);
        alert("Route Error: " + e.message);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}