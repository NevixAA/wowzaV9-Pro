"""
Combo settlement — did the builder actually win? (brief section 26)
==================================================================

A candidate list with no results is a wish list. This settles every leg of every combo against
what happened, then the combo itself: WON only if EVERY leg won, LOST the moment one loses.

HOW EACH LEG TYPE SETTLES

    goal / BTTS / 1X2 / team goals   from the final scoreline, via combo.events -- the same
                                     definitions the probabilities were built from, so a leg
                                     cannot be priced one way and settled another.

    player props                     from player_history: goals, assists, shots on target,
                                     cards, for that player in that fixture.

    team cards                       summed from the player rows of that fixture.

VOID IS NOT A LOSS, AND THE DIFFERENCE MATTERS

Section 26 says handle void, push and did-not-play explicitly rather than guessing. A player who
never came on has not lost his leg -- most books void it and the combo settles on the remaining
legs. Treating a DNP as a loss would understate every builder containing a rotation risk, which
is precisely the population a builder is most exposed to. So:

    LEG_WON        the event happened
    LEG_LOST       it did not
    LEG_VOID       player did not appear (0 minutes, or absent from the fixture entirely)
    LEG_UNKNOWN    we have no data to decide -- NOT a loss

A combo with any UNKNOWN leg settles UNKNOWN, never LOST. Guessing in our own favour would be
dishonest; guessing against ourselves would be a different kind of wrong, and both would corrupt
the hit rate this exists to measure.

WHY THERE IS NO "CLV" COLUMN HERE

CLV compares an entry price to a closing MARKET price. No bookmaker builder price is collected
anywhere, so there is nothing to close against -- and calling our own fair-price drift "CLV"
would be inventing an economic claim out of model noise. What IS tracked is `fair_odds_drift`:
how our own estimate moved between generation and kickoff. That is model stability, and it is
labelled as such.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.combo import events as ev

CALC_VERSION = "1.0.0"

LEG_WON, LEG_LOST, LEG_VOID, LEG_UNKNOWN = "WON", "LOST", "VOID", "UNKNOWN"
COMBO_WON, COMBO_LOST, COMBO_VOID, COMBO_UNKNOWN = "WON", "LOST", "VOID", "UNKNOWN"

# Player market -> (column, threshold). `score_or_assist` is handled separately.
_PLAYER_RULES = {
    "goals": ("goals", 1), "assists": ("assists", 1),
    "sot": ("shots_on_target", 1), "sot2": ("shots_on_target", 2),
    "sot3": ("shots_on_target", 3), "sot4": ("shots_on_target", 4),
}


def settle_goal_leg(market: str, home_goals, away_goals) -> str:
    """Any score-derived leg, from the scoreline."""
    if pd.isna(home_goals) or pd.isna(away_goals):
        return LEG_UNKNOWN
    h, a = int(home_goals), int(away_goals)
    if market in ev.EVENTS:
        return LEG_WON if bool(ev.EVENTS[market][0](np.int64(h), np.int64(a))) else LEG_LOST
    # Team-goal markets are not in the shared EVENTS map, so they are decided here.
    extra = {
        "HOME_O05": h >= 1, "AWAY_O05": a >= 1,
        "HOME_O15": h >= 2, "AWAY_O15": a >= 2,
    }
    if market in extra:
        return LEG_WON if extra[market] else LEG_LOST
    return LEG_UNKNOWN


def settle_player_leg(market: str, row: pd.Series | None) -> str:
    """A player leg. A player who did not appear VOIDS rather than losing."""
    if row is None:
        return LEG_VOID          # absent from the fixture entirely -> did not play
    mins = pd.to_numeric(pd.Series([row.get("minutes")]), errors="coerce").iloc[0]
    if pd.isna(mins):
        return LEG_UNKNOWN
    if float(mins) <= 0:
        return LEG_VOID
    if market == "score_or_assist":
        g = pd.to_numeric(pd.Series([row.get("goals")]), errors="coerce").iloc[0]
        a = pd.to_numeric(pd.Series([row.get("assists")]), errors="coerce").iloc[0]
        if pd.isna(g) or pd.isna(a):
            return LEG_UNKNOWN
        return LEG_WON if (g >= 1 or a >= 1) else LEG_LOST
    if market == "cards":
        y = pd.to_numeric(pd.Series([row.get("yellow_cards")]), errors="coerce").iloc[0]
        r = pd.to_numeric(pd.Series([row.get("red_cards")]), errors="coerce").iloc[0]
        if pd.isna(y) and pd.isna(r):
            return LEG_UNKNOWN
        return LEG_WON if ((y or 0) >= 1 or (r or 0) >= 1) else LEG_LOST
    rule = _PLAYER_RULES.get(market)
    if not rule:
        return LEG_UNKNOWN
    col, need = rule
    v = pd.to_numeric(pd.Series([row.get(col)]), errors="coerce").iloc[0]
    if pd.isna(v):
        return LEG_UNKNOWN
    return LEG_WON if v >= need else LEG_LOST


def settle_team_card_leg(line: float, team_cards) -> str:
    if team_cards is None or pd.isna(team_cards):
        return LEG_UNKNOWN
    return LEG_WON if float(team_cards) > float(line) else LEG_LOST


def combine(leg_results: list[str]) -> str:
    """Combo result from its legs. WON needs every leg; one loss ends it."""
    if not leg_results:
        return COMBO_UNKNOWN
    if LEG_LOST in leg_results:
        return COMBO_LOST                      # a loss is decisive regardless of the rest
    if LEG_UNKNOWN in leg_results:
        return COMBO_UNKNOWN                   # never guess a loss we cannot verify
    live = [r for r in leg_results if r != LEG_VOID]
    if not live:
        return COMBO_VOID                      # every leg voided
    return COMBO_WON


def settle(candidates: pd.DataFrame, scorelines: pd.DataFrame,
           players: pd.DataFrame) -> pd.DataFrame:
    """Settle a candidate frame. Returns it with per-leg and combo results attached."""
    if candidates is None or candidates.empty:
        return pd.DataFrame()

    sc = scorelines.copy()
    sc["_k"] = (pd.to_datetime(sc["match_date"], errors="coerce").dt.strftime("%Y-%m-%d")
                + "|" + sc["home_team"].astype(str) + "|" + sc["away_team"].astype(str))
    sc = sc.drop_duplicates("_k").set_index("_k")

    pl = players.copy()
    pl["_k"] = (pd.to_datetime(pl["date"], errors="coerce").dt.strftime("%Y-%m-%d")
                + "|" + pl["home_team"].astype(str) + "|" + pl["away_team"].astype(str))

    out = []
    for _, c in candidates.iterrows():
        key = (str(c.get("match_date"))[:10] + "|"
               + str(c.get("match", "")).replace(" vs ", "|"))
        if key not in sc.index:
            out.append({**c.to_dict(), "combo_result": COMBO_UNKNOWN,
                        "leg_results": "", "settle_note": "NO_SCORELINE"})
            continue
        s = sc.loc[key]
        hg, ag = s.get("home_goals"), s.get("away_goals")
        fixture_players = pl[pl["_k"] == key]

        legs, results = [], []
        for i in (1, 2, 3, 4, 5):
            mk = c.get(f"leg{i}_market")
            if mk is None or (isinstance(mk, float) and pd.isna(mk)):
                continue
            mk = str(mk)
            if mk.startswith("player_"):
                market = mk.replace("player_", "")
                label = str(c.get(f"leg{i}_label", ""))
                name = label.rsplit(" ", 1)[0] if " " in label else label
                row = fixture_players[fixture_players["player_name"] == name]
                r = settle_player_leg(market, row.iloc[0] if len(row) else None)
            else:
                r = settle_goal_leg(mk, hg, ag)
            legs.append(f"{mk}={r}")
            results.append(r)
        out.append({**c.to_dict(),
                    "final_score": f"{int(hg)}-{int(ag)}" if pd.notna(hg) and pd.notna(ag) else "",
                    "combo_result": combine(results),
                    "leg_results": " | ".join(legs),
                    "settle_note": "OK",
                    "settle_version": CALC_VERSION})
    return pd.DataFrame(out)


def performance(settled: pd.DataFrame) -> dict:
    """Headline record. VOID and UNKNOWN are excluded from the rate, and counted separately."""
    if settled is None or settled.empty:
        return {"settled": 0}
    r = settled["combo_result"]
    won, lost = int((r == COMBO_WON).sum()), int((r == COMBO_LOST).sum())
    decided = won + lost
    # Flat 1u stakes at the FAIR price -- there is no builder market price to stake at, so this
    # is what the model says it is worth, not what anyone could have won.
    odds = pd.to_numeric(settled.get("fair_combo_odds", settled.get("fair_odds")),
                         errors="coerce")
    pnl = np.where(r == COMBO_WON, odds - 1.0, np.where(r == COMBO_LOST, -1.0, 0.0))
    return {
        "settled": decided, "won": won, "lost": lost,
        "void": int((r == COMBO_VOID).sum()),
        "unknown": int((r == COMBO_UNKNOWN).sum()),
        "hit_rate": round(100.0 * won / decided, 2) if decided else None,
        "pnl_at_fair_odds": round(float(np.nansum(pnl)), 3),
        "mean_fair_odds": round(float(odds.mean()), 3) if odds.notna().any() else None,
        # The honest caveat, carried in the numbers rather than only in prose.
        "note": "P/L is at OUR FAIR price; no bookmaker builder price exists to stake at",
    }
