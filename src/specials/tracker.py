"""
Specials tracker - the live, forward RESEARCH record. No tips, no stakes, no messages.

    python -m src.specials.tracker --mode log|settle|evaluate|all [--dry-run]

WHAT IS RECORDED. For EVERY upcoming fixture (within HORIZON_DAYS) the score model can rate - not only
the flagged ones, so the selection rule can be judged later without bias - one frozen row with:
  * the Dixon-Coles lambdas and rho (the whole score matrix is reproducible from them),
  * p_<key>: the full exact-score grid 0-0..6-6 + other, the goal and margin bands and the specials,
  * base_<key>: the same outcome's share in THAT league's own matches before the log date,
  * ratio_<special> = p / base, the flags cand_<special> against the league's own cutoff from the
    history study (output/specials/cutoffs.json; no cutoff -> NaN with cand_status NO_CUTOFF),
  * the Under/Over 1.5 price (the only special-related market v9 captures) when one was quoted before
    kickoff; every other special market's price is recorded as NOT_CAPTURED, never invented.

FIRST SIGHT. Rows are appended once per fixture, before kickoff, and never rewritten. Results go to a
SEPARATE file beside the log (specials_settled.csv), from v9's repaired history (90-minute score).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.combo import dixon_coles as dc
from src.specials import outcomes as O
from src.specials import study as ST

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "output" / "specials"
LOG_FILE = OUT_DIR / "specials_log.csv"
SETTLED_FILE = OUT_DIR / "specials_settled.csv"
EVAL_FILE = OUT_DIR / "specials_eval.json"
CUTOFF_FILE = OUT_DIR / "cutoffs.json"

CALC_VERSION = "1.0.0"
HORIZON_DAYS = 3                      # same look-ahead as the 1X2 paper record
SETTLE_AFTER_HOURS = 3                # a result is looked for only once the match can be over
# The only special-related market v9 captures with both sides. Everything else is NOT_CAPTURED.
PRICE_FILES = ("output/standard_sidemarket_odds_history.csv", "output/newformat_odds_history.csv")
PRICE_MARKETS = ("under15", "over15")


def row_id(fixture_key: str) -> str:
    return hashlib.sha1(str(fixture_key).encode("utf-8")).hexdigest()[:16]


# ── inputs ──────────────────────────────────────────────────────────────────────────────────────

def upcoming_fixtures(now: dt.datetime) -> pd.DataFrame:
    from src.data import season_store as store
    fx = store.read("fixtures")
    if fx.empty:
        return fx
    fx = fx.copy()
    fx["_ko"] = pd.to_datetime(fx.get("kickoff_utc"), errors="coerce", utc=True)
    fx = fx[fx["fixture_key"].notna()].dropna(subset=["_ko"]).drop_duplicates("fixture_key", keep="last")
    return fx[(fx["_ko"] > now) & (fx["_ko"] <= now + dt.timedelta(days=HORIZON_DAYS))]


def load_cutoffs(path: Path = CUTOFF_FILE) -> dict:
    if not path.exists():
        return {}
    return (json.loads(path.read_text(encoding="utf-8")) or {}).get("leagues", {}) or {}


def load_prices(v9_root: Path) -> pd.DataFrame:
    """Every pre-kickoff Over/Under 1.5 quote v9 stored, one row per (snapshot, match, market)."""
    parts = []
    for f in PRICE_FILES:
        p = Path(v9_root) / f
        if not p.exists():
            continue
        d = pd.read_csv(p, low_memory=False)
        d = d[d["market"].isin(PRICE_MARKETS)].copy()
        d["price_source"] = f
        parts.append(d)
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    sp = d["match"].astype(str).str.split(" vs ", n=1, expand=True)
    d["home"], d["away"] = sp[0], sp[1]
    d["snap"] = pd.to_datetime(d["snapshot_ts"], errors="coerce", utc=True)
    d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    return d.dropna(subset=["snap", "odds", "home", "away"])


def attach_price(prices: pd.DataFrame, league: str, day: str, home: str, away: str,
                 ko: pd.Timestamp, now: pd.Timestamp, tn) -> dict:
    """The latest Under 1.5 / Over 1.5 quote taken before both `now` and kickoff, for this fixture."""
    if prices is None or prices.empty:
        return {"price_status": "NO_PRICE_FILE"}
    f = prices[(prices["league"] == league) & (prices["match_date"].astype(str) == day)]
    if f.empty:
        return {"price_status": "NOT_QUOTED"}
    h = tn.resolve(str(home), sorted(f["home"].unique()))
    a = tn.resolve(str(away), sorted(f["away"].unique()))
    if h is None or a is None:
        return {"price_status": "NAME_UNPROVEN"}
    f = f[(f["home"] == h) & (f["away"] == a) & (f["snap"] < ko) & (f["snap"] <= now)]
    if f.empty:
        return {"price_status": "NOT_QUOTED_BEFORE_KICKOFF"}
    last = f["snap"].max()
    g = f[f["snap"] == last]
    out = {"price_status": "QUOTED", "price_ts": last.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "price_source": g["price_source"].iloc[0]}
    for m in PRICE_MARKETS:
        x = g[g["market"] == m]
        out[f"price_{m}"] = float(x["odds"].iloc[-1]) if len(x) else np.nan
    return out


# ── log ─────────────────────────────────────────────────────────────────────────────────────────

def build_rows(hist: pd.DataFrame, fixtures: pd.DataFrame, now: dt.datetime, cutoffs: dict,
               prices: pd.DataFrame | None, tn, canon) -> tuple[pd.DataFrame, dict]:
    """One row per fixture the model can rate. `canon` maps a league name to v9's canonical name."""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = pd.Timestamp(now.date())
    counts = {"fixtures": int(len(fixtures)), "no_league_model": 0, "unresolved_team": 0, "unrated": 0}
    models: dict = {}
    rows = []
    now_ts = pd.Timestamp(now)
    for _, f in fixtures.iterrows():
        lg = canon(f.get("league"))
        past = hist[(hist["league"] == lg) & (hist["date"] < today)] if lg else hist.iloc[0:0]
        if lg not in models:
            models[lg] = ST._fit(past) if len(past) >= ST.RULE["min_league_matches"] else None
        model = models[lg]
        if model is None:
            counts["no_league_model"] += 1
            continue
        teams = sorted(model["attack"])
        h, a = tn.resolve(str(f.get("home_team")), teams), tn.resolve(str(f.get("away_team")), teams)
        if h is None or a is None:
            counts["unresolved_team"] += 1
            continue
        pr = dc.predict(model, h, a)
        if not pr:
            counts["unrated"] += 1
            continue
        base = O.base_rates(past["home_goals"], past["away_goals"])
        p = O.matrix_probs(pr["matrix"])
        pick, ratio = O.unusual_pick(p, base)
        r = {"row_id": row_id(f["fixture_key"]), "logged_at": stamp, "fixture_key": f["fixture_key"],
             "league": lg, "match_date": f.get("match_date"),
             "kickoff_utc": f["_ko"].strftime("%Y-%m-%dT%H:%M:%SZ"),
             "home_team": f.get("home_team"), "away_team": f.get("away_team"),
             "model_home": h, "model_away": a,
             "hours_to_kickoff": round((f["_ko"] - now_ts).total_seconds() / 3600.0, 2),
             "lam_home": pr["lam_home"], "lam_away": pr["lam_away"], "rho": float(model["rho"]),
             "n_league_history": int(len(past)), "rule_version": ST.RULE["version"],
             "calc_version": CALC_VERSION,
             "cs_unusual_pick": pick, "p_cs_unusual": p.get(pick, np.nan) if pick else np.nan,
             "base_cs_unusual": base.get(pick, np.nan) if pick else np.nan,
             "ratio_cs_unusual": ratio}
        r.update({f"p_{k}": round(v, 6) for k, v in p.items()})
        r.update({f"base_{k}": round(base.get(k, np.nan), 6) for k in O.OUTCOME_KEYS})
        lc = cutoffs.get(lg, {})
        flagged = []
        for k in ST.CANDIDATE_KEYS:
            stat = ratio if k == "cs_unusual" else p[k]
            if k != "cs_unusual":
                b = base.get(k)
                r[f"ratio_{k}"] = round(p[k] / b, 4) if b else np.nan
            c = lc.get(k)
            if c is None or stat is None or stat != stat:
                r[f"cand_{k}"] = np.nan
                r[f"cut_{k}"] = np.nan
            else:
                r[f"cut_{k}"] = c["cutoff"]
                r[f"cand_{k}"] = float(stat > c["cutoff"])
                if stat > c["cutoff"]:
                    flagged.append(k)
        r["cand_status"] = "NO_CUTOFF" if not lc else "OK"
        r["flagged"] = ",".join(flagged)
        if prices is not None:
            r.update(attach_price(prices, lg, f["_ko"].strftime("%Y-%m-%d"), f.get("home_team"),
                                  f.get("away_team"), f["_ko"], now_ts, tn))
        r["price_other_specials"] = "NOT_CAPTURED"
        rows.append(r)
    return pd.DataFrame(rows), counts


