"""Tests for metrics and validation splits."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pm25.models.evaluate import (
    WINTER_MONTHS,
    episode_metrics,
    loso_splits,
    regression_metrics,
    time_split,
    winter_mask,
)


def test_regression_metrics_perfect_prediction():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    m = regression_metrics(y, y.copy())
    assert m["n"] == 4
    assert m["rmse"] == 0.0 and m["mae"] == 0.0 and m["r2"] == 1.0 and m["bias"] == 0.0


def test_regression_metrics_handles_empty_and_nan():
    m = regression_metrics([], [])
    assert m["n"] == 0 and np.isnan(m["rmse"])
    y = np.array([1.0, np.nan, 3.0])
    p = np.array([1.0, 99.0, np.nan])
    m = regression_metrics(y, p)
    assert m["n"] == 1   # only the first pair is finite on both sides


def test_regression_metrics_constant_target():
    y = np.array([5.0, 5.0, 5.0])
    m = regression_metrics(y, np.array([4.0, 5.0, 6.0]))
    assert np.isnan(m["r2"])   # ss_tot = 0 -> undefined, not inf


def test_episode_metrics_recall_and_far():
    y = np.array([130.0, 100.0, 140.0, 90.0])
    p = np.array([125.0, 135.0, 110.0, 85.0])
    m = episode_metrics(y, p, threshold=120.0)
    # observed = [T, F, T, F], predicted = [T, T, F, F]
    # tp=1 (130), fn=1 (140 missed), fp=1 (135 was a false alarm)
    assert m["n_episode"] == 2
    assert m["recall"] == 0.5
    assert m["far"] == 0.5


def test_episode_metrics_no_events_is_not_a_crash():
    m = episode_metrics(np.array([10.0, 20.0]), np.array([15.0, 25.0]), threshold=120.0)
    assert m["n_episode"] == 0 and np.isnan(m["recall"]) and np.isnan(m["far"])


def test_winter_mask():
    df = pd.DataFrame(
        {"time": pd.to_datetime(
            ["2024-01-15", "2024-03-15", "2024-11-15", "2024-07-15", "2024-02-29"], utc=True
        )}
    )
    expected = pd.Series([True, False, True, False, True])
    assert winter_mask(df).equals(expected)
    assert set(WINTER_MONTHS) == {11, 12, 1, 2}


def test_time_split_is_year_ordered():
    df = pd.DataFrame(
        {"time": pd.to_datetime(
            ["2023-01-01", "2023-06-01", "2024-01-01", "2024-06-01"], utc=True
        )}
    )
    train, test = time_split(df, 2024)
    assert (train["time"].dt.year < 2024).all()
    assert (test["time"].dt.year >= 2024).all()


def test_time_split_raises_on_empty_side():
    df = pd.DataFrame({"time": pd.to_datetime(["2023-01-01", "2023-06-01"], utc=True)})
    with pytest.raises(ValueError):
        time_split(df, 2030)   # test side would be empty


def test_loso_splits_covers_every_station():
    df = pd.DataFrame(
        {
            "station": ["a", "a", "b", "b", "c", "c"],
            "time": pd.to_datetime(["2024-01-01"] * 6, utc=True),
        }
    )
    held_out = [s for s, train, test in loso_splits(df)]
    assert held_out == ["a", "b", "c"]
    for _, train, test in loso_splits(df):
        assert set(train["station"]) | set(test["station"]) == {"a", "b", "c"}
        assert not (set(train["station"]) & set(test["station"]))
