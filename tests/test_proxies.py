"""Tests for the rule-based source proxies."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pm25.explain import proxies


def _frame(n: int = 200) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "time": times,
            "station": "a",
            "pm25": 80.0,
            "pm10": 120.0,       # ratio 1.5 < 2.6 -> dust rule cannot fire
            "no2": 30.0,
            "o3": 30.0,
            "rh": 50.0,          # < 70 -> secondary rule cannot fire
            "wind_speed": 1.0,   # < 2.5 -> dust rule cannot fire
            "dist_road_km": 0.3,
            "fire_upwind": 0.0,
        }
    )
    # 25% of hours with strong upwind transport: all above the fire threshold
    # (max(2.0, 70th pct of the nonzero population) = 8 here).
    df.loc[50:99, "fire_upwind"] = 8.0
    return df


def test_high_fire_hours_labelled_biomass():
    labelled = proxies.assign(_frame())
    assert (labelled.loc[50:99, "proxy"] == "biomass").all()
    # And never biomass when there is no transport.
    assert (labelled.loc[:49, "proxy"] != "biomass").all()


def test_labels_are_from_the_known_set():
    labelled = proxies.assign(_frame())
    assert set(labelled["proxy"]) <= set(proxies.PROXY_LABELS)


def test_biomass_wins_over_other_rules():
    """A high-fire hour that also satisfies the traffic rule must stay biomass:
    transport events have the highest priority."""
    df = _frame()
    # Make the fire hours also peak NO2 rush hours on a weekday near a road.
    df["no2"] = 10.0
    df.loc[50:99, "no2"] = 90.0
    labelled = proxies.assign(df)
    assert (labelled.loc[50:99, "proxy"] == "biomass").all()


def test_dust_rule_requires_all_three_conditions():
    df = _frame()
    # PM10/PM25 ratio high, but wind too low and RH too high.
    df.loc[10:20, "pm10"] = df.loc[10:20, "pm25"] * 4.0
    labelled = proxies.assign(df)
    assert (labelled.loc[10:20, "proxy"] != "dust").all()

    df2 = _frame()
    df2.loc[10:20, "pm10"] = df2.loc[10:20, "pm25"] * 4.0
    df2.loc[10:20, "rh"] = 50.0
    df2.loc[10:20, "wind_speed"] = 3.0
    labelled2 = proxies.assign(df2)
    assert (labelled2.loc[10:20, "proxy"] == "dust").all()


def test_prevalence_shares_sum_to_one():
    labelled = proxies.assign(_frame())
    prev = proxies.prevalence(labelled, by="station")
    assert list(prev.columns) == proxies.PROXY_LABELS
    np.testing.assert_allclose(prev.sum(axis=1), 1.0)
    assert prev.loc["a", "biomass"] == pytest.approx(50 / 200, abs=1e-3)