def append_first_sight(new: pd.DataFrame, path: Path = LOG_FILE, now: dt.datetime | None = None) -> int:
    """Append rows whose row_id is not yet logged and whose kickoff is still ahead. Never rewrites."""
    if new.empty:
        return 0
    now = pd.Timestamp(now or dt.datetime.now(dt.timezone.utc))
    ko = pd.to_datetime(new["kickoff_utc"], utc=True, errors="coerce")
    new = new[ko > now]
    if path.exists():
        have = set(pd.read_csv(path, usecols=["row_id"])["row_id"].astype(str))
        new = new[~new["row_id"].astype(str).isin(have)]
    new = new.drop_duplicates("row_id")
    if new.empty:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        cols = list(pd.read_csv(path, nrows=0).columns)
        extra = [c for c in new.columns if c not in cols]
        if extra:                     # a new column would misalign the append: refuse, loudly
            raise ValueError(f"log schema changed, new columns {extra[:5]}...; start a new log version")
        new.reindex(columns=cols).to_csv(path, mode="a", header=False, index=False)
    else:
        new.to_csv(path, index=False)
    return int(len(new))


# ── settle ──────────────────────────────────────────────────────────────────────────────────────

def settle_rows(log: pd.DataFrame, settled: pd.DataFrame, hist: pd.DataFrame, now: dt.datetime,
                tn) -> pd.DataFrame:
    """Result rows for logged fixtures that have finished, from v9's repaired history. One result per
    row_id; the match must be the ONLY history row of that league with both resolved clubs on the
    kickoff date (or, failing that, one day either side - provider dates)."""
    done = set(settled["row_id"].astype(str)) if len(settled) else set()
    todo = log[~log["row_id"].astype(str).isin(done)].copy()
    ko = pd.to_datetime(todo["kickoff_utc"], utc=True, errors="coerce")
    todo = todo[ko + pd.Timedelta(hours=SETTLE_AFTER_HOURS) <= pd.Timestamp(now)]
    out = []
    for _, r in todo.iterrows():
        k = pd.Timestamp(str(r["kickoff_utc"])[:10])
        found = None
        for days in ([0], [-1, 1]):
            cand = hist[(hist["league"] == r["league"]) &
                        (hist["date"].isin([k + pd.Timedelta(days=x) for x in days]))]
            if cand.empty:
                continue
            h = tn.resolve_result(str(r["model_home"]), sorted(cand["home_team"].unique()))
            a = tn.resolve_result(str(r["model_away"]), sorted(cand["away_team"].unique()))
            hit = cand[(cand["home_team"] == h) & (cand["away_team"] == a)] if h and a else cand.iloc[0:0]
            if len(hit) == 1:
                found = hit.iloc[0]
                break
        if found is None:
            continue
        y = O.score_outcomes([found["home_goals"]], [found["away_goals"]])
        rec = {"row_id": r["row_id"], "home_goals": int(found["home_goals"]),
               "away_goals": int(found["away_goals"]), "result_date": str(found["date"].date()),
               "result_source": "v9 repaired history (90 min)",
               "settled_at": pd.Timestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")}
        rec.update({f"y_{k}": int(v[0]) for k, v in y.items()})
        pick = r.get("cs_unusual_pick")
        rec["y_cs_unusual"] = int(y[pick][0]) if isinstance(pick, str) and pick in y else np.nan
        out.append(rec)
    return pd.DataFrame(out)


# ── evaluate ────────────────────────────────────────────────────────────────────────────────────

def evaluate_live(log: pd.DataFrame, settled: pd.DataFrame) -> dict:
    res = {"rule": ST.RULE, "logged": int(len(log)), "settled": int(len(settled)), "specials": {}}
    if log.empty or settled.empty:
        res["status"] = "INSUFFICIENT"
        return res
    d = log.merge(settled, on="row_id", how="inner")
    d["date"] = pd.to_datetime(d["kickoff_utc"].astype(str).str[:10])
    for k in ST.CANDIDATE_KEYS:
        if f"cand_{k}" not in d:
            continue
        ce = ST.candidate_eval(d, k, ST.RULE["candidate_quantile"])
        if ce.get("verdict") == "PENDING_HOLM":
            ce["verdict"] = "LIVE_UNCORRECTED"
        res["specials"][k] = ce
    res["status"] = "OK"
    return res


# ── main ────────────────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Specials tracker (research only)")
    ap.add_argument("--mode", choices=["log", "settle", "evaluate", "all"], default="all")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--history", help="parquet of v9's repaired history (else exported from V9_LOCAL)")
    a = ap.parse_args(argv)
    from config import pro_config as cfg
    from src.data import v9_config
    from src.specials import history as HI
    now = dt.datetime.now(dt.timezone.utc)
    tn = v9_config.team_names()
    if a.history:
        hist, hinfo = HI.clean_history(pd.read_parquet(a.history))
    else:
        hist, hinfo = HI.export_v9_history()
    print(f"[specials] history {hinfo['rows']} rows, {hinfo['leagues']} leagues, to {hinfo['date_max']}")

    if a.mode in ("log", "all"):
        fx = upcoming_fixtures(now)
        rows, counts = build_rows(hist, fx, now, load_cutoffs(), load_prices(cfg.V9_LOCAL), tn,
                                  v9_config.canonical_league)
        n_flag = int((rows["flagged"] != "").sum()) if len(rows) else 0
        print(f"[specials] {len(rows)} fixture(s) rated, {n_flag} flagged; skipped {counts}")
        if not a.dry_run:
            print(f"[specials] appended {append_first_sight(rows, now=now)} new row(s)")
    if a.mode in ("settle", "all") and LOG_FILE.exists():
        log = pd.read_csv(LOG_FILE, low_memory=False)
        settled = pd.read_csv(SETTLED_FILE, low_memory=False) if SETTLED_FILE.exists() else pd.DataFrame()
        new = settle_rows(log, settled, hist, now, tn)
        print(f"[specials] {len(new)} result(s) settled")
        if not a.dry_run and len(new):
            pd.concat([settled, new], ignore_index=True).to_csv(SETTLED_FILE, index=False)
    if a.mode in ("evaluate", "all") and LOG_FILE.exists():
        log = pd.read_csv(LOG_FILE, low_memory=False)
        settled = pd.read_csv(SETTLED_FILE, low_memory=False) if SETTLED_FILE.exists() else pd.DataFrame()
        res = evaluate_live(log, settled)
        res["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if not a.dry_run:
            EVAL_FILE.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        print(f"[specials] evaluation: {res.get('status')}, settled {res['settled']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
