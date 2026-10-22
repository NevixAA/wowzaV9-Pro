"""Adaptive Bankroll Strategy System — evidence-driven monthly allocator (owner brief 2026-10-13).

    python -m src.bankroll.run            # monthly review -> output/bankroll/*

Not a prediction model. Each month it asks: given ONLY the evidence available now, what bankroll
exposure is justified for the next month? Slow to add risk (+0.25 pp per track per month at most,
multi-signal case required), fast to remove it (any amount, on any material deterioration).

Pro is the authority for evidence; v9 is the authority for execution. The monthly run writes a
versioned recommendation and, when a change is justified, opens a PR against wowza-betting that
touches ONLY config/bankroll_policy.json. v9 never fetches Pro at runtime.

Sizing uses v9's own reader (src/bankroll_policy.py, imported read-only via V9_LOCAL), so every
simulation stakes bets with exactly the code production would use.

Never changes: prediction logic, model selection, SNIPER/MARKSMAN/VALUABLE thresholds, the
Argentina BTTS pre-registration, promotion rules, ledgers, settlement, player-model behaviour,
V11 methodology. Never enables: player props, MLS (paper), Cloudbet REAL, stakes > 2%, daily
exposure > 7.5%, odds > 2.75, new markets.
"""
CALC_VERSION = "bankroll-1.0.0"

# Evidence epochs (project's own): tips before the cutoff predate fixes; the pipeline ran without a
# known defect only from RELIABLE_FROM (v9 src/allocation.py).
PERFORMANCE_CUTOFF = "2026-08-10"
RELIABLE_FROM = "2026-09-24"

STAKE_BANDS = (0.0, 0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015)    # 2% only as a final capped amount
MAX_AUTO_BASE = 0.015
MAX_MONTHLY_STEP_UP = 0.0025
STATE_BAND_LIMITS = {"PROBATION": 0.0025, "ACTIVE_LOW": 0.005, "ACTIVE": 0.0125,
                     "ACTIVE_STRONG": 0.015, "DEGRADED": 0.005}
HARD_BOUNDS = {"single_bet_cap": 0.02, "fixture_cap": 0.02, "daily_cap_min": 0.03,
               "daily_cap_max": 0.075, "daily_cap_increase_above": 0.06, "league_daily_cap": 0.04,
               "league_market_daily_cap": 0.03, "max_odds": 2.75, "blocked_odds": 3.0,
               "tier": {"SNIPER": (1.00, 1.25), "MARKSMAN": (0.75, 1.00), "VALUABLE": (0.00, 1.00)}, "convergence": (1.00, 1.20)}
SURVIVAL = {"p_dd20": 0.05, "p_below75": 0.05, "p_below50": 0.01}
