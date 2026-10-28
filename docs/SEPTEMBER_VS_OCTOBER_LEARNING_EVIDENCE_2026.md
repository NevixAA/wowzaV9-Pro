# SEPTEMBER 2026 vs OCTOBER 2026 LEARNING EVIDENCE REPORT

Generated 2026-10-28T08:50:03Z by `python -m src.studies.monthly_learning` (calc 1.0.0). Data read from GitHub `origin/main` after `git fetch`: v9 `7317a9bd0983` (2026-10-28T07:30:04Z), wowza_v11 `b2edc05ac986` (2026-10-27T23:53:15Z); Pro `4203992ebf44`. ANALYSIS ONLY - nothing in production was changed.

Comparison A: September 1-30 vs October 1-27 (latest settled October match date 2026-10-27). Comparison B (reliable evidence): September 24-30 vs the same October window. `RELIABLE_FROM = 2026-09-24` is defined in v9 src/allocation.py:52 RELIABLE_FROM = "2026-09-24" (mirrored in Pro src/bankroll/__init__.py:26): it is the date from which the pipeline ran without a KNOWN defect. A and B are reported side by side and never mixed. Money is flat 1-unit stakes at the FIRST-LOGGED price (P/L in units).

## Plain-English summary

* **Did October make more money than September?** On the raw tip ledger, yes on the point estimate, but not provably. All O/U 2.5 tips: September -7.2% ROI on 396 bets (-28.36u); October -1.6% on 412 bets (-6.48u). The change is +5.6%, 90% interval [-8.1%, +17.7%] - the interval includes zero, so October is not demonstrably better. Every market together (genuine prices only): September -0.7% on 642, October -0.2% on 618, change +0.4% [-10.3%, +11.7%].
* **The one change that IS statistically clear is a deterioration:** New Format BTTS went from +27.7% (n 104) to -4.3% (n 107), change -32.1% [-54.5%, -7.7%]. Argentina alone accounts for -16.91u of the -33.47u swing (+40.7% -> +4.3%, n 47/52); the October studies had already shown Argentina BTTS to be a league regime, not model skill.
* **Forecast quality did not measurably improve.** On every O/U 2.5 fixture v9 published (not only tips), v9's log loss changed by +0.0092 on Standard and -0.0075 on New Format (lower is better; both 95% intervals include zero), and the bookmaker's own de-vigged price stayed better than the model in both months.
* **What clearly improved is the machinery that decides what to trust.** Retrain promotions fell from 60/63 (95%) in September to 39/56 (70%) in October; promotions of a model whose own holdout got WORSE fell from 20 to 9; and under the strict PG-1.0 gate (from 2026-10-25) 0 of 7 retrains reached production. Certified closing-price coverage went from 7.8% (October, before the collector fix) to 70.6% after it. 19 of the 20 evidence capabilities listed in section 18 first landed in October; 1 in September.
* **Standard results are PRE_REPAIR evidence.** They come from a pipeline with known data defects (section 2). A bad Standard month is not proof the model idea fails, and a better month is not proof it was fixed.

**Worked example - why one bad month is not 'the model is broken'.** League One O/U 2.5, Sep 1-10-27: 57 settled tips, 17 won. The bookmaker's own prices, after removing a ~5% margin, implied about 25.6 wins. Getting 17 or fewer by chance has probability 0.014 - unusual, so League One is genuinely bad. But League One also carries the heaviest data defects in the Standard repair audit (alias collisions 36% of legacy rows; 80 team-sides whose rolling form contained a FUTURE match). The honest reading is 'a broken input pipeline produced bad tips here', which only the repaired-v9 rerun can separate from 'bad model idea'.

**Worked example - reading an interval.** October's O/U 2.5 ROI was +5.6% better than September's. The 90% interval [-8.1%, +17.7%] is built by re-drawing whole matchdays (a Saturday with 20 bets is one draw, not 20). Because it runs from a loss to a gain, the data cannot tell a real improvement from a lucky month.

## 19. Learning scorecard

| Area | September | October | Verdict |
|---|---|---|---|
| Main performance (all O/U 2.5 tips) | -7.2% on 396 (-28.36u) | -1.6% on 412 (-6.48u) | MIXED (change +5.6%, CI [-8.1%, +17.7%]) |
| New Format performance (all markets) | +4.5% on 373 (+16.83u) | +2.6% on 413 (+10.62u) | MIXED (OU25 better n.s.; BTTS significantly worse) |
| Standard (PRE_REPAIR) | OU25 -12.3% on 175 | OU25 -7.5% on 150 | MIXED - PRE_REPAIR, not structural evidence |
| Side markets (genuine prices) | NF BTTS +27.7%, NF O1.5 +0.8% | NF BTTS -4.3%, NF O1.5 +17.2% | DETERIORATED (NF BTTS CI excludes zero; others n.s.) |
| Prediction quality (OU25 log loss, all fixtures) | Std 0.6900 / NF 0.6857 | Std 0.6993 / NF 0.6782 | MIXED (no change outside noise; market still better) |
| CLV quality (measurement) | NOT MEASURABLE (no certified close stream; v91_shadow starts 2026-10-04) | T30 certified 7.8% pre-fix -> 70.6% post-fix | STRONGLY IMPROVED (measurement); CLV values themselves flat |
| Model promotion discipline | 60/63 promoted, 20 with worse holdout, no CI | 39/56 promoted, 9 with worse holdout; PG-1.0: 0/7 to production | STRONGLY IMPROVED |
| Data integrity | alias split fix (09-24); first-logged prices still overwritable | first-logged freeze, 1H-BTTS + synthetic-price exclusion, heartbeat, identity audit (Standard still unrepaired) | IMPROVED |
| Research quality | 1 evidence capability landed | 19 capabilities landed (shadow challenger, strict gate, first-sight stores, market-first shadow, weekly panel) | STRONGLY IMPROVED |
| Bankroll (Pro walk-forward) | ADAPTIVE +17.1%, BALANCED +16.5% | ADAPTIVE -0.4%, BALANCED +5.0% | DETERIORATED for managed policies (September made more); flat staking did better in October |

Verdict rule for performance rows: IMPROVED / DETERIORATED only when the 90% matchday-bootstrap interval of the Oct-Sep change excludes zero; otherwise MIXED. Process rows are judged on counts and dates in sections 8, 11 and 18.

## 20. Final questions

1. **Is there numerical evidence that WOWZA learned?** In its DECISION PROCESS, yes: promotion rate 95% -> 70%, worse-holdout promotions 20 -> 9, certified closes 7.8% -> 70.6%. In its PREDICTIONS and RESULTS, no change survives the matchday bootstrap except the NF BTTS deterioration.
2. **Strongest numbers.** Strict gate: 0 of 7 retrains reached production on 2026-10-25 (one PG-1.0 rollback). CLV certification 70.6% T30 / 60.3% T10 post-fix. Standard ex League One/Two OU25 -5.1% -> +5.1% (n 114/104, CI [-15.6%, +35.5%]) - directional only. NF O1.5 October +17.2% with ROI CI [+0.1%, +34.5%] on n 38 (small). H-MODEL-01 HGB on New Format: log loss -0.0208 vs champion, CI [-0.0689, -0.0056] on 105 fixtures / 5 matchdays.
3. **What did not improve.** Forecast quality vs the market (v9 still loses to the de-vigged price on log loss in both months); mean CLV of tips (-0.18% -> -0.18%); tier ordering (Big/Medium/Small gap is not monotonic in either month); NF BTTS; League One; the Standard HGB challenger.
4. **Was October more profitable?** Raw betting: point estimate yes (all OU25 -28.36u -> -6.48u; every market -4.30u -> -1.50u), not significant. Bankroll simulation: NO for the managed policies (ADAPTIVE +17.1% -> -0.4%, BALANCED +16.5% -> +5.0%), yes for flat staking. Forecast quality: no measurable change.
5. **Did New Format improve?** NF OU25 -3.1% -> +1.8% (change +4.9%, CI [-18.2%, +27.3%]); NF all markets +4.5% -> +2.6% (CI [-19.8%, +15.5%]); NF BTTS significantly worse. Net: NOT demonstrably improved.
6. **Did Standard improve? (PRE_REPAIR)** OU25 -12.3% -> -7.5% (CI [-14.9%, +25.3%]); forecast log loss slightly worse in October (+0.0092, CI includes zero). Not demonstrably; and pre-repair evidence cannot answer it - rerun OLD V9 vs REPAIRED V9 vs MARKET.
7. **Leagues that improved most (point estimate, n>=10 both months).** Bundesliga 2 OU25 -51.4% -> +54.7% (n 16/21, CI [+48.1%, +160.4%], TOO_SMALL); Austrian Bundesliga OU25 -64.4% -> -31.4% (n 12/11, CI [-38.6%, +93.5%], TOO_SMALL); Norway Eliteserien OU25 -22.5% -> +8.7% (n 10/19, CI [-49.4%, +109.4%], TOO_SMALL); Ligue 2 OU25 -24.7% -> -8.0% (n 11/11, CI [-58.4%, +98.3%], TOO_SMALL). Cells whose interval excludes zero on the upside: Bundesliga 2 OU25; cells that pass the sample floor AND the interval (IMPROVED): none.
8. **Leagues that deteriorated.** Argentina Primera Division BTTS +40.7% -> +4.3% (n 47/52, CI [-72.9%, -1.5%], DETERIORATED); Sweden Allsvenskan OU25 +40.7% -> +8.5% (n 15/23, CI [-94.7%, +37.0%], TOO_SMALL); Serie B OU25 +13.6% -> -18.3% (n 25/22, CI [-90.2%, +25.8%], STABLE); League One OU25 -22.1% -> -52.1% (n 30/27, CI [-72.9%, +0.9%], STABLE). Cells classified DETERIORATED: Argentina Primera Division BTTS.
9. **Is promotion more selective?** Yes: 95% -> 70% under the old gate alone, and the strict PG-1.0 gate now requires a 95% CI that excludes zero, a material gain, calibration, a canary, no league regression AND a prospective period of >=1000 rows per track. Replayed under the new gate, the 98 legacy promotions become {'UNKNOWN_NO_CI': 59, 'KEEP_CHAMPION': 36, 'SHADOW_MORE': 3}.
10. **Did market-data quality improve?** Yes: certified T30 close 7.8% -> 70.6%, median last pre-kickoff close 321.5 min -> 1.9 min; first-logged prices frozen from 2026-10-26; 1H-BTTS and synthetic-price rows excluded from certified ROI.
11. **What WOWZA learned in October that it did not know in September.** (a) The NF BTTS profit was a league regime (Argentina), not selection skill - October proved it out of sample. (b) Raw model-market disagreement is not a quality ordering. (c) v9 adds nothing measurable to the market price (v11 residual, edge_v2 shadow, Pro consensus all agree). (d) Most September 'improvements' at retrain were noise - a gate with a CI rejects them. (e) The Standard pipeline has concrete data defects (aliases, future-form leak, closing-price training) that must be fixed before its results mean anything. (f) NF OU25 UNDER does not earn its stake (monthly review proposes STOP). (g) An HGB challenger may help New Format - too early to say.
12. **What should NOT be changed yet.** No promotion of the HGB challenger (5 matchdays, PG-1.0 needs >=1000 prospective rows per track); no Standard staking or threshold change before the repaired-v9 rerun; no stake increase on NF BTTS or NF O1.5 from one month; no new per-league rules from October league ROI (every cell but one is TOO_SMALL or STABLE); keep the strict gate, the first-logged freeze and the CLV collector exactly as they are.

