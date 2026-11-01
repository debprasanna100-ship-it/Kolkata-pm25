"""Weather: Open-Meteo (default, no key) or ERA5 via Copernicus CDS.

Open-Meteo is the default because it needs no account and returns clean hourly
JSON. Its archive is ERA5/ERA5-Land underneath, so the meteorology is the same
product - what it does *not* expose is boundary layer height.

PBL matters more than any other single meteorological variable for PM2.5: a
shallow winter boundary layer is the physical reason pollution accumulates.
If you want the real thing, use provider: era5 (free CDS account, ~1 min per
station-year). Otherwise `pbl` stays NaN and the feature pipeline imputes it,
which the model handles but which costs you accuracy on exactly the winter
episodes you care about.
"""

from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd
import requests

from ..stations import Station, get_stations
from ..utils import get_logger

log = get_logger("pm25.weather")

OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

OPEN_METEO_HOURLY = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
    "cloud_cover",
    # Requested opportunistically; ignored if the endpoint does not return it.
    "boundary_layer_height",
]


def _meteo_to_uv(speed: np.ndarray, direction_from: np.ndarray):
    """Meteorological direction (FROM, degrees CW from N) -> u (east), v (north)."""
    rad = np.radians(direction_from)
    u = -speed * np.sin(rad)
    v = -speed * np.cos(rad)
    return u, v


def fetch_openmeteo(cfg) -> pd.DataFrame:
    station_keys = cfg.get("data.stations")
    start = pd.Timestamp(cfg.get("data.start")).date().isoformat()
    end = pd.Timestamp(cfg.get("data.end")).date().isoformat()

    frames = []
    for station in get_stations(station_keys):
        params = {
            "latitude": station.lat,
            "longitude": station.lon,
            "start_date": start,
            "end_date": end,
            "hourly": ",".join(OPEN_METEO_HOURLY),
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        }
        for attempt in range(4):
            response = requests.get(OPEN_METEO_ARCHIVE, params=params, timeout=120)
            if response.status_code == 200:
                break
            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"Open-Meteo {response.status_code}: {response.text[:200]}")
        if response.status_code != 200:
            # All attempts were rate limited; without this the .json() call
            # below would fail with an opaque parse error on the 429 body.
            raise RuntimeError(
                f"Open-Meteo kept returning 429 for {station.key} after 4 attempts - "
                "wait a minute and retry, or set weather.provider: era5."
            )

        payload = response.json().get("hourly", {})
        if not payload:
            log.warning("Open-Meteo returned nothing for %s", station.key)
            continue

        frame = pd.DataFrame({"time": pd.to_datetime(payload["time"], utc=True)})
        frame["temp"] = payload.get("temperature_2m")
        frame["rh"] = payload.get("relative_humidity_2m")
        frame["wind_speed"] = payload.get("wind_speed_10m")
        frame["wind_dir"] = payload.get("wind_direction_10m")
        frame["precip"] = payload.get("precipitation")
        frame["cloud"] = payload.get("cloud_cover")
        frame["pbl"] = payload.get("boundary_layer_height")  # often absent

        if frame["pbl"].isna().all():
            log.warning(
                "%s: boundary_layer_height not provided by Open-Meteo archive. "
                "Set weather.provider: era5 to get it.", station.key
            )

        frame["wind_u"], frame["wind_v"] = _meteo_to_uv(
            frame["wind_speed"].to_numpy(dtype=float), frame["wind_dir"].to_numpy(dtype=float)
        )
        frame["station"] = station.key
        frames.append(frame)
        time.sleep(0.5)

    if not frames:
        raise RuntimeError("Open-Meteo returned no data for any station.")

    out = pd.concat(frames, ignore_index=True)
    log.info("Open-Meteo: %d hourly rows", len(out))
    return out


def fetch_era5(cfg) -> pd.DataFrame:
    """ERA5 single-level hourly. Requires `pip install cdsapi xarray netcdf4`."""
    try:
        import cdsapi
        import xarray as xr
    except ImportError as exc:
        raise RuntimeError(
            "ERA5 needs `pip install cdsapi xarray netcdf4` and a ~/.cdsapirc file."
        ) from exc

    station_keys = cfg.get("data.stations")
    stations = get_stations(station_keys)
    start = pd.Timestamp(cfg.get("data.start"))
    end = pd.Timestamp(cfg.get("data.end"))

    # One request covering all stations (a small box around Kolkata) is far
    # cheaper than one request per station.
    lats = [s.lat for s in stations]
    lons = [s.lon for s in stations]
    area = [max(lats) + 0.15, min(lons) - 0.15, min(lats) - 0.15, max(lons) + 0.15]

    variables = [
        "2m_temperature",
        "2m_dewpoint_temperature",
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
        "boundary_layer_height",
        "total_precipitation",
        "total_cloud_cover",
    ]

    target = cfg.path("raw") / "era5_kolkata.nc"
    if not target.exists():
        log.info("requesting ERA5 %s..%s (this can take a few minutes)", start.date(), end.date())
        client = cdsapi.Client()
        client.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "variable": variables,
                "year": sorted({str(y) for y in range(start.year, end.year + 1)}),
                "month": [f"{m:02d}" for m in range(1, 13)],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "time": [f"{h:02d}:00" for h in range(24)],
                "area": area,
                "format": "netcdf",
            },
            str(target),
        )

    ds = xr.open_dataset(target)
    frames = []
    for station in stations:
        point = ds.sel(latitude=station.lat, longitude=station.lon, method="nearest")
        frame = pd.DataFrame(
            {
                "time": pd.to_datetime(point["time"].values, utc=True),
                "temp": point["t2m"].values - 273.15,
                "dewpoint": point["d2m"].values - 273.15,
                "wind_u": point["u10"].values,
                "wind_v": point["v10"].values,
                "pbl": point["blh"].values,
                "precip": point["tp"].values * 1000.0,   # m -> mm
                "cloud": point["tcc"].values,
            }
        )
        frame["rh"] = _rh_from_dewpoint(frame["temp"].to_numpy(), frame["dewpoint"].to_numpy())
        frame["wind_speed"] = np.hypot(frame["wind_u"], frame["wind_v"])
        frame["wind_dir"] = (270.0 - np.degrees(np.arctan2(frame["wind_v"], frame["wind_u"]))) % 360.0
        frame["station"] = station.key
        frames.append(frame.drop(columns=["dewpoint"]))

    out = pd.concat(frames, ignore_index=True)
    log.info("ERA5: %d hourly rows", len(out))
    return out


def _rh_from_dewpoint(temp_c: np.ndarray, dew_c: np.ndarray) -> np.ndarray:
    """Magnus formula."""
    a, b = 17.625, 243.04
    rh = 100.0 * np.exp((a * dew_c) / (b + dew_c)) / np.exp((a * temp_c) / (b + temp_c))
    return np.clip(rh, 1.0, 100.0)


def fetch(cfg) -> pd.DataFrame:
    provider = str(cfg.get("weather.provider", "openmeteo")).lower()
    if provider == "era5":
        return fetch_era5(cfg)
    if provider == "openmeteo":
        return fetch_openmeteo(cfg)
    raise ValueError(f"Unknown weather.provider: {provider!r} (use 'openmeteo' or 'era5')")
