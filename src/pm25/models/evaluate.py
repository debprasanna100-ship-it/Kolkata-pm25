"""Validation: time-based splits, leave-one-station-out, and metrics that
actually matter for an air quality paper.

Two splits, both honest:
  * `time_split`  - train on earlier data, test on the latest year. Answers
                    "does this work for next year?"
  * `loso_splits` - train on the other stations, test on the held-out one.
                    Answers "does this work for a city with no monitor?"

Random `train_test_split` on hourly data is not used anywhere: consecutive
hours are autocorrelated, so a random split leaks the answer and produces
R² values that collapse on real out-of-sample data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPISODE_THRESHOLD = 120.0   # µg/m³, CPCB "Poor" boundary
WINTER_MONTHS = [11, 12, 1, 2]   # the smog season episode metrics restrict to


def regression_metrics(y_true, y_pred) -> dict:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p)
    y, p = y[mask], p[mask]
    if y.size == 0:
        return {"n": 0, "rmse": np.nan, "mae": np.nan, "r2": np.nan, "bias": np.nan, "mape": np.nan}

    err = p - y
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))

    return {
        "n": int(y.size),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
        "bias": float(np.mean(err)),
        "mape": float(np.mean(np.abs(err) / np.maximum(y, 1.0)) * 100.0),
    }


def episode_metrics(y_true, y_pred, threshold: float = EPISODE_THRESHOLD) -> dict:
    """Detection skill during high-pollution episodes.

    A model with a good overall RMSE can still be useless for the thing people
    care about - the winter smog days. `recall` and `far` make that visible.
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p)
    y, p = y[mask], p[mask]

    observed = y >= threshold
    predicted = p >= threshold
    tp = int(np.sum(observed & predicted))
    fn = int(np.sum(observed & ~predicted))
    fp = int(np.sum(~observed & predicted))

    recall = tp / (tp + fn) if (tp + fn) else np.nan
    far = fp / (tp + fp) if (tp + fp) else np.nan

    out = {"threshold": threshold, "n_episode": int(observed.sum())}
    out.update({f"ep_{k}": v for k, v in regression_metrics(y[observed], p[observed]).items()})
    out["recall"] = recall
    out["far"] = far
    return out


def time_split(df: pd.DataFrame, test_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    years = df["time"].dt.year
    train = df[years < test_year]
    test = df[years >= test_year]
    if len(train) == 0 or len(test) == 0:
        raise ValueError(
            f"time_split produced an empty side (train={len(train)}, test={len(test)}). "
            f"Check data.start/end and models.test_year={test_year}."
        )
    return train.reset_index(drop=True), test.reset_index(drop=True)


def loso_splits(df: pd.DataFrame):
    """Yield (station, train_df, test_df) for each station."""
    for station in sorted(df["station"].unique()):
        test = df[df["station"] == station]
        train = df[df["station"] != station]
        if len(train) and len(test):
            yield station, train.reset_index(drop=True), test.reset_index(drop=True)


def winter_mask(df: pd.DataFrame) -> pd.Series:
    """Nov-Feb rows. Episode metrics are computed on this slice so that recall
    and FAR describe the winter smog season the validation protocol promises,
    not a year-round average dominated by ordinary days."""
    return df["time"].dt.month.isin(WINTER_MONTHS)


def summarise_by_station(df: pd.DataFrame, y_pred) -> pd.DataFrame:
    tmp = df[["station", "y", "time"]].copy()
    tmp["pred"] = np.asarray(y_pred)
    rows = []
    for station, chunk in tmp.groupby("station"):
        m = regression_metrics(chunk["y"], chunk["pred"])
        m["station"] = station
        rows.append(m)
    return pd.DataFrame(rows).set_index("station")[
        ["n", "rmse", "mae", "r2", "bias", "mape"]
    ].round(3)