## 1. The two comparisons

| Comparison | September window | October window | Why |
|---|---|---|---|
| A | 2026-09-01 to 2026-09-30 | 2026-10-01 to 2026-10-27 | calendar months |
| B | 2026-09-24 to 2026-09-30 | 2026-10-01 to 2026-10-27 | reliable-evidence epoch only |

Ledger audit: 1450 live ledger rows since Sep 1, first-logged state recovered from v9's git history for 1450. Rows whose PRICE was rewritten after first log (side ledger, before 2026-10-26): {'btts': 59, 'ou25': 0, 'over15': 14, 'over35': 3}. Rows whose TIER was upgraded in place: {'btts': 86, 'ou25': 271, 'over15': 22, 'over35': 4}. All results below use the first-logged price and tier.

## 2. Standard = PRE_REPAIR STANDARD EVIDENCE / LEGACY

**Every Standard number in this report is labelled PRE_REPAIR STANDARD EVIDENCE / LEGACY - CONTAMINATED BY KNOWN DATA DEFECTS:** alias duplication and split team histories; future-match contamination in rolling form; wrong season weighting; closing-price train/live mismatch; invalid synthetic historical BTTS/O1.5 prices. It is NOT proof of structural improvement or deterioration. **This report must be rerun as OLD V9 vs REPAIRED V9 vs MARKET once a repaired v9 exists.**

Data-quality burden (read-only from `C:\Users\nevo.APOLLO\dev\wowza\pro_v9r\output\standard_repair`, status PASS, cutoff 2026-10-26, v9 f792f06b798c): 9687 alias rows removed from the legacy frame; 302 Standard fixtures had a future match inside the 5-game rolling window (legacy; 276 after canonicalisation); identity quarantine rows 0; 89% of the training frame's OU25 price equals the CLOSING price where both are known.

| League | Legacy rows | Alias-collision share (legacy) | Aliases resolved | Future-form leak sides legacy / canonical | OU25 real entry price share | Certified T30 close (forward) | 1H-BTTS rows removed | Live-constant features |
|---|---|---|---|---|---|---|---|---|
| Championship | 2913 | 29.6% | 5 | 0 / 0 | 80% | 22% | 56 | home_advantage |
| League One | 2909 | 36.4% | 9 | 80 / 70 | 60% | 26% | 58 | home_advantage |
| League Two | 2922 | 34.7% | 10 | 110 / 90 | 79% | 27% | 53 | home_advantage |
| Bundesliga 2 | 1610 | 45.0% | 15 | 0 / 0 | 78% | 11% | 34 | home_advantage |
| La Liga 2 | 2444 | 33.2% | 9 | 0 / 0 | 80% | 22% | 46 | home_advantage |
| Ligue 2 | 1836 | 0.0% | 0 | 0 / 0 | 78% | 27% | 0 | home_advantage |
| Serie B | 2003 | 0.4% | 2 | 0 / 0 | 79% | 26% | 13 | home_advantage |

Note: the owner brief quoted ~370 future-form rows (League One 95, League Two 125). The repair worktree's current file reports the figures above; that worktree is still being written by another agent, so the count is a moving measurement - the direction (League One and League Two carry the leak; the others ~0) is stable.

## 3. Main O/U 2.5 betting (first-logged price, one row per fixture x side)

### Comparison A

**O/U 2.5 - comparison A**

| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds | Mean CLV | CLV>0 | Close present |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | Sep | 396 | 27 | 165-231 | 41.7% | 44.8% | -28.36u | -7.2% | [-15.2%, +0.3%] | 2.29 / 2.20 | -0.18% | 39% | 100% |
| all | Oct | 412 | 25 | 180-232 | 43.7% | 44.4% | -6.48u | -1.6% | [-13.3%, +8.3%] | 2.31 / 2.23 | -0.18% | 39% | 100% |
| Standard | Sep | 175 | 20 | 74-101 | 42.3% | 48.4% | -21.53u | -12.3% | [-22.9%, +1.0%] | 2.09 / 2.07 | -0.38% | 38% | 100% |
| Standard | Oct | 150 | 21 | 64-86 | 42.7% | 46.4% | -11.30u | -7.5% | [-22.4%, +9.3%] | 2.19 / 2.10 | +0.62% | 45% | 100% |
| New Format | Sep | 221 | 26 | 91-130 | 41.2% | 42.0% | -6.83u | -3.1% | [-22.0%, +14.7%] | 2.44 / 2.38 | -0.03% | 39% | 100% |
| New Format | Oct | 262 | 24 | 116-146 | 44.3% | 43.3% | +4.82u | +1.8% | [-11.5%, +12.9%] | 2.38 / 2.28 | -0.64% | 36% | 100% |
| Standard|OVER | Sep | 91 | 18 | 39-52 | 42.9% | 49.8% | -11.93u | -13.1% | [-31.4%, +10.5%] | 2.02 / 1.99 | +1.33% | 42% | 100% |
| Standard|OVER | Oct | 79 | 19 | 35-44 | 44.3% | 50.6% | -10.14u | -12.8% | [-27.9%, +3.3%] | 1.99 / 1.97 | +1.02% | 48% | 100% |
| Standard|UNDER | Sep | 84 | 15 | 35-49 | 41.7% | 46.8% | -9.60u | -11.4% | [-25.5%, +4.5%] | 2.16 / 2.12 | -2.23% | 34% | 100% |
| Standard|UNDER | Oct | 71 | 18 | 29-42 | 40.8% | 41.7% | -1.16u | -1.6% | [-21.3%, +19.2%] | 2.42 / 2.40 | +0.17% | 41% | 100% |
| New Format|OVER | Sep | 60 | 21 | 27-33 | 45.0% | 42.8% | +2.08u | +3.5% | [-29.6%, +32.4%] | 2.40 / 2.41 | +1.35% | 52% | 100% |
| New Format|OVER | Oct | 27 | 15 | 13-14 | 48.1% | 41.4% | +4.87u | +18.0% | [-17.1%, +58.0%] | 2.49 / 2.58 | +2.50% | 67% | 100% |
| New Format|UNDER | Sep | 161 | 25 | 64-97 | 39.8% | 41.7% | -8.91u | -5.5% | [-25.9%, +14.4%] | 2.46 / 2.36 | -0.54% | 35% | 100% |
| New Format|UNDER | Oct | 235 | 22 | 103-132 | 43.8% | 43.5% | -0.05u | -0.0% | [-12.9%, +10.2%] | 2.37 / 2.25 | -1.00% | 33% | 100% |
| Standard ex League One/Two | Sep | 114 | 19 | 52-62 | 45.6% | 47.8% | -5.84u | -5.1% | [-20.6%, +12.3%] | 2.12 / 2.08 | -0.15% | 44% | 100% |
| Standard ex League One/Two | Oct | 104 | 19 | 50-54 | 48.1% | 46.4% | +5.28u | +5.1% | [-13.3%, +24.3%] | 2.19 / 2.10 | +0.09% | 40% | 100% |

| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < 20 bets or < 4 matchdays) |
|---|---|---|---|---|---|
| all | +5.6% | [-8.1%, +17.7%] | +2.0% | +21.88u | MIXED |
| Standard | +4.8% | [-14.9%, +25.3%] | +0.4% | +10.23u | MIXED |
| New Format | +4.9% | [-18.2%, +27.3%] | +3.1% | +11.65u | MIXED |
| Standard|OVER | +0.3% | [-27.9%, +23.8%] | +1.4% | +1.79u | MIXED |
| Standard|UNDER | +9.8% | [-15.3%, +35.1%] | -0.8% | +8.44u | MIXED |
| New Format|OVER | +14.6% | [-32.6%, +66.1%] | +3.1% | +2.79u | MIXED |
| New Format|UNDER | +5.5% | [-20.1%, +28.8%] | +4.1% | +8.86u | MIXED |
| Standard ex League One/Two | +10.2% | [-15.6%, +35.5%] | +2.5% | +11.12u | MIXED |

### Comparison B

**O/U 2.5 - comparison B**

| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds | Mean CLV | CLV>0 | Close present |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | Sep | 49 | 6 | 21-28 | 42.9% | 46.9% | -3.60u | -7.3% | [-28.7%, +18.3%] | 2.19 / 2.08 | +0.56% | 39% | 100% |
| all | Oct | 412 | 25 | 180-232 | 43.7% | 44.4% | -6.48u | -1.6% | [-13.3%, +8.3%] | 2.31 / 2.23 | -0.18% | 39% | 100% |
| Standard | Sep | 26 | 4 | 11-15 | 42.3% | 50.6% | -3.73u | -14.3% | [-36.2%, +8.0%] | 2.00 / 1.94 | -0.46% | 31% | 100% |
| Standard | Oct | 150 | 21 | 64-86 | 42.7% | 46.4% | -11.30u | -7.5% | [-22.4%, +9.3%] | 2.19 / 2.10 | +0.62% | 45% | 100% |
| New Format | Sep | 23 | 6 | 10-13 | 43.5% | 42.7% | +0.13u | +0.6% | [-39.1%, +25.2%] | 2.40 / 2.38 | +1.71% | 48% | 100% |
| New Format | Oct | 262 | 24 | 116-146 | 44.3% | 43.3% | +4.82u | +1.8% | [-11.5%, +12.9%] | 2.38 / 2.28 | -0.64% | 36% | 100% |
| Standard|OVER | Sep | 12 | 3 | 4-8 | 33.3% | 52.1% | -4.39u | -36.6% | [-60.8%, -30.2%] | 1.93 / 1.84 | -1.85% | 8% | 100% |
| Standard|OVER | Oct | 79 | 19 | 35-44 | 44.3% | 50.6% | -10.14u | -12.8% | [-27.9%, +3.3%] | 1.99 / 1.97 | +1.02% | 48% | 100% |
| Standard|UNDER | Sep | 14 | 3 | 7-7 | 50.0% | 49.3% | +0.66u | +4.7% | [-4.2%, +54.8%] | 2.06 / 2.01 | +0.72% | 50% | 100% |
| Standard|UNDER | Oct | 71 | 18 | 29-42 | 40.8% | 41.7% | -1.16u | -1.6% | [-21.3%, +19.2%] | 2.42 / 2.40 | +0.17% | 41% | 100% |
| New Format|OVER | Sep | 2 | 2 | 1-1 | 50.0% | 55.2% | -0.12u | -6.0% | [-100.0%, +88.0%] | 1.81 / 1.81 | -2.44% | 50% | 100% |
| New Format|OVER | Oct | 27 | 15 | 13-14 | 48.1% | 41.4% | +4.87u | +18.0% | [-17.1%, +58.0%] | 2.49 / 2.58 | +2.50% | 67% | 100% |
| New Format|UNDER | Sep | 21 | 6 | 9-12 | 42.9% | 41.5% | +0.25u | +1.2% | [-45.4%, +34.4%] | 2.45 / 2.38 | +2.11% | 48% | 100% |
| New Format|UNDER | Oct | 235 | 22 | 103-132 | 43.8% | 43.5% | -0.05u | -0.0% | [-12.9%, +10.2%] | 2.37 / 2.25 | -1.00% | 33% | 100% |
| Standard ex League One/Two | Sep | 9 | 4 | 3-6 | 33.3% | 50.1% | -3.01u | -33.4% | [-100.0%, +8.0%] | 2.00 / 1.96 | -0.75% | 33% | 100% |
| Standard ex League One/Two | Oct | 104 | 19 | 50-54 | 48.1% | 46.4% | +5.28u | +5.1% | [-13.3%, +24.3%] | 2.19 / 2.10 | +0.09% | 40% | 100% |

| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < 20 bets or < 4 matchdays) |
|---|---|---|---|---|---|
| all | +5.8% | [-24.0%, +27.3%] | +0.8% | -2.88u | MIXED |
| Standard | +6.8% | [-21.5%, +33.9%] | +0.4% | -7.57u | MIXED |
| New Format | +1.3% | [-28.8%, +40.4%] | +0.8% | +4.69u | MIXED |
| Standard|OVER | +23.7% | [+7.5%, +59.7%] | +11.0% | -5.75u | TOO_SMALL (CI would read IMPROVED) |
| Standard|UNDER | -6.3% | [-70.7%, +17.6%] | -9.2% | -1.82u | TOO_SMALL |
| New Format|OVER | +24.0% | [-86.1%, +139.0%] | -1.8% | +4.99u | TOO_SMALL |
| New Format|UNDER | -1.2% | [-36.5%, +43.1%] | +1.0% | -0.30u | MIXED |
| Standard ex League One/Two | +38.5% | [-14.9%, +98.3%] | +14.8% | +8.29u | TOO_SMALL |

### By raw-gap label (comparison A)

These are historical raw-gap labels, not confidence levels.

**all - SNIPER/Big gap, MARKSMAN/Medium gap, VALUABLE/Small gap**

| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds | Mean CLV | CLV>0 | Close present |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SNIPER/Big gap | Sep | 25 | 10 | 11-14 | 44.0% | 45.1% | -1.87u | -7.5% | [-28.4%, +20.3%] | 2.31 / 2.14 | -1.57% | 44% | 100% |
| SNIPER/Big gap | Oct | 57 | 18 | 19-38 | 33.3% | 37.9% | -3.61u | -6.3% | [-38.0%, +25.9%] | 2.74 / 2.62 | -1.00% | 40% | 100% |
| MARKSMAN/Medium gap | Sep | 69 | 17 | 31-38 | 44.9% | 44.4% | +1.26u | +1.8% | [-14.5%, +18.9%] | 2.32 / 2.28 | +0.13% | 29% | 100% |
| MARKSMAN/Medium gap | Oct | 80 | 17 | 27-53 | 33.8% | 43.2% | -20.70u | -25.9% | [-44.6%, -4.5%] | 2.36 / 2.25 | -0.81% | 30% | 100% |
| VALUABLE/Small gap | Sep | 302 | 26 | 123-179 | 40.7% | 44.9% | -27.75u | -9.2% | [-20.0%, -0.2%] | 2.28 / 2.20 | -0.14% | 41% | 100% |
| VALUABLE/Small gap | Oct | 275 | 25 | 134-141 | 48.7% | 46.1% | +17.83u | +6.5% | [-10.5%, +21.8%] | 2.21 / 2.12 | +0.17% | 42% | 100% |

| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < 20 bets or < 4 matchdays) |
|---|---|---|---|---|---|
| SNIPER/Big gap | +1.1% | [-38.2%, +39.2%] | -10.7% | -1.74u | MIXED |
| MARKSMAN/Medium gap | -27.7% | [-51.5%, +0.2%] | -11.2% | -21.96u | MIXED |
| VALUABLE/Small gap | +15.7% | [-3.4%, +33.4%] | +8.0% | +45.58u | MIXED |

**Standard - SNIPER/Big gap, MARKSMAN/Medium gap, VALUABLE/Small gap**

| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds | Mean CLV | CLV>0 | Close present |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SNIPER/Big gap | Sep | 14 | 7 | 7-7 | 50.0% | 49.6% | -0.34u | -2.4% | [-36.9%, +37.4%] | 2.04 / 2.00 | +0.07% | 57% | 100% |
| SNIPER/Big gap | Oct | 9 | 8 | 2-7 | 22.2% | 41.6% | -3.60u | -40.0% | [-100.0%, +35.0%] | 2.45 / 2.45 | -3.62% | 33% | 100% |
| MARKSMAN/Medium gap | Sep | 30 | 10 | 15-15 | 50.0% | 49.7% | +0.83u | +2.8% | [-27.1%, +24.3%] | 2.04 / 1.97 | -0.83% | 17% | 100% |
| MARKSMAN/Medium gap | Oct | 14 | 9 | 6-8 | 42.9% | 42.0% | -0.45u | -3.2% | [-50.5%, +67.5%] | 2.43 / 2.52 | -1.56% | 29% | 100% |
| VALUABLE/Small gap | Sep | 131 | 20 | 52-79 | 39.7% | 47.9% | -22.02u | -16.8% | [-27.4%, -3.4%] | 2.10 / 2.08 | -0.33% | 41% | 100% |
| VALUABLE/Small gap | Oct | 127 | 20 | 56-71 | 44.1% | 47.2% | -7.25u | -5.7% | [-24.0%, +13.5%] | 2.15 / 2.07 | +1.16% | 47% | 100% |

| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < 20 bets or < 4 matchdays) |
|---|---|---|---|---|---|
| SNIPER/Big gap | -37.6% | [-105.5%, +41.0%] | -27.8% | -3.26u | TOO_SMALL |
| MARKSMAN/Medium gap | -6.0% | [-58.5%, +70.0%] | -7.1% | -1.28u | TOO_SMALL |
| VALUABLE/Small gap | +11.1% | [-12.2%, +32.5%] | +4.4% | +14.77u | MIXED |

**New Format - SNIPER/Big gap, MARKSMAN/Medium gap, VALUABLE/Small gap**

| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds | Mean CLV | CLV>0 | Close present |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SNIPER/Big gap | Sep | 11 | 8 | 4-7 | 36.4% | 39.3% | -1.53u | -13.9% | [-62.7%, +45.0%] | 2.67 / 2.32 | -3.66% | 27% | 100% |
| SNIPER/Big gap | Oct | 48 | 16 | 17-31 | 35.4% | 37.2% | -0.01u | -0.0% | [-32.0%, +29.9%] | 2.79 / 2.69 | -0.50% | 42% | 100% |
| MARKSMAN/Medium gap | Sep | 39 | 15 | 16-23 | 41.0% | 40.4% | +0.43u | +1.1% | [-29.0%, +33.1%] | 2.54 / 2.45 | +0.87% | 38% | 100% |
| MARKSMAN/Medium gap | Oct | 66 | 15 | 21-45 | 31.8% | 43.5% | -20.25u | -30.7% | [-48.5%, -10.1%] | 2.34 / 2.25 | -0.65% | 30% | 100% |
| VALUABLE/Small gap | Sep | 171 | 25 | 71-100 | 41.5% | 42.5% | -5.73u | -3.4% | [-24.1%, +19.4%] | 2.41 / 2.36 | -0.00% | 40% | 100% |
| VALUABLE/Small gap | Oct | 148 | 24 | 78-70 | 52.7% | 45.1% | +25.08u | +17.0% | [-4.4%, +35.6%] | 2.26 / 2.23 | -0.68% | 37% | 100% |

| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < 20 bets or < 4 matchdays) |
|---|---|---|---|---|---|
| SNIPER/Big gap | +13.9% | [-50.5%, +69.0%] | -0.9% | +1.52u | TOO_SMALL |
| MARKSMAN/Medium gap | -31.8% | [-66.3%, +6.6%] | -9.2% | -20.68u | MIXED |
| VALUABLE/Small gap | +20.3% | [-10.2%, +48.5%] | +11.2% | +30.81u | MIXED |

Close present = a closing price exists in the ledger. It is NOT a certified close: 19.7% (Sep) and 23.3% (Oct) of OU25 closes equal the entry price exactly, the signature of a missing close. Certified close coverage is in section 11.

## 4. Side markets - genuine observed prices only

