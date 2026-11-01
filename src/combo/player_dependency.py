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
    # The derived builder leg, measured directly so it has its own cells (Data Truth 2026-11-01).
    "score_or_assist": lambda d: (d["goals"] >= 1) | (d["assists"] >= 1),
}

# Team card lines the builder offers, measured per team-match against the same match markets.
TEAM_CARD_LINES = (0.5, 1.5, 2.5, 3.5)

# Match markets, from the scoreline. Same definitions as src/combo/events.py.
MATCH_MARKETS = {
    "O15": lambda h, a: (h + a) >= 2,
    "O25": lambda h, a: (h + a) >= 3,
    "O35": lambda h, a: (h + a) >= 4,
    "U25": lambda h, a: (h + a) <= 2,
    "U35": lambda h, a: (h + a) <= 3,
    "BTTS": lambda h, a: (h >= 1) & (a >= 1),
    "BTTS_NO": lambda h, a: (h == 0) | (a == 0),
    "HOME": lambda h, a: h > a,
    "DRAW": lambda h, a: h == a,
    "AWAY": lambda h, a: h < a,
}


def _join_scorelines(players: pd.DataFrame, scorelines: pd.DataFrame) -> pd.DataFrame:
    """player rows x their fixture's scoreline, joined on the API-Football fixture_id.

    player_history.fixture_id and team_match_stats.fixture_id are the same provider id. The old
    join on raw date|home|away strings silently dropped every row whose club was spelled
    differently in the two sources (Data Truth 2026-11-01). Rows without an id are counted."""
    need = "fixture_id"
    if need not in players.columns or need not in scorelines.columns:
        raise ValueError("player_dependency needs fixture_id on both player rows and scorelines")
    p = players.copy()
    t = scorelines.copy()
    p["_fid"] = pd.to_numeric(p[need], errors="coerce")
    t["_fid"] = pd.to_numeric(t[need], errors="coerce")
    t = t.dropna(subset=["_fid"]).drop_duplicates("_fid")
    keep = [c for c in ("_fid", "home_goals", "away_goals") if c in t.columns]
    if "league" in t.columns and "league" not in p.columns:
        keep.append("league")
    j = p.merge(t[keep], on="_fid", how="inner")
    print(f"[dependency] joined {len(j):,} of {len(p):,} player rows to a scoreline by fixture_id "
          f"({int(p['_fid'].isna().sum()):,} without an id)")
    return j


def prepare(players: pd.DataFrame, scorelines: pd.DataFrame) -> pd.DataFrame:
    """Join player-match rows to their fixture's scoreline and settle both sides."""
    j = _join_scorelines(players, scorelines)
    j = j[pd.to_numeric(j["minutes"], errors="coerce") >= MIN_MINUTES].copy()

    hg = pd.to_numeric(j["home_goals"], errors="coerce")
    ag = pd.to_numeric(j["away_goals"], errors="coerce")
    # A missing score is not 'no goals': those rows cannot settle a match market, so they go.
    known = hg.notna() & ag.notna()
    if not known.all():
        print(f"[dependency] dropped {int((~known).sum()):,} rows whose scoreline is missing")
    j, hg, ag = j[known].copy(), hg[known], ag[known]
    for name, fn in MATCH_MARKETS.items():
        j[f"m_{name}"] = fn(hg, ag).astype(bool)
    for name, fn in PROP_MARKETS.items():
        j[f"p_{name}"] = fn(j).astype(bool)

    # The player's own rate, for conditioning. Computed from HIS OTHER matches only -- using the
    # current match would leak the outcome into the bucket that predicts it.
    for name in PROP_MARKETS:
        col = f"p_{name}"
        g = j.groupby("player_id")[col]
        # A player with no OTHER match has no rate (NaN), not a rate of 0.
        others = (g.transform("size") - 1).where(lambda x: x > 0)
        j[f"rate_{name}"] = (g.transform("sum") - j[col].astype(int)) / others
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


def team_card_cells(players: pd.DataFrame, scorelines: pd.DataFrame) -> pd.DataFrame:
    """Team-cards x match-market cells, measured by fixture_id (the builder's card legs).

    Team card totals are summed from a team's player rows; team-matches with fewer than
    team_markets.MIN_SQUAD_ROWS rows are incomplete collection and are not counted."""
    from src.combo.team_markets import MIN_SQUAD_ROWS
    j = _join_scorelines(players, scorelines)
    g = (j.groupby(["_fid", "team"])
          .agg(cards=("yellow_cards", "sum"), rows=("minutes", "size"),
               home_goals=("home_goals", "first"), away_goals=("away_goals", "first"))
          .reset_index())
    g = g[g["rows"] >= MIN_SQUAD_ROWS].copy()
    hg = pd.to_numeric(g["home_goals"], errors="coerce")
    ag = pd.to_numeric(g["away_goals"], errors="coerce")
    g = g[hg.notna() & ag.notna()].copy()
    hg, ag = hg[g.index], ag[g.index]
    rows: list[dict] = []
    for line in TEAM_CARD_LINES:
        a = (g["cards"] >= int(line + 0.5)).to_numpy(dtype=bool)
        for mkt, fn in MATCH_MARKETS.items():
            b = fn(hg, ag).to_numpy(dtype=bool)
            n = len(a)
            if n < MIN_CELL_N:
                continue
            pa, pb, pj = float(a.mean()), float(b.mean()), float((a & b).mean())
            if pa * pb <= 0:
                continue
            rows.append({"prop_market": f"teamcard_cards_o{line}", "match_market": mkt,
                         "segment": "ALL", "n": n, "p_prop": round(pa, 5), "p_match": round(pb, 5),
                         "p_joint": round(pj, 5), "independent_joint": round(pa * pb, 5),
                         "dependency_ratio": round(pj / (pa * pb), 4),
                         "calc_version": CALC_VERSION})
    return pd.DataFrame(rows)


def joint_lookup(matrix: pd.DataFrame) -> dict:
    """{(prop, match): dependency_ratio} from the ALL segment, for the builder to apply."""
    a = matrix[matrix["segment"] == "ALL"]
    return {(r.prop_market, r.match_market): r.dependency_ratio for r in a.itertuples()}
