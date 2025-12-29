import pandas as pd
import zipfile
import os
import requests
import traceback

# UPDATED REGISTRY with working MTA link
GTFS_REGISTRY = {
    "hoboken": "http://web.mta.info/developers/data/nyct/subway/google_transit.zip", 
    "new york": "http://web.mta.info/developers/data/nyct/subway/google_transit.zip",
    "manhattan": "http://web.mta.info/developers/data/nyct/subway/google_transit.zip"
}

class GTFSLoader:
    def __init__(self, city_name):
        self.city_name = city_name.lower()
        self.gtfs_path = f"data/raw/{self.city_name.replace(' ', '_')}_gtfs.zip"
        self.stops = None
        self.stop_times = None
        
    def _get_download_url(self):
        for key, url in GTFS_REGISTRY.items():
            if key in self.city_name:
                print(f"[GTFS] Match found in registry: '{key}' -> {url}")
                return url
        print(f"[GTFS] No auto-download URL found for '{self.city_name}' in registry.")
        return None

    def download_data(self):
        os.makedirs("data/raw", exist_ok=True)

        if os.path.exists(self.gtfs_path):
            print(f"[GTFS] File already exists at {self.gtfs_path}. Skipping download.")
            return True

        url = self._get_download_url()
        if not url: return False

        print(f"[GTFS] Downloading from {url}...")
        try:
            # Added User-Agent to prevent 403 Forbidden errors
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(url, stream=True, headers=headers)
            r.raise_for_status()
            with open(self.gtfs_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"[GTFS] Download complete. Saved to {self.gtfs_path}")
            return True
        except Exception as e:
            print(f"[GTFS] Download FAILED: {e}")
            return False

    def load_data(self):
        has_data = self.download_data()
        if not has_data:
            # Don't crash, just let the fusion logic handle the missing data gracefully
            print("[GTFS] No data available. Routing will be walk-only.")
            return

        print(f"[GTFS] Parsing zip file: {self.gtfs_path}...")
        try:
            with zipfile.ZipFile(self.gtfs_path) as z:
                files = z.namelist()
                stops_file = next((f for f in files if 'stops.txt' in f), None)
                times_file = next((f for f in files if 'stop_times.txt' in f), None)
                
                if not stops_file or not times_file:
                    print("[GTFS] Critical files missing in zip.")
                    return

                self.stops = pd.read_csv(z.open(stops_file))
                self.stop_times = pd.read_csv(z.open(times_file))
                
                self.stops.columns = self.stops.columns.str.strip()
                self.stop_times.columns = self.stop_times.columns.str.strip()
                
                if 'stop_lat' in self.stops.columns:
                    self.stops.rename(columns={'stop_lat': 'lat', 'stop_lon': 'lon'}, inplace=True)
                
                self.stops = self.stops[['stop_id', 'stop_name', 'lat', 'lon']].copy()
                self.stop_times = self.stop_times[['trip_id', 'stop_id', 'departure_time', 'stop_sequence', 'arrival_time']].copy()
                
                # Limit to 50k for performance
                if len(self.stop_times) > 50000:
                    self.stop_times = self.stop_times.head(50000)

                print(f"[GTFS] Loaded {len(self.stops)} stops and {len(self.stop_times)} scheduled times.")
                
        except Exception as e:
            print(f"[GTFS] Error parsing zip: {e}")
            traceback.print_exc()

    def get_transit_edges(self):
        if self.stops is None: return []
        
        print("[GTFS] Calculating average travel times between stations...")
        st = self.stop_times.sort_values(['trip_id', 'stop_sequence'])
        
        st['next_stop_id'] = st.groupby('trip_id')['stop_id'].shift(-1)
        st['next_arrival_time'] = st.groupby('trip_id')['arrival_time'].shift(-1)
        
        edges = st.dropna(subset=['next_stop_id']).copy()

        def time_to_min(t_str):
            try:
                if pd.isna(t_str): return 0
                parts = list(map(int, t_str.split(':')))
                return parts[0] * 60 + parts[1] + parts[2] / 60
            except:
                return 0

        edges['dep_min'] = edges['departure_time'].apply(time_to_min)
        edges['arr_min'] = edges['next_arrival_time'].apply(time_to_min)
        edges['duration'] = edges['arr_min'] - edges['dep_min']
        
        valid_edges = edges[(edges['duration'] > 0) & (edges['duration'] < 120)]
        
        summary = valid_edges.groupby(['stop_id', 'next_stop_id'])['duration'].mean().reset_index()
        return summary.to_dict('records')