"""Tests for the upwind fire-transport feature (pure, no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pm25.config import Config
from pm25.data import fires


@pytest.fixture
def cfg(tmp_path):
    return Config.load(root=tmp_path)


def _hourly(n: int = 48) -> pd.DataFrame:
    times = pd.date_range("2024-11-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"time": times, "station": "victoria_memorial", "wind_dir": 315.0}
    )


def _fire_table() -> pd.DataFrame:
    # A cluster NW of the station (bearing ~315 degrees), detections on Nov 1 only.
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-11-01", tz="UTC")],
            "fire_count": [10.0],
            "fire_lat": [24.0],
            "fire_lon": [87.0],
        }
    )


def test_aligned_wind_carries_full_transport(cfg):
    out = fires.add_upwind_features(_hourly(), _fire_table(), cfg)
    day1 = out[out["time"].dt.day == 1]
    day2 = out[out["time"].dt.day == 2]
    assert (day1["fire_count"] == 10.0).all()
    # Wind FROM 315 with the fire AT ~315 degrees: alignment ~1, smoothed = 1.
    assert np.allclose(day1["fire_upwind"], 10.0, atol=0.1)
    # No detections on day 2 -> nothing to transport.
    assert (day2["fire_upwind"] == 0.0).all()


def test_downwind_wind_transports_nothing(cfg):
    hourly = _hourly()
    hourly["wind_dir"] = 135.0   # FROM the SE: fire is downwind all day
    out = fires.add_upwind_features(hourly, _fire_table(), cfg)
    assert (out["fire_upwind"] == 0.0).all()


def test_alignment_is_smoothed_over_six_hours(cfg):
    """A single aligned hour in an otherwise downwind day must not produce a
    full-strength spike: transport integrates over several hours."""
    hourly = _hourly()
    hourly["wind_dir"] = 135.0
    hourly.loc[12, "wind_dir"] = 315.0   # one aligned hour at 12:00

    out = fires.add_upwind_features(hourly, _fire_table(), cfg)
    spike = float(out.loc[12, "fire_upwind"])
    assert 0.0 < spike < 10.0            # diluted by its downwind neighbours
    assert float(out.loc[5, "fire_upwind"]) == 0.0   # outside the 6 h window


def test_bearing_is_met_convention():
    # Station -> fire cluster due NW: bearing should be ~315, not ~135.
    b = fires._bearing(22.5448, 88.3426, 24.0, 87.0)
    assert 300.0 < b < 330.0
