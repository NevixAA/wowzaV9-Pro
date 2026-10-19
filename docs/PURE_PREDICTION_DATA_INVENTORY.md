# PURE PREDICTION — DATA INVENTORY

What exists, over what period, and how complete it is. This document is written before 
any model is fitted, because it decides which questions the warehouse can be asked at 
all. A feature present on 2% of rows is not a weak feature — it is an absent one, and 
an experiment that 'tests' it is really testing the 2% of fixtures that happen to have it.

**Fixtures usable for the match lab: 62,742** across 30 leagues.

## Sources

| source | repo | path | granularity | rows | span | used for |
|---|---|---|---|---|---|---|
| football-data.co.uk history | wowza-betting (v9) | `output/fd_history.parquet` | fixture | 62,742 | 2019-02 → 2026-09 | targets, shots, SOT, corners, fouls, HT goals, odds |
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
| 0.05 | 2020-02-02 | 3138 | 59604 | 0 | 0 |
| 0.25 | 2022-09-08 | 15678 | 47064 | 0 | 0 |
| 0.55 | 2024-07-13 | 34486 | 28256 | 0 | 0 |
| 0.85 | 2026-01-01 | 53294 | 9448 | 0 | 0 |


Single-feature AUC was also checked as a tripwire: of 568 feature-target 
pairs, 0 exceeded 0.80. The strongest single column 
anywhere reaches AUC 0.6478, which is what a real football feature looks 
like. A leaked outcome would sit near 1.0.

## Per-league coverage