Excluded from certified ROI: [{'market': 'btts', 'excl_reason': 'SYNTHETIC_FILL_CONSTANT', 'n': 18}, {'market': 'over15', 'excl_reason': 'SYNTHETIC_FILL_CONSTANT', 'n': 1}] (rows priced exactly at v9's synthetic fill constant {'btts': 1.85, 'over15': 1.4, 'over35': 2.6} are dropped fail-closed, the rule in v9 `src/market_edge.py::exclude_synthetic_prices`; BTTS entries above 3.2 are the first-half market and dropped; BTTS closes above 3.2 are dropped from CLV).

**Side markets - comparison A**

| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds | Mean CLV | CLV>0 | Close present |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| New Format|btts | Sep | 104 | 22 | 67-37 | 64.4% | 51.4% | +28.82u | +27.7% | [+11.6%, +42.9%] | 1.98 / 2.00 | -0.95% | 34% | 80% |
| New Format|btts | Oct | 107 | 25 | 52-55 | 48.6% | 51.3% | -4.65u | -4.3% | [-21.5%, +14.1%] | 1.98 / 2.00 | -0.60% | 37% | 86% |
| New Format|over15 | Sep | 37 | 16 | 24-13 | 64.9% | 64.2% | +0.29u | +0.8% | [-20.9%, +24.5%] | 1.56 / 1.56 | +1.18% | 46% | 100% |
| New Format|over15 | Oct | 38 | 19 | 29-9 | 76.3% | 64.8% | +6.54u | +17.2% | [+0.1%, +34.5%] | 1.55 / 1.55 | +2.18% | 55% | 100% |
| Standard|btts | Sep | 84 | 18 | 47-37 | 56.0% | 54.2% | +2.40u | +2.9% | [-15.9%, +21.3%] | 1.85 / 1.83 | -0.06% | 38% | 87% |
| Standard|btts | Oct | 53 | 15 | 29-24 | 54.7% | 55.0% | -0.26u | -0.5% | [-18.4%, +20.4%] | 1.82 / 1.80 | -0.50% | 34% | 94% |
| Standard|over15 | Sep | 7 | 6 | 4-3 | 57.1% | 69.3% | -1.30u | -18.6% | [-75.8%, +24.4%] | 1.45 / 1.49 | +0.21% | 43% | 100% |
| Standard|over15 | Oct | 1 | 1 | 1-0 | 100.0% | 69.9% | +0.43u | +43.0% | n/a | 1.43 / 1.43 | -5.92% | 0% | 100% |
| New Format|over35 | Sep | 11 | 8 | 3-8 | 27.3% | 48.3% | -5.45u | -49.5% | [-82.9%, -12.8%] | 2.10 / 2.14 | +2.71% | 55% | 100% |
| New Format|over35 | Oct | 6 | 4 | 5-1 | 83.3% | 50.9% | +3.91u | +65.2% | [+35.3%, +95.0%] | 1.97 / 1.94 | +0.87% | 33% | 100% |
| Standard|over35 | Sep | 3 | 3 | 1-2 | 33.3% | 36.0% | -0.70u | -23.3% | [-100.0%, +53.3%] | 3.01 / 2.42 | +2.48% | 67% | 100% |
| Standard|over35 | Oct | 1 | 1 | 0-1 | 0.0% | 43.5% | -1.00u | -100.0% | n/a | 2.30 / 2.30 | +0.88% | 100% | 100% |

| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < 20 bets or < 4 matchdays) |
|---|---|---|---|---|---|
| New Format|btts | -32.1% | [-54.5%, -7.7%] | -15.8% | -33.47u | DETERIORATED |
| New Format|over15 | +16.4% | [-11.9%, +44.8%] | +11.5% | +6.25u | MIXED |
| Standard|btts | -3.3% | [-28.6%, +24.6%] | -1.2% | -2.66u | MIXED |
| Standard|over15 | +61.6% | n/a | +42.9% | +1.73u | TOO_SMALL |
| New Format|over35 | +114.7% | [+66.1%, +165.1%] | +56.1% | +9.36u | TOO_SMALL (CI would read IMPROVED) |
| Standard|over35 | -76.7% | n/a | -33.3% | -0.30u | TOO_SMALL |

**Side markets - comparison B**

| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds | Mean CLV | CLV>0 | Close present |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| New Format|btts | Sep | 12 | 4 | 8-4 | 66.7% | 65.5% | +0.32u | +2.7% | [-8.0%, +56.1%] | 1.53 / 1.52 | -1.31% | 17% | 100% |
| New Format|btts | Oct | 107 | 25 | 52-55 | 48.6% | 51.3% | -4.65u | -4.3% | [-21.5%, +14.1%] | 1.98 / 2.00 | -0.60% | 37% | 86% |
| New Format|over15 | Sep | 0 | - | - | - | - | - | - | - | - | - | - | - |
| New Format|over15 | Oct | 38 | 19 | 29-9 | 76.3% | 64.8% | +6.54u | +17.2% | [+0.1%, +34.5%] | 1.55 / 1.55 | +2.18% | 55% | 100% |
| Standard|btts | Sep | 16 | 3 | 9-7 | 56.2% | 57.9% | -0.45u | -2.8% | [-64.8%, +10.3%] | 1.74 / 1.71 | -2.64% | 25% | 100% |
| Standard|btts | Oct | 53 | 15 | 29-24 | 54.7% | 55.0% | -0.26u | -0.5% | [-18.4%, +20.4%] | 1.82 / 1.80 | -0.50% | 34% | 94% |
| Standard|over15 | Sep | 0 | - | - | - | - | - | - | - | - | - | - | - |
| Standard|over15 | Oct | 1 | 1 | 1-0 | 100.0% | 69.9% | +0.43u | +43.0% | n/a | 1.43 / 1.43 | -5.92% | 0% | 100% |

| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < 20 bets or < 4 matchdays) |
|---|---|---|---|---|---|
| New Format|btts | -7.1% | [-48.8%, +16.0%] | -18.1% | -4.97u | TOO_SMALL |
| Standard|btts | +2.3% | [-20.4%, +76.9%] | -1.5% | +0.19u | TOO_SMALL |

## 5. League-level change

Category rule: TOO_SMALL unless both months have >= 20 settled bets and >= 4 matchdays; then IMPROVED / DETERIORATED only if the 90% matchday-bootstrap CI of the ROI change excludes zero, else STABLE. Full table (both comparisons, OU25 and BTTS): `output/monthly_learning_by_league.csv`.

| Market | League | Track | Sep N | Sep ROI | Oct N | Oct ROI | ROI change | 90% CI | Hit change | PnL change | Category | Pattern |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTTS | Argentina Primera Division | New Format | 47 | +40.7% | 52 | +4.3% | -36.4% | [-72.9%, -1.5%] | -15.8% | -16.91u | DETERIORATED | POSITIVE_BOTH |
| BTTS | Brazil Serie A | New Format | 18 | +40.4% | 12 | +25.0% | -15.5% | [-65.4%, +32.5%] | -5.5% | -4.28u | TOO_SMALL | POSITIVE_BOTH |
| BTTS | Japan J-League | New Format | 13 | +2.6% | 9 | -33.3% | -35.9% | [-102.8%, +22.0%] | -20.5% | -3.33u | TOO_SMALL | POS_TO_NEG |
| BTTS | Championship (PRE_REPAIR) | Standard | 10 | +8.5% | 15 | +20.6% | +12.2% | [-67.2%, +90.4%] | +6.7% | +2.24u | TOO_SMALL | POSITIVE_BOTH |
| BTTS | La Liga 2 (PRE_REPAIR) | Standard | 22 | -6.8% | 9 | -14.3% | -7.5% | [-76.7%, +58.2%] | -5.6% | +0.20u | TOO_SMALL | NEGATIVE_BOTH |
| BTTS | League One (PRE_REPAIR) | Standard | 9 | -24.2% | 7 | -24.6% | -0.4% | [-55.2%, +58.4%] | -1.6% | +0.45u | TOO_SMALL | NEGATIVE_BOTH |
| BTTS | League Two (PRE_REPAIR) | Standard | 11 | -19.2% | 8 | -10.3% | +8.9% | [-77.6%, +71.9%] | +4.5% | +1.30u | TOO_SMALL | NEGATIVE_BOTH |
| BTTS | Ligue 2 (PRE_REPAIR) | Standard | 11 | +36.5% | 5 | +45.8% | +9.3% | [-46.6%, +72.3%] | +7.3% | -1.73u | TOO_SMALL | POSITIVE_BOTH |
| BTTS | Serie B (PRE_REPAIR) | Standard | 21 | +15.8% | 9 | -20.1% | -35.9% | [-92.2%, +55.7%] | -17.5% | -5.13u | TOO_SMALL | POS_TO_NEG |
| OU25 | Argentina Primera Division | New Format | 32 | -10.0% | 18 | +2.9% | +12.9% | [-53.5%, +84.1%] | +4.5% | +3.72u | TOO_SMALL | NEG_TO_POS |
| OU25 | Austrian Bundesliga | New Format | 12 | -64.4% | 11 | -31.4% | +33.0% | [-38.6%, +93.5%] | +10.6% | +4.27u | TOO_SMALL | NEGATIVE_BOTH |
| OU25 | Brazil Serie A | New Format | 18 | +8.7% | 30 | +20.9% | +12.2% | [-26.8%, +69.4%] | +10.0% | +4.70u | TOO_SMALL | POSITIVE_BOTH |
| OU25 | China Super League | New Format | 9 | +53.4% | 15 | -7.3% | -60.8% | [-140.7%, +23.8%] | -26.7% | -5.91u | TOO_SMALL | POS_TO_NEG |
| OU25 | Denmark Superliga | New Format | 9 | +16.6% | 16 | -25.2% | -41.8% | [-113.4%, +48.4%] | -13.2% | -5.52u | TOO_SMALL | POS_TO_NEG |
| OU25 | Finland Veikkausliiga | New Format | 10 | +45.6% | 18 | +23.7% | -21.9% | [-53.6%, +18.1%] | -8.9% | -0.29u | TOO_SMALL | POSITIVE_BOTH |
| OU25 | Ireland Premier Division | New Format | 10 | -38.9% | 13 | -36.7% | +2.2% | [-74.0%, +61.9%] | +0.8% | -0.88u | TOO_SMALL | NEGATIVE_BOTH |
| OU25 | Japan J-League | New Format | 21 | +12.3% | 23 | +24.4% | +12.1% | [-23.4%, +60.7%] | +4.1% | +3.03u | STABLE | POSITIVE_BOTH |
| OU25 | Mexico Liga MX | New Format | 19 | +18.1% | 27 | +18.1% | +0.0% | [-62.3%, +60.8%] | +2.9% | +1.45u | TOO_SMALL | POSITIVE_BOTH |
| OU25 | Norway Eliteserien | New Format | 10 | -22.5% | 19 | +8.7% | +31.2% | [-49.4%, +109.4%] | +6.8% | +3.91u | TOO_SMALL | NEG_TO_POS |
| OU25 | Sweden Allsvenskan | New Format | 15 | +40.7% | 23 | +8.5% | -32.2% | [-94.7%, +37.0%] | -12.2% | -4.16u | TOO_SMALL | POSITIVE_BOTH |
| OU25 | USA MLS | New Format | 56 | -25.6% | 49 | -14.3% | +11.3% | [-28.2%, +51.5%] | +4.1% | +7.33u | STABLE | NEGATIVE_BOTH |
| OU25 | Bundesliga 2 (PRE_REPAIR) | Standard | 16 | -51.4% | 21 | +54.7% | +106.1% | [+48.1%, +160.4%] | +43.1% | +19.71u | TOO_SMALL | NEG_TO_POS |
| OU25 | Championship (PRE_REPAIR) | Standard | 29 | -2.2% | 23 | -14.5% | -12.3% | [-55.2%, +42.6%] | -9.2% | -2.70u | STABLE | NEGATIVE_BOTH |
| OU25 | La Liga 2 (PRE_REPAIR) | Standard | 33 | +7.1% | 27 | +7.6% | +0.5% | [-37.5%, +33.9%] | +0.3% | -0.29u | STABLE | POSITIVE_BOTH |
| OU25 | League One (PRE_REPAIR) | Standard | 30 | -22.1% | 27 | -52.1% | -30.0% | [-72.9%, +0.9%] | -14.4% | -7.45u | STABLE | NEGATIVE_BOTH |
| OU25 | League Two (PRE_REPAIR) | Standard | 31 | -29.3% | 19 | -13.2% | +16.1% | [-18.4%, +53.5%] | +6.6% | +6.56u | TOO_SMALL | NEGATIVE_BOTH |
| OU25 | Ligue 2 (PRE_REPAIR) | Standard | 11 | -24.7% | 11 | -8.0% | +16.7% | [-58.4%, +98.3%] | +9.1% | +1.84u | TOO_SMALL | NEGATIVE_BOTH |
| OU25 | Serie B (PRE_REPAIR) | Standard | 25 | +13.6% | 22 | -18.3% | -32.0% | [-90.2%, +25.8%] | -15.1% | -7.44u | STABLE | POS_TO_NEG |

