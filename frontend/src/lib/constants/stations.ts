export interface Station {
  key: string;
  name: string;
  lat: number;
  lon: number;
  openaqHint: string;
  distRoadKm: number;
  notes: string;
}

export const KOLKATA_STATIONS: Record<string, Station> = {
  victoria_memorial: {
    key: "victoria_memorial",
    name: "Victoria Memorial",
    lat: 22.5448,
    lon: 88.3426,
    openaqHint: "victoria",
    distRoadKm: 0.35,
    notes: "Central Kolkata, heavy traffic ring around the monument."
  },
  jadavpur: {
    key: "jadavpur",
    name: "Jadavpur",
    lat: 22.4989,
    lon: 88.3717,
    openaqHint: "jadavpur",
    distRoadKm: 0.6,
    notes: "South Kolkata, university campus, residential + small industry."
  },
  rabindra_bharati: {
    key: "rabindra_bharati",
    name: "Rabindra Bharati University",
    lat: 22.5839,
    lon: 88.3617,
    openaqHint: "rabindra",
    distRoadKm: 0.25,
    notes: "North Kolkata, dense old-city fabric, near B.T. Road corridor."
  },
  ballygunge: {
    key: "ballygunge",
    name: "Ballygunge",
    lat: 22.5283,
    lon: 88.365,
    openaqHint: "ballygunge",
    distRoadKm: 0.45,
    notes: "South-central, residential with commercial frontage."
  },
  fort_william: {
    key: "fort_william",
    name: "Fort William",
    lat: 22.5551,
    lon: 88.3388,
    openaqHint: "fort william",
    distRoadKm: 0.9,
    notes: "Open ground inside the fort - lowest traffic influence of the set."
  },
  bidhannagar: {
    key: "bidhannagar",
    name: "Bidhannagar",
    lat: 22.58,
    lon: 88.41,
    openaqHint: "bidhannagar",
    distRoadKm: 1.2,
    notes: "Salt Lake / New Town edge, more construction dust."
  }
};

export const STATION_KEYS = Object.keys(KOLKATA_STATIONS);
// The current demo/live dataset only covers 4 stations (not fort_william/bidhannagar).
// Default selection matches the dataset so filters don't silently no-op.
export const DATASET_STATION_KEYS = ["victoria_memorial", "jadavpur", "rabindra_bharati", "ballygunge"];
export const DEFAULT_MAP_CENTER = { lat: 22.5448, lon: 88.3626, zoom: 11.5 };

