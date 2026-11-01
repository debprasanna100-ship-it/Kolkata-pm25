"""Tests for the OpenAQ client's rate-limit handling and chunk cache.

All network access is faked - no key, no socket.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from pm25.config import Config
from pm25.data import openaq


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = "fake body"

    def json(self):
        return self._payload


class _FakeSession:
    """Returns queued responses in order; records every request."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        return self._responses.pop(0)


@pytest.fixture
def cfg(tmp_path):
    return Config.load(root=tmp_path)


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    """Tests must not actually sleep through backoff or throttling."""
    monkeypatch.setattr(openaq.time, "sleep", lambda *_: None)
    monkeypatch.setattr(openaq, "_last_request_monotonic", 0.0)


@pytest.fixture(autouse=True)
def _reset_throttle():
    yield
    openaq._last_request_monotonic = 0.0


def _measurement_payload(n=3):
    return {
        "results": [
            {
                "period": {"datetimeFrom": {"utc": f"2024-01-01T0{i}:00:00Z"}},
                "value": 50.0 + i,
            }
            for i in range(n)
        ]
    }


# --- _get: 429 patience ------------------------------------------------------


def test_get_retries_429_then_succeeds():
    session = _FakeSession([
        _FakeResponse(429, headers={"x-ratelimit-remaining": "0"}),
        _FakeResponse(429, headers={"x-ratelimit-remaining": "0"}),
        _FakeResponse(200, _measurement_payload()),
    ])
    payload = openaq._get(session, "http://x", {})
    assert payload["results"][0]["value"] == 50.0
    assert len(session.calls) == 3


def test_get_gives_up_with_actionable_message():
    session = _FakeSession([_FakeResponse(429)] * 8)
    with pytest.raises(openaq.OpenAQError, match="2,000/hour|cached"):
        openaq._get(session, "http://x", {}, retries=3)


def test_get_raises_immediately_on_auth_error():
    session = _FakeSession([_FakeResponse(401)])
    with pytest.raises(openaq.OpenAQError, match="401"):
        openaq._get(session, "http://x", {})


def test_rate_limit_wait_honours_retry_after():
    response = _FakeResponse(429, headers={"Retry-After": "30"})
    assert 30.0 <= openaq._rate_limit_wait(response, attempt=0) <= 32.0


def test_rate_limit_wait_parses_epoch_reset():
    import time as _time

    response = _FakeResponse(429, headers={"x-ratelimit-reset": str(_time.time() + 120)})
    wait = openaq._rate_limit_wait(response, attempt=0)
    assert 100.0 < wait <= openaq._MAX_429_WAIT_S


def test_rate_limit_wait_bails_on_far_future_reset():
    import time as _time

    response = _FakeResponse(429, headers={"x-ratelimit-reset": str(_time.time() + 7200)})
    with pytest.raises(openaq.OpenAQError, match="resets in"):
        openaq._rate_limit_wait(response, attempt=0)


def test_rate_limit_wait_falls_back_to_backoff():
    assert openaq._rate_limit_wait(_FakeResponse(429), attempt=2) == 4.0


# --- fetch_sensor: chunk cache ----------------------------------------------


def test_fetch_sensor_caches_chunks_and_resumes(cfg, monkeypatch):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 3, 1, tzinfo=timezone.utc)   # two 30-day chunks

    calls = {"n": 0}

    def fake_get(session, url, params, retries=8):
        calls["n"] += 1
        return _measurement_payload()

    monkeypatch.setattr(openaq, "_get", fake_get)

    first = openaq.fetch_sensor(None, 42, start, end, cfg=cfg)
    assert len(first) == 6          # 3 rows per chunk x 2 chunks
    assert calls["n"] == 2          # one request per chunk

    cache_dir = cfg.path("raw") / "openaq_cache"
    files = sorted(cache_dir.glob("42_*.csv"))
    assert len(files) == 2

    # Second run must hit zero requests: everything comes from disk.
    second = openaq.fetch_sensor(None, 42, start, end, cfg=cfg)
    assert calls["n"] == 2
    pd.testing.assert_frame_equal(first, second)


def test_sensor_ids_keeps_all_candidates():
    """Retired and replacement sensors coexist per pollutant; dropping any
    would silently lose data."""
    location = {
        "sensors": [
            {"id": 19997, "parameter": {"id": 2, "name": "pm25"}},
            {"id": 12235887, "parameter": {"id": 2, "name": "pm25"}},
            {"id": 19994, "parameter": {"id": 1, "name": "pm10"}},
            {"id": 99, "parameter": {"id": 55, "name": "nox"}},   # not wanted
        ]
    }
    out = openaq._sensor_ids(location, ["pm25", "pm10"])
    assert out == {"pm25": [19997, 12235887], "pm10": [19994]}


def test_fetch_sensor_caches_empty_months_only_after_data(cfg, monkeypatch):
    """Gaps *inside* a sensor's reporting period are cached; months before the
    sensor starts reporting are not (the sensor may simply begin later)."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 4, 1, tzinfo=timezone.utc)   # three chunks: Jan, Feb, Mar

    def fake_get(session, url, params, retries=8):
        # Data exists in February; chunks are 30-day windows, so a chunk
        # overlaps February when it starts before Mar 1 and ends after Feb 1.
        overlaps_feb = (
            params["datetime_from"] < "2024-03-01" and params["datetime_to"] > "2024-02-01"
        )
        return _measurement_payload() if overlaps_feb else {"results": []}

    monkeypatch.setattr(openaq, "_get", fake_get)
    out = openaq.fetch_sensor(None, 7, start, end, cfg=cfg)
    assert len(out) == 3   # only February has rows

    cache_dir = cfg.path("raw") / "openaq_cache"
    cached = sorted(f.name for f in cache_dir.glob("7_*.csv"))
    # Four 30-day chunks from Jan 1 to Apr 1; Feb's data turns has_data on,
    # so the three chunks from that point on are cached, January never is.
    assert len(cached) == 3
    assert not any("_20240101_" in name for name in cached)   # January not poisoned

    # Resume: Jan re-requested (1 call), Feb+Mar from cache.
    calls = {"n": 0}

    def counting_get(session, url, params, retries=8):
        calls["n"] += 1
        return fake_get(session, url, params, retries)

    monkeypatch.setattr(openaq, "_get", counting_get)
    openaq.fetch_sensor(None, 7, start, end, cfg=cfg)
    assert calls["n"] == 1


def test_fetch_sensor_gives_up_on_dead_sensor_after_six_empty_months(cfg, monkeypatch):
    """A sensor with nothing in the first six months of the range probably
    starts later - stop early instead of a request per remaining month."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 9, 1, tzinfo=timezone.utc)   # eight chunks

    calls = {"n": 0}

    def fake_get(session, url, params, retries=8):
        calls["n"] += 1
        return {"results": []}

    monkeypatch.setattr(openaq, "_get", fake_get)
    out = openaq.fetch_sensor(None, 9, start, end, cfg=cfg)
    assert out.empty
    assert calls["n"] == 6   # early exit, not 8

    # And a dead sensor leaves no cache files to poison later runs.
    cache_dir = cfg.path("raw") / "openaq_cache"
    assert not list(cache_dir.glob("9_*.csv"))
