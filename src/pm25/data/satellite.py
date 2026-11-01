"""Satellite features from Google Earth Engine.

IMPORTANT - resolution reality check
------------------------------------
AOD is **not** an hourly product. MODIS/MAIAC (MCD19A2) is one retrieval per
day per overpass at 1 km; VIIRS is similar; TROPOMI NO2 is a single ~13:30
overpass. Any "hourly PM2.5" model therefore uses *daily* satellite features
joined onto every hour of that day, and gets its hourly variation from
meteorology, time-of-day and lagged PM2.5. Claiming otherwise in a report is
the fastest way to get the method section torn apart.

Consequence for validation: a same-day AOD feature is only legitimate for a
nowcast. For a +24 h forecast the previous day's AOD is used instead - see
`features.make_features`, which enforces this.

Requires: `pip install earthengine-api`, then `earthengine authenticate`, and
GEE_PROJECT set in .env.
"""

from __future__ import annotations

import os

import pandas as pd

from ..stations import get_stations
from ..utils import get_logger

log = get_logger("pm25.satellite")

AOD_SCALE = 0.001          # MCD19A2 scale factor
NO2_SCALE = 1e-6           # mol/m2


def _init_ee():
    try:
        import ee
    except ImportError as exc:
        raise RuntimeError(
            "Satellite features need `pip install earthengine-api` and a one-time "
            "`earthengine authenticate`. Or set satellite.provider: none."
        ) from exc

    project = os.environ.get("GEE_PROJECT", "").strip()
    try:
        ee.Initialize(project=project) if project else ee.Initialize()
    except Exception as exc:
        raise RuntimeError(
            f"Earth Engine init failed ({exc}). Run `earthengine authenticate` once, "
            "then set GEE_PROJECT in .env."
        ) from exc
    return ee


def _station_fc(ee, cfg, buffer_m: int):
    stations = get_stations(cfg.get("data.stations"))
    features = [
        ee.Feature(ee.Geometry.Point([s.lon, s.lat]).buffer(buffer_m), {"station": s.key})
        for s in stations
    ]
    return ee.FeatureCollection(features)


def _month_chunks(start: pd.Timestamp, end: pd.Timestamp):
    cursor = start.replace(day=1)
    while cursor <= end:
        nxt = (cursor + pd.offsets.MonthBegin(1)).normalize()
        yield cursor.strftime("%Y-%m-%d"), min(nxt, end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        cursor = nxt


def _daily_reduce(ee, daily_ic, fc, scale: int) -> pd.DataFrame:
    """Server-side reduceRegions over every image, then one getInfo per chunk."""

    def per_image(image):
        date = image.get("date")
        reduced = image.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=scale)
        return reduced.map(lambda f: f.set("date", date))

    flattened = daily_ic.map(per_image).flatten()
    info = flattened.getInfo()
    rows = [f["properties"] for f in info.get("features", [])]
    return pd.DataFrame(rows)


def _aod_daily(ee, cfg, fc, start: str, end: str):
    collection = (
        ee.ImageCollection(cfg.get("satellite.aod_collection"))
        .filterDate(start, end)
        .select(["Optical_Depth_047", "AOD_QA"])
    )

    def mask(image):
        qa = image.select("AOD_QA")
        clear = qa.bitwiseAnd(7).eq(0)          # bits 0-2: cloud / adjacency mask
        aod = image.select("Optical_Depth_047").updateMask(clear).multiply(AOD_SCALE)
        return aod.rename("aod")

    masked = collection.map(mask)
    days = ee.List.sequence(
        0, ee.Date(end).difference(ee.Date(start), "day").subtract(1)
    )

    def per_day(offset):
        day = ee.Date(start).advance(offset, "day")
        image = masked.filterDate(day, day.advance(1, "day")).mean()
        return image.set("date", day.format("YYYY-MM-dd"))

    return ee.ImageCollection(days.map(per_day))


def _no2_daily(ee, cfg, fc, start: str, end: str):
    collection = (
        ee.ImageCollection(cfg.get("satellite.no2_collection"))
        .filterDate(start, end)
        .select(cfg.get("satellite.no2_band"))
    )
    days = ee.List.sequence(
        0, ee.Date(end).difference(ee.Date(start), "day").subtract(1)
    )

    def per_day(offset):
        day = ee.Date(start).advance(offset, "day")
        image = collection.filterDate(day, day.advance(1, "day")).mean()
        return image.multiply(NO2_SCALE).rename("no2_sat").set("date", day.format("YYYY-MM-dd"))

    return ee.ImageCollection(days.map(per_day))


def fetch(cfg) -> pd.DataFrame:
    provider = str(cfg.get("satellite.provider", "gee")).lower()
    if provider == "none":
        log.info("satellite.provider = none, skipping satellite features")
        return pd.DataFrame(columns=["time", "station", "aod", "no2_sat"])

    ee = _init_ee()
    buffer_m = int(cfg.get("satellite.buffer_m", 5000))
    fc = _station_fc(ee, cfg, buffer_m)

    start = pd.Timestamp(cfg.get("data.start"))
    end = pd.Timestamp(cfg.get("data.end"))

    frames = []
    for chunk_start, chunk_end in _month_chunks(start, end):
        log.info("GEE %s .. %s", chunk_start, chunk_end)

        aod_ic = _aod_daily(ee, cfg, fc, chunk_start, chunk_end)
        aod = _daily_reduce(ee, aod_ic, fc, scale=1000)

        no2_ic = _no2_daily(ee, cfg, fc, chunk_start, chunk_end)
        no2 = _daily_reduce(ee, no2_ic, fc, scale=1000)

        merged = aod.merge(no2, on=["station", "date"], how="outer")
        frames.append(merged)

    out = pd.concat(frames, ignore_index=True)
    out["time"] = pd.to_datetime(out["date"], utc=True)
    out = out.drop(columns=["date"], errors="ignore")

    for col in ("aod", "no2_sat"):
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    log.info("GEE: %d station-days, AOD present on %.1f%%",
             len(out), 100 * out["aod"].notna().mean() if "aod" in out else 0.0)
    return out


def expand_daily_to_hourly(daily: pd.DataFrame, hourly_index: pd.DataFrame) -> pd.DataFrame:
    """Broadcast daily satellite values onto every hour of that day."""
    if daily.empty:
        return hourly_index.assign(aod=pd.NA, no2_sat=pd.NA)

    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["time"], utc=True).dt.floor("D")

    hourly = hourly_index.copy()
    hourly["date"] = pd.to_datetime(hourly["time"], utc=True).dt.floor("D")

    cols = [c for c in ("aod", "no2_sat") if c in daily.columns]
    return hourly.merge(daily[["station", "date"] + cols], on=["station", "date"], how="left").drop(
        columns=["date"]
    )
