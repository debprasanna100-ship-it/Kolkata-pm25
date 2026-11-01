"""Dataset assembly: one function that produces the modelling table."""

from __future__ import annotations

import pandas as pd

from ..config import Config
from ..stations import get_stations
from ..utils import get_logger, write_table
from . import fires, openaq, roads, satellite, synthetic, weather

log = get_logger("pm25.build")


def build(cfg: Config) -> pd.DataFrame:
    mode = str(cfg.get("data.mode", "demo")).lower()

    if mode == "demo":
        df = synthetic.generate(cfg)
        log.info("demo dataset: %d rows, %d stations", len(df), df["station"].nunique())
        _report(df)
        write_table(df, cfg.dataset_csv)
        log.info("wrote %s", cfg.dataset_csv)
        return df

    if mode != "live":
        raise ValueError(f"data.mode must be 'demo' or 'live', got {mode!r}")

    return build_live(cfg)


def build_live(cfg: Config) -> pd.DataFrame:
    log.info("LIVE mode - this needs OPENAQ_API_KEY and network access")

    # 1. ground truth -------------------------------------------------------
    ground = openaq.fetch(cfg)
    ground["time"] = pd.to_datetime(ground["time"], utc=True)
    ground = ground.dropna(subset=["time"]).sort_values(["station", "time"])

    # Collapse to exactly one row per station-hour. Coerce first: a single
    # object-dtype column (a feed quirk, a pandas concat artefact) would
    # otherwise silently fall out of select_dtypes and vanish here.
    identity = {"time", "station", "station_name", "lat", "lon"}
    for col in ground.columns:
        if col not in identity:
            ground[col] = pd.to_numeric(ground[col], errors="coerce")
    numeric = ground.select_dtypes("number").columns.tolist()
    ground = (
        ground.groupby(["station", "station_name", "lat", "lon", "time"], as_index=False)[numeric]
        .mean()
    )
    log.info("ground truth: %d station-hours", len(ground))

    # 2. weather ------------------------------------------------------------
    wx = weather.fetch(cfg)
    wx["time"] = pd.to_datetime(wx["time"], utc=True)
    df = ground.merge(wx, on=["station", "time"], how="left")
    log.info("after weather join: %d rows, %.1f%% with temp",
             len(df), 100 * df["temp"].notna().mean())

    # 3. satellite (daily -> hourly) ---------------------------------------
    try:
        daily = satellite.fetch(cfg)
        df = satellite.expand_daily_to_hourly(daily, df)
        log.info("after satellite join: AOD present on %.1f%% of rows",
                 100 * df["aod"].notna().mean() if "aod" in df else 0.0)
    except Exception as exc:
        log.warning("satellite step skipped: %s", exc)
        df["aod"] = pd.NA

    # 4. fires --------------------------------------------------------------
    try:
        fire_table = fires.fetch(cfg)
        df = fires.add_upwind_features(df, fire_table, cfg)
    except Exception as exc:
        log.warning("fire step skipped: %s", exc)
        df["fire_count"] = 0.0
        df["fire_upwind"] = 0.0

    # 5. road proximity -----------------------------------------------------
    try:
        distances = roads.fetch(cfg, stations=df["station"].unique().tolist())
        df["dist_road_km"] = df["station"].map(distances)
    except Exception as exc:
        log.warning("road step skipped: %s", exc)
        from ..stations import FALLBACK_ROAD_KM

        df["dist_road_km"] = df["station"].map(FALLBACK_ROAD_KM)

    # 6. tidy ---------------------------------------------------------------
    df = df.sort_values(["station", "time"]).reset_index(drop=True)
    keep = _column_order(df)
    df = df[keep]

    _report(df)
    write_table(df, cfg.dataset_csv)
    log.info("wrote %s", cfg.dataset_csv)
    return df


def _column_order(df: pd.DataFrame) -> list[str]:
    front = ["time", "station", "station_name", "lat", "lon"]
    front = [c for c in front if c in df.columns]
    rest = [c for c in df.columns if c not in front]
    return front + rest


def _report(df: pd.DataFrame) -> None:
    g = df.groupby("station")["pm25"]
    table = pd.DataFrame(
        {
            "mean": g.mean().round(1),
            "p95": g.quantile(0.95).round(1),
            "max": g.max().round(1),
            "n": g.size(),
        }
    )
    if "aod" in df.columns:
        table["aod_missing_%"] = (
            df.groupby("station")["aod"].apply(lambda s: round(100 * s.isna().mean(), 1))
        )
    log.info("PM2.5 summary by station:\n%s", table.to_string())

    span = (df["time"].max() - df["time"].min()).days
    coverage = len(df) / max(1, (span + 1) * 24 * df["station"].nunique())
    log.info("time span %s..%s, hourly coverage %.1f%%",
             df["time"].min(), df["time"].max(), 100 * coverage)
