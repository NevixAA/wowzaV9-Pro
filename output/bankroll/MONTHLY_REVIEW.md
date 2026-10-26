WOWZA MONTHLY BANKROLL REVIEW

Evidence cutoff: 2026-10-25
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
- new_format|OU25_OVER: 0.50% -> 0.50% KEEP (ACTIVE_LOW)
- new_format|OU25_UNDER: 0.50% -> 0 STOP (STOPPED)
- new_format|OVER15: 0.50% -> 0.50% KEEP (ACTIVE_LOW)
- standard|OU25_OVER: 0 -> 0 KEEP_PAPER (PAPER)
- standard|OU25_UNDER: 0 -> 0 KEEP_PAPER (PAPER)
- standard|BTTS: 0 -> 0 KEEP_PAPER (PAPER)
- standard|OVER15: 0 -> 0 KEEP_PAPER (PAPER)
- new_format|OVER35: 0 -> 0 KEEP_BLOCKED (BLOCKED)
- standard|OVER35: 0 -> 0 KEEP_BLOCKED (BLOCKED)
- player_props: 0 -> 0 KEEP_BLOCKED (BLOCKED_FROM_REAL)

Convergence leagues: none qualify

Expected historical / stress profile (recommended policy):
- NORMAL_HISTORY: return +33.4%, max DD 8.2%
- EX_ARGENTINA: return +12.7%, max DD 3.9%
- EX_BEST_LEAGUE (Argentina Primera Division): return +12.7%, max DD 3.9%
- EX_BEST_MONTH (2026-09): return +11.8%, max DD 8.2%
- EX_5_LARGEST_WINS: return +24.0%, max DD 8.2%
- HAIRCUT_2.5PCT: return +27.0%, max DD 8.3%
- HAIRCUT_5PCT: return +20.8%, max DD 8.4%
- ODDS_CAPPED_TIGHTER: return +26.6%, max DD 8.2%
- proposed adaptive: P(DD>20%) 0.0%, median end 134.78

BEST_GROWTH_POLICY = G_PROPOSED_ADAPTIVE
BEST_SURVIVAL_POLICY = E_SAFE
POLICY_CHANGE_RECOMMENDED = YES
Changes:
  - new_format|OU25_UNDER.state: ACTIVE_LOW -> STOPPED
  - new_format|OU25_UNDER.base_fraction: 0.005 -> 0.0

Evidence panel (reported only - does not feed the allocator):
- PRICE_TRADER_STAKES_ALLOWED: NO
- PLAYER_V3_STAKES_ALLOWED: NO
- RATING_MAY_INCREASE_STAKE_ABOVE_BASE: NO (league rating scales down only; any increase needs owner approval)
- N: 1497
- realized_ROI: -0.0064
- shrunk_ROI_K200: -0.0056
- avg_CLV: -0.0007
- max_drawdown_units: 37.55
- risk_adjusted_PnL_over_DD: -0.254
- league_concentration_top_share: 0.282
- market_concentration_top_share: 0.912
- v11_residual_rows: 20
- price_trader_state: COLLECTING
- player_v3_forward_state: COLLECTING

PRODUCTION_SELECTION_LOGIC_CHANGED = NO
PREDICTION_THRESHOLDS_CHANGED = NO
PLAYER_PROP_REAL_STAKING_ENABLED = NO
