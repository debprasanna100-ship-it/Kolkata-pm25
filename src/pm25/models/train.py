"""Train every model, for every horizon, with both validation schemes."""

from __future__ import annotations

import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ..config import Config
from ..features import feature_columns, make_features, usable_feature_columns
from ..utils import ensure_dir, get_logger, read_table, write_json, write_table
from . import deep, evaluate
from .baselines import Climatology, LinearBaseline, Persistence
from .gbdt import monotonic_fix, train as train_gbdt

log = get_logger("pm25.train")


def _xy(df: pd.DataFrame, cols: list[str], medians: pd.Series | None = None):
    X = df[cols].astype(float)
    med = X.median() if medians is None else medians
    X = X.fillna(med)
    return X, df["y"].astype(float), med


def _score(y_true, y_pred, times=None) -> dict:
    """Overall metrics on everything, episode metrics on the winter slice.

    Recall/FAR are a winter question: the smog season (Nov-Feb) is where the
    threshold crossings cluster and where detection skill actually matters.
    Restricting the slice matches what the validation protocol documents.
    """
    base = evaluate.regression_metrics(y_true, y_pred)
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    if times is not None:
        months = pd.Series(pd.to_datetime(times)).dt.month
        winter = months.isin(evaluate.WINTER_MONTHS).to_numpy()
        y, p = y[winter], p[winter]
    base.update(evaluate.episode_metrics(y, p))
    return base


