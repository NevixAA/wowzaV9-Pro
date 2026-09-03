"""
Scheduler observability — what the cadence ACTUALLY was (Prompt 01 section 7).
=============================================================================
    python -m src.monitoring.scheduler [--days 14] [--write]

Writes `output/scheduler_health.json` (is the machine running as intended, right now) and
`output/high_activity_coverage.json` (what did we actually capture, measured).

THE ONE IDEA THIS MODULE EXISTS FOR

    A configured interval is not an observed interval.

`predict.yml` says `9-59/15 8-23 * * 5,6,0`. That is a REQUEST. What lands is decided by runner
queueing, the 20-minute job, a `git pull --rebase` that aborts, an API that got slow, and a
concurrency group that drops an overlapping fire. Every incident in this project's history looked
like a healthy schedule and an empty table — the 2026-08-19 freeze incident had every functional
step green and persisted nothing for hours. Reading the cron tells you nothing about that; reading
the timestamps of what was stored tells you everything.

So every number here is measured from `observed_at` in the canonical store. Nothing is inferred
from a cron expression, and where the two disagree the measurement wins.

WHY NEAR-KICKOFF COVERAGE IS THE HEADLINE

Odds are pre-match only and cannot be backfilled — established by probe, 0 of 3 fixtures in every
season 2019-2025, ~830 calls spent proving it. A price not captured before kickoff is gone
permanently. So the question is not "did the workflow run today" but "for the fixtures that
kicked off today, did we hold a price at T-6h, T-3h, T-1h, T-30m, T-10m". A run that fires
perfectly every 15 minutes and covers no fixture inside its last hour has failed at the only
thing it was collecting for.

MISSED WINDOWS ARE COUNTED, NOT ESTIMATED

A gap is a pair of consecutive observations further apart than the target interval. The count is
`floor(gap / target) - 1`, so a 47-minute gap against a 10-minute target is 3 missed windows, not
"one long gap". Reported alongside median and p90 spacing, because a median can look perfect while
the tail is where the closing prices were lost.

WHAT THIS DOES NOT DO

It does not change any schedule. Section 7 asks for observability first, and a cadence change
made before the current cadence is measured is a guess. The `recommendations` block states what
the numbers imply and stops there.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

import config.pro_config as cfg

# Section 7: roughly 10 minutes on heavy fixture days, 5-10 during live matches. Held here as the
# YARDSTICK the measurement is scored against, not as something this module can enforce — the
# actual cadence lives in cron expressions in two repositories.
TARGET_MINUTES = {"LIVE_MATCH": 10, "HIGH_ACTIVITY": 10, "NORMAL": 30, "QUIET": 60}

# Kickoff horizons that matter for a price. Ordered wide -> tight.
HORIZONS = ((360, "T-6h"), (180, "T-3h"), (60, "T-1h"), (30, "T-30m"), (10, "T-10m"))

# A day with at least this many kickoffs is a heavy day. Derived from the store rather than
# assumed to be "Fri/Sat/Sun": section 7 is explicit that fixture density is the real variable and
# a Tuesday cup round is a heavy day whatever the weekday says.
HEAVY_DAY_FIXTURES = 20

# How far ahead of a kickoff we consider ourselves "on duty". An observation taken 8h before the
# next kickoff on the board is not a missed 10-minute window — nothing was near enough to matter.
# 6h matches the widest horizon the coverage table reports.
ACTIVE_HORIZON_H = 6.0


def _utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", utc=True)


def _read(table: str) -> pd.DataFrame:
    from src.data import season_store as store
    try:
        return store.read(table)
    except Exception:                                              # noqa: BLE001
        return pd.DataFrame()


def spacing(ts: pd.Series, target_min: float, *, active: pd.Series | None = None) -> dict:
    """Observed cadence of a series of capture timestamps.

    Deduplicated first: one run writes thousands of rows sharing a timestamp, and leaving them in
    would report a spacing of zero minutes and a flawless schedule.

    ALL_TIME vs ACTIVE_WINDOW (Prompt 1.5 section 22). The first version counted every gap the
    same way, so a quiet 03:00-08:00 UTC with no fixture anywhere on earth contributed hundreds
    of "missed windows" identical in kind to a genuine capture failure during a Saturday
    afternoon. That inflates the headline and, worse, makes the number useless for deciding
    anything: you cannot tell a scheduling fault from a night's sleep.

    `active` is a boolean mask over the same index marking observations inside a period we
    actually wanted to be collecting. Gaps are then measured a second time within those periods
    only, and both figures are reported. The all-time number stays because it is the honest
    denominator for "how much history is there"; the active number is the operational one.
    """
    t = _utc(ts).dropna()
    if active is not None:
        act = active.reindex(t.index).fillna(False).astype(bool)
    else:
        act = None
    t = t.drop_duplicates().sort_values()
    if len(t) < 2:
        return {"n_observations": int(len(t)), "median_gap_min": None, "p90_gap_min": None,
                "max_gap_min": None, "missed_windows": None,
                "active_median_gap_min": None, "active_p90_gap_min": None,
                "active_missed_windows": None}
    gaps = t.diff().dropna().dt.total_seconds() / 60.0
    # floor(gap/target) - 1 per gap: a 47-minute gap on a 10-minute target is 3 missed windows.
    missed = int(np.clip(np.floor(gaps / max(target_min, 1e-9)) - 1, 0, None).sum())
    out = {
        "n_observations": int(len(t)),
        "median_gap_min": round(float(gaps.median()), 1),
        "p90_gap_min": round(float(gaps.quantile(0.90)), 1),
        "max_gap_min": round(float(gaps.max()), 1),
        "missed_windows": missed,
        "first": t.iloc[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last": t.iloc[-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Active-window figures. A gap counts only when BOTH ends sit inside an active period —
    # a gap that starts at 23:00 and ends at 09:00 spans a quiet night and is not a fault.
    if act is not None and act.any():
        at = _utc(ts)[act.values].dropna().drop_duplicates().sort_values()
        if len(at) >= 2:
            ag = at.diff().dropna().dt.total_seconds() / 60.0
            # Drop gaps longer than 3x the active window's own median: those bridge inactive
            # periods rather than measuring cadence within one.
            med = float(ag.median())
            inside = ag[ag <= max(med * 3, target_min * 6)]
            if len(inside):
                out["active_median_gap_min"] = round(float(inside.median()), 1)
                out["active_p90_gap_min"] = round(float(inside.quantile(0.90)), 1)
                out["active_missed_windows"] = int(
                    np.clip(np.floor(inside / max(target_min, 1e-9)) - 1, 0, None).sum())
                out["active_n_observations"] = int(len(at))
    out.setdefault("active_median_gap_min", None)
    out.setdefault("active_p90_gap_min", None)
    out.setdefault("active_missed_windows", None)
    return out


def _near_kickoff(snaps: pd.DataFrame, fx: pd.DataFrame) -> dict:
    """Per-horizon coverage: of the fixtures that have KICKED OFF, how many hold an observation
    inside each window.

    Restricted to kicked-off fixtures on purpose. A fixture three days out has no T-10m
    observation because T-10m has not happened yet, and counting it as uncovered would make the
    number meaningless exactly when the board is full of future fixtures.
    """
    if snaps.empty or fx.empty or "kickoff_utc" not in fx.columns:
        return {"status": "NO_DATA"}
    f = fx.drop_duplicates("fixture_key")[["fixture_key", "kickoff_utc", "league"]].copy()
    f["ko"] = _utc(f["kickoff_utc"])
    now = pd.Timestamp.now(tz="UTC")
    f = f[f["ko"].notna() & (f["ko"] <= now)]
    if f.empty:
        return {"status": "NO_KICKED_OFF_FIXTURES"}

    s = snaps[["fixture_key", "observed_at"]].copy()
    s["obs"] = _utc(s["observed_at"])
    s = s.merge(f[["fixture_key", "ko"]], on="fixture_key", how="inner")
    s = s[s["obs"].notna()]
    if s.empty:
        return {"status": "NO_JOINED_OBSERVATIONS", "kicked_off_fixtures": int(len(f))}
    s["mtk"] = (s["ko"] - s["obs"]).dt.total_seconds() / 60.0
    # Pre-kickoff only. A post-kickoff observation is never a pre-match price (section 14).
    pre = s[s["mtk"] >= 0]

    out = {"status": "OK", "kicked_off_fixtures": int(len(f)),
           "fixtures_with_any_prematch_obs": int(pre["fixture_key"].nunique())}
    prev = None
    for lo, name in HORIZONS:
        # The window is (previous horizon, this one]: T-1h means "captured between 1h and 3h out"
        # would be wrong, so each bucket is the band ending at its own bound.
        band = pre[pre["mtk"] <= lo] if prev is None else pre[pre["mtk"] <= lo]
        n = int(band["fixture_key"].nunique())
        out[name] = {"fixtures_covered": n,
                     "pct_of_kicked_off": round(100.0 * n / len(f), 1)}
        prev = lo
    return out


def collect(days: int = 14) -> tuple[dict, dict]:
    """Returns (scheduler_health, high_activity_coverage)."""
    now = pd.Timestamp.now(tz="UTC")
    since = now - pd.Timedelta(days=days)

    fx = _read("fixtures")
    mkt = _read("market_snapshots")
    mdl = _read("model_snapshots")
    props = _read("player_props")
    live = _read("live_signals")
    live_odds = _read("live_odds_snapshots")

    # ---- scheduler MODE, from fixture density and live matches ------------------------
    kicks = pd.Series(dtype="datetime64[ns, UTC]")
    if not fx.empty and "kickoff_utc" in fx.columns:
        kicks = _utc(fx.drop_duplicates("fixture_key")["kickoff_utc"]).dropna()
    today = kicks[(kicks >= now.normalize()) & (kicks < now.normalize() + pd.Timedelta(days=1))]
    # "Active" = kicked off within the last 2h and not yet plausibly finished.
    active = int(((kicks <= now) & (kicks >= now - pd.Timedelta(hours=2))).sum())
    n_today = int(len(today))
    if active > 0:
        mode = "LIVE_MATCH"
    elif n_today >= HEAVY_DAY_FIXTURES:
        mode = "HIGH_ACTIVITY"
    elif n_today > 0:
        mode = "NORMAL"
    else:
        mode = "QUIET"
    target = TARGET_MINUTES[mode]

    # ---- observed cadence per table ---------------------------------------------------
    def _recent(d: pd.DataFrame) -> pd.Series:
        if d.empty or "observed_at" not in d.columns:
            return pd.Series(dtype=object)
        o = _utc(d["observed_at"])
        return d.loc[o >= since, "observed_at"]

    # An observation is "active" when a fixture kicks off within the next ACTIVE_HORIZON_H, i.e.
    # when there was something worth capturing. Built from the fixture list rather than from a
    # hardcoded clock, so a midweek European night counts and a quiet Monday does not.
    def _active_mask(s: pd.Series) -> pd.Series | None:
        if s.empty or kicks.empty:
            return None
        o = _utc(s)
        ko = np.sort(kicks.values)
        # For each observation, the next kickoff at or after it.
        idx = np.searchsorted(ko, o.values, side="left")
        nxt = np.where(idx < len(ko), ko[np.clip(idx, 0, len(ko) - 1)], np.datetime64("NaT"))
        hours = (nxt - o.values) / np.timedelta64(1, "h")
        return pd.Series((hours >= 0) & (hours <= ACTIVE_HORIZON_H), index=s.index)

    cadence = {}
    for name, d, tgt in (("market_snapshots", mkt, target), ("model_snapshots", mdl, target),
                         ("player_props", props, target),
                         ("live_signals", live, TARGET_MINUTES["LIVE_MATCH"]),
                         ("live_odds_snapshots", live_odds, TARGET_MINUTES["LIVE_MATCH"])):
        s = _recent(d)
        cadence[name] = spacing(s, tgt, active=_active_mask(s))

    # ---- freshness: how old is the newest row in each table ---------------------------
    freshness = {}
    for name, d in (("fixtures", fx), ("market_snapshots", mkt), ("model_snapshots", mdl),
                    ("player_props", props), ("live_signals", live),
                    ("live_odds_snapshots", live_odds)):
        if d.empty or "observed_at" not in d.columns:
            freshness[name] = {"age_hours": None, "status": "EMPTY"}
            continue
        last = _utc(d["observed_at"]).max()
        age = (now - last).total_seconds() / 3600.0 if pd.notna(last) else None
        freshness[name] = {
            "last_observed_at": last.strftime("%Y-%m-%dT%H:%M:%SZ") if pd.notna(last) else None,
            "age_hours": round(age, 2) if age is not None else None,
            # 6h rather than a tight bound: several collectors are deliberately daily, so a
            # tighter threshold would flag the design rather than a fault.
            "status": ("STALE" if age is not None and age > 6 else "OK") if age is not None
                      else "UNKNOWN",
        }

    # ---- API budget, read from v9's own meter -----------------------------------------
    api = _api_budget()

    health = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "scheduler_mode": mode,
        "target_interval_min": target,
        "fixtures_today": n_today,
        "active_matches": active,
        "fixture_horizon": {
            "next_3h": int(((kicks > now) & (kicks <= now + pd.Timedelta(hours=3))).sum()),
            "next_6h": int(((kicks > now) & (kicks <= now + pd.Timedelta(hours=6))).sum()),
            "next_24h": int(((kicks > now) & (kicks <= now + pd.Timedelta(hours=24))).sum()),
            "next_72h": int(((kicks > now) & (kicks <= now + pd.Timedelta(hours=72))).sum()),
        },
        "observed_cadence": cadence,
        "freshness": freshness,
        "api_budget": api,
        "odds_api_budget": _odds_api_budget(mkt),
        "odds_spend_by_horizon": _credits_by_horizon(mkt, fx),
        "active_window_horizon_hours": ACTIVE_HORIZON_H,
        # A judgement, kept separate from the measurements so a threshold change can never be
        # mistaken for the data changing.
        "status": _status(cadence, freshness, target, api),
    }

    # ---- coverage: what did we actually capture ---------------------------------------
    coverage = {
        "generated_at": health["generated_at"],
        "window_days": days,
        "scheduler_mode": mode,
        "target_interval_min": target,
        "fixtures": {
            "in_store": int(fx["fixture_key"].nunique()) if not fx.empty else 0,
            "kicked_off": int((kicks <= now).sum()),
            "with_model_snapshot": int(mdl["fixture_key"].nunique()) if not mdl.empty else 0,
            "with_market_snapshot": int(mkt["fixture_key"].nunique()) if not mkt.empty else 0,
            "with_player_props": int(props["fixture_key"].nunique()) if not props.empty else 0,
        },
        "near_kickoff_market": _near_kickoff(mkt, fx),
        "near_kickoff_model": _near_kickoff(mdl, fx),
        "by_weekday": _by_weekday(mkt, fx, target),
        "live": {
            "live_signal_fixtures": int(live["fixture_key"].nunique()) if not live.empty else 0,
            # Distinct from live_signals and NOT interchangeable with it (section 6): signals are
            # our opinion during a match, this is the market's price during a match.
            "live_odds_fixtures": (int(live_odds["fixture_id"].nunique())
                                   if not live_odds.empty and "fixture_id" in live_odds.columns
                                   else 0),
            "live_odds_rows": int(len(live_odds)),
        },
        "by_league": _coverage_by(mkt, fx, "league"),
        "by_market": _coverage_by(mkt, fx, "market"),
        "weekend": _weekend_detail(mkt, mdl, props, live_odds, fx, target),
        "recommendations": [],
    }
    coverage["recommendations"] = _recommend(coverage, cadence, target, mode)
    cov_status, cov_problems = coverage_status(coverage)
    coverage["status"] = cov_status
    coverage["problems"] = cov_problems
    health["coverage_status"] = cov_status
    health["coverage_problems"] = cov_problems
    return health, coverage


def _coverage_by(mkt: pd.DataFrame, fx: pd.DataFrame, col: str) -> dict:
    """Near-kickoff coverage split by league or market — section 23.

    The split matters because the headline hides the shape: a 9% T-10m figure could be every
    fixture equally thin, or a handful of leagues covered well and the rest not at all. Those
    call for opposite fixes.
    """
    if mkt.empty or fx.empty or col not in mkt.columns or "kickoff_utc" not in fx.columns:
        return {}
    f = fx.drop_duplicates("fixture_key")[["fixture_key", "kickoff_utc"]].copy()
    f["ko"] = _utc(f["kickoff_utc"])
    now = pd.Timestamp.now(tz="UTC")
    f = f[f["ko"].notna() & (f["ko"] <= now)]
    if f.empty:
        return {}
    d = mkt[["fixture_key", "observed_at", col]].copy()
    d["obs"] = _utc(d["observed_at"])
    d = d.merge(f, on="fixture_key", how="inner")
    d = d[d["obs"].notna()]
    if d.empty:
        return {}
    d["mtk"] = (d["ko"] - d["obs"]).dt.total_seconds() / 60.0
    pre = d[d["mtk"] >= 0]
    out = {}
    for key, grp in pre.groupby(col):
        fixtures = grp["fixture_key"].nunique()
        if fixtures < 5:               # too thin to read; reported as a count only
            out[str(key)] = {"fixtures": int(fixtures), "sample_status": "INSUFFICIENT"}
            continue
        row = {"fixtures": int(fixtures), "sample_status": "OK"}
        for lo, name in HORIZONS:
            row[name] = round(100.0 * grp[grp["mtk"] <= lo]["fixture_key"].nunique()
                              / fixtures, 1)
        out[str(key)] = row
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["fixtures"])[:20])


def _weekend_detail(mkt, mdl, props, live_odds, fx, target: float) -> dict:
    """Fri/Sat/Sun reported separately with every stream — section 23's explicit request."""
    if fx.empty or "kickoff_utc" not in fx.columns:
        return {}
    ko = _utc(fx.drop_duplicates("fixture_key")["kickoff_utc"]).dropna()
    names = {4: "Fri", 5: "Sat", 6: "Sun"}
    out = {}
    for dow, nm in names.items():
        row = {"fixtures_kicking_off": int((ko.dt.dayofweek == dow).sum())}
        for label, d in (("market", mkt), ("model", mdl), ("props", props),
                         ("live_odds", live_odds)):
            if d.empty or "observed_at" not in d.columns:
                row[f"{label}_observations"] = 0
                continue
            o = _utc(d["observed_at"])
            day = d.loc[o.dt.dayofweek == dow, "observed_at"]
            row[f"{label}_observations"] = int(len(day))
            if label == "market":
                sp = spacing(day, target)
                row["market_median_gap_min"] = sp["median_gap_min"]
                row["market_p90_gap_min"] = sp["p90_gap_min"]
        out[nm] = row
    return out