| league | model_type | rows | first | last | cov_shots | cov_sot | cov_corners | cov_ht_goals | cov_cards | cov_xg | cov_odds_ou25 | rate_btts | rate_over25 | avg_goals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USA MLS | new_format | 4716 | 2019-03-02 | 2026-10-15 | 0.4659 | 0.4659 | 0.4656 | 0.0816 | 0.0 | 0.207 | 0.0592 | 0.5982 | 0.5867 | 2.992 |
| Argentina Primera Division | new_format | 4475 | 2019-07-27 | 2026-10-16 | 0.3911 | 0.3911 | 0.3908 | 0.0612 | 0.0 | 0.1397 | 0.082 | 0.4413 | 0.373 | 2.179 |
| Brazil Serie A | new_format | 3835 | 2019-04-27 | 2026-10-13 | 0.5254 | 0.5254 | 0.5244 | 0.0688 | 0.0 | 0.1961 | 0.1072 | 0.5053 | 0.4516 | 2.449 |
| Mexico Liga MX | new_format | 3311 | 2019-07-20 | 2026-10-12 | 0.457 | 0.457 | 0.4567 | 0.0541 | 0.0 | 0.1033 | 0.0577 | 0.5545 | 0.5165 | 2.719 |
| Japan J-League | new_format | 3129 | 2019-02-22 | 2026-10-11 | 0.5312 | 0.5312 | 0.5312 | 0.0681 | 0.0 | 0.1304 | 0.0444 | 0.5078 | 0.4787 | 2.598 |
| Sweden Allsvenskan | new_format | 2965 | 2019-03-31 | 2026-10-12 | 0.6125 | 0.6125 | 0.6125 | 0.115 | 0.0 | 0.2027 | 0.0749 | 0.5255 | 0.5309 | 2.8 |
| China Super League | new_format | 2737 | 2019-03-01 | 2026-10-11 | 0.54 | 0.54 | 0.5396 | 0.0837 | 0.0 | 0.1319 | 0.0877 | 0.5627 | 0.5667 | 2.947 |
| League One | standard | 2534 | 2023-08-05 | 2026-10-10 | 1.0 | 1.0 | 0.6938 | 0.6938 | 0.0 | 0.2466 | 0.6938 | 0.5272 | 0.5091 | 2.627 |
| League Two | standard | 2500 | 2023-08-05 | 2026-10-10 | 1.0 | 1.0 | 0.708 | 0.708 | 0.0 | 0.2556 | 0.708 | 0.5344 | 0.4988 | 2.677 |
| Championship | standard | 2348 | 2023-08-04 | 2026-10-14 | 1.0 | 1.0 | 0.756 | 0.756 | 0.0 | 0.3454 | 0.756 | 0.5298 | 0.4911 | 2.572 |
| La Liga 2 | standard | 2302 | 2023-08-11 | 2026-10-12 | 1.0 | 1.0 | 0.6451 | 0.6451 | 0.0 | 0.2354 | 0.6451 | 0.5122 | 0.4596 | 2.507 |
| Norway Eliteserien | new_format | 2281 | 2019-03-30 | 2026-10-12 | 0.4989 | 0.4985 | 0.4985 | 0.0605 | 0.0 | 0.2126 | 0.1162 | 0.5835 | 0.6028 | 3.078 |
| Romanian Superliga | new_format | 2232 | 2019-07-12 | 2026-09-04 | 0.9373 | 0.9337 | 0.9373 | 0.2469 | 0.0 | 0.1658 | 0.0 | 0.4843 | 0.4328 | 2.425 |
| Austrian Bundesliga | new_format | 2154 | 2019-07-26 | 2026-10-11 | 0.5279 | 0.5279 | 0.5279 | 0.1058 | 0.0 | 0.0803 | 0.0896 | 0.5515 | 0.5455 | 2.863 |
| Bundesliga 2 | standard | 1926 | 2023-07-28 | 2026-10-11 | 1.0 | 1.0 | 0.5093 | 0.5093 | 0.0 | 0.2139 | 0.5093 | 0.5955 | 0.5955 | 3.032 |
| Saudi Pro League | new_format | 1920 | 2019-08-22 | 2026-09-04 | 0.988 | 0.988 | 0.987 | 0.2589 | 0.0 | 0.1625 | 0.0 | 0.562 | 0.5573 | 2.903 |
| National League | standard | 1811 | 2023-08-05 | 2026-10-10 | 0.0856 | 0.0856 | 0.0856 | 1.0 | 0.0 | 0.1734 | 1.0 | 0.5704 | 0.5472 | 2.874 |
| Ireland Premier Division | new_format | 1800 | 2019-02-15 | 2026-10-12 | 0.165 | 0.165 | 0.165 | 0.0861 | 0.0 | 0.1311 | 0.1089 | 0.4867 | 0.4589 | 2.488 |
| Denmark Superliga | new_format | 1758 | 2019-07-12 | 2026-10-12 | 0.4181 | 0.4181 | 0.4181 | 0.0586 | 0.0 | 0.2361 | 0.1177 | 0.5876 | 0.558 | 2.891 |
| Finland Veikkausliiga | new_format | 1605 | 2019-04-03 | 2026-10-12 | 0.21 | 0.2093 | 0.21 | 0.0629 | 0.0 | 0.1695 | 0.1227 | 0.5358 | 0.5352 | 2.774 |
| K-League 1 | new_format | 1472 | 2020-05-08 | 2026-08-30 | 0.7412 | 0.7412 | 0.7412 | 0.2704 | 0.0 | 0.1087 | 0.0 | 0.534 | 0.4694 | 2.54 |
| Serie B | standard | 1270 | 2023-08-18 | 2026-10-11 | 1.0 | 1.0 | 0.9449 | 0.9449 | 0.0 | 0.3008 | 0.9449 | 0.548 | 0.4819 | 2.528 |
| Greek Super League | standard | 1202 | 2023-08-18 | 2026-10-12 | 0.9992 | 0.9992 | 0.624 | 0.624 | 0.0 | 0.2388 | 0.6248 | 0.4983 | 0.5133 | 2.657 |
| Turkish Super Lig | standard | 1091 | 2023-08-11 | 2026-10-12 | 0.9982 | 0.9982 | 0.9982 | 0.9982 | 0.0 | 0.4189 | 1.0 | 0.5472 | 0.5344 | 2.808 |
| Ligue 2 | standard | 1062 | 2023-08-05 | 2026-10-12 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.161 | 1.0 | 0.5 | 0.4727 | 2.525 |
| Belgian First Division A | standard | 1007 | 2023-07-28 | 2026-10-11 | 0.999 | 0.999 | 0.999 | 0.999 | 0.0 | 0.3088 | 1.0 | 0.5333 | 0.5263 | 2.77 |
| Dutch Eredivisie | standard | 990 | 2023-08-11 | 2026-10-11 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1333 | 1.0 | 0.5909 | 0.6111 | 3.179 |
| Portuguese Primeira Liga | standard | 989 | 2023-08-11 | 2026-10-12 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5662 | 1.0 | 0.5015 | 0.5288 | 2.709 |
| Scottish Premiership | standard | 732 | 2023-08-05 | 2026-10-11 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.2678 | 1.0 | 0.5178 | 0.5546 | 2.816 |
| Scottish Championship | standard | 588 | 2023-08-04 | 2026-10-13 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1718 | 1.0 | 0.4796 | 0.4813 | 2.539 |
