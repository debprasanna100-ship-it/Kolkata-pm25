"""Tests for the shared helpers in pm25.utils.

The important one: write_json must emit RFC-8259 valid JSON. Python's
json.dumps happily writes bare `NaN`/`Infinity` tokens, which are invalid
JSON and crash strict parsers — including the browser's JSON.parse that
the frontend uses to read metrics.json.
"""

from __future__ import annotations

import json
import math

import numpy as np

from pm25.utils import write_json


def test_write_json_replaces_nan_with_null(tmp_path):
    obj = {
        "far": float("nan"),
        "nested": {"inf": float("inf"), "neg_inf": float("-inf")},
        "np_nan": np.float64("nan"),
        "list": [1.0, float("nan"), 3.0],
        "ok": 1.5,
    }
    path = write_json(obj, tmp_path / "out.json")
    raw = path.read_text(encoding="utf-8")

    # No bare NaN/Infinity tokens may appear anywhere in the output.
    assert "NaN" not in raw
    assert "Infinity" not in raw

    # The file must parse with a strict JSON parser (no allow_nan escape).
    parsed = json.loads(raw)
    assert parsed["far"] is None
    assert parsed["nested"]["inf"] is None
    assert parsed["nested"]["neg_inf"] is None
    assert parsed["np_nan"] is None
    assert parsed["list"][1] is None
    assert parsed["ok"] == 1.5


def test_write_json_roundtrips_finite_values(tmp_path):
    obj = {"a": 1.25, "b": [1, 2, 3], "c": {"d": True}}
    parsed = json.loads(write_json(obj, tmp_path / "out.json").read_text(encoding="utf-8"))
    assert parsed == obj


def test_metrics_from_episode_are_json_safe():
    """Regression guard: episode_metrics produces NaN when there are no
    episodes; after sanitization it must survive a strict json.loads."""
    from pm25.models.evaluate import episode_metrics
    from pm25.utils import _sanitize_json

    m = episode_metrics(np.array([10.0, 20.0]), np.array([15.0, 25.0]))
    assert math.isnan(m["recall"])  # original metric is NaN by design
    safe = _sanitize_json(m)
    json.dumps(safe)  # would raise on bare NaN if not sanitized
    assert safe["recall"] is None
