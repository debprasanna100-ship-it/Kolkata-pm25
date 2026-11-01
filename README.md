# Kolkata PM2.5 — Hourly Estimation & Source Attribution

Estimate hourly PM2.5 at Kolkata monitoring stations from satellite AOD, reanalysis
meteorology, fire transport and time features — then explain *why* the model says what
it says, and check those explanations against independent source proxies.

Built to run **immediately with no API keys**, then upgrade to real data in one flag.

```bash
pip install -r requirements.txt
python -m pm25.cli all          # build -> train -> explain  (~2 min)
python -m pm25.cli app          # dashboard at localhost:8501
make test                       # unit tests + dashboard smoke test
```

That runs on a deterministic synthetic dataset. Same schema, same causal structure, no
network. When you have keys: `python -m pm25.cli build --mode live`.

---

## Why the structure looks like this

**Satellite AOD is not hourly.** MODIS/MAIAC gives one retrieval per day at 1 km, TROPOMI
gives one overpass around 13:30 local. So "hourly PM2.5" means: *daily* satellite features
broadcast onto every hour, with hourly variation coming from meteorology, time-of-day and
lagged PM2.5. Anything else is a methodological error, and it is the first thing a reviewer
will catch.

**AOD is missing precisely when you need it.** Cloud cover removes the retrieval, and cloudy
days are not a random sample. The pipeline therefore carries an `aod_missing` flag and the
Robustness tab quantifies the accuracy hit rather than hiding it.

**No co-pollutant features.** PM10, NO2, SO2, CO and O3 are in the dataset but never enter
the model. They are measured at the same station and are correlated with PM2.5 by
construction — including them inflates R² with no operational value. They are used only for
the source proxies, which is exactly what they are good for.

**No random train/test split.** Consecutive hours are autocorrelated. The pipeline uses a
time split (train on earlier years, test on the latest) plus leave-one-station-out. Random
splits produce R² that collapses the moment you try it on next month's data.

---

## Three layers

| Layer | Status | What it gives you |
|---|---|---|
| **Core** | done | Hourly PM2.5 + NO2 prediction from AOD, weather, fires, time |
| **Extension** | done | 1 h / 6 h / 24 h forecasts, four model families compared |
| **Stretch** | done | SHAP attribution + rule-based source proxies + Streamlit dashboard |

Skipped on purpose: PMF, low-cost sensor calibration, street-level mapping. All three need
speciated filter data or a sensor network that isn't publicly available for Kolkata.

---

## Pipeline

```
data/                    features/               models/                explain/
├── openaq.py    ──┐     ├── lags 0/1/3/6/12/24  ├── persistence       ├── SHAP
├── weather.py     │     ├── rolling 6/24        ├── climatology       ├── permutation
├── satellite.py   ├──►  ├── cyclical hour/month ├── ridge             └── proxies
├── fires.py       │     ├── upwind fire        ├── quantile GBDT
├── roads.py       │     └── leakage guards     └── LSTM / CNN-LSTM
└── synthetic.py ──┘
```

`build` → `data/processed/dataset.csv`
`train` → `artifacts/metrics.json`, `artifacts/predictions.csv`, `artifacts/models/*.joblib`
`explain` → `artifacts/seasonal_importance.csv`, `artifacts/proxy_agreement.csv`

---

## What the demo run actually produces

Real output from `python -m pm25.cli all` on the synthetic dataset. **These are pipeline
checks, not findings** — but the *shape* is what you should expect from real data, and it
is the shape your report has to explain.

Time split: train 2025 (Mar–Dec), test 2026 (Jan–Oct) — the verified live coverage
window, also the demo default. n ≈ 27,800 test hours per horizon. Episode recall is
computed on the winter slice (Nov–Feb), where the threshold crossings actually cluster.

| Horizon | Model | RMSE | MAE | R² | Episode recall | PI80 |
|---|---|---|---|---|---|---|
| **+1 h** | persistence | 14.53 | 10.24 | 0.871 | 0.76 | — |
| | climatology | 29.92 | 19.34 | 0.452 | 0.00 | — |
| | ridge | 13.54 | 9.53 | 0.888 | 0.79 | — |
| | **GBDT** | **12.50** | **8.62** | **0.904** | 0.77 | 0.737 |
| **+6 h** | persistence | 29.46 | 21.77 | 0.468 | 0.49 | — |
| | **GBDT** | **18.07** | **12.34** | **0.800** | 0.44 | 0.736 |
| **+24 h** | persistence | 24.50 | 16.98 | 0.632 | 0.54 | — |
| | ridge | 19.28 | 13.62 | 0.772 | 0.51 | — |
| | **GBDT** | **19.47** | **13.27** | **0.768** | 0.32 | 0.729 |

