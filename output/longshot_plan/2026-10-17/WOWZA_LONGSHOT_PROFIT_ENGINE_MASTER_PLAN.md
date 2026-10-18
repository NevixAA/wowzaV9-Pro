# WOWZA LONGSHOT PROFIT ENGINE — MASTER PLAN

Evidence to 2026-10-17 · first-sight bets · plan only, nothing wired into production.

> NEVER STOP LEARNING. `BET_ENABLED` decides only where real money may go. Every league keeps collecting, predicting, settling, CLV, V11, Pro research and retraining data exactly as today, and every bet a gate blocks stays paper-tracked.

## 1. Executive summary
- Walk-forward (flags set on data before each month, frozen, then scored): blocked bets made **+28.02u** in total — gross losses avoided 350.00u, gross wins forgone 378.02u. A negative blocked total means the filter helped.
- ALL NON-MLS (all tiers): N 807, PnL +43.56u, ROI +5.4%, max DD 19.5u
- ALL CORE: N 428, PnL +29.99u, ROI +7.0%, max DD 21.0u
- ALL NEW_FORMAT: N 501, PnL +61.48u, ROI +12.3%, max DD 16.4u
- NEW_FORMAT BTTS: N 158, PnL +34.05u, ROI +21.5%, max DD 5.0u
- CURRENT BALANCED POLICY: N 250, PnL +45.02u, ROI +18.0%, max DD 7.1u
- SNIPER ONLY: N 195, PnL +19.55u, ROI +10.0%, max DD 10.0u
- LONGSHOT ENGINE (walk-forward kept): N 108, PnL +15.53u, ROI +14.4%, max DD 7.6u
- LONGSHOT ENGINE, core tiers only: N 71, PnL +5.24u, ROI +7.4%, max DD 10.2u
- Top Picks VALUE (tip_ranker backtest, top 5/day, own window): N 180, PnL +21.06u, ROI +11.7%
- Top Picks SHORTEST_ODDS (tip_ranker backtest, top 5/day, own window): N 180, PnL +15.84u, ROI +8.8%
- **VERDICT: FILTER_BEATS_SIMPLE_BASELINES = NO.** Return/drawdown: engine 2.03 vs best simple baseline 'NEW_FORMAT BTTS' 6.81. By section 32 the gate filter is NOT adopted; the flags below are candidates to keep evaluating monthly, not decisions.
- Walk-forward covers only 2 months: treat it as the first check, not proof. NEXT STEP: keep the walk-forward running monthly before any real staking change.

## 2-3. Profit map / loss map
See CURRENT_WINNERS / CURRENT_LOSERS sheets (cells N>=30 ranked by evidence score).

## 4. League bet eligibility
- TRUE candidates: ['Serie B', 'Brazil Serie A', 'Finland Veikkausliiga', 'Mexico Liga MX', 'Denmark Superliga', 'Argentina Primera Division', 'Japan J-League', 'Sweden Allsvenskan']
- FALSE candidates: ['La Liga 2', 'Norway Eliteserien', 'League Two', 'League One']
- REVIEW (not enough evidence; stays as today): ['Bundesliga 2', 'Championship', 'China Super League', 'Ligue 2', 'Dutch Eredivisie', 'Austrian Bundesliga', 'Belgian First Division A', 'Turkish Super Lig', 'Ireland Premier Division', 'Poland Ekstraklasa']

## 5-8. Model / market / side / odds eligibility
- model|market FALSE: ['standard | OU25']
- side FALSE: ['standard | OU25 | OVER', 'standard | OU25 | UNDER']
- odds band FALSE: ['new_format | OVER15 | 1.60-1.79', 'new_format | OU25 | 2.50-2.74', 'standard | OU25 | 1.80-1.99', 'new_format | OU25 | 3.00-3.49', 'standard | OU25 | 2.00-2.24']

## 9. Cell-level eligibility
CELL_BET_FLAGS sheet: league x model x market x side, the narrowest justified restriction.

## 10-11. Profit evidence score and shrinkage
Documented in the module docstring and the PROFIT_EVIDENCE_SCORE sheet: shrunk ROI (K=100 toward break-even) leads, raw ROI never decides alone; +50% at n=10 scores far below +8% at n=300.

## 12. V11 confirmation
League gates add V11 toward-minus-placebo and residual; a league is not 'strong' because toward > 50%.

## 13-14. Portfolio and staking bands
One real position per fixture (highest evidence gate wins; the others stay paper). Stake bands 0-2% by evidence score (PORTFOLIO_PLAN). League rating (1-10) already scales stakes down; both stay under existing caps.

