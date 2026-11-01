"""OpenAQ v3 client for CPCB CAAQMS data.

OpenAQ mirrors the CPCB feed, which is the only practical way to get Kolkata
station data programmatically - the CPCB portal itself has no open API and
blocks scripted access. If you need the official numbers, download the CSV
from cpcbccr.com by hand and use `load_cpcb_csv()`.

Requires OPENAQ_API_KEY (free: https://explore.openaq.org/register).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from ..stations import Station, get_stations
from ..utils import ensure_dir, get_logger

log = get_logger("pm25.openaq")

BASE = "https://api.openaq.org/v3"
# Pollutant names this pipeline understands. Matching is done by NAME, not id:
# v2 and v3 use different numeric parameter ids (no2 is 7 in v2, 5 in v3), and
# the same name can even carry two ids within one v3 location payload.
PARAMETER_NAMES = {"pm25", "pm10", "no2", "so2", "co", "o3"}


class OpenAQError(RuntimeError):
    pass


def _session() -> requests.Session:
    key = os.environ.get("OPENAQ_API_KEY", "").strip()
    if not key:
        raise OpenAQError(
            "OPENAQ_API_KEY is not set. Get a free key at https://explore.openaq.org/register "
            "and put it in .env, or run with --mode demo."
        )
    session = requests.Session()
    session.headers.update({"X-API-Key": key, "Accept": "application/json"})
    return session


def _get(session: requests.Session, url: str, params: dict, retries: int = 8) -> dict:
    """GET with pacing and 429 patience.

    OpenAQ v3 free tier: 60 requests/min and 2,000 requests/hour. The throttle
    below keeps us under the minute cap by construction; the backoff handles
    the moment the hour cap bites. `x-ratelimit-reset` tells us when the
    window restarts - honour it instead of hammering (repeated 429s can earn
    a temporary ban per the OpenAQ docs).
    """
    last_status = "unknown"
    for attempt in range(retries):
        _throttle()
        response = session.get(url, params=params, timeout=60)
        last_status = f"HTTP {response.status_code}"
        if response.status_code == 200:
            return response.json()
        if response.status_code >= 500:
            # Transient server errors happen on the measurements endpoint;
            # back off like a rate limit. A sensor that keeps 500ing is
            # handled by the caller, which moves on to the next candidate.
            wait = min(2.0 ** attempt, 30.0)
            log.warning("HTTP %d from %s, retrying in %.0fs", response.status_code, url, wait)
            time.sleep(wait)
            continue
        if response.status_code == 429:
            wait = _rate_limit_wait(response, attempt)
            log.warning(
                "rate limited (x-ratelimit-remaining=%s), sleeping %.0fs",
                response.headers.get("x-ratelimit-remaining", "?"), wait,
            )
            time.sleep(wait)
            continue
        raise OpenAQError(f"{response.status_code} for {url}: {response.text[:300]}")
    raise OpenAQError(
        f"gave up on {url} after {retries} attempts (last: {last_status}). "
        "OpenAQ free tier allows 60 requests/min and 2,000/hour - the hour window is "
        "probably exhausted. Wait a few minutes and rerun: fetched chunks are cached "
        "under data/raw/openaq_cache/ and the run resumes where it stopped."
    )


# ---------------------------------------------------------------------------
# Rate-limit helpers
# ---------------------------------------------------------------------------

_MIN_REQUEST_INTERVAL = 1.05      # seconds -> ~57 requests/min, under the 60 cap
_MAX_429_WAIT_S = 900.0           # never sleep more than 15 min on one 429
_last_request_monotonic = 0.0


def _throttle() -> None:
    """Sleep just enough to keep a minimum interval between requests."""
    global _last_request_monotonic
    now = time.monotonic()
    wait = _last_request_monotonic + _MIN_REQUEST_INTERVAL - now
    if wait > 0:
        time.sleep(wait)
    _last_request_monotonic = time.monotonic()


def _rate_limit_wait(response: requests.Response, attempt: int) -> float:
    """Seconds to sleep on a 429: honour Retry-After / x-ratelimit-reset when
    they carry usable information, otherwise exponential backoff."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after) + 1.0, _MAX_429_WAIT_S)
        except ValueError:
            pass

    reset = response.headers.get("x-ratelimit-reset")
    if reset:
        try:
            value = float(reset)
            # Epoch timestamp vs seconds-until-reset: distinguish by magnitude.
            seconds = value - time.time() if value > 1e9 else value
            if seconds > _MAX_429_WAIT_S:
                raise OpenAQError(
                    f"OpenAQ hourly quota exhausted; resets in ~{seconds / 60:.0f} min. "
                    "Wait and rerun - fetched chunks are cached and the run resumes."
                )
            if seconds > 0:
                return seconds + 1.0
        except ValueError:
            pass

    return min(2.0 ** attempt, 60.0)


