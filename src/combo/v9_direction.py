"""Refuse a combo whose goal-total legs point the opposite way to v9's live O/U tip.

WHY THIS EXISTS. On 2026-09-06 the builder offered "Over 3.5 goals + three shots-on-target legs"
on Hertha Berlin v 1. FC Magdeburg and on Greuther Fürth v 1. FC Heidenheim, while v9 was tipping
UNDER 2.5 on both. Two products of the same estate telling one customer opposite things about the
same 90 minutes is indefensible whatever the maths says, so the gate refuses it.

WHAT IT IS NOT. It is NOT a claim that the two models disagree — they do not. Measured on the same
board, v9's own `p_over25` was 0.5043 on Hertha and 0.5207 on Fürth: a coin flip, marginally
towards goals in both cases. v9 tips UNDER there because the UNDER PRICE is generous against a
~50% model (2.92, +15.3% edge), not because it expects few goals. Gating on v9's model
probability therefore blocks almost nothing — measured, 1 of 302 candidates — because there is no
probability contradiction to find.

So this gates on v9's PUBLISHED BET DIRECTION, which is a statement about a price and not about
goals. That is a presentation rule, deliberately, and it is the honest description of it: the
purpose is that the two Telegram feeds never contradict each other in front of the user.

CONSEQUENCES, both of which are accepted rather than hidden:

  * It only covers fixtures v9 actually bets. v9 publishes a row in `output/bets.csv` only where
    it signalled something, so on the 2026-09-06 board 132 of 302 candidates had a v9 direction
    and 170 had none. Combos on fixtures v9 does not cover pass through ungated, by construction.
  * It does not touch WHY Over 3.5 dominates the board. That is `match_picture.build` ranking on
    `dependency_ratio`, which is monotonically highest for the rarest goal leg (measured means on
    the same board: O35 1.751, O25 1.542, BTTS 1.369, O15 1.245, unders ~1.01) — so 127 of 302
    candidates led with Over 3.5 and 5 with any under. This gate removes the contradictory subset;
    it does not change the ranking that produced it.

Pro never writes to v9. `bets.csv` is read over HTTP from v9's public tree, same as every other
v9 read in this repo. Fixtures are matched on the canonical league (v9 registry), the date and
v9's league-scoped club resolver (src/team_names.resolve), not on a hand-folded name key.
"""

from __future__ import annotations

import os

import pandas as pd

# Legs that assert MORE goals than the 2.5 line, and legs that assert fewer. Over 1.5 and BTTS are
# in NEITHER set on purpose: both are perfectly consistent with Under 2.5 (a 1-1 satisfies all
# three), so blocking them would reject bets that do not contradict anything.
OVER_LEGS = {"O25", "O35"}
UNDER_LEGS = {"U25", "U15"}

# Set on every candidate when v9's bets.csv cannot be read. The board is NOT shipped ungated:
# notify and the daily selection hold rows carrying it (Data Truth 2026-11-01).
GATE_UNAVAILABLE = "GATE_UNAVAILABLE"


def directions() -> pd.DataFrame | None:
    """v9's live O/U tips as rows (league, date, home_team, away_team, bet), or None when
    bets.csv cannot be read. An empty frame means v9 tips nothing today (the gate is ON with
    nothing to contradict); None means the gate cannot run, which the caller must NOT treat as
    'no contradictions'."""
    try:
        from src.data import v9_source as v9
        b = v9.fetch_csv("output/bets.csv", required=True)
    except Exception as e:                                       # noqa: BLE001
        print(f"[v9gate] could not read v9 bets.csv ({type(e).__name__}) — {GATE_UNAVAILABLE}")
        return None
    need = {"league", "date", "home_team", "away_team", "bet"}
    if b is None or not need <= set(b.columns):
        print(f"[v9gate] v9 bets.csv lacks {sorted(need - set(getattr(b, 'columns', [])))} — "
              f"{GATE_UNAVAILABLE}")
        return None
    b = b.assign(bet=b["bet"].astype(str).str.strip().str.upper())
    return b[b["bet"].isin(["OVER", "UNDER"])][sorted(need)].reset_index(drop=True)


