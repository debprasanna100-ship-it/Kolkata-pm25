"""Small shared helpers: logging, IO, seeding."""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LOG_FORMAT = "%(asctime)s  %(levelname)-7s %(name)-18s %(message)s"


def get_logger(name: str = "pm25") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


log = get_logger()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    """CSV out. Kept dependency-free on purpose (no pyarrow requirement)."""
    p = Path(path)
    ensure_dir(p.parent)
    df.to_csv(p, index=False)
    return p


def read_table(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def write_json(obj: Any, path: str | Path) -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(json.dumps(obj, indent=2, default=_json_default), encoding="utf-8")
    return p


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return str(obj)


def human_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def require(condition: bool, message: str) -> None:
    """Fail fast with an actionable message instead of a stack trace deep in pandas."""
    if not condition:
        raise SystemExit(f"\n[pm25] {message}\n")
