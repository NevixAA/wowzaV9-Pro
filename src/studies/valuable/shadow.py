"""Prospective LOW-EDGE SHADOW: every pre-kickoff candidate v9 sees, including below the VALUABLE floor.

    python -m src.studies.valuable.shadow --v9 <wowza-betting clone>     # capture + settle, idempotent

Owner brief 2026-10-20 sec. 7: "capture ALL pre-kickoff candidate predictions, including below the current
VALUABLE floor. Do NOT notify. Do NOT bet. Never retroactively invent a snapshot."

HOW IT CANNOT INVENT A SNAPSHOT. The source is v9's own committed output/predictions.csv: every row here
names the v9 commit (snapshot_sha) it was read from, and a candidate enters at the FIRST committed snapshot
that priced it, strictly before kickoff. Nothing is computed from data the run did not have. The capture
starts at REGISTERED_START; anything earlier is the historical snapshot study, never this file.

Rows: one per fixture x market x side at first sight with raw_edge >= 0 (OU25 Over/Under, BTTS Yes/No,
O1.5 Over, O3.5 Over). Settled later from Pro team_match_stats via v9's league-scoped name resolver; the
closing price is the last committed snapshot before kickoff (CLV vs that, same source). Read-only towards
v9: no tip, no notification, no stake, no production change.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

REGISTERED_START = "2026-10-21T00:00:00Z"
CLOSE_MAX_MIN = 30.0
OUT = cfg.BASE_DIR / "output" / "valuable_shadow"
FILE = OUT / "valuable_shadow.csv"
STATE = OUT / "valuable_shadow_state.json"
SIDE_OVERROUND = 1.08                       # production's fixed side-market vig (pipeline.py), for production_tier only
COLS = ["generated_at", "kickoff", "fixture_id", "league", "home_team", "away_team", "model_type", "market", "side",
        "model_probability", "odds", "opposite_side_odds", "bookmaker_count", "raw_implied_probability",
        "fair_market_probability", "raw_edge", "fair_edge", "FAIR_EDGE_AVAILABLE", "production_tier",
        "production_thresholds", "tier_rule_source", "would_have_been_valuable", "would_have_been_marksman",
        "would_have_been_sniper", "result", "flat_pnl", "closing_odds", "clv", "close_minutes_to_kickoff",
        "close_status", "model_version", "retrain_batch",
        "snapshot_sha"]
KEEP = ["league", "date", "kickoff_utc", "home_team", "away_team", "model_type", "model_version", "generated_at",
        "p_over25", "odds_over25", "odds_under25", "tier_over", "tier_under", "p_btts", "odds_btts", "odds_btts_no",
        "p_over15", "odds_over15", "p_over35", "odds_over35"]


def _git(v9: str, *a) -> bytes:
    return subprocess.run(["git", "-C", v9, *a], capture_output=True, check=True).stdout


def _fid(league, date, home, away) -> str:
    return hashlib.sha1(f"{league}|{str(date)[:10]}|{home}|{away}".encode()).hexdigest()[:16]


def _snapshots(v9: str, since: str) -> pd.DataFrame:
    log = _git(v9, "log", f"--since={since}", "--format=%H %cI", "--", "output/predictions.csv").decode().split("\n")
    out = []
    for line in filter(None, log):
        sha, ts = line.split(" ", 1)
        try:
            d = pd.read_csv(io.BytesIO(_git(v9, "show", f"{sha}:output/predictions.csv")), low_memory=False,
                            usecols=lambda c: c in KEEP)
        except Exception:                                              # noqa: BLE001 - unreadable snapshot skipped, never guessed
            continue
        d["snapshot_sha"], d["committed_at"] = sha[:10], ts
        out.append(d)
    if not out:
        return pd.DataFrame()
    s = pd.concat(out, ignore_index=True)
    s["committed_at"] = pd.to_datetime(s["committed_at"], utc=True)
    s["gen"] = pd.to_datetime(s.get("generated_at"), utc=True, errors="coerce").fillna(s["committed_at"])
    s["kick"] = pd.to_datetime(s["kickoff_utc"], utc=True, errors="coerce")
    return s[s["kick"].notna() & (s["gen"] < s["kick"])].sort_values("gen")


def _gates(v9: str) -> dict:
    code = ("import json,sys; sys.path.insert(0,'.'); from src.gate_resolver import all_gates;"
            "print(json.dumps({g.league: g.as_dict() for g in all_gates(('over25',))}))")
    env = {**__import__("os").environ, "LEAGUE_SNIPER_CAP": "0.12", "MARKSMAN_THRESHOLD": "0.08", "VALUABLE_THRESHOLD": "0.03"}
    try:
        r = subprocess.run([__import__("sys").executable, "-c", code], cwd=v9, capture_output=True, text=True, env=env)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:                                                  # noqa: BLE001
        return {}


def candidates(s: pd.DataFrame, gates: dict) -> pd.DataFrame:
    rows = []

    def add(g, market, side, p, odds, opp, prod_tier, floors, src):
        imp = 1 / odds
        fair = (imp / (imp + 1 / opp)) if opp is not None else pd.Series(np.nan, index=g.index)
        if market == "over25":
            raw = p - imp
        else:
            raw = p - imp / SIDE_OVERROUND
        f = pd.DataFrame({"generated_at": g["gen"], "kickoff": g["kick"], "league": g["league"], "home_team": g["home_team"],
                          "away_team": g["away_team"], "model_type": g["model_type"], "market": market, "side": side,
                          "model_probability": p, "odds": odds, "opposite_side_odds": opp if opp is not None else np.nan,
                          "bookmaker_count": np.nan, "raw_implied_probability": imp, "fair_market_probability": fair,
                          "raw_edge": raw * 100, "fair_edge": (p - fair) * 100,
                          "FAIR_EDGE_AVAILABLE": "YES" if opp is not None else "NO",
                          "production_tier": prod_tier, "model_version": g.get("model_version"),
                          "snapshot_sha": g["snapshot_sha"]})
        f["production_thresholds"] = floors
        f["tier_rule_source"] = src
        rows.append(f)

    ou = s.dropna(subset=["p_over25", "odds_over25", "odds_under25"])
    fl = ou["league"].map(lambda l: json.dumps({k: gates.get(l, {}).get(k) for k in ("valuable", "marksman", "sniper")}))
    srcs = ou["league"].map(lambda l: gates.get(l, {}).get("sniper_source", "gate_resolver unavailable"))
    add(ou, "over25", "OVER", ou["p_over25"], ou["odds_over25"], ou["odds_under25"], ou.get("tier_over"), fl, srcs)
    add(ou, "over25", "UNDER", 1 - ou["p_over25"], ou["odds_under25"], ou["odds_over25"], ou.get("tier_under"), fl, srcs)
    side_src = "pipeline.py side-market rule 0.04/0.08/0.10 on p-(1/odds)/1.08 (approved league rules may differ)"
    side_fl = json.dumps({"valuable": 0.04, "marksman": 0.08, "sniper": 0.10})
    bt = s.dropna(subset=["p_btts", "odds_btts"])
    no = bt["odds_btts_no"].where(bt["odds_btts_no"] > 1) if "odds_btts_no" in bt else None
    add(bt, "btts", "YES", bt["p_btts"], bt["odds_btts"], no, None, side_fl, side_src)
    btn = bt.dropna(subset=["odds_btts_no"])
    add(btn, "btts", "NO", 1 - btn["p_btts"], btn["odds_btts_no"], btn["odds_btts"], None, side_fl,
        "never a production market (Yes only) - shadow only")
    for m in ("over15", "over35"):
        x = s.dropna(subset=[f"p_{m}", f"odds_{m}"])
        add(x, m, "OVER", x[f"p_{m}"], x[f"odds_{m}"], None, None, side_fl, side_src)
    c = pd.concat(rows, ignore_index=True)
    c = c[c["odds"] > 1]
    c["fixture_id"] = [_fid(*t) for t in zip(c.league, c.kickoff.dt.date, c.home_team, c.away_team)]
    # production tier for side markets: the production rule on the production edge
    side = c["market"] != "over25"
    e = c["raw_edge"] / 100
    c.loc[side, "production_tier"] = np.select([e >= 0.10, e >= 0.08, e >= 0.04], ["SNIPER", "MARKSMAN", "VALUABLE"], "AVOID")[side.values]
    th = c["production_thresholds"].map(json.loads)
    for t in ("valuable", "marksman", "sniper"):
        c[f"would_have_been_{t}"] = [bool(x.get(t) is not None and r / 100 >= x[t]) for x, r in zip(th, c["raw_edge"])]
    c["retrain_batch"] = np.nan                                           # not exposed in predictions.csv
    return c


def capture(v9: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    s = _snapshots(v9, REGISTERED_START)
    old = pd.read_csv(FILE, dtype={"fixture_id": str}) if FILE.exists() else pd.DataFrame(columns=COLS)
    if s.empty:
        return {"new_rows": 0, "rows": len(old), "note": "no committed snapshot since the registered start yet"}
    c = candidates(s, _gates(v9))
    c = c[c["generated_at"] >= pd.Timestamp(REGISTERED_START)]
    c = c[c["raw_edge"] >= 0].sort_values("generated_at")
    first = c.drop_duplicates(["fixture_id", "market", "side"], keep="first")      # FIRST SIGHT
    have = set(zip(old.fixture_id.astype(str), old.market, old.side)) if len(old) else set()
    new = first[[k not in have for k in zip(first.fixture_id, first.market, first.side)]]
    # closing price = last committed snapshot before kickoff (same source); refreshed for unsettled rows
    lastrow = c.drop_duplicates(["fixture_id", "market", "side"], keep="last").set_index(["fixture_id", "market", "side"])
    last = lastrow["odds"]
    # CERTIFIED CLOSE ONLY (owner rule 2026-10-22, same as v9 src/shadow_settlement.py): the last committed
    # snapshot counts as the close only if it was taken within CLOSE_MAX_MIN of kickoff; otherwise the
    # price is kept but CLV is NaN with close_status STALE_CLOSE_GT_30MIN.
    gap = ((pd.to_datetime(lastrow["kickoff"], utc=True) - pd.to_datetime(lastrow["generated_at"], utc=True))
           .dt.total_seconds() / 60).round(1)
    allr = pd.concat([old, new.reindex(columns=COLS)], ignore_index=True)
    k = list(zip(allr.fixture_id.astype(str), allr.market, allr.side))
    allr["closing_odds"] = [last.get(x, co) for x, co in zip(k, allr["closing_odds"])]
    allr["close_minutes_to_kickoff"] = [gap.get(x, m) for x, m in zip(k, allr.get("close_minutes_to_kickoff", pd.Series([None] * len(allr))))]
    mins = pd.to_numeric(allr["close_minutes_to_kickoff"], errors="coerce")
    allr["close_status"] = np.where(mins.isna(), "NO_CLOSE", np.where(mins <= CLOSE_MAX_MIN, "OK", "STALE_CLOSE_GT_30MIN"))
    allr["clv"] = np.where(allr["close_status"] == "OK",
                           (pd.to_numeric(allr["odds"]) / pd.to_numeric(allr["closing_odds"]) - 1) * 100, np.nan)
    allr = settle(allr, v9)
    allr[COLS].to_csv(FILE, index=False)
    st = {"registered_start": REGISTERED_START, "rows": int(len(allr)), "new_rows": int(len(new)),
          "settled": int(allr["result"].isin(["WIN", "LOSS"]).sum()),
          "last_snapshot": str(s["gen"].max()), "by_market": allr.groupby("market").size().to_dict(),
          "below_valuable_floor_rows": int((~allr["would_have_been_valuable"].astype(bool)).sum())}
    STATE.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")
    return st


def settle(r: pd.DataFrame, v9: str) -> pd.DataFrame:
    import glob
    spec = importlib.util.spec_from_file_location("v9_team_names", Path(v9) / "src" / "team_names.py")
    tn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tn)
    fs = sorted(glob.glob(str(cfg.BASE_DIR / "data" / "season_2026_27" / "team_match_stats" / "**" / "*.parquet"), recursive=True))
    if not fs or not len(r):
        return r
    res = pd.concat([pd.read_parquet(f, columns=["league", "match_date", "home_team", "away_team", "home_goals", "away_goals"])
                     for f in fs], ignore_index=True).dropna(subset=["home_goals", "away_goals"])
    res["md"] = pd.to_datetime(res["match_date"]).dt.normalize()
    r = r.copy()
    todo = r["result"].isna() | ~r["result"].isin(["WIN", "LOSS"])
    for lg, g in r[todo].groupby("league"):
        rl = res[res.league == lg]
        names = sorted(set(rl.home_team) | set(rl.away_team))
        for (h0, a0, ko), idx in g.groupby(["home_team", "away_team", "kickoff"]).groups.items():
            h, a = tn.resolve(h0, names), tn.resolve(a0, names)
            if not h or not a:
                continue
            md = pd.Timestamp(ko).tz_localize(None).normalize() if pd.Timestamp(ko).tzinfo else pd.Timestamp(ko).normalize()
            m = rl[(rl.home_team == h) & (rl.away_team == a) & ((rl.md - md).abs() <= pd.Timedelta(days=1))]
            if len(m) != 1:
                continue
            hg, ag = float(m.home_goals.iloc[0]), float(m.away_goals.iloc[0])
            for i in idx:
                mk, sd = r.at[i, "market"], r.at[i, "side"]
                hit = {"over25": hg + ag > 2.5, "over15": hg + ag > 1.5, "over35": hg + ag > 3.5,
                       "btts": hg > 0 and ag > 0}[mk]
                won = hit if sd in ("OVER", "YES") else not hit
                r.at[i, "result"] = "WIN" if won else "LOSS"
                r.at[i, "flat_pnl"] = round(float(r.at[i, "odds"]) - 1, 4) if won else -1.0
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--v9", required=True)
    print(json.dumps(capture(ap.parse_args().v9), indent=1, default=str))
