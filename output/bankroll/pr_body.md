Monthly bankroll evidence review, evidence cutoff 2026-10-21.

**Only `config/bankroll_policy.json` changes.** No model, threshold, selection or prediction change.
Human approval required before this policy is used.

- Current policy: `balanced-2026-10-13`
- Proposed policy: `balanced-2026-10-13+review-2026-10` (CURRENT_WITH_RISK_REDUCTIONS_ONLY)
- Allocator walk-forward: NOT_VALIDATED_INSUFFICIENT_MONTHS

### Changes
- none

### Evidence by changed track

### Unchanged tracks
new_format|BTTS, new_format|OU25, new_format|OVER15, standard|OU25, standard|BTTS, standard|OVER15, new_format|OVER35, standard|OVER35, player_props

### Stress (recommended)
- NORMAL_HISTORY: +42.5%, max DD 4.9%
- EX_ARGENTINA: +22.0%, max DD 2.6%
- EX_BEST_LEAGUE (Argentina Primera Division): +22.0%, max DD 2.6%
- EX_BEST_MONTH (2026-09): +22.3%, max DD 3.9%
- EX_5_LARGEST_WINS: +32.6%, max DD 4.9%
- HAIRCUT_2.5PCT: +34.1%, max DD 5.2%
- HAIRCUT_5PCT: +26.2%, max DD 5.6%
- ODDS_CAPPED_TIGHTER: +27.8%, max DD 7.9%

Source: wowzaV9-Pro `output/bankroll/` (current_policy_recommendation.json, policy_candidates.csv, stress_tests.csv, walk_forward.csv).

PRODUCTION_SELECTION_LOGIC_CHANGED = NO · PREDICTION_THRESHOLDS_CHANGED = NO · PLAYER_PROP_REAL_STAKING_ENABLED = NO
