# PURE PREDICTION — DATA INVENTORY

What exists, over what period, and how complete it is. This document is written before 
any model is fitted, because it decides which questions the warehouse can be asked at 
all. A feature present on 2% of rows is not a weak feature — it is an absent one, and 
an experiment that 'tests' it is really testing the 2% of fixtures that happen to have it.

**Fixtures usable for the match lab: 62,468** across 30 leagues.

## Sources

| source | repo | path | granularity | rows | span | used for |
|---|---|---|---|---|---|---|
| football-data.co.uk history | wowza-betting (v9) | `output/fd_history.parquet` | fixture | 62,468 | 2019-02 → 2026-09 | targets, shots, SOT, corners, fouls, HT goals, odds |
| API-Football history | wowza-betting (v9) | `output/af_history.parquet` | fixture | 28,504 | 2019-02 → 2026-09 | cards; nominally xG and inside-box |
| player match log | wowza-betting (v9) | `player_history.parquet` | player-match | 302,456 | 2022-08 → 2026-08 | goalscorer research |
| Pro season store | wowzaV9-Pro | `data/season_2026_27/**` | many | 5 weeks | 2026-08 → | too short for this lab; not used |

## The two findings that changed what could be asked

**1. xG is effectively absent.** The `HXG`/`AXG` columns exist in `af_history.parquet` and 
are populated on between 0.0% and 2.0% of rows in every single league. Inside-box shots 
are the same. So the question 'does xG materially help?' has no answer available from 
this warehouse — not a negative answer, *no* answer. Anything reported about xG would be 
a statement about the handful of fixtures that happen to carry it.

**2. Corners, half-time goals and the O/U 2.5 price were missing from every FINISHED 
season of the seven leagues we bet — and it was a cache bug, not a source gap.** 
Broken out by season the pattern is unmistakable: the Championship sits at 0% corners, 
0% half-time goals and 0% O/U price across 2023, 2024, 2025 and 2026, and at 100% on 
all three in 2026/27 — the one season the downloader always re-fetches. Same shape for 
League One, League Two, La Liga 2, Serie B, Bundesliga 2 and the Greek Super League.

The cause was in v9's `_ci_download_all`: a season already in the cache is never 
re-requested, and the check had started matching seasons whose cached rows predated the 
current column map — so the thin copy was served forever. Fixed in wowza-betting 
`36fcf4b5` (a season counts as banked only when its rows actually carry those columns), 
which re-downloads 21 historical league-seasons. **Any number in this report that 
touches CORNERS or HT was therefore computed on roughly one season of those leagues 
rather than four, and the next weekly run will supersede it.** The affected rows are 
the CORNERS and HT lines of the ablation table; the FORM, SHOTS, SOT and STRENGTH 
families are unaffected, since shots and shots on target were complete throughout.

One genuine source gap remains and cannot be closed: BTTS, Over 1.5 and Over 3.5 prices 
for these leagues. football-data.co.uk does not publish them in these files (2026/27 is 
0% too, on rows that are otherwise complete), and API-Football's odds endpoint is 
pre-match only. Those accumulate forward or not at all.

## Leakage verification

The features were rebuilt after randomising every result from a cutoff date onward. 
Every feature value on every earlier fixture had to be bit-identical. It was, at all 
four cutoffs:

| cutoff_q | cutoff_date | past_rows | future_rows | cells_changed | columns_leaking |
|---|---|---|---|---|---|
| 0.05 | 2020-02-01 | 3113 | 59355 | 0 | 0 |
| 0.25 | 2022-09-04 | 15566 | 46902 | 0 | 0 |
| 0.55 | 2024-07-06 | 34333 | 28135 | 0 | 0 |
| 0.85 | 2025-12-21 | 53056 | 9412 | 0 | 0 |


Single-feature AUC was also checked as a tripwire: of 568 feature-target 
pairs, 0 exceeded 0.80. The strongest single column 
anywhere reaches AUC 0.6470, which is what a real football feature looks 
like. A leaked outcome would sit near 1.0.

## Per-league coverage

