"""Configuration loading with sensible defaults baked in.

The project must run with *no* config file at all, so `DEFAULTS` mirrors
`config.example.yaml`. A user config is deep-merged on top of it.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

# --------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "project": {"name": "kolkata-pm25", "seed": 42},
    "data": {
        "mode": "demo",
        # Verified 2026-11: Kolkata WBPCB replacement sensors started ~2025-02-18.
        # Earlier windows return nothing from OpenAQ v3.
        "start": "2025-03-01",
        "end": "2026-10-31",
        "target": "pm25",
        "stations": ["victoria_memorial", "jadavpur", "rabindra_bharati", "ballygunge"],
        "extra_pollutants": ["pm10", "no2", "so2", "co", "o3"],
    },
    "weather": {"provider": "openmeteo"},
    "satellite": {
        "provider": "gee",
        "aod_collection": "MODIS/061/MCD19A2_GRANULES",
        "aod_band": "Optical_Depth_047",
        "no2_collection": "COPERNICUS/S5P/OFFL/L3_NO2",
        "no2_band": "tropospheric_NO2_column_number_density",
        "buffer_m": 5000,
    },
    "fires": {
        "source": "VIIRS_SNPP_NRT",
        "bbox": [85.0, 20.5, 92.0, 25.5],
        "upwind_radius_deg": 3.0,
    },
    "features": {"lags": [0, 1, 3, 6, 12, 24], "rolling_windows": [6, 24], "aod_available_ahead_h": 2},
    "models": {
        "horizons": [1, 6, 24],
        "test_year": 2026,
        "quantiles": [0.1, 0.5, 0.9],
        "gbdt": {"n_estimators": 400, "learning_rate": 0.05, "max_depth": 6, "min_samples_leaf": 20},
    },
    "paths": {
        "raw": "data/raw",
        "processed": "data/processed",
        "artifacts": "artifacts",
        "figures": "artifacts/figures",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we do not depend on python-dotenv."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class Config:
    """Thin dot-path wrapper around the merged config dict."""

    def __init__(self, data: dict[str, Any], root: Path | None = None):
        self._data = data
        self.root = root or Path.cwd()

    # -- construction ------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None, root: str | Path | None = None) -> "Config":
        root_path = Path(root or Path.cwd()).resolve()
        _load_dotenv(root_path / ".env")

        merged = copy.deepcopy(DEFAULTS)
        candidate = Path(path) if path else root_path / "config.yaml"
        if candidate.exists():
            loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            merged = _deep_merge(merged, loaded)

        return cls(merged, root_path)

    # -- access ------------------------------------------------------------

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        """Override one value. This is the supported way for CLI flags to
        change the config; reaching into `_data` from outside is not."""
        node = self._data
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ValueError(f"cannot set {dotted!r}: {part!r} is not a section")
        node[parts[-1]] = value

    def __getitem__(self, dotted: str) -> Any:
        value = self.get(dotted, _MISSING)
        if value is _MISSING:
            raise KeyError(dotted)
        return value

    # -- paths -------------------------------------------------------------

    def path(self, key: str) -> Path:
        """Resolve a path from the `paths` block against the project root."""
        raw = self.get(f"paths.{key}", key)
        resolved = (self.root / str(raw)).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    @property
    def dataset_csv(self) -> Path:
        return self.path("processed") / "dataset.csv"

    @property
    def features_csv(self) -> Path:
        return self.path("processed") / "features.csv"

    @property
    def metrics_json(self) -> Path:
        return self.path("artifacts") / "metrics.json"

    @property
    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)


_MISSING = object()
