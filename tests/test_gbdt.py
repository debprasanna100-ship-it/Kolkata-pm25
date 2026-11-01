"""Tests for the quantile GBDT wrapper: interval ordering and the crossing fix."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pm25.config import Config
from pm25.models.gbdt import QuantileGBDT, monotonic_fix, train as train_gbdt


def test_monotonic_fix_sorts_crossed_rows():
    preds = pd.DataFrame(
        {"q10": [5.0, 10.0], "q50": [3.0, 12.0], "q90": [4.0, 11.0]}
    )
    fixed = monotonic_fix(preds)
    np.testing.assert_allclose(fixed.loc[0, ["q10", "q50", "q90"]], [3.0, 4.0, 5.0])
    np.testing.assert_allclose(fixed.loc[1, ["q10", "q50", "q90"]], [10.0, 11.0, 12.0])
    assert (fixed["q10"] <= fixed["q50"]).all()
    assert (fixed["q50"] <= fixed["q90"]).all()
    np.testing.assert_allclose(fixed["interval_width"], [2.0, 2.0])


def test_quantile_training_then_fix_is_ordered(tmp_path):
    cfg = Config.load(root=tmp_path)
    cfg.set("models.gbdt.n_estimators", 40)

    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(300, 4)), columns=[f"f{i}" for i in range(4)])
    y = pd.Series(10.0 * X["f0"] + rng.normal(0, 2.0, 300))

    model = train_gbdt(X, y, cfg)
    assert isinstance(model, QuantileGBDT)
    assert model.features == list(X.columns)

    out = monotonic_fix(model.predict(X))
    assert (out["q10"] <= out["q50"]).all()
    assert (out["q50"] <= out["q90"]).all()
    assert float((out["q90"] - out["q10"]).mean()) > 0.0   # a real interval, not a point

    # The 80% interval should roughly cover 80% of homoscedastic noise.
    inside = ((y >= out["q10"]) & (y <= out["q90"])).mean()
    assert 0.65 < inside < 0.95


def test_feature_importance_is_normalised(tmp_path):
    cfg = Config.load(root=tmp_path)
    cfg.set("models.gbdt.n_estimators", 30)
    rng = np.random.default_rng(1)
    X = pd.DataFrame(rng.normal(size=(200, 3)), columns=["a", "b", "c"])
    y = pd.Series(5.0 * X["a"])
    model = train_gbdt(X, y, cfg, quantiles=[0.5])
    importance = model.feature_importance()
    assert len(importance) == 3
    np.testing.assert_allclose(importance.sum(), 1.0)
