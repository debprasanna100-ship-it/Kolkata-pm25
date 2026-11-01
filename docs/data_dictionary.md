# Data dictionary

One row per station-hour. `dataset.csv` is the output of `pm25.cli build`;
`features.csv` adds the engineered columns from `features.py`.

## Identity

| Column | Type | Notes |
|---|---|---|
| `time` | datetime (UTC) | Hour start. Always UTC — never mix local time into a model with a diurnal cycle. |
| `station` | str | Key from `stations.py`, e.g. `victoria_memorial`. |
| `station_name` | str | Human readable. |
| `lat`, `lon` | float | WGS84 decimal degrees. Approximate — verify. |
| `dist_road_km` | float | Distance to nearest motorway/trunk/primary/secondary road. |

## Target and co-pollutants (µg/m³ unless noted)

| Column | Notes |
|---|---|
| `pm25` | **Target.** Hourly mean. |
| `pm10` | Coarse fraction. Used for the dust proxy only — never a model input. |
| `no2` | Traffic tracer. Proxy only. |
| `so2` | Proxy only. |
| `co` | mg/m³. Proxy only. |
| `o3` | Photochemistry tracer. Proxy only. |

Co-pollutants are excluded from the feature matrix on purpose: they are measured at the
same station, so using them to predict PM2.5 is circular.

## Meteorology

| Column | Unit | Notes |
|---|---|---|
| `temp` | °C | 2 m air temperature |
| `rh` | % | Relative humidity (from dewpoint for ERA5) |
| `wind_u` | m/s | Eastward component |
| `wind_v` | m/s | Northward component |
| `wind_speed` | m/s | `hypot(u, v)` |
| `wind_dir` | degrees | Meteorological: the direction the wind blows **FROM**, clockwise from north |
| `precip` | mm/h | Total precipitation |
| `pbl` | m | Boundary layer height. **NaN if provider is Open-Meteo.** |
| `cloud` | 0–1 | Total cloud cover |

### Wind direction convention
`wind_dir = (270 − atan2(v, u)) mod 360`.

- u = +1, v = 0 → wind blows east → comes from the west → 270°. ✓
- u = 0, v = −1 → wind blows south → comes from the north → 0°. ✓

Getting this backwards silently inverts the fire-transport feature and makes biomass
burning look like a negative predictor.

## Satellite

| Column | Unit | Notes |
|---|---|---|
| `aod` | dimensionless | MAIAC 550 nm AOD, 5 km buffer mean. NaN on cloudy days. |
| `aod_lag24` | dimensionless | Previous day's AOD — the only satellite feature usable at +24 h. |
| `aod_missing` | 0/1 | 1 when `aod` is NaN. Keep this: the model learns to distrust itself. |
| `no2_sat` | mol/m² | TROPOMI tropospheric NO2 column. |

## Fires

| Column | Unit | Notes |
|---|---|---|
| `fire_count` | count | Detections in the bbox for that day (confidence ≥ 60). |
| `fire_upwind` | count | `fire_count × max(0, cos(wind_from − bearing_to_fire_centroid))`. |
| `fire_upwind_lag24` | count | Previous day, for transported events arriving overnight. |

## Engineered (in `features.py`)

| Column | Definition |
|---|---|
| `hour`, `month`, `dow`, `doy` | Raw calendar fields (kept for plotting, excluded from features) |
| `hour_sin`, `hour_cos` | `sin/cos(2π·hour/24)` |
| `month_sin`, `month_cos` | `sin/cos(2π·month/12)` |
| `is_weekend` | dayofweek ≥ 5 |
| `wind_dir_sin`, `wind_dir_cos` | Cyclical wind direction |
| `pbl_inv` | `1/(pbl + 100)` — hyperbolic trapping term |
| `ventilation` | `wind_speed × pbl` — ventilation coefficient |
| `pm25_lag{k}` | `pm25(t − k)` per station |
| `pm25_diff{k}` | `pm25(t) − pm25(t − k)` |
| `pm25_roll{w}` | Mean of the previous `w` hours, excluding the current hour |
| `pm25_rollstd{w}` | Standard deviation over the same window |
| `y` | `pm25(t + horizon)` — the modelling target |
| `proxy` | Rule-based source label (`biomass` / `dust` / `traffic` / `secondary` / `background`) |

## Artifacts

| File | Contents |
|---|---|
| `artifacts/metrics.json` | All model metrics per horizon, including LOSO and interval coverage |
| `artifacts/predictions.csv` | Test-set predictions at h = 0 with q10/q90 and diagnostics |
| `artifacts/importance_h0.csv` | Full-model feature importance |
| `artifacts/importance_attrib.csv` | Attribution-model importance (no lags) |
| `artifacts/seasonal_importance.csv` | Per-season importance (SHAP, or within-season permutation when shap is absent) |
| `artifacts/proxy_prevalence.csv` | Share of hours per proxy per season |
| `artifacts/proxy_agreement.csv` | Proxy × season × SHAP agreement verdict |
| `artifacts/attribution_summary.json` | Top drivers, overall proxy shares, caveat text |
| `artifacts/models/gbdt_h{h}.joblib` | Trained quantile models per horizon |
| `artifacts/models/attrib_h0.joblib` | Attribution model (no autoregressive features) |
