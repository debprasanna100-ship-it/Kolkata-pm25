"""Deterministic synthetic Kolkata dataset.

Why this exists
---------------
The real pipeline needs three API keys and a Google Earth Engine account. That
is a terrible first-run experience, and it makes the repo untestable in CI.
This generator produces a dataset with the *same schema and the same causal
structure* as the real one, so:

  * the whole pipeline (features -> models -> SHAP -> dashboard) runs offline,
  * the numbers are plausible enough to sanity-check the analysis,
  * every structural assumption is visible in one file you can argue with.

It is NOT a substitute for real data. Nothing here is a measurement.

Structure that is deliberately encoded
--------------------------------------
  * winter inversion (low boundary layer) drives the annual PM2.5 peak
  * monsoon ventilation + rain washout drives the annual minimum
  * double diurnal peak (morning rush, late evening)
  * monsoon wind reversal: SW in summer, light NE in winter
  * post-monsoon stubble-burning transport, modulated by wind alignment to NW
  * AOD is a *noisy, cloud-gapped* function of PM2.5 - never a clean proxy
  * station-level offsets from road proximity and land use
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..stations import FALLBACK_ROAD_KM, get_stations
from ..utils import get_logger

log = get_logger("pm25.synthetic")

# Station multiplicative offsets (log space). Rough land-use / traffic effect.
STATION_OFFSET = {
    "victoria_memorial": 0.12,
    "jadavpur": 0.05,
    "rabindra_bharati": 0.18,
    "ballygunge": 0.02,
    "fort_william": -0.15,
    "bidhannagar": 0.08,
}

# Tuning constants, grouped so they are easy to argue about.
K = {
    "pm_base": 62.0,          # µg/m³, annual-ish baseline
    "winter_amp": 0.62,       # log-space amplitude of the seasonal cycle
    "diurnal_amp": 0.26,
    "wind_dilution": 0.055,   # per m/s
    "pbl_effect": 0.00034,    # per metre of boundary layer height
    "rh_effect": 0.0055,      # per %RH above 70
    "fire_effect": 0.048,     # per upwind fire detection
    # Weather explains the shape, not the hour-to-hour wiggle. These two terms
    # are what stop the synthetic data from being trivially invertible: with
    # low noise a linear model recovers the generating function and reports
    # R² = 0.99, which no real AOD-PM2.5 study ever achieves.
    "noise_sd": 0.17,
    "ar1": 0.82,
    # Station-specific emissions that no feature observes (a diesel generator,
    # a construction site, a busy junction). This is the main reason a model
    # cannot reach R² = 0.95 on real data.
    "local_sd": 0.12,
    "local_ar1": 0.95,
    # Instrument + sampling error on the reported concentration.
    "measurement_sd": 0.05,
}


def _seasonal(doy: np.ndarray, peak_doy: float) -> np.ndarray:
    """+1 at peak_doy, -1 half a year later."""
    return np.cos(2 * np.pi * (doy - peak_doy) / 365.25)


def _diurnal(hour: np.ndarray, peak_hour: float) -> np.ndarray:
    return np.cos(2 * np.pi * (hour - peak_hour) / 24.0)


def _wind_dir_from_uv(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Meteorological convention: the direction the wind blows FROM, degrees CW from N."""
    return (270.0 - np.degrees(np.arctan2(v, u))) % 360.0


def _ar1_noise(rng: np.random.Generator, n: int, sd: float, rho: float) -> np.ndarray:
    eps = rng.normal(0.0, sd * np.sqrt(1 - rho**2), n)
    out = np.empty(n)
    acc = rng.normal(0.0, sd)
    for i in range(n):
        acc = rho * acc + eps[i]
        out[i] = acc
    return out


