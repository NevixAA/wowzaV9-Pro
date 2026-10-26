# PURE PREDICTION — DATA INVENTORY

What exists, over what period, and how complete it is. This document is written before 
any model is fitted, because it decides which questions the warehouse can be asked at 
all. A feature present on 2% of rows is not a weak feature — it is an absent one, and 
an experiment that 'tests' it is really testing the 2% of fixtures that happen to have it.

**Fixtures usable for the match lab: 63,007** across 30 leagues.

## Sources

| source | repo | path | granularity | rows | span | used for |
|---|---|---|---|---|---|---|
| football-data.co.uk history | wowza-betting (v9) | `output/fd_history.parquet` | fixture | 63,007 | 2019-02 → 2026-09 | targets, shots, SOT, corners, fouls, HT goals, odds |
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
| 0.05 | 2020-02-07 | 3150 | 59857 | 0 | 0 |
| 0.25 | 2022-09-10 | 15712 | 47295 | 0 | 0 |
| 0.55 | 2024-07-19 | 34642 | 28365 | 0 | 0 |
| 0.85 | 2026-01-16 | 53539 | 9468 | 0 | 0 |


Single-feature AUC was also checked as a tripwire: of 568 feature-target 
pairs, 0 exceeded 0.80. The strongest single column 
anywhere reaches AUC 0.6483, which is what a real football feature looks 
like. A leaked outcome would sit near 1.0.

## Per-league coverage

