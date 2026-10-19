"""Two-sided player-prop MARKET CONSENSUS — forward-only research dataset (owner brief 2026-10-19 §16).

    python -m src.player_v3.consensus        # -> output/player_v3/consensus/*

Source: v9 output/prop_quotes/<YYYY-MM>.csv (append-only quote log since 2026-10-14). A fair
probability needs BOTH sides of ONE market from ONE book at (nearly) one moment:

    raw_over  = 1/over_odds,  raw_under = 1/under_odds
    fair_over = raw_over / (raw_over + raw_under)        (and fair_under = 1 - fair_over)

PAIRING RULES (never relaxed to make coverage look better):
  * same bookmaker, fixture (match + match_date), player, market and LINE (`point`; missing == missing)
  * sides are a true complement: over/under or yes/no
  * the two quotes are at most PAIR_TOL_MIN apart; the pair is stamped at the LATER quote
  * player names that look corrupted (an isolated 1-char token, e.g. "Isaac Og e") are excluded and
    counted — they are a capture defect, not a different player
Then per (fixture, player, market, line, ~timestamp): per-book fair probability, median and trimmed
consensus across books, dispersion, book count, best price and consensus price.

FORWARD-ONLY. Under/No quotes only exist from the first real capture onward; nothing here is, or may
be presented as, a historical two-sided validation of Player V3.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR / "player_v3" / "consensus"
CALC = "prop_consensus-1.0.0"
PAIR_TOL_MIN = 10
COMPLEMENT = {"over": "under", "under": "over", "yes": "no", "no": "yes"}
_BROKEN = re.compile(r"(?:^|\s)\S(?:\s|$)")      # an isolated single character inside a name


def load_quotes(root=None) -> pd.DataFrame:
    root = root or (cfg.V9_LOCAL / "output" / "prop_quotes")
    parts = [pd.read_csv(p, low_memory=False) for p in sorted(root.glob("*.csv"))]
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    d["ts"] = pd.to_datetime(d["snapshot_ts"], utc=True, errors="coerce")
    d["side"] = d["side"].astype(str).str.lower().str.strip()
    d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    d["point_key"] = d["point"].astype(str).replace({"nan": "", "None": ""})
    d["player_ok"] = ~d["player"].astype(str).str.strip().str.contains(_BROKEN)
    return d[d["odds"] > 1.0].reset_index(drop=True)


def pair(d: pd.DataFrame) -> pd.DataFrame:
    """Over/Under (Yes/No) pairs from the SAME book, player, market, line and fixture, <= tolerance."""
    keys = ["bookmaker", "match_date", "match", "player", "market", "point_key"]
    d = d[d["player_ok"]]
    pos = d[d["side"].isin(["over", "yes"])]
    neg = d[d["side"].isin(["under", "no"])]
    if pos.empty or neg.empty:
        return pd.DataFrame()
    m = pos.merge(neg, on=keys, suffixes=("_pos", "_neg"))
    m = m[m["side_neg"] == m["side_pos"].map(COMPLEMENT)]
    m["gap_min"] = (m["ts_pos"] - m["ts_neg"]).abs().dt.total_seconds() / 60
    m = m[m["gap_min"] <= PAIR_TOL_MIN]
    if m.empty:
        return m
    m["pair_ts"] = m[["ts_pos", "ts_neg"]].max(axis=1)
    # one pair per (keys, later-quote time): keep the tightest-in-time match
    m = m.sort_values("gap_min").drop_duplicates(keys + ["pair_ts"], keep="first")
    rp, rn = 1 / m["odds_pos"], 1 / m["odds_neg"]
    m["overround"] = rp + rn
    m["fair_pos"] = rp / (rp + rn)
    return m[keys + ["pair_ts", "odds_pos", "odds_neg", "side_pos", "overround", "fair_pos", "gap_min"]]


def consensus(pairs: pd.DataFrame) -> pd.DataFrame:
    if pairs.empty:
        return pairs
    p = pairs.copy()
    p["t_bucket"] = p["pair_ts"].dt.floor("30min")
    rows = []
    for k, g in p.groupby(["match_date", "match", "player", "market", "point_key", "side_pos", "t_bucket"]):
        f = g["fair_pos"].to_numpy()
        trimmed = float(np.mean(np.sort(f)[1:-1])) if len(f) >= 4 else float(np.median(f))
        rows.append(dict(zip(["match_date", "match", "player", "market", "point_key", "side", "t_bucket"], k),
                         n_books=int(g["bookmaker"].nunique()), fair_median=float(np.median(f)),
                         fair_trimmed=trimmed, dispersion=float(np.std(f)) if len(f) > 1 else 0.0,
                         best_price=float(g["odds_pos"].max()),
                         consensus_price=float(1 / np.median(f)),
                         books=",".join(sorted(g["bookmaker"].astype(str).unique()))))
    return pd.DataFrame(rows)


def coverage(d: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    two = pairs if len(pairs) else pd.DataFrame(columns=["match", "player", "market", "bookmaker"])
    return {"calculation_version": CALC,
            "first_quote": str(d["ts"].min())[:19] if len(d) else None,
            "last_quote": str(d["ts"].max())[:19] if len(d) else None,
            "quotes_total": int(len(d)),
            "quotes_by_side": d["side"].value_counts().to_dict(),
            "corrupted_player_names_excluded": int((~d["player_ok"]).sum()),
            "two_sided_matched_pairs": int(len(pairs)),
            "players": int(two["player"].nunique()), "fixtures": int(two["match"].nunique()),
            "markets": sorted(two["market"].unique().tolist()) if len(two) else [],
            "books": sorted(two["bookmaker"].unique().tolist()) if len(two) else [],
            "pairs_by_league": (pairs.merge(d[["match", "league"]].drop_duplicates(), on="match")
                                .groupby("league").size().to_dict() if len(pairs) else {}),
            "pairs_by_market": two.groupby("market").size().to_dict() if len(two) else {},
            "status": ("COLLECTING" if len(pairs) < 500 else "USABLE_FOR_FORWARD_TEST"),
            "note": ("forward-only: Under/No quotes exist only from the first capture; the feeds return "
                     "almost only Over/Yes, so two-sided fair probabilities are rare until capture changes")}


# ── Player V3 forward test V2 (two-sided consensus). V1 stays untouched. ──────────────────────
REG_DIR = cfg.BASE_DIR / "registry" / "player_v3_forward"
REGISTRATION_V2 = {
    "version": "player_v3_forward_v2",
    "registered_at": "2026-10-19",
    "forward_window_start": "2026-10-20",
    "relationship_to_v1": "ADDITIONAL experiment; registration.json (V1) is unchanged and keeps running",
    "market_reference": "two-sided de-vigged fair probability from consensus.py (same book, line, player, "
                        "fixture, <=10 min apart); median across books",
    "arms": ["MARKET_CONSENSUS_ONLY", "MARKET_CONSENSUS + WOWZA_V3", "MARKET_CONSENSUS + EXPECTED_MINUTES_ONLY",
             "MARKET_CONSENSUS + FULL_V3"],
    "same_fixtures_rule": "every arm is scored only on props where ALL arms have a prediction and a consensus",
    "primary_metrics": ["log_loss", "brier", "calibration_ece", "clv_vs_last_pre_kickoff_consensus",
                        "roi_of_preregistered_ev_rule"],
    "ev_rule": "bet the side whose arm probability x best price >= 1.05; flat 1u; paper only",
    "gates": {"min_two_sided_props": 500, "min_match_days": 30, "min_bets_for_roi": 150,
              "promotion": "an arm beats MARKET_CONSENSUS_ONLY on log loss with a 90% CI excluding zero AND "
                           "positive CLV; ROI only as confirmation"},
    "SAFE_TO_PROMOTE_V3": "NO",
    "PLAYER_PROP_REAL_STAKING": "NO (paper-only, permanently, per CLAUDE.md invariant 2)",
}


def registration_v2() -> dict:
    REG_DIR.mkdir(parents=True, exist_ok=True)
    p = REG_DIR / "registration_v2.json"
    if not p.exists():
        p.write_text(json.dumps(REGISTRATION_V2, indent=1, sort_keys=True), encoding="utf-8")
    if json.loads(p.read_text(encoding="utf-8")) != REGISTRATION_V2:
        raise RuntimeError("registration_v2.json was edited — create v3, never edit a registration")
    return REGISTRATION_V2


def run() -> dict:
    registration_v2()
    OUT.mkdir(parents=True, exist_ok=True)
    d = load_quotes()
    pairs = pair(d) if len(d) else pd.DataFrame()
    cons = consensus(pairs) if len(pairs) else pd.DataFrame()
    if len(pairs):
        pairs.to_csv(OUT / "two_sided_pairs.csv", index=False)
    if len(cons):
        cons.to_csv(OUT / "consensus.csv", index=False)
    cov = coverage(d, pairs)
    cov["generated_at"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    cov["SAFE_TO_PROMOTE_V3"] = "NO"
    cov["PLAYER_PROP_REAL_STAKING_ENABLED"] = "NO"
    (OUT / "coverage.json").write_text(json.dumps(cov, indent=1, default=str), encoding="utf-8")
    return cov


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str))
