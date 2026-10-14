# Wowza Price Trader / Arbitrage Lab — report (2026-10-14)

Research only. PRODUCTION_SELECTION_CHANGED = NO · REAL_TRADING_ENABLED = NO · CURRENT_STAKING_CHANGED = NO.
Code: `src/price_trader/` (hedge maths unit-tested; trades and price paths from recorded quotes only).

## The question
If Wowza backs at the moment its signal exists, at a price that really existed, can the position later be
greened at a price that really existed, for a positive locked profit after costs — better than controls?

## Answer: NO, on the data we have

| Level of the hierarchy | Result |
|---|---|
| Toward Wowza | **41.5%** of 934 trades (the price of Wowza's side moved away more often than toward) |
| Beats placebo | **No** — Wowza minus fixed-anchor −0.35 pp per trade, 90% CI [−0.65, −0.08] |
| Move large enough | **No** — favourable moves average +3.7%, the two-way bookmaker margin at entry is 5.3% (median), adverse moves −10.6% |
| Executable price | yes for the bookmaker dutch (real quotes); exchange only for 169 tips |
| Liquidity | not measurable — THEORETICAL_ONLY |
| Survives commission | **No** — exchange route −5.6% at 0%, −6.5% at 2%, −8.0% at 5% |
| Survives slippage | **No** — already negative before any deterioration |
| Positive locked ROI | **No** — FULL_GREEN, every pre-registered exit rule: −9.6% to −10.6% per trade; green rate 1–8% |
| Chronological holdout | **No** — no league × market qualified on the training third; holdout all-signals −10.7% |
| Prospective | paper engine running from 2026-10-15 |

* **HOLD_TO_RESULT** (no hedge): +1.9% per bet, CI includes zero. Partial greens are worse than holding.
* **Entry timing:** 12–48 h before kickoff greens most often (17–19%) but still loses on average.
* **Japan / Mexico special study:** Japan J-League OU25 toward 34.6%, Wowza −1.1 pp per trade vs placebo;
  Mexico Liga MX OU25 toward 45.5%, −0.2 pp. The V11 74–75% figures do not survive as executable trades:
  they measure fair-probability movement across many snapshots, not a trade entered at the real signal.
* **Instant arbitrage** (separate business): both sides coverable at a profit on **1.0%** of 48,466
  bookmaker snapshots, median margin 0.84%, before stake limits — THEORETICAL_ONLY until limits are known.

## What would change this
1. Exchange lay ladders with matched volume (Betfair/Matchbook API) — the dutch route pays the full 5%
   bookmaker margin; an exchange hedge pays ~1–2%. Even then the exchange sample here loses at 0% commission.
2. Entering later (the signal re-evaluated at 12–48 h) rather than at the first tip.
3. Two-way exchange data would let the paper engine test the brief's exact back-to-lay mechanics.

## Verdict
`price_trader_verdict.json`: MOVEMENT_SIGNAL_EXISTS NO · MOVEMENT_BEATS_PLACEBO NO · FULL_GREEN_PROFITABLE_AFTER_COSTS NO ·
TRADING_BEATS_HOLD NO · EXECUTABLE_PRICE_DATA_SUFFICIENT NO · PROSPECTIVE_CONFIRMATION INSUFFICIENT_DATA.
This is the brief's valid negative: "toward rate is high, but fixed-anchor placebo performs equally well" and
"moves too small to overcome trading costs". Outcome edge (signal A) and price-discovery edge (signal B) are
independent; this lab finds no B. Recommendation: keep the paper engine running; do not build execution.