def _by_weekday(mkt: pd.DataFrame, fx: pd.DataFrame, target: float) -> dict:
    """Fri/Sat/Sun reported separately (section 18), and the other days too — the comparison is
    the point, and 'is the weekend better than Tuesday' cannot be answered by weekend numbers."""
    if mkt.empty or "observed_at" not in mkt.columns:
        return {}
    o = _utc(mkt["observed_at"]).dropna()
    if o.empty:
        return {}
    out = {}
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    ko = (_utc(fx.drop_duplicates("fixture_key")["kickoff_utc"]).dropna()
          if not fx.empty and "kickoff_utc" in fx.columns else pd.Series(dtype=object))
    for i, nm in enumerate(names):
        day = o[o.dt.dayofweek == i]
        entry = spacing(day, target)
        entry["fixtures_kicking_off"] = int((ko.dt.dayofweek == i).sum()) if len(ko) else 0
        out[nm] = entry
    return out


def _api_budget() -> dict:
    """API-Football usage, read from v9's committed meter.

    Pro does not poll the quota endpoint itself: v9's af_usage_monitor already does it every 3
    hours and commits the result, so re-polling would spend calls to learn something already
    written down. Absent when Pro runs without a v9 checkout, which is stated rather than
    guessed at.
    """
    roots = [os.getenv("V9_LOCAL", ""), str(cfg.BASE_DIR.parent / "v9"),
             str(cfg.BASE_DIR.parent / "_v9")]
    for r in roots:
        if not r:
            continue
        p = Path(r) / "output" / "api_usage_log.csv"
        if not p.exists():
            continue
        try:
            u = pd.read_csv(p)
            if u.empty:
                continue
            last = u.iloc[-1]
            used, lim = float(last.get("requests_used", 0)), float(last.get("limit_day", 0) or 0)
            pct = round(100.0 * used / lim, 1) if lim else None
            return {
                "source": str(p),
                "snapshot_ts": last.get("snapshot_ts"),
                "requests_used": int(used),
                "limit_day": int(lim),
                "pct_used": pct,
                "plan": last.get("plan"),
                # Section 8's guardrail, stated as thresholds rather than actions: this module
                # reports, it does not abort anyone's workflow.
                "alert_at": 45000, "abort_at": 60000,
                "status": ("ABORT" if used >= 60000 else
                           "ALERT" if used >= 45000 else "OK"),
            }
        except Exception as e:                                     # noqa: BLE001
            return {"status": "UNREADABLE", "error": f"{type(e).__name__}: {e}", "source": str(p)}
    return {"status": "NO_V9_CHECKOUT",
            "note": "set V9_LOCAL, or check v9 out beside Pro, to read output/api_usage_log.csv"}


