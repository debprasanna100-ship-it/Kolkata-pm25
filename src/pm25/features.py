"""Feature engineering.

Design decisions worth defending
--------------------------------
1. **No co-pollutant features.** PM10, NO2, SO2, CO and O3 are *not* model
   inputs, even though the dataset has them. They are measured at the same
   station and are highly correlated with PM2.5 by construction, so including
   them would inflate R² without any operational value (if you already have the
   station, you do not need to estimate PM2.5). They are kept for the source
   proxies only.

2. **No station identifier feature.** LOSO validation would be meaningless if
   the model could memorise a station offset. Location enters only as lat/lon
   plus road distance, which can interpolate to an unseen site.

3. **Satellite leakage is handled per horizon.** AOD is a daytime satellite
   retrieval for the *same day*. For a nowcast that is fine. For a +24 h
   forecast it is the future, so the AOD columns are dropped and only the
   previous day's AOD survives.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config
from .utils import get_logger

log = get_logger("pm25.features")

# Columns that must never become model inputs.
TARGET = "pm25"
CO_POLLUTANTS = ["pm10", "no2", "so2", "co", "o3"]
IDENTITY = ["time", "station", "station_name"]
STATIC = ["lat", "lon", "dist_road_km"]

# Grouped so the attribution step can talk about them coherently.
FEATURE_GROUPS = {
    "meteorology": ["temp", "rh", "wind_speed", "wind_dir_sin", "wind_dir_cos",
                    "precip", "pbl", "pbl_inv", "ventilation", "cloud"],
    "satellite": ["aod", "aod_lag24", "aod_missing"],
    "fires": ["fire_count", "fire_upwind", "fire_upwind_lag24"],
    "time": ["hour_sin", "hour_cos", "month_sin", "month_cos", "dow", "is_weekend"],
    "autoregressive": [],   # filled in dynamically from the lag list
    "static": ["dist_road_km", "lat", "lon"],
}


def _group(df: pd.DataFrame, col: str):
    return df.groupby("station", sort=False)[col]


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    t = df["time"]
    hour = t.dt.hour
    month = t.dt.month
    df["hour"] = hour
    df["dow"] = t.dt.dayofweek
    df["month"] = month
    df["doy"] = t.dt.dayofyear
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["month_sin"] = np.sin(2 * np.pi * month / 12)
    df["month_cos"] = np.cos(2 * np.pi * month / 12)
    df["is_weekend"] = (t.dt.dayofweek >= 5).astype(int)
    return df


def add_wind_features(df: pd.DataFrame) -> pd.DataFrame:
    if "wind_speed" not in df.columns or df["wind_speed"].isna().any():
        df["wind_speed"] = np.hypot(df.get("wind_u", 0), df.get("wind_v", 0))

    direction = df["wind_dir"].fillna(0.0)
    df["wind_dir_sin"] = np.sin(np.radians(direction))
    df["wind_dir_cos"] = np.cos(np.radians(direction))

    pbl = df["pbl"].fillna(df["pbl"].median())
    df["pbl_inv"] = 1.0 / (pbl + 100.0)
    df["ventilation"] = df["wind_speed"] * pbl
    return df


def add_lag_features(df: pd.DataFrame, lags: list[int], windows: list[int]) -> pd.DataFrame:
    df = df.sort_values(["station", "time"]).reset_index(drop=True)

    for lag in lags:
        if lag == 0:
            # The most recent observation is available at prediction time, so it
            # belongs in the feature set. It is only legitimate for horizon >= 1;
            # at horizon 0 it would be the answer itself, so make_features drops
            # it there (enforced below, unit-tested in tests/test_features.py).
            df["pm25_lag0"] = df[TARGET]
            continue
        df[f"pm25_lag{lag}"] = _group(df, TARGET).shift(lag)
        df[f"pm25_diff{lag}"] = df[TARGET] - df[f"pm25_lag{lag}"]

    for window in windows:
        df[f"pm25_roll{window}"] = df.groupby("station", sort=False)[TARGET].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=max(2, w // 2)).mean()
        )
        df[f"pm25_rollstd{window}"] = df.groupby("station", sort=False)[TARGET].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=max(2, w // 2)).std()
        )

    # AOD is a daily product, so the only legitimate lag is a full day.
    df["aod_lag24"] = _group(df, "aod").shift(24)
    df["fire_upwind_lag24"] = _group(df, "fire_upwind").shift(24)
    return df


def make_features(
    df: pd.DataFrame,
    cfg: Config,
    horizon: int = 0,
    include_lags: bool = True,
) -> pd.DataFrame:
    """Return a modelling frame with a `y` column = PM2.5 at t + horizon."""
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    out = out.dropna(subset=["time"]).sort_values(["station", "time"]).reset_index(drop=True)

    out = add_time_features(out)
    out = add_wind_features(out)

    lags = cfg.get("features.lags", [1, 3, 6, 12, 24])
    windows = cfg.get("features.rolling_windows", [6, 24])
    out = add_lag_features(out, lags, windows)

    # Leakage guard: at horizon 0, pm25_lag0 IS the target. Dropping it here
    # makes the rule in add_lag_features enforceable instead of aspirational.
    if horizon == 0:
        out = out.drop(columns=["pm25_lag0"], errors="ignore")

    # Missing-AOD indicator: the model can learn to distrust itself on cloudy days.
    out["aod_missing"] = out["aod"].isna().astype(int)

    # --- satellite leakage guard ------------------------------------------
    aod_window = int(cfg.get("features.aod_available_ahead_h", 2))
    if horizon > aod_window:
        out = out.drop(columns=["aod"], errors="ignore")

    # --- target ------------------------------------------------------------
    out["y"] = out.groupby("station", sort=False)[TARGET].shift(-horizon)
    out = out.dropna(subset=["y"]).reset_index(drop=True)

    if not include_lags:
        drop = [c for c in out.columns if c.startswith("pm25_lag") or c.startswith("pm25_roll") or c.startswith("pm25_diff")]
        out = out.drop(columns=drop, errors="ignore")

    return out


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Every numeric column that is not identity, target or a co-pollutant."""
    banned = set(IDENTITY + CO_POLLUTANTS + [TARGET, "y", "hour", "month", "doy"])
    # Columns written by the pipeline itself; never feed them back in.
    banned |= {"pred", "q10", "q50", "q90", "interval_width",
               "proxy", "proxy_rule", "season", "aod_state", "rh_bin"}
    cols = []
    for col in df.columns:
        if col in banned:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols


def usable_feature_columns(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """Feature columns that carry information in THIS frame.

    A column that is NaN everywhere (live mode with the satellite step skipped
    leaves aod/aod_lag24 all-NaN) has a NaN median, so median imputation is a
    no-op and the column poisons every estimator that rejects NaN - ridge
    crashes outright, and the others carry dead weight. Drop them once, here,
    so train/test/LOSO all see the same columns.
    """
    keep = [c for c in cols if not df[c].isna().all()]
    dropped = [c for c in cols if c not in keep]
    if dropped:
        log.info("dropping all-NaN feature columns: %s", dropped)
    return keep


def group_of(feature: str) -> str:
    for name, members in FEATURE_GROUPS.items():
        if feature in members:
            return name
    if feature.startswith("pm25_") or feature.startswith("aod"):
        return "satellite" if feature.startswith("aod") else "autoregressive"
    if feature.startswith("fire"):
        return "fires"
    return "other"


def split_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    cols = feature_columns(df)
    X = df[cols].copy()
    # Median-impute per column; the model also gets aod_missing so it can adapt.
    X = X.fillna(X.median(numeric_only=True))
    y = df["y"].astype(float)
    return X, y
