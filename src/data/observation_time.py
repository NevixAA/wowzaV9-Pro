"""
When was a price actually observed? Provider time vs Pro's ingest time.
=====================================================================
Data Truth round 3 (2026-11-02). `observed_at` in market_snapshots and book_odds_snapshots was the
INGEST time on 100% of rows (788k): every importer left it blank and season_store.append filled in
"now". So "T-10m coverage" measured when Pro's collect job happened to run, not when a price existed.

The provider's own stamp exists for most rows: v9's capture time (`snapshot_ts`) on the per-book and
odds-history files, and the board's `generated_at` on predictions. This module is the one place that
(1) turns those into an `observed_at` + `observed_at_source` pair at import, and (2) tells a reader
which time to trust for an already-stored row. A stamp with no time of day (date-only backfills,
written as T00:00:00) is not an observation time and is never used as one.
"""
from __future__ import annotations

import pandas as pd

INGEST = "ingest_time"
PROVIDER_PREFIX = "provider:"

#: Stored columns that carry a provider observation time, in order of preference.
PROVIDER_TIME_COLUMNS = ("snapshot_ts", "captured_at")


def _iso(values: pd.Series) -> pd.Series:
    t = pd.to_datetime(values.astype("string"), utc=True, errors="coerce", format="mixed")
    raw = values.astype("string").fillna("")
    has_clock = raw.str.contains(r"\d{1,2}:\d{2}", regex=True)
    midnight = (t.dt.hour == 0) & (t.dt.minute == 0) & (t.dt.second == 0)
    t = t.where(has_clock & ~midnight)                      # date-only stamps are not times
    s = t.dt.strftime("%Y-%m-%dT%H:%M:%SZ").astype(object)
    s[t.isna().to_numpy()] = None
    return s


#: A provider stamp later than the import moment by more than this is not an observation time.
FUTURE_TOLERANCE = pd.Timedelta(minutes=10)


def provider_observed_at(values: pd.Series, source: str,
                         now: pd.Timestamp | None = None) -> pd.DataFrame:
    """observed_at (provider stamp, ISO UTC; None where unusable -> the store fills ingest time) and
    observed_at_source ('provider:<source>' or 'ingest_time') for each row.

    NAIVE STAMPS ARE READ AS UTC (Data Truth round 5, verified, not assumed). v9 writes
    standard_odds_history / newformat_odds_dense snapshot_ts with a naive `datetime.now()`
    (src/drift.py snapshot), which is UTC only because GitHub's ubuntu runners run in UTC and no
    v9 workflow sets TZ. Checked at v9 origin/data-truth-100: all 748 commits of each file are by
    github-actions[bot]; on 30 sampled commits per file the newest naive stamp is 0.0h before the
    commit's UTC time (Israel local time would put it 2-3h AFTER). The other v9 files carry 'Z'.
    The guard below keeps that true: a stamp later than `now` (+10 min) cannot be when a price was
    observed - it is what a local-time (UTC+2/+3) write would look like - so it is not used.
    """
    iso = _iso(values)
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    t = pd.to_datetime(iso, utc=True, errors="coerce")
    future = (t > now + FUTURE_TOLERANCE).fillna(False).to_numpy()
    if future.any():
        print(f"[observation_time] {int(future.sum())} {source} stamp(s) later than the import "
              f"time - not used as observation time (ingest time recorded instead)")
        iso = iso.copy()
        iso[future] = None
    src = pd.Series(INGEST, index=values.index, dtype=object)
    src[iso.notna()] = PROVIDER_PREFIX + source
    return pd.DataFrame({"observed_at": iso, "observed_at_source": src}, index=values.index)


def provider_time(df: pd.DataFrame) -> pd.Series:
    """The provider observation time of each stored row (UTC), NaT when only ingest time is known.

    observed_at counts only where observed_at_source says it came from the provider; otherwise the
    first usable provider column (snapshot_ts, captured_at) is used. Never falls back to ingest."""
    out = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    if "observed_at_source" in df.columns and "observed_at" in df.columns:
        ok = df["observed_at_source"].astype("string").str.startswith(PROVIDER_PREFIX).fillna(False)
        out[ok] = pd.to_datetime(df.loc[ok, "observed_at"], utc=True, errors="coerce", format="mixed")
    for c in PROVIDER_TIME_COLUMNS:
        if c in df.columns:
            need = out.isna()
            if need.any():
                iso = _iso(df.loc[need, c])
                out[need] = pd.to_datetime(iso, utc=True, errors="coerce")
    return out
