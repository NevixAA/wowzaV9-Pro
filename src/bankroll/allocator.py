"""The monthly risk committee: previous policy + evidence (as of a date) -> proposed policy.

ASYMMETRIC BY DESIGN. Slow to add risk, fast to remove it.

INCREASE one band (+0.25 pp, never above the state limit or 1.50% base, never above the
quarter-Kelly size implied by the SHRUNK edge) only when ALL hold:
  n >= 100, matchdays >= 30, >= 2 months; shrunk ROI >= +1%; 90% matchday-block lower bound > 0;
  BOTH halves of the record positive (two independent periods); last 30 days not below -5%;
  median CLV >= 0 on >= 30 bets; edge not resting on one league (top share <= 60%, or the rest
  is positive on its own); no portfolio drawdown warning.
REDUCE one band on ANY of: 30- and 60-day ROI both negative (n60 >= 25); recent median CLV
  < -2% (>= 30 bets); one league > 75% of the record AND the rest negative. Two signals: two bands.
STOP (base 0, state STOPPED): shrunk ROI < -2% on n >= 60, or 60-day ROI < -15% with negative
  recent CLV, or the track is BLOCKED / its data is stale.
PRICE CAP: tightened to the lower edge of the top odds band when that band loses > 25% on
  >= 25 bets. Never widened automatically in this version (widening needs evidence this record
  cannot yet supply).
PAPER tracks never get money automatically; strong evidence only raises PAPER_PROMOTION_REVIEW
  for the owner. BLOCKED stays blocked.
"""
from __future__ import annotations

import copy
import math

import pandas as pd

from src.bankroll import HARD_BOUNDS, MAX_AUTO_BASE, MAX_MONTHLY_STEP_UP, STAKE_BANDS
from src.bankroll.evidence import convergence_leagues, track_evidence

REAL = ("PROBATION", "ACTIVE_LOW", "ACTIVE", "ACTIVE_STRONG", "DEGRADED")


def band_state(base: float) -> str:
    if base <= 0:
        return "STOPPED"
    if base <= 0.0025:
        return "PROBATION"
    if base <= 0.005:
        return "ACTIVE_LOW"
    if base <= 0.0125:
        return "ACTIVE"
    return "ACTIVE_STRONG"


def _down(base: float, steps: int = 1) -> float:
    lower = [b for b in STAKE_BANDS if b < base - 1e-12]
    return lower[-steps] if len(lower) >= steps else 0.0


def _up(base: float) -> float:
    higher = [b for b in STAKE_BANDS if b > base + 1e-12]
    return min(higher[0], base + MAX_MONTHLY_STEP_UP, MAX_AUTO_BASE) if higher else base


def _quarter_kelly(edge: float, odds: float) -> float:
    return 0.0 if edge <= 0 or odds <= 1 else 0.25 * edge / (odds - 1)