def _odds_api_budget(mkt: pd.DataFrame) -> dict:
    """The Odds API credit picture — Prompt 1.5 section 19.

    THERE IS NO CREDIT METER. API-Football publishes usage on its own endpoint and v9 records it;
    The Odds API does not, and nothing in any of the three repos counts credits. So this ESTIMATES
    from the evidence actually stored, and says loudly that it is an estimate.

    The estimator: OddsAPI bills markets x regions per event request, and Pro can see how many
    distinct (fixture, market) observations were stored per day. That is a LOWER BOUND on credits
    — a request returning nothing still bills, and those leave no row — so the true figure is
    higher. A lower bound is still the right thing to publish: it answers "are we anywhere near
    100,000/month" honestly, and it cannot lull anyone by understating the ceiling.

    Reported per section 19 by market and by time-to-kickoff bucket, because the allocation
    question is not "how many credits" but "how many were spent on far-future quiet fixtures that
    had not moved" — spend that section 20 wants moved to the close.
    """
    out: dict = {"source": "ESTIMATED from stored market_snapshots — no credit meter exists",
                 "is_estimate": True, "monthly_allowance": 100_000}
    if mkt.empty or "observed_at" not in mkt.columns:
        out["status"] = "NO_DATA"
        return out
    d = mkt.copy()
    d["obs"] = _utc(d["observed_at"])
    d = d[d["obs"].notna()]
    if d.empty:
        out["status"] = "NO_DATA"
        return out

    now = pd.Timestamp.now(tz="UTC")
    d["day"] = d["obs"].dt.date
    # One billable unit per (fixture, market, capture-minute): several selections of one market
    # arrive in a single response, so counting rows would multiply the estimate by the number of
    # sides quoted.
    d["unit"] = (d["fixture_key"].astype(str) + "|" + d.get("market", "").astype(str) + "|"
                 + d["obs"].dt.strftime("%Y-%m-%dT%H:%M"))
    per_day = d.groupby("day")["unit"].nunique()
    month = d[d["obs"] >= now.normalize().replace(day=1)]
    used_month = int(month["unit"].nunique())
    days_elapsed = max(1, now.day)
    days_in_month = pd.Period(now.strftime("%Y-%m")).days_in_month

    out.update({
        "status": "OK",
        "credits_used_today": int(per_day.get(now.date(), 0)),
        "credits_used_month": used_month,
        "credits_remaining_month": max(0, 100_000 - used_month),
        "estimated_month_end_usage": int(used_month / days_elapsed * days_in_month),
        "mean_per_day": round(float(per_day.mean()), 1),
        "pct_of_monthly_allowance": round(100.0 * used_month / 100_000, 2),
    })
    if "market" in d.columns:
        out["credits_by_market"] = {str(k): int(v) for k, v in
                                    d.groupby("market")["unit"].nunique().items()}
    if "league" in d.columns:
        top = d.groupby("league")["unit"].nunique().sort_values(ascending=False).head(12)
        out["credits_by_league_top12"] = {str(k): int(v) for k, v in top.items()}
    return out