| league | model_type | rows | first | last | cov_shots | cov_sot | cov_corners | cov_ht_goals | cov_cards | cov_xg | cov_odds_ou25 | rate_btts | rate_over25 | avg_goals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USA MLS | new_format | 4686 | 2019-03-02 | 2026-10-07 | 0.4688 | 0.4688 | 0.4686 | 0.0822 | 0.0 | 0.1995 | 0.0593 | 0.5973 | 0.5856 | 2.987 |
| Argentina Primera Division | new_format | 4458 | 2019-07-27 | 2026-10-06 | 0.3926 | 0.3926 | 0.3923 | 0.0615 | 0.0 | 0.1375 | 0.0814 | 0.4412 | 0.373 | 2.178 |
| Brazil Serie A | new_format | 3825 | 2019-04-27 | 2026-10-09 | 0.5268 | 0.5268 | 0.5258 | 0.069 | 0.0 | 0.1963 | 0.1067 | 0.5048 | 0.4515 | 2.448 |
| Mexico Liga MX | new_format | 3302 | 2019-07-20 | 2026-09-28 | 0.4582 | 0.4582 | 0.4579 | 0.0542 | 0.0 | 0.0996 | 0.0578 | 0.5536 | 0.5167 | 2.717 |
| Japan J-League | new_format | 3119 | 2019-02-22 | 2026-09-20 | 0.5329 | 0.5329 | 0.5329 | 0.0683 | 0.0 | 0.1292 | 0.0446 | 0.5079 | 0.4787 | 2.598 |
| Sweden Allsvenskan | new_format | 2957 | 2019-03-31 | 2026-09-20 | 0.6141 | 0.6141 | 0.6141 | 0.1153 | 0.0 | 0.1992 | 0.0751 | 0.5262 | 0.5313 | 2.799 |
| China Super League | new_format | 2729 | 2019-03-01 | 2026-09-18 | 0.5416 | 0.5416 | 0.5412 | 0.0839 | 0.0 | 0.1341 | 0.0879 | 0.5625 | 0.5665 | 2.944 |
| League One | standard | 2522 | 2023-08-05 | 2026-10-03 | 1.0 | 1.0 | 0.6923 | 0.6923 | 0.0 | 0.2383 | 0.6923 | 0.5266 | 0.5083 | 2.626 |
| League Two | standard | 2488 | 2023-08-05 | 2026-10-03 | 1.0 | 1.0 | 0.7066 | 0.7066 | 0.0 | 0.2496 | 0.7066 | 0.5346 | 0.5 | 2.68 |
| Championship | standard | 2324 | 2023-08-04 | 2026-09-20 | 1.0 | 1.0 | 0.7534 | 0.7534 | 0.0 | 0.3343 | 0.7534 | 0.5297 | 0.4901 | 2.568 |
| La Liga 2 | standard | 2291 | 2023-08-11 | 2026-10-05 | 1.0 | 1.0 | 0.6434 | 0.6434 | 0.0 | 0.2226 | 0.6434 | 0.512 | 0.4588 | 2.505 |
| Norway Eliteserien | new_format | 2273 | 2019-03-30 | 2026-09-20 | 0.5007 | 0.5002 | 0.5002 | 0.0607 | 0.0 | 0.2116 | 0.1157 | 0.5825 | 0.6027 | 3.076 |
| Romanian Superliga | new_format | 2232 | 2019-07-12 | 2026-09-04 | 0.9373 | 0.9337 | 0.9373 | 0.2469 | 0.0 | 0.1662 | 0.0 | 0.4843 | 0.4328 | 2.425 |
| Austrian Bundesliga | new_format | 2148 | 2019-07-26 | 2026-09-20 | 0.5293 | 0.5293 | 0.5293 | 0.1061 | 0.0 | 0.0801 | 0.0894 | 0.5521 | 0.5456 | 2.863 |
| Saudi Pro League | new_format | 1920 | 2019-08-22 | 2026-09-04 | 0.988 | 0.988 | 0.987 | 0.2589 | 0.0 | 0.1641 | 0.0 | 0.562 | 0.5573 | 2.903 |
| Bundesliga 2 | standard | 1917 | 2023-07-28 | 2026-09-20 | 1.0 | 1.0 | 0.507 | 0.507 | 0.0 | 0.2196 | 0.507 | 0.5962 | 0.5962 | 3.033 |
| National League | standard | 1799 | 2023-08-05 | 2026-10-03 | 0.0795 | 0.0795 | 0.0795 | 1.0 | 0.0 | 0.2029 | 1.0 | 0.5714 | 0.547 | 2.871 |
| Ireland Premier Division | new_format | 1798 | 2019-02-15 | 2026-10-08 | 0.1652 | 0.1652 | 0.1652 | 0.0862 | 0.0 | 0.1224 | 0.1079 | 0.4861 | 0.4583 | 2.486 |
| Denmark Superliga | new_format | 1752 | 2019-07-12 | 2026-09-20 | 0.4195 | 0.4195 | 0.4195 | 0.0588 | 0.0 | 0.2323 | 0.1182 | 0.5879 | 0.5576 | 2.889 |
| Finland Veikkausliiga | new_format | 1599 | 2019-04-03 | 2026-10-08 | 0.2108 | 0.2101 | 0.2108 | 0.0632 | 0.0 | 0.1614 | 0.122 | 0.5366 | 0.5366 | 2.777 |
| K-League 1 | new_format | 1472 | 2020-05-08 | 2026-08-30 | 0.7412 | 0.7412 | 0.7412 | 0.2704 | 0.0 | 0.1135 | 0.0 | 0.534 | 0.4694 | 2.54 |
| Serie B | standard | 1260 | 2023-08-18 | 2026-09-20 | 1.0 | 1.0 | 0.9444 | 0.9444 | 0.0 | 0.2865 | 0.9444 | 0.5484 | 0.4817 | 2.525 |
| Greek Super League | standard | 1195 | 2023-08-18 | 2026-09-20 | 0.9992 | 0.9992 | 0.6218 | 0.6218 | 0.0 | 0.2192 | 0.6226 | 0.4987 | 0.513 | 2.656 |
| Turkish Super Lig | standard | 1082 | 2023-08-11 | 2026-09-20 | 0.9982 | 0.9982 | 0.9982 | 0.9982 | 0.0 | 0.4168 | 1.0 | 0.549 | 0.5323 | 2.809 |
| Ligue 2 | standard | 1053 | 2023-08-05 | 2026-09-19 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.169 | 1.0 | 0.5005 | 0.4739 | 2.524 |
| Belgian First Division A | standard | 998 | 2023-07-28 | 2026-09-20 | 0.999 | 0.999 | 0.999 | 0.999 | 0.0 | 0.3156 | 1.0 | 0.5321 | 0.5251 | 2.762 |
| Dutch Eredivisie | standard | 981 | 2023-08-11 | 2026-09-20 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1295 | 1.0 | 0.5902 | 0.6126 | 3.178 |
| Portuguese Primeira Liga | standard | 980 | 2023-08-11 | 2026-09-20 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5735 | 1.0 | 0.501 | 0.5286 | 2.708 |
| Scottish Premiership | standard | 726 | 2023-08-05 | 2026-09-20 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.2782 | 1.0 | 0.5193 | 0.5551 | 2.817 |
| Scottish Championship | standard | 582 | 2023-08-04 | 2026-10-03 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1581 | 1.0 | 0.4777 | 0.4811 | 2.54 |
