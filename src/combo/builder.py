"""
Bet-builder candidate generation (brief Phases 4-5).
===================================================

SAME-MATCH builders and CROSS-MATCH multiples, on real upcoming fixtures. PAPER only.

WHERE THE JOINT PROBABILITY COMES FROM, PER LEG TYPE

    goals / BTTS / 1X2   ->  EXACT, read off the fitted score distribution. Not approximated:
                             P(O2.5 and BTTS) is the mass on scorelines where both hold.

    player props, cards  ->  NOT MODELLED. The brief (section 5) is explicit that if the
                             player-match dependence cannot be estimated from existing inputs,
                             it must not be faked. It cannot: `player_props` carries a model
                             probability and a price, and nothing that ties a player's shot
                             count to the match goal environment.

                             So a player leg is priced with FRECHET BOUNDS -- the widest range
                             any joint can occupy given the marginals -- and flagged
                             JOINT_PLAYER_DEPENDENCE_UNMODELED. The lower bound is what a
                             conservative EV would use. Independence is NOT used, because the
                             true dependence is known to be positive (a high-scoring match
                             produces more shots) and independence would understate it in an
                             unknown direction.

WHY NO EV COLUMN IS POPULATED FOR SAME-MATCH BUILDERS

Section 9 and section 21: a same-game builder price cannot be reconstructed by multiplying
singles, because the bookmaker applies its own correlation adjustment. No builder odds are
collected anywhere in any repo, so `builder_odds` is empty, `executable` is False, and EV is
NULL rather than computed against an imaginary price. `fair_combo_odds` is published so the
moment a real builder price appears the comparison is one subtraction away.

Cross-match multiples are different: their legs ARE separately executable, so combined odds are
the product of real single prices and EV is computable.
"""
from __future__ import annotations

import hashlib
import itertools

import numpy as np
import pandas as pd

from src.combo import events as ev
from src.combo import score_model as sm

CALC_VERSION = "1.0.0"

# Legs read off the score distribution. Half-time markets are excluded: v9 models them but
# team_match_stats has no half-time score, so nothing can ever settle or validate them here.
SCORE_LEGS = ("O15", "U15", "O25", "U25", "O35", "U35", "BTTS", "BTTS_NO",
              "HOME", "DRAW", "AWAY")

# Cross-match legs must be individually bettable, so only markets with a real two-sided price.
MIN_LEG_PROB = 0.12          # below this a leg is a longshot, not a signal
MAX_LEG_PROB = 0.95          # above this it adds no odds and only adds a way to lose
MIN_COMBO_PROB = 0.10        # a builder under this is a lottery ticket (section 30)

# Shrinkage toward the market for cross-match legs (section 14). Wowza's edge is the thing being
# tested, so a combination must not compound the model's optimism across legs unchecked.
SHRINK = 0.35


def _combo_id(parts: list[str]) -> str:
    return hashlib.sha1("|".join(sorted(parts)).encode()).hexdigest()[:16]


def _fair(p: float) -> float | None:
    return round(1.0 / p, 3) if p and p > 0 else None


