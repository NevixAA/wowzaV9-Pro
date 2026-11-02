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
    LEG_VOID       player did not appear (a player row with 0 minutes)
    LEG_UNKNOWN    we have no data to decide -- NOT a loss. A player with NO row is UNKNOWN: a
                   join miss is not evidence that he did not play (Data Truth 2026-11-01).

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
    """A player leg. A player who did not appear (0 minutes on his row) VOIDS rather than losing.

    No row at all is UNKNOWN: it may be a name/join miss, and only a minutes record can say he
    did not play."""
    if row is None:
        return LEG_UNKNOWN
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
        if (pd.notna(y) and y >= 1) or (pd.notna(r) and r >= 1):
            return LEG_WON
        # Not carded is only decidable when BOTH counts are known (a missing count is not 0).
        return LEG_LOST if pd.notna(y) and pd.notna(r) else LEG_UNKNOWN
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

    # Fallback for rows without a usable fixture_key: same date, same CANONICAL league, and both
    # clubs placed by v9's league-scoped result resolver (team_names.resolve_result). The old
    # fallback joined raw "date|home|away" strings, which silently fails across sources.
    from src.data import v9_config
    sc = scorelines.copy()
    sc["_d"] = pd.to_datetime(sc["match_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    sc["_lg"] = (sc["league"].map(v9_config.canonical_league) if "league" in sc.columns
                 else pd.Series(None, index=sc.index, dtype="object"))

    def _by_names(c) -> pd.Series | None:
        lg = v9_config.canonical_league(c.get("league"))
        parts = str(c.get("match", "")).split(" vs ", 1)
        if lg is None or len(parts) != 2:
            return None
        day = sc[(sc["_d"] == str(c.get("match_date"))[:10]) & (sc["_lg"] == lg)]
        if day.empty:
            return None
        tn = v9_config.team_names()
        h = tn.resolve_result(parts[0].strip(), sorted(day["home_team"].astype(str).unique()))
        a = tn.resolve_result(parts[1].strip(), sorted(day["away_team"].astype(str).unique()))
        if h is None or a is None:
            return None
        hit = day[(day["home_team"].astype(str) == h) & (day["away_team"].astype(str) == a)]
        return hit.iloc[0] if len(hit) == 1 else None

    # PREFER THE FIXTURE KEY. The name join is a last resort: club names demonstrably differ
    # between sources (invariant 11: Kaiserslautern, QPR, Cadiz). On the first settlement pass
    # that cost 1,956 of 2,532 combos, which were then reported as UNKNOWN. They were not
    # unverifiable; they were unjoined. Both sides carry `fixture_key`, so when they do, use it.
    by_key = {}
    if "fixture_key" in scorelines.columns:
        s2 = scorelines.dropna(subset=["fixture_key"]).drop_duplicates("fixture_key")
        by_key = {str(r["fixture_key"]): r for _, r in s2.iterrows()}

    # TWO WAYS A PLAYER LEG CAN BE SETTLED, and the graded one is preferred.
    #
    # (a) GRADED: Pro's `player_props` already carries a settled `result` per (fixture, player,
    #     market), produced by the same grader that settles single props. Using it means a leg
    #     cannot be graded here by one rule and there by another -- and it needs no match log.
    # (b) RAW: a match-level player log with minutes/goals/assists/cards, settled by the rules
    #     below. Kept because it is the only option when a prop was never graded.
    #
    # Anything neither can decide stays UNKNOWN, which `combine` never turns into a loss.
    graded: dict[tuple, str] = {}
    _MAP = {"WIN": LEG_WON, "LOSS": LEG_LOST, "VOID": LEG_VOID, "PENDING": LEG_UNKNOWN}
    if not players.empty and {"fixture_key", "player_name", "market", "result"} <= set(players.columns):
        g = players.dropna(subset=["fixture_key", "player_name", "market"])
        if "observed_at" in g.columns:
            g = g.sort_values("observed_at")
        for _, r in g.iterrows():
            graded[(str(r["fixture_key"]), str(r["player_name"]), str(r["market"]))] = \
                _MAP.get(str(r.get("result")), LEG_UNKNOWN)

    # Player rows are joined by fixture_key ONLY (no raw date|home|away string join).
    pl = players.copy()

    out = []
    for _, c in candidates.iterrows():
        fk = c.get("fixture_key")
        fk = "" if fk is None or (isinstance(fk, float) and pd.isna(fk)) else str(fk)
        s, how = None, ""
        if fk and fk in by_key:
            s, how = by_key[fk], "FIXTURE_KEY"
        else:
            s = _by_names(c)
            how = "RESOLVER" if s is not None else ""
        if s is None:
            out.append({**c.to_dict(), "combo_result": COMBO_UNKNOWN,
                        "leg_results": "", "settle_note": "NO_SCORELINE"})
            continue
        hg, ag = s.get("home_goals"), s.get("away_goals")
        # Owner rule 2026-11-02 (result_guard): a match played more than 48h from the kickoff the
        # combo was built for voids the combo; within 48h it settles on the match played.
        from src.data import result_guard as rg
        verdict = rg.reschedule_verdict(c.get("kickoff_utc"), s.get("kickoff_utc"))
        if verdict == rg.VOID_RESCHEDULED:
            out.append({**c.to_dict(), "combo_result": COMBO_VOID, "leg_results": "",
                        "settle_note": verdict, "settle_version": CALC_VERSION})
            continue
        fixture_players = (pl[pl["fixture_key"].astype(str) == fk]
                           if fk and "fixture_key" in pl.columns else pl.iloc[0:0])

        legs, results = [], []
        for i in (1, 2, 3, 4, 5):
            mk = c.get(f"leg{i}_market")
            if mk is None or (isinstance(mk, float) and pd.isna(mk)):
                continue
            mk = str(mk)
            if mk.startswith("player_"):
                market = mk.replace("player_", "")
                # The player is the machine column written at build time (leg{i}_player). Older
                # rows only have the display label: the LONGEST known player name it starts with
                # is used, and with no such name the leg is UNKNOWN - the label is never cut
                # into a guessed name (that produced 'R. Karjalainen 1+ shot on' and a VOID).
                name = c.get(f"leg{i}_player")
                if name is None or (isinstance(name, float) and pd.isna(name)):
                    label = str(c.get(f"leg{i}_label", ""))
                    names = ([str(x) for x in fixture_players["player_name"].dropna().unique()]
                             if len(fixture_players) else [])
                    cands = [n for n in names if label.startswith(n)]
                    name = max(cands, key=len) if cands else None
                if name is None:
                    r = LEG_UNKNOWN
                else:
                    name = str(name)
                    r = graded.get((fk, name, market))
                    if r is None:
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
                    # Which join decided it, so a future coverage drop is attributable rather
                    # than showing up as an unexplained rise in UNKNOWN.
                    "settle_note": f"OK:{how}",
                    "settle_version": CALC_VERSION})
    return pd.DataFrame(out)


