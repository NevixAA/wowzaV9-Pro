# PURE PREDICTION — DATA INVENTORY

What exists, over what period, and how complete it is. This document is written before 
any model is fitted, because it decides which questions the warehouse can be asked at 
all. A feature present on 2% of rows is not a weak feature — it is an absent one, and 
an experiment that 'tests' it is really testing the 2% of fixtures that happen to have it.

**Fixtures usable for the match lab: 54,316** across 32 leagues.

## Sources

| source | repo | path | granularity | rows | span | used for |
|---|---|---|---|---|---|---|
| football-data.co.uk history | wowza-betting (v9) | `output/fd_history.parquet` | fixture | 54,316 | 2019-02 → 2026-09 | targets, shots, SOT, corners, fouls, HT goals, odds |
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
| 0.05 | 2019-11-10 | 2701 | 51615 | 0 | 0 |
| 0.25 | 2022-08-06 | 13538 | 40778 | 0 | 0 |
| 0.55 | 2024-08-10 | 29802 | 24514 | 0 | 0 |
| 0.85 | 2026-02-03 | 46158 | 8158 | 0 | 0 |


Single-feature AUC was also checked as a tripwire: of 568 feature-target 
pairs, 0 exceeded 0.80. The strongest single column 
anywhere reaches AUC 0.6737, which is what a real football feature looks 
like. A leaked outcome would sit near 1.0.

## Per-league coverage

