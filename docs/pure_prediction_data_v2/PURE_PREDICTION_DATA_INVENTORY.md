# PURE PREDICTION — DATA INVENTORY

What exists, over what period, and how complete it is. This document is written before 
any model is fitted, because it decides which questions the warehouse can be asked at 
all. A feature present on 2% of rows is not a weak feature — it is an absent one, and 
an experiment that 'tests' it is really testing the 2% of fixtures that happen to have it.

**Fixtures usable for the match lab: 54,524** across 32 leagues.

## Sources

| source | repo | path | granularity | rows | span | used for |
|---|---|---|---|---|---|---|
| football-data.co.uk history | wowza-betting (v9) | `output/fd_history.parquet` | fixture | 54,524 | 2019-02 → 2026-09 | targets, shots, SOT, corners, fouls, HT goals, odds |
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
| 0.05 | 2019-11-10 | 2701 | 51823 | 0 | 0 |
| 0.25 | 2022-08-07 | 13581 | 40943 | 0 | 0 |
| 0.55 | 2024-08-14 | 29988 | 24536 | 0 | 0 |
| 0.85 | 2026-02-08 | 46339 | 8185 | 0 | 0 |


Single-feature AUC was also checked as a tripwire: of 568 feature-target 
pairs, 0 exceeded 0.80. The strongest single column 
anywhere reaches AUC 0.6786, which is what a real football feature looks 
like. A leaked outcome would sit near 1.0.

## Per-league coverage

