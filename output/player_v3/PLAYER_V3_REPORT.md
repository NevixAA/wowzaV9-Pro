# Player Model V3 / Player-vs-Player Edge Lab — report

Shadow research in wowzaV9-Pro (`src/player_v3`), 2026-10-13/14. **PRODUCTION_PLAYER_SELECTION_CHANGED = NO.**
Verdicts are in `player_v3_verdict.json`, derived by rule from the result files (`src/player_v3/report.py`).

**Protocol.** One frozen chronological split, fixed before any result: train < 2025-02-01, calibrate
Feb–Jun 2025, score once on the holdout (>= 2025-07-01; 288,396 appearances). Learner = HGB with v9's
settings. Every variant is v9's own 138 features (BASE_V9) plus one family. Paired per-row log-loss
differences, 95% CI by matchday-block bootstrap. Leakage: future outcomes scrambled -> earlier
features identical, and a match never sees its own result (`tests/test_player_v3_*.py`).

## Headline

1. **Wowza adds information to the bookmaker (LEVEL 4).** On settled priced props (since 2026-06-28,
   all inside the holdout), market + Wowza beats the market alone on the later half of the record:
   goals −0.0066 [−0.0084, −0.0051] (n_test 14,633), SOT 1+ −0.0110 [−0.0173, −0.0051] (4,407),
   SOT 2+ −0.0074, SOT 3+ −0.0054; SOT 4+ unclear. It survives the hardest leak test: rebuilt from V3's
   own leak-proven features only (no v9 stored feature), the result holds (SOT 1+ −0.0116).
2. **It is not yet money (LEVEL 5 promising, LEVEL 6 not shown).** A fixed rule (combined
   probability x best entry odds > 1.05, weights fit on the earlier half) selects only 0.3–1% of props:
   43–65 bets per market. ROI intervals include zero. But those bets beat the closing price far more than
   props in general: median CLV +6% to +16% and 61–77% beating the close, against 0 and 38–48% for all
   props.
3. **The biggest single improvement is v9's calibration form, not a feature.** v9 fits Platt scaling on
   the raw probability; fitting it on the log-odds improves every SOT line by 0.0025–0.0073 log loss —
   more than every V3 feature family together — and fixes over-confidence at the top: v9's top-5% SOT
   predictions say 65.7%, reality is 60.5%. v9's TEAM models use the same form (`src/model.py`), which
   is a candidate explanation for the "O/U model compressed ~52%" finding. Not changed here.

## The ten questions

1. **Does modelling expected minutes separately help?** Yes, twice. The dedicated minutes model beats the
   v9 view by a wide margin (start Brier 0.144 vs 0.273), and adding its outputs to the SOT model improves
   holdout log loss by −0.0012 [−0.0014, −0.0010]. The ablation keeps it as a needed family.
2. **Does usage/share add more than raw rolling stats?** On its own, yes (−0.0011). Inside the full model
   it is redundant once shrunk form and team environment are present — the team-environment part
   (the team's own SOT/shots rate, and the opponent's) is the piece that carries.
3. **Does projected defender/GK personnel add more than team aggregates?** No measurable difference
   (−0.00005, CI includes zero). Verdict UNCLEAR, practically nil.
4. **Which player-vs-player interactions are predictive OOS?** None found. Raw attacker x projected-unit
   pairs add nothing (UNCLEAR). Side-specific matchups (winger vs full-back) cannot be built: the data has
   G/D/M/F only, no lineup positions.
5. **Does a coherent SOT count distribution beat separate classifiers?** Yes, modestly, against
   properly calibrated classifiers: HGB mean + Negative Binomial wins on every line (1+ −0.0002,
   2+ −0.0003, 3+ −0.0006, 4+ −0.0010) and can never price 2+ above 1+ (binary violations: 1.1%
   of holdout rows). Against v9's own calibration the gap is 10x larger, but that is calibration.
6. **Which SOT line is most mispriced?** By incremental information over the market: **1+**
   (−0.0110), then 2+ (−0.0074), 3+ (−0.0054); 4+ unclear (n 913).
7. **Does Wowza improve the market probability?** Yes (point 1). This is LEVEL 4 evidence only.
8. **Is the advantage concentrated?** One pre-registered cell (of 103) is positive after multiple-testing
   correction: forwards, anytime scorer, market < 30%, model > market by 5+ points — n 81, hit 34.6%
   vs 18.9% implied, CLV +8.7% (q = 0.031). Exploratory: found by searching, must be confirmed
   forward. 41 cells are significantly NEGATIVE (one-sided prop margins), 49 too small.
9. **Prediction, CLV, ROI?** Prediction: yes. Market residual: yes. CLV: promising on the few selected
   bets. ROI: not shown.
10. **Smallest feature set keeping nearly all the gain?** v9 base + shrunk form + team environment +
    expected minutes. Multi-horizon form, usage share, personnel, matchup pairs, role and v9's 24
    handcrafted composites are REDUNDANT_IN_V3_CHALLENGER (composites stay in v9 untouched).

## Evidence levels

| Level | Result |
|---|---|
| 1 better than naive | YES |
| 2 better than current Wowza | YES (ALL_V3 −0.0042 on SOT 1+) |
| 3 better calibration | YES vs v9's Platt form; no gain beyond a log-odds Platt |
| 4 improves the market probability | YES (goals, SOT 1+/2+/3+) |
| 5 positive CLV | PROMISING (small n) |
| 6 executable ROI | NOT SHOWN |
| 7 persists prospectively | NOT TESTED — needs the forward test below |

## Limits

* Prices are OVER only, 3 books, median 1 book, since 2026-06-28: the "market" is a recalibrated
  one-sided implied price, not a two-way de-vigged consensus. Under prices would make this much stronger.
* Assists and cards were not evaluated in this pass; the goals count model was not built.
* Settlement uses appearances (void if the player did not take part), matched by date + league +
  initial-surname with ambiguous names refused.

## Recommendation

**SHADOW_CHALLENGER** — not promotion. Concretely, for owner decision:
1. Pre-register the market-residual rule (and the one exploratory cell) as a forward paper test, like
   `PROPS_SEGMENTS.md`, judged on future props only.
2. A v9 logging hook to store Under prices and per-book quotes (no behaviour change).
3. Test the log-odds Platt form on v9's player AND team models in Pro as its own challenger.

SAFE_TO_PROMOTE_V3 = NO (by contract: LEVEL 1–4 evidence never promotes; the owner decides).
