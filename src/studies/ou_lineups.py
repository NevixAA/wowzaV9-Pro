"""LINEUPS as O/U model inputs (owner 2026-10-19: "each data the model can have"). Research only.

    python -m src.studies.ou_lineups features   # as-of lineup strength per side -> lineup_features.parquet
    python -m src.studies.ou_lineups report     # after the walk-forward probe has run

Source: API-Football /fixtures/lineups for 32,831 finished fixtures since 2023-07 (cached in
experiments/ou_info_inputs_2026_10/lineups/), matched to v9's own training rows through the fixture map
the weather study built. A lineup is published ~1 hour before kickoff and never revised, so it carries no
hindsight — but it is a LATE input: v9's tips are frozen days earlier, so a positive result could only be
used by a pre-kickoff re-check (a v9 change that would need owner approval).

Per side, every number uses ONLY the team's matches strictly BEFORE this fixture (player_history):
  xi_ga_share       share of the team's goals+assists over its last 10 matches produced by today's XI
  xi_minutes_share  sum over today's XI of each player's share of team minutes (~11 = the usual XI)
  missing_reg_ga    goals+assists share of the 5 most-used players (last 10) who are NOT starting
  rotation          starters today who did not start the team's previous match
Missing data stays NaN (no lineup, team not in player_history, no prior matches) — never 0.
"""
from __future__ import annotations

import bisect
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

EXP = cfg.BASE_DIR / "experiments" / "ou_info_inputs_2026_10"
LINEUPS = EXP / "lineups"
LOOKBACK = 10
COLS = ["xi_ga_share", "xi_minutes_share", "missing_reg_ga", "rotation"]


def _team_history():
    ph = pd.read_parquet(Path(cfg.V9_LOCAL) / "player_history.parquet",
                         columns=["fixture_id", "player_id", "date", "team", "minutes", "goals", "assists", "started"])
    ph["date"] = pd.to_datetime(ph["date"], errors="coerce", utc=True).dt.tz_localize(None)
    ph = ph.dropna(subset=["date", "player_id", "fixture_id"])
    ph["ga"] = ph["goals"].fillna(0) + ph["assists"].fillna(0)
    ph["minutes"] = ph["minutes"].fillna(0)
    hist = {}
    for team, g in ph.groupby("team"):
        fx = []
        for (fid, d), x in g.groupby(["fixture_id", "date"]):
            fx.append((d, int(fid), dict(zip(x["player_id"].astype(int), zip(x["minutes"], x["ga"]))),
                       set(x.loc[x["started"].fillna(False).astype(bool), "player_id"].astype(int)),
                       float(x["ga"].sum()), float(x["minutes"].sum())))
        fx.sort(key=lambda r: r[0])
        hist[team] = (fx, [r[0] for r in fx])
    return hist


def _side(hist, team: str, date, xi: set, fixture_id: int | None = None) -> dict:
    h = hist.get(team)
    if h is None or not xi:
        return {c: np.nan for c in COLS}
    fx, dates = h
    # LEAK FIX 2026-10-20: player_history dates are MIDNIGHT, kickoffs are later the same day, so
    # bisect on the kickoff timestamp counted THIS match as history in 98.9% of fixtures - its own
    # goals fed xi_ga_share. Cut on the calendar day, and drop the fixture by id as well (a late
    # kickoff can sit on the next UTC day).
    i = bisect.bisect_left(dates, pd.Timestamp(date).normalize())
    prev = [r for r in fx[:i] if r[1] != fixture_id][-LOOKBACK:]
    if not prev:
        return {c: np.nan for c in COLS}
    mins, ga = defaultdict(float), defaultdict(float)
    for _, _, players, _, _, _ in prev:
        for pid, (m, g) in players.items():
            mins[pid] += m
            ga[pid] += g
    team_min = sum(r[5] for r in prev) or 1.0
    team_ga = sum(ga.values()) or 1.0
    regulars = [p for p, _ in sorted(mins.items(), key=lambda kv: -kv[1])[:5]]
    return {"xi_ga_share": sum(ga[p] for p in xi) / team_ga,
            "xi_minutes_share": sum(mins[p] for p in xi) / team_min * 11,
            "missing_reg_ga": sum(ga[p] for p in regulars if p not in xi) / team_ga,
            "rotation": float(len(xi - prev[-1][3])) if prev[-1][3] else np.nan}


def features() -> dict:
    wf = pd.read_parquet(EXP / "weather_features.parquet",
                         columns=["league", "date", "home_team", "away_team", "af_fixture_id"])
    wf = wf.dropna(subset=["af_fixture_id"]).drop_duplicates(["league", "date", "home_team", "away_team"])
    afx = pd.read_parquet(EXP / "af_fixtures.parquet", columns=["af_fixture_id", "home_id", "away_id",
                                                               "home_team", "away_team", "fixture_ts"])
    afx = afx.rename(columns={"home_team": "af_home", "away_team": "af_away"})
    m = wf.merge(afx, on="af_fixture_id", how="left")
    hist = _team_history()
    rows, no_lineup = [], 0
    for r in m.itertuples(index=False):
        p = LINEUPS / f"{int(r.af_fixture_id)}.json"
        lu = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        xi = {}
        for t in lu or []:
            tid = (t.get("team") or {}).get("id")
            xi[tid] = {int(x["player"]["id"]) for x in t.get("startXI") or [] if (x.get("player") or {}).get("id")}
        if not xi:
            no_lineup += 1
        d = pd.Timestamp(r.fixture_ts).tz_convert(None) if pd.notna(r.fixture_ts) else pd.Timestamp(r.date)
        fid = int(r.af_fixture_id)
        h = _side(hist, r.af_home, d, xi.get(r.home_id, set()), fid)
        a = _side(hist, r.af_away, d, xi.get(r.away_id, set()), fid)
        rec = {"league": r.league, "date": r.date, "home_team": r.home_team, "away_team": r.away_team}
        rec.update({f"home_{k}": v for k, v in h.items()})
        rec.update({f"away_{k}": v for k, v in a.items()})
        rows.append(rec)
    out = pd.DataFrame(rows)
    out["total_xi_ga_share"] = out["home_xi_ga_share"] + out["away_xi_ga_share"]
    out["total_missing_reg_ga"] = out["home_missing_reg_ga"] + out["away_missing_reg_ga"]
    out.to_parquet(EXP / "lineup_features.parquet", index=False)
    cov = out.groupby("league")["home_xi_ga_share"].apply(lambda s: round(float(s.notna().mean()), 3))
    res = {"rows": len(out), "no_lineup": no_lineup,
           "with_features": int(out["home_xi_ga_share"].notna().sum()),
           "coverage_by_league": cov.to_dict(),
           "ranges": {c: [round(float(out[c].quantile(q)), 3) for q in (0.05, 0.5, 0.95)]
                      for c in out.columns if c.startswith(("home_", "total_")) and c != "home_team"}}
    (EXP / "lineup_audit.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


if __name__ == "__main__":
    print(json.dumps({"features": features}[sys.argv[1] if len(sys.argv) > 1 else "features"](), indent=1, default=str))