* **Positive both months** (n>=10 both months): Brazil Serie A OU25, Finland Veikkausliiga OU25, Japan J-League OU25, La Liga 2 OU25, Mexico Liga MX OU25, Sweden Allsvenskan OU25, Argentina Primera Division BTTS, Brazil Serie A BTTS, Championship BTTS
* **Negative -> positive** (n>=10 both months): Argentina Primera Division OU25, Bundesliga 2 OU25, Norway Eliteserien OU25
* **Positive -> negative** (n>=10 both months): Serie B OU25
* **Persistently negative** (n>=10 both months): Austrian Bundesliga OU25, Championship OU25, Ireland Premier Division OU25, League One OU25, League Two OU25, Ligue 2 OU25, USA MLS OU25

Comparison B: with only Sep 24-30 on the September side, every league cell is TOO_SMALL; no league-level claim can be made from the reliable-evidence window yet.

## 6. New Format

**New Format totals - comparison A**

| Scope | Month | N | Matchdays | W-L | Hit | Break-even hit | PnL | ROI | ROI 90% CI | Avg / med odds | Mean CLV | CLV>0 | Close present |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NF all markets | Sep | 373 | 27 | 185-188 | 49.6% | 47.0% | +16.83u | +4.5% | [-9.2%, +18.5%] | 2.22 / 2.20 | -0.03% | 39% | 94% |
| NF all markets | Oct | 413 | 26 | 202-211 | 48.9% | 47.4% | +10.62u | +2.6% | [-8.3%, +13.4%] | 2.19 / 2.12 | -0.34% | 38% | 96% |
| NF OU25 | Sep | 221 | 26 | 91-130 | 41.2% | 42.0% | -6.83u | -3.1% | [-22.0%, +14.7%] | 2.44 / 2.38 | -0.03% | 39% | 100% |
| NF OU25 | Oct | 262 | 24 | 116-146 | 44.3% | 43.3% | +4.82u | +1.8% | [-11.5%, +12.9%] | 2.38 / 2.28 | -0.64% | 36% | 100% |
| NF OU25 OVER | Sep | 60 | 21 | 27-33 | 45.0% | 42.8% | +2.08u | +3.5% | [-29.6%, +32.4%] | 2.40 / 2.41 | +1.35% | 52% | 100% |
| NF OU25 OVER | Oct | 27 | 15 | 13-14 | 48.1% | 41.4% | +4.87u | +18.0% | [-17.1%, +58.0%] | 2.49 / 2.58 | +2.50% | 67% | 100% |
| NF OU25 UNDER | Sep | 161 | 25 | 64-97 | 39.8% | 41.7% | -8.91u | -5.5% | [-25.9%, +14.4%] | 2.46 / 2.36 | -0.54% | 35% | 100% |
| NF OU25 UNDER | Oct | 235 | 22 | 103-132 | 43.8% | 43.5% | -0.05u | -0.0% | [-12.9%, +10.2%] | 2.37 / 2.25 | -1.00% | 33% | 100% |
| NF BTTS | Sep | 104 | 22 | 67-37 | 64.4% | 51.4% | +28.82u | +27.7% | [+11.6%, +42.9%] | 1.98 / 2.00 | -0.95% | 34% | 80% |
| NF BTTS | Oct | 107 | 25 | 52-55 | 48.6% | 51.3% | -4.65u | -4.3% | [-21.5%, +14.1%] | 1.98 / 2.00 | -0.60% | 37% | 86% |
| NF O1.5 | Sep | 37 | 16 | 24-13 | 64.9% | 64.2% | +0.29u | +0.8% | [-20.9%, +24.5%] | 1.56 / 1.56 | +1.18% | 46% | 100% |
| NF O1.5 | Oct | 38 | 19 | 29-9 | 76.3% | 64.8% | +6.54u | +17.2% | [+0.1%, +34.5%] | 1.55 / 1.55 | +2.18% | 55% | 100% |

| Scope | ROI change Oct - Sep | 90% CI (matchday bootstrap) | Hit change | PnL change | Read (TOO_SMALL if either month < 20 bets or < 4 matchdays) |
|---|---|---|---|---|---|
| NF all markets | -1.9% | [-19.8%, +15.5%] | -0.7% | -6.21u | MIXED |
| NF OU25 | +4.9% | [-18.2%, +27.3%] | +3.1% | +11.65u | MIXED |
| NF OU25 OVER | +14.6% | [-32.6%, +66.1%] | +3.1% | +2.79u | MIXED |
| NF OU25 UNDER | +5.5% | [-20.1%, +28.8%] | +4.1% | +8.86u | MIXED |
| NF BTTS | -32.1% | [-54.5%, -7.7%] | -15.8% | -33.47u | DETERIORATED |
| NF O1.5 | +16.4% | [-11.9%, +44.8%] | +11.5% | +6.25u | MIXED |

**Did New Format improve?** Not demonstrably. All NF markets: +4.5% -> +2.6%, change -1.9%, 90% CI [-19.8%, +15.5%]. NF OU25 moved up (+4.9%, CI [-18.2%, +27.3%]) while NF BTTS fell (-32.1%, CI [-54.5%, -7.7%]). Forecast-wise NF OU25 log loss moved -0.0075 (CI [-0.0360, +0.0185]). NF leagues are in section 5.

## 7. Standard per league - PRE_REPAIR

| League (PRE_REPAIR) | N Sep-Oct | Matchdays | Wins | Bookmaker-expected wins (raw / ~5% de-vig) | P(W <= observed) raw / de-vig | PnL | ROI |
|---|---|---|---|---|---|---|---|
| Championship | 52 | 20 | 23 | 24.9 / 23.7 | 0.3459 / 0.4748 | -3.96u | -7.6% |
| League One | 57 | 15 | 17 | 26.9 / 25.6 | 0.0056 / 0.014 | -20.69u | -36.3% |
| League Two | 50 | 11 | 19 | 24.6 / 23.4 | 0.0728 / 0.1309 | -11.58u | -23.2% |
| Bundesliga 2 | 37 | 17 | 16 | 14.9 / 14.2 | 0.7069 / 0.7843 | +3.25u | +8.8% |
| La Liga 2 | 60 | 27 | 31 | 29.0 / 27.7 | 0.7381 / 0.8409 | +4.37u | +7.3% |
| Ligue 2 | 22 | 12 | 9 | 10.5 / 10.0 | 0.3312 / 0.4131 | -3.60u | -16.4% |
| Serie B | 47 | 16 | 23 | 23.3 / 22.2 | 0.5255 / 0.6517 | -0.62u | -1.3% |

Owner reference reproduced from the GitHub ledger (1u at logged odds): Standard OU25 September 175 bets -12.3% -21.53u; October 150 bets -7.5% -11.30u. Ex League One/Two: September 114 -5.1%, October 104 +5.1%. League One 17 wins vs ~25.6 bookmaker-expected (p 0.014). All verified - the OU25 ledger price was never overwritten (0 rows), so ledger price = first-logged price for OU25.

A bad Standard month is NOT read as pure model failure: League One and League Two, the two worst leagues, are also the only two Standard leagues with future-form leakage, and all seven serve `home_advantage` as a constant live while it varies in training. Those are implementation defects to remove before the model idea can be judged.

## 8. Retraining and promotion

| Month | Retrain days | Candidates | Promoted | Rejected / held | Promotion rate | Promoted with WORSE holdout LL | Promoted with a CI | Promoted with CI excluding zero |
|---|---|---|---|---|---|---|---|---|
| 2026-09 | 9 | 63 | 60 | 3 | 95% | 20 | 0 | 0 |
| 2026-10 | 8 | 56 | 39 | 17 | 70% | 9 | 11 | 1 |

