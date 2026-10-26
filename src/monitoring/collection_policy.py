"""Cost-aware collection policy for Pro's own API-Football collectors (owner brief 2026-10-26, E2).

    python -m src.monitoring.collection_policy            # budget status from the run ledger
    python -m src.monitoring.collection_policy --replay   # before/after replay on recorded data

WHAT WAS WRONG. Measured on 14 days of Pro's store (scheduler_health.json, 2026-10-26): 79% of
stored odds observations were more than 24h from kickoff, 0.5% at T-1h, 0.3% at T-30m, 0.2% at
T-10m, and T-1h coverage sat on its 30% floor. In the scout specifically — the largest metered
spender, ~1,400 calls/day for the 2-hourly sweep — every sweep re-polled every league with a
fixture anywhere in the next 7 days, although API-Football refreshes a pre-match price only about
every 3 hours that far out and most of those polls re-read an unchanged number. Meanwhile the
near-kickoff loop polled every watched fixture every 10 minutes for its last 75 minutes (~7 calls a
fixture) whenever it happened to be running.

THE POLICY, in the owner's priority order:

    P1 NEAR_CLOSE                 fixture inside T-6h. Needed for CLV / market research; a price
                                  not captured before kickoff is gone for good (CLAUDE.md:
                                  historical odds cannot be backfilled). NEVER shed by the
                                  monthly guard — only the daily quota floor (SCOUT_MIN_QUOTA,
                                  which protects v9) can stop it.
    P2 PRODUCTION                 a league v9 bets (scout leagues exclude these by construction).
    P3 REGISTERED_EXPERIMENT      a league with a registered prospective hypothesis in its
                                  CONFIRMATION window (registry/scout_hypotheses.json, E3;
                                  H-EDGE2 / weekly panel / scout forward tests).
    P4 CANDIDATE_NEAR_THRESHOLD   a scout league within reach of its evidence gate (EARLY, or
                                  >= 200 of the 300 settled-with-close fixtures READABLE needs).
    P5 FAR_HORIZON                everything else.

WASTE IS CUT BEFORE CLOSE COVERAGE:
  * re-poll interval by horizon band, not by cron: inside T-6h every opportunity; T-24h..T-6h
    every 3h; T-72h..T-24h every 8h; beyond T-72h once a day. Halved for P2/P3.
  * a far-horizon (> T-24h) league whose last two polls changed nothing is re-polled half as often.
  * near-kickoff: one sample per fixture per CLOSE BAND (T-120..60m, T-60..30m, T-30..10m,
    T-10..1m) instead of every 10 minutes for 75 minutes — at most 4 calls a fixture instead of
    ~7, and one more horizon covered — and fixtures of one league that are
    due together are fetched with one league call when that is cheaper than per-fixture calls.

TIMING. Nothing here depends on a cron firing near its slot (CLAUDE.md, "GitHub Actions cannot hit
a clock"). Every decision is made in-run against REAL kickoff times and RECORDED poll timestamps
(the run ledger and the change-log's snapshot_ts) — never a file mtime.

HARD BUDGET GUARD. Every metered run writes one ledger record (output/budget/runs/<YYYY-MM>/...,
one new file per run, so concurrent workflows can never conflict on it). The guard projects
month-end usage with the same formula and thresholds as scheduler_health (E1) and sheds by
priority: OK -> all classes; WARN -> P5 shed; RED -> only P1 and P2. A per-day cap (the
remaining allowance spread over the remaining days, x1.5 for weekend peaks) sheds P3-P5 for the
rest of the day once it is spent.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import pandas as pd

from config import pro_config as cfg
from src.monitoring.scheduler import (BUDGET_RED_PCT, BUDGET_WARN_PCT, TRAILING_DAYS,
                                      budget_status, project_month_end)

LEDGER_DIR = cfg.OUTPUT_DIR / "budget" / "runs"
REPLAY_OUT = cfg.OUTPUT_DIR / "budget" / "collection_policy_replay.json"

#: Pro's self-imposed monthly allowance for its METERED API-Football collectors. API-Football's
#: plan is 75,000/day (~2.25M/month) shared with v9, whose production loop has priority; this
#: number is Pro's share, deliberately small so Pro can never become the reason v9 is starved.
MONTHLY_ALLOWANCE = int(os.getenv("PRO_AF_MONTHLY_ALLOWANCE", "100000"))
#: Planning target: the policy is designed to sit at or below this share of the allowance.
HEADROOM_TARGET_PCT = 80.0
DAY_CAP_PEAK_FACTOR = 1.5

PRIORITY = {1: "NEAR_CLOSE", 2: "PRODUCTION", 3: "REGISTERED_EXPERIMENT",
            4: "CANDIDATE_NEAR_THRESHOLD", 5: "FAR_HORIZON"}
NEAR_CLOSE_MIN = 360.0

# (upper bound in minutes to kickoff, band name, minimum minutes between polls)
REPOLL_BANDS = ((NEAR_CLOSE_MIN, "T-6h..T-0", 0.0),
                (1440.0, "T-24h..T-6h", 180.0),
                (4320.0, "T-72h..T-24h", 480.0),
                (float("inf"), ">T-72h", 1440.0))
UNCHANGED_STREAK_FOR_BACKOFF = 2

#: Near-kickoff close bands: one sample per fixture per band, (upper, lower] minutes to kickoff.
#: Aligned with the coverage bands scheduler_health reports, so a sample counts where it is read.
NEAR_BANDS = ((120.0, 60.0, "T-3h"), (60.0, 30.0, "T-1h"), (30.0, 10.0, "T-30m"), (10.0, 1.0, "T-10m"))
NEAR_WATCH_MIN = NEAR_BANDS[0][0]
NEAR_PASS_SECONDS = 300          # a pass every 5 min; every band is wider than that
ODDS_PAGE_SIZE = 10              # API-Football /odds pages at 10 fixtures

# Coverage bands used in the replay — the same edges as scheduler._credits_by_horizon.
COVERAGE_BANDS = ((0, 10, "T-10m"), (10, 30, "T-30m"), (30, 60, "T-1h"), (60, 180, "T-3h"),
                  (180, 360, "T-6h"), (360, 1440, "T-24h"), (1440, 1e9, "far"))


# ── priority and due-ness ─────────────────────────────────────────────────────────────────────
def priority_class(minutes_to_kickoff: float, *, production: bool = False,
                   experiment: bool = False, candidate: bool = False) -> int:
    if minutes_to_kickoff is not None and 0 < minutes_to_kickoff <= NEAR_CLOSE_MIN:
        return 1
    if production:
        return 2
    if experiment:
        return 3
    if candidate:
        return 4
    return 5


def repoll_minutes(minutes_to_kickoff: float, prio: int, unchanged_streak: int = 0) -> float:
    """Minimum spacing between polls of the same market at this horizon."""
    for upper, _, gap in REPOLL_BANDS:
        if minutes_to_kickoff <= upper:
            base = gap
            break
    if prio in (2, 3):
        base /= 2.0
    # Back-off applies only beyond T-24h: inside a day of kickoff an unchanged market is still
    # worth re-reading, because that is where it starts to move.
    if minutes_to_kickoff > 1440 and unchanged_streak >= UNCHANGED_STREAK_FOR_BACKOFF:
        base *= 2.0
    return base


def is_due(minutes_to_kickoff: float, last_polled_min_ago: float | None, prio: int,
           unchanged_streak: int = 0) -> bool:
    if last_polled_min_ago is None:              # never polled: always due
        return True
    return last_polled_min_ago >= repoll_minutes(minutes_to_kickoff, prio, unchanged_streak)


def near_band(minutes_to_kickoff: float) -> str | None:
    for hi, lo, name in NEAR_BANDS:
        if lo < minutes_to_kickoff <= hi:
            return name
    return None


def league_pages(n_fixtures: int) -> int:
    return max(1, math.ceil(n_fixtures / ODDS_PAGE_SIZE))


def plan_near_calls(due: pd.DataFrame, league_upcoming: dict) -> list[tuple[str, int, int]]:
    """Cheapest call set for the fixtures due a near sample this pass.

    due: columns fixture_id, league_id. league_upcoming: {league_id: priced upcoming fixtures},
    which sets what a league call costs (pages). Returns [(kind, id, cost)] with kind 'league'
    or 'fixture'. A league call is used only when it costs fewer calls than the fixtures it
    replaces — 'reduce duplicate polls' without ever losing a due fixture.
    """
    out = []
    for lid, g in due.groupby("league_id"):
        pages = league_pages(int(league_upcoming.get(lid, len(g))))
        if len(g) > pages:
            out.append(("league", int(lid), pages))
        else:
            out += [("fixture", int(f), 1) for f in g["fixture_id"]]
    return out


# ── the run ledger (recorded counts; never mtime) ─────────────────────────────────────────────
def record_run(collector: str, started: str, finished: str, api_calls: int, *,
               quota_remaining=None, detail: dict | None = None, dry: bool = False) -> Path | None:
    """One new file per run. Concurrent workflows never touch the same path, so a rebase can
    never conflict on the ledger and a push can never drop another run's record."""
    rec = {"collector": collector, "started": started, "finished": finished,
           "api_calls": int(api_calls or 0), "quota_remaining": quota_remaining,
           "run_id": cfg.run_id(), "detail": detail or {}}
    if dry:
        print(f"  [dry-run] ledger record {rec['collector']}: {rec['api_calls']} call(s)")
        return None
    d = LEDGER_DIR / str(started)[:7]
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{collector}__{rec['run_id']}__{str(started).replace(':', '')}.json"
    p.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return p


