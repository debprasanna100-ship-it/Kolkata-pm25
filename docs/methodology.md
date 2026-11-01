# Methodology

The document you would defend in a viva. Every choice has a reason and a known weakness.

---

## 1. Problem framing

**Target.** Hourly mean PM2.5 (µg/m³) at a fixed ground monitor.

**Why it is hard.** The satellite sees a column, the monitor sees the surface. Converting
one to the other is the entire problem: aerosol optical depth (AOD) is a vertically
integrated extinction measurement, while PM2.5 is a dry surface mass concentration. The
relationship depends on boundary layer height, humidity (hygroscopic growth), aerosol type
and vertical distribution. A machine learning model learns that mapping empirically rather
than physically, which is why it needs meteorology as input.

**What "hourly" honestly means.** Satellite retrievals are not hourly:

| Product | Temporal | Spatial |
|---|---|---|
| MODIS MAIAC (MCD19A2) | 1/day per overpass | 1 km |
| VIIRS AOD | 1/day per overpass | 6 km |
| TROPOMI NO2 | ~13:30 local, 1/day | 5.5 × 3.5 km |
| ERA5 | hourly | ~31 km |
| CPCB station | hourly | point |

So the model is: **daily satellite context + hourly meteorology + hourly autoregression**.
Reporting it as an "hourly satellite product" would be wrong.

---

## 2. Data

### Ground truth
CPCB CAAQMS via OpenAQ v3. Known issues: gaps during instrument downtime, occasional
stuck-at-zero sensors, unit changes. Mitigation: collapse duplicates to hourly means,
drop non-physical values (PM2.5 > 1000, negative), and require at least 18 valid hours per
day for a day to enter the daily aggregates used in evaluation.

### Meteorology
ERA5 single levels: 2 m temperature, 2 m dewpoint (→ RH via Magnus), 10 m u/v wind,
boundary layer height, total precipitation, total cloud cover.

**Boundary layer height is the single most important meteorological variable** for surface
PM2.5. It is also the one Open-Meteo does not expose, which is why the ERA5 path exists.

### Satellite
MAIAC AOD with QA masking: keep pixels where `AOD_QA & 0b111 == 0` (clear), scale by 0.001,
mean over a 5 km buffer. TROPOMI NO2 as an additional column.

The 5 km buffer is a compromise: larger buffers smooth over local gradients, smaller buffers
hit too many missing pixels.

### Fires
FIRMS VIIRS detections, filtered to confidence ≥ 60 to remove hot roofs and industrial
flares. Converted to an **upwind** signal:

```
alignment = max(0, cos(wind_from_direction − bearing_to_fire_centroid))
fire_upwind = daily_fire_count × alignment
```

Without the alignment term the feature is nearly useless — 200 fires 600 km downwind carry
no information about the air over your station.

### Roads
Nearest motorway/trunk/primary/secondary way from OSM, via Overpass. Static per station;
enters as `dist_road_km`.

---

## 3. Feature engineering

| Group | Features | Rationale |
|---|---|---|
| Time | `hour_sin/cos`, `month_sin/cos`, `dow`, `is_weekend` | Cyclical encoding; a raw hour integer would make 23 and 0 far apart |
| Meteorology | temp, RH, wind speed, wind dir sin/cos, precip, PBL, `pbl_inv`, `ventilation` | Dilution and trapping |
| Satellite | `aod`, `aod_lag24`, `aod_missing` | Column → surface proxy, plus a missingness flag |
| Fires | `fire_count`, `fire_upwind`, `fire_upwind_lag24` | Transport events |
| Autoregressive | `pm25_lag{1,3,6,12,24}`, rolling mean/std 6/24, diffs | Persistence |
| Static | `dist_road_km`, lat, lon | Traffic context, spatial interpolation |

**`ventilation = wind_speed × PBL`** is the standard ventilation coefficient — the single
most physically meaningful interaction in the set.

**`pbl_inv = 1 / (PBL + 100)`** because the relationship is hyperbolic, not linear: the
difference between a 100 m and 300 m boundary layer is far more consequential than between
1500 m and 1700 m.