| league | model_type | rows | first | last | cov_shots | cov_sot | cov_corners | cov_ht_goals | cov_cards | cov_xg | cov_odds_ou25 | rate_btts | rate_over25 | avg_goals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USA MLS | new_format | 4732 | 2019-03-02 | 2026-10-22 | 0.4643 | 0.4643 | 0.4641 | 0.0814 | 0.0 | 0.2086 | 0.0596 | 0.5987 | 0.5866 | 2.992 |
| Argentina Primera Division | new_format | 4489 | 2019-07-27 | 2026-10-20 | 0.3898 | 0.3898 | 0.3896 | 0.061 | 0.0 | 0.1357 | 0.0826 | 0.442 | 0.3734 | 2.18 |
| Brazil Serie A | new_format | 3845 | 2019-04-27 | 2026-10-20 | 0.5241 | 0.5241 | 0.523 | 0.0687 | 0.0 | 0.2016 | 0.1074 | 0.5051 | 0.4512 | 2.448 |
| Mexico Liga MX | new_format | 3329 | 2019-07-20 | 2026-10-22 | 0.4545 | 0.4545 | 0.4542 | 0.0538 | 0.0 | 0.1123 | 0.0577 | 0.5545 | 0.5167 | 2.722 |
| Japan J-League | new_format | 3149 | 2019-02-22 | 2026-10-21 | 0.5278 | 0.5278 | 0.5278 | 0.0676 | 0.0 | 0.088 | 0.0441 | 0.5075 | 0.4802 | 2.601 |
| Sweden Allsvenskan | new_format | 2973 | 2019-03-31 | 2026-10-19 | 0.6108 | 0.6108 | 0.6108 | 0.1147 | 0.0 | 0.2028 | 0.0747 | 0.5254 | 0.5308 | 2.8 |
| China Super League | new_format | 2745 | 2019-03-01 | 2026-10-18 | 0.5384 | 0.5384 | 0.5381 | 0.0834 | 0.0 | 0.1319 | 0.0874 | 0.5621 | 0.5668 | 2.947 |
| League One | standard | 2558 | 2023-08-05 | 2026-10-21 | 1.0 | 1.0 | 0.6966 | 0.6966 | 0.0 | 0.2506 | 0.6966 | 0.5258 | 0.509 | 2.627 |
| League Two | standard | 2524 | 2023-08-05 | 2026-10-20 | 1.0 | 1.0 | 0.7108 | 0.7108 | 0.0 | 0.2678 | 0.7108 | 0.5357 | 0.4988 | 2.678 |
| Championship | standard | 2361 | 2023-08-04 | 2026-10-20 | 1.0 | 1.0 | 0.7573 | 0.7573 | 0.0 | 0.341 | 0.7573 | 0.5294 | 0.4909 | 2.572 |
| La Liga 2 | standard | 2313 | 2023-08-11 | 2026-10-19 | 1.0 | 1.0 | 0.6468 | 0.6468 | 0.0 | 0.2352 | 0.6468 | 0.5123 | 0.4596 | 2.508 |
| Norway Eliteserien | new_format | 2289 | 2019-03-30 | 2026-10-18 | 0.4972 | 0.4967 | 0.4967 | 0.0603 | 0.0 | 0.2145 | 0.1166 | 0.5837 | 0.6029 | 3.08 |
| Romanian Superliga | new_format | 2232 | 2019-07-12 | 2026-09-04 | 0.9373 | 0.9337 | 0.9373 | 0.2469 | 0.0 | 0.1622 | 0.0 | 0.4843 | 0.4328 | 2.425 |
| Austrian Bundesliga | new_format | 2160 | 2019-07-26 | 2026-10-18 | 0.5264 | 0.5264 | 0.5264 | 0.1056 | 0.0 | 0.088 | 0.0898 | 0.5514 | 0.5463 | 2.867 |
| Bundesliga 2 | standard | 1935 | 2023-07-28 | 2026-10-18 | 1.0 | 1.0 | 0.5116 | 0.5116 | 0.0 | 0.2212 | 0.5116 | 0.5948 | 0.5943 | 3.028 |
| Saudi Pro League | new_format | 1920 | 2019-08-22 | 2026-09-04 | 0.988 | 0.988 | 0.987 | 0.2589 | 0.0 | 0.1625 | 0.0 | 0.562 | 0.5573 | 2.903 |
| National League | standard | 1811 | 2023-08-05 | 2026-10-10 | 0.0856 | 0.0856 | 0.0856 | 1.0 | 0.0 | 0.1872 | 1.0 | 0.5704 | 0.5472 | 2.874 |
| Ireland Premier Division | new_format | 1807 | 2019-02-15 | 2026-10-19 | 0.1644 | 0.1644 | 0.1644 | 0.0858 | 0.0 | 0.1251 | 0.109 | 0.487 | 0.4588 | 2.488 |
| Denmark Superliga | new_format | 1764 | 2019-07-12 | 2026-10-19 | 0.4167 | 0.4167 | 0.4167 | 0.0584 | 0.0 | 0.1729 | 0.1173 | 0.5879 | 0.5584 | 2.891 |
| Finland Veikkausliiga | new_format | 1612 | 2019-04-03 | 2026-10-21 | 0.2091 | 0.2084 | 0.2091 | 0.0627 | 0.0 | 0.1669 | 0.1234 | 0.536 | 0.5347 | 2.775 |
| K-League 1 | new_format | 1472 | 2020-05-08 | 2026-08-30 | 0.7412 | 0.7412 | 0.7412 | 0.2704 | 0.0 | 0.1162 | 0.0 | 0.534 | 0.4694 | 2.54 |
| Serie B | standard | 1280 | 2023-08-18 | 2026-10-18 | 1.0 | 1.0 | 0.9453 | 0.9453 | 0.0 | 0.3102 | 0.9453 | 0.55 | 0.4836 | 2.532 |
| Greek Super League | standard | 1208 | 2023-08-18 | 2026-10-18 | 0.9992 | 0.9992 | 0.6258 | 0.6258 | 0.0 | 0.2351 | 0.6267 | 0.4992 | 0.5141 | 2.661 |
| Turkish Super Lig | standard | 1100 | 2023-08-11 | 2026-10-19 | 0.9982 | 0.9982 | 0.9982 | 0.9982 | 0.0 | 0.4045 | 1.0 | 0.5464 | 0.5345 | 2.805 |
| Ligue 2 | standard | 1071 | 2023-08-05 | 2026-10-19 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1877 | 1.0 | 0.5014 | 0.4753 | 2.536 |
| Belgian First Division A | standard | 1007 | 2023-07-28 | 2026-10-11 | 0.999 | 0.999 | 0.999 | 0.999 | 0.0 | 0.3237 | 1.0 | 0.5333 | 0.5263 | 2.77 |
| Dutch Eredivisie | standard | 999 | 2023-08-11 | 2026-10-18 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1441 | 1.0 | 0.5936 | 0.6146 | 3.192 |
| Portuguese Primeira Liga | standard | 990 | 2023-08-11 | 2026-10-19 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5697 | 1.0 | 0.502 | 0.5293 | 2.709 |
| Scottish Premiership | standard | 738 | 2023-08-05 | 2026-10-18 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.2764 | 1.0 | 0.5217 | 0.5569 | 2.828 |
| Scottish Championship | standard | 594 | 2023-08-04 | 2026-10-20 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1869 | 1.0 | 0.4781 | 0.4764 | 2.529 |