Four things worth reading off this table:

1. **Persistence collapses from R² 0.87 to 0.47 by +6 h.** That is the honest reason a
   model exists at all. At +1 h it is a serious competitor.
2. **PI80 coverage is 0.73–0.74 against a nominal 0.80.** The intervals are slightly
   overconfident. Reporting that instead of hiding it is the point.
3. **Episode recall falls with lead time** (0.77 → 0.44 → 0.32) while overall R² falls
   much less — and by +24 h persistence actually catches *more* episodes (0.54) than the
   GBDT (0.32). A model can look fine on RMSE and still lose the smog days; that trade
   is the thing to report, not hide.
4. **Climatology is terrible here (R² ≈ 0.45) because the window starts in March.**
   Train-2025 never sees January or February, so its station × month × hour table has no
   winter entries and falls back to the global mean exactly when it matters. The GBDT
   interpolates through `month_sin/cos` and does not care. Any window that does not
   start on 1 January has this artifact — check for it before quoting climatology.

### Leave-one-station-out

| Horizon | Mean LOSO R² | Mean LOSO RMSE |
|---|---|---|
| +1 h | 0.903 | 12.35 |
| +6 h | 0.798 | 17.83 |
| +24 h | 0.763 | 19.34 |

Per-station spread is small in the demo (0.756–0.906) **because the synthetic stations share
one generating function**. On live data expect LOSO to drop meaningfully below the time-split
number — that gap *is* the spatial-generalisation story, and it is the number to quote.

### Attribution

Top model drivers: `month_cos`, `aod`, `fire_upwind`, `ventilation`, `hour_sin`, `pbl_inv`.

9 of 20 season × proxy pairs are supported by the model's own importances:

| Season | Proxy | Share of hours | Supported by model |
|---|---|---|---|
| post-monsoon | biomass | 48% | ✅ `fire_upwind` in top-5 |
| post-monsoon | background | 34% | ✅ `pbl` |
| pre-monsoon | dust | 15% | ✅ `ventilation` |
| pre-monsoon | traffic | 21% | ✅ `hour_sin` |
| monsoon | background | 72% | ✅ `ventilation` |
| winter | traffic | 28% | ✅ `hour_sin`, `hour_cos` |

The unsupported pairs matter as much as the supported ones — `secondary` essentially never
fires in this dataset (≤5% of hours everywhere), and winter dust (20% of hours) finds none of
its expected drivers in the model's winter top-5, which leans on humidity and ventilation
instead. The model does not pretend otherwise, and neither should the report.

---

## Models

| Model | Role |
|---|---|
| Persistence | "tomorrow = today". The bar everything must clear. |
| Climatology | station × month × hour mean. Beats persistence in stable seasons. |
| Ridge | linear baseline on the identical feature matrix, so the GBDT gap is fair. |
| **Quantile GBDT** | main model. Three models at q10/q50/q90 give an 80% interval. |
| LSTM / CNN-LSTM | tests whether temporal structure beyond engineered lags helps. |

LightGBM is used when installed, otherwise scikit-learn's `HistGradientBoostingRegressor`
— which also supports `loss="quantile"`, so prediction intervals work either way.

---

## Uncertainty, and why it is cheap here

`quantile_fix` trains three models instead of one and sorts them per row to remove quantile
crossing. The output is an 80% prediction interval and a `pi80_coverage` metric — the
fraction of observed values that actually fall inside. A calibrated model lands near 0.80.
That is a one-number answer to "how much should I trust this?" and it costs one extra fit.

---

## Source attribution

The honest ceiling without speciation:

1. **SHAP** on an attribution model that excludes autoregressive PM2.5 lags. Without that
   exclusion, lag-1 dominates everything and you learn nothing about sources.