def load_runs(since: pd.Timestamp | None = None, root: Path | None = None) -> pd.DataFrame:
    """All ledger records (files may hold one record or a list — the git-history backfill is a
    list). Timestamps come from the record's own `started`, never from the file."""
    root = root or LEDGER_DIR
    recs = []
    for f in sorted(root.glob("*/*.json")) if root.exists() else []:
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                              # noqa: BLE001
            continue
        recs += j if isinstance(j, list) else [j]
    if not recs:
        return pd.DataFrame(columns=["collector", "started", "api_calls"])
    d = pd.DataFrame(recs)
    d["ts"] = pd.to_datetime(d["started"], utc=True, errors="coerce")
    d = d.dropna(subset=["ts"]).drop_duplicates(["collector", "started"])
    if since is not None:
        d = d[d["ts"] >= since]
    return d.sort_values("ts").reset_index(drop=True)


def budget(now: pd.Timestamp | None = None, runs: pd.DataFrame | None = None,
           allowance: int = MONTHLY_ALLOWANCE) -> dict:
    """Month-end projection and status for Pro's metered collectors, from the ledger."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    runs = load_runs() if runs is None else runs
    if runs.empty:
        return {"status": "NO_DATA", "monthly_allowance": allowance,
                "note": "no ledger records yet (output/budget/runs)"}
    start = now.normalize().replace(day=1)
    mtd = runs[(runs["ts"] >= start) & (runs["ts"] <= now)]
    tr = runs[(runs["ts"] >= now - pd.Timedelta(days=TRAILING_DAYS)) & (runs["ts"] <= now)]
    used = int(mtd["api_calls"].sum())
    proj = project_month_end(used, now, trailing_used=int(tr["api_calls"].sum()))
    status, pct = budget_status(proj["projected_month_end"], used, allowance)
    today = runs[runs["ts"] >= now.normalize()]
    remaining_days = max(1.0, proj["remaining_days"])
    day_cap = max(0.0, allowance - used) / remaining_days * DAY_CAP_PEAK_FACTOR
    return {"status": status, "monthly_allowance": allowance,
            "headroom_target_pct": HEADROOM_TARGET_PCT,
            "projected_pct_of_allowance": pct, "projection": proj,
            "used_today": int(today["api_calls"].sum()), "day_cap": int(day_cap),
            "by_collector_mtd": {k: int(v) for k, v in mtd.groupby("collector")["api_calls"].sum().items()},
            "metered_collectors": sorted(runs["collector"].unique().tolist()),
            "thresholds": {"WARN_above_pct": BUDGET_WARN_PCT, "RED_above_pct": BUDGET_RED_PCT},
            "source": "output/budget/runs ledger (recorded per-run call counts)"}


class Guard:
    """Sheds by priority. Built once per run from the ledger; `spend()` keeps it current in-run."""

    def __init__(self, now: pd.Timestamp | None = None, runs: pd.DataFrame | None = None,
                 allowance: int = MONTHLY_ALLOWANCE):
        self.b = budget(now, runs, allowance)
        self.spent = 0

    def spend(self, n: int) -> None:
        self.spent += int(n)

    @property
    def max_priority(self) -> int:
        s = self.b.get("status")
        lim = {"RED": 2, "WARN": 4}.get(s, 5)
        cap = self.b.get("day_cap")
        if cap is not None and self.b.get("used_today", 0) + self.spent >= cap:
            lim = min(lim, 2)
        return lim

    def allowed(self, prio: int) -> bool:
        return prio == 1 or prio <= self.max_priority


# ── replay on recorded data: calls/month and horizon coverage, before vs after ────────────────
def _coverage(obs: pd.DataFrame, fixtures: pd.DataFrame) -> dict:
    """obs: fixture_id, ts (UTC). % of fixtures with >= 1 observation in each band."""
    if obs.empty or fixtures.empty:
        return {}
    o = obs.merge(fixtures[["fixture_id", "ko"]], on="fixture_id")
    o["mtk"] = (o["ko"] - o["ts"]).dt.total_seconds() / 60.0
    n = fixtures["fixture_id"].nunique()
    return {name: round(100.0 * o[(o["mtk"] > lo) & (o["mtk"] <= hi)]["fixture_id"].nunique() / n, 1)
            for lo, hi, name in COVERAGE_BANDS}


def replay(days: int = 14, near_minutes_after: float = 330.0) -> dict:
    """Replays the scout's RECORDED runs (ledger, i.e. the committed per-run summaries) against
    the fixtures the scout actually priced, under the old cadence and under this policy.

    Sweep calls are modelled as 11 date calls + one /odds page per 10 priced upcoming fixtures
    per polled league, calibrated against each run's recorded `api_calls`. Near-loop calls are
    one per watched fixture per 10-minute pass (before) and one per close band, league-grouped
    (after). The after case keeps GitHub's ACTUAL deliveries (same run starts) and lengthens
    near runs to `near_minutes_after`; it does not assume any extra run fires.
    """
    from src.data import season_store as store
    now = pd.Timestamp.now(tz="UTC")
    since = now - pd.Timedelta(days=days)
    runs = load_runs(since - pd.Timedelta(days=1))
    sweeps = runs[(runs["collector"] == "scout_sweep") & (runs["ts"] >= since)].copy()
    nears = runs[(runs["collector"] == "scout_near") & (runs["ts"] >= since)].copy()
    odds = store.read("scout_odds")
    if odds.empty or sweeps.empty:
        return {"status": "NO_DATA"}
    odds["ts"] = pd.to_datetime(odds["snapshot_ts"], utc=True, errors="coerce")
    fx = (odds.groupby("fixture_id").agg(league_id=("league_id", "first"),
                                          kickoff_ts=("kickoff_ts", "first"),
                                          first_seen=("ts", "min")).reset_index())
    fx["ko"] = pd.to_datetime(fx["kickoff_ts"], unit="s", utc=True)
    status = _league_status_flags()

    # Changes per (league, sweep): any change-log row written during that sweep.
    sweeps["fin"] = pd.to_datetime(sweeps["finished"], utc=True, errors="coerce")
    sweep_rows = []
    for r in sweeps.itertuples():
        t, t1 = r.ts, (r.fin if pd.notna(r.fin) else r.ts + pd.Timedelta(minutes=5))
        up = fx[(fx["ko"] > t) & (fx["first_seen"] <= t1)]
        per_lg = up.groupby("league_id")["fixture_id"].nunique()
        nearest = up.groupby("league_id")["ko"].min()
        ch = odds[(odds["ts"] >= t) & (odds["ts"] <= t1)].groupby("league_id")["fixture_id"].size()
        sweep_rows.append({"ts": t, "recorded": int(r.api_calls), "per_lg": per_lg,
                           "nearest": nearest, "changed": ch})

    # ---- BEFORE: every league with a priced upcoming fixture, every sweep -----------------
    modelled_before = [11 + sum(league_pages(int(n)) for n in s["per_lg"]) for s in sweep_rows]
    recorded = [s["recorded"] for s in sweep_rows]
    calib = (sum(recorded) / sum(modelled_before)) if sum(modelled_before) else 1.0

    # ---- AFTER: league polled only when due under the policy ------------------------------
    last_poll: dict = {}
    streak: dict = {}
    modelled_after, polls_before, polls_after = [], [], []
    for s in sweep_rows:
        t = s["ts"]
        calls = 11
        for lid, n in s["per_lg"].items():
            mtk = (s["nearest"][lid] - t).total_seconds() / 60.0
            polls_before.append((lid, t))
            fl = status.get(int(lid), {})
            prio = priority_class(mtk, experiment=fl.get("experiment", False),
                                  candidate=fl.get("candidate", False))
            ago = None if lid not in last_poll else (t - last_poll[lid]).total_seconds() / 60.0
            if is_due(mtk, ago, prio, streak.get(lid, 0)):
                calls += league_pages(int(n))
                last_poll[lid] = t
                polls_after.append((lid, t))
                streak[lid] = 0 if int(s["changed"].get(lid, 0)) else streak.get(lid, 0) + 1
        modelled_after.append(calls)

    # ---- near loop -------------------------------------------------------------------------
    nears["fin"] = pd.to_datetime(nears["finished"], utc=True, errors="coerce")
    near_calls_before, near_obs_before = 0, []
    for r in nears.itertuples():
        t, end = r.ts, (r.fin if pd.notna(r.fin) else r.ts + pd.Timedelta(minutes=165))
        while t < end - pd.Timedelta(minutes=1):
            tg = fx[(fx["ko"] > t) & (fx["ko"] <= t + pd.Timedelta(minutes=75)) & (fx["first_seen"] <= t)]
            near_calls_before += len(tg)
            near_obs_before += [(f, t) for f in tg["fixture_id"]]
            t += pd.Timedelta(minutes=10)
    windows = []
    for r in nears.sort_values("ts").itertuples():
        a, b = r.ts, r.ts + pd.Timedelta(minutes=near_minutes_after)
        if windows and a <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], b))
        else:
            windows.append((a, b))
    near_calls_after, near_obs_after, sampled = 0, [], set()
    for a, b in windows:
        t = a
        while t < b - pd.Timedelta(minutes=1):
            tg = fx[(fx["ko"] > t) & (fx["ko"] <= t + pd.Timedelta(minutes=NEAR_WATCH_MIN)) & (fx["first_seen"] <= t)].copy()
            if len(tg):
                tg["band"] = [near_band((k - t).total_seconds() / 60.0) for k in tg["ko"]]
                tg = tg[tg["band"].notna()]
                tg = tg[[(f, bnd) not in sampled for f, bnd in zip(tg["fixture_id"], tg["band"])]]
                if len(tg):
                    up = fx[(fx["ko"] > t) & (fx["first_seen"] <= t)].groupby("league_id")["fixture_id"].nunique().to_dict()
                    for kind, _id, cost in plan_near_calls(tg, up):
                        near_calls_after += cost
                    sampled |= set(zip(tg["fixture_id"], tg["band"]))
                    near_obs_after += [(f, t) for f in tg["fixture_id"]]
            t += pd.Timedelta(seconds=NEAR_PASS_SECONDS)

    # ---- coverage on fixtures that kicked off inside the replay window ----------------------
    done = fx[(fx["ko"] > since + pd.Timedelta(days=1)) & (fx["ko"] <= now)]

    def _obs_from_polls(polls):
        if not polls:
            return pd.DataFrame(columns=["fixture_id", "ts"])
        p = pd.DataFrame(polls, columns=["league_id", "ts"])
        o = p.merge(done[["fixture_id", "league_id", "ko", "first_seen"]], on="league_id")
        return o[(o["ts"] < o["ko"]) & (o["first_seen"] <= o["ts"] + pd.Timedelta(minutes=5))][["fixture_id", "ts"]]

    def _obs(pairs):
        return pd.DataFrame(pairs, columns=["fixture_id", "ts"]) if pairs else pd.DataFrame(columns=["fixture_id", "ts"])

    obs_before = pd.concat([_obs_from_polls(polls_before), _obs(near_obs_before)], ignore_index=True)
    obs_after = pd.concat([_obs_from_polls(polls_after), _obs(near_obs_after)], ignore_index=True)
    span_days = max(1e-9, (sweeps["ts"].max() - sweeps["ts"].min()).total_seconds() / 86400.0)
    per_month = lambda x: int(round(x / span_days * 30.4))  # noqa: E731

    sweep_before = sum(recorded)
    sweep_after = sum(modelled_after) * calib
    near_before_rec = int(nears["api_calls"].sum())
    near_calib = (near_before_rec / near_calls_before) if near_calls_before else 1.0
    near_after = near_calls_after * near_calib
    out = {
        "generated_at": cfg.utc_now_iso(), "window_days": days,
        "replay_span_days": round(span_days, 2),
        "recorded_runs": {"scout_sweep": int(len(sweeps)), "scout_near": int(len(nears))},
        "calibration": {"sweep_recorded_over_modelled": round(calib, 3),
                        "near_recorded_over_modelled": round(near_calib, 3)},
        "calls_per_month": {
            "before": {"scout_sweep": per_month(sweep_before), "scout_near": per_month(near_before_rec),
                       "total": per_month(sweep_before + near_before_rec)},
            "after": {"scout_sweep": per_month(sweep_after), "scout_near": per_month(near_after),
                      "total": per_month(sweep_after + near_after)},
            "allowance": MONTHLY_ALLOWANCE, "headroom_target_pct": HEADROOM_TARGET_PCT,
        },
        "league_polls": {"before": len(polls_before), "after": len(polls_after)},
        "coverage_pct_of_kicked_off_fixtures": {
            "n_fixtures": int(done["fixture_id"].nunique()),
            "before": _coverage(obs_before, done), "after": _coverage(obs_after, done)},
        "assumptions": [
            "same GitHub deliveries as recorded (run start times from the ledger); near runs lengthened to "
            f"{near_minutes_after:.0f} min in the after case",
            "a league /odds call returns every priced upcoming fixture of that league (pages of 10)",
            "a fixture is pollable from its first stored price (first snapshot_ts) onward",
            "modelled calls are scaled by the recorded/modelled ratio of the before case",
        ],
    }
    return out


def _league_status_flags() -> dict:
    """{league_id: {candidate, experiment}} from the scout status and the E3 hypothesis registry."""
    out: dict = {}
    try:
        st = json.loads((cfg.OUTPUT_DIR / "scout" / "league_status.json").read_text(encoding="utf-8"))
        for r in st.get("leagues", []):
            out[int(r["league_id"])] = {
                "candidate": r.get("status") in ("EARLY", "READABLE") or int(r.get("settled_with_close", 0)) >= 200}
    except Exception:                                                  # noqa: BLE001
        pass
    try:
        reg = json.loads((cfg.REGISTRY_DIR / "scout_hypotheses.json").read_text(encoding="utf-8"))
        for h in reg.get("hypotheses", []):
            if h.get("state") == "CONFIRMING":
                out.setdefault(int(h["league_id"]), {})["experiment"] = True
    except Exception:                                                  # noqa: BLE001
        pass
    return out


def league_flags() -> dict:
    return _league_status_flags()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.replay:
        r = replay(a.days)
        # Separates the two levers: the policy alone (near runs keep their old 165-minute life)
        # versus the policy plus the longer near runs the workflow now asks for.
        s = replay(a.days, near_minutes_after=165.0)
        r["sensitivity_policy_only_near_runs_165min"] = {
            "calls_per_month_after": s.get("calls_per_month", {}).get("after"),
            "coverage_after": s.get("coverage_pct_of_kicked_off_fixtures", {}).get("after")}
        print(json.dumps(r, indent=1, default=str))
        if a.write:
            REPLAY_OUT.parent.mkdir(parents=True, exist_ok=True)
            REPLAY_OUT.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
        return 0
    print(json.dumps(budget(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
