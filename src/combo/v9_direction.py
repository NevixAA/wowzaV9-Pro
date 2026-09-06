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
v9 read in this repo.
"""

from __future__ import annotations

import os
import re
import unicodedata

import pandas as pd

# Legs that assert MORE goals than the 2.5 line, and legs that assert fewer. Over 1.5 and BTTS are
# in NEITHER set on purpose: both are perfectly consistent with Under 2.5 (a 1-1 satisfies all
# three), so blocking them would reject bets that do not contradict anything.
OVER_LEGS = {"O25", "O35"}
UNDER_LEGS = {"U25", "U15"}

_STOPWORDS = re.compile(r"\b(fc|cf|sc|sv|spvgg|ac|as|ss|us|afc|club|de|the)\b")


def _norm(s: object) -> str:
    """Fold a club name to a comparison key.

    Deliberately blunt: strip accents, drop the corporate-form words the two sources disagree
    about ("SpVgg Greuther Fürth" vs "Greuther Fürth", "Cádiz CF" vs "Cadiz"), collapse the rest.
    A false NON-match costs one ungated combo; a false match would gate the wrong fixture, so the
    key keeps every distinguishing token — this is not `startswith(first_word)`.
    """
    t = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    t = _STOPWORDS.sub(" ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _key(date: object, home: object, away: object) -> str:
    return f"{str(date)[:10]}|{_norm(home)}|{_norm(away)}"


def directions() -> dict[str, str]:
    """{fixture key: "OVER"|"UNDER"} from v9's live O/U tips, or {} if it cannot be read.

    FAILS OPEN AND SAYS SO. If v9 is unreachable the builder must still produce a board — a gate
    that silently empties the product on a network blip is worse than the contradiction it
    prevents. The caller reports how many candidates were actually matched, so a resolver that
    has quietly stopped matching shows up as "0 gated" rather than as success.
    """
    try:
        from src.data import v9_source as v9
        b = v9.fetch_csv("output/bets.csv", required=False)
    except Exception as e:                                       # noqa: BLE001
        print(f"[v9gate] could not read v9 bets.csv ({type(e).__name__}) — gate is OFF")
        return {}
    if b is None or b.empty or not {"date", "home_team", "away_team", "bet"} <= set(b.columns):
        print("[v9gate] v9 bets.csv unusable — gate is OFF")
        return {}
    out: dict[str, str] = {}
    for _, r in b.iterrows():
        d = str(r.get("bet") or "").strip().upper()
        if d in ("OVER", "UNDER"):
            out[_key(r.get("date"), r.get("home_team"), r.get("away_team"))] = d
    return out


def apply(cand: pd.DataFrame, dirs: dict[str, str] | None = None) -> pd.DataFrame:
    """Drop candidates whose goal-total legs contradict v9's tip on the same fixture."""
    if cand is None or cand.empty:
        return cand
    if os.getenv("COMBO_V9_GATE", "1").strip() == "0":
        print("[v9gate] disabled by COMBO_V9_GATE=0")
        return cand
    dirs = directions() if dirs is None else dirs
    if not dirs:
        return cand

    need = {"match_date", "match"}
    if not need <= set(cand.columns):
        print(f"[v9gate] candidates missing {sorted(need - set(cand.columns))} — gate is OFF")
        return cand

    legcols = [c for c in cand.columns if c.startswith("leg") and c.endswith("_market")]
    if not legcols:
        return cand

    split = cand["match"].astype(str).str.split(" vs ", n=1, expand=True)
    if split.shape[1] < 2:
        print("[v9gate] could not split `match` into two clubs — gate is OFF")
        return cand
    keys = [_key(d, h, a) for d, h, a in zip(cand["match_date"], split[0], split[1])]
    d_of = pd.Series([dirs.get(k) for k in keys], index=cand.index)

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
    return cand[~blocked].copy()
