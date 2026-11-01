"""Feature attribution: SHAP when available, permutation importance otherwise.

Both answer "how much does this feature move the prediction", but SHAP is
additive and sign-aware, so it can support statements like "low boundary layer
adds +38 µg/m³ on winter mornings". Permutation importance only gives magnitude,
which is why the dashboard labels whichever method actually ran.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from ..utils import get_logger

log = get_logger("pm25.importance")

try:  # optional
    import shap
    HAS_SHAP = True
except Exception:  # pragma: no cover
    shap = None
    HAS_SHAP = False


SEASONS = {
    "winter": [12, 1, 2],
    "pre_monsoon": [3, 4, 5],
    "monsoon": [6, 7, 8, 9],
    "post_monsoon": [10, 11],
}


def season_of(month: int) -> str:
    for name, months in SEASONS.items():
        if month in months:
            return name
    return "other"


def _tree_shap(model, X: pd.DataFrame):
    """Try the fast exact path first, then the model-agnostic one."""
    estimator = model.median if hasattr(model, "median") else model
    try:
        explainer = shap.TreeExplainer(estimator)
        return explainer.shap_values(X)
    except Exception as exc:  # HistGradientBoosting is not a TreeExplainer target
        log.info("TreeExplainer unavailable (%s); trying generic Explainer", type(exc).__name__)
    try:
        explainer = shap.Explainer(estimator.predict, X)
        return explainer(X).values
    except Exception as exc:
        log.warning("SHAP failed entirely (%s) - falling back to permutation importance", exc)
        return None


def compute(model, X: pd.DataFrame, y: pd.Series, sample: int = 3000, seed: int = 42) -> dict:
    """Returns {'method', 'per_feature': DataFrame, 'shap': ndarray|None}."""
    rng = np.random.default_rng(seed)
    if len(X) > sample:
        idx = rng.choice(len(X), size=sample, replace=False)
        Xs = X.iloc[idx]
    else:
        Xs = X

    if HAS_SHAP:
        values = _tree_shap(model, Xs)
        if values is not None:
            values = np.asarray(values)
            if values.ndim == 3:          # (n, features, outputs)
                values = values[:, :, 0]
            mean_abs = np.abs(values).mean(axis=0)
            per_feature = (
                pd.DataFrame({"feature": Xs.columns, "importance": mean_abs})
                .sort_values("importance", ascending=False)
                .reset_index(drop=True)
            )
            log.info("SHAP computed on %d rows x %d features", len(Xs), Xs.shape[1])
            return {"method": "shap", "per_feature": per_feature, "shap": values, "X": Xs}

    result = permutation_importance(
        model.median if hasattr(model, "median") else model,
        Xs, y.iloc[idx] if len(X) > sample else y,
        n_repeats=5, random_state=seed, scoring="neg_root_mean_squared_error",
    )
    per_feature = (
        pd.DataFrame({"feature": Xs.columns, "importance": result.importances_mean})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    log.info("Permutation importance computed on %d rows", len(Xs))
    return {"method": "permutation", "per_feature": per_feature, "shap": None, "X": Xs}


def by_season(shap_values: np.ndarray, X: pd.DataFrame, times: pd.Series) -> pd.DataFrame:
    """Mean |SHAP| per feature per season - the core table for the dashboard."""
    months = pd.to_datetime(times).dt.month.to_numpy()
    seasons = np.array([season_of(m) for m in months])

    out = []
    for season in SEASONS:
        mask = seasons == season
        if mask.sum() < 50:
            continue
        mean_abs = np.abs(shap_values[mask]).mean(axis=0)
        frame = pd.DataFrame({"feature": X.columns, "season": season, "mean_abs_shap": mean_abs})
        out.append(frame)

    if not out:
        return pd.DataFrame(columns=["feature", "season", "mean_abs_shap"])

    result = pd.concat(out, ignore_index=True)
    # Normalise within season so the dashboard can compare shapes, not scales.
    result["share"] = result.groupby("season")["mean_abs_shap"].transform(
        lambda s: s / s.sum() if s.sum() > 0 else s
    )
    return result.sort_values(["season", "mean_abs_shap"], ascending=[True, False]).reset_index(drop=True)


def top_features(per_feature: pd.DataFrame, k: int = 8) -> list[str]:
    return per_feature.head(k)["feature"].tolist()


def seasonal_importance(model, X: pd.DataFrame, y: pd.Series, times: pd.Series,
                        sample: int = 4000, seed: int = 42) -> tuple[pd.DataFrame, str]:
    """Per-season importance with the same schema regardless of method.

    SHAP gives sign-aware, additive attributions. Without it we compute
    permutation importance *within each season*, which answers the same
    question - "what does the model lean on in winter vs pre-monsoon?" - using
    a different metric. The agreement test downstream does not care which one
    produced the ranking, only that the ranking is seasonal.

    Returns (table, method_name).
    """
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(X), size=min(sample, len(X)), replace=False) if len(X) > sample else np.arange(len(X))
    Xs = X.iloc[idx]
    ts = pd.to_datetime(times.iloc[idx] if hasattr(times, "iloc") else times).dt.month.to_numpy()
    seasons = np.array([season_of(m) for m in ts])

    if HAS_SHAP:
        values = _tree_shap(model, Xs)
        if values is not None:
            values = np.asarray(values)
            if values.ndim == 3:
                values = values[:, :, 0]
            table = by_season(values, Xs, pd.Series(pd.to_datetime(times.iloc[idx])))
            table["method"] = "shap"
            return table, "shap"

    estimator = model.median if hasattr(model, "median") else model
    rows = []
    for season in SEASONS:
        mask = seasons == season
        if mask.sum() < 100:
            continue
        X_season = Xs.iloc[mask]
        y_season = y.iloc[idx][mask]

        result = permutation_importance(
            estimator, X_season, y_season,
            n_repeats=3, random_state=seed,
            scoring="neg_root_mean_squared_error",
        )
        # Negative values mean the feature hurts when shuffled (noise); clamp to 0.
        importance = np.clip(result.importances_mean, 0, None)
        rows.append(pd.DataFrame({
            "feature": Xs.columns,
            "season": season,
            "mean_abs_shap": importance,
        }))

    if not rows:
        return pd.DataFrame(columns=["feature", "season", "mean_abs_shap", "share", "method"]), "permutation"

    table = pd.concat(rows, ignore_index=True)
    table["share"] = table.groupby("season")["mean_abs_shap"].transform(
        lambda s: s / s.sum() if s.sum() > 0 else s
    )
    table["method"] = "permutation"
    return table.sort_values(["season", "mean_abs_shap"], ascending=[True, False]).reset_index(drop=True), "permutation"