def decide_track(name: str, t: dict, ev: dict | None, as_of, dd_warning: bool) -> tuple[dict, dict]:
    t = dict(t)
    base, state = float(t.get("base_fraction", 0.0)), t.get("state", "UNSUPPORTED")
    rec = {"track": name, "previous_state": state, "previous_fraction": base, "reasons": []}
    if state in ("BLOCKED", "BLOCKED_FROM_REAL", "UNSUPPORTED"):
        rec.update(decision="KEEP_BLOCKED", proposed_fraction=0.0, proposed_state=state)
        return t, rec
    if ev is None:
        rec["reasons"].append("no settled bets before the review date")
        rec.update(decision="KEEP" if state != "PAPER" else "KEEP_PAPER",
                   proposed_fraction=base, proposed_state=state)
        return t, rec
    h = ev["horizons"]
    r30, r60 = h["LAST_30D"], h["LAST_60D"]
    if state == "PAPER":
        strong = (ev["n"] >= 150 and ev["matchdays"] >= 40 and ev["shrunk_roi"] > 0.01
                  and (ev["roi_lo90"] or -1) > 0 and (ev["half1_roi"] or -1) > 0
                  and (ev["half2_roi"] or -1) > 0 and (ev["clv_median"] or -1) >= 0)
        rec.update(decision="PAPER_PROMOTION_REVIEW" if strong else "KEEP_PAPER",
                   proposed_fraction=0.0, proposed_state="PAPER")
        rec["reasons"].append("evidence meets the paper-promotion bar - owner decision" if strong
                              else "paper track; money requires owner approval")
        return t, rec

    # ── stop ────────────────────────────────────────────────────────────────────
    stale = (pd.Timestamp(as_of) - pd.Timestamp(ev["last_bet"])).days > 21
    stop = []
    if ev["n"] >= 60 and ev["shrunk_roi"] < -0.02:
        stop.append(f"shrunk ROI {ev['shrunk_roi']:+.1%} on n={ev['n']}")
    if r60["n"] >= 40 and (r60["roi"] or 0) < -0.15 and (ev["clv_recent_median"] or 0) < 0:
        stop.append(f"60-day ROI {r60['roi']:+.1%} with negative recent CLV")
    if stop:
        t.update(base_fraction=0.0, state="STOPPED")
        rec.update(decision="STOP", proposed_fraction=0.0, proposed_state="STOPPED", reasons=stop)
        return t, rec

    # ── reduce ──────────────────────────────────────────────────────────────────
    red = []
    if r60["n"] >= 25 and (r60["roi"] or 0) < 0 and (r30["roi"] or 0) < 0:
        red.append(f"30-day {r30['roi']:+.1%} and 60-day {r60['roi']:+.1%} ROI both negative")
    if ev["clv_n"] >= 30 and ev["clv_recent_median"] is not None and ev["clv_recent_median"] < -0.02:
        red.append(f"recent median CLV {ev['clv_recent_median']:+.1%}")
    if (ev["top_league_share"] or 0) > 0.75 and (ev["ex_top_league_roi"] if ev["ex_top_league_roi"] is not None else 0) < 0:
        red.append(f"{ev['top_league_share']:.0%} of bets in {ev['top_league']} and the rest negative "
                   f"({ev['ex_top_league_roi']:+.1%})")
    # price cap: tighten when the top populated odds band loses heavily
    cap = float(t.get("max_odds", HARD_BOUNDS["max_odds"]))
    bands = [(k, v) for k, v in ev["odds_bands"].items() if v["n"] >= 25]
    if bands:
        k, v = bands[-1]
        lo_edge = float(k.strip("(]").split(",")[0])
        if v["roi"] < -0.25 and lo_edge < cap and lo_edge >= 1.6:
            t["max_odds"] = round(lo_edge, 2)
            rec["reasons"].append(f"max odds {cap:.2f} -> {lo_edge:.2f}: band {k} ROI {v['roi']:+.1%} on {v['n']}")
            rec["price_cap_change"] = [cap, lo_edge]
    if red:
        nb = _down(base, 2 if len(red) >= 2 else 1)
        t.update(base_fraction=nb, state=band_state(nb) if nb > 0 else "STOPPED")
        rec.update(decision="REDUCE", proposed_fraction=nb, proposed_state=t["state"],
                   reasons=rec["reasons"] + red)
        return t, rec

    # ── increase ────────────────────────────────────────────────────────────────
    need = {
        "n >= 100": ev["n"] >= 100, "matchdays >= 30": ev["matchdays"] >= 30,
        ">= 2 months": ev["months"] >= 2, "shrunk ROI >= +1%": ev["shrunk_roi"] >= 0.01,
        "90% lower bound > 0": (ev["roi_lo90"] or -1) > 0,
        "both halves positive": (ev["half1_roi"] or -1) > 0 and (ev["half2_roi"] or -1) > 0,
        "last 30d not below -5%": (r30["roi"] if r30["roi"] is not None else 0) >= -0.05,
        "median CLV >= 0 on 30+": ev["clv_n"] >= 30 and (ev["clv_median"] or -1) >= 0,
        "not one-league": (ev["top_league_share"] or 1) <= 0.60 or (ev["ex_top_league_roi"] or -1) > 0,
        "no portfolio drawdown warning": not dd_warning,
    }
    target = _quarter_kelly(ev["shrunk_roi"], ev["mean_odds"])
    nb = _up(base)
    need["quarter-Kelly supports the next band"] = target >= nb - 1e-9
    if all(need.values()) and nb > base and not stale:
        t.update(base_fraction=nb, state=band_state(nb))
        rec.update(decision="INCREASE_ONE_STEP", proposed_fraction=nb, proposed_state=t["state"],
                   reasons=rec["reasons"] + [k for k in need])
        return t, rec
    rec.update(decision="KEEP", proposed_fraction=base, proposed_state=state,
               reasons=rec["reasons"] + ([f"increase blocked: {', '.join(k for k, v in need.items() if not v)}"]
                                         if not all(need.values()) else []) + (["data stale"] if stale else []))
    return t, rec


