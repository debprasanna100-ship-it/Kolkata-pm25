"""OpenAQ v3 client for CPCB CAAQMS data.

OpenAQ mirrors the CPCB feed, which is the only practical way to get Kolkata
station data programmatically - the CPCB portal itself has no open API and
blocks scripted access. If you need the official numbers, download the CSV
from cpcbccr.com by hand and use `load_cpcb_csv()`.

Requires OPENAQ_API_KEY (free: https://explore.openaq.org/register).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from ..stations import Station, get_stations
from ..utils import ensure_dir, get_logger

log = get_logger("pm25.openaq")

BASE = "https://api.openaq.org/v3"
PARAMETER_IDS = {"pm25": 2, "pm10": 1, "no2": 7, "so2": 9, "co": 8, "o3": 10}


class OpenAQError(RuntimeError):
    pass


def _session() -> requests.Session:
    key = os.environ.get("OPENAQ_API_KEY", "").strip()
    if not key:
        raise OpenAQError(
            "OPENAQ_API_KEY is not set. Get a free key at https://explore.openaq.org/register "
            "and put it in .env, or run with --mode demo."
        )
    session = requests.Session()
    session.headers.update({"X-API-Key": key, "Accept": "application/json"})
    return session


def _get(session: requests.Session, url: str, params: dict, retries: int = 4) -> dict:
    for attempt in range(retries):
        response = session.get(url, params=params, timeout=60)
        if response.status_code == 200:
            return response.json()
        if response.status_code == 429:
            wait = 2**attempt
            log.warning("rate limited, sleeping %ds", wait)
            time.sleep(wait)
            continue
        raise OpenAQError(f"{response.status_code} for {url}: {response.text[:300]}")
    raise OpenAQError(f"gave up on {url}")


def find_locations(session, station: Station, radius_m: int = 25000) -> list[dict]:
    payload = _get(
        session,
        f"{BASE}/locations",
        {"coordinates": f"{station.lat},{station.lon}", "radius": radius_m, "limit": 100},
    )
    results = payload.get("results", [])
    hint = station.openaq_hint
    matched = [r for r in results if hint in str(r.get("name", "")).lower()]
    return matched or results[:3]


def _sensor_ids(location: dict, parameters: list[str]) -> dict[str, int]:
    wanted = {PARAMETER_IDS[p] for p in parameters if p in PARAMETER_IDS}
    out = {}
    for sensor in location.get("sensors", []) or []:
        pid = (sensor.get("parameter") or {}).get("id")
        name = (sensor.get("parameter") or {}).get("name")
        if pid in wanted and name:
            out[name] = sensor.get("id")
    return out


def fetch_sensor(session, sensor_id: int, start: datetime, end: datetime) -> pd.DataFrame:
    """Hourly series for one sensor, paginated."""
    rows: list[dict] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=30), end)
        page = 1
        while True:
            payload = _get(
                session,
                f"{BASE}/sensors/{sensor_id}/measurements",
                {
                    "datetime_from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "datetime_to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "limit": 1000,
                    "page": page,
                },
            )
            results = payload.get("results", [])
            if not results:
                break
            for item in results:
                period = item.get("period") or {}
                stamp = (period.get("datetimeFrom") or {}).get("utc")
                rows.append({"time": stamp, "value": item.get("value")})
            if len(results) < 1000:
                break
            page += 1
            if page > 60:
                break
        cursor = chunk_end
        time.sleep(0.2)
    return pd.DataFrame(rows)


def fetch(cfg) -> pd.DataFrame:
    """Ground truth for every configured station."""
    session = _session()
    station_keys = cfg.get("data.stations")
    parameters = ["pm25"] + [p for p in cfg.get("data.extra_pollutants", []) if p in PARAMETER_IDS]
    start = pd.Timestamp(cfg.get("data.start")).to_pydatetime()
    end = pd.Timestamp(cfg.get("data.end")).to_pydatetime()

    frames = []
    for station in get_stations(station_keys):
        locations = find_locations(session, station)
        if not locations:
            log.warning("no OpenAQ location near %s", station.key)
            continue

        location = locations[0]
        log.info("%s -> OpenAQ location %s (%s)", station.key, location.get("id"), location.get("name"))

        sensors = _sensor_ids(location, parameters)
        if not sensors:
            log.warning("no matching sensors at %s", location.get("name"))
            continue

        merged: pd.DataFrame | None = None
        for name, sensor_id in sensors.items():
            series = fetch_sensor(session, sensor_id, start, end)
            if series.empty:
                continue
            series["time"] = pd.to_datetime(series["time"], utc=True, errors="coerce")
            series = series.dropna(subset=["time"])
            # CPCB reports hourly means; collapse duplicates defensively.
            series = series.groupby("time", as_index=False)["value"].mean()
            series = series.rename(columns={"value": name})
            merged = series if merged is None else merged.merge(series, on="time", how="outer")

        if merged is None:
            continue

        merged["station"] = station.key
        merged["station_name"] = station.name
        merged["lat"] = station.lat
        merged["lon"] = station.lon
        frames.append(merged)
        time.sleep(1.0)

    if not frames:
        raise OpenAQError("No station data retrieved. Check the station keys and the API key.")

    out = pd.concat(frames, ignore_index=True).sort_values(["station", "time"])
    log.info("OpenAQ: %d rows across %d stations", len(out), out["station"].nunique())
    return out.reset_index(drop=True)


def load_cpcb_csv(path: str, station_key: str, station_name: str, lat: float, lon: float) -> pd.DataFrame:
    """Adapter for a manually downloaded CPCB CSV export.

    CPCB exports vary; this expects at least a timestamp column and a PM2.5
    column. Edit the rename map to match your file.
    """
    raw = pd.read_csv(path)
    rename = {}
    for col in raw.columns:
        low = col.lower()
        if "pm2.5" in low or "pm25" in low:
            rename[col] = "pm25"
        elif "pm10" in low:
            rename[col] = "pm10"
        elif "no2" in low:
            rename[col] = "no2"
        elif "timestamp" in low or "date" in low:
            rename[col] = "time"
    raw = raw.rename(columns=rename)
    if "time" not in raw or "pm25" not in raw:
        raise ValueError(f"Could not find time/pm25 columns in {path}. Columns: {list(raw.columns)}")

    raw["time"] = pd.to_datetime(raw["time"], utc=True, errors="coerce")
    raw = raw.dropna(subset=["time"])
    raw["station"] = station_key
    raw["station_name"] = station_name
    raw["lat"] = lat
    raw["lon"] = lon
    return raw