| league | model_type | rows | first | last | cov_shots | cov_sot | cov_corners | cov_ht_goals | cov_cards | cov_xg | cov_odds_ou25 | rate_btts | rate_over25 | avg_goals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USA MLS | new_format | 4371 | 2019-03-02 | 2026-11-08 | 0.5024 | 0.5024 | 0.5022 | 0.0881 | 0.0046 | 0.2178 | 0.0837 | 0.6019 | 0.5921 | 3.005 |
| Argentina Primera Division | new_format | 3808 | 2019-07-27 | 2026-11-08 | 0.4596 | 0.4596 | 0.4593 | 0.072 | 0.0068 | 0.1368 | 0.0993 | 0.4454 | 0.3768 | 2.192 |
| Romanian Superliga | new_format | 3470 | 2019-07-12 | 2026-11-09 | 0.5712 | 0.5689 | 0.5709 | 0.1458 | 0.0003 | 0.0974 | 0.0184 | 0.4856 | 0.4352 | 2.445 |
| Brazil Serie A | new_format | 3164 | 2019-04-27 | 2026-11-06 | 0.6369 | 0.6369 | 0.6356 | 0.0834 | 0.0035 | 0.2165 | 0.1267 | 0.5019 | 0.4501 | 2.441 |
| Japan J-League | new_format | 2657 | 2019-02-22 | 2026-11-08 | 0.6255 | 0.6255 | 0.6255 | 0.0802 | 0.0041 | 0.0903 | 0.0632 | 0.5036 | 0.4821 | 2.6 |
| Mexico Liga MX | new_format | 2534 | 2019-07-20 | 2026-11-09 | 0.5967 | 0.5967 | 0.5963 | 0.0706 | 0.0047 | 0.1369 | 0.1034 | 0.5552 | 0.5142 | 2.732 |
| Saudi Pro League | new_format | 1920 | 2019-08-22 | 2026-09-04 | 0.988 | 0.988 | 0.987 | 0.2589 | 0.0 | 0.1583 | 0.0 | 0.562 | 0.5573 | 2.903 |
| Sweden Allsvenskan | new_format | 1918 | 2019-03-31 | 2026-11-08 | 0.9468 | 0.9468 | 0.9468 | 0.1778 | 0.0036 | 0.1554 | 0.0412 | 0.524 | 0.5282 | 2.776 |
| Norway Eliteserien | new_format | 1897 | 2019-03-30 | 2026-11-09 | 0.5999 | 0.5994 | 0.5994 | 0.0727 | 0.0074 | 0.2061 | 0.1223 | 0.583 | 0.6046 | 3.097 |
| Championship | standard | 1849 | 2023-08-04 | 2026-11-07 | 1.0 | 1.0 | 0.993 | 0.993 | 0.0 | 0.3342 | 0.993 | 0.5381 | 0.5035 | 2.611 |
| China Super League | new_format | 1845 | 2019-03-01 | 2026-11-08 | 0.8011 | 0.8011 | 0.8005 | 0.1241 | 0.0043 | 0.1285 | 0.0743 | 0.5691 | 0.5696 | 2.957 |
| National League | standard | 1845 | 2023-08-05 | 2026-10-31 | 0.1024 | 0.1024 | 0.1024 | 1.0 | 0.0 | 0.1718 | 1.0 | 0.5729 | 0.5512 | 2.885 |
| League Two | standard | 1833 | 2023-08-05 | 2026-11-03 | 1.0 | 1.0 | 0.9929 | 0.9929 | 0.0 | 0.2651 | 0.9929 | 0.5368 | 0.4965 | 2.68 |
| League One | standard | 1829 | 2023-08-05 | 2026-11-04 | 1.0 | 1.0 | 0.9923 | 0.9923 | 0.0 | 0.2559 | 0.9923 | 0.5205 | 0.503 | 2.613 |
| La Liga 2 | standard | 1543 | 2023-08-11 | 2026-11-09 | 1.0 | 1.0 | 0.989 | 0.989 | 0.0 | 0.2443 | 0.989 | 0.5094 | 0.4569 | 2.489 |
| Denmark Superliga | new_format | 1483 | 2019-07-12 | 2026-11-08 | 0.4956 | 0.4956 | 0.4956 | 0.0695 | 0.0047 | 0.2097 | 0.1753 | 0.588 | 0.5604 | 2.883 |
| K-League 1 | new_format | 1472 | 2020-05-08 | 2026-08-30 | 0.7412 | 0.7412 | 0.7412 | 0.2704 | 0.0 | 0.1121 | 0.0 | 0.534 | 0.4694 | 2.54 |
| Austrian Bundesliga | new_format | 1436 | 2019-07-26 | 2026-11-08 | 0.7918 | 0.7918 | 0.7918 | 0.1588 | 0.007 | 0.101 | 0.1525 | 0.5529 | 0.5578 | 2.916 |
| Ireland Premier Division | new_format | 1358 | 2019-02-15 | 2026-11-07 | 0.2187 | 0.2187 | 0.2187 | 0.1127 | 0.0044 | 0.1141 | 0.0987 | 0.4882 | 0.4617 | 2.486 |
| Finland Veikkausliiga | new_format | 1328 | 2019-04-03 | 2026-11-08 | 0.2538 | 0.253 | 0.2538 | 0.0625 | 0.0045 | 0.1453 | 0.1446 | 0.5316 | 0.5256 | 2.761 |
| Serie B | standard | 1278 | 2023-08-18 | 2026-11-08 | 1.0 | 1.0 | 0.9781 | 0.9781 | 0.0 | 0.3216 | 0.9781 | 0.5469 | 0.4757 | 2.516 |
| Turkish Super Lig | standard | 1127 | 2023-08-11 | 2026-11-08 | 0.9982 | 0.9982 | 0.9982 | 0.9982 | 0.0 | 0.2547 | 1.0 | 0.5448 | 0.5368 | 2.818 |
| Ligue 2 | standard | 1098 | 2023-08-05 | 2026-11-07 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1703 | 1.0 | 0.5 | 0.4754 | 2.536 |
| Belgian First Division A | standard | 1035 | 2023-07-28 | 2026-11-08 | 0.999 | 0.999 | 0.999 | 0.999 | 0.0 | 0.3111 | 1.0 | 0.5362 | 0.5314 | 2.793 |
| Dutch Eredivisie | standard | 1026 | 2023-08-11 | 2026-11-08 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5058 | 1.0 | 0.5955 | 0.615 | 3.214 |
| Bundesliga 2 | standard | 1022 | 2023-07-28 | 2026-11-08 | 1.0 | 1.0 | 0.9951 | 0.9951 | 0.0 | 0.184 | 0.9951 | 0.592 | 0.591 | 3.011 |
| Portuguese Primeira Liga | standard | 1016 | 2023-08-11 | 2026-11-08 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5719 | 1.0 | 0.498 | 0.5276 | 2.699 |
| Greek Super League | standard | 780 | 2023-08-18 | 2026-11-08 | 1.0 | 1.0 | 0.9962 | 0.9962 | 0.0 | 0.2231 | 0.9962 | 0.5026 | 0.5205 | 2.665 |
| Scottish Premiership | standard | 759 | 2023-08-05 | 2026-11-08 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.2899 | 1.0 | 0.5231 | 0.5586 | 2.835 |
| Scottish Championship | standard | 609 | 2023-08-04 | 2026-11-07 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1856 | 1.0 | 0.4762 | 0.4778 | 2.542 |
| Scottish League One | standard | 609 | 2023-08-05 | 2026-11-07 | 0.9984 | 0.9984 | 0.9984 | 1.0 | 0.0 | 0.0525 | 1.0 | 0.5402 | 0.5517 | 2.844 |
| Scottish League Two | standard | 605 | 2023-08-05 | 2026-11-07 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0314 | 1.0 | 0.5372 | 0.5174 | 2.777 |