def same_match(fixtures: pd.DataFrame, *, props: pd.DataFrame | None = None,
               max_legs: int = 2, generated_at: str = "") -> pd.DataFrame:
    """Same-match builder candidates.

    `fixtures` needs fixture_key, league, match_date, home_team, away_team and the v9 model
    probabilities OU15/OU25/OU35/BTTS.
    """
    rows: list[dict] = []
    for _, fx in fixtures.iterrows():
        targets = {"O15": fx.get("OU15"), "O25": fx.get("OU25"),
                   "O35": fx.get("OU35"), "BTTS": fx.get("BTTS")}
        targets = {k: float(v) for k, v in targets.items() if pd.notna(v)}
        viol = sm.monotonicity_violation(targets)
        if viol:
            # Section 3: do not build legs from a logically inconsistent probability set.
            rows.append({"fixture_key": fx["fixture_key"], "combo_id": None,
                         "data_quality": viol, "deployment_mode": "REJECTED"})
            continue
        f = sm.fit(targets)
        if not f.get("ok"):
            continue
        m = f["matrix"]
        legs = {k: sm.prob(m, k) for k in SCORE_LEGS}

        for a, b in itertools.combinations(SCORE_LEGS, 2):
            if ev.is_redundant(a, b):
                continue
            pa, pb = legs[a], legs[b]
            if not (MIN_LEG_PROB <= pa <= MAX_LEG_PROB and MIN_LEG_PROB <= pb <= MAX_LEG_PROB):
                continue
            pj = sm.joint(m, a, b)
            if pj < MIN_COMBO_PROB:
                continue
            lo, hi = ev.frechet_bounds(pa, pb)
            indep = pa * pb
            rows.append({
                "generated_at": generated_at,
                "fixture_key": fx["fixture_key"], "league": fx.get("league"),
                "match_date": fx.get("match_date"),
                "match": f'{fx.get("home_team")} vs {fx.get("away_team")}',
                "combo_id": _combo_id([str(fx["fixture_key"]), a, b]),
                "n_legs": 2,
                "leg1_market": a, "leg1_label": ev.EVENTS[a][1], "leg1_model_p": round(pa, 4),
                "leg2_market": b, "leg2_label": ev.EVENTS[b][1], "leg2_model_p": round(pb, 4),
                "joint_probability": round(pj, 4),
                "independence_probability": round(indep, 4),
                # How badly independence would have priced this one.
                "dependency_ratio": round(pj / indep, 4) if indep > 0 else None,
                "frechet_lo": round(lo, 4), "frechet_hi": round(hi, 4),
                "fair_combo_odds": _fair(pj),
                "independence_fair_odds": _fair(indep),
                "builder_odds": None, "builder_bookmaker": None,
                "executable": False,          # no builder prices are collected anywhere
                "raw_ev": None, "conservative_ev": None,
                "joint_source": "SCORE_DISTRIBUTION_EXACT",
                "fit_quality": f["fit_quality"], "fit_max_error": f["max_abs_error"],
                "lam_home": f["lam_home"], "lam_away": f["lam_away"],
                "data_quality": "OK",
                "deployment_mode": "PAPER",
                "calc_version": CALC_VERSION,
            })

        # ── Player / card legs paired with a match leg ────────────────────────
        if props is not None and len(props):
            pr = props[props["fixture_key"] == fx["fixture_key"]]
            for _, p in pr.iterrows():
                pp = pd.to_numeric(pd.Series([p.get("model_prob")]), errors="coerce").iloc[0]
                if pd.isna(pp) or not (MIN_LEG_PROB <= float(pp) <= MAX_LEG_PROB):
                    continue
                for a in ("O25", "BTTS", "HOME", "AWAY", "O15"):
                    pa = legs[a]
                    if not (MIN_LEG_PROB <= pa <= MAX_LEG_PROB):
                        continue
                    lo, hi = ev.frechet_bounds(pa, float(pp))
                    if hi < MIN_COMBO_PROB:
                        continue
                    rows.append({
                        "generated_at": generated_at,
                        "fixture_key": fx["fixture_key"], "league": fx.get("league"),
                        "match_date": fx.get("match_date"),
                        "match": f'{fx.get("home_team")} vs {fx.get("away_team")}',
                        "combo_id": _combo_id([str(fx["fixture_key"]), a,
                                               str(p.get("player_name")), str(p.get("market"))]),
                        "n_legs": 2,
                        "leg1_market": a, "leg1_label": ev.EVENTS[a][1],
                        "leg1_model_p": round(pa, 4),
                        "leg2_market": f'player_{p.get("market")}',
                        "leg2_label": f'{p.get("player_name")} {p.get("market")}',
                        "leg2_model_p": round(float(pp), 4),
                        "leg2_tier": p.get("signal_tier"),
                        "leg2_market_odds": p.get("market_odds"),
                        # NOT a point estimate: the dependence is unknown, so the honest answer
                        # is the interval, and the lower bound is what any EV must use.
                        "joint_probability": None,
                        "independence_probability": round(pa * float(pp), 4),
                        "frechet_lo": round(lo, 4), "frechet_hi": round(hi, 4),
                        "fair_combo_odds": None,
                        "fair_odds_at_frechet_lo": _fair(lo),
                        "builder_odds": None, "executable": False,
                        "raw_ev": None, "conservative_ev": None,
                        "joint_source": "FRECHET_BOUNDS_ONLY",
                        "data_quality": "JOINT_PLAYER_DEPENDENCE_UNMODELED",
                        "deployment_mode": "PAPER",
                        "calc_version": CALC_VERSION,
                    })
    return pd.DataFrame(rows)


