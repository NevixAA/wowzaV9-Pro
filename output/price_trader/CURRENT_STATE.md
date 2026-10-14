# Price Trader — CURRENT STATE (audit, 2026-10-14)

What V11 and the recorded price data can and cannot tell us about EXECUTABLE back-to-lay trading.

## What V11 measures
`wowza_v11/src/movement.py`: residual = p_model − p_market_entry; signed move = (p_close − p_entry) ×
sign(residual); toward_wowza = signed move > 0, on the DE-VIGGED CONSENSUS (fair) probability.
Its own docstring: signed movement IS closing-line value in fair-probability space, and "they diverge only
when CLV is computed from actual EXECUTABLE odds — the one that would decide whether any of this is
monetisable." Headline numbers (2026-10-13 artifacts):
* fixture-level, earliest entry: toward 55.3% (n 1,464), mean signed move +0.47 pp;
* FIXED-ANCHOR placebo, fixture-level: **57.2%** — i.e. the model-free anchor does at least as well;
* placebo table (snapshot level, 1,476 fixtures): v9 residual toward 27.6% vs fixed anchor 28.2%.
The per-league 65–75% figures are snapshot-level toward rates on fair probabilities; they are not trades.

## Recorded price data
| Source | What it has | What it lacks |
|---|---|---|
| v9 `book_odds_snapshots.csv` | 280k per-book quotes since 2026-08-19, OU15/OU25/OU35/BTTS, BOTH sides, 25 books incl. matchbook (41k) and betfair_ex_uk (1.1k); median 9 books and 17 snapshots per fixture-market | it is a CHANGE-LOG (carry forward per book); exchange rows are BACK prices only |
| v9 `standard/newformat_odds_history.csv`, `odds_history_v9.json` | consensus price paths | no per-book, no side detail |
| Exchanges | back prices on the opposite side (≈ a lay) for 19% of tips at entry | **no lay ladder, no matched volume, no depth** |
| Bookmaker limits | — | **none recorded** |

## Consequences
* A back-to-back DUTCH hedge (back Over early, back Under later — exact opposites) is fully testable on
  real recorded quotes. That is the lab's primary venue.
* Exchange hedging is testable only where an exchange back price was recorded (169 tips), with commission.
* LIQUIDITY and CAPACITY cannot be measured: every money result is THEORETICAL_ONLY on capacity.
* Wowza's signal time is its first tip (`generated_at`), a median 5.6 days before kickoff.
