# League-level inputs (A) and market-anchored (B) challengers — Nov 2026

Owner request 2026-11-01 ("do both"). Research only: v9 main, `predict.yml` and the serving models are unchanged.
Nothing here is registered as promotable.

## What was tested

| Arm | What it is |
|---|---|
| CHAMPION | the model as served (same trainer, features, weights, four chronological blocks) |
| A_LEAGUE | the same, plus as-of league-level inputs: league goals per game and Over 1.5 / 2.5 / 3.5 / BTTS rates over the league's last 100 and 300 matches, and season-to-date goals. Strictly earlier dates only — tests prove a row never sees its own day or the future (`v9 tests/test_league_level.py`). |
| B_CHAMP / B_LEAGUE | anchored to the market: `y ~ logit(entry price) + logit(model)`, refitted each month on earlier rows only |
| MARKET | the de-vigged two-sided ENTRY price |

- **Holdout:** the newest 20%, untouched (about Oct 2025 to Oct 26, 2026). Live rows are from 2026-09-01.
- **Tracks:** results are per track and never pooled.
- **Tips:** simulated with production's edge rule at the deployed `predict.yml` thresholds (VALUABLE 0.03, MARKSMAN 0.08, SNIPER cap 0.12; side markets 0.04 / 0.08 / 0.10 with production's `/1.08` rule), at the same entry prices.

**Prices, real and entry only:**
- Standard O/U uses football-data non-C columns.
- Standard side markets use v9's side-market capture, first pre-kickoff quote, with summer 2026 dropped.
- New Format uses `newformat_odds_history.csv`, also with summer 2026 dropped. Rows with a negative two-way margin (best-of-books) are excluded: 420 for O/U.
- New Format O1.5 / O3.5 use the forward capture only.
- Standard O1.5 / O3.5 have prices only from the live period (never backfilled).

**Data defect found on the way.** In `newformat_odds_history.csv`, the "over15" prices have a median of 1.66 in the backfill and 1.57 in summer 2026, against 1.20 in the trusted forward capture. The summer "over25" has a median of 2.20 (mean 2.77). These are not full-match lines.
- The first CI run (41293196146) used them and showed New Format Over 3.5 at +90% ROI. **Those New Format side-market numbers are void.**
- The re-run (41293822136) excludes them. Every number below is from the re-run.

## Verdict per track × market

Log loss is per row; lower is better. Δ is the challenger minus the champion, with a 95% matchday-block interval.

| Market | Track | A vs champion (holdout) | League spread: actual / champ / A | Champion vs market (priced) | B vs market | Tips at real prices, holdout (live from Sep 1) |
|---|---|---|---|---|---|---|
| O/U 2.5 | Standard | **WORSE** +0.0010 [+0.0004, +0.0017]; live WORSE | 0.055 / 0.014 / 0.012 | loses (0.6872 vs 0.6789) | ties (0.6786) | Champion 1,753 tips −12.1% [−17.7, −6.9] (live 324, −12.3%); A −9.5% [−14.6, −4.0]; **B: 0 tips** |
| O/U 2.5 | New Format | no difference | 0.074 / 0.059 / 0.062 | loses on holdout, ties live | ties | Champion 1,372 tips (74% Under) −1.7% [−8.0, +4.5]; A +2.2% n.s.; B 221 tips (79% Over) +5.0% [−8.4, +18.5]; **live B: 5 tips** |
| BTTS | Standard | no difference (live WORSE) | 0.051 / 0.008 / 0.006 | loses | ties | Champion −1.2% (1,360); B_CHAMP +6.0% [0.0, +12.0] (784, all YES; live 102 tips +2.2%) — see note |
| BTTS | New Format | **BETTER** −0.0006 [−0.0011, −0.0001]; live n.s. | 0.060 / 0.010 / 0.010 | loses | ties | Champion +5.0% n.s. (938); **A +7.3% [+0.2, +14.4] (969)**; live A +7.7% n.s. (95) |
| Over 1.5 | Standard | no difference | 0.048 / 0.009 / 0.008 | loses | ties | all arms about 0% (154 / 46 tips) |
| Over 1.5 | New Format | **BETTER** −0.0011 [−0.0021, −0.0001] | 0.060 / 0.013 / 0.017 | loses | ties | Champion −1.0% (108); A +3.7% n.s.; B −1.6% (190) |
| Over 3.5 | Standard | **WORSE** +0.0017 [+0.0003, +0.0031] | 0.048 / 0.031 / 0.033 | loses | ties | Champion −4.7% (208); A +2.0% n.s.; B_LEAGUE −33.6% [−59, −1] (45) |
| Over 3.5 | New Format | no difference | 0.068 / 0.034 / 0.045 | loses | ties (B_LEAGUE loses) | Champion −14.2% (103), live −22.1%; **B: 0–3 tips** |

## What it means, plainly

1. **Giving the models the league's scoring level does not fix the flattening.**
   - On Standard O/U, A's spread between leagues is 0.012 against the champion's 0.014; the real spread is 0.055.
   - A is significantly *worse* on Standard O/U and Standard Over 3.5, and only marginally better on New Format BTTS and New Format Over 1.5.
   - So the information was never the problem. The base models have the league level in their inputs and still average it away.
   - Part of the "actual" spread is also sampling noise: with about 350 matches per league, a league's rate wobbles by about ±0.027. Even so, the true spread is about 0.048, still 3–4× the model's.
2. **Anchoring to the price makes the model about as good as the market, and that's all.** B ties the market on every market and track; its log loss sits within ±0.001 of the price. This repeats the October finding: the price already holds what the model knows.
3. **So B leaves almost no O/U tips:** Standard **0** (holdout and live), New Format 221 on the holdout but only **5** since Sep 1. The few New Format tips it does leave are mostly Overs and land +5% to +30% on samples far too small to mean anything.
4. **B's side-market "tips" are mostly an artefact of the production rule, not information.** The side-market rule is `edge = p − (1/odds)/1.08`, which assumes an 8% margin. Real BTTS margins are about 5–6%, so even the market's own de-vigged probability shows a 2–3% "edge" on every match. B's Standard BTTS tips (+6.0%) are short-priced YES bets, the same league pattern as the registered Serie B BTTS YES forward test (`H-BTTS-REGIME-SB`), not model skill.
5. **The current Standard O/U model loses at real entry prices:** −12.1% over 1,753 holdout tips, with an interval that excludes zero, and −12.3% live.

## Recommendation

- **Do not switch to A or B anywhere.**
- The only weak lead is **New Format BTTS with league inputs** (A +7.3% on 969 holdout tips, interval just above zero; live +7.7% on 95 tips). If you want it pursued, it belongs in a frozen forward test with a blind-YES control, not in production.

## Provenance

- **v9** `research/league-level-and-anchor-2026-11`:
  - `9c22d8cf0`: `src/league_level.py`, `tests/test_league_level.py`, `scripts/league_anchor_benchmark.py`
  - `9961a783f`: invalid New Format historical side prices dropped
- **Pro** `research/league-level-and-anchor-2026-11`:
  - `b21ab152`: workflow and collector
  - `9f753679`: CI results in `output/studies/league_anchor/{verdict.csv, tips.csv, summary.json, raw/}`
- **CI runs:**
  - 41293196146 succeeded, but its New Format side-market numbers are void (bad prices).
  - **41293822136** succeeded and is authoritative.
