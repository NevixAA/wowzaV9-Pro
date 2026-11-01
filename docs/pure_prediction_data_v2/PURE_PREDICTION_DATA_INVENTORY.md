# PURE PREDICTION — DATA INVENTORY

What exists, over what period, and how complete it is. This document is written before 
any model is fitted, because it decides which questions the warehouse can be asked at 
all. A feature present on 2% of rows is not a weak feature — it is an absent one, and 
an experiment that 'tests' it is really testing the 2% of fixtures that happen to have it.

**Fixtures usable for the match lab: 51,624** across 30 leagues.

## Sources

| source | repo | path | granularity | rows | span | used for |
|---|---|---|---|---|---|---|
| football-data.co.uk history | wowza-betting (v9) | `output/fd_history.parquet` | fixture | 51,624 | 2019-02 → 2026-09 | targets, shots, SOT, corners, fouls, HT goals, odds |
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
| 0.05 | 2019-11-01 | 2582 | 49042 | 0 | 0 |
| 0.25 | 2022-07-08 | 12898 | 38726 | 0 | 0 |
| 0.55 | 2024-07-17 | 28384 | 23240 | 0 | 0 |
| 0.85 | 2026-01-24 | 43820 | 7804 | 0 | 0 |


Single-feature AUC was also checked as a tripwire: of 568 feature-target 
pairs, 0 exceeded 0.80. The strongest single column 
anywhere reaches AUC 0.6690, which is what a real football feature looks 
like. A leaked outcome would sit near 1.0.

## Per-league coverage

