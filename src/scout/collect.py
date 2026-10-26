"""League scout collector — one sweep.

    python -m src.scout.collect [--dry-run] [--max-calls N] [--history-budget N]

ONE SWEEP DOES FOUR THINGS, in this order, each bounded:

1. HISTORY. Finished matches for the last 4 completed seasons plus the current one, per league,
   resumable (`output/scout/history_done.json`). Feeds the baseline model. Results persist
   historically on API-Football, so this can be caught up at any time; it is bounded per run so
   it never crowds out step 3, which cannot be caught up.
2. FIXTURES BY DATE. `/fixtures?date=` for 3 days back and 7 ahead: one call per day covers every
   league in the world, so upcoming fixtures and new results cost 11 calls total.
3. ODDS. `/odds?league&season` for each watched league that has a fixture in the next 7 days,
   priority-1 leagues first. Kept: Pinnacle, Bet365 and the cross-book median, for O/U 1.5/2.5/3.5
   and BTTS. Stored as a CHANGE-LOG (a row only when a price moved), except inside the last 3
   hours, where every observation is kept so the close is seen with a timestamp. THIS IS THE STEP
   THAT CANNOT BE BACKFILLED — once a match starts its odds are gone from the API.
4. MODEL FREEZE. The first time a fixture is seen with odds, the baseline model's probabilities
   are written once and never revised, so the later comparison is prospective.

Writes only Pro's own season store (scout_results, scout_odds, scout_model). Never v9.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store
from src.scout import af, model, parse
from src.scout import leagues as reg

OUT = cfg.OUTPUT_DIR / "scout"
HISTORY_DONE = OUT / "history_done.json"
HISTORY_SEASONS = 4          # completed seasons per league, plus the current one
DAYS_BACK, DAYS_AHEAD = 3, 7
QUOTE_LOOKBACK_DAYS = 12     # odds partitions read to rebuild the last stored price per key


# ── store helpers ─────────────────────────────────────────────────────────────────────────────
def _read_recent(table: str, days: int) -> pd.DataFrame:
    """Read only the partitions observed in the last `days` days. The change-log needs the last
    stored price per key, and every key that matters belongs to a fixture that has not kicked
    off, so old partitions are never needed here."""
    root = cfg.season_dir() / table
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    files = [f for f in sorted(root.glob("dt=*/run=*.parquet"))
             if f.parent.name.split("=", 1)[1] >= cut]
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else pd.DataFrame()


def _append(table: str, rows: list[dict] | pd.DataFrame, tag: str, dry: bool) -> int:
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df.empty:
        return 0
    if dry:
        print(f"  [dry-run] would append {len(df):,} row(s) to {table}")
        return len(df)
    try:
        store.append(table, df, source="api_football:scout", rid=f"{cfg.run_id()}-{tag}")
    except store.LocalWriteRefused as e:
        print(f"  NOT written — {e}")
        return 0
    return len(df)


def _results() -> pd.DataFrame:
    d = store.read("scout_results")
    if d.empty:
        return d
    return d.sort_values("ingested_at").drop_duplicates("fixture_id", keep="last")


# ── steps ─────────────────────────────────────────────────────────────────────────────────────
def step_history(c: af.Client, watch: list[dict], budget: int, dry: bool) -> int:
    done = json.loads(HISTORY_DONE.read_text(encoding="utf-8")) if HISTORY_DONE.exists() else {}
    body = c.get("/leagues", {}) or {}
    seasons = {}
    for x in body.get("response") or []:
        ss = sorted(x.get("seasons") or [], key=lambda s: s["year"])
        cur = [s["year"] for s in ss if s.get("current")]
        if cur:
            past = [s["year"] for s in ss if s["year"] < cur[0]][-HISTORY_SEASONS:]
            seasons[x["league"]["id"]] = (past, cur[0])
    rows, used = [], 0
    for lg in watch:
        past, cur = seasons.get(lg["id"], ([], None))
        for yr in past + ([cur] if cur else []):
            k = f"{lg['id']}:{yr}"
            if k in done or used >= budget:
                continue
            resp = c.get_all_pages("/fixtures", {"league": lg["id"], "season": yr})
            used += 1
            fin = [r for r in parse.fixture_rows(resp) if r["status"] in parse.FINISHED]
            rows.extend(fin)
            # An empty answer may be a failed call; only a real payload marks the season done,
            # otherwise a transient error would silently cost a league a season of history.
            if resp:
                done[k] = len(fin)
    n = _append("scout_results", rows, "hist", dry)
    if not dry:
        OUT.mkdir(parents=True, exist_ok=True)
        HISTORY_DONE.write_text(json.dumps(done, indent=0, sort_keys=True), encoding="utf-8")
    print(f"[scout] history: {used} league-season(s) fetched, {n:,} finished match(es); "
          f"{len(done)} league-seasons done in total")
    return n


def step_dates(c: af.Client, ids: set[int]) -> pd.DataFrame:
    today = datetime.now(timezone.utc).date()
    rows = []
    for k in range(-DAYS_BACK, DAYS_AHEAD + 1):
        resp = (c.get("/fixtures", {"date": str(today + timedelta(days=k))}) or {}).get("response") or []
        rows.extend(r for r in parse.fixture_rows(resp) if r["league_id"] in ids)
    return pd.DataFrame(rows)


def step_results(fx: pd.DataFrame, dry: bool) -> int:
    if fx.empty:
        return 0
    fin = fx[fx["status"].isin(parse.FINISHED)]
    have = _results()
    if not have.empty:
        fin = fin[~fin["fixture_id"].isin(have["fixture_id"])]
    n = _append("scout_results", fin, "res", dry)
    print(f"[scout] results: {n:,} newly finished match(es)")
    return n


def _last_polls(now: pd.Timestamp) -> tuple[dict, dict]:
    """{league_id: last poll Timestamp}, {league_id: consecutive unchanged polls} from the RUN
    LEDGER (recorded sweep records), never from a file mtime. A league absent from the ledger is
    treated as never polled, so the first sweep after deploy polls everything once."""
    from src.monitoring import collection_policy as pol
    runs = pol.load_runs(now - pd.Timedelta(days=4))
    last, streak = {}, {}
    if runs.empty or "detail" not in runs.columns:
        return last, streak
    for r in runs[runs["collector"] == "scout_sweep"].itertuples():
        polled = r.detail.get("leagues_polled") if isinstance(r.detail, dict) else None
        for lid, n_changed in (polled or {}).items():
            lid = int(lid)
            last[lid] = r.ts
            streak[lid] = 0 if int(n_changed) else streak.get(lid, 0) + 1
    return last, streak


def step_odds(c: af.Client, watch: list[dict], fx: pd.DataFrame, dry: bool,
              summary: dict | None = None) -> pd.DataFrame:
    """Poll each watched league with an upcoming fixture WHEN IT IS DUE under the cost-aware
    policy (src/monitoring/collection_policy.py, E2 2026-10-26): every sweep inside T-6h of the
    league's next kickoff, every 3h to T-24h, 8h to T-72h, daily beyond — halved for registered
    experiments, doubled beyond T-24h when the last two polls changed nothing — and subject to
    the monthly budget guard, which sheds far-horizon leagues first and never sheds a
    near-close one."""
    from src.monitoring import collection_policy as pol
    now = int(time.time())
    now_ts = pd.Timestamp.now(tz="UTC")
    snap = cfg.utc_now_iso()
    up = fx[(fx["kickoff_ts"] > now) & ~fx["status"].isin(parse.FINISHED)] if not fx.empty else fx
    active = up.groupby("league_id")["season"].first().to_dict() if not up.empty else {}
    nearest = up.groupby("league_id")["kickoff_ts"].min().to_dict() if not up.empty else {}
    last, streak = _last_polls(now_ts)
    flags = pol.league_flags()
    guard = pol.Guard(now_ts)
    rows, polled_ids, skipped = [], [], {"not_due": 0, "budget": 0}
    for lg in watch:                                     # registry order = priority order
        lid = lg["id"]
        if lid not in active:
            continue
        mtk = (nearest[lid] - now) / 60.0
        fl = flags.get(int(lid), {})
        prio = pol.priority_class(mtk, experiment=fl.get("experiment", False),
                                  candidate=fl.get("candidate", False))
        ago = None if lid not in last else (now_ts - last[lid]).total_seconds() / 60.0
        if not pol.is_due(mtk, ago, prio, streak.get(lid, 0)):
            skipped["not_due"] += 1
            continue
        if not guard.allowed(prio):
            skipped["budget"] += 1
            continue
        before = c.calls
        resp = c.get_all_pages("/odds", {"league": lid, "season": active[lid]})
        guard.spend(c.calls - before)
        rows.extend(parse.odds_rows(resp, snap, now))
        polled_ids.append(lid)
    prev = _read_recent("scout_odds", QUOTE_LOOKBACK_DAYS)
    last_q = {}
    if not prev.empty:
        prev = prev.sort_values("snapshot_ts")
        last_q = {(r.fixture_id, r.market, r.selection, r.bookmaker): r.odds
                  for r in prev.drop_duplicates(["fixture_id", "market", "selection", "bookmaker"],
                                                keep="last").itertuples()}
    keep = parse.changed(rows, last_q)
    n = _append("scout_odds", keep, "odds", dry)
    changed_by_lg = pd.Series([r["league_id"] for r in keep]).value_counts().to_dict() if keep else {}
    if summary is not None:
        summary["leagues_polled"] = {str(x): int(changed_by_lg.get(x, 0)) for x in polled_ids}
        summary["leagues_skipped"] = skipped
        summary["league_seasons"] = {str(k): str(v) for k, v in active.items()}
        summary["budget_status"] = guard.b.get("status")
        summary["max_priority_polled"] = guard.max_priority
    print(f"[scout] odds: {len(active)} league(s) with fixtures, {len(polled_ids)} polled "
          f"({skipped['not_due']} not due, {skipped['budget']} shed by budget "
          f"{guard.b.get('status')}), {len(rows):,} quote(s) seen, {n:,} stored (change-log)")
    return pd.DataFrame(rows)


def step_freeze(quotes: pd.DataFrame, fx: pd.DataFrame, dry: bool) -> int:
    """Baseline model probabilities, written once per fixture at first sight of odds."""
    if quotes.empty or fx.empty:
        return 0
    frozen = store.read("scout_model")
    seen = set(frozen["fixture_id"]) if not frozen.empty else set()
    todo = fx[fx["fixture_id"].isin(set(quotes["fixture_id"])) & ~fx["fixture_id"].isin(seen)]
    if todo.empty:
        return 0
    res = _results()
    now = int(time.time())
    out, skipped = [], 0
    for lid, g in todo.groupby("league_id"):
        m = model.fit(res[res["league_id"] == lid], now) if not res.empty else None
        if m is None:
            skipped += len(g)                # history not collected yet: freeze on a later sweep
            continue
        for r in g.itertuples():
            p = model.predict(m, r.home_id, r.away_id)
            out.append({"fixture_id": int(r.fixture_id), "league_id": int(lid),
                        "kickoff_ts": int(r.kickoff_ts), "home_team": r.home_team,
                        "away_team": r.away_team, "home_id": r.home_id, "away_id": r.away_id,
                        "model_version": model.VERSION, "frozen_ts": cfg.utc_now_iso(),
                        "minutes_to_kickoff": round((r.kickoff_ts - now) / 60, 1),
                        # a team with under 5 matches in the window is rated mostly from the prior
                        "quality_flags": ("FEATURE_DEGRADED"
                                          if min(p["home_games"], p["away_games"]) < 5 else ""),
                        **p})
    n = _append("scout_model", out, "model", dry)
    print(f"[scout] model: {n:,} fixture(s) frozen, {skipped:,} waiting for league history")
    return n


# ── near-kickoff loop ─────────────────────────────────────────────────────────────────────────
NEAR_WINDOW_MIN = 120      # fixtures kicking off within this many minutes are watched (policy bands)
NEAR_SPACING_MIN = 5       # a pass every ~5 minutes; each fixture is CALLED at most once per band


def near_targets(window_min: float = NEAR_WINDOW_MIN, o: pd.DataFrame | None = None) -> pd.DataFrame:
    """Fixtures already priced by a sweep whose kickoff is within the window."""
    o = _read_recent("scout_odds", QUOTE_LOOKBACK_DAYS) if o is None else o
    if o.empty:
        return o
    now = time.time()
    f = o.drop_duplicates("fixture_id")[["fixture_id", "league_id", "kickoff_ts"]]
    return f[(f["kickoff_ts"] > now) & (f["kickoff_ts"] <= now + window_min * 60)]


def sampled_bands(o: pd.DataFrame) -> set:
    """(fixture_id, band) pairs already OBSERVED, from the stored rows' own minutes_to_kickoff.
    Inside 3h every observation is stored (parse.changed), so the store is the record — a run
    that restarts mid-window does not re-buy a band an earlier run already captured."""
    from src.monitoring import collection_policy as pol
    if o.empty or "minutes_to_kickoff" not in o.columns:
        return set()
    w = o[(o["minutes_to_kickoff"] > 0) & (o["minutes_to_kickoff"] <= NEAR_WINDOW_MIN)]
    out = set()
    for f, m in zip(w["fixture_id"], w["minutes_to_kickoff"]):
        b = pol.near_band(float(m))
        if b is not None:
            out.add((int(f), b))
    return out


def near_loop(c: af.Client, minutes: float, dry: bool) -> dict:
    """Sample closing prices as kickoffs approach, inside ONE long-running job.

    WHY A LOOP. GitHub does not fire crons on time (CLAUDE.md, measured 2026-09-10) — the scout's
    own first two slots were skipped outright. A job that starts whenever and then samples against
    REAL kickoff times is robust to that; a cron aimed at "T-10 minutes" is not.

    ONE SAMPLE PER CLOSE BAND (E2, 2026-10-26). Each watched fixture is called once in each of
    T-120..60m, T-60..30m, T-30..10m and T-10..1m (collection_policy.NEAR_BANDS) — the bands
    scheduler_health reports — instead of every 10 minutes through its last 75 minutes (~7 calls).
    API-Football's price is ~12 minutes old inside the final hour (measured 2026-10-08), so a
    second read inside one band mostly re-reads the same number. Fixtures of one league due in
    the same pass share one /odds?league&season&date call when that costs fewer calls.

    Every observation inside the final 3 hours is stored (parse.changed keeps them all), so the
    close is OBSERVED with a timestamp.
    """
    from src.monitoring import collection_policy as pol
    end = time.time() + minutes * 60
    passes = stored = 0
    calls0 = c.calls
    seen, league_calls, fixture_calls = set(), 0, 0
    # (fixture, band) pairs ATTEMPTED this run: a fixture whose call returns no price must not be
    # re-called every pass for the rest of its band.
    attempted: set = set()
    seasons = _league_seasons()
    while time.time() < end - 60:
        o = _read_recent("scout_odds", QUOTE_LOOKBACK_DAYS)
        T = near_targets(o=o)
        if T.empty:
            time.sleep(min(300, max(0, end - time.time() - 60)))
            continue
        now = int(time.time())
        T = T.assign(band=[pol.near_band((k - now) / 60.0) for k in T["kickoff_ts"]])
        done = sampled_bands(o) | attempted
        mask = [b is not None and (int(f), b) not in done for f, b in zip(T["fixture_id"], T["band"])]
        due = T[mask]
        attempted |= {(int(f), b) for f, b in zip(due["fixture_id"], due["band"])}
        if due.empty:
            time.sleep(min(NEAR_SPACING_MIN * 60, max(0, end - time.time() - 60)))
            continue
        snap = cfg.utc_now_iso()
        upcoming = o[o["kickoff_ts"] > now].drop_duplicates("fixture_id")
        rows = []
        for kind, _id, _cost in pol.plan_near_calls(due, _same_day_counts(upcoming, due)):
            if kind == "league" and str(_id) in seasons:
                days = sorted({datetime.fromtimestamp(int(k), timezone.utc).strftime("%Y-%m-%d")
                               for k in due[due["league_id"] == _id]["kickoff_ts"]})
                for day in days:
                    resp = c.get_all_pages("/odds", {"league": _id, "season": seasons[str(_id)],
                                                     "date": day})
                    rows.extend(parse.odds_rows(resp, snap, now))
                league_calls += 1
                seen |= set(due[due["league_id"] == _id]["fixture_id"].astype(int))
                continue
            fids = ([_id] if kind == "fixture"
                    else due[due["league_id"] == _id]["fixture_id"].astype(int).tolist())
            for fid in fids:
                body = c.get("/odds", {"fixture": fid}) or {}
                rows.extend(parse.odds_rows(body.get("response") or [], snap, now))
                seen.add(fid)
                fixture_calls += 1
        last = {}
        if not o.empty:
            prev = o.sort_values("snapshot_ts")
            last = {(r.fixture_id, r.market, r.selection, r.bookmaker): r.odds
                    for r in prev.drop_duplicates(["fixture_id", "market", "selection", "bookmaker"],
                                                  keep="last").itertuples()}
        stored += _append("scout_odds", parse.changed(rows, last), f"near{passes}", dry)
        passes += 1
        print(f"[scout near] pass {passes}: {len(due)} fixture-band(s) due of {len(T)} watched, "
              f"{len(rows)} quote(s), {stored} stored so far")
        time.sleep(min(NEAR_SPACING_MIN * 60, max(0, end - time.time() - 60)))
    return {"passes": passes, "fixtures_watched": len(seen), "rows_stored": stored,
            "api_calls": c.calls - calls0, "league_calls": league_calls,
            "fixture_calls": fixture_calls}


def _league_seasons() -> dict:
    """{league_id: season} as the latest recorded sweep saw it (the near loop has no fixtures
    call of its own, and /odds?league needs a season). Empty -> per-fixture calls only."""
    from src.monitoring import collection_policy as pol
    runs = pol.load_runs(pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=3))
    if runs.empty or "detail" not in runs.columns:
        return {}
    for r in runs[runs["collector"] == "scout_sweep"].iloc[::-1].itertuples():
        d = r.detail if isinstance(r.detail, dict) else {}
        if d.get("league_seasons"):
            return d["league_seasons"]
    return {}


def _same_day_counts(upcoming: pd.DataFrame, due: pd.DataFrame) -> dict:
    """{league_id: priced fixtures on the due fixtures' kickoff day(s)} — what a league+date
    call costs in pages."""
    if upcoming.empty:
        return {}
    def day(s):
        return pd.to_datetime(s, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    u = upcoming.assign(day=day(upcoming["kickoff_ts"]))
    d = due.assign(day=day(due["kickoff_ts"]))
    m = u.merge(d[["league_id", "day"]].drop_duplicates(), on=["league_id", "day"])
    return m.groupby("league_id")["fixture_id"].nunique().to_dict()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--history-budget", type=int, default=150,
                    help="max league-seasons of history fetched this run")
    ap.add_argument("--near-loop", type=float, default=0,
                    help="instead of a sweep, sample closing prices for N minutes")
    a = ap.parse_args()
    if a.near_loop:
        c = af.Client()
        summary = {"started": cfg.utc_now_iso(), "mode": "near-kickoff loop", "minutes": a.near_loop}
        try:
            summary.update(near_loop(c, a.near_loop, a.dry_run))
            summary["status"] = "ok"
        except af.QuotaFloor as e:
            summary["status"] = f"stopped at quota floor: {e}"
        summary.update({"quota_remaining": c.remaining, "finished": cfg.utc_now_iso()})
        if not a.dry_run:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "last_near_run.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        _ledger("scout_near", summary, c, a.dry_run)
        print(json.dumps(summary))
        return 0
    watch = reg.load()
    ids = {x["id"] for x in watch}
    c = af.Client()
    summary = {"started": cfg.utc_now_iso(), "leagues": len(watch)}
    try:
        fx = step_dates(c, ids)
        summary["fixtures_in_window"] = int(len(fx))
        summary["results_stored"] = step_results(fx, a.dry_run)
        quotes = step_odds(c, watch, fx, a.dry_run, summary)  # first among the bounded steps: unrecoverable
        summary["quotes_seen"] = int(len(quotes))
        summary["model_frozen"] = step_freeze(quotes, fx, a.dry_run)
        summary["history_rows"] = step_history(c, watch, a.history_budget, a.dry_run)
        summary["status"] = "ok"
    except af.QuotaFloor as e:
        summary["status"] = f"stopped at quota floor: {e}"
        print(f"[scout] {summary['status']}")
    summary.update({"api_calls": c.calls, "quota_remaining": c.remaining,
                    "finished": cfg.utc_now_iso()})
    if not a.dry_run:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "last_run.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    _ledger("scout_sweep", summary, c, a.dry_run)
    print(json.dumps(summary))
    return 0


def _ledger(collector: str, summary: dict, c: af.Client, dry: bool) -> None:
    """One run-ledger record (output/budget/runs) with the RECORDED call count. Never fatal:
    a ledger failure must not cost a run its prices."""
    try:
        from src.monitoring import collection_policy as pol
        keep = ("leagues_polled", "leagues_skipped", "league_seasons", "budget_status",
                "max_priority_polled", "passes", "fixtures_watched", "league_calls",
                "fixture_calls", "status")
        pol.record_run(collector, summary.get("started"), summary.get("finished"), c.calls,
                       quota_remaining=c.remaining,
                       detail={k: summary[k] for k in keep if k in summary}, dry=dry)
    except Exception as e:                                             # noqa: BLE001
        print(f"[scout] ledger record not written ({type(e).__name__}: {e})")


if __name__ == "__main__":
    raise SystemExit(main())