def _credits_by_horizon(mkt: pd.DataFrame, fx: pd.DataFrame) -> dict:
    """Where the odds spend actually goes, by time to kickoff. Section 19's most useful cut:
    it is what turns "reduce waste" from an opinion into an allocation anyone can check."""
    if mkt.empty or fx.empty or "kickoff_utc" not in fx.columns:
        return {}
    f = fx.drop_duplicates("fixture_key")[["fixture_key", "kickoff_utc"]].copy()
    f["ko"] = _utc(f["kickoff_utc"])
    d = mkt[["fixture_key", "observed_at"]].copy()
    d["obs"] = _utc(d["observed_at"])
    d = d.merge(f[["fixture_key", "ko"]], on="fixture_key", how="inner")
    d = d[d["obs"].notna() & d["ko"].notna()]
    if d.empty:
        return {}
    d["mtk"] = (d["ko"] - d["obs"]).dt.total_seconds() / 60.0
    bands = [(-1e9, 0, "post_kickoff"), (0, 10, "T-10m"), (10, 30, "T-30m"), (30, 60, "T-1h"),
             (60, 180, "T-3h"), (180, 360, "T-6h"), (360, 1440, "T-24h"), (1440, 1e9, "far")]
    out = {}
    total = len(d)
    for lo, hi, name in bands:
        n = int(((d["mtk"] > lo) & (d["mtk"] <= hi)).sum())
        out[name] = {"observations": n, "pct": round(100.0 * n / total, 1) if total else 0.0}
    return out