### Leakage guards

- Lags use `shift(+k)` only, grouped by station.
- Rolling windows use `shift(1)` before rolling, so the current hour never enters its own
  feature.
- For horizons beyond `features.aod_available_ahead_h` (default 2 h), the `aod` column is
  **dropped** and only `aod_lag24` survives. Same-day AOD at +24 h is the future.
- Co-pollutants never enter the feature matrix.

---

## 4. Models

**Persistence** — `ŷ(t+h) = y(t)`. Brutal to beat at h = 1, useless at h = 24.

**Climatology** — station × month × hour mean from training data only.

**Ridge** — same features, standardised. Establishes how much of the signal is linear.

**Quantile GBDT** — three models (q10, q50, q90). LightGBM if available, otherwise
`HistGradientBoostingRegressor(loss="quantile")`. Hyperparameters are modest on purpose:
400 trees, depth 6, lr 0.05, L2 = 1.0. On 50k rows with strong features, deeper models
overfit the winter episodes and lose LOSO performance.

**LSTM / CNN-LSTM** — 24-hour windows, standardised per feature, Huber loss, early stopping
on a time-ordered validation tail. Included to test whether raw temporal structure beats
engineered lags. Usually it does not, and saying so with evidence is the point.

---

## 5. Validation

### Time split
Train on years `< test_year`, test on `≥ test_year`. Answers forward generalisation.
Never random: hourly autocorrelation (lag-1 ≈ 0.85) makes random splits leak.

### Leave-one-station-out
Train on 3 stations, test on the 4th, for every station. Answers spatial generalisation.
The model must rely on lat/lon and road distance rather than a memorised station offset —
which is why the station id is deliberately not a feature.

### Episode metrics
Computed on the **winter slice (Nov–Feb)** — the season the threshold crossings actually
cluster in — not on the full test year, where ordinary days would dominate the counts.
For observations above 120 µg/m³ (CPCB "Poor"):

- **Recall** = TP / (TP + FN) — of the bad days, how many did we flag?
- **FAR** = FP / (TP + FP) — of our warnings, how many were false?

A model with good overall RMSE can have terrible recall on episodes, because episodes are
rare and the loss is dominated by ordinary days. Report both.

### Interval calibration
`pi80_coverage` should be ≈ 0.80. Above 0.90 the intervals are uselessly wide; below 0.70
they are overconfident.

### Missing-satellite slice
Stratify test error by `aod_missing`. This is the number most papers omit and the one a
reviewer will ask for.

---

## 6. Attribution

### Why not PMF
Positive Matrix Factorization needs a speciated concentration matrix: ions (SO4²⁻, NO3⁻,
NH4⁺), metals, OC/EC. That requires filter sampling with lab analysis. No public hourly
dataset of this kind exists for Kolkata. Anything claiming otherwise is either using
simulated data or a much coarser source.

### What we do instead
1. **Attribution model** — same features minus autoregressive lags. Lag-1 explains most of
   the variance and would bury every source signal under "yesterday was also polluted".
2. **SHAP** on that model, aggregated by season.
3. **Rule-based proxies** from co-pollutants and meteorology.
4. **Agreement test** — does each proxy's expected driver set intersect the model's top-5
   features in the season where that proxy dominates?

### How to read the result
A supported pair means two independent constructions agree. That is evidence of
consistency, not proof of mechanism. The write-up must say this plainly.

### Failure modes to watch
- If `fire_upwind` never appears in top features, the FIRMS bbox or the alignment logic is
  wrong, or the study period had no transport events.
- If `pbl` is missing (Open-Meteo path), winter attribution collapses toward humidity — a
  classic symptom of a missing boundary layer variable.
- If `hour_sin` dominates everything, the model is fitting the diurnal traffic cycle and the
  meteorological features are too noisy to compete.

---

## 7. Reproducibility

- Single seed in `config.yaml`, applied to numpy/random.
- Deterministic synthetic generator (`data/synthetic.py`).
- All artefacts written to disk; the dashboard reads only from disk.
- `python -m pm25.cli all` reproduces everything from scratch.