def find_locations(session, station: Station, radius_m: int = 25000) -> list[dict]:
    payload = _get(
        session,
        f"{BASE}/locations",
        {"coordinates": f"{station.lat},{station.lon}", "radius": radius_m, "limit": 100},
    )
    results = payload.get("results", [])
    hint = station.openaq_hint
    matched = [r for r in results if hint in str(r.get("name", "")).lower()]
    return matched or results[:3]


def _sensor_ids(location: dict, parameters: list[str]) -> dict[str, list[int]]:
    """All sensor ids per parameter name.

    Locations usually carry several sensors for the same pollutant: retired
    instruments and their replacements, kept as separate entries. Keeping only
    one id per name would silently pick whichever appeared last in the list -
    which is exactly how a sensor that died in 2019 can shadow a live one.
    Matching is by name; numeric parameter ids differ across API versions and
    even within one location payload.
    """
    wanted = {p for p in parameters if p in PARAMETER_NAMES}
    out: dict[str, list[int]] = {}
    for sensor in location.get("sensors", []) or []:
        parameter = sensor.get("parameter") or {}
        name = parameter.get("name")
        if name in wanted:
            out.setdefault(name, []).append(sensor.get("id"))
    return out


def fetch_sensor(session, sensor_id: int, start: datetime, end: datetime,
                 cfg=None) -> pd.DataFrame:
    """Hourly series for one sensor, paginated.

    Every fetched 30-day chunk is cached under data/raw/openaq_cache/. A run
    that dies (rate limit, network, Ctrl-C) resumes from disk on the next
    attempt instead of re-paying the API quota - with the free tier's
    2,000 requests/hour cap, that is the difference between finishing and
    never finishing.

    Two guards against the instrument-replacement reality of CPCB feeds:
      * a sensor with nothing in the first six months of the requested range
        almost certainly starts later - stop early instead of burning a
        request on every remaining month;
      * empty chunks are cached only once the sensor has produced data, so a
        dead sensor can never poison the cache with header-only files.
    """
    cache_dir = None
    if cfg is not None:
        cache_dir = ensure_dir(cfg.path("raw") / "openaq_cache")

    parts: list[pd.DataFrame] = []
    cursor = start
    has_data = False
    empty_leading = 0
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=30), end)
        cache_file = None
        if cache_dir is not None:
            cache_file = cache_dir / f"{sensor_id}_{cursor:%Y%m%d}_{chunk_end:%Y%m%d}.csv"

        if cache_file is not None and cache_file.exists():
            chunk_df = pd.read_csv(cache_file)
        else:
            rows: list[dict] = []
            page = 1
            while True:
                payload = _get(
                    session,
                    f"{BASE}/sensors/{sensor_id}/measurements",
                    {
                        "datetime_from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "datetime_to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "limit": 1000,
                        "page": page,
                    },
                )
                results = payload.get("results", [])
                if not results:
                    break
                for item in results:
                    period = item.get("period") or {}
                    stamp = (period.get("datetimeFrom") or {}).get("utc")
                    rows.append({"time": stamp, "value": item.get("value")})
                if len(results) < 1000:
                    break
                page += 1
                if page > 60:
                    break
            chunk_df = pd.DataFrame(rows, columns=["time", "value"])
            # Cache empties only after we have seen data from this sensor:
            # "no data anywhere in range" must stay cache-free, because the
            # sensor may simply start later than the requested window.
            if cache_file is not None and (has_data or not chunk_df.empty):
                chunk_df.to_csv(cache_file, index=False)

        if chunk_df["time"].notna().any():
            has_data = True
            empty_leading = 0
        elif not has_data:
            empty_leading += 1
            if empty_leading >= 6:
                log.warning(
                    "sensor %s: no data in the first six months of %s..%s - "
                    "it probably starts later; skipping the remaining months",
                    sensor_id, start.date(), end.date(),
                )
                break

        parts.append(chunk_df)
        cursor = chunk_end

    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=["time", "value"])
    # Empty parts are dropped, not just because they carry nothing: they are
    # read back with object columns, and pandas 3's concat lets an empty
    # frame's dtype poison the whole column (float64 -> object), which then
    # silently falls out of build_live's select_dtypes("number") collapse.
    return pd.concat(parts, ignore_index=True)