def cross_match(legs: pd.DataFrame, *, max_legs: int = 2, top_n: int = 400,
                generated_at: str = "") -> pd.DataFrame:
    """Cross-match multiples from individually-executable legs.

    `legs` needs fixture_key, match, market, selection, model_prob, market_odds.

    Different fixtures are far less correlated than markets within one, so the product is
    defensible here -- but the model probability is SHRUNK TOWARD THE MARKET first. Three
    slightly optimistic legs multiply into a badly optimistic combination, which is the specific
    failure section 16 warns about.
    """
    d = legs.copy()
    d["p"] = pd.to_numeric(d["model_prob"], errors="coerce")
    d["odds"] = pd.to_numeric(d["market_odds"], errors="coerce")
    d = d[d["p"].between(MIN_LEG_PROB, MAX_LEG_PROB) & d["odds"].notna() & (d["odds"] > 1.01)]
    if d.empty:
        return pd.DataFrame()
    d["p_market"] = 1.0 / d["odds"]
    d["p_shrunk"] = (1 - SHRINK) * d["p"] + SHRINK * d["p_market"]
    d = d.sort_values("p_shrunk", ascending=False)

    rows = []
    for combo in itertools.combinations(d.index, max_legs):
        sub = d.loc[list(combo)]
        # A fixture must never appear twice in one accumulator: the legs would be correlated
        # and, for opposite outcomes, jointly impossible.
        if sub["fixture_key"].nunique() != len(sub):
            continue
        p_raw = float(np.prod(sub["p"].values))
        p_cons = float(np.prod(sub["p_shrunk"].values))
        odds = float(np.prod(sub["odds"].values))
        if p_cons < MIN_COMBO_PROB:
            continue
        rows.append({
            "generated_at": generated_at,
            "combo_id": _combo_id([f'{r.fixture_key}:{r.market}:{r.selection}'
                                   for r in sub.itertuples()]),
            "n_legs": len(sub),
            **{f"fixture_{i+1}": r.match for i, r in enumerate(sub.itertuples())},
            **{f"market_{i+1}": f"{r.market} {r.selection}" for i, r in enumerate(sub.itertuples())},
            **{f"p_{i+1}": round(r.p, 4) for i, r in enumerate(sub.itertuples())},
            **{f"odds_{i+1}": round(r.odds, 3) for i, r in enumerate(sub.itertuples())},
            "raw_joint_probability": round(p_raw, 4),
            "conservative_joint_probability": round(p_cons, 4),
            "combined_odds": round(odds, 3),
            "raw_ev": round(p_raw * odds - 1.0, 4),
            "conservative_ev": round(p_cons * odds - 1.0, 4),
            "min_leg_prob": round(float(sub["p"].min()), 4),
            "min_leg_odds": round(float(sub["odds"].min()), 3),
            "correlation_warning": "DIFFERENT_FIXTURES_ASSUMED_INDEPENDENT",
            "shrink_lambda": SHRINK,
            "executable": True,
            "deployment_mode": "PAPER",
            "calc_version": CALC_VERSION,
        })
        if len(rows) >= top_n:
            break
    out = pd.DataFrame(rows)
    return out.sort_values("conservative_ev", ascending=False) if len(out) else out
