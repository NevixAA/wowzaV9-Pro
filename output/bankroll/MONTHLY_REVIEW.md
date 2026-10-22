WOWZA MONTHLY BANKROLL REVIEW

Evidence cutoff: 2026-10-21
Current policy: balanced-2026-10-13
Recommended policy: balanced-2026-10-13+review-2026-10 (CURRENT_WITH_RISK_REDUCTIONS_ONLY)
Walk-forward: NOT_VALIDATED_INSUFFICIENT_MONTHS (2 of 6 months)

Portfolio:
- daily_cap: 6.00% -> 6.00%
- fixture_cap: 2.00% -> 2.00%
- league_daily_cap: 3.00% -> 3.00%
- league_market_daily_cap: 3.00% -> 3.00%

Tracks:
- new_format|BTTS: 1.25% -> 1.25% KEEP (ACTIVE)
- new_format|OU25: 0.50% -> 0.50% KEEP (ACTIVE_LOW)
- new_format|OVER15: 0.50% -> 0.50% KEEP (ACTIVE_LOW)
- standard|OU25: 0 -> 0 KEEP_PAPER (PAPER)
- standard|BTTS: 0 -> 0 KEEP_PAPER (PAPER)
- standard|OVER15: 0 -> 0 KEEP_PAPER (PAPER)
- new_format|OVER35: 0 -> 0 KEEP_BLOCKED (BLOCKED)
- standard|OVER35: 0 -> 0 KEEP_BLOCKED (BLOCKED)
- player_props: 0 -> 0 KEEP_BLOCKED (BLOCKED_FROM_REAL)

Convergence leagues: none qualify

Expected historical / stress profile (recommended policy):
- NORMAL_HISTORY: return +42.5%, max DD 4.9%
- EX_ARGENTINA: return +22.0%, max DD 2.6%
- EX_BEST_LEAGUE (Argentina Primera Division): return +22.0%, max DD 2.6%
- EX_BEST_MONTH (2026-09): return +22.3%, max DD 3.9%
- EX_5_LARGEST_WINS: return +32.6%, max DD 4.9%
- HAIRCUT_2.5PCT: return +34.1%, max DD 5.2%
- HAIRCUT_5PCT: return +26.2%, max DD 5.6%
- ODDS_CAPPED_TIGHTER: return +27.8%, max DD 7.9%
- proposed adaptive: P(DD>20%) 0.0%, median end 146.47

BEST_GROWTH_POLICY = G_PROPOSED_ADAPTIVE
BEST_SURVIVAL_POLICY = E_SAFE
POLICY_CHANGE_RECOMMENDED = NO

Evidence panel (reported only - does not feed the allocator):
- PRICE_TRADER_STAKES_ALLOWED: NO
- PLAYER_V3_STAKES_ALLOWED: NO
- RATING_MAY_INCREASE_STAKE_ABOVE_BASE: NO (league rating scales down only; any increase needs owner approval)
- N: 1244
- realized_ROI: 0.0264
- shrunk_ROI_K200: 0.0227
- avg_CLV: 0.0012
- max_drawdown_units: 33.43
- risk_adjusted_PnL_over_DD: 0.982
- league_concentration_top_share: 0.309
- market_concentration_top_share: 0.899
- v11_residual_rows: 20
- price_trader_state: COLLECTING
- player_v3_forward_state: COLLECTING

PRODUCTION_SELECTION_LOGIC_CHANGED = NO
PREDICTION_THRESHOLDS_CHANGED = NO
PLAYER_PROP_REAL_STAKING_ENABLED = NO