2. **Rule-based proxies** over co-pollutants and meteorology:
   - *biomass* — upwind FIRMS detections in the top 15% for that station
   - *dust* — PM10/PM2.5 ≥ 2.6, RH < 62%, wind ≥ 2.5 m/s
   - *traffic* — rush hour + weekday + near a major road + high NO2
   - *secondary* — RH ≥ 70% + elevated O3 + low wind
3. **Agreement check** — for each season, does a proxy's expected drivers appear in the
   model's top-5 SHAP features? This is the part that makes the project convincing: two
   independent methods, built from different data, telling the same seasonal story.

It is a consistency argument, not proof. Say so in the report — it reads as rigour, not
weakness.

---

## Validation protocol

| Split | Purpose |
|---|---|
| Time split (`test_year`) | Generalisation forward in time |
| Leave-one-station-out | Generalisation to an unmonitored site |
| Winter episode metrics | Recall + false alarm ratio above 120 µg/m³ |
| PI80 coverage | Interval calibration |
| AOD-missing slice | Honest accuracy when the satellite is blind |

Metrics: RMSE, MAE, R², bias, MAPE, plus episode recall/FAR.

---

## Going live

```bash
cp config.example.yaml config.yaml
cp .env.example .env
# fill OPENAQ_API_KEY, GEE_PROJECT, FIRMS_MAP_KEY (all free)
# optionally: earthengine authenticate ; ~/.cdsapirc for ERA5
python -m pm25.cli build --mode live
```

**OpenAQ rate limits (free tier): 60 requests/min, 2,000/hour.** The client throttles
itself below the minute cap (a ~20-month build takes ~10 minutes) and backs off using
`x-ratelimit-reset` when the hour cap bites. Every fetched 30-day chunk is cached under
`data/raw/openaq_cache/` — if a run dies or gives up, just rerun the same command and
it resumes from disk instead of re-paying the quota.

**Live coverage reality (verified 2026-11):** CPCB/WBPCB stations on OpenAQ often carry
*several* sensors per pollutant — retired instruments and their replacements. The old
Kolkata sensors stopped reporting years ago and the replacement generation started
**~2025-02-18** (Jadavpur, Ballygunge); Rabindra Bharati's PM2.5 has no recent data at
all. Requesting 2023–2024 therefore returns nothing — the client tries every sensor
listed for a pollutant and skips dead ones, and the config defaults already use the
verified window, so the bare commands work:

```bash
python -m pm25.cli build --mode live    # 2025-03-01 .. 2026-10-31 (default)
python -m pm25.cli train                # test_year 2026 (default)
python -m pm25.cli explain
```

| Source | Provides | Cost |
|---|---|---|
| OpenAQ v3 | CPCB station PM2.5, PM10, NO2, SO2, CO, O3 | free key |
| Open-Meteo | temp, RH, wind, rain, cloud (ERA5 underneath) | free, no key |
| ERA5 via CDS | + boundary layer height — **worth the extra step** | free key |
| Google Earth Engine | MAIAC AOD, TROPOMI NO2 | free, needs auth |
| NASA FIRMS | fire detections | free MAP_KEY |
| Overpass / OSM | road distance per station | free |

Optional packages are commented in `requirements.txt`. Every adapter raises a clear,
actionable error instead of a stack trace if its key or package is missing.

---

## Layout

```
kolkata-pm25/
├── config.example.yaml
├── requirements.txt
├── src/pm25/
│   ├── cli.py            entry point
│   ├── config.py         dot-path config with baked-in defaults
│   ├── stations.py       station registry (VERIFY the coordinates)
│   ├── features.py       engineering + leakage guards
│   ├── data/             adapters + demo generator
│   ├── models/           baselines, gbdt, deep, evaluate, train
│   ├── explain/          importance, proxies, attribution
│   └── app/dashboard.py  Streamlit, 6 tabs
├── tests/                pytest (leakage guards, metrics, proxies) + dashboard smoke test
└── docs/
    ├── methodology.md
    ├── data_dictionary.md
    └── report_outline.md
```

---

## Known limitations

1. AOD is daily, not hourly — hourly variation is meteorology + lags.
2. AOD is missing when cloudy, and that missingness is informative.
3. Source proxies are heuristics. No PMF, no speciation, no proof.
4. Station coordinates in `stations.py` are approximate — verify before publishing.
5. Ground truth is a monitor, not personal exposure.
6. The demo dataset is synthetic. Any number produced in demo mode is a pipeline check,
   never a finding.
