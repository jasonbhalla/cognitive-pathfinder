import os
import requests
import zipfile
import pandas as pd
import shutil
from io import BytesIO

# --- REGISTRY ---
# For now, I'm hard-coding certain cities with their data since I'm not sure if there's a good way to have it be universal and generalized for any city
GTFS_FEEDS = {
    'hoboken': ['https://data.trilliumtransit.com/gtfs/path-nj-us/path-nj-us.zip'],
    'new york': [
        # MTA New York City Transit (Subway)
        'http://web.mta.info/developers/data/nyct/subway/google_transit.zip',
        # PATH (Port Authority Trans-Hudson)
        'https://data.trilliumtransit.com/gtfs/path-nj-us/path-nj-us.zip'
    ],
    'san francisco': ['https://gtfs.bart.gov/GTFS/google_transit.zip']
}

class GTFSLoader:
    def __init__(self, city_name):
        self.city_name = city_name.lower()
        self.feeds = []
        for key, urls in GTFS_FEEDS.items():
            if key in self.city_name:
                self.feeds = urls
                break
        
        # Storing the combined data
        self.stops = pd.DataFrame()
        self.stop_times = pd.DataFrame()
        self.trips = pd.DataFrame()

    def load_data(self):
        """Downloads and merges ALL feeds for the city."""
        if not self.feeds:
            raise FileNotFoundError(f"No GTFS registry entry for {self.city_name}")

        all_stops = []
        all_stop_times = []
        all_trips = []

        for i, url in enumerate(self.feeds):
            print(f"[GTFS] Processing Feed {i+1}/{len(self.feeds)}: {url}")
            try:
                # 1. Download
                response = requests.get(url)
                if response.status_code != 200:
                    print(f"[GTFS] Failed to download {url}")
                    continue
                
                zip_file = zipfile.ZipFile(BytesIO(response.content))
                
                # 2. Extract to Pandas (in memory)
                # Prefix IDs with the feed index (0_, 1_) to prevent collisions
                # e.g. If both feeds have stop_id "1", they become "0_1" and "1_1".
                prefix = f"{i}_"
                
                # STOPS
                with zip_file.open('stops.txt') as f:
                    df_stops = pd.read_csv(f)
                    df_stops['stop_id'] = prefix + df_stops['stop_id'].astype(str)
                    # Standardize columns
                    if 'stop_lat' in df_stops.columns:
                        df_stops = df_stops.rename(columns={'stop_lat': 'lat', 'stop_lon': 'lon'})
                    all_stops.append(df_stops[['stop_id', 'lat', 'lon']])

                # TRIPS
                with zip_file.open('trips.txt') as f:
                    df_trips = pd.read_csv(f)
                    df_trips['trip_id'] = prefix + df_trips['trip_id'].astype(str)
                    df_trips['route_id'] = prefix + df_trips['route_id'].astype(str)
                    all_trips.append(df_trips)

                # STOP TIMES
                with zip_file.open('stop_times.txt') as f:
                    df_st = pd.read_csv(f)
                    df_st['trip_id'] = prefix + df_st['trip_id'].astype(str)
                    df_st['stop_id'] = prefix + df_st['stop_id'].astype(str)
                    
                    # Optimization: Only keep what we need
                    all_stop_times.append(df_st[['trip_id', 'stop_id', 'arrival_time', 'stop_sequence']])
                    
            except Exception as e:
                print(f"[GTFS] Error processing feed {url}: {e}")

        # 3. Merge
        if all_stops:
            self.stops = pd.concat(all_stops, ignore_index=True)
            self.trips = pd.concat(all_trips, ignore_index=True)
            self.stop_times = pd.concat(all_stop_times, ignore_index=True)
            
            print(f"[GTFS] Merged Data: {len(self.stops)} stops, {len(self.stop_times)} schedules.")
        else:
            raise Exception("No GTFS data could be loaded.")

    def get_transit_edges(self):
        """
        Calculates edges between stops based on trip schedules.
        Returns: List of dicts {'stop_id', 'next_stop_id', 'duration'}
        """
        if self.stop_times.empty: return []

        # Sort by trip and sequence
        print("[GTFS] Sorting schedules...")
        df = self.stop_times.sort_values(['trip_id', 'stop_sequence'])
        
        # Shift to get next stop
        df['next_stop_id'] = df.groupby('trip_id')['stop_id'].shift(-1)
        df['next_arrival'] = df.groupby('trip_id')['arrival_time'].shift(-1)
        
        # Drop last stops
        df = df.dropna(subset=['next_stop_id'])
        
        # Calculate duration (simplified for now)
        # In the future I want to parse "HH:MM:SS", but for now I just take the average.
        # Grouping by the edge (u, v) and count frequencies.
        
        # Assuming a standard 2-minute time
        
        edges = []
        unique_links = df[['stop_id', 'next_stop_id']].drop_duplicates()
        
        for _, row in unique_links.iterrows():
            edges.append({
                'stop_id': row['stop_id'],
                'next_stop_id': row['next_stop_id'],
                'duration': 2.0 # Default 2 mins between stops
            })
            
        return edges