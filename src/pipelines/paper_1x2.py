"""
Forward PAPER record for the 1X2 model.
=======================================
    python -m src.pipelines.paper_1x2 --mode log      # record today's picks + the price now
    python -m src.pipelines.paper_1x2 --mode settle   # grade what has finished
    python -m src.pipelines.paper_1x2 --mode all

WHY A FORWARD RECORD AND NOT ANOTHER BACKTEST

The offline evaluation says this model loses to the closing line (log-loss 1.0693 vs 1.0305 on
505 joined fixtures). That is evidence, but it is not the whole question, and the owner's
objection is a fair one: a backtest can be right in-sample and wrong in reality for reasons it
structurally cannot see -- which fixtures actually get priced and when, what odds were really
available, whether club-name resolution holds up live, whether the picks cluster in leagues where
prices are stale. A forward record is out-of-sample IN TIME, which no re-run of history is, and it
includes the operational reality a backtest silently assumes away.

It is PAPER. Nothing here notifies, tiers, or stakes. The model currently loses to the price, so
betting it would be paying to learn something this file learns for free.

RECORD EVERYTHING, DECIDE THE SELECTION RULE LATER

The obvious rule -- bet only the top few percent by model-vs-market edge -- was measured on the
505-fixture sample and it is the WORST slice available, monotonically:

    top 3%   n=12   hit  8.3%   ROI -73.3%        top 25%  n=100  hit 30.0%  ROI  -1.0%
    top 5%   n=20   hit 15.0%   ROI -48.2%        all      n=400  hit 33.8%  ROI  -8.6%
    top 10%  n=40   hit 20.0%   ROI -12.1%

Ranking by "the model disagrees with the price most" finds overpriced longshots by construction
(mean odds 3.81 in the top slice), which is the same longshot machine v11 was built to avoid. So
this logs EVERY fixture the model can price, with the price attached, and leaves the choice of
selection rule to be made from the record afterwards. Baking today's guess into the collection
would make the data unable to answer the question.

WHAT IS STORED, AND WHY EACH FIELD

    model p_home/p_draw/p_away  the opinion, at a stated time before kickoff
    market m_* and raw odds     what was actually available at that moment -- ROI needs the
                                price with the vig in it, not the de-vigged probability
    hours_to_kickoff            so "was it early or late" is answerable, not assumed
    closing_*                   filled at settlement, which is what CLV is measured against

APPEND-ONLY. A logged opinion is evidence precisely because it cannot be revised once the result
is known. Rows are matched on a stable id and an existing row is never overwritten by a later one.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.combo import dixon_coles as dc

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output"
MODEL_FILE = OUT / "model_1x2.json"
PAPER_FILE = OUT / "paper_1x2.csv"

CALC_VERSION = "1.0.0"
HORIZON_DAYS = 3


def _v9_root() -> Path | None:
    import os
    for r in (os.getenv("V9_LOCAL", ""), str(ROOT / "_v9"), str(ROOT.parent / "v9")):
        if r and (Path(r) / "output").exists():
            return Path(r)
    return None


def _row_id(fixture_key: str, match_date: str, home: str, away: str) -> str:
    """Stable per-fixture id. Uses fixture_key when present, else the name triple -- the same
    preference order the combo settler uses, for the same reason (invariant 11)."""
    base = fixture_key or f"{match_date}|{home}|{away}"
    return hashlib.sha1(str(base).encode("utf-8")).hexdigest()[:16]


def _market_snapshots() -> pd.DataFrame:
    """Every h2h snapshot from v9's sharp tracker, one row per (fixture, snapshot).

    Not just the closing price: logging needs the price AS IT WAS when the opinion was formed,
    and settlement needs the last one before kickoff. Both come from the same source so they
    cannot disagree about which fixture is which.
    """
    v9 = _v9_root()
    if v9 is None:
        return pd.DataFrame()
    rows = []
    for f in sorted(glob.glob(str(v9 / "output" / "sharp_history" / "*.json"))):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for v in (d.values() if isinstance(d, dict) else d):
            for s in (v if isinstance(v, list) else [v]):
                if not isinstance(s, dict) or s.get("market") != "h2h":
                    continue
                for snap in (s.get("snapshots") or []):
                    o = snap.get("odds") or {}
                    oh, od, oa = o.get("odds_home"), o.get("odds_draw"), o.get("odds_away")
                    if not (oh and od and oa):
                        continue
                    rows.append({
                        "league": s.get("league"), "home_team": s.get("home"),
                        "away_team": s.get("away"),
                        "kickoff": pd.to_datetime(str(s.get("date")), errors="coerce"),
                        "snapshot_at": pd.to_datetime(str(snap.get("at")), errors="coerce"),
                        "o_home": float(oh), "o_draw": float(od), "o_away": float(oa),
                    })
    m = pd.DataFrame(rows)
    if m.empty:
        return m
    inv = 1.0 / m[["o_home", "o_draw", "o_away"]].to_numpy()
    tot = inv.sum(axis=1, keepdims=True)
    m[["m_home", "m_draw", "m_away"]] = inv / tot
    m["overround"] = tot.ravel()
    return m


def _models() -> dict:
    if not MODEL_FILE.exists():
        print(f"[paper1x2] {MODEL_FILE.name} not found — run train_1x2 first")
        return {}
    try:
        return (json.loads(MODEL_FILE.read_text(encoding="utf-8")) or {}).get("leagues", {}) or {}
    except Exception as e:                                       # noqa: BLE001
        print(f"[paper1x2] could not read the model: {type(e).__name__}: {e}")
        return {}


def log_picks(now: dt.datetime | None = None) -> pd.DataFrame:
    """One row per upcoming fixture the model can price, with the price available right now."""
    from src.data import season_store as store
    now = now or dt.datetime.now(dt.timezone.utc)
    models = _models()
    if not models:
        return pd.DataFrame()

    fx = store.read("fixtures")
    if fx.empty:
        print("[paper1x2] no fixtures in the store")
        return pd.DataFrame()
    fx = fx.copy()
    fx["_ko"] = pd.to_datetime(fx.get("kickoff_utc"), errors="coerce", utc=True)
    fx = fx.dropna(subset=["_ko"]).drop_duplicates("fixture_key", keep="last")
    fx = fx[(fx["_ko"] > now) & (fx["_ko"] <= now + dt.timedelta(days=HORIZON_DAYS))]
    print(f"[paper1x2] {len(fx)} upcoming fixture(s) within {HORIZON_DAYS}d")
    if fx.empty:
        return pd.DataFrame()

    mkt = _market_snapshots()
    latest = pd.DataFrame()
    if not mkt.empty:
        mk = mkt.dropna(subset=["snapshot_at"]).sort_values("snapshot_at")
        latest = mk.drop_duplicates(subset=["league", "home_team", "away_team"], keep="last")

    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows, no_model, no_rating = [], 0, 0
    for _, f in fx.iterrows():
        m = models.get(f.get("league"))
        if not m:
            no_model += 1
            continue
        pr = dc.predict(m, str(f.get("home_team")), str(f.get("away_team")))
        if not pr:
            no_rating += 1                      # team unseen in training — no honest rating
            continue
        r = {
            "row_id": _row_id(str(f.get("fixture_key", "")), str(f.get("match_date", "")),
                              str(f.get("home_team")), str(f.get("away_team"))),
            "logged_at": stamp, "fixture_key": f.get("fixture_key"), "league": f.get("league"),
            "match_date": f.get("match_date"),
            "kickoff_utc": f["_ko"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "home_team": f.get("home_team"), "away_team": f.get("away_team"),
            "hours_to_kickoff": round((f["_ko"] - now).total_seconds() / 3600.0, 2),
            "p_home": round(pr["p_home"], 4), "p_draw": round(pr["p_draw"], 4),
            "p_away": round(pr["p_away"], 4),
            "calc_version": CALC_VERSION,
        }
        # The price as it stands now. Absent for most fixtures — the sharp tracker covers 19
        # leagues — and that is recorded as missing rather than guessed, because a row with no
        # price can still measure calibration, just not ROI.
        if len(latest):
            hit = latest[(latest["home_team"] == f.get("home_team"))
                         & (latest["away_team"] == f.get("away_team"))]
            if len(hit):
                h = hit.iloc[-1]
                r.update({"o_home": h["o_home"], "o_draw": h["o_draw"], "o_away": h["o_away"],
                          "m_home": round(float(h["m_home"]), 4),
                          "m_draw": round(float(h["m_draw"]), 4),
                          "m_away": round(float(h["m_away"]), 4),
                          "overround": round(float(h["overround"]), 4),
                          "price_at": str(h["snapshot_at"])[:19]})
        rows.append(r)

    d = pd.DataFrame(rows)
    priced = int(d["o_home"].notna().sum()) if "o_home" in d.columns else 0
    print(f"[paper1x2] logged {len(d)} pick(s), {priced} with a market price "
          f"(skipped: no league model {no_model}, unrated team {no_rating})")
    return d


def settle(d: pd.DataFrame | None = None, now: dt.datetime | None = None) -> pd.DataFrame:
    """Grade logged picks whose fixture has finished, and attach the CLOSING price.

    Takes the frame directly so a log+settle pass can grade what it just produced WITHOUT writing
    an intermediate file — the first version round-tripped through disk, which quietly made
    --dry-run write.
    """
    from src.data import season_store as store
    now = now or dt.datetime.now(dt.timezone.utc)
    if d is None:
        if not PAPER_FILE.exists():
            print("[paper1x2] nothing logged yet")
            return pd.DataFrame()
        d = pd.read_csv(PAPER_FILE, low_memory=False)
    if d.empty:
        return d

    need = {"home_team", "away_team", "home_goals", "away_goals", "match_date"}
    res = [t for t in (store.read("team_match_stats"), store.read("settlements_backfill"))
           if not t.empty and need.issubset(t.columns)]
    if not res:
        print("[paper1x2] no scoreline source — cannot settle")
        return d
    r = pd.concat(res, ignore_index=True)
    r["_k"] = (pd.to_datetime(r["match_date"], errors="coerce").dt.strftime("%Y-%m-%d")
               + "|" + r["home_team"].astype(str) + "|" + r["away_team"].astype(str))
    by_key = {}
    if "fixture_key" in r.columns:
        by_key = {str(k): v for k, v in
                  r.dropna(subset=["fixture_key"]).drop_duplicates("fixture_key")
                   .set_index("fixture_key")[["home_goals", "away_goals"]].iterrows()}
    by_name = r.drop_duplicates("_k").set_index("_k")[["home_goals", "away_goals"]]

    mkt = _market_snapshots()
    closing = pd.DataFrame()
    if not mkt.empty:
        mk = mkt.dropna(subset=["snapshot_at", "kickoff"])
        mk = mk[mk["snapshot_at"] <= mk["kickoff"]].sort_values("snapshot_at")
        closing = mk.drop_duplicates(subset=["home_team", "away_team"], keep="last")

    out = d.copy()
    for c in ("result", "settled_at", "c_home", "c_draw", "c_away"):
        if c not in out.columns:
            out[c] = pd.NA

    graded = 0
    for i, row in out.iterrows():
        if pd.notna(row.get("result")):
            continue                                   # already graded — never re-decide
        fk = str(row.get("fixture_key") or "")
        rec = by_key.get(fk)
        if rec is None:
            k = f'{str(row.get("match_date"))[:10]}|{row.get("home_team")}|{row.get("away_team")}'
            if k in by_name.index:
                rec = by_name.loc[k]
        if rec is None:
            continue
        hg, ag = rec["home_goals"], rec["away_goals"]
        if pd.isna(hg) or pd.isna(ag):
            continue
        out.at[i, "result"] = 0 if hg > ag else (1 if hg == ag else 2)
        out.at[i, "settled_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if len(closing):
            h = closing[(closing["home_team"] == row["home_team"])
                        & (closing["away_team"] == row["away_team"])]
            if len(h):
                out.at[i, "c_home"] = float(h.iloc[-1]["o_home"])
                out.at[i, "c_draw"] = float(h.iloc[-1]["o_draw"])
                out.at[i, "c_away"] = float(h.iloc[-1]["o_away"])
        graded += 1
    print(f"[paper1x2] graded {graded} newly-finished pick(s)")
    return out


def scoreboard(d: pd.DataFrame) -> dict:
    """The record so far. Reported over EVERY logged pick, with slices shown separately."""
    if d is None or d.empty or "result" not in d.columns:
        return {"logged": 0 if d is None else len(d), "settled": 0}
    s = d[pd.to_numeric(d["result"], errors="coerce").notna()].copy()
    if s.empty:
        return {"logged": len(d), "settled": 0}
    P = s[["p_home", "p_draw", "p_away"]].to_numpy(dtype=float)
    Y = pd.to_numeric(s["result"], errors="coerce").to_numpy(dtype=int)
    rep = {"logged": len(d), "settled": len(s),
           "model_logloss": round(dc.multiclass_logloss(P, Y), 4),
           "accuracy": round(float((P.argmax(1) == Y).mean()), 4)}
    if {"m_home", "m_draw", "m_away"}.issubset(s.columns):
        w = s.dropna(subset=["m_home", "m_draw", "m_away"])
        if len(w) >= 10:
            M = w[["m_home", "m_draw", "m_away"]].to_numpy(dtype=float)
            Yw = pd.to_numeric(w["result"], errors="coerce").to_numpy(dtype=int)
            Pw = w[["p_home", "p_draw", "p_away"]].to_numpy(dtype=float)
            rep["vs_market_n"] = len(w)
            rep["model_logloss_priced"] = round(dc.multiclass_logloss(Pw, Yw), 4)
            rep["market_logloss"] = round(dc.multiclass_logloss(M, Yw), 4)
            rep["model_beats_market"] = bool(rep["model_logloss_priced"] < rep["market_logloss"])
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("log", "settle", "all"), default="all")
    ap.add_argument("--dry-run", action="store_true", help="compute and report, write nothing")
    args = ap.parse_args()

    existing = (pd.read_csv(PAPER_FILE, low_memory=False)
                if PAPER_FILE.exists() else pd.DataFrame())
    d = existing

    if args.mode in ("log", "all"):
        fresh = log_picks()
        if not fresh.empty:
            if existing.empty:
                d = fresh
            else:
                # APPEND-ONLY: an opinion already on the record is never replaced by a later one,
                # or the file stops being evidence of what was believed beforehand.
                new = fresh[~fresh["row_id"].isin(set(existing["row_id"]))]
                print(f"[paper1x2] {len(new)} new, {len(fresh) - len(new)} already on the record")
                d = pd.concat([existing, new], ignore_index=True)

    if args.mode in ("settle", "all"):
        if not d.empty:
            before = int(pd.to_numeric(d.get("result"), errors="coerce").notna().sum()) \
                if "result" in d.columns else 0
            d = settle(None if args.mode == "settle" else d)
            after = int(pd.to_numeric(d.get("result"), errors="coerce").notna().sum()) \
                if "result" in d.columns else 0
            if after < before:
                raise RuntimeError(f"settlement lost graded rows ({before} -> {after})")

    print(f"[paper1x2] scoreboard: {scoreboard(d)}")
    if not args.dry_run and not d.empty:
        OUT.mkdir(exist_ok=True)
        d.to_csv(PAPER_FILE, index=False, encoding="utf-8")
        print(f"[paper1x2] wrote {PAPER_FILE.name} ({len(d):,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
