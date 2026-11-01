# Log-odds calibration challenger — November 2026

**Research only. Production unchanged. Nothing here is promotable.**
Owner request 2026-11-01. CI run `41291787056` (Pro branch `research/logit-calibration-2026-11`, commit `7bb370c7`),
v9 code on `research/logit-calibration-2026-11` (`ac0aadd82`). Data: `output/studies/logit_calibration/`.

## The question

v9's team models give almost the same Over chance in every league. On the repaired Standard O/U model
the league averages vary 0.014 while reality varies 0.055. Platt calibration and the final blend are
logistic regressions on *probabilities*, which can squeeze predictions toward 50%. Does fitting them on
*log-odds* instead ("logit") fix the flattening?

## How it was tested

For each model as it serves (Standard O/U on the repaired recipe; New Format O/U and the side markets
on legacy features, side markets trained pooled across tracks as production does), both versions were
trained by v9's own trainer on **identical** chronological blocks: base fit, calibration, blend, then
an **untouched holdout** (newest 20%, roughly Sep/Oct 2025 to 26 Oct 2026). The only difference is the
calibration space. Every result is reported **per track**, never pooled. "Live" = holdout rows from
2026-09-01 (August 2026 had a production bug), descriptive only.

Verdict rule, fixed before results: holdout log-loss difference (logit − prob), 95% matchday-bootstrap
CI below 0 = LOGIT_BETTER, above 0 = LOGIT_WORSE, otherwise NO_DIFFERENCE.

## Results (holdout)

| Model | Track | n | Log loss prob → logit | Verdict | League spread: actual / market / prob / logit | League slope prob → logit |
|---|---|---|---|---|---|---|
| O/U 2.5 | Standard | 6,238 | 0.6875 → 0.6867 (CI −0.0016…+0.0001) | NO_DIFFERENCE | 0.055 / 0.046 / 0.014 / 0.021 | 3.07 → 2.10 |
| O/U 2.5 | New Format | 8,077 | 0.6774 → 0.6775 | NO_DIFFERENCE | 0.074 / 0.074 / 0.059 / 0.067 | 1.23 → 1.08 |
| BTTS | Standard | 8,426 | 0.6894 → 0.6898 | NO_DIFFERENCE | 0.051 / – / 0.008 / 0.011 | 3.67 → 2.73 |
| BTTS | New Format | 6,717 | 0.6856 → 0.6859 | NO_DIFFERENCE | 0.060 / 0.055 / 0.010 / 0.014 | 4.50 → 3.43 |
| Over 1.5 | Standard | 8,426 | 0.5517 → 0.5524 | NO_DIFFERENCE | 0.048 / – / 0.009 / 0.012 | 4.25 → 3.11 |
| Over 1.5 | New Format | 6,717 | 0.5389 → 0.5389 | NO_DIFFERENCE | 0.060 / 0.092 / 0.013 / 0.017 | 4.06 → 3.25 |
| Over 3.5 | Standard | 8,426 | 0.6026 → 0.6043 (CI +0.0009…+0.0025) | **LOGIT_WORSE** | 0.048 / – / 0.031 / 0.034 | 1.21 → 1.10 |
| Over 3.5 | New Format | 6,717 | 0.6055 → 0.6053 | NO_DIFFERENCE | 0.068 / 0.066 / 0.034 / 0.039 | 2.03 → 1.79 |

League slope = how far reality moves per point the model's league average moves (1.0 = right; 3 = the
model's league differences are a third of the real ones).

## What it means, in plain words

1. **Log-odds calibration is not the fix.** It never improves accuracy significantly, and it makes
   Standard Over 3.5 slightly worse. It widens the league spread a little (Standard O/U 0.014 → 0.021)
   but leaves most of the gap: reality 0.055.
2. **The flattening comes from the base models, not mainly the calibration step.** On the Standard O/U
   holdout the served model's calibration slope is 1.95 — its probabilities need stretching about 2×
   to be right. Logit calibration brings that to 1.19 (better calibrated) without moving accuracy,
   because the base models' raw outputs already carry too little league-level difference. The earlier
   suggestion (2026-11-01) that the probability-scale Platt formula was the main cause is refuted.
3. **The bookmaker still beats every version.** Standard O/U holdout log loss: market 0.677, model 0.687
   (either version). Market + model does not beat market for Standard O/U. New Format O/U adds a little
   over the full holdout (gain +0.004, CI above 0) but not from 2026-09-01 (gain −0.006).
4. Standard side markets have no market price in the training frame (no football-data BTTS / O1.5 /
   O3.5 columns), so their residual test could not run; New Format side markets use a one-sided price
   with an assumed 6% margin — a proxy, not a real two-sided market.

## What a switch would change

Nothing worth switching for. Serving logit-calibrated models would leave tips almost unchanged on every
track and would not remove the Under/Over skews per league. **Recommendation: do not switch; keep the
`calibration_space` option on the research branch only.** The lever that remains untested is giving the
base models an explicit league-level input (or anchoring to the market price) — a separate study.
