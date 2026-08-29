"""
Team-level and combined player markets — the legs a real bet builder is made of.
================================================================================

WHY THIS EXISTS

The first builder only knew match-level markets (match totals, BTTS, 1X2) and single player
props. A real same-game builder is usually assembled from legs like:

    Kerkez to be carded
    Forest over 0.5 team goals
    Szoboszlai to score or assist
    Forest over 2.5 team cards

Three of those four were not expressible at all. This module adds them.

WHAT IS DERIVABLE, AND FROM WHERE

    TEAM GOALS over X     ->  EXACT from the fitted score distribution. P(home_goals >= 1) is
                              simply the mass on those scorelines, and it is automatically
                              coherent with the match total and BTTS read off the same matrix.

    TEAM CARDS over X     ->  EMPIRICAL, aggregated from player_history. team_match_stats has NO
                              card columns at all, so team card totals are summed from the player
                              rows of each fixture. Base rates over 20,811 team-matches with a
                              full squad: over 0.5 = 86.4%, over 1.5 = 59.5%, over 2.5 = 31.9%,
                              over 3.5 = 13.4%.

    SCORE OR ASSIST       ->  P(goal) + P(assist) - P(both). The overlap is small but real --
                              1.06% of starter matches feature both -- so adding the two
                              marginals overstates the market by about that much. Measured
                              directly: 15.74% against 9.67% + 7.12% = 16.79% if naively added.

WHAT IS NOT MODELLED, AND IS SAID SO

Card markets have no score distribution behind them. A team's card count is driven by referee,
derby status and game state, none of which the goal model represents, so team-card legs carry
`CARD_DEPENDENCE_EMPIRICAL_ONLY`: their dependence on goal markets is taken from the measured
player-card ratios (which sit at 0.95-1.04, i.e. essentially independent of goals) rather than
from any joint model. That near-independence is itself the measured finding, not an assumption.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CALC_VERSION = "1.0.0"

MIN_SQUAD_ROWS = 11          # a team-match with fewer player rows has incomplete card data


def team_goal_markets(matrix: np.ndarray) -> dict[str, float]:
    """P(team scores over X) for each side, straight off the score matrix."""
    n = matrix.shape[0]
    H, A = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    out: dict[str, float] = {}
    for line, k in ((0.5, 1), (1.5, 2), (2.5, 3)):
        out[f"HOME_GOALS_O{str(line).replace('.', '')}"] = float(matrix[H >= k].sum())
        out[f"AWAY_GOALS_O{str(line).replace('.', '')}"] = float(matrix[A >= k].sum())
    return out


def team_card_rates(players: pd.DataFrame) -> pd.DataFrame:
    """Per team-match card totals, aggregated from player rows.

    Returns one row per (fixture, team) with the cards actually shown. Only fixtures with a
    plausible squad are kept -- a team-match with six player rows has not had six cards, it has
    had incomplete collection, and treating it as a low-card match would bias every rate down.
    """
    p = players.copy()
    p["_k"] = (pd.to_datetime(p["date"], errors="coerce").dt.strftime("%Y-%m-%d") + "|"
               + p["home_team"].astype(str) + "|" + p["away_team"].astype(str))
    g = p.groupby(["_k", "team"]).agg(
        team_cards=("yellow_cards", "sum"),
        team_reds=("red_cards", "sum"),
        team_goals=("goals", "sum"),
        squad_rows=("minutes", "size"),
        is_home=("is_home", "max"),
    ).reset_index()
    return g[g["squad_rows"] >= MIN_SQUAD_ROWS].copy()


def team_card_baselines(cards: pd.DataFrame) -> dict[str, float]:
    """Unconditional P(team cards over X). The fallback when a team has no history."""
    return {f"TEAM_CARDS_O{str(l).replace('.', '')}": float((cards["team_cards"] >= k).mean())
            for l, k in ((0.5, 1), (1.5, 2), (2.5, 3), (3.5, 4))}


def team_card_probability(cards: pd.DataFrame, team: str, line: float,
                          *, shrink_n: float = 10.0) -> tuple[float, int, str]:
    """P(this team goes over `line` cards), shrunk toward the league baseline.

    A team with four matches of history has a card rate measured on four matches; taking it at
    face value would let a small sample dominate the price. Shrinkage weights the team's own
    rate against the baseline by its sample size, so a long history moves the estimate and a
    short one barely does.
    """
    k = int(line + 0.5)
    base = float((cards["team_cards"] >= k).mean())
    own = cards[cards["team"] == team]
    n = len(own)
    if n == 0:
        return base, 0, "BASELINE_ONLY_NO_TEAM_HISTORY"
    rate = float((own["team_cards"] >= k).mean())
    w = n / (n + shrink_n)
    return w * rate + (1 - w) * base, n, "OK" if n >= shrink_n else "THIN_TEAM_HISTORY"


def score_or_assist(p_goal: float, p_assist: float,
                    overlap_rate: float = 0.0106 / 0.1574) -> float:
    """P(player scores OR assists) = P(goal) + P(assist) - P(both).

    NOT the sum. Measured on starter matches: 15.74% do one or the other, while the marginals
    add to 16.79% -- 1.06% of matches feature both, and counting those twice overstates the
    market by roughly that much every time.

    `overlap_rate` is the share of the union that is the intersection, measured on the same
    sample, used to scale the correction to this player's own probability level rather than
    subtracting a flat constant that would be wrong for a defender and wrong for a striker.
    """
    union_naive = p_goal + p_assist
    if union_naive <= 0:
        return 0.0
    both = min(overlap_rate * union_naive, min(p_goal, p_assist))
    return float(max(0.0, min(1.0, union_naive - both)))