def fetch(cfg) -> pd.DataFrame:
    """Ground truth for every configured station."""
    session = _session()
    station_keys = cfg.get("data.stations")
    parameters = ["pm25"] + [p for p in cfg.get("data.extra_pollutants", []) if p in PARAMETER_NAMES]
    start = pd.Timestamp(cfg.get("data.start")).to_pydatetime()
    end = pd.Timestamp(cfg.get("data.end")).to_pydatetime()

    frames = []
    for station in get_stations(station_keys):
        locations = find_locations(session, station)
        if not locations:
            log.warning("no OpenAQ location near %s", station.key)
            continue

        location = locations[0]
        log.info("%s -> OpenAQ location %s (%s)", station.key, location.get("id"), location.get("name"))

        sensors = _sensor_ids(location, parameters)
        if not sensors:
            log.warning("no matching sensors at %s", location.get("name"))
            continue

        merged: pd.DataFrame | None = None
        for name, candidates in sensors.items():
            # Try every sensor listed for this pollutant until one has data in
            # the requested window - retired instruments and their replacements
            # coexist in the location payload.
            series = None
            for sensor_id in candidates:
                try:
                    candidate = fetch_sensor(session, sensor_id, start, end, cfg=cfg)
                except OpenAQError as exc:
                    # A sensor whose endpoint consistently 500s should cost its
                    # retries, not the whole build.
                    log.warning("%s: %s sensor %s failed (%s) - trying next candidate",
                                station.key, name, sensor_id, exc)
                    continue
                if not candidate["time"].dropna().empty:
                    series = candidate
                    log.info("%s: %s <- sensor %s", station.key, name, sensor_id)
                    break
            if series is None:
                log.warning(
                    "%s: no %s data from any of %d sensor(s) in %s..%s - "
                    "the instrument may not report in this window",
                    station.key, name, len(candidates), start.date(), end.date(),
                )
                continue
            series["time"] = pd.to_datetime(series["time"], utc=True, errors="coerce")
            series = series.dropna(subset=["time"])
            # CPCB reports hourly means; collapse duplicates defensively.
            series = series.groupby("time", as_index=False)["value"].mean()
            series = series.rename(columns={"value": name})
            merged = series if merged is None else merged.merge(series, on="time", how="outer")

        if merged is None or "pm25" not in merged:
            log.warning("%s: no usable PM2.5 in this window - skipping station", station.key)
            continue

        merged["station"] = station.key
        merged["station_name"] = station.name
        merged["lat"] = station.lat
        merged["lon"] = station.lon
        frames.append(merged)
        time.sleep(1.0)

    if not frames:
        raise OpenAQError(
            "No station data retrieved for "
            f"{start.date()}..{end.date()}. Likely causes: (1) the requested window "
            "predates the stations' reporting - most Kolkata WBPCB sites' old sensors "
            "stopped years ago and replacements started ~2025-02-18, so try "
            "--start 2025-03-01 --end 2026-10-31; (2) a wrong API key; (3) an "
            "exhausted rate-limit window (wait a few minutes - fetched chunks are "
            "cached and the run resumes)."
        )

    out = pd.concat(frames, ignore_index=True).sort_values(["station", "time"])
    # The v3 CPCB feed reports quarter-hourly, but this pipeline is hourly.
    # Floor to the hour here; build_live's groupby then collapses the sub-hour
    # rows into their hourly mean. Without this, only the :00 rows match the
    # hourly weather join and the rest lose their meteorology.
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce").dt.floor("h")
    out = out.dropna(subset=["time"])
    # Pollutant columns must be numeric no matter what the feed did; an object
    # column would silently drop out of build_live's select_dtypes collapse.
    for col in out.columns:
        if col not in ("time", "station", "station_name"):
            out[col] = pd.to_numeric(out[col], errors="coerce")
    log.info("OpenAQ: %d rows across %d stations", len(out), out["station"].nunique())
    return out.reset_index(drop=True)


def load_cpcb_csv(path: str, station_key: str, station_name: str, lat: float, lon: float) -> pd.DataFrame:
    """Adapter for a manually downloaded CPCB CSV export.

    CPCB exports vary; this expects at least a timestamp column and a PM2.5
    column. Edit the rename map to match your file.
    """
    raw = pd.read_csv(path)
    rename = {}
    for col in raw.columns:
        low = col.lower()
        if "pm2.5" in low or "pm25" in low:
            rename[col] = "pm25"
        elif "pm10" in low:
            rename[col] = "pm10"
        elif "no2" in low:
            rename[col] = "no2"
        elif "timestamp" in low or "date" in low:
            rename[col] = "time"
    raw = raw.rename(columns=rename)
    if "time" not in raw or "pm25" not in raw:
        raise ValueError(f"Could not find time/pm25 columns in {path}. Columns: {list(raw.columns)}")

    raw["time"] = pd.to_datetime(raw["time"], utc=True, errors="coerce")
    raw = raw.dropna(subset=["time"])
    raw["station"] = station_key
    raw["station_name"] = station_name
    raw["lat"] = lat
    raw["lon"] = lon
    return raw
