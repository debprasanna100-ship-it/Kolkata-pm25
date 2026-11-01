"""Road proximity per station, via the OpenStreetMap Overpass API.

Road distance is the cheapest available traffic proxy: it does not vary in
time, but it explains a large share of the between-station PM2.5 differences,
and it makes LOSO validation possible (the model can interpolate to a station
it has never seen, using its road context).

Falls back to a hardcoded table if Overpass is unreachable.
"""

from __future__ import annotations

import math
import time

import requests

from ..stations import FALLBACK_ROAD_KM, get_stations
from ..utils import get_logger

log = get_logger("pm25.roads")

OVERPASS = "https://overpass-api.de/api/interpreter"
HIGHWAY_FILTER = "motorway|trunk|primary|secondary"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_major_road_km(lat: float, lon: float, radius_m: int = 5000) -> float | None:
    query = f"""
    [out:json][timeout:90];
    way(around:{radius_m},{lat},{lon})["highway"~"^({HIGHWAY_FILTER})$"];
    out geom;
    """
    # Short timeouts on purpose: this is a nice-to-have feature with a
    # documented fallback table. A dead Overpass should cost a minute, not
    # twenty, before the build moves on.
    for attempt in range(2):
        try:
            response = requests.post(OVERPASS, data={"data": query}, timeout=30)
            if response.status_code != 200:
                time.sleep(2 * (attempt + 1))
                continue

            elements = response.json().get("elements", [])
            best = None
            for way in elements:
                for node in way.get("geometry", []) or []:
                    d = _haversine_km(lat, lon, node["lat"], node["lon"])
                    if best is None or d < best:
                        best = d
            return best
        except Exception as exc:
            log.warning("Overpass attempt %d failed: %s", attempt + 1, exc)
            time.sleep(2 * (attempt + 1))
    return None


def fetch(cfg, stations: list[str] | None = None) -> dict[str, float]:
    """Nearest-major-road distance per station.

    `stations` limits the lookups to stations actually present in the dataset;
    querying a dead station's road context wastes a request and its retries.
    """
    keys = list(stations) if stations else cfg.get("data.stations")
    result: dict[str, float] = {}
    for station in get_stations(keys):
        distance = nearest_major_road_km(station.lat, station.lon)
        if distance is None:
            distance = FALLBACK_ROAD_KM.get(station.key, 0.8)
            log.warning("%s: Overpass unavailable, using fallback %.2f km", station.key, distance)
        else:
            log.info("%s: nearest major road %.2f km", station.key, distance)
        result[station.key] = round(float(distance), 3)
        time.sleep(1.0)
    return result