def generate(cfg: Config) -> pd.DataFrame:
    seed = int(cfg.get("project.seed", 42))
    start = pd.Timestamp(cfg.get("data.start"))
    end = pd.Timestamp(cfg.get("data.end"))
    station_keys = cfg.get("data.stations")
    stations = get_stations(station_keys)

    times = pd.date_range(start, end, freq="h", tz="UTC")
    n = len(times)
    log.info("Synthetic generator: %d hours x %d stations = %d rows", n, len(stations), n * len(stations))

    doy = times.day_of_year.to_numpy().astype(float)
    hour = times.hour.to_numpy().astype(float)
    dow = times.day_of_week.to_numpy()

    winter = _seasonal(doy, peak_doy=10)        # +1 mid-January
    monsoon = _seasonal(doy, peak_doy=205)      # +1 late July
    pre_monsoon = _seasonal(doy, peak_doy=105)  # +1 mid-April, the dry windy season
    fire_season = _seasonal(doy, peak_doy=310)  # +1 early November

    # ---------------- regional meteorology (shared by all stations) --------
    rng_w = np.random.default_rng(seed)

    temp = (
        26.5
        + 5.5 * _seasonal(doy, peak_doy=145)
        + 3.8 * _diurnal(hour, peak_hour=15)
        - 1.5 * monsoon
        + rng_w.normal(0, 0.6, n)
    )
    rh = np.clip(
        72
        + 10 * monsoon
        - 6 * pre_monsoon
        - 0.55 * (temp - 26.5)
        - 7 * _diurnal(hour, peak_hour=15)
        + rng_w.normal(0, 3, n),
        25,
        99,
    )

    # Wind: SW monsoon in summer, a dry dusty northerly in pre-monsoon,
    # light NE in winter.
    u = 2.6 * monsoon - 1.5 * winter + 1.9 * pre_monsoon + rng_w.normal(0, 1.1, n)
    v = 2.1 * monsoon - 1.0 * winter + 1.3 * pre_monsoon + rng_w.normal(0, 1.1, n)
    wind_speed = np.hypot(u, v)
    wind_dir = _wind_dir_from_uv(u, v)

    day_factor = np.clip(np.sin(2 * np.pi * (hour - 6) / 24.0), 0, None) ** 1.5
    pbl = np.clip(
        (320 + 1250 * day_factor) * (1 - 0.38 * winter) * (1 + 0.22 * monsoon)
        + rng_w.normal(0, 90, n),
        90,
        3200,
    )

    rain_prob = np.clip(0.02 + 0.30 * np.clip(monsoon, 0, 1), 0, 0.6)
    precip = np.where(rng_w.random(n) < rain_prob, rng_w.gamma(1.3, 3.0, n), 0.0)

    cloud = np.clip(0.28 + 0.42 * monsoon + rng_w.normal(0, 0.14, n), 0, 1)

    # Fires to the north-west, transported when the wind is from the NW.
    fire_lambda = np.clip(1.0 + 32.0 * np.clip(fire_season, 0, 1) ** 2, 0, None)
    fire_count = rng_w.poisson(fire_lambda).astype(float)

    # Alignment is smoothed over 6 hours on purpose. Transport integrates over
    # many hours; letting it swing with the instantaneous wind direction makes
    # PM2.5 jump by 5x between consecutive hours, which is not physical and
    # destroys any model's 1-hour skill.
    raw_alignment = np.clip(np.cos(np.radians(wind_dir - 315.0)), 0, 1)
    nw_alignment = (
        pd.Series(raw_alignment).rolling(6, min_periods=1, center=True).mean().to_numpy()
    )
    fire_upwind = fire_count * nw_alignment

    # Traffic proxy: double rush hour, weekdays only.
    weekday = ((dow >= 0) & (dow <= 4)).astype(float)
    rush = np.exp(-((hour - 9.0) ** 2) / 5.0) + 0.85 * np.exp(-((hour - 19.5) ** 2) / 7.0)
    traffic = (0.35 + rush) * (0.55 + 0.45 * weekday)

    frames = []
    for idx, st in enumerate(stations):
        rng = np.random.default_rng(seed + 1000 * (idx + 1))

        # Mechanical dust index: dry + windy. Peaks in pre-monsoon (Mar-May),
        # which is when Kolkata actually sees raised PM10.
        dry_windy = np.clip((wind_speed - 1.5) / 2.5, 0, 1) * np.clip((75.0 - rh) / 25.0, 0, 1)

        # ---------------- PM2.5 -------------------------------------------
        log_pm = (
            np.log(K["pm_base"])
            + K["winter_amp"] * winter
            + K["diurnal_amp"] * (rush / rush.max())
            - K["wind_dilution"] * wind_speed
            - K["pbl_effect"] * (pbl - 600.0)
            + K["rh_effect"] * (rh - 70.0)
            + K["fire_effect"] * fire_upwind
            + 0.12 * dry_windy                                # dust contributes mass too
            + STATION_OFFSET.get(st.key, 0.0)
            + 0.05 * traffic
            - 0.22 * np.clip(precip, 0, 4) / 4.0          # wet deposition
        )
        log_pm = log_pm + _ar1_noise(rng, n, K["noise_sd"], K["ar1"])
        # Unobserved local source: persistent, station-specific, not in any feature.
        log_pm = log_pm + _ar1_noise(rng, n, K["local_sd"], K["local_ar1"])

        pm25 = np.exp(log_pm)
        # Instrument / sampling error on the reported value.
        pm25 = pm25 * np.exp(rng.normal(0, K["measurement_sd"], n))
        pm25 = np.clip(pm25, 4.0, 900.0)

        # ---------------- co-pollutants ------------------------------------
        pm10 = pm25 * (1.55 + 2.6 * dry_windy + rng.normal(0, 0.10, n))
        pm10 = np.clip(pm10, pm25 * 1.05, None)

        log_no2 = (
            np.log(14.0)
            + 0.55 * traffic
            + 0.30 * winter
            - 0.045 * wind_speed
            - 0.00028 * (pbl - 600.0)
            + 0.30 * STATION_OFFSET.get(st.key, 0.0) * 3
            + _ar1_noise(rng, n, 0.10, 0.7)
        )
        no2 = np.clip(np.exp(log_no2), 2.0, 260.0)

        so2 = np.clip(np.exp(np.log(6.0) + 0.25 * winter - 0.03 * wind_speed + _ar1_noise(rng, n, 0.12, 0.6)), 0.5, 90)
        co = np.clip(np.exp(np.log(0.55) + 0.35 * winter + 0.30 * traffic + _ar1_noise(rng, n, 0.09, 0.7)), 0.05, 8.0)
        o3 = np.clip(
            np.exp(np.log(28.0) + 0.35 * _diurnal(hour, peak_hour=15) - 0.20 * winter - 0.05 * no2 / 20 + _ar1_noise(rng, n, 0.12, 0.6)),
            2.0, 200.0,
        )

        # ---------------- satellite AOD ------------------------------------
        # Noisy, cloud-gapped. This is the single biggest reason real models
        # cap out around R² = 0.6-0.75 rather than 0.95.
        aod_true = 0.06 + 0.0019 * pm25 + 0.05 * rh / 100.0
        aod = aod_true * np.exp(rng.normal(0, 0.22, n))
        cloud_gap = rng.random(n) < np.clip(cloud - 0.15, 0, 0.95)
        aod = np.where(cloud_gap, np.nan, np.round(np.clip(aod, 0, 4.0), 3))

        df = pd.DataFrame(
            {
                "time": times,
                "station": st.key,
                "station_name": st.name,
                "lat": st.lat,
                "lon": st.lon,
                "pm25": np.round(pm25, 1),
                "pm10": np.round(pm10, 1),
                "no2": np.round(no2, 1),
                "so2": np.round(so2, 1),
                "co": np.round(co, 3),
                "o3": np.round(o3, 1),
                "temp": np.round(temp + rng.normal(0, 0.4, n), 2),
                "rh": np.round(np.clip(rh + rng.normal(0, 1.5, n), 20, 100), 1),
                "wind_u": np.round(u + rng.normal(0, 0.2, n), 2),
                "wind_v": np.round(v + rng.normal(0, 0.2, n), 2),
                "wind_speed": np.round(np.hypot(u, v) + rng.normal(0, 0.15, n), 2),
                "wind_dir": np.round(wind_dir, 1),
                "precip": np.round(precip, 2),
                "pbl": np.round(pbl + rng.normal(0, 30, n), 0),
                "cloud": np.round(np.clip(cloud + rng.normal(0, 0.05, n), 0, 1), 3),
                "aod": aod,
                "fire_count": fire_count,
                "fire_upwind": np.round(fire_upwind, 2),
                # NOTE: `traffic` is deliberately NOT exported. It is an internal
                # generator term, and a perfect traffic column would never exist
                # in real data. The model has to reconstruct the rush-hour cycle
                # from hour/dow, exactly as it must in live mode.
                # Static site context. The real build overwrites this with the
                # OSM value; the fallback table keeps the schema identical.
                "dist_road_km": FALLBACK_ROAD_KM.get(st.key, 0.8),
            }
        )
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)

    # Station outages and a few weather dropouts, because real data is messy.
    rng_all = np.random.default_rng(seed + 7)
    outage = rng_all.random(len(out)) < 0.045
    out.loc[outage, "pm25"] = np.nan
    out.loc[rng_all.random(len(out)) < 0.004, "pbl"] = np.nan

    out = out.sort_values(["station", "time"]).reset_index(drop=True)
    out["aod"] = out.groupby("station")["aod"].transform(lambda s: s)  # keep dtype
    return out