def _status(cadence: dict, freshness: dict, target: float, api: dict) -> str:
    """PASS / WARN / FAIL, judged on the ACTIVE-window cadence where one exists.

    Judging on the all-time p90 was making this permanently FAIL for a reason that is not a
    fault: a quiet overnight gap is not a missed capture, and a health signal that is always red
    is one nobody reads — the same trap PLANNED_OPTIONAL was introduced to escape on the
    registry side.
    """
    if api.get("status") == "ABORT":
        return "FAIL"
    stale = [k for k, v in freshness.items() if v.get("status") == "STALE"]
    core = ("market_snapshots", "model_snapshots")
    if any(freshness.get(k, {}).get("status") in ("STALE", "EMPTY") for k in core):
        return "FAIL"
    slow = []
    for k in core:
        c = cadence.get(k, {})
        # Prefer the active-window p90; fall back to all-time only when there is no active
        # measurement to make.
        p90 = c.get("active_p90_gap_min")
        if p90 is None:
            p90 = c.get("p90_gap_min") or 0
        if p90 > target * 3:
            slow.append(k)
    if slow or stale or api.get("status") == "ALERT":
        return "WARN"
    return "PASS"


def coverage_status(coverage: dict, *, floor_t1h: float = 30.0) -> tuple[str, list[str]]:
    """Health verdict on near-kickoff coverage — Prompt 1.5 section 35.

    A floor rather than a target: the targets in section 15 are where we want to get to, and
    failing health every run until we arrive would make the signal useless. This fires when
    coverage falls below what has already been achieved, which is the thing worth alarming on.
    """
    problems = []
    nk = coverage.get("near_kickoff_market", {})
    if nk.get("status") != "OK":
        return "UNKNOWN", ["no kicked-off fixtures to measure yet"]
    t1h = nk.get("T-1h", {}).get("pct_of_kicked_off")
    if t1h is not None and t1h < floor_t1h:
        problems.append(f"T-1h coverage {t1h}% is below the {floor_t1h}% floor")
    if coverage.get("live", {}).get("live_odds_rows", 0) == 0:
        problems.append("live_odds_snapshots holds no rows")
    return ("WARN" if problems else "PASS"), problems