def propose(prev: dict, bets: pd.DataFrame, as_of, v11: pd.DataFrame | None = None,
            dd_warning: bool = False) -> tuple[dict, list[dict], dict]:
    """Returns (proposed_policy, per-track decisions, evidence). Uses bets before `as_of` only."""
    ev = track_evidence(bets, as_of)
    pol = copy.deepcopy(prev)
    decisions = []
    for name, t in prev["tracks"].items():
        nt, rec = decide_track(name, t, ev.get(name), as_of, dd_warning)
        e = ev.get(name) or {}
        rec.update({k: e.get(k) for k in ("n", "matchdays", "roi", "shrunk_roi", "roi_lo90", "roi_hi90",
                                         "clv_median", "clv_recent_median", "top_league", "top_league_share")})
        rec.update({f"roi_{k.lower()}": (e.get("horizons", {}).get(k) or {}).get("roi")
                    for k in ("LAST_30D", "LAST_60D", "LAST_90D", "FULL_PROSPECTIVE_RECORD")})
        rec["delta"] = round(rec["proposed_fraction"] - rec["previous_fraction"], 4)
        pol["tracks"][name] = nt
        # one-position-per-fixture ranking key: shrunk edge first, then depth of evidence, then CLV
        if nt.get("state") in REAL and e:
            nt["evidence_score"] = round(100 * e["shrunk_roi"] + math.log10(max(e["n"], 1))
                                         + (1.0 if (e.get("clv_median") or -1) > 0 else 0.0), 3)
        decisions.append(rec)
    conv = convergence_leagues(bets, as_of, v11) if v11 is not None else []
    real_leagues = set(bets.loc[bets["track"].isin([k for k, v in pol["tracks"].items()
                                                    if v.get("state") in REAL]), "league"])
    pol["convergence"] = {"multiplier": prev.get("convergence", {}).get("multiplier", 1.15),
                          "leagues": sorted(r["league"] for r in conv if r["qualifies"] and r["league"] in real_leagues)}
    pol["policy_version"] = f"adaptive-{pd.Timestamp(as_of):%Y-%m}"
    pol["evidence_cutoff"] = (pd.Timestamp(as_of) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    pol["generated_at"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    return pol, decisions, {"tracks": ev, "convergence": conv}


def reduce_only(current: dict, proposed: dict) -> dict:
    """Current policy with ONLY the proposal's risk reductions applied — the default while the
    allocator itself is not walk-forward validated (owner brief 36: Balanced stays until then;
    removing risk is always allowed)."""
    p = copy.deepcopy(current)
    for k, t in p["tracks"].items():
        q = proposed["tracks"].get(k, t)
        if float(q.get("base_fraction", 0)) < float(t.get("base_fraction", 0)):
            t.update(base_fraction=q["base_fraction"], state=q.get("state", t.get("state")))
        if "max_odds" in q and float(q["max_odds"]) < float(t.get("max_odds", 9)):
            t["max_odds"] = q["max_odds"]
    return p


def validate(policy: dict) -> list[str]:
    """Hard-bound violations. A policy with any violation must not be recommended."""
    v = []
    pf = policy["portfolio"]
    if pf["single_bet_cap"] > HARD_BOUNDS["single_bet_cap"]: v.append("single bet cap > 2%")
    if pf["fixture_cap"] > HARD_BOUNDS["fixture_cap"]: v.append("fixture cap > 2%")
    if not HARD_BOUNDS["daily_cap_min"] <= pf["daily_cap"] <= HARD_BOUNDS["daily_cap_max"]: v.append("daily cap outside 3%-7.5%")
    if pf["league_daily_cap"] > HARD_BOUNDS["league_daily_cap"]: v.append("league/day cap > 4%")
    if pf["league_market_daily_cap"] > HARD_BOUNDS["league_market_daily_cap"]: v.append("league x market/day cap > 3%")
    for k, (lo, hi) in HARD_BOUNDS["tier"].items():
        m = policy["tier_multipliers"].get(k, lo)
        if not lo <= m <= hi: v.append(f"{k} multiplier outside {lo}-{hi}")
    lo, hi = HARD_BOUNDS["convergence"]
    if not lo <= policy["convergence"]["multiplier"] <= hi: v.append("convergence multiplier outside 1.00-1.20")
    for k, t in policy["tracks"].items():
        if float(t.get("base_fraction", 0)) > MAX_AUTO_BASE + 1e-12: v.append(f"{k} base > 1.50%")
        if float(t.get("max_odds", 0)) > HARD_BOUNDS["max_odds"] + 1e-12: v.append(f"{k} max odds > 2.75")
        if k == "player_props" and float(t.get("base_fraction", 0)) > 0: v.append("player props in the real path")
        if "OVER35" in k and float(t.get("base_fraction", 0)) > 0: v.append(f"{k} is BLOCKED")
    if "USA MLS" not in policy.get("paper_leagues", []): v.append("USA MLS must stay PAPER")
    return v