| league | model_type | rows | first | last | cov_shots | cov_sot | cov_corners | cov_ht_goals | cov_cards | cov_xg | cov_odds_ou25 | rate_btts | rate_over25 | avg_goals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USA MLS | new_format | 4356 | 2019-03-02 | 2026-11-02 | 0.5041 | 0.5041 | 0.5039 | 0.0884 | 0.0023 | 0.2163 | 0.081 | 0.6024 | 0.5923 | 3.005 |
| Argentina Primera Division | new_format | 3795 | 2019-07-27 | 2026-11-05 | 0.4611 | 0.4611 | 0.4609 | 0.0722 | 0.004 | 0.1344 | 0.0964 | 0.4453 | 0.3773 | 2.192 |
| Romanian Superliga | new_format | 3462 | 2019-07-12 | 2026-11-02 | 0.5725 | 0.5702 | 0.5722 | 0.1462 | 0.0003 | 0.0976 | 0.0168 | 0.4856 | 0.4356 | 2.447 |
| Brazil Serie A | new_format | 3163 | 2019-04-27 | 2026-11-06 | 0.6371 | 0.6371 | 0.6358 | 0.0835 | 0.0032 | 0.2163 | 0.1265 | 0.5021 | 0.4499 | 2.44 |
| Japan J-League | new_format | 2647 | 2019-02-22 | 2026-11-01 | 0.6279 | 0.6279 | 0.6279 | 0.0805 | 0.0019 | 0.0884 | 0.0597 | 0.5036 | 0.4828 | 2.601 |
| Mexico Liga MX | new_format | 2525 | 2019-07-20 | 2026-11-02 | 0.5988 | 0.5988 | 0.5984 | 0.0709 | 0.0024 | 0.135 | 0.1006 | 0.5556 | 0.5145 | 2.731 |
| Saudi Pro League | new_format | 1920 | 2019-08-22 | 2026-09-04 | 0.988 | 0.988 | 0.987 | 0.2589 | 0.0 | 0.1583 | 0.0 | 0.562 | 0.5573 | 2.903 |
| Sweden Allsvenskan | new_format | 1910 | 2019-03-31 | 2026-11-03 | 0.9508 | 0.9508 | 0.9508 | 0.1785 | 0.0016 | 0.1539 | 0.0372 | 0.5241 | 0.5283 | 2.779 |
| Norway Eliteserien | new_format | 1889 | 2019-03-30 | 2026-11-01 | 0.6024 | 0.6019 | 0.6019 | 0.0731 | 0.0037 | 0.2033 | 0.1191 | 0.5828 | 0.604 | 3.091 |
| National League | standard | 1845 | 2023-08-05 | 2026-10-31 | 0.1024 | 0.1024 | 0.1024 | 1.0 | 0.0 | 0.1718 | 1.0 | 0.5729 | 0.5512 | 2.885 |
| Championship | standard | 1837 | 2023-08-04 | 2026-11-04 | 1.0 | 1.0 | 0.9929 | 0.9929 | 0.0 | 0.3364 | 0.9929 | 0.5373 | 0.5019 | 2.606 |
| China Super League | new_format | 1837 | 2019-03-01 | 2026-10-24 | 0.8046 | 0.8046 | 0.804 | 0.1247 | 0.0 | 0.129 | 0.0735 | 0.5689 | 0.5683 | 2.952 |
| League Two | standard | 1833 | 2023-08-05 | 2026-11-03 | 1.0 | 1.0 | 0.9929 | 0.9929 | 0.0 | 0.2651 | 0.9929 | 0.5368 | 0.4965 | 2.68 |
| League One | standard | 1829 | 2023-08-05 | 2026-11-04 | 1.0 | 1.0 | 0.9923 | 0.9923 | 0.0 | 0.2559 | 0.9923 | 0.5205 | 0.503 | 2.613 |
| La Liga 2 | standard | 1534 | 2023-08-11 | 2026-11-02 | 1.0 | 1.0 | 0.9889 | 0.9889 | 0.0 | 0.2458 | 0.9889 | 0.5091 | 0.4557 | 2.489 |
| Denmark Superliga | new_format | 1477 | 2019-07-12 | 2026-11-02 | 0.4976 | 0.4976 | 0.4976 | 0.0697 | 0.0027 | 0.2085 | 0.172 | 0.5884 | 0.5606 | 2.883 |
| K-League 1 | new_format | 1472 | 2020-05-08 | 2026-08-30 | 0.7412 | 0.7412 | 0.7412 | 0.2704 | 0.0 | 0.1121 | 0.0 | 0.534 | 0.4694 | 2.54 |
| Austrian Bundesliga | new_format | 1430 | 2019-07-26 | 2026-11-01 | 0.7951 | 0.7951 | 0.7951 | 0.1594 | 0.0035 | 0.0979 | 0.1503 | 0.5524 | 0.5566 | 2.909 |
| Ireland Premier Division | new_format | 1357 | 2019-02-15 | 2026-10-30 | 0.2189 | 0.2189 | 0.2189 | 0.1127 | 0.0037 | 0.1135 | 0.0987 | 0.4878 | 0.4613 | 2.486 |
| Finland Veikkausliiga | new_format | 1325 | 2019-04-03 | 2026-11-02 | 0.2543 | 0.2536 | 0.2543 | 0.0626 | 0.0023 | 0.1434 | 0.1426 | 0.5313 | 0.5253 | 2.756 |
| Serie B | standard | 1268 | 2023-08-18 | 2026-11-01 | 1.0 | 1.0 | 0.9779 | 0.9779 | 0.0 | 0.3241 | 0.9779 | 0.5473 | 0.4771 | 2.518 |
| Turkish Super Lig | standard | 1118 | 2023-08-11 | 2026-11-02 | 0.9982 | 0.9982 | 0.9982 | 0.9982 | 0.0 | 0.2567 | 1.0 | 0.5465 | 0.5367 | 2.816 |
| Ligue 2 | standard | 1089 | 2023-08-05 | 2026-11-02 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1717 | 1.0 | 0.5023 | 0.4757 | 2.536 |
| Belgian First Division A | standard | 1026 | 2023-07-28 | 2026-11-04 | 0.999 | 0.999 | 0.999 | 0.999 | 0.0 | 0.3138 | 1.0 | 0.537 | 0.5322 | 2.793 |
| Dutch Eredivisie | standard | 1017 | 2023-08-11 | 2026-11-01 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5103 | 1.0 | 0.5929 | 0.6136 | 3.202 |
| Bundesliga 2 | standard | 1013 | 2023-07-28 | 2026-11-01 | 1.0 | 1.0 | 0.9951 | 0.9951 | 0.0 | 0.1856 | 0.9951 | 0.5923 | 0.5903 | 3.012 |
| Portuguese Primeira Liga | standard | 1008 | 2023-08-11 | 2026-11-02 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5764 | 1.0 | 0.498 | 0.5288 | 2.703 |
| Greek Super League | standard | 773 | 2023-08-18 | 2026-11-02 | 1.0 | 1.0 | 0.9961 | 0.9961 | 0.0 | 0.2251 | 0.9961 | 0.5006 | 0.5201 | 2.668 |
| Scottish Premiership | standard | 753 | 2023-08-05 | 2026-11-01 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.2922 | 1.0 | 0.5232 | 0.5591 | 2.833 |
| Scottish Championship | standard | 604 | 2023-08-04 | 2026-10-31 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.1871 | 1.0 | 0.4752 | 0.4785 | 2.538 |
| Scottish League One | standard | 604 | 2023-08-05 | 2026-10-31 | 0.9983 | 0.9983 | 0.9983 | 1.0 | 0.0 | 0.053 | 1.0 | 0.5381 | 0.548 | 2.834 |
| Scottish League Two | standard | 600 | 2023-08-05 | 2026-10-31 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0317 | 1.0 | 0.5367 | 0.5167 | 2.775 |