| league | model_type | rows | first | last | cov_shots | cov_sot | cov_corners | cov_ht_goals | cov_cards | cov_xg | cov_odds_ou25 | rate_btts | rate_over25 | avg_goals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USA MLS | new_format | 4341 | 2019-03-02 | 2026-10-29 | 0.5059 | 0.5059 | 0.5056 | 0.0887 | 0.0039 | 0.2119 | 0.0562 | 0.6019 | 0.5918 | 3.003 |
| Argentina Primera Division | new_format | 3778 | 2019-07-27 | 2026-10-27 | 0.4632 | 0.4632 | 0.4629 | 0.0725 | 0.0032 | 0.1305 | 0.0723 | 0.4442 | 0.3764 | 2.188 |
| Brazil Serie A | new_format | 3152 | 2019-04-27 | 2026-10-30 | 0.6393 | 0.6393 | 0.638 | 0.0838 | 0.0051 | 0.2154 | 0.1082 | 0.5019 | 0.4496 | 2.439 |
| Japan J-League | new_format | 2637 | 2019-02-22 | 2026-10-25 | 0.6303 | 0.6303 | 0.6303 | 0.0808 | 0.0019 | 0.1062 | 0.0527 | 0.504 | 0.4816 | 2.598 |
| Mexico Liga MX | new_format | 2516 | 2019-07-20 | 2026-10-29 | 0.601 | 0.601 | 0.6006 | 0.0711 | 0.0024 | 0.1387 | 0.0771 | 0.5552 | 0.5135 | 2.729 |
| Romanian Superliga | new_format | 2232 | 2019-07-12 | 2026-09-04 | 0.9373 | 0.9337 | 0.9373 | 0.2469 | 0.0 | 0.1622 | 0.0 | 0.4843 | 0.4328 | 2.425 |
| Saudi Pro League | new_format | 1920 | 2019-08-22 | 2026-09-04 | 0.988 | 0.988 | 0.987 | 0.2589 | 0.0 | 0.1625 | 0.0 | 0.562 | 0.5573 | 2.903 |
| Sweden Allsvenskan | new_format | 1902 | 2019-03-31 | 2026-10-29 | 0.9548 | 0.9548 | 0.9548 | 0.1793 | 0.0042 | 0.2035 | 0.0037 | 0.5242 | 0.5284 | 2.782 |
| Norway Eliteserien | new_format | 1881 | 2019-03-30 | 2026-10-25 | 0.605 | 0.6045 | 0.6045 | 0.0734 | 0.0037 | 0.2238 | 0.0999 | 0.5827 | 0.6029 | 3.086 |
| National League | standard | 1833 | 2023-08-05 | 2026-10-28 | 0.0966 | 0.0966 | 0.0966 | 1.0 | 0.0 | 0.1849 | 1.0 | 0.5723 | 0.5505 | 2.881 |
| China Super League | new_format | 1833 | 2019-03-01 | 2026-10-24 | 0.8063 | 0.8063 | 0.8058 | 0.1249 | 0.0044 | 0.1342 | 0.0709 | 0.569 | 0.5685 | 2.954 |
| League Two | standard | 1820 | 2023-08-05 | 2026-10-27 | 1.0 | 1.0 | 0.9929 | 0.9929 | 0.0 | 0.2566 | 0.9929 | 0.5346 | 0.4951 | 2.675 |
| Championship | standard | 1813 | 2023-08-04 | 2026-10-24 | 1.0 | 1.0 | 0.9928 | 0.9928 | 0.0 | 0.3183 | 0.9928 | 0.5372 | 0.4997 | 2.598 |
| League One | standard | 1813 | 2023-08-05 | 2026-10-27 | 1.0 | 1.0 | 0.9923 | 0.9923 | 0.0 | 0.2559 | 0.9923 | 0.5212 | 0.5041 | 2.613 |
| La Liga 2 | standard | 1524 | 2023-08-11 | 2026-10-26 | 1.0 | 1.0 | 0.9888 | 0.9888 | 0.0 | 0.2244 | 0.9888 | 0.5079 | 0.4554 | 2.485 |
| K-League 1 | new_format | 1472 | 2020-05-08 | 2026-08-30 | 0.7412 | 0.7412 | 0.7412 | 0.2704 | 0.0 | 0.1162 | 0.0 | 0.534 | 0.4694 | 2.54 |
| Denmark Superliga | new_format | 1471 | 2019-07-12 | 2026-10-26 | 0.4997 | 0.4997 | 0.4997 | 0.07 | 0.002 | 0.1808 | 0.1421 | 0.5887 | 0.5608 | 2.882 |
| Austrian Bundesliga | new_format | 1424 | 2019-07-26 | 2026-10-25 | 0.7985 | 0.7985 | 0.7985 | 0.1601 | 0.0035 | 0.1088 | 0.1369 | 0.552 | 0.5569 | 2.908 |
| Ireland Premier Division | new_format | 1352 | 2019-02-15 | 2026-10-23 | 0.2197 | 0.2197 | 0.2197 | 0.1132 | 0.0037 | 0.1309 | 0.0806 | 0.4867 | 0.4601 | 2.48 |
| Finland Veikkausliiga | new_format | 1322 | 2019-04-03 | 2026-10-29 | 0.2549 | 0.2542 | 0.2549 | 0.0628 | 0.0053 | 0.1649 | 0.118 | 0.5318 | 0.525 | 2.753 |
| Serie B | standard | 1258 | 2023-08-18 | 2026-10-28 | 1.0 | 1.0 | 0.9777 | 0.9777 | 0.0 | 0.3124 | 0.9777 | 0.5477 | 0.4785 | 2.52 |
| Turkish Super Lig | standard | 1109 | 2023-08-11 | 2026-10-26 | 0.9982 | 0.9982 | 0.9982 | 0.9982 | 0.0 | 0.4013 | 1.0 | 0.5464 | 0.5347 | 2.807 |
| Ligue 2 | standard | 1080 | 2023-08-05 | 2026-10-26 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1861 | 1.0 | 0.5028 | 0.475 | 2.534 |
| Belgian First Division A | standard | 1015 | 2023-07-28 | 2026-10-25 | 0.999 | 0.999 | 0.999 | 0.999 | 0.0 | 0.3212 | 1.0 | 0.534 | 0.53 | 2.784 |
| Dutch Eredivisie | standard | 1008 | 2023-08-11 | 2026-10-25 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5129 | 1.0 | 0.5952 | 0.6141 | 3.194 |
| Bundesliga 2 | standard | 1004 | 2023-07-28 | 2026-10-25 | 1.0 | 1.0 | 0.995 | 0.995 | 0.0 | 0.2092 | 0.995 | 0.5916 | 0.5896 | 3.014 |
| Portuguese Primeira Liga | standard | 999 | 2023-08-11 | 2026-10-26 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5646 | 1.0 | 0.5005 | 0.5295 | 2.709 |
| Greek Super League | standard | 766 | 2023-08-18 | 2026-10-25 | 1.0 | 1.0 | 0.9961 | 0.9961 | 0.0 | 0.235 | 0.9961 | 0.5013 | 0.5196 | 2.667 |
| Scottish Premiership | standard | 750 | 2023-08-05 | 2026-10-28 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.272 | 1.0 | 0.524 | 0.56 | 2.835 |
| Scottish Championship | standard | 599 | 2023-08-04 | 2026-10-27 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1853 | 1.0 | 0.4741 | 0.4741 | 2.521 |
