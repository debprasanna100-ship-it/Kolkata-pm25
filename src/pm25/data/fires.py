"""NASA FIRMS fire detections, converted into an upwind transport signal.

Raw fire counts are a weak feature: 200 fires 600 km away and downwind mean
nothing. What matters is fires *upwind of the station right now*. So the daily
count is modulated by the cosine of the angle between the wind direction and
the bearing to the fire cluster, clipped to zero when the wind is blowing the
other way.

That single transformation is usually what makes the biomass-burning signal
show up in a model at all.
"""

from __future__ import annotations

import io
import os
import time

import numpy as np
import pandas as pd
import requests

from ..stations import Station, get_stations
from ..utils import ensure_dir, get_logger

log = get_logger("pm25.firms")

AREA_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def fetch(cfg) -> pd.DataFrame:
    """Daily fire detections inside the configured bbox.

    Returns columns: date, fire_count, fire_lat, fire_lon (cluster centroid).

    Each 5-day chunk is cached under data/raw/firms_cache/ - the walk from
    `data.start` to `data.end` is ~120 requests, and rerunning the build
    should not re-pay them.
    """
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        log.warning("FIRMS_MAP_KEY not set - fire features will be zero. "
                    "Free key: https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        return pd.DataFrame(columns=["date", "fire_count", "fire_lat", "fire_lon"])

    source = cfg.get("fires.source", "VIIRS_SNPP_NRT")
    west, south, east, north = cfg.get("fires.bbox", [85.0, 20.5, 92.0, 25.5])
    start = pd.Timestamp(cfg.get("data.start"))
    end = pd.Timestamp(cfg.get("data.end"))
    cache_dir = ensure_dir(cfg.path("raw") / "firms_cache")

    frames = []
    cursor = start
    while cursor < end:
        span = min(5, (end - cursor).days + 1)          # area API caps at 10 days
        cache_file = cache_dir / f"{source}_{cursor:%Y%m%d}.csv"

        if cache_file.exists():
            chunk = pd.read_csv(cache_file)
            if not chunk.empty:
                frames.append(chunk)
        else:
            url = f"{AREA_API}/{key}/{source}/{west},{south},{east},{north}/{span}/{cursor.date()}"
            response = requests.get(url, timeout=120)

            if response.status_code == 200 and response.text.strip():
                try:
                    chunk = pd.read_csv(io.StringIO(response.text))
                    # Cache the raw response verbatim - including "no data"
                    # days - so a rerun never re-requests a span.
                    cache_file.write_text(response.text, encoding="utf-8")
                    if "latitude" in chunk:
                        frames.append(chunk)
                except Exception as exc:
                    log.warning("could not parse FIRMS chunk %s: %s", cursor.date(), exc)
            else:
                log.warning("FIRMS %s -> HTTP %s (chunk left uncached)", cursor.date(),
                            response.status_code)

        cursor += pd.Timedelta(days=span)
        time.sleep(1.0)

    if not frames:
        return pd.DataFrame(columns=["date", "fire_count", "fire_lat", "fire_lon"])

    raw = pd.concat(frames, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["acq_date"], utc=True, errors="coerce").dt.floor("D")
    raw = raw.dropna(subset=["date"])

    # High-confidence detections only; low-confidence VIIRS pixels are mostly
    # hot roofs and industrial flares in this region.
    if "confidence" in raw:
        conf = pd.to_numeric(raw["confidence"], errors="coerce")
        raw = raw[(conf.isna()) | (conf >= 60)]

    daily = raw.groupby("date").agg(
        fire_count=("latitude", "size"),
        fire_lat=("latitude", "mean"),
        fire_lon=("longitude", "mean"),
    ).reset_index()

    log.info("FIRMS: %d detections over %d days", len(raw), len(daily))
    return daily


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees CW from north."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dlambda = np.radians(lon2 - lon1)
    y = np.sin(dlambda) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlambda)
    return (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0


def add_upwind_features(hourly: pd.DataFrame, fires: pd.DataFrame, cfg) -> pd.DataFrame:
    """Merge daily counts and modulate by wind alignment, per hour."""
    out = hourly.copy()

    if fires.empty:
        out["fire_count"] = 0.0
        out["fire_upwind"] = 0.0
        return out

    fires = fires.copy()
    fires["date"] = pd.to_datetime(fires["date"], utc=True).dt.floor("D")
    out["date"] = pd.to_datetime(out["time"], utc=True).dt.floor("D")

    # One bearing per station per day, to the centroid of that day's detections.
    bearings = {}
    for station_key, group in out.groupby("station"):
        station = next(s for s in get_stations([station_key]))
        per_day = fires.apply(
            lambda row: _bearing(station.lat, station.lon, row["fire_lat"], row["fire_lon"]),
            axis=1,
        )
        bearings[station_key] = pd.Series(per_day.to_numpy(), index=fires["date"]).groupby(level=0).mean()

    out["fire_count"] = 0.0
    out["fire_upwind"] = 0.0

    merged = out.merge(
        fires[["date", "fire_count"]].rename(columns={"fire_count": "fire_count_day"}),
        on="date",
        how="left",
    )
    merged["fire_count_day"] = merged["fire_count_day"].fillna(0.0)
    out["fire_count"] = merged["fire_count_day"].to_numpy()

    for station_key, idx in out.groupby("station").groups.items():
        table = bearings[station_key]
        # Days without detections have no bearing. Fill from the nearest day
        # that had fires: the cluster did not move, there was just nothing
        # detected (cloud, off-cycle burning). Filling with 0 instead would
        # create a phantom source at due north whose alignment (cos 315° ≈ 0.7)
        # leaks into the neighbouring fire day's tail through the smoothing
        # below. Fire count stays zero on those days, so this only affects
        # alignment, never the transport itself.
        all_dates = pd.DatetimeIndex(sorted(out.loc[idx, "date"].unique()))
        table = table.reindex(all_dates).ffill().bfill()

        dates = out.loc[idx, "date"]
        bearing = dates.map(table).astype(float).fillna(0.0).to_numpy()

        wind_from = out.loc[idx, "wind_dir"].astype(float)
        # Wind blowing FROM the bearing means the source is upwind. Transport
        # integrates over several hours, not the instantaneous wind - letting
        # the alignment swing hour by hour makes fire_upwind flicker and loses
        # the signal. Smooth the same way the synthetic generator does (6 h,
        # centred), so live features and demo data share one definition.
        alignment = np.clip(np.cos(np.radians(wind_from - bearing)), 0, 1)
        alignment = alignment.rolling(6, min_periods=1, center=True).mean()
        out.loc[idx, "fire_upwind"] = out.loc[idx, "fire_count"] * alignment

    return out.drop(columns=["date"])
