"""Gradient boosted trees with prediction intervals.

Uses LightGBM when it is installed (faster, native quantile objective), and
falls back to scikit-learn's HistGradientBoostingRegressor, which ships with
scikit-learn, handles NaN natively and also supports `loss="quantile"`.
That fallback is why this repo has no hard dependency on LightGBM.

Quantile regression is the cheap uncertainty story: train three models at
0.1 / 0.5 / 0.9 and you get an 80% prediction interval for free. It also makes
the "model is unsure on cloudy days" claim measurable rather than rhetorical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ..config import Config
from ..utils import get_logger

log = get_logger("pm25.gbdt")

try:  # optional
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except Exception:  # pragma: no cover
    lgb = None
    HAS_LIGHTGBM = False

from sklearn.ensemble import HistGradientBoostingRegressor


@dataclass
class QuantileGBDT:
    """A bundle of quantile models sharing one feature space."""

    models: dict[float, Any]
    features: list[str]
    backend: str

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X[self.features]
        out = {}
        for q, model in self.models.items():
            out[q] = model.predict(X)
        frame = pd.DataFrame(out, index=X.index)
        frame.columns = [f"q{int(q * 100):02d}" for q in self.models]
        return frame

    @property
    def median(self) -> Any:
        return self.models.get(0.5, next(iter(self.models.values())))

    def feature_importance(self) -> pd.Series:
        model = self.median
        if hasattr(model, "feature_importances_"):
            values = np.asarray(model.feature_importances_, dtype=float)
        else:
            # HistGradientBoosting has no built-in importance; use split counts
            # if available, else a uniform placeholder that permutation
            # importance will override downstream.
            values = np.ones(len(self.features))
        total = values.sum() or 1.0
        return pd.Series(values / total, index=self.features).sort_values(ascending=False)


def _make_one(cfg: Config, quantile: float | None, seed: int):
    params = cfg.get("models.gbdt", {})
    n_estimators = int(params.get("n_estimators", 400))
    lr = float(params.get("learning_rate", 0.05))
    depth = int(params.get("max_depth", 6))
    leaf = int(params.get("min_samples_leaf", 20))

    if HAS_LIGHTGBM:
        kwargs = dict(
            n_estimators=n_estimators,
            learning_rate=lr,
            num_leaves=max(15, 2**depth // 2),
            max_depth=depth,
            min_child_samples=leaf,
            subsample=0.85,
            subsample_freq=1,
            colsample_bytree=0.85,
            reg_lambda=1.0,
            random_state=seed,
            n_jobs=-1,
            verbose=-1,
        )
        if quantile is not None:
            kwargs.update(objective="quantile", alpha=quantile)
        return lgb.LGBMRegressor(**kwargs)

    kwargs = dict(
        max_iter=n_estimators,
        learning_rate=lr,
        max_depth=depth,
        min_samples_leaf=leaf,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=seed,
    )
    if quantile is not None:
        kwargs.update(loss="quantile", quantile=quantile)
    return HistGradientBoostingRegressor(**kwargs)


def train(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cfg: Config,
    quantiles: list[float] | None = None,
    features: list[str] | None = None,
) -> QuantileGBDT:
    quantiles = quantiles or cfg.get("models.quantiles", [0.1, 0.5, 0.9])
    if 0.5 not in quantiles:
        quantiles = sorted(set(list(quantiles) + [0.5]))

    features = features or list(X_train.columns)
    seed = int(cfg.get("project.seed", 42))

    X_train = X_train[features]
    models: dict[float, Any] = {}
    for q in quantiles:
        model = _make_one(cfg, q, seed)
        model.fit(X_train, y_train)
        models[q] = model

    backend = "lightgbm" if HAS_LIGHTGBM else "sklearn-hist"
    log.info("Trained %d quantile models (%s) on %d rows x %d features",
             len(models), backend, len(X_train), len(features))
    return QuantileGBDT(models=models, features=features, backend=backend)


def monotonic_fix(preds: pd.DataFrame) -> pd.DataFrame:
    """Quantile crossing happens in practice; sort the columns per row."""
    qs = sorted([c for c in preds.columns if c.startswith("q")])
    values = np.sort(preds[qs].to_numpy(), axis=1)
    fixed = pd.DataFrame(values, index=preds.index, columns=qs)
    fixed["interval_width"] = fixed[qs[-1]] - fixed[qs[0]]
    return fixed