Gates: **OLD LEGACY GATE** (v9 retrain.py tolerance rule: promote unless holdout log loss rose by more than 0.005 - later 0.030 - no interval) ran every September and October retrain through 2026-10-18. The **champion high-water mark** (src/champion_gate.py, 2026-10-18) judged the 2026-10-25 batch. The **STRICT PG-1.0 GATE** (src/promotion_gate.py + config/promotion_gate.json, declared 2026-10-25) became the sole writer of current_champions.json minutes later and requires: n >= 1000 per track, a material gain (<= -0.001 LL), 95% matchday block-bootstrap CI excluding zero, Brier/ECE/slope not worse, a prediction canary, no league regression, AND a prospective period of >= 1000 rows per track.

By gate: 2026-09: {'OLD_LEGACY_GATE': {'candidates': 63, 'promoted': 60}}; 2026-10: {'CHAMPION_GATE_HWM': {'candidates': 7, 'promoted': 1}, 'OLD_LEGACY_GATE': {'candidates': 49, 'promoted': 38}}

**September examples of weak models the old gate promoted** (holdout log loss got WORSE, promoted anyway):

* 2026-09-24 newformat: delta +0.00119 - "log loss 0.59537 -> 0.59656 (+0.00119), within the 0.00500 tolerance"
* 2026-09-24 btts: delta +0.00031 - "log loss 0.65603 -> 0.65634 (+0.00031), within the 0.00500 tolerance"
* 2026-09-25 over15: delta +0.00077 - "log loss 0.54509 -> 0.54586 (+0.00077), within the 0.03000 tolerance"
* 2026-09-26 standard: delta +0.00032 - "log loss 0.68753 -> 0.68785 (+0.00033), within the 0.03000 tolerance"
* 2026-09-26 newformat: delta +0.00035 - "log loss 0.67959 -> 0.67994 (+0.00035), within the 0.03000 tolerance"
* 2026-09-26 ht_over05: delta +0.01927 - "log loss 0.64789 -> 0.66716 (+0.01927), within the 0.03000 tolerance"
* 2026-09-26 ht_over15: delta +0.00393 - "log loss 0.56759 -> 0.57152 (+0.00394), within the 0.03000 tolerance"
* 2026-09-26 over35: delta +0.00125 - "log loss 0.59826 -> 0.59951 (+0.00124), within the 0.03000 tolerance"

**October rejections:**

* 2026-10-05 standard: LEGACY_BLOCKED, delta +0.000970 - log loss ROSE +0.00097 (0.68751 -> 0.68848) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-05 newformat: LEGACY_BLOCKED, delta +0.000510 - log loss ROSE +0.00051 (0.68181 -> 0.68232) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-05 ht_over15: LEGACY_BLOCKED, delta +0.000080 - log loss ROSE +0.00008 (0.65010 -> 0.65018) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-11 standard: LEGACY_BLOCKED, delta +0.000380 - log loss ROSE +0.00038 (0.68770 -> 0.68808) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-11 newformat: LEGACY_BLOCKED, delta +0.000440 - log loss ROSE +0.00045 (0.68270 -> 0.68314) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-11 ht_over15: LEGACY_BLOCKED, delta +0.000430 - log loss ROSE +0.00043 (0.65000 -> 0.65043) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-11 btts: LEGACY_BLOCKED, delta +0.000010 - log loss ROSE +0.00001 (0.68543 -> 0.68544) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-11 over35: LEGACY_BLOCKED, delta +0.000130 - log loss ROSE +0.00013 (0.60102 -> 0.60115) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-18 ht_over15: LEGACY_BLOCKED, delta +0.000630 - log loss ROSE +0.00064 (0.64968 -> 0.65031) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-18 btts: LEGACY_BLOCKED, delta +0.000220 - log loss ROSE +0.00022 (0.68575 -> 0.68597) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-18 over35: LEGACY_BLOCKED, delta +0.000300 - log loss ROSE +0.00030 (0.60125 -> 0.60155) on the incumbent's own holdout — a worse candidate does not replace a serving champion
* 2026-10-25 standard: SHADOW_MORE, delta -0.000883 - possibly better (delta -0.00088, CI [-0.00218, +0.00034]) but not proven: material_improvement, ci_excludes_zero

**2026-10-25, model by model:**

| Model | Gate | Verdict | LL delta | 95% CI | Brier delta | ECE delta | Later-half delta | Why |
|---|---|---|---|---|---|---|---|---|
| standard | CHAMPION_GATE_HWM | SHADOW_MORE | -0.000883 | [-0.0022, +0.0003] | -0.000435 | +0.0026 | -0.000970 | possibly better (delta -0.00088, CI [-0.00218, +0.00034]) but not proven: material_improvement, ci_excludes_zero |
| newformat | CHAMPION_GATE_HWM | PROMOTE | -0.001581 | [-0.0028, -0.0004] | -0.000739 | +0.0064 | -0.000480 | materially better: delta -0.00158, CI [-0.00282, -0.00038], later half -0.00048, Brier -0.00074, ECE +0.0064 |
| btts | CHAMPION_GATE_HWM | KEEP_CHAMPION | +0.000373 | [-0.0005, +0.0012] | +0.000181 | -0.0011 | +0.000625 | challenger not better: delta +0.000373 (0.68426 -> 0.68463); worse or tied keeps the champion |
| over15 | CHAMPION_GATE_HWM | KEEP_CHAMPION | -0.000024 | [-0.0008, +0.0007] | -0.000004 | +0.0014 | -0.000087 | statistically tied: delta -0.000024, CI [-0.00082, +0.00067] does not even admit a material (0.001) gain |
| over35 | CHAMPION_GATE_HWM | KEEP_CHAMPION | -0.000066 | [-0.0005, +0.0004] | -0.000025 | -0.0017 | +0.000250 | statistically tied: delta -0.000066, CI [-0.00051, +0.00043] does not even admit a material (0.001) gain |
| ht_over05 | CHAMPION_GATE_HWM | KEEP_CHAMPION | -0.000001 | [-0.0003, +0.0004] | +0.000001 | -0.0053 | -0.000173 | statistically tied: delta -0.000001, CI [-0.00033, +0.00039] does not even admit a material (0.001) gain |
| ht_over15 | CHAMPION_GATE_HWM | KEEP_CHAMPION | -0.000152 | [-0.0006, +0.0003] | -0.000070 | +0.0011 | -0.000709 | statistically tied: delta -0.000152, CI [-0.00065, +0.00032] does not even admit a material (0.001) gain |

PG-1.0 decisions the same day: ROLLBACK newformat newformat_20261018T080423Z_9eb6b4b4 -> ROLLBACK (owner 2026-10-25: promoted by the retired champion_gate minutes before PG-1.0 went live; holdout-qualified but no prospective period - parked as challenger); PARK newformat newformat_20261025T082056Z_cfa68e5c -> SHADOW_MORE (owner 2026-10-25: parked after rollback; promotes only via the prospective period)

So on 2026-10-25: standard HELD (SHADOW_MORE - possibly better, CI includes zero, not material); newformat was promoted by the retiring high-water-mark gate, then ROLLED BACK under PG-1.0 because it had no prospective period, and parked as a challenger; btts KEPT (challenger worse); over15, over35, ht_over05, ht_over15 KEPT (statistically tied - the CI does not even admit a material gain). Net: 0 of 7 retrains changed production.

Did the system get better at rejecting weak models? Yes. Replaying every legacy promotion under the new gate gives {'UNKNOWN_NO_CI': 59, 'KEEP_CHAMPION': 36, 'SHADOW_MORE': 3} - not one would have been a clean PROMOTE.

## 9. Forecast quality (log loss, Brier, ECE)

Comparable datasets only. **(a)** O/U 2.5 on EVERY fixture v9 published, from wowza_v11's shadow log (the same pipeline in both months; last pre-kickoff snapshot; graded by v11). **(b)** O/U 2.5, BTTS, O1.5, O3.5 from the Pro canonical store: v9 model snapshot (last pre-kickoff) vs the median de-vigged two-sided quote over >= 3 books (last pre-kickoff quote per book, change-log carried forward), graded on v9 fd_history scores; 1201 of 1498 fixtures matched to a final score. v91_shadow starts 2026-10-04, so it is **NOT DIRECTLY COMPARABLE** for September and is used only in section 11.

| (a) OU25, all published fixtures | N | Matchdays | Model LL | Market LL | Model Brier | Market Brier | Model ECE | Market ECE | Model - market LL (95% CI) |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09|Standard | 244 | 20 | 0.6900 | 0.6836 | 0.2485 | 0.2452 | 0.030 | 0.052 | +0.0065 [-0.0118, +0.0222] |
| 2026-10|Standard | 233 | 20 | 0.6993 | 0.6805 | 0.2530 | 0.2437 | 0.039 | 0.019 | +0.0188 [+0.0013, +0.0323] |
| 2026-09|New Format | 248 | 26 | 0.6857 | 0.6698 | 0.2463 | 0.2389 | 0.023 | 0.048 | +0.0158 [-0.0144, +0.0448] |
| 2026-10|New Format | 270 | 28 | 0.6782 | 0.6663 | 0.2426 | 0.2366 | 0.051 | 0.042 | +0.0119 [-0.0079, +0.0374] |

* Standard: model LL Oct - Sep +0.0092 [-0.0058, +0.0272]; gap to market Oct - Sep +0.0123 [-0.0107, +0.0341].
* New Format: model LL Oct - Sep -0.0075 [-0.0360, +0.0185]; gap to market Oct - Sep -0.0039 [-0.0402, +0.0358].

