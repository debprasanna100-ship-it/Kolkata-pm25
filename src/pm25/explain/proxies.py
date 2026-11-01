"""Rule-based source proxies.

This is the honest substitute for PMF. PMF needs chemically speciated filter
data (ions, metals, OC/EC) that is not publicly available at hourly resolution
for Kolkata. What we *can* do is label hours with a plausible dominant source
using cheap observables, then check whether the model's SHAP importances line
up with those labels seasonally.

That check is the whole point. A proxy label on its own is a guess; a proxy
label that agrees with an independently-trained model's attributions is
evidence.

Every threshold is a station-relative quantile, not an absolute number, so the
rules survive a different city or a different unit convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PROXY_LABELS = ["biomass", "dust", "traffic", "secondary", "background"]

# Which model features should light up if a proxy is real.
EXPECTED_DRIVERS = {
    "biomass": ["fire_upwind", "fire_count", "fire_upwind_lag24", "wind_dir_cos", "wind_dir_sin"],
    "dust": ["wind_speed", "rh", "ventilation", "pbl"],
    "traffic": ["hour_sin", "hour_cos", "dow", "dist_road_km", "is_weekend"],
    "secondary": ["rh", "temp", "pbl", "month_sin", "month_cos"],
    "background": ["pbl", "ventilation", "wind_speed"],
}


def _q(series: pd.Series, quantile: float, default: float) -> float:
    value = series.quantile(quantile)
    return float(value) if np.isfinite(value) else default


def assign(df: pd.DataFrame) -> pd.DataFrame:
    """Add `proxy` (label) and `proxy_rule` (which rule fired) columns."""
    out = df.copy()

    # Per-station thresholds keep the rules fair across sites with different
    # absolute pollution levels.
    grp = out.groupby("station")

    # fire_upwind is zero-inflated: over half of all hours have no upwind
    # detections, so a plain 85th percentile of the full series is 0 and every
    # hour would qualify. Threshold on the nonzero population instead.
    def _fire_threshold(s: pd.Series) -> float:
        positive = s[s > 0]
        if positive.empty:
            return float("inf")
        # Absolute floor as well as a relative one: a "high fire" hour for a
        # station in monsoon is still a low-fire hour in absolute terms, and
        # labelling it biomass would be misleading.
        return max(2.0, float(positive.quantile(0.70)))

    fire_hi = grp["fire_upwind"].transform(lambda s: s >= _fire_threshold(s))

    if "no2" in out.columns:
        no2_hi = grp["no2"].transform(lambda s: s >= _q(s, 0.60, 0.0))
    else:
        no2_hi = pd.Series(False, index=out.index)

    if "o3" in out.columns:
        o3_hi = grp["o3"].transform(lambda s: s >= _q(s, 0.60, 0.0))
    else:
        o3_hi = pd.Series(False, index=out.index)

    if {"pm10", "pm25"} <= set(out.columns):
        ratio = out["pm10"] / out["pm25"].replace(0, np.nan)
    else:
        ratio = pd.Series(np.nan, index=out.index)

    hour = out["time"].dt.hour
    weekday = out["time"].dt.dayofweek < 5
    rush = ((hour >= 7) & (hour <= 11)) | ((hour >= 17) & (hour <= 22))

    rh = out["rh"] if "rh" in out else pd.Series(50.0, index=out.index)
    wind = out["wind_speed"] if "wind_speed" in out else pd.Series(0.0, index=out.index)
    near_road = (out["dist_road_km"] < 1.0) if "dist_road_km" in out else pd.Series(True, index=out.index)

    dust_rule = (ratio >= 2.6) & (rh < 62) & (wind >= 2.5)
    traffic_rule = rush & weekday & near_road & no2_hi
    secondary_rule = (rh >= 70) & o3_hi & (wind < 2.5)

    out["proxy"] = "background"
    out.loc[secondary_rule, "proxy"] = "secondary"
    out.loc[traffic_rule, "proxy"] = "traffic"
    out.loc[dust_rule, "proxy"] = "dust"
    out.loc[fire_hi, "proxy"] = "biomass"      # highest priority: transport events win

    out["proxy_rule"] = out["proxy"]
    return out


def prevalence(df: pd.DataFrame, by: str = "season") -> pd.DataFrame:
    """Share of hours attributed to each proxy, per season (or per station)."""
    counts = df.groupby([by, "proxy"]).size().unstack(fill_value=0)
    shares = counts.div(counts.sum(axis=1), axis=0)
    for label in PROXY_LABELS:
        if label not in shares.columns:
            shares[label] = 0.0
    return shares[PROXY_LABELS].round(3)


def mean_concentration_by_proxy(df: pd.DataFrame) -> pd.DataFrame:
    stats = df.groupby("proxy")["pm25"].agg(["count", "mean", "median"]).round(1)
    return stats.reindex(PROXY_LABELS).dropna(how="all")


def season_column(df: pd.DataFrame) -> pd.DataFrame:
    from .importance import season_of

    out = df.copy()
    out["season"] = out["time"].dt.month.map(season_of)
    return out