def performance(settled: pd.DataFrame) -> dict:
    """Headline record. VOID and UNKNOWN are excluded from the rate, and counted separately.

    Data Truth round 3: the headline counts `record_audit.scoreboard_result` (the tip_scoreboard
    rule), so a combo WON on its remaining legs after a leg voided, a combo with a side-specific leg
    from the symmetric score fit, and a joint outside the Frechet bound are reported beside it and
    never mixed in. `combo_result` itself is untouched."""
    if settled is None or settled.empty:
        return {"settled": 0}
    from src.combo import record_audit as ra
    a = ra.annotate(settled)
    r = a["scoreboard_result"]
    won, lost = int((r == COMBO_WON).sum()), int((r == COMBO_LOST).sum())
    decided = won + lost
    # Flat 1u stakes at the FAIR price -- there is no builder market price to stake at, so this
    # is what the model says it is worth, not what anyone could have won.
    odds = pd.to_numeric(a.get("fair_combo_odds", a.get("fair_odds")),
                         errors="coerce")
    pnl = np.where(r == COMBO_WON, odds - 1.0, np.where(r == COMBO_LOST, -1.0, 0.0))
    raw = a["combo_result"]
    return {
        "settled": decided, "won": won, "lost": lost,
        "void": int((r == COMBO_VOID).sum()),
        "unknown": int((r == COMBO_UNKNOWN).sum()),
        "excluded_void_leg": int((r == ra.EXCLUDED_VOID_LEG).sum()),
        "excluded_void_leg_won": int(((r == ra.EXCLUDED_VOID_LEG) & (raw == COMBO_WON)).sum()),
        "excluded_invalid_model": int((r == ra.EXCLUDED_INVALID_MODEL).sum()),
        "excluded_frechet": int((r == ra.EXCLUDED_FRECHET).sum()),
        "hit_rate": round(100.0 * won / decided, 2) if decided else None,
        "pnl_at_fair_odds": round(float(np.nansum(pnl)), 3),
        "mean_fair_odds": round(float(odds.mean()), 3) if odds.notna().any() else None,
        # The honest caveat, carried in the numbers rather than only in prose.
        "note": "P/L is at OUR FAIR price; no bookmaker builder price exists to stake at",
    }