## 15. Walk-forward
WALK_FORWARD_PLAN sheet: month-by-month kept vs blocked; repeat every month; a filter that does not beat the simple baselines risk-adjusted is not adopted.

## 16. Paper tracking of disabled bets
FALSE_FLAG_PAPER_RESULTS: every blocked bet keeps probability, odds, result, flat PnL, CLV and the blocking gate.

## 17. Retrain re-enable engine
RE_ENABLE_CANDIDATES (priority): none yet. After every meaningful retrain, re-score all FALSE gates on chronological OOS evidence; candidate -> shadow -> owner approval.

## 18-19. Stress tests and season scenarios
STRESS_TEST_PLAN and SEASON_SCENARIOS sheets. These are run-rate scenarios, not forecasts. They assume observed volume and/or ROI persists and do not model future fixture calendar, market adaptation, injuries, model drift, variance, or regression to the mean.

## 20. Implementation architecture
Proposed `betting_eligibility.json` (one file, read by the staking layer only: v9 stake plan + wowza-exec). Collection, prediction, settlement, research and retraining never read it. Draft: betting_eligibility_PROPOSED.json.

## 21. Owner approval gates
Any TRUE/FALSE production change, any re-enable, any stake-band change: owner approval. The plan executes none.

## Hypotheses
- H1: new_format stronger than standard (core) — SUPPORTED
- H2: new-format BTTS is the strongest large track — SUPPORTED
- H3: new-format OU25 improved in the recent regime (before vs since 09-24) — SUPPORTED
- H4: standard OU25 is a major current drag — SUPPORTED
- H5: standard UNDER especially weak (vs standard OVER) — SUPPORTED
- H6: new-format OVER outperforms new-format UNDER — SUPPORTED
- H7: new-format OU25 at 2.25-2.49 especially strong (vs rest of NF OU25) — SUPPORTED
- H8: OU25 at 2.75+ (a) / 3.00+ (b) destructive (all tiers) — SUPPORTED
- H9: Japan/Mexico/Finland/Serie B show outcome+market convergence; V11 STRONG_CONVERGENCE = ['Brazil Serie A', 'Japan J-League', 'Mexico Liga MX', 'Serie B'] — PARTLY SUPPORTED
- H10: Argentina profit without V11 movement confirmation — V11 class MIXED, toward-minus-placebo +0.232
- H11: Championship / League One / League Two standard markets: BET_ENABLED=FALSE candidates — SUPPORTED

## Final summary
```
MASTER_PLAN_CREATED = YES
PRODUCTION_CHANGES_EXECUTED = NO
ALL_EXISTING_LEAGUES_CONTINUE_TRACKING = YES
ALL_EXISTING_LEAGUES_CONTINUE_DATA_COLLECTION = YES
ALL_EXISTING_LEAGUES_CONTINUE_RESEARCH = YES
HISTORICAL_DATA_REMOVED = NO
BET_ENABLED_FLAG_PLANNED = YES
FALSE_BETS_CONTINUE_PAPER_TRACKING = YES
FALSE_LEAGUES_CONTINUE_RETRAIN_DATA = YES
RETRAIN_CAN_TRIGGER_REENABLE_REVIEW = YES
MODEL_THRESHOLDS_CHANGED = NO
PREDICTION_LOGIC_CHANGED = NO
BANKROLL_CHANGED = NO

BET_ENABLED_TRUE_CANDIDATES = ['Serie B', 'Brazil Serie A', 'Finland Veikkausliiga', 'Mexico Liga MX', 'Denmark Superliga', 'Argentina Primera Division', 'Japan J-League', 'Sweden Allsvenskan']
BET_ENABLED_FALSE_CANDIDATES = ['La Liga 2', 'Norway Eliteserien', 'League Two', 'League One']
MODEL_MARKET_FALSE_CANDIDATES = ['standard | OU25']
SIDE_FALSE_CANDIDATES = ['standard | OU25 | OVER', 'standard | OU25 | UNDER']
ODDS_BAND_FALSE_CANDIDATES = ['new_format | OVER15 | 1.60-1.79', 'new_format | OU25 | 2.50-2.74', 'standard | OU25 | 1.80-1.99', 'new_format | OU25 | 3.00-3.49', 'standard | OU25 | 2.00-2.24']
RE_ENABLE_PRIORITY_CANDIDATES = []
FILTER_BEATS_SIMPLE_BASELINES = NO (best simple: NEW_FORMAT BTTS)
NEXT_STEP = WALK_FORWARD VALIDATE BET_ENABLED FILTER BEFORE TOUCHING REAL STAKING
```
