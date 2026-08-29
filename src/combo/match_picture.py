"""
The whole picture for one match, from every v9 model — then builders from it.
=============================================================================

WHAT THIS IS

Pro reads every opinion v9 already produces for a fixture and assembles them into one coherent
view, then builds multi-leg combinations from it. Nothing here retrains or replaces a v9 model;
it consumes their output.

    v9 model_snapshots   ->  O1.5  O2.5  O3.5  BTTS  HT O0.5  HT O1.5
    fitted score matrix  ->  1X2, team goals over 0.5/1.5, and EVERY joint among goal markets
    v9 player_props      ->  per player: goals, SOT 1+/2+/3+, assists, cards
    player_history       ->  team card totals, and score-or-assist overlap

WHY N LEGS AND NOT TWO

A bet builder is normally several LIKELY things stacked until the price is worth having --
"Kerkez carded, Forest over 0.5 goals, Szoboszlai to score or assist, Forest over 2.5 cards".
Each leg is probable on its own; the combination is what pays. The earlier two-leg limit, and a
cap that rejected anything above 55%, had it exactly backwards: high per-leg probability is the
point, not a disqualification.

HOW THE JOINT IS COMPUTED ACROSS MANY LEGS

    goal-derived legs      EXACT and jointly, in one step. Any number of match-total, BTTS, 1X2
                           and team-goal legs are a single mask over the score matrix, so their
                           combined probability is the mass where all of them hold. No pairwise
                           chaining and no independence.

    player and card legs   Conditional on the goal block, using the MEASURED ratios from
                           player_dependency (goals x O2.5 = 1.45, assists x O2.5 = 1.48,
                           cards x anything ~= 1.00). Applied one leg at a time against the goal
                           block, then multiplied between player legs.

THE HONEST LIMIT, STATED ON EVERY ROW

Two players' events are treated as conditionally independent given the match state. That is an
approximation: two forwards on the same team compete for the same chances. It is NOT measured
here, so any builder containing two player legs carries `MULTI_PLAYER_INDEPENDENCE_ASSUMED`, and
its probability should be read as an upper estimate. Legs from a single player are never
combined at all -- "Szoboszlai to score" and "Szoboszlai to score or assist" is one bet.

AND THE PRICE

No bookmaker same-game-builder price exists in any repo, so every same-match row reports a FAIR
price only. The comparison the user actually makes is against their own book: if it offers more
than the fair price, there is value; if less, the correlation margin has eaten it.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from src.combo import score_model as sm
from src.combo import team_markets as tm

CALC_VERSION = "2.0.0"

MAX_LEGS = 5
MIN_LEG_PROB = 0.15          # a builder is made of LIKELY things
MIN_COMBO_PROB = 0.03        # below this the price is a lottery ticket whatever the odds
MIN_FAIR_ODDS = 1.8          # under this it is not worth the extra ways to lose


def goal_legs(matrix: np.ndarray) -> dict[str, tuple[float, np.ndarray, str]]:
    """Every goal-derived leg as (probability, score-grid mask, label)."""
    n = matrix.shape[0]
    H, A = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    T = H + A
    masks = {
        "O15": (T >= 2, "Over 1.5 goals"), "O25": (T >= 3, "Over 2.5 goals"),
        "O35": (T >= 4, "Over 3.5 goals"), "U35": (T <= 3, "Under 3.5 goals"),
        "U25": (T <= 2, "Under 2.5 goals"),
        "BTTS": ((H >= 1) & (A >= 1), "Both teams to score"),
        "BTTS_NO": ((H == 0) | (A == 0), "Both teams to score - No"),
        "HOME": (H > A, "Home win"), "DRAW": (H == A, "Draw"), "AWAY": (H < A, "Away win"),
        "1X": (H >= A, "Home or draw"), "X2": (H <= A, "Draw or away"),
        "HOME_O05": (H >= 1, "Home over 0.5 goals"),
        "AWAY_O05": (A >= 1, "Away over 0.5 goals"),
        "HOME_O15": (H >= 2, "Home over 1.5 goals"),
        "AWAY_O15": (A >= 2, "Away over 1.5 goals"),
    }
    return {k: (float(matrix[m].sum()), m, lbl) for k, (m, lbl) in masks.items()}


def player_legs(props: pd.DataFrame, *, min_p: float = MIN_LEG_PROB) -> list[dict]:
    """One row per (player, market), plus a derived score-or-assist leg where possible."""
    if props is None or props.empty:
        return []
    p = props.copy()
    p["model_prob"] = pd.to_numeric(p["model_prob"], errors="coerce")
    p = p.dropna(subset=["model_prob"])
    if "observed_at" in p.columns:
        p = p.sort_values("observed_at")
    p = p.drop_duplicates(subset=["player_name", "market"], keep="last")

    legs: list[dict] = []
    for _, r in p.iterrows():
        if not (min_p <= float(r["model_prob"]) <= 0.98):
            continue
        legs.append({"kind": "player", "player": r["player_name"], "market": str(r["market"]),
                     "p": float(r["model_prob"]), "odds": r.get("market_odds"),
                     "tier": r.get("signal_tier"),
                     "label": f'{r["player_name"]} {_market_label(str(r["market"]))}'})
    # Score-or-assist, built from the two marginals with the overlap removed.
    by_player = p.pivot_table(index="player_name", columns="market", values="model_prob",
                              aggfunc="last")
    if {"goals", "assists"}.issubset(by_player.columns):
        for name, row in by_player.iterrows():
            g, a = row.get("goals"), row.get("assists")
            if pd.isna(g) or pd.isna(a):
                continue
            u = tm.score_or_assist(float(g), float(a))
            if min_p <= u <= 0.98:
                legs.append({"kind": "player", "player": name, "market": "score_or_assist",
                             "p": u, "odds": None, "tier": None,
                             "label": f"{name} to score or assist"})
    return legs


def _market_label(m: str) -> str:
    return {"goals": "to score", "assists": "to assist", "sot": "1+ shot on target",
            "sot2": "2+ shots on target", "sot3": "3+ shots on target",
            "sot4": "4+ shots on target", "cards": "to be carded"}.get(m, m)


def team_card_legs(cards: pd.DataFrame, home: str, away: str) -> list[dict]:
    """Team card lines for both sides, shrunk toward the league baseline."""
    out: list[dict] = []
    if cards is None or cards.empty:
        return out
    for team, side in ((home, "Home"), (away, "Away")):
        for line in (0.5, 1.5, 2.5, 3.5):
            pr, n, status = tm.team_card_probability(cards, team, line)
            if MIN_LEG_PROB <= pr <= 0.98:
                out.append({"kind": "team_card", "team": team, "market": f"cards_o{line}",
                            "p": pr, "odds": None, "n_history": n, "status": status,
                            "label": f"{team} over {line} cards"})
    return out


def build(matrix: np.ndarray, *, props: pd.DataFrame | None = None,
          cards: pd.DataFrame | None = None, home: str = "", away: str = "",
          dep: dict | None = None, max_legs: int = 4, top_n: int = 40) -> pd.DataFrame:
    """All builder combinations for one fixture, from every available leg."""
    g = goal_legs(matrix)
    goal_pool = {k: v for k, v in g.items() if MIN_LEG_PROB <= v[0] <= 0.97}
    p_pool = player_legs(props) if props is not None else []
    c_pool = team_card_legs(cards, home, away) if cards is not None else []

    pool: list[dict] = []
    for k, (pr, mask, lbl) in goal_pool.items():
        pool.append({"kind": "goal", "key": k, "p": pr, "mask": mask, "label": lbl})
    pool += p_pool + c_pool

    rows: list[dict] = []
    for n_legs in range(2, max_legs + 1):
        for combo in itertools.combinations(range(len(pool)), n_legs):
            legs = [pool[i] for i in combo]
            bad = _reject(legs)
            if bad:
                continue
            pj, src, flags = _joint(legs, matrix, dep or {})
            if pj is None or pj < MIN_COMBO_PROB:
                continue
            fair = 1.0 / pj
            if fair < MIN_FAIR_ODDS:
                continue
            indep = float(np.prod([l["p"] for l in legs]))
            row = {
                "n_legs": n_legs,
                "legs": " + ".join(l["label"] for l in legs),
                "leg_probs": ", ".join(f'{l["p"]:.0%}' for l in legs),
                "joint_probability": round(pj, 4),
                "independence_probability": round(indep, 4),
                "dependency_ratio": round(pj / indep, 3) if indep > 0 else None,
                "fair_odds": round(fair, 2),
                "independence_fair_odds": round(1.0 / indep, 2) if indep > 0 else None,
                "joint_source": src,
                "leg_flags": "|".join(flags) if flags else "OK",
            }
            # Machine-readable leg identity alongside the human label. Without it the settler
            # would have to parse the display string back into markets, which breaks the moment
            # a label is reworded -- the settlement rules must key on the SAME identifiers the
            # probabilities were computed from.
            for i, l in enumerate(legs, start=1):
                row[f"leg{i}_market"] = (l["key"] if l["kind"] == "goal"
                                         else f'player_{l["market"]}' if l["kind"] == "player"
                                         else f'teamcard_{l["market"]}')
                row[f"leg{i}_label"] = l["label"]
                row[f"leg{i}_p"] = round(float(l["p"]), 4)
            rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # `top_n` IS A QUOTA PER LEG COUNT, NOT A GLOBAL HEAD, and the distinction was silently
    # deciding what this module could produce. The previous line was
    #
    #     out.sort_values(["n_legs", "fair_odds"]).head(top_n)
    #
    # which sorts leg count ASCENDING and then keeps the first 40 rows -- so two-leg combos
    # filled the entire quota and no three- or four-leg builder ever survived. Measured on one
    # fixture with props: 489 two-leg, 2,702 three-leg and 5,276 four-leg combos passed every
    # filter, and the sort discarded all 7,978 of the longer ones. Across a whole board that
    # produced 6,360 candidates of which 100% were two-leg, which reads like a modelling limit
    # and was a line of presentation code.
    #
    # Ranked by dependency ratio within each leg count: the further a combo sits from what
    # multiplying its legs would imply, the more it is worth showing, since that gap is the only
    # thing this system knows that a naive price does not.
    # MIXED COMBOS WIN THE QUOTA. Ranking on dependency ratio alone hands every slot to
    # goal-family pairs, because legs that restate one opinion about goals are the most correlated
    # things on the board — "Over 2.5 + BTTS" scores highest precisely because it is nearly one
    # bet. The result was 3,744 candidates of which 144 contained a player leg and 124 a card leg,
    # so the builder people actually want was being crowded out before the notifier ever saw it.
    # Combos carrying a player prop or a team-card line sort first within each leg count.
    mkcols = [c for c in out.columns if c.startswith("leg") and c.endswith("_market")]
    mixed = out[mkcols].apply(
        lambda r: r.astype(str).str.startswith(("player_", "teamcard")).any(), axis=1)
    out = out.assign(_mixed=mixed.astype(int))
    return (out.sort_values(["_mixed", "dependency_ratio"], ascending=[False, False])
               .groupby("n_legs", group_keys=False).head(top_n)
               .sort_values(["n_legs", "_mixed", "dependency_ratio"],
                            ascending=[True, False, False])
               .drop(columns=["_mixed"]))


def _reject(legs: list[dict]) -> str | None:
    """Combinations that are not bets.

    NESTING IS DECIDED FROM THE SCORE-GRID MASKS, by set containment, exactly as
    events.is_redundant does. The first version checked only for repeated players and card
    lines, and promptly produced "Home win + Home or draw" -- winning implies not losing, so
    that combination IS the home win -- and "Home win + Home over 0.5 goals", which is the same
    error since a winning side has scored. Comparing masks catches every such pair, including
    the team-goal markets added later, without anyone maintaining a list.
    """
    players = [l.get("player") for l in legs if l["kind"] == "player"]
    if len(players) != len(set(players)):
        return "SAME_PLAYER_TWICE"          # one player's two markets is one bet, not two legs
    teams = [(l.get("team"), l.get("market")) for l in legs if l["kind"] == "team_card"]
    if len(teams) != len(set(teams)) or len({t for t, _ in teams}) < len(teams):
        return "SAME_TEAM_CARD_LINE_TWICE"  # nested card lines collapse to the strictest
    goal = [l for l in legs if l["kind"] == "goal"]
    # AT MOST ONE VIEW OF THE SCORELINE. Every goal-family leg -- over/under, BTTS, team goals,
    # 1X2 -- is read off the SAME fitted score matrix, so two of them are one model's output
    # combined with itself rather than two opinions. The mask checks below catch pairs that are
    # nested or impossible, but "Over 3.5 + BTTS + Away over 1.5" is neither: it is merely the
    # same belief about goals said three times, which is what the first live tips were and what
    # they were rejected for. Enforced HERE rather than only at notify time, so the per-fixture
    # quota is spent on shapes that can actually be sent instead of being filled with combos the
    # notifier will refuse.
    if len(goal) > 1:
        return "MORE_THAN_ONE_GOAL_FAMILY_LEG"
    for a, b in itertools.combinations(goal, 2):
        ma, mb = a["mask"], b["mask"]
        if not (ma & mb).any():
            return f"MUTUALLY_EXCLUSIVE_{a['key']}_{b['key']}"
        if (ma & ~mb).sum() == 0 or (mb & ~ma).sum() == 0:
            return f"NESTED_{a['key']}_{b['key']}"
    return None


def _joint(legs: list[dict], matrix: np.ndarray, dep: dict) -> tuple[float | None, str, list[str]]:
    """Combined probability. Goal legs exactly and together; others conditionally."""
    flags: list[str] = []
    goal = [l for l in legs if l["kind"] == "goal"]
    other = [l for l in legs if l["kind"] != "goal"]

    if goal:
        mask = goal[0]["mask"].copy()
        for l in goal[1:]:
            mask &= l["mask"]
        p_goal = float(matrix[mask].sum())
        if p_goal <= 0:
            return None, "IMPOSSIBLE", ["MUTUALLY_EXCLUSIVE_GOAL_LEGS"]
    else:
        p_goal = 1.0

    p = p_goal
    src = "SCORE_MATRIX_EXACT" if not other else "SCORE_MATRIX_PLUS_MEASURED_DEPENDENCE"
    n_players = 0
    for l in other:
        ratio = 1.0
        if l["kind"] == "player" and goal:
            # Measured against the FIRST goal leg; conditioning on the whole goal block is not
            # something the pairwise table can express, so this is deliberately conservative.
            ratio = dep.get((l["market"], goal[0]["key"]), 1.0)
        elif l["kind"] == "team_card":
            flags.append("CARD_DEPENDENCE_EMPIRICAL_ONLY")
        if l["kind"] == "player":
            n_players += 1
        p *= float(l["p"]) * float(ratio)
    if n_players >= 2:
        flags.append("MULTI_PLAYER_INDEPENDENCE_ASSUMED")
    return float(min(max(p, 0.0), 1.0)), src, sorted(set(flags))
