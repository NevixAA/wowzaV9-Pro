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


def step_odds(c: af.Client, watch: list[dict], fx: pd.DataFrame, dry: bool) -> pd.DataFrame:
    now = int(time.time())
    snap = cfg.utc_now_iso()
    up = fx[(fx["kickoff_ts"] > now) & ~fx["status"].isin(parse.FINISHED)] if not fx.empty else fx
    active = up.groupby("league_id")["season"].first().to_dict() if not up.empty else {}
    rows = []
    for lg in watch:                                     # registry order = priority order
        if lg["id"] not in active:
            continue
        resp = c.get_all_pages("/odds", {"league": lg["id"], "season": active[lg["id"]]})
        rows.extend(parse.odds_rows(resp, snap, now))
    prev = _read_recent("scout_odds", QUOTE_LOOKBACK_DAYS)
    last = {}
    if not prev.empty:
        prev = prev.sort_values("snapshot_ts")
        last = {(r.fixture_id, r.market, r.selection, r.bookmaker): r.odds
                for r in prev.drop_duplicates(["fixture_id", "market", "selection", "bookmaker"],
                                              keep="last").itertuples()}
    keep = parse.changed(rows, last)
    n = _append("scout_odds", keep, "odds", dry)
    print(f"[scout] odds: {len(active)} league(s) with fixtures, {len(rows):,} quote(s) seen, "
          f"{n:,} stored (change-log)")
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--history-budget", type=int, default=150,
                    help="max league-seasons of history fetched this run")
    a = ap.parse_args()
    watch = reg.load()
    ids = {x["id"] for x in watch}
    c = af.Client()
    summary = {"started": cfg.utc_now_iso(), "leagues": len(watch)}
    try:
        fx = step_dates(c, ids)
        summary["fixtures_in_window"] = int(len(fx))
        summary["results_stored"] = step_results(fx, a.dry_run)
        quotes = step_odds(c, watch, fx, a.dry_run)       # first among the bounded steps: unrecoverable
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
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
