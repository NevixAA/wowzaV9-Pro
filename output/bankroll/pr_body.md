Monthly bankroll evidence review, evidence cutoff 2026-10-25.

**Only `config/bankroll_policy.json` changes.** No model, threshold, selection or prediction change.
Human approval required before this policy is used.

- Current policy: `balanced-2026-10-13`
- Proposed policy: `balanced-2026-10-13+review-2026-10` (CURRENT_WITH_RISK_REDUCTIONS_ONLY)
- Allocator walk-forward: NOT_VALIDATED_INSUFFICIENT_MONTHS

### Changes
- new_format|OU25_UNDER.state: ACTIVE_LOW -> STOPPED
- new_format|OU25_UNDER.base_fraction: 0.005 -> 0.0

### Evidence by changed track
- **new_format|OU25_UNDER** STOP: n=402, ROI -0.0038, shrunk -0.0202, 90% [-0.1063, 0.1026], CLV 0.0; shrunk ROI -2.0% on n=402

### Unchanged tracks
new_format|BTTS, new_format|OU25_OVER, new_format|OVER15, standard|OU25_OVER, standard|OU25_UNDER, standard|BTTS, standard|OVER15, new_format|OVER35, standard|OVER35, player_props

### Stress (recommended)
- NORMAL_HISTORY: +33.4%, max DD 8.2%
- EX_ARGENTINA: +12.7%, max DD 3.9%
- EX_BEST_LEAGUE (Argentina Primera Division): +12.7%, max DD 3.9%
- EX_BEST_MONTH (2026-09): +11.8%, max DD 8.2%
- EX_5_LARGEST_WINS: +24.0%, max DD 8.2%
- HAIRCUT_2.5PCT: +27.0%, max DD 8.3%
- HAIRCUT_5PCT: +20.8%, max DD 8.4%
- ODDS_CAPPED_TIGHTER: +26.6%, max DD 8.2%

Source: wowzaV9-Pro `output/bankroll/` (current_policy_recommendation.json, policy_candidates.csv, stress_tests.csv, walk_forward.csv).

PRODUCTION_SELECTION_LOGIC_CHANGED = NO · PREDICTION_THRESHOLDS_CHANGED = NO · PLAYER_PROP_REAL_STAKING_ENABLED = NO
