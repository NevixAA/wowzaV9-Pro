Monthly bankroll evidence review, evidence cutoff 2026-11-01.

**Only `config/bankroll_policy.json` changes.** No model, threshold, selection or prediction change.
Human approval required before this policy is used.

- Current policy: `balanced-2026-10-13+nf-under-paper-2026-11-02+league-rating-off-2026-11-02`
- Proposed policy: `balanced-2026-10-13+nf-under-paper-2026-11-02+league-rating-off-2026-11-02+review-2026-11` (CURRENT_WITH_RISK_REDUCTIONS_ONLY)
- Allocator walk-forward: NOT_VALIDATED_INSUFFICIENT_MONTHS

### Changes
- none

### Evidence by changed track

### Unchanged tracks
new_format|BTTS, new_format|OU25_OVER, new_format|OU25_UNDER, new_format|OVER15, standard|OU25_OVER, standard|OU25_UNDER, standard|BTTS, standard|OVER15, new_format|OVER35, standard|OVER35, player_props

### Stress (recommended)
- NORMAL_HISTORY: +37.5%, max DD 8.2%
- EX_ARGENTINA: +14.6%, max DD 3.9%
- EX_BEST_LEAGUE (Argentina Primera Division): +14.6%, max DD 3.9%
- EX_BEST_MONTH (2026-09): +15.2%, max DD 8.2%
- EX_5_LARGEST_WINS: +27.1%, max DD 9.1%
- HAIRCUT_2.5PCT: +29.8%, max DD 8.3%
- HAIRCUT_5PCT: +23.3%, max DD 8.4%
- ODDS_CAPPED_TIGHTER: +27.3%, max DD 8.5%

Source: wowzaV9-Pro `output/bankroll/` (current_policy_recommendation.json, policy_candidates.csv, stress_tests.csv, walk_forward.csv).

PRODUCTION_SELECTION_LOGIC_CHANGED = NO · PREDICTION_THRESHOLDS_CHANGED = NO · PLAYER_PROP_REAL_STAKING_ENABLED = NO