| (b) Pro store | N | Matchdays | Model LL | Market LL | Model Brier | Market Brier | Model ECE | Market ECE | Model - market LL (95% CI) |
|---|---|---|---|---|---|---|---|---|---|
| BTTS|New Format|2026-09 | 330 | 27 | 0.6784 | 0.6855 | 0.2427 | 0.2462 | 0.042 | 0.072 | -0.0072 [-0.0218, +0.0068] |
| BTTS|New Format|2026-10 | 357 | 26 | 0.6761 | 0.6663 | 0.2416 | 0.2370 | 0.031 | 0.041 | +0.0098 [-0.0089, +0.0246] |
| BTTS|Standard|2026-09 | 257 | 22 | 0.6816 | 0.6694 | 0.2442 | 0.2382 | 0.064 | 0.060 | +0.0122 [+0.0033, +0.0224] |
| BTTS|Standard|2026-10 | 257 | 21 | 0.6898 | 0.6916 | 0.2483 | 0.2492 | 0.027 | 0.036 | -0.0018 [-0.0197, +0.0084] |
| OU15|New Format|2026-09 | 25 | 14 | 0.7487 | 0.6928 | 0.2737 | 0.2497 | 0.170 | 0.058 | +0.0560 [-0.0465, +0.1476] |
| OU15|New Format|2026-10 | 32 | 18 | 0.5668 | 0.5965 | 0.1895 | 0.2026 | 0.063 | 0.128 | -0.0296 [-0.0744, +0.0123] |
| OU25|New Format|2026-09 | 317 | 25 | 0.6933 | 0.6723 | 0.2500 | 0.2401 | 0.047 | 0.036 | +0.0210 [+0.0008, +0.0422] |
| OU25|New Format|2026-10 | 339 | 25 | 0.6854 | 0.6714 | 0.2462 | 0.2392 | 0.077 | 0.030 | +0.0140 [-0.0028, +0.0338] |
| OU25|Standard|2026-09 | 257 | 22 | 0.6891 | 0.6854 | 0.2480 | 0.2461 | 0.025 | 0.063 | +0.0037 [-0.0151, +0.0194] |
| OU25|Standard|2026-10 | 257 | 21 | 0.7020 | 0.6917 | 0.2544 | 0.2491 | 0.054 | 0.050 | +0.0103 [-0.0084, +0.0235] |
| OU35|New Format|2026-09 | 134 | 22 | 0.6620 | 0.6496 | 0.2347 | 0.2285 | 0.100 | 0.070 | +0.0124 [-0.0256, +0.0376] |
| OU35|New Format|2026-10 | 133 | 18 | 0.6854 | 0.6551 | 0.2456 | 0.2312 | 0.090 | 0.081 | +0.0303 [-0.0025, +0.0716] |
| OU35|Standard|2026-09 | 38 | 11 | 0.6543 | 0.6745 | 0.2302 | 0.2407 | 0.104 | 0.163 | -0.0202 [-0.0927, +0.0723] |
| OU35|Standard|2026-10 | 54 | 14 | 0.6393 | 0.6377 | 0.2230 | 0.2227 | 0.101 | 0.120 | +0.0016 [-0.0845, +0.0800] |

* OU25|Standard: model LL Oct - Sep +0.0129 [-0.0004, +0.0283]; gap to market Oct - Sep +0.0066 [-0.0186, +0.0306].
* OU25|New Format: model LL Oct - Sep -0.0079 [-0.0312, +0.0157]; gap to market Oct - Sep -0.0070 [-0.0335, +0.0211].
* BTTS|Standard: model LL Oct - Sep +0.0082 [-0.0057, +0.0286]; gap to market Oct - Sep -0.0140 [-0.0349, -0.0004].
* BTTS|New Format: model LL Oct - Sep -0.0023 [-0.0214, +0.0174]; gap to market Oct - Sep +0.0170 [-0.0056, +0.0380].
* OU35|Standard: model LL Oct - Sep -0.0150 [-0.1904, +0.1346]; gap to market Oct - Sep +0.0219 [-0.1006, +0.1255].
* OU35|New Format: model LL Oct - Sep +0.0234 [-0.0308, +0.0981]; gap to market Oct - Sep +0.0179 [-0.0235, +0.0745].

O1.5 has too few fixtures with >= 3 two-sided books to compare month on month: NOT DIRECTLY COMPARABLE. Cells where the model's own log loss improved with a CI excluding zero: none. Cells where the gap to the market narrowed with a CI excluding zero: BTTS|Standard - check whether that is the model improving or the market getting worse (compare the two LL columns above).

## 10. HGB challenger (H-MODEL-01) - shadow, DO NOT PROMOTE

| Track | Paired N | Matchdays | Window | Champion LL | Challenger LL | Champion Brier | Challenger Brier | LL delta (95% CI) | Brier delta (95% CI) | Market LL same rows |
|---|---|---|---|---|---|---|---|---|---|---|
| newformat | 105 | 5 | 2026-10-23 to 2026-10-27 | 0.6889 | 0.6681 | 0.2479 | 0.2378 | -0.0208 [-0.0689, -0.0056] | -0.0102 [-0.0340, -0.0030] | 0.64826 |
| standard | 88 | 5 | 2026-10-23 to 2026-10-27 | 0.6995 | 0.7113 | 0.2532 | 0.2589 | +0.0118 [-0.0031, +0.0270] | +0.0058 [-0.0015, +0.0132] | 0.71122 |

Recomputed here and matching v9's own evaluator (`shadow_experiments_eval.json`). New Format: the challenger is better on both metrics with intervals excluding zero - but on 5 matchdays, against PG-1.0's prospective floor of 1000 rows per track, and it is still worse than the market on the same rows. Standard: the challenger is worse (CI includes zero). Neither is promotable; no Sep/Oct comparison exists because the experiment started 2026-10-22.

## 11. CLV collection

| Period | Eligible | T30 certified | T10 certified | Stale close | Median last pre-kickoff close (min) |
|---|---|---|---|---|---|
| ALL-TIME (v91_shadow from 2026-10-04) | 658 | 26.3% | 19.0% | 485 | 204.2 |
| POST-COLLECTION-FIX (from 2026-10-23) | 194 | 70.6% | 60.3% | 57 | 1.9 |
| October before the fix (recomputed) | 464 | 7.8% | 1.7% | 92.2% | 321.5 |
| October after the fix (recomputed, settled) | 194 | 70.6% | 60.3% | 29.4% | 1.9 |
| September | NOT MEASURABLE | - | - | - | - |

Collector window since 2026-10-23 (all markets, 296 fixtures): T30 67.9%, T10 65.8%, median last observation 1.6 min before kickoff; health check {'status': 'PASS', 'reasons': []}.

Why September is not measurable: the odds archives are change-logs (a row only when a price moves), so the last stored row is the last CHANGE, not the last time anyone looked. Only the odds heartbeat (from 2026-10-22) and v91_shadow's close audit measure the last OBSERVATION. **Is October evidence more trustworthy?** For CLV, yes - after 2026-10-23 a CLV figure is backed by a close observed inside 30 minutes about 70% of the time, versus under 10% before. For ROI, only modestly: the first-logged freeze (2026-10-26) removes rewritten side-market prices going forward, but October's results still come from the same v9 models.

## 12. Market-relative: is WOWZA learning information the market does not know?

| Source | Sep | Oct |
|---|---|---|
| v11 residual: market+WOWZA blend minus market LL (OU25, all fixtures) | +0.00126 [-0.0018, +0.0051] n 492 | -0.00021 [-0.0014, +0.0011] n 503 |
| v9 model minus market LL, OU25 Standard | +0.0065 [-0.0118, +0.0222] | +0.0188 [+0.0013, +0.0323] |
| v9 model minus market LL, OU25 New Format | +0.0158 [-0.0144, +0.0448] | +0.0119 [-0.0079, +0.0374] |

market_edge_v2 shadow (model vs fair market vs decision probability, from 2026-10-25 only - October snapshot, NOT COMPARABLE with September):

| Market / track | N | Matchdays | Model LL | Market LL | Decision LL | Model Brier | Market Brier | Decision Brier | Model - market LL 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| BTTS|new_format | 33 | 3 | 0.6154 | 0.5775 | 0.5814 | 0.2115 | 0.1932 | 0.1951 | [-0.0422, +0.1381] |
| BTTS|standard | 26 | 3 | 0.7074 | 0.7021 | 0.7017 | 0.2570 | 0.2542 | 0.2540 | [-0.0657, +0.0948] |
| OU25|new_format | 33 | 3 | 0.6954 | 0.6147 | 0.6174 | 0.2513 | 0.2118 | 0.2130 | [-0.0083, +0.3360] |
| OU25|standard | 26 | 3 | 0.6672 | 0.6307 | 0.6345 | 0.2371 | 0.2193 | 0.2212 | [+0.0129, +0.0747] |
| OU35|new_format | 14 | 2 | 0.7416 | 0.7003 | 0.7011 | 0.2710 | 0.2537 | 0.2542 | [+0.0398, +0.0451] |

**Answer: no measurable evidence.** In both months the de-vigged market forecasts at least as well as v9, and adding v9 to the market does not improve it (September +0.00126 [-0.0018, +0.0051], October -0.00021 [-0.0014, +0.0011]). The decision probability of the market-first engine tracks the market, which is the intended behaviour.

## 13. Bankroll research (Pro walk-forward, paper)

| Policy | Sep return | Sep max DD | Oct return | Oct max DD | Bankroll end Oct |
|---|---|---|---|---|---|
| ADAPTIVE | +17.07% | 2.0% | -0.38% | 8.5% | 116.63 |
| STATIC_BALANCED | +16.52% | 4.1% | +4.97% | 6.8% | 122.31 |
| FLAT_0.5 | +2.79% | 2.9% | +6.59% | 6.1% | 109.56 |
| FLAT_1 | +6.66% | 4.0% | +10.99% | 6.5% | 118.38 |
| FLAT_2 | +9.99% | 4.7% | +13.52% | 6.9% | 124.86 |

