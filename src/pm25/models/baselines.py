"""Baselines. Always report these - a model that cannot beat persistence is
not a model, and reviewers ask for exactly this table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class Persistence:
    """Tomorrow looks like today: predict PM2.5(t) for PM2.5(t + h)."""

    name = "persistence"

    def fit(self, df: pd.DataFrame, y: pd.Series) -> "Persistence":
        self._fallback = float(np.nanmean(y)) if len(y) else 0.0
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if "pm25" not in df.columns:
            return np.full(len(df), self._fallback)
        return df["pm25"].to_numpy(dtype=float)


class Climatology:
    """Average PM2.5 for this station, month and hour, learned on train only."""

    name = "climatology"

    def fit(self, df: pd.DataFrame, y: pd.Series) -> "Climatology":
        frame = df[["station", "time"]].copy()
        frame["y"] = np.asarray(y)
        frame["month"] = frame["time"].dt.month
        frame["hour"] = frame["time"].dt.hour
        self._table = frame.groupby(["station", "month", "hour"])["y"].mean()
        self._global = float(np.nanmean(y))
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        frame = df[["station", "time"]].copy()
        frame["month"] = frame["time"].dt.month
        frame["hour"] = frame["time"].dt.hour
        keys = pd.MultiIndex.from_frame(frame[["station", "month", "hour"]])
        values = self._table.reindex(keys).to_numpy(dtype=float)
        return np.where(np.isfinite(values), values, self._global)


class LinearBaseline:
    """Ridge on the same feature matrix, so the gap to the GBDT is fair."""

    name = "ridge"

    def __init__(self, alpha: float = 1.0):
        self.pipeline = Pipeline(
            [("scale", StandardScaler()), ("ridge", Ridge(alpha=alpha))]
        )

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LinearBaseline":
        self.pipeline.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.pipeline.predict(X)
