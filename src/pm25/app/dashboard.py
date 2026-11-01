"""Streamlit dashboard for the Kolkata PM2.5 project.

Reads only from disk (data/processed + artifacts), so it never triggers a
recompute and can be shipped alongside a report.

    python -m pm25.cli app
    # or: streamlit run src/pm25/app/dashboard.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Paths and loading
# ---------------------------------------------------------------------------

ROOT = Path(os.environ.get("PM25_ROOT", Path(__file__).resolve().parents[3]))
ARTIFACTS = ROOT / "artifacts"
PROCESSED = ROOT / "data" / "processed"

ACCENT = "#c2410c"
COOL = "#0f766e"


@st.cache_data(show_spinner=False)
def load_csv(path: str) -> pd.DataFrame | None:
    p = Path(path)
    if not p.exists():
        return None
    df = pd.read_csv(p)
    for col in ("time", "date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    return df


@st.cache_data(show_spinner=False)
def load_json(path: str) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def missing_notice(what: str, command: str) -> None:
    st.warning(f"**{what} not found.** Run this first:\n\n```bash\n{command}\n```")


# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Kolkata PM2.5 — Estimation & Source Attribution",
    page_icon="🌫️",
    layout="wide",
)

st.set_page_config(
    page_title="Kolkata PM2.5 — Estimation & Source Attribution",
    page_icon="🌫️",
    layout="wide",
)

st.title("🌫️ Hourly PM2.5 Estimation & Source Attribution — Kolkata")
st.caption(
    "Satellite AOD + ERA5 meteorology + fire transport + ground stations. "
    "Model: quantile gradient boosting. Explanation: SHAP vs rule-based source proxies."
)
st.markdown(
    "<small>Tip: plots are cached after first render. The live dataset is ~24K rows; "
    "the Overview tab samples 4,000 rows for the scatter so the dashboard loads quickly.</small>",
    unsafe_allow_html=True,
)

dataset = load_csv(str(PROCESSED / "dataset.csv"))
metrics = load_json(str(ARTIFACTS / "metrics.json"))
predictions = load_csv(str(ARTIFACTS / "predictions.csv"))
importance = load_csv(str(ARTIFACTS / "importance_attrib.csv"))
# Seasonal importance: SHAP when available, within-season permutation otherwise.
shap_seasonal = load_csv(str(ARTIFACTS / "seasonal_importance.csv"))
if shap_seasonal is None:      # backwards compatibility with older runs
    shap_seasonal = load_csv(str(ARTIFACTS / "shap_by_season.csv"))
prevalence = load_csv(str(ARTIFACTS / "proxy_prevalence.csv"))
agreement = load_csv(str(ARTIFACTS / "proxy_agreement.csv"))
attrib_summary = load_json(str(ARTIFACTS / "attribution_summary.json"))

if dataset is None:
    missing_notice("Dataset", "python -m pm25.cli build --mode demo")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

stations = sorted(dataset["station"].unique())
with st.sidebar:
    st.header("Filters")
    chosen = st.multiselect("Stations", stations, default=stations)
    if dataset["time"].notna().any():
        lo, hi = dataset["time"].min().date(), dataset["time"].max().date()
        window = st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
    else:
        window = None

    st.divider()
    st.caption(f"Root: `{ROOT}`")
    if metrics is None:
        st.error("No metrics yet — run `python -m pm25.cli train`")
    if attrib_summary is None:
        st.info("No attribution yet — run `python -m pm25.cli explain`")


def filter_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[df["station"].isin(chosen)]
    if window and isinstance(window, tuple) and len(window) == 2 and "time" in out:
        start, end = pd.Timestamp(window[0], tz="UTC"), pd.Timestamp(window[1], tz="UTC") + pd.Timedelta(days=1)
        out = out[(out["time"] >= start) & (out["time"] < end)]
    return out


tabs = st.tabs(["Overview", "Model", "Explainability", "Sources", "Robustness", "Method"])

# ---------------------------------------------------------------------------
# 1. Overview
# ---------------------------------------------------------------------------
with tabs[0]:
    view = filter_frame(dataset)

    c1, c2, c3, c4 = st.columns(4)
    # Aggregate summaries up front (cheap), cache plots (expensive).
    st.markdown(f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
        <div style="background:#f0f2f6;padding:15px;border-radius:8px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{len(view):,}</div>
            <div style="font-size:12px;color:#555">rows</div>
        </div>
        <div style="background:#f0f2f6;padding:15px;border-radius:8px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{view['pm25'].mean():.1f}</div>
            <div style="font-size:12px;color:#555">mean PM2.5</div>
        </div>
        <div style="background:#f0f2f6;padding:15px;border-radius:8px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{view['pm25'].quantile(0.95):.1f}</div>
            <div style="font-size:12px;color:#555">95th percentile</div>
        </div>
        <div style="background:#f0f2f6;padding:15px;border-radius:8px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{100*(1-view['aod'].isna().mean()):.0f}</div>
            <div style="font-size:12px;color:#555">AOD coverage</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    monthly = (
        view.dropna(subset=["pm25"])
        .assign(month=lambda d: d["time"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp())
        .groupby(["month", "station"])["pm25"].mean()
        .reset_index()
    )
    st.subheader("Monthly mean by station")
    @st.cache_data(show_spinner=True)
    def _monthly_fig(df):
        return px.line(df, x="month", y="pm25", color="station", markers=True,
                       labels={"pm25": "PM2.5 (µg/m³)", "month": ""})
    if not monthly.empty:
        st.plotly_chart(_monthly_fig(monthly), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Diurnal cycle")
        diurnal = (
            view.dropna(subset=["pm25"])
            .assign(hour=lambda d: d["time"].dt.hour)
            .groupby(["hour", "station"])["pm25"].mean()
            .reset_index()
        )
        if not diurnal.empty:
            @st.cache_data(show_spinner=True)
            def _diurnal_fig(df):
                return px.line(df, x="hour", y="pm25", color="station",
                               labels={"pm25": "PM2.5 (µg/m³)", "hour": "hour of day (UTC)"})
            st.plotly_chart(_diurnal_fig(diurnal), use_container_width=True)

    with right:
        st.subheader("Distribution")
        @st.cache_data(show_spinner=True)
        def _violin_fig(view, chosen):
            fig = go.Figure()
            for station in chosen:
                series = view.loc[view["station"] == station, "pm25"].dropna()
                if len(series):
                    fig.add_trace(go.Violin(y=series, name=station, box_visible=True,
                                            meanline_visible=True))
            fig.update_layout(yaxis_title="PM2.5 (µg/m³)", showlegend=False, height=420)
            return fig
        if view["pm25"].notna().any():
            st.plotly_chart(_violin_fig(view, chosen), use_container_width=True)

# ---------------------------------------------------------------------------
# 2. Model
# ---------------------------------------------------------------------------
with tabs[1]:
    if metrics is None:
        missing_notice("Metrics", "python -m pm25.cli train")
    else:
        rows = []
        for key, block in metrics.items():
            for name, m in block["models"].items():
                if not isinstance(m, dict) or "rmse" not in m:
                    continue
                rows.append(
                    {
                        "horizon (h)": block["horizon_h"],
                        "model": name,
                        "RMSE": m.get("rmse"),
                        "MAE": m.get("mae"),
                        "R²": m.get("r2"),
                        "bias": m.get("bias"),
                        "winter episode recall": m.get("recall"),
                        "PI80 coverage": m.get("pi80_coverage"),
                    }
                )
        table = pd.DataFrame(rows).sort_values(["horizon (h)", "model"])

        st.subheader("Accuracy by horizon")
        st.dataframe(
            table.style.format(
                {"RMSE": "{:.2f}", "MAE": "{:.2f}", "R²": "{:.3f}", "bias": "{:+.2f}",
                 "winter episode recall": "{:.2f}", "PI80 coverage": "{:.2f}"},
                na_rep="—",
            ),
            use_container_width=True, hide_index=True,
        )

        r2_fig = px.bar(
            table.dropna(subset=["R²"]),
            x="horizon (h)", y="R²", color="model", barmode="group",
            title="R² by forecast horizon — the drop from 0h to 24h is the honest story",
        )
        r2_fig.update_layout(height=380)
        st.plotly_chart(r2_fig, use_container_width=True)

        loso = None
        for block in metrics.values():
            if "gbdt_loso" in block.get("models", {}):
                loso = block["models"]["gbdt_loso"]
                break
        if loso:
            st.subheader("Leave-one-station-out")
            st.caption(
                "Train on three stations, test on the fourth. This is the number that "
                "matters for a city that has no monitor."
            )
            loso_df = pd.DataFrame(loso["per_station"]).T.reset_index().rename(columns={"index": "station"})
            st.dataframe(loso_df, use_container_width=True, hide_index=True)
            st.caption(f"Mean R² across held-out stations: **{loso['mean_r2']:.3f}** · "
                       f"mean RMSE **{loso['mean_rmse']:.2f} µg/m³**")

        if predictions is not None:
            st.subheader("Nowcast: predicted vs observed")
            pred_view = predictions[predictions["station"].isin(chosen)]
            if not pred_view.empty:
                sample = pred_view.sample(min(4000, len(pred_view)), random_state=0)
                @st.cache_data(show_spinner=True)
                def _scatter_fig(sample):
                    limit = float(max(sample["y"].max(), sample["pred"].max()))
                    fig = px.scatter(sample, x="y", y="pred", color="station", opacity=0.45,
                                     labels={"y": "observed PM2.5", "pred": "predicted PM2.5"})
                    fig.add_shape(type="line", x0=0, y0=0, x1=limit, y1=limit,
                                  line=dict(dash="dash", color="grey"))
                    fig.update_layout(height=480)
                    return fig
                scatter = _scatter_fig(sample)
                st.plotly_chart(scatter, use_container_width=True)

                if {"q10", "q90"} <= set(pred_view.columns):
                    st.subheader("Prediction interval")
                    ts = pred_view.sort_values("time").tail(400)

                    @st.cache_data(show_spinner=True)
                    def _band_fig(ts):
                        band = go.Figure()
                        band.add_trace(go.Scatter(x=ts["time"], y=ts["q90"], line=dict(width=0),
                                                  showlegend=False))
                        band.add_trace(go.Scatter(x=ts["time"], y=ts["q10"], line=dict(width=0),
                                                  fill="tonexty", fillcolor="rgba(194,65,12,0.18)",
                                                  name="80% interval"))
                        band.add_trace(go.Scatter(x=ts["time"], y=ts["y"], name="observed",
                                                  line=dict(color="black", width=1.4)))
                        band.add_trace(go.Scatter(x=ts["time"], y=ts["pred"], name="predicted",
                                                  line=dict(color=ACCENT, width=1.6)))
                        band.update_layout(height=380, yaxis_title="PM2.5 (µg/m³)")
                        return band
                    st.plotly_chart(_band_fig(ts), use_container_width=True)

# ---------------------------------------------------------------------------
# 3. Explainability
# ---------------------------------------------------------------------------
with tabs[2]:
    if importance is None:
        missing_notice("Feature importance", "python -m pm25.cli explain")
    else:
        method = (attrib_summary or {}).get("method", "unknown")
        st.caption(
            f"Attribution model = same features **minus autoregressive PM2.5 lags**, "
            f"so the drivers shown are meteorology, emissions and transport — not persistence. "
            f"Method: **{method}**."
        )

        top = importance.head(15).sort_values("importance")
        st.subheader("Global importance")
        st.plotly_chart(
            px.bar(top, x="importance", y="feature", orientation="h",
                   color_discrete_sequence=[ACCENT]),
            use_container_width=True,
        )

        if shap_seasonal is not None and not shap_seasonal.empty:
            st.subheader("Seasonal shift in drivers")
            st.caption(
                "Share of total attribution per season. If the model is learning physics "
                "rather than noise, the profile should move: fires and low wind in winter, "
                "dust and ventilation in pre-monsoon."
            )
            pivot = shap_seasonal.pivot_table(index="feature", columns="season", values="share")
            keep = shap_seasonal.groupby("feature")["share"].max().nlargest(14).index
            pivot = pivot.loc[[f for f in keep if f in pivot.index]]

            @st.cache_data(show_spinner=True)
            def _heatmap(pivot):
                heat = px.imshow(pivot, aspect="auto", color_continuous_scale="OrRd",
                                 labels={"x": "", "y": "", "color": "share"})
                heat.update_layout(height=520)
                return heat
            st.plotly_chart(_heatmap(pivot), use_container_width=True)

# ---------------------------------------------------------------------------
# 4. Sources
# ---------------------------------------------------------------------------
with tabs[3]:
    if prevalence is None:
        missing_notice("Source proxies", "python -m pm25.cli explain")
    else:
        st.caption(
            "Proxy labels are rule-based heuristics over co-pollutants and meteorology — "
            "not measured source contributions. The value is in the **agreement check** below."
        )

        left, right = st.columns([1.1, 1])
        with left:
            st.subheader("Proxy prevalence by season")
            pv = prevalence.set_index("season") if "season" in prevalence else prevalence

            @st.cache_data(show_spinner=True)
            def _prox_heat(pv):
                return px.imshow(pv, aspect="auto", color_continuous_scale="Teal",
                                 labels={"color": "share of hours"})
            st.plotly_chart(_prox_heat(pv), use_container_width=True)
        with right:
            st.subheader("Mean PM2.5 per proxy")
            conc = load_csv(str(ARTIFACTS / "proxy_concentration.csv"))
            if conc is not None:
                st.dataframe(conc, use_container_width=True, hide_index=True)

        if agreement is not None:
            st.subheader("Does the model agree with the proxies?")
            st.dataframe(
                agreement,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "supported": st.column_config.CheckboxColumn("supported"),
                    "proxy_share": st.column_config.ProgressColumn(
                        "proxy share", min_value=0.0, max_value=1.0, format="%.2f"
                    ),
                },
            )
            supported = int(agreement["supported"].sum()) if "supported" in agreement else 0
            st.metric("Season × proxy pairs supported by SHAP", f"{supported} / {len(agreement)}")
            st.caption(
                "A pair counts as supported when the proxy occupies ≥5% of hours in that season "
                "*and* at least one of its expected drivers appears in the model's top-5 features."
            )

# ---------------------------------------------------------------------------
# 5. Robustness
# ---------------------------------------------------------------------------
with tabs[4]:
    st.subheader("What happens when the satellite is blind?")
    st.caption(
        "AOD is missing whenever it is cloudy — which correlates with exactly the "
        "conditions where the model is most needed. Most papers report only the "
        "all-sky number. This splits it."
    )

    if predictions is None or "aod_missing" not in predictions:
        missing_notice("Predictions with AOD flags", "python -m pm25.cli train")
    else:
        pred = predictions[predictions["station"].isin(chosen)].copy()
        pred["aod_state"] = pred["aod_missing"].map({1: "AOD missing", 0: "AOD available"})

        rows = []
        for state, chunk in pred.groupby("aod_state"):
            err = chunk["pred"] - chunk["y"]
            rows.append(
                {
                    "condition": state,
                    "n": len(chunk),
                    "RMSE": float((err**2).mean() ** 0.5),
                    "MAE": float(err.abs().mean()),
                    "R²": 1 - float((err**2).sum() / ((chunk["y"] - chunk["y"].mean()) ** 2).sum()),
                    "mean interval width": float((chunk["q90"] - chunk["q10"]).mean())
                    if {"q10", "q90"} <= set(chunk.columns) else None,
                }
            )
        st.dataframe(pd.DataFrame(rows).round(2), use_container_width=True, hide_index=True)

        if {"q10", "q90"} <= set(pred.columns):
            st.subheader("Interval width vs humidity")
            st.caption("If the intervals widen with humidity, the model knows it is guessing.")
            pred["rh_bin"] = pd.cut(pred["rh"], bins=8)

            rows = []
            for (rh_bin, state), chunk in pred.groupby(["rh_bin", "aod_state"], observed=True):
                rows.append(
                    {
                        "rh_mid": float(rh_bin.mid),
                        "aod_state": state,
                        "interval_width": float((chunk["q90"] - chunk["q10"]).mean()),
                    }
                )
            width = pd.DataFrame(rows).sort_values("rh_mid")

            @st.cache_data(show_spinner=True)
            def _width_fig(width):
                return px.line(width, x="rh_mid", y="interval_width", color="aod_state",
                               markers=True,
                               labels={"rh_mid": "relative humidity (%)",
                                       "interval_width": "80% interval width"})
            st.plotly_chart(_width_fig(width), use_container_width=True)

# ---------------------------------------------------------------------------
# 6. Method
# ---------------------------------------------------------------------------
with tabs[5]:
    st.markdown(
        f"""
