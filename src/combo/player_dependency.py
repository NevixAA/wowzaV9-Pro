"""
Player-prop x match-market dependence, measured (brief section 5, section 33 priority 2).
=========================================================================================

THE GAP THIS CLOSES

`builder.same_match` could price goals/BTTS/1X2 combinations exactly, because a score
distribution contains their joint. It could not price a player leg at all -- nothing in
`player_props` links a player's shot count to how many goals the match has -- so those legs got
Frechet bounds and a `JOINT_PLAYER_DEPENDENCE_UNMODELED` flag: an honest interval instead of an
invented number.

The dependence was never unmeasurable, only unmeasured. `player_history.parquet` holds 302,456
player-match rows with goals, assists, shots on target and cards; joining each to that match's
final scoreline gives the joint directly, exactly the way O2.5 x BTTS was measured on 23,604
fixtures. No model, no assumption -- counts.

WHY IT MATTERS MORE HERE THAN FOR MATCH MARKETS

The match-market dependencies were mostly obvious in direction (more goals implies BTTS). For
players the direction is obvious too, but the SIZE is not, and the size is what decides whether
a builder is priced fairly. Independence on a player leg is not a small error: a striker's
shot-on-target chance in a match that goes over 2.5 is not his unconditional rate.

STARTERS ONLY, AND WHY

Restricted to 60+ minutes. A substitute's prop probability is dominated by whether he plays at
all, which is a lineup question rather than a match-environment one, and mixing the two would
measure squad rotation and call it correlation. `MIN_MINUTES` makes that choice explicit.

CONDITIONING ON THE PLAYER'S OWN RATE

A dependency ratio pooled over every player answers a question nobody asks. What the builder
needs is the ratio for a player at THIS probability level, so the matrix is also cut by the
player's own recent rate. Cells below `MIN_CELL_N` are not emitted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CALC_VERSION = "1.0.0"

MIN_MINUTES = 60          # starters only; a sub's prop is a lineup question, not a match one
MIN_CELL_N = 500          # player-match rows required before a cell is emitted

# Player prop markets, named exactly as v9's player model names them.
PROP_MARKETS = {
    "goals": lambda d: d["goals"] >= 1,
    "assists": lambda d: d["assists"] >= 1,
    "sot": lambda d: d["shots_on_target"] >= 1,
    "sot2": lambda d: d["shots_on_target"] >= 2,
    "sot3": lambda d: d["shots_on_target"] >= 3,
    "sot4": lambda d: d["shots_on_target"] >= 4,
    "cards": lambda d: (d["yellow_cards"] >= 1) | (d["red_cards"] >= 1),
}

# Match markets, from the scoreline. Same definitions as src/combo/events.py.
MATCH_MARKETS = {
    "O15": lambda h, a: (h + a) >= 2,
    "O25": lambda h, a: (h + a) >= 3,
    "O35": lambda h, a: (h + a) >= 4,
    "U25": lambda h, a: (h + a) <= 2,
    "BTTS": lambda h, a: (h >= 1) & (a >= 1),
    "BTTS_NO": lambda h, a: (h == 0) | (a == 0),
    "HOME": lambda h, a: h > a,
    "DRAW": lambda h, a: h == a,
    "AWAY": lambda h, a: h < a,
}


def prepare(players: pd.DataFrame, scorelines: pd.DataFrame) -> pd.DataFrame:
    """Join player-match rows to their fixture's scoreline and settle both sides."""
    p = players.copy()
    t = scorelines.copy()
    p["_d"] = pd.to_datetime(p["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    t["_d"] = pd.to_datetime(t["match_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for d in (p, t):
        d["_k"] = (d["_d"] + "|" + d["home_team"].astype(str) + "|"
                   + d["away_team"].astype(str))
    t = t.drop_duplicates("_k")[["_k", "home_goals", "away_goals", "league"]]
    j = p.merge(t, on="_k", how="inner")
    j = j[pd.to_numeric(j["minutes"], errors="coerce") >= MIN_MINUTES].copy()

    hg = pd.to_numeric(j["home_goals"], errors="coerce")
    ag = pd.to_numeric(j["away_goals"], errors="coerce")
    for name, fn in MATCH_MARKETS.items():
        j[f"m_{name}"] = fn(hg, ag).astype(bool)
    for name, fn in PROP_MARKETS.items():
        j[f"p_{name}"] = fn(j).astype(bool)

    # The player's own rate, for conditioning. Computed from HIS OTHER matches only -- using the
    # current match would leak the outcome into the bucket that predicts it.
    for name in PROP_MARKETS:
        col = f"p_{name}"
        g = j.groupby("player_id")[col]
        j[f"rate_{name}"] = (g.transform("sum") - j[col].astype(int)) / \
                            (g.transform("size") - 1).clip(lower=1)
    return j


def build(j: pd.DataFrame, *, by_rate_bucket: bool = True) -> pd.DataFrame:
    """One row per (prop market, match market[, player-rate bucket])."""
    rows: list[dict] = []

    def emit(d: pd.DataFrame, prop: str, mkt: str, segment: str):
        n = len(d)
        if n < MIN_CELL_N:
            return
        a = d[f"p_{prop}"].to_numpy(dtype=bool)
        b = d[f"m_{mkt}"].to_numpy(dtype=bool)
        pa, pb = float(a.mean()), float(b.mean())
        pj = float((a & b).mean())
        indep = pa * pb
        if indep <= 0:
            return
        # Standard error on the joint, for an honest interval on the ratio.
        se = float(np.sqrt(max(pj * (1 - pj) / n, 0.0)))
        rows.append({
            "prop_market": prop, "match_market": mkt, "segment": segment,
            "n": n,
            "p_prop": round(pa, 5), "p_match": round(pb, 5),
            "p_joint": round(pj, 5),
            "independent_joint": round(indep, 5),
            "dependency_ratio": round(pj / indep, 4),
            "excess_pp": round(100 * (pj - indep), 3),
            "joint_ci_lo": round(max(pj - 1.96 * se, 0.0), 5),
            "joint_ci_hi": round(min(pj + 1.96 * se, 1.0), 5),
            # If independence sits inside the interval it is a defensible approximation here.
            "independence_within_ci": bool(pj - 1.96 * se <= indep <= pj + 1.96 * se),
            # Conditional probability is what the builder actually multiplies by.
            "p_prop_given_match": round(float(a[b].mean()) if b.any() else np.nan, 5),
            "calc_version": CALC_VERSION,
        })

    for prop in PROP_MARKETS:
        for mkt in MATCH_MARKETS:
            emit(j, prop, mkt, "ALL")
            if not by_rate_bucket:
                continue
            r = j[f"rate_{prop}"]
            if r.notna().sum() < 3 * MIN_CELL_N:
                continue
            try:
                buck = pd.qcut(r, 3, labels=["low", "mid", "high"], duplicates="drop")
            except ValueError:
                continue
            for lab, g in j.groupby(buck, observed=True):
                emit(g, prop, mkt, f"player_rate={lab}")
    return pd.DataFrame(rows)


def joint_lookup(matrix: pd.DataFrame) -> dict:
    """{(prop, match): dependency_ratio} from the ALL segment, for the builder to apply."""
    a = matrix[matrix["segment"] == "ALL"]
    return {(r.prop_market, r.match_market): r.dependency_ratio for r in a.itertuples()}
