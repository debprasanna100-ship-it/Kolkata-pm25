"""Tests for the feature pipeline.

The point of this file is to lock in the leakage guards: if any of these
fail, the reported metrics are fraudulent, not just worse.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pm25.config import Config
from pm25.features import feature_columns, make_features


@pytest.fixture
def cfg(tmp_path):
    # No config.yaml in tmp_path -> pure DEFAULTS, same as a fresh clone.
    return Config.load(root=tmp_path)


def _frame(hours: int = 72) -> pd.DataFrame:
    """Two stations, strictly increasing PM2.5 so lags are easy to verify."""
    times = pd.date_range("2024-01-01", periods=hours, freq="h", tz="UTC")
    frames = []
    for i, station in enumerate(["a", "b"]):
        pm = 10.0 + np.arange(hours, dtype=float) + 100.0 * i
        frames.append(
            pd.DataFrame(
                {
                    "time": times,
                    "station": station,
                    "station_name": station,
                    "lat": 22.5 + 0.01 * i,
                    "lon": 88.3 + 0.01 * i,
                    "pm25": pm,
                    "pm10": pm * 2.0,
                    "no2": 20.0,
                    "so2": 5.0,
                    "co": 0.5,
                    "o3": 30.0,
                    "temp": 25.0,
                    "rh": 60.0,
                    "wind_speed": 2.0,
                    "wind_dir": 180.0,
                    "precip": 0.0,
                    "pbl": 800.0,
                    "cloud": 0.3,
                    "aod": 0.3,
                    "fire_count": 0.0,
                    "fire_upwind": 0.0,
                    "dist_road_km": 0.5,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _station(frame: pd.DataFrame, station: str) -> pd.DataFrame:
    return frame[frame["station"] == station].sort_values("time").reset_index(drop=True)


# --- leakage guards ---------------------------------------------------------


def test_lag0_dropped_at_horizon_zero(cfg):
    """pm25_lag0 IS the target at h=0. Keeping it would report R² = 1."""
    feat = make_features(_frame(), cfg, horizon=0)
    cols = feature_columns(feat)
    assert "pm25_lag0" not in cols
    assert "pm25" not in cols and "y" not in cols


def test_lag0_kept_for_forecast_horizons(cfg):
    """At h >= 1 the current observation is a legitimate feature."""
    cols = feature_columns(make_features(_frame(), cfg, horizon=1))
    assert "pm25_lag0" in cols


def test_aod_dropped_beyond_availability_window(cfg):
    """Same-day AOD is the future for h > aod_available_ahead_h (default 2 h)."""
    h1 = feature_columns(make_features(_frame(), cfg, horizon=1))
    h6 = feature_columns(make_features(_frame(), cfg, horizon=6))
    h24 = feature_columns(make_features(_frame(), cfg, horizon=24))
    assert "aod" in h1
    assert "aod" not in h6 and "aod" not in h24
    # The previous day's retrieval survives at every horizon.
    assert "aod_lag24" in h24
    # The missingness flag is computed before the drop and always survives.
    assert "aod_missing" in h24


def test_lag_is_shifted_per_station(cfg):
    raw = _frame()
    feat = make_features(raw, cfg, horizon=1)
    for station in ("a", "b"):
        block = _station(feat, station)
        original = _station(raw, station)["pm25"].to_numpy()
        # With pm = 10 + arange, lag1 at row k = original[k] - 1.
        assert np.isnan(block["pm25_lag1"].iloc[0])
        np.testing.assert_allclose(block["pm25_lag1"].to_numpy()[1:], original[1:-1] - 1.0)


def test_rolling_excludes_current_hour(cfg):
    """Rolling features use shift(1): the current hour must not leak into itself."""
    raw = _frame()
    times = sorted(raw["time"].unique())
    spike = 10_000.0
    raw.loc[(raw["station"] == "a") & (raw["time"] == times[24]), "pm25"] = spike

    feat = make_features(raw, cfg, horizon=1)
    block = _station(feat, "a")
    original = _station(raw, "a")["pm25"].to_numpy()
    spike_idx = 24
    assert original[spike_idx] == spike

    # roll6 at the spike must be the mean of the six hours BEFORE it.
    expected = original[spike_idx - 6 : spike_idx].mean()
    got = float(block["pm25_roll6"].iloc[spike_idx])
    np.testing.assert_allclose(got, expected)
    assert got < spike / 10.0   # the spike clearly did not leak in


def test_y_is_target_shifted_by_horizon(cfg):
    raw = _frame()
    for horizon in (1, 6):
        feat = make_features(raw, cfg, horizon=horizon)
        for station in ("a", "b"):
            block = _station(feat, station)
            original = _station(raw, station)["pm25"].to_numpy()
            n = len(block)
            np.testing.assert_allclose(block["y"].to_numpy(), original[horizon : horizon + n])


def test_no_copollutants_or_identity_in_features(cfg):
    cols = feature_columns(make_features(_frame(), cfg, horizon=1))
    for banned in ("pm10", "no2", "so2", "co", "o3", "time", "station",
                   "station_name", "pm25", "y", "hour", "month", "doy"):
        assert banned not in cols, f"{banned} leaked into the feature matrix"


def test_include_lags_false_strips_every_autoregressive_column(cfg):
    cols = feature_columns(make_features(_frame(), cfg, horizon=0, include_lags=False))
    assert not any(c.startswith(("pm25_lag", "pm25_roll", "pm25_diff")) for c in cols)


def test_usable_columns_drop_all_nan_features(cfg):
    """Live mode with the satellite step skipped leaves aod columns all-NaN;
    their median is NaN, imputation is a no-op, and ridge crashes on them."""
    from pm25.features import usable_feature_columns

    feat = make_features(_frame(), cfg, horizon=24)
    feat["aod_lag24"] = np.nan          # simulate satellite step skipped
    feat["ventilation"] = np.nan
    cols = feature_columns(feat)
    usable = usable_feature_columns(feat, cols)
    assert "aod_lag24" not in usable and "ventilation" not in usable
    assert "temp" in usable             # healthy columns untouched
    assert len(usable) == len(cols) - 2