### What this is

An hourly PM2.5 estimator for Kolkata CAAQMS stations, trained on satellite AOD,
reanalysis meteorology, fire transport and time features — with an attribution
layer that is honest about its limits.

### Validation

| Split | Question it answers |
|---|---|
| Time split (train on earlier years, test on the latest) | Does it work next year? |
| Leave-one-station-out | Does it work at a station with no monitor? |
| Winter episode metrics | Does it catch the days people actually care about? |
| PI80 coverage | Are the uncertainty bands calibrated? |

Random train/test splits are **not** used anywhere. Consecutive hours are
autocorrelated, so a random split leaks the answer.

### The honest limitations

1. **AOD is daily, not hourly.** MODIS/MAIAC gives one retrieval per day at 1 km;
   TROPOMI gives one overpass. Hourly variation comes from weather, time and lags.
2. **AOD is missing when it is cloudy** — systematically, not randomly. The
   Robustness tab quantifies the damage.
3. **Source proxies are heuristics, not PMF.** Real apportionment needs speciated
   filter data (ions, metals, OC/EC) at hourly resolution, which is not publicly
   available for Kolkata. The agreement check is a consistency argument, not proof.
4. **Ground truth is a station, not a person.** A monitor at 3 m height in a
   courtyard is not the exposure of someone on a bike 200 m away.

### Reproduce

```bash
python -m pm25.cli build --mode demo    # or --mode live with API keys
python -m pm25.cli train
python -m pm25.cli explain
python -m pm25.cli app
```
"""
    )
