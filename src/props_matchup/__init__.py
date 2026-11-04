"""Props matchup research track (owner approval 2026-11-04). SCAFFOLD ONLY.

    python -m src.props_matchup --check-readiness     # the data readiness gate; exit 1 while not ready
    python -m src.props_matchup --inventory           # counts of the real inputs, nothing else

THE QUESTION. For every player, league and props market (SoT 1+/2+, anytime goalscorer, ...): what
bar must a tip clear, and does the bookmaker under-price a player when the OPPOSING defence is
weakened - a key defender or the goalkeeper out through injury or suspension?

WHAT IS HERE (and what is deliberately not):
  inputs.py      readers for the real v9 / Pro inputs, every frame with explicit provenance
  features.py    matchup features with point-in-time correctness (a decision time per fixture)
  readiness.py   the data readiness gate: fail-closed, thresholds are OWNER decisions (None = unset)
  evaluation.py  walk-forward splitter, nested shrinkage bars, BH / BY / Holm, CLV and line-move tests

Owner rule (no-train-on-unclean-data): nothing in this package fits a model, backtests, or computes
an edge or ROI on real data. Only the readiness gate and the inventory read real data. The
statistics functions are exercised on synthetic data only (tests/test_props_matchup.py).
Design: reports/R_PROPS_MATCHUP_SPEC.md.
"""
from __future__ import annotations

#: Defensive unit of the opponent: player_history's per-match position letter (API-Football G/D/M/F).
DEFENSIVE_POSITIONS = ("G", "D")

#: Output contract of the (future) bar table. Nothing writes it yet; v9 would read it PAPER-only.
BAR_COLUMNS = ("market", "league", "role", "player_id", "n_bets", "n_matchdays", "posterior_mean",
               "posterior_sd", "bar", "q_value", "permission", "built_at", "data_gate_sha")

#: Permission values a bar row may carry. LIVE is not among them: real money needs the owner's
#: approval AFTER the Clean Record milestone evidence (milestone/2) and is granted outside Pro.
PERMISSIONS = ("BLOCKED", "PAPER")
