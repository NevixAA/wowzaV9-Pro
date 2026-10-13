"""Player Model V3 / Player-vs-Player Edge Lab — SHADOW RESEARCH ONLY.

Question: does Wowza hold player-specific information the bookmaker has not priced?
Built BESIDE v9's player model, never instead of it. Reads v9 read-only through V9_LOCAL.

RESEARCH CONTRACT (owner brief, 2026-10-13)
  * No v9 player selection, threshold, tier, settlement, eligibility or Fantasy behaviour changes.
    PRODUCTION_PLAYER_SELECTION_CHANGED must stay "NO".
  * Every hypothesis H1..H7 is tested separately, chronologically, with a proper scoring rule and an
    uncertainty interval. No random splits for evidence. No tuning on the holdout.
  * Every feature is built as-of match time: rolling stats are SHIFTED so the target match never
    feeds its own features. Leakage perturbation tests prove it (tests/test_player_v3_*.py).
  * Verdicts use only YES / NO / UNCLEAR / INSUFFICIENT_DATA. Recommendations only
    REJECT / KEEP_RESEARCHING / SHADOW_CHALLENGER / PROMOTION_CANDIDATE. Nothing is promoted here.
  * Accuracy is not edge: LEVEL 1-3 (prediction, calibration) never support a betting claim;
    an edge claim needs the MARKET baseline (LEVEL 4+), CLV (5), ROI (6), and persistence (7).

Phases (one commit each): A audit+contract · B minutes · C form+usage · D role/personnel ·
E SOT count model · F bookmaker consensus · G market residual · H ablation+calibration · I report.
"""
CALC_VERSION = "player_v3-0.1.0"

VERDICT_KEYS = (
    "DATA_LEAKAGE_SAFE", "EXPECTED_MINUTES_BEATS_CURRENT_HEURISTIC", "MULTI_HORIZON_FORM_HELPS",
    "USAGE_SHARE_HELPS", "ROLE_MODEL_HELPS", "OPPONENT_PERSONNEL_HELPS", "TRUE_MATCHUP_FEATURES_HELP",
    "SOT_COUNT_MODEL_BEATS_BINARY", "GOAL_COUNT_MODEL_BEATS_BINARY", "PLAYER_WOWZA_ADDS_TO_MARKET",
    "BEST_MARKET_FOR_INCREMENTAL_EDGE", "BEST_ROLE_MARKET_COMBINATION", "BEST_PLAYER_MATCHUP_SIGNAL",
    "CALIBRATION_IMPROVES", "PRODUCTION_PLAYER_SELECTION_CHANGED", "SAFE_TO_PROMOTE_V3",
)
VERDICT_VALUES = ("YES", "NO", "UNCLEAR", "INSUFFICIENT_DATA")
RECOMMENDATIONS = ("REJECT", "KEEP_RESEARCHING", "SHADOW_CHALLENGER", "PROMOTION_CANDIDATE")

# Chronological evidence split, fixed BEFORE any V3 result (2026-10-13). Season 2025/26 onward is
# the holdout; a validation block inside training is used for any tuning.
TRAIN_END = "2025-01-31"        # fit on everything before this
VALID_END = "2025-06-30"        # tune (k, dispersion, weights) on Feb-Jun 2025 only
HOLDOUT_FROM = "2025-07-01"     # never looked at while choosing anything
