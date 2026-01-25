var map = L.map('map', { renderer: L.canvas() }).setView([40.735, -74.03], 14);
var tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

// Separate Layers
var transitLayer = L.layerGroup();
var walkingLayer = L.layerGroup();
var routeLayer = L.layerGroup().addTo(map);

var startMarker = null, endMarker = null, selectionMode = 'start';
var transitLoaded = false;

// --- LOGGING ---
console.log("Log Poller Active");
setInterval(fetchLogs, 1000); 

async function fetchLogs() {
    try {
        const response = await fetch('/api/logs?t=' + new Date().getTime());
        if (!response.ok) return;
        const data = await response.json();
        const terminal = document.getElementById('terminal');
        if (data.logs.length > 0) {
            const isBottom = terminal.scrollHeight - terminal.scrollTop <= terminal.clientHeight + 50;
            terminal.innerHTML = data.logs.map(l => `<div class="log-entry">${escapeHtml(l)}</div>`).join('');
            if (isBottom) terminal.scrollTop = terminal.scrollHeight;
        }
    } catch (e) {}
}

function escapeHtml(text) {
    if (!text) return "";
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- VISUALIZATION CONTROLLER ---
async function toggleGraphView() {
    var isGraphMode = document.getElementById('graphToggle').checked;
    
    if (isGraphMode) {
        document.getElementById('body').classList.add('graph-mode');
        map.addLayer(walkingLayer);
        map.addLayer(transitLayer);
        tileLayer.setOpacity(0.1); 
        
        // 1. Load Transit ONCE (Global)
        if (!transitLoaded) {
            await loadTransitLayer();
            transitLoaded = true;
        }

        // 2. Load Walking NOW (Local)
        await loadWalkingLayer();

        // 3. Listen for moves to reload walking
        map.on('moveend', loadWalkingLayer);

    } else {
        document.getElementById('body').classList.remove('graph-mode');
        map.removeLayer(walkingLayer);
        map.removeLayer(transitLayer);
        tileLayer.setOpacity(1.0);
        map.off('moveend', loadWalkingLayer);
    }
}

// --- LAYER 1: TRANSIT (Global) ---
async function loadTransitLayer() {
    var city = document.getElementById('cityInput').value;
    console.log("Loading Transit Layer...");
    
    try {
        const res = await fetch('/api/layers/transit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ city: city })
        });
        const data = await res.json();
        
        // Render Red/Black lines on top
        if (data.edges) {
            data.edges.forEach(e => {
                L.polyline(e.coords, { 
                    color: e.color, 
                    weight: 3, // Thicker
                    opacity: 1.0,
                    interactive: false 
                }).addTo(transitLayer);
            });
        }
        if (data.nodes) {
            data.nodes.forEach(n => {
                L.circleMarker(n, {
                    radius: 4, // Bigger dots
                    color: '#fff',
                    fillColor: '#ff3333',
                    fillOpacity: 1,
                    interactive: false
                }).addTo(transitLayer);
            });
        }
    } catch (e) { console.error(e); }
}

// --- LAYER 2: WALKING (Viewport) ---
async function loadWalkingLayer() {
    if (!document.getElementById('graphToggle').checked) return;
    
    var city = document.getElementById('cityInput').value;
    var bounds = map.getBounds();
    var payload = {
        city: city,
        bounds: {
            min_lat: bounds.getSouth(), max_lat: bounds.getNorth(),
            min_lon: bounds.getWest(), max_lon: bounds.getEast()
        }
    };
    
    document.getElementById('loading').style.display = 'block';
    
    try {
        const res = await fetch('/api/layers/walking', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        walkingLayer.clearLayers(); // Clear old viewport data
        
        if (data.edges) {
            data.edges.forEach(e => {
                L.polyline(e.coords, { 
                    color: '#3388ff', 
                    weight: 1, // Thinner
                    opacity: 0.5,
                    interactive: false 
                }).addTo(walkingLayer);
            });
        }
        // Optional: Don't render walking nodes (dots) if too messy
        // or render them tiny
        if (data.nodes) {
            data.nodes.forEach(n => {
                L.circleMarker(n, {
                    radius: 1, 
                    color: '#3388ff',
                    fillOpacity: 0.5,
                    interactive: false
                }).addTo(walkingLayer);
            });
        }
    } catch (e) { console.error(e); }
    finally { document.getElementById('loading').style.display = 'none'; }
}


// --- REST OF APP (Click, Route) ---
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

async function findRoute() {
    var city = document.getElementById('cityInput').value;
    var startVal = document.getElementById('startInput').value;
    var endVal = document.getElementById('endInput').value;

    if (!city || !startVal || !endVal) { alert("Please select start/end points"); return; }
    
    try {
        var [startLat, startLon] = startVal.split(',').map(s => parseFloat(s));
        var [endLat, endLon] = endVal.split(',').map(s => parseFloat(s));
    } catch (e) { alert("Invalid coordinates"); return; }

    document.getElementById('loading').style.display = 'block';
    routeLayer.clearLayers();

    try {
        const response = await fetch('/api/route', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                city, start_lat: startLat, start_lon: startLon, end_lat: endLat, end_lon: endLon 
            })
        });

        if (!response.ok) throw new Error("Route failed");
        const data = await response.json();

        if (data.segments) {
            data.segments.forEach(seg => {
                L.polyline(seg.coords, {
                    color: seg.color, weight: 6, opacity: 1.0
                }).addTo(routeLayer);
            });
            var allPoints = data.segments.flatMap(s => s.coords);
            if(allPoints.length > 0) map.fitBounds(L.polyline(allPoints).getBounds());
        }
        
        document.getElementById('distVal').innerText = data.time_minutes + " mins";
        document.getElementById('nodesVal').innerText = data.node_count;
        document.getElementById('stats').style.display = 'block';

    } catch (e) { alert("Route Error: " + e.message); } 
    finally { document.getElementById('loading').style.display = 'none'; }
}