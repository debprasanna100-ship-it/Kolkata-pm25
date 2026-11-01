"""Source attribution: combine model explanations with rule-based proxies.

The claim this produces is deliberately modest:

  "In winter, the features that drive the model are also the features that
   drive the biomass-burning proxy. In pre-monsoon, the model shifts to wind
   and humidity, matching the dust proxy."

That is a *consistency* check, not proof of source apportionment. It is still
much stronger than either artefact alone, and it is the honest ceiling for
public data without speciation.
"""

from __future__ import annotations

import joblib
import numpy as np
import pandas as pd

from ..config import Config
from ..features import feature_columns
from ..utils import get_logger, read_json, read_table, write_json, write_table
from . import importance, proxies

log = get_logger("pm25.attribution")


def run(cfg: Config, top_k: int = 5) -> dict:
    artifacts = cfg.path("artifacts")
    train_path = artifacts / "attrib_train.csv"
    model_path = artifacts / "models" / "attrib_h0.joblib"

    if not train_path.exists() or not model_path.exists():
        raise SystemExit(
            "Attribution artefacts missing. Run `python -m pm25.cli train` first "
            "(it writes attrib_train.csv and models/attrib_h0.joblib)."
        )

    frame = read_table(train_path)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    model = joblib.load(model_path)

    cols = feature_columns(frame)
    X = frame[cols].astype(float)
    X = X.fillna(X.median())
    y = frame["y"].astype(float)

    # --- SHAP / permutation -----------------------------------------------
    result = importance.compute(model, X, y, sample=min(4000, len(X)))
    method = result["method"]
    per_feature = result["per_feature"]
    write_table(per_feature, artifacts / "importance_attrib.csv")

    seasonal_table, seasonal_method = importance.seasonal_importance(
        model, X, y, frame["time"], sample=min(4000, len(X))
    )
    write_table(seasonal_table, artifacts / "seasonal_importance.csv")

    if seasonal_method != "shap":
        log.warning(
            "`shap` is not installed - seasonal importance uses within-season permutation "
            "instead of SHAP. Same schema, different metric. `pip install shap` for exact "
            "attributions."
        )

    # --- proxies -----------------------------------------------------------
    labelled = proxies.assign(frame)
    labelled["season"] = labelled["time"].dt.month.map(importance.season_of)

    prevalence = proxies.prevalence(labelled, by="season")
    write_table(prevalence.reset_index(), artifacts / "proxy_prevalence.csv")

    concentration = proxies.mean_concentration_by_proxy(labelled)
    write_table(concentration.reset_index(), artifacts / "proxy_concentration.csv")

    # --- agreement ---------------------------------------------------------
    agreement = pd.DataFrame()
    verdict = {}
    if not seasonal_table.empty:
        agreement, verdict = _agreement(seasonal_table, prevalence, top_k)
        write_table(agreement, artifacts / "proxy_agreement.csv")

    summary = {
        "method": method,
        "seasonal_method": seasonal_method,
        "top_features": per_feature.head(12)["feature"].tolist(),
        "proxy_share_overall": labelled["proxy"].value_counts(normalize=True).round(3).to_dict(),
        "agreement": verdict,
        "caveat": (
            "Proxy labels are rule-based heuristics over co-pollutants and meteorology, "
            "not measured source contributions. Agreement with SHAP supports the "
            "interpretation; it does not prove it."
        ),
    }
    write_json(summary, artifacts / "attribution_summary.json")

    _print(summary, prevalence, agreement)
    return summary


def _agreement(seasonal: pd.DataFrame, prevalence: pd.DataFrame, top_k: int):
    """For each season, does a proxy's expected drivers reach the SHAP top-k?"""
    rows = []
    verdict: dict[str, dict] = {}

    for season in seasonal["season"].unique():
        block = seasonal[seasonal["season"] == season].sort_values("mean_abs_shap", ascending=False)
        top = block.head(top_k)["feature"].tolist()
        season_verdict = {"top_features": top, "proxies": {}}

        for proxy_name, expected in proxies.EXPECTED_DRIVERS.items():
            share = float(prevalence.loc[season, proxy_name]) if (
                season in prevalence.index and proxy_name in prevalence.columns
            ) else 0.0

            hits = [f for f in expected if f in top]
            rows.append(
                {
                    "season": season,
                    "proxy": proxy_name,
                    "proxy_share": round(share, 3),
                    "expected_drivers": ", ".join(expected),
                    "drivers_in_top": ", ".join(hits) if hits else "-",
                    "n_hits": len(hits),
                    "supported": bool(hits) and share >= 0.05,
                }
            )
            season_verdict["proxies"][proxy_name] = {
                "share": round(share, 3),
                "hits": hits,
                "supported": bool(hits) and share >= 0.05,
            }

        verdict[season] = season_verdict

    return pd.DataFrame(rows), verdict


def _print(summary: dict, prevalence: pd.DataFrame, agreement: pd.DataFrame) -> None:
    log.info("")
    log.info("SOURCE ATTRIBUTION (%s)", summary["method"].upper())
    log.info("-" * 62)
    log.info("Top model drivers: %s", ", ".join(summary["top_features"][:8]))
    log.info("")
    log.info("Proxy prevalence by season:\n%s", prevalence.to_string())
    if not agreement.empty:
        log.info("")
        log.info("Proxy vs SHAP agreement:\n%s", agreement.to_string(index=False))
        supported = agreement[agreement["supported"]]
        log.info("")
        log.info("%d of %d season-proxy pairs are supported by the model's own attributions.",
                 len(supported), len(agreement))
