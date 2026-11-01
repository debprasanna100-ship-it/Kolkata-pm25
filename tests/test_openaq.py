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


def test_fetch_sensor_caches_empty_months(cfg, monkeypatch):
    """A month with no data is an answer, not an error - cache it so we never
    pay for it twice."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 31, tzinfo=timezone.utc)   # exactly one 30-day chunk

    monkeypatch.setattr(openaq, "_get", lambda *a, **k: {"results": []})
    empty = openaq.fetch_sensor(None, 7, start, end, cfg=cfg)
    assert empty.empty

    cache_dir = cfg.path("raw") / "openaq_cache"
    assert len(list(cache_dir.glob("7_*.csv"))) == 1