def _direction_of(dirs: pd.DataFrame, league, date, home, away, tn) -> str | None:
    """v9's direction for one candidate fixture: same CANONICAL league and same date, then both
    clubs placed by v9's league-scoped resolver on the SAME v9 row. Anything else -> None."""
    from src.data import v9_config
    lg = v9_config.canonical_league(league)
    if lg is None:
        return None
    day = dirs[(dirs["_lg"] == lg) & (dirs["date"].astype(str).str[:10] == str(date)[:10])]
    if day.empty:
        return None
    h = tn.resolve(str(home), sorted(day["home_team"].astype(str).unique()))
    a = tn.resolve(str(away), sorted(day["away_team"].astype(str).unique()))
    if h is None or a is None:
        return None
    hit = day[(day["home_team"].astype(str) == h) & (day["away_team"].astype(str) == a)]
    return str(hit["bet"].iloc[0]) if len(hit) == 1 else None


def apply(cand: pd.DataFrame, dirs: pd.DataFrame | None = None, *, fetch: bool = True) -> pd.DataFrame:
    """Drop candidates whose goal-total legs contradict v9's tip on the same fixture.

    When v9's tips cannot be read, every row is kept but flagged v9_gate=GATE_UNAVAILABLE and
    the senders hold it, so an unreadable gate never silently becomes 'no contradictions'."""
    if cand is None or cand.empty:
        return cand
    if os.getenv("COMBO_V9_GATE", "1").strip() == "0":
        print("[v9gate] disabled by COMBO_V9_GATE=0")
        return cand
    if dirs is None and fetch:
        dirs = directions()
    if dirs is None:
        return cand.assign(v9_gate=GATE_UNAVAILABLE)

    need = {"league", "match_date", "match"}
    if not need <= set(cand.columns):
        print(f"[v9gate] candidates missing {sorted(need - set(cand.columns))} — {GATE_UNAVAILABLE}")
        return cand.assign(v9_gate=GATE_UNAVAILABLE)

    legcols = [c for c in cand.columns if c.startswith("leg") and c.endswith("_market")]
    if not legcols:
        return cand.assign(v9_gate="OK")

    split = cand["match"].astype(str).str.split(" vs ", n=1, expand=True)
    if split.shape[1] < 2:
        print(f"[v9gate] could not split `match` into two clubs — {GATE_UNAVAILABLE}")
        return cand.assign(v9_gate=GATE_UNAVAILABLE)

    from src.data import v9_config
    tn = v9_config.team_names()
    dirs = dirs.assign(_lg=dirs["league"].map(v9_config.canonical_league))
    memo: dict[tuple, str | None] = {}
    d_list = []
    for lg, d, h, a in zip(cand["league"], cand["match_date"], split[0], split[1]):
        k = (lg, str(d)[:10], h, a)
        if k not in memo:
            memo[k] = _direction_of(dirs, lg, d, h, a, tn)
        d_list.append(memo[k])
    d_of = pd.Series(d_list, index=cand.index, dtype="object")

    legs = cand[legcols].astype("object")
    has_over = legs.isin(OVER_LEGS).any(axis=1)
    has_under = legs.isin(UNDER_LEGS).any(axis=1)
    blocked = ((d_of == "UNDER") & has_over) | ((d_of == "OVER") & has_under)

    matched = int(d_of.notna().sum())
    print(f"[v9gate] {matched}/{len(cand)} candidate(s) sit on a fixture v9 tips; "
          f"{int(blocked.sum())} dropped for contradicting it")
    if matched and not blocked.any():
        # Not an error — v9 may simply agree everywhere today. Said out loud because a resolver
        # that has stopped matching looks exactly like agreement from the outside.
        print("[v9gate] nothing contradicted v9 on this board")
    return cand[~blocked].assign(v9_gate="OK")