Source: Pro `output/bankroll/walk_forward.csv` (each month's policy chosen with data before that month; evidence cutoff 2026-10-25). **September made more money under the managed policies**: ADAPTIVE +17.1% with a 2.0% drawdown, then -0.4% with a 8.5% drawdown in October. That pattern is consistent with the NF BTTS reversal: the managed policies stake NF BTTS hardest (1.25% vs 0.5% for the other active tracks) because it had the best evidence, so its October reversal costs them most (attribution by track was not recomputed here); flat staking spreads risk evenly and did better in October. Discipline here means sizing by evidence and cutting what fails (NF OU25 UNDER -> STOP proposed); it bounds drawdown and survival risk, it does not guarantee a better month. Walk-forward validation is NOT_VALIDATED_INSUFFICIENT_MONTHS (2 of 6).

## 14. Track level

| Track | Sep evidence | Oct evidence | Change (90% CI) | Current state (v9 config/bankroll_policy.json) | Pro monthly review (dry run, cutoff 2026-10-25) |
|---|---|---|---|---|---|
| NF BTTS | +27.7% n 104 | -4.3% n 107 | -32.1% [-54.5%, -7.7%] | ACTIVE 1.25% | KEEP -> ACTIVE ('increase blocked: median CLV >= 0 on 30+, quarter-Kelly supports the next band') |
| NF OU25 OVER | +3.5% n 60 | +18.0% n 27 | +14.6% [-32.6%, +66.1%] | ACTIVE_LOW 0.50% | KEEP -> ACTIVE_LOW ('increase blocked: shrunk ROI >= +1%, 90% lower bound > 0, both halves positive, quarter-Kelly supports the next band') |
| NF OU25 UNDER | -5.5% n 161 | -0.0% n 235 | +5.5% [-20.1%, +28.8%] | ACTIVE_LOW 0.50% | STOP -> STOPPED ('shrunk ROI -2.0% on n=402') |
| NF O1.5 | +0.8% n 37 | +17.2% n 38 | +16.4% [-11.9%, +44.8%] | ACTIVE_LOW 0.50% | KEEP -> ACTIVE_LOW ('increase blocked: shrunk ROI >= +1%, 90% lower bound > 0, both halves positive, quarter-Kelly supports the next band') |
| Standard OU25 | -12.3% n 175 | -7.5% n 150 | +4.8% [-14.9%, +25.3%] | OVER PAPER / UNDER PAPER | KEEP_PAPER -> PAPER ('paper track; money requires owner approval') |
| Standard BTTS | +2.9% n 84 | -0.5% n 53 | -3.3% [-28.6%, +24.6%] | PAPER 0.00% | KEEP_PAPER -> PAPER ('paper track; money requires owner approval') |

Learned policy change: the 2026-10 monthly review (Pro `output/bankroll/MONTHLY_REVIEW.md`, dry run for the 11-01 cycle) proposes NF OU25 UNDER ACTIVE_LOW -> STOP on n=402 settled bets, shrunk ROI -2.0%. This report's own figures agree: NF OU25 UNDER -5.5% in September and -0.0% in October. Production is unchanged until the owner approves the PR.

## 15. Tier learning

These are historical raw-gap labels, not confidence levels.

| Window / scope / month | ROI Big gap | ROI Medium gap | ROI Small gap | N (B/M/S) | Monotonic? |
|---|---|---|---|---|---|
| A|all|sep | -7.5% | +1.8% | -9.2% | 25/69/302 | False |
| A|all|oct | -6.3% | -25.9% | +6.5% | 57/80/275 | False |
| A|Standard|sep | -2.4% | +2.8% | -16.8% | 14/30/131 | False |
| A|Standard|oct | -40.0% | -3.2% | -5.7% | 9/14/127 | False |
| A|New Format|sep | -13.9% | +1.1% | -3.4% | 11/39/171 | False |
| A|New Format|oct | -0.0% | -30.7% | +17.0% | 48/66/148 | False |
| B|all|sep | -16.2% | +3.7% | -12.0% | 9/17/23 | False |
| B|all|oct | -6.3% | -25.9% | +6.5% | 57/80/275 | False |
| B|Standard|sep | +13.2% | +17.1% | -49.4% | 5/9/12 | False |
| B|Standard|oct | -40.0% | -3.2% | -5.7% | 9/14/127 | False |
| B|New Format|sep | -53.0% | -11.4% | +28.7% | 4/8/11 | False |
| B|New Format|oct | -0.0% | -30.7% | +17.0% | 48/66/148 | False |

Not monotonic in any window, scope or month. **Raw model-market disagreement magnitude is not a reliable quality ordering.** Tiers here are the FIRST-LOGGED tier (before 2026-10-26 the ledger upgraded tiers in place; 271 OU25 rows were upgraded).

## 16. V11 independent scoreboard (v9 tips as graded by wowza_v11)

| Month | System | Picks | W | L | Hit | PnL | PnL / pick |
|---|---|---|---|---|---|---|---|
| 2026-09 | v9 | 209 | 76 | 133 | 36.4 | -26.60 | -0.127 |
| 2026-09 | v11 | 0 | 0 | 0 |  | +0.00 | n/a |
| 2026-10 | v9 | 278 | 118 | 160 | 42.4 | -4.23 | -0.015 |
| 2026-10 | v11 | 0 | 0 | 0 |  | +0.00 | n/a |

v11 grades v9's live O/U 2.5 tips from its own shadow log and prices, so its counts differ from the first-logged ledger in section 3. Direction agrees with section 3: v9 lost less per pick in October. v11 itself placed 0 bets in both months - its market-first engine has never found a BET or PAPER state worth taking.

## 17. V11 research learning, September -> October

* Movement signal month 2026-09: toward-model rate 0.5141 (CI 0.4816-0.5452, p 0.38363), mean signed move 0.2583pp, mean CLV -0.0861%, CLV>0 0.3869, n 17522 snapshots / 701 fixtures.
* Movement signal month 2026-10: toward-model rate 0.513 (CI 0.4805-0.5429, p 0.41355), mean signed move 0.0379pp, mean CLV -0.3979%, CLV>0 0.3086, n 16808 snapshots / 851 fixtures.
* Residual-movement fold 1 (2026-08-21 to 2026-08-24): coef +0.0125 [+0.0025, +0.0238], excludes zero True.
* Residual-movement fold 2 (2026-08-24 to 2026-08-26): coef +0.0064 [+0.0012, +0.0118], excludes zero True.
* Residual-movement fold 3 (2026-08-26 to 2026-09-17): coef +0.0217 [+0.0097, +0.0323], excludes zero True.
* Residual-movement fold 4 (2026-09-17 to 2026-10-27): coef +0.0017 [-0.0014, +0.0049], excludes zero False.
* Placebo table (all months pooled): v9 residual toward-rate 0.2742 vs shuffled-residual placebo 0.2715 and fixed-anchor placebo 0.2795: the real residual sits between its placebos - it does not clearly beat them.
* Residual model (market + WOWZA vs market): September +0.00126, October -0.00021 LL - no gain either month.

Read: the movement signal weakened from August into September and October (October fold's residual coefficient CI includes zero, mean CLV turned more negative). These are negative results and they count: v11 is not profitable and has not found an edge; it learned that the earlier movement 'signal' does not persist out of sample.

## 18. System maturity (dated from git history on origin/main)

| First on main | Repo | Capability | Path / commit |
|---|---|---|---|
| 2026-09-24 | v9 | Club alias split fix (one club was becoming two teams) | `6c80672f` |
| 2026-10-01 | v9 | Leak-free validation harness + champion/challenger gate (shadow) | `src/promotion_gate.py` |
| 2026-10-04 | v9 | v9.1 shadow: every fixture's served prob + market + outcome | `output/v91_shadow.csv` |
| 2026-10-06 | v9 | Evidence allocator with RELIABLE_FROM epoch + matchday bootstrap | `src/allocation.py` |
| 2026-10-13 | v9 | Bankroll policy file (WIRED_PAPER) | `config/bankroll_policy.json` |
| 2026-10-13 | pro | Pro bankroll research (walk-forward, stress tests) | `src/bankroll/__init__.py` |
| 2026-10-18 | v9 | Champion high-water mark: retrains are challengers | `src/champion_gate.py` |
| 2026-10-18 | v9 | Model lineage (champion history, retrain batches) | `output/model_lineage/champion_history.csv` |
| 2026-10-22 | v9 | Shadow challenger framework (H-MODEL-01 HGB) | `output/model_lineage/shadow_experiments.csv` |
| 2026-10-22 | v9 | CLV collection health (T30/T10 certified close) | `output/clv_collection_health.json` |
| 2026-10-22 | v9 | Odds heartbeat (last OBSERVATION, not last change) | `output/odds_heartbeat` |
| 2026-10-25 | v9 | STRICT PG-1.0 gate declared (sole writer of current_champions) | `config/promotion_gate.json` |
| 2026-10-25 | v9 | Market-first shadow engine (market_edge_v2) | `src/edge_engine_shadow.py` |
| 2026-10-25 | v9 | Research lock: protected-track fingerprint | `src/research_lock.py` |
| 2026-10-25 | v9 | First-sight immutable research store | `src/research/first_sight.py` |
| 2026-10-25 | v9 | Weekly league panel (first sight) | `output/league_weekly_research.csv` |
| 2026-10-25 | v9 | Canonical system-health checks | `output/system_health.json` |
| 2026-10-25 | v9 | Opposite-direction guard on one fixture | `src/direction_guard.py` |
| 2026-10-26 | v9 | Ledger first-logged freeze (later sightings logged separately) | `output/ledger_tier_seen.csv` |
| 2026-10-26 | pro | Standard repair programme (league x market x side) | `src/studies/standard_repair` |

Commits by month (origin/main, Sep-Oct): v9: {'2026-09': {'automated': 1512, 'human': 108}, '2026-10': {'automated': 1493, 'human': 247}}; pro: {'2026-10': {'automated': 752, 'human': 127}}; v11: {'2026-09': {'automated': 136, 'human': 5}, '2026-10': {'automated': 99, 'human': 1}}. (Pro's history on main starts 2026-10-12, so it has no September commits to count.)

1 listed capability landed in September; 19 in October. September's system had one gate (a tolerance with no interval), no lineage, no shadow challenger, no certified close, no first-sight store and overwritable ledger prices. October's has all of them, plus protected-track locks (research_lock) and an explicit identity/alias audit for Standard.

## Method and traps handled

* Data: v9 and wowza_v11 read with `git show origin/main:<path>` after `git fetch`; Pro store and bankroll outputs from the Pro worktree at origin/main; Standard data-quality burden read-only from the pro_v9r worktree.
* Ledger: first-logged odds and tier rebuilt from every v9 commit of each ledger since 2026-08-20; P/L in units at that price.
* Intervals: 90% for ROI and ROI changes, 95% for log-loss/Brier deltas; matchday block bootstrap, 2000 draws, fixed seed.
* Snapshots treated as change-logs (last pre-kickoff quote per book carried forward); no merge_asof index assignment; thresholds not re-derived from config.py; no mtime-based freshness.

PRODUCTION_CHANGES_MADE = NO
