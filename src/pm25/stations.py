"""Kolkata CAAQMS station registry.

Coordinates are approximate and rounded to 4 decimals - good enough for
satellite buffers (5 km) and ERA5 cells (9 km), but VERIFY each one against
the CPCB station list before publishing. A station placed on the wrong side of
a road changes its road-proximity proxy.

`openaq_hint` is a lowercase fragment used to match the station against
OpenAQ location names, which are inconsistent across sources.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Station:
    key: str
    name: str
    lat: float
    lon: float
    openaq_hint: str
    notes: str = ""


KOLKATA_STATIONS: dict[str, Station] = {
    "victoria_memorial": Station(
        key="victoria_memorial",
        name="Victoria Memorial",
        lat=22.5448,
        lon=88.3426,
        openaq_hint="victoria",
        notes="Central Kolkata, heavy traffic ring around the monument.",
    ),
    "jadavpur": Station(
        key="jadavpur",
        name="Jadavpur",
        lat=22.4989,
        lon=88.3717,
        openaq_hint="jadavpur",
        notes="South Kolkata, university campus, residential + small industry.",
    ),
    "rabindra_bharati": Station(
        key="rabindra_bharati",
        name="Rabindra Bharati University",
        lat=22.5839,
        lon=88.3617,
        openaq_hint="rabindra",
        notes="North Kolkata, dense old-city fabric, near B.T. Road corridor.",
    ),
    "ballygunge": Station(
        key="ballygunge",
        name="Ballygunge",
        lat=22.5283,
        lon=88.3650,
        openaq_hint="ballygunge",
        notes="South-central, residential with commercial frontage.",
    ),
    "fort_william": Station(
        key="fort_william",
        name="Fort William",
        lat=22.5551,
        lon=88.3388,
        openaq_hint="fort william",
        notes="Open ground inside the fort - lowest traffic influence of the set.",
    ),
    "bidhannagar": Station(
        key="bidhannagar",
        name="Bidhannagar",
        lat=22.5800,
        lon=88.4100,
        openaq_hint="bidhannagar",
        notes="Salt Lake / New Town edge, more construction dust.",
    ),
}

# Fallback road distances (km to the nearest national/state highway) used when
# the OSM adapter is unavailable. Rough, but stable and documented.
FALLBACK_ROAD_KM: dict[str, float] = {
    "victoria_memorial": 0.35,
    "jadavpur": 0.60,
    "rabindra_bharati": 0.25,
    "ballygunge": 0.45,
    "fort_william": 0.90,
    "bidhannagar": 1.20,
}


def get_stations(keys: list[str]) -> list[Station]:
    missing = [k for k in keys if k not in KOLKATA_STATIONS]
    if missing:
        raise KeyError(
            f"Unknown station key(s): {missing}. "
            f"Available: {sorted(KOLKATA_STATIONS)}"
        )
    return [KOLKATA_STATIONS[k] for k in keys]


def stations_frame(keys: list[str]):
    import pandas as pd

    rows = []
    for st in get_stations(keys):
        rows.append(
            {
                "station": st.key,
                "station_name": st.name,
                "lat": st.lat,
                "lon": st.lon,
                "dist_road_km": FALLBACK_ROAD_KM.get(st.key, 0.8),
            }
        )
    return pd.DataFrame(rows)
