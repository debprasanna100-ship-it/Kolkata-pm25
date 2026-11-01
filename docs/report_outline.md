# Report outline

A structure that survives a viva. Each section states what it must prove, so you can tell
whether it is done.

---

## Abstract (~200 words)

Estimate hourly surface PM2.5 at four Kolkata CAAQMS stations using satellite AOD,
ERA5 meteorology, fire transport and lagged observations; quantify uncertainty with quantile
regression; attribute drivers with SHAP and validate those attributions against independent
source proxies.

State the headline numbers: RMSE, R², LOSO R², interval coverage. State the limitation in
one sentence. Do not oversell.

---

## 1. Introduction

**Must prove:** the problem is real, local, and not already solved.

- Kolkata's PM2.5 exceeds CPCB limits for most of the year; the winter inversion is the
  acute episode.
- Ground monitoring is sparse: a handful of stations for ~15 million people.
- Satellite offers spatial coverage but measures a column, not surface mass.

---

## 2. Data

**Must prove:** you know exactly what each source gives you, at what resolution, with what
failure modes.

- 2.1 Ground truth (CPCB via OpenAQ) — station list, coverage, gaps
- 2.2 Meteorology (ERA5) — variables, why PBL matters
- 2.3 Satellite (MAIAC AOD, TROPOMI NO2) — **explicitly state daily, not hourly**
- 2.4 Fires (FIRMS) — confidence filtering, upwind transform
- 2.5 Static context (OSM roads)
- 2.6 Table: source × variable × temporal resolution × spatial resolution × missingness

The resolution table is where most student reports lose credibility. Include it.

---

## 3. Methods

- 3.1 Feature engineering — lags, cyclical encoding, ventilation coefficient
- 3.2 Leakage controls — why the AOD column is dropped at +24 h
- 3.3 Models — persistence, climatology, ridge, quantile GBDT, LSTM
- 3.4 Validation — time split, LOSO, episode metrics
- 3.5 Uncertainty — quantile regression, PI80 coverage
- 3.6 Attribution — SHAP on a lag-free model, rule-based proxies, agreement test

---

## 4. Results

**Must prove:** the model works, and you know where it fails.

- 4.1 Model comparison table (RMSE / MAE / R² / bias) per horizon
- 4.2 Persistence gap: how much better than "tomorrow = today"
- 4.3 LOSO table — the spatial generalisation number
- 4.4 Episode performance: recall and FAR above 120 µg/m³
- 4.5 Interval calibration: observed vs nominal coverage
- 4.6 **AOD-missing slice** — accuracy when the satellite is blind
- 4.7 Error seasonality: where in the year does the model break?

4.6 and 4.7 are the sections that make this better than a standard submission.

---

## 5. Source attribution

**Must prove:** two independent methods tell the same story.

- 5.1 Global SHAP ranking
- 5.2 Seasonal SHAP profile (heatmap)
- 5.3 Proxy prevalence by season
- 5.4 Agreement table — which pairs are supported
- 5.5 The narrative: winter = biomass + trapping; pre-monsoon = dust + ventilation;
  monsoon = washout; post-monsoon = transport onset

- 5.6 **Explicit limitations of the attribution.** Heuristics, not PMF. Consistency, not proof.

Section 5.6 is not optional. Stating the limit of your own method is what separates a
defensible report from an overclaim.

---

## 6. Discussion

- Comparison with published Kolkata/South-Asian PM2.5-AOD studies (typical R² 0.5–0.75;
  if you report 0.95, something is leaking)
- Why LOSO < time-split performance, and what that means operationally
- What would improve it: real PBL, geostationary AOD (GEO-KOMPSAT/INSAT-3DR hourly),
  low-cost sensor network

---

## 7. Conclusion

Three sentences: what you built, what it achieves, what it cannot do.

---

## 8. Reproducibility appendix

```
python -m pm25.cli build --mode live
python -m pm25.cli train
python -m pm25.cli explain
```

Plus: package versions, seed, hardware, runtime.

---

## Figures to produce

| # | Figure | Why |
|---|---|---|
| 1 | Study area + station map | Orientation |
| 2 | PM2.5 time series by station | Shows the winter episode |
| 3 | Diurnal and monthly cycles | Motivation for cyclical features |
| 4 | AOD vs PM2.5 scatter | Shows the core relationship *and* its noise |
| 5 | Predicted vs observed (test) | Headline accuracy |
| 6 | Time series with 80% interval | Uncertainty story |
| 7 | Model comparison bar chart by horizon | Degradation with lead time |
| 8 | LOSO per-station R² | Spatial generalisation |
| 9 | SHAP summary (beeswarm) | Drivers with direction |
| 10 | Seasonal SHAP heatmap | The attribution narrative |
| 11 | Proxy prevalence by season | Independent evidence |
| 12 | Interval width vs humidity / AOD-missing | Honest failure characterisation |

Twelve figures is a paper. For a 6-week project, 1, 5, 7, 9, 10, 11 are the minimum set.

---

## Claims you can and cannot make

| ✅ Defensible | ❌ Overclaim |
|---|---|
| "R² = 0.6x on held-out 2024 data" | "Accurately predicts PM2.5 across Kolkata" |
| "SHAP and proxies agree on winter biomass influence" | "Biomass burning causes 40% of winter PM2.5" |
| "Recall of 0.7 on >120 µg/m³ episodes" | "Reliably detects pollution episodes" |
| "LOSO R² drops to 0.4x at the unseen station" | "Generalises to unmonitored locations" |
| "Intervals cover 78% of observations at 80% nominal" | "Provides calibrated uncertainty" |
