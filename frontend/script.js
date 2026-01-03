var map = L.map('map', { renderer: L.canvas() }).setView([40.735, -74.03], 14);
var tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

var graphLayer = L.layerGroup();
var routeLayer = L.layerGroup().addTo(map);
var startMarker = null, endMarker = null, selectionMode = 'start', graphLoaded = false;

// --- LOGGING SYSTEM ---
console.log("Starting Log Poller...");
setInterval(fetchLogs, 1000); 

async function fetchLogs() {
    try {
        const response = await fetch('/api/logs?t=' + new Date().getTime());
        if (!response.ok) return;

        const data = await response.json();
        const terminal = document.getElementById('terminal');

        if (data.logs && data.logs.length > 0) {
            const isScrolledToBottom = terminal.scrollHeight - terminal.scrollTop <= terminal.clientHeight + 20;
            const html = data.logs.map(line => 
                `<div class="log-entry">${escapeHtml(line)}</div>`
            ).join('');
            
            if (terminal.innerHTML !== html) {
                terminal.innerHTML = html;
                if (isScrolledToBottom) terminal.scrollTop = terminal.scrollHeight;
            }
        }
    } catch (e) {
        console.error("Poll error:", e);
    }
}

function escapeHtml(text) {
    if (!text) return "";
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- VISUALIZATION LOGIC ---
async function toggleGraphView() {
    var isGraphMode = document.getElementById('graphToggle').checked;
    
    if (isGraphMode) {
        document.getElementById('body').classList.add('graph-mode');
        // Force reload every time toggle is checked to respect NEW map bounds
        graphLayer.clearLayers(); 
        await loadGraphData();
        
        map.addLayer(graphLayer);
        tileLayer.setOpacity(0.1); 
    } else {
        document.getElementById('body').classList.remove('graph-mode');
        map.removeLayer(graphLayer);
        tileLayer.setOpacity(1.0);
    }
}

async function loadGraphData() {
    var city = document.getElementById('cityInput').value;
    document.getElementById('loading').innerText = "Fetching visible graph...";
    document.getElementById('loading').style.display = 'block';

    // NEW: Get current map bounds to send to backend
    var bounds = map.getBounds();
    
    var payload = {
        city: city,
        bounds: {
            min_lat: bounds.getSouth(),
            max_lat: bounds.getNorth(),
            min_lon: bounds.getWest(),
            max_lon: bounds.getEast()
        }
    };

    try {
        const response = await fetch('/api/graph-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`Server Error ${response.status}: ${errText}`);
        }

        const data = await response.json();
        
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