def _recommend(cov: dict, cadence: dict, target: float, mode: str) -> list[str]:
    """What the numbers imply. Deliberately advisory — section 7 asks for observability, and a
    cadence changed before it was measured is a guess with a commit message."""
    out = []
    nk = cov.get("near_kickoff_market", {})
    if isinstance(nk, dict) and nk.get("status") == "OK":
        tight = nk.get("T-10m", {}).get("pct_of_kicked_off")
        hour = nk.get("T-1h", {}).get("pct_of_kicked_off")
        if tight is not None and tight < 50:
            out.append(f"T-10m market coverage is {tight}% of kicked-off fixtures. Closing price "
                       f"cannot be backfilled, so this is a permanent loss per uncovered fixture.")
        if hour is not None and hour < 80:
            out.append(f"T-1h market coverage is {hour}%. The final hour is where the sharp "
                       f"money moves; a capture window inside it is worth more than an extra "
                       f"one three days out.")
    for t in ("market_snapshots", "model_snapshots"):
        p90 = cadence.get(t, {}).get("p90_gap_min")
        if p90 and p90 > target * 3:
            out.append(f"{t} p90 gap is {p90:.0f} min against a {target:.0f} min target "
                       f"({cadence[t].get('missed_windows')} missed windows) — the tail, not the "
                       f"median, is where captures are being lost.")
    if cov.get("live", {}).get("live_odds_rows", 0) == 0:
        out.append("live_odds_snapshots is empty: no in-play market price has ever been stored. "
                   "v9 does not produce one (inplay_snapshots.csv is score/SOT state and "
                   "live_games.csv holds MODEL fair odds), so pro_live_odds.yml is the only "
                   "source and its first successful window is what fills this.")
    if not out:
        out.append(f"No cadence action indicated: mode {mode}, target {target:.0f} min, "
                   f"observed gaps within tolerance.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--write", action="store_true", help="write the two JSON artifacts")
    args = ap.parse_args()

    health, coverage = collect(args.days)

    print(f"[scheduler] mode={health['scheduler_mode']} target={health['target_interval_min']}min "
          f"fixtures_today={health['fixtures_today']} active={health['active_matches']} "
          f"status={health['status']}")
    for t, c in health["observed_cadence"].items():
        if c.get("n_observations", 0) < 2:
            print(f"    {t:22} {c.get('n_observations', 0)} observation(s) — no cadence to measure")
            continue
        am, aw = c.get("active_median_gap_min"), c.get("active_missed_windows")
        act = (f" | ACTIVE median {am:>6.1f} · {aw:>4} missed" if am is not None
               else " | ACTIVE n/a")
        print(f"    {t:22} median {c['median_gap_min']:>6.1f} min · p90 {c['p90_gap_min']:>7.1f} "
              f"· max {c['max_gap_min']:>8.1f} · {c['missed_windows']:>4} missed{act}")
    nk = coverage.get("near_kickoff_market", {})
    if nk.get("status") == "OK":
        print(f"    near-kickoff market coverage ({nk['kicked_off_fixtures']} kicked-off "
              f"fixtures):")
        for _, name in HORIZONS:
            e = nk.get(name, {})
            print(f"      {name:6} {e.get('fixtures_covered', 0):>5} fixtures "
                  f"({e.get('pct_of_kicked_off', 0)}%)")
    for r in coverage["recommendations"]:
        print(f"    -> {r}")

    if args.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for name, payload in (("scheduler_health.json", health),
                              ("high_activity_coverage.json", coverage)):
            p = cfg.OUTPUT_DIR / name
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str),
                           encoding="utf-8")
            json.loads(tmp.read_text(encoding="utf-8"))            # parses? else raise, tmp left
            os.replace(tmp, p)
            print(f"[scheduler] wrote {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