def run(
    cfg: Config,
    horizons: list[int] | None = None,
    test_year: int | None = None,
    with_loso: bool = True,
    with_deep: bool = False,
    quick: bool = False,
) -> dict:
    started = time.time()
    dataset_path = cfg.dataset_csv
    if not dataset_path.exists():
        raise SystemExit(
            f"Dataset not found at {dataset_path}. Run `python -m pm25.cli build` first."
        )

    df = read_table(dataset_path)
    df["time"] = pd.to_datetime(df["time"], utc=True)

    horizons = horizons if horizons is not None else cfg.get("models.horizons", [1, 6, 24])
    test_year = int(test_year or cfg.get("models.test_year", 2026))

    artifacts = cfg.path("artifacts")
    models_dir = ensure_dir(artifacts / "models")

    all_metrics: dict[str, dict] = {}
    predictions_h0: pd.DataFrame | None = None
    importance_h0: pd.DataFrame | None = None
    attrib_frame: pd.DataFrame | None = None

    # The shortest horizon is the one the dashboard shows as the "nowcast".
    primary_horizon = min(horizons)

    for horizon in horizons:
        log.info("=" * 62)
        log.info("HORIZON +%dh", horizon)

        feat = make_features(df, cfg, horizon=horizon)
        cols = usable_feature_columns(feat, feature_columns(feat))
        train_df, test_df = evaluate.time_split(feat, test_year)

        X_tr, y_tr, medians = _xy(train_df, cols)
        X_te, y_te, _ = _xy(test_df, cols, medians)

        log.info("train %d rows (%s..%s) | test %d rows (%s..%s)",
                 len(train_df), train_df["time"].min().date(), train_df["time"].max().date(),
                 len(test_df), test_df["time"].min().date(), test_df["time"].max().date())

        results: dict[str, dict] = {}

        # --- baselines -----------------------------------------------------
        persistence = Persistence().fit(train_df, y_tr)
        results["persistence"] = _score(y_te, persistence.predict(test_df), test_df["time"])

        climatology = Climatology().fit(train_df, y_tr)
        results["climatology"] = _score(y_te, climatology.predict(test_df), test_df["time"])

        ridge = LinearBaseline().fit(X_tr, y_tr)
        results["ridge"] = _score(y_te, ridge.predict(X_te), test_df["time"])

        # --- gradient boosting --------------------------------------------
        gbdt = train_gbdt(X_tr, y_tr, cfg)
        raw = gbdt.predict(X_te)
        intervals = monotonic_fix(raw)
        pred = intervals["q50"].to_numpy()
        results["gbdt"] = _score(y_te, pred, test_df["time"])

        # Interval coverage: how often does the truth land inside q10..q90?
        lo, hi = intervals["q10"].to_numpy(), intervals["q90"].to_numpy()
        inside = (y_te.to_numpy() >= lo) & (y_te.to_numpy() <= hi)
        results["gbdt"]["pi80_coverage"] = float(np.mean(inside))
        results["gbdt"]["pi80_mean_width"] = float(np.mean(hi - lo))

        joblib.dump(gbdt, models_dir / f"gbdt_h{horizon}.joblib")

        # --- optional sequence model ---------------------------------------
        if with_deep and deep.is_available():
            # The LSTM cannot handle NaN, so hand it the imputed matrices.
            tr_imp = train_df.copy()
            te_imp = test_df.copy()
            tr_imp[cols] = X_tr.to_numpy()
            te_imp[cols] = X_te.to_numpy()
            seq_pred = deep.train_sequence_model(tr_imp, te_imp, cols, seq_len=24)
            if seq_pred is not None:
                mask = np.isfinite(seq_pred)
                if mask.sum() > 100:
                    results["lstm"] = _score(
                        y_te.to_numpy()[mask], seq_pred[mask], test_df["time"].to_numpy()[mask]
                    )
                    results["lstm"]["n_skipped_warmup"] = int((~mask).sum())

        # --- leave-one-station-out (median model only, for speed) ----------
        if with_loso and not quick:
            loso_rows = []
            for station, lo_train, lo_test in evaluate.loso_splits(feat):
                a, b, med = _xy(lo_train, cols)
                c, d, _ = _xy(lo_test, cols, med)
                m = train_gbdt(a, b, cfg, quantiles=[0.5], features=cols)
                p = m.predict(c)["q50"].to_numpy()
                row = evaluate.regression_metrics(d, p)
                row["station"] = station
                loso_rows.append(row)
            if loso_rows:
                loso_df = pd.DataFrame(loso_rows).set_index("station")
                results["gbdt_loso"] = {
                    "per_station": loso_df.round(3).to_dict(orient="index"),
                    "mean_r2": float(loso_df["r2"].mean()),
                    "mean_rmse": float(loso_df["rmse"].mean()),
                }

        all_metrics[f"h{horizon}"] = {
            "horizon_h": horizon,
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "n_features": len(cols),
            "models": results,
        }

        if horizon == primary_horizon:
            extra = [c for c in ("aod_missing", "rh", "pbl", "wind_speed", "month") if c in test_df.columns]
            pred_frame = test_df[["time", "station", "y"] + extra].copy()
            pred_frame["pred"] = pred
            pred_frame["q10"] = lo
            pred_frame["q90"] = hi
            predictions_h0 = pred_frame

            imp = gbdt.feature_importance().reset_index()
            imp.columns = ["feature", "importance"]
            importance_h0 = imp

            # Attribution model: same data, no autoregressive features, so the
            # drivers we report are meteorology and emissions, not persistence.
            log.info("training attribution model (no lag features)")
            attrib_feat = make_features(df, cfg, horizon=0, include_lags=False)
            acols = usable_feature_columns(attrib_feat, feature_columns(attrib_feat))
            a_tr, b_tr = evaluate.time_split(attrib_feat, test_year)
            Xa, ya, meda = _xy(a_tr, acols)
            attrib_model = train_gbdt(Xa, ya, cfg, quantiles=[0.5], features=acols)
            joblib.dump(attrib_model, models_dir / "attrib_h0.joblib")
            attrib_frame = a_tr.assign(pred=attrib_model.predict(Xa)["q50"].to_numpy())

    # --- persist -----------------------------------------------------------
    write_json(all_metrics, cfg.metrics_json)
    if predictions_h0 is not None:
        write_table(predictions_h0, artifacts / "predictions.csv")
    if importance_h0 is not None:
        write_table(importance_h0, artifacts / "importance_h0.csv")
    if attrib_frame is not None:
        write_table(attrib_frame, artifacts / "attrib_train.csv")

    _print_summary(all_metrics)

    log.info("done in %.1fs -> %s", time.time() - started, cfg.metrics_json)
    return all_metrics


def _print_summary(metrics: dict) -> None:
    rows = []
    for key, block in metrics.items():
        for name, m in block["models"].items():
            if "rmse" not in m:
                continue
            rows.append(
                {
                    "horizon": block["horizon_h"],
                    "model": name,
                    "rmse": round(m["rmse"], 2),
                    "mae": round(m["mae"], 2),
                    "r2": round(m.get("r2", float("nan")), 3),
                    "ep_recall": round(m.get("recall", float("nan")), 3) if "recall" in m else None,
                    "pi80": round(m.get("pi80_coverage", float("nan")), 3) if "pi80_coverage" in m else None,
                }
            )
    table = pd.DataFrame(rows)
    log.info("\n%s", table.to_string(index=False))
