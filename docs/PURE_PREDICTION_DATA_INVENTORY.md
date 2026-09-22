# PURE PREDICTION — DATA INVENTORY

What exists, over what period, and how complete it is. This document is written before 
any model is fitted, because it decides which questions the warehouse can be asked at 
all. A feature present on 2% of rows is not a weak feature — it is an absent one, and 
an experiment that 'tests' it is really testing the 2% of fixtures that happen to have it.

**Fixtures usable for the match lab: 58,155** across 30 leagues.

## Sources

| source | repo | path | granularity | rows | span | used for |
|---|---|---|---|---|---|---|
| football-data.co.uk history | wowza-betting (v9) | `output/fd_history.parquet` | fixture | 58,155 | 2019-02 → 2026-09 | targets, shots, SOT, corners, fouls, HT goals, odds |
| API-Football history | wowza-betting (v9) | `output/af_history.parquet` | fixture | 28,504 | 2019-02 → 2026-09 | cards; nominally xG and inside-box |
| player match log | wowza-betting (v9) | `player_history.parquet` | player-match | 302,456 | 2022-08 → 2026-08 | goalscorer research |
| Pro season store | wowzaV9-Pro | `data/season_2026_27/**` | many | 5 weeks | 2026-08 → | too short for this lab; not used |

## The two findings that changed what could be asked

**1. xG is effectively absent.** The `HXG`/`AXG` columns exist in `af_history.parquet` and 
are populated on between 0.0% and 2.0% of rows in every single league. Inside-box shots 
are the same. So the question 'does xG materially help?' has no answer available from 
this warehouse — not a negative answer, *no* answer. Anything reported about xG would be 
a statement about the handful of fixtures that happen to carry it.

**2. Coverage is split by league in a way that tracks the source file, not the league.** 
The English, Spanish, Italian and German second divisions carry shots and shots on target 
on 100% of rows but corners, half-time goals and O/U prices on about 5%. Ligue 2, 
Belgium, the Netherlands, Portugal, Scotland and Turkey carry all of them on 100%. That 
is a collection-side asymmetry worth fixing — football-data.co.uk publishes `HC`/`AC` and 
`HTHG`/`HTAG` for the English files — but until it is, any corner or half-time feature is 
structurally missing for the leagues we most care about, and this lab treats it as NaN 
rather than imputing a number that would claim no corners were taken.

**Columns present but unusable:** xG (best league coverage 1.5%); shots inside the box (best league coverage 1.7%).

## Leakage verification

The features were rebuilt after randomising every result from a cutoff date onward. 
Every feature value on every earlier fixture had to be bit-identical. It was, at all 
four cutoffs:

| cutoff_q | cutoff_date | past_rows | future_rows | cells_changed | columns_leaking |
|---|---|---|---|---|---|
| 0.05 | 2019-12-01 | 2876 | 55279 | 0 | 0 |
| 0.25 | 2022-07-30 | 14515 | 43640 | 0 | 0 |
| 0.55 | 2024-05-19 | 31917 | 26238 | 0 | 0 |
| 0.85 | 2025-12-13 | 49416 | 8739 | 0 | 0 |


Single-feature AUC was also checked as a tripwire: of 600 feature-target 
pairs, 0 exceeded 0.80. The strongest single column 
anywhere reaches AUC 0.6481, which is what a real football feature looks 
like. A leaked outcome would sit near 1.0.

## Per-league coverage

| league | model_type | rows | first | last | cov_shots | cov_sot | cov_corners | cov_ht_goals | cov_cards | cov_xg | cov_odds_ou25 | rate_btts | rate_over25 | avg_goals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USA MLS | new_format | 4668 | 2019-03-02 | 2026-09-21 | 0.4707 | 0.4707 | 0.4704 | 0.0825 | 0.6382 | 0.0109 | 0.0593 | 0.5973 | 0.585 | 2.985 |
| Argentina Primera Division | new_format | 4444 | 2019-07-27 | 2026-09-22 | 0.3938 | 0.3938 | 0.3936 | 0.0617 | 0.5729 | 0.007 | 0.0812 | 0.4408 | 0.3724 | 2.177 |
| Brazil Serie A | new_format | 3813 | 2019-04-27 | 2026-09-20 | 0.5285 | 0.5285 | 0.5274 | 0.0692 | 0.6541 | 0.005 | 0.1065 | 0.5046 | 0.4511 | 2.447 |
| Mexico Liga MX | new_format | 3293 | 2019-07-20 | 2026-09-21 | 0.4595 | 0.4595 | 0.4592 | 0.0544 | 0.5973 | 0.0043 | 0.0574 | 0.5533 | 0.5162 | 2.714 |
| Japan J-League | new_format | 3119 | 2019-02-22 | 2026-09-20 | 0.5329 | 0.5329 | 0.5329 | 0.0683 | 0.6008 | 0.0 | 0.0446 | 0.5079 | 0.4787 | 2.598 |
| Sweden Allsvenskan | new_format | 2957 | 2019-03-31 | 2026-09-20 | 0.6141 | 0.6141 | 0.6141 | 0.1153 | 0.6121 | 0.003 | 0.0751 | 0.5262 | 0.5313 | 2.799 |
| China Super League | new_format | 2729 | 2019-03-01 | 2026-09-18 | 0.5416 | 0.5416 | 0.5412 | 0.0839 | 0.5464 | 0.0037 | 0.0879 | 0.5625 | 0.5665 | 2.944 |
| Norway Eliteserien | new_format | 2273 | 2019-03-30 | 2026-09-20 | 0.5007 | 0.5002 | 0.5002 | 0.0607 | 0.7695 | 0.0013 | 0.1157 | 0.5825 | 0.6027 | 3.076 |
| Romanian Superliga | new_format | 2232 | 2019-07-12 | 2026-09-04 | 0.9373 | 0.9337 | 0.9373 | 0.2469 | 0.9306 | 0.0049 | 0.0 | 0.4843 | 0.4328 | 2.425 |
| Austrian Bundesliga | new_format | 2148 | 2019-07-26 | 2026-09-20 | 0.5293 | 0.5293 | 0.5293 | 0.1061 | 0.5507 | 0.0047 | 0.0894 | 0.5521 | 0.5456 | 2.863 |
| Saudi Pro League | new_format | 1920 | 2019-08-22 | 2026-09-04 | 0.988 | 0.988 | 0.987 | 0.2589 | 0.9719 | 0.0146 | 0.0 | 0.562 | 0.5573 | 2.903 |
| Ireland Premier Division | new_format | 1795 | 2019-02-15 | 2026-09-19 | 0.1655 | 0.1655 | 0.1655 | 0.0864 | 0.3097 | 0.005 | 0.1075 | 0.4852 | 0.4579 | 2.485 |
| League One | standard | 1778 | 2023-08-05 | 2026-09-19 | 1.0 | 1.0 | 0.0467 | 0.0467 | 0.0 | 0.0 | 0.0467 | 0.5242 | 0.5079 | 2.626 |
| League Two | standard | 1772 | 2023-08-05 | 2026-09-19 | 1.0 | 1.0 | 0.0474 | 0.0474 | 0.0 | 0.0 | 0.0474 | 0.5322 | 0.4972 | 2.676 |
| Championship | standard | 1770 | 2023-08-04 | 2026-09-20 | 1.0 | 1.0 | 0.0537 | 0.0537 | 0.0 | 0.0 | 0.0537 | 0.5373 | 0.4989 | 2.591 |
| National League | standard | 1764 | 2023-08-05 | 2026-09-19 | 0.0612 | 0.0612 | 0.0612 | 1.0 | 0.0 | 0.0 | 1.0 | 0.5709 | 0.5454 | 2.862 |
| Denmark Superliga | new_format | 1752 | 2019-07-12 | 2026-09-20 | 0.4195 | 0.4195 | 0.4195 | 0.0588 | 0.6689 | 0.0 | 0.1182 | 0.5879 | 0.5576 | 2.889 |
| Finland Veikkausliiga | new_format | 1596 | 2019-04-03 | 2026-09-19 | 0.2112 | 0.2105 | 0.2112 | 0.0633 | 0.3515 | 0.0 | 0.1216 | 0.5376 | 0.537 | 2.778 |
| La Liga 2 | standard | 1485 | 2023-08-11 | 2026-09-20 | 1.0 | 1.0 | 0.0444 | 0.0444 | 0.0 | 0.0 | 0.0444 | 0.503 | 0.4519 | 2.465 |
| K-League 1 | new_format | 1472 | 2020-05-08 | 2026-08-30 | 0.7412 | 0.7412 | 0.7412 | 0.2704 | 0.7147 | 0.0 | 0.0 | 0.534 | 0.4694 | 2.54 |
| Serie B | standard | 1222 | 2023-08-18 | 2026-09-20 | 1.0 | 1.0 | 0.0409 | 0.0409 | 0.0 | 0.0 | 0.0409 | 0.5475 | 0.4787 | 2.515 |
| Turkish Super Lig | standard | 1082 | 2023-08-11 | 2026-09-20 | 0.9982 | 0.9982 | 0.9982 | 0.9982 | 0.0 | 0.0 | 1.0 | 0.549 | 0.5323 | 2.809 |
| Ligue 2 | standard | 1053 | 2023-08-05 | 2026-09-19 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 | 0.5005 | 0.4739 | 2.524 |
| Bundesliga 2 | standard | 1005 | 2023-07-28 | 2026-09-20 | 1.0 | 1.0 | 0.0537 | 0.0537 | 0.0 | 0.0 | 0.0537 | 0.596 | 0.597 | 3.046 |
| Belgian First Division A | standard | 998 | 2023-07-28 | 2026-09-20 | 0.999 | 0.999 | 0.999 | 0.999 | 0.0 | 0.0 | 1.0 | 0.5321 | 0.5251 | 2.762 |
| Dutch Eredivisie | standard | 981 | 2023-08-11 | 2026-09-20 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 | 0.5902 | 0.6126 | 3.178 |
| Portuguese Primeira Liga | standard | 980 | 2023-08-11 | 2026-09-20 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 | 0.501 | 0.5286 | 2.708 |
| Greek Super League | standard | 753 | 2023-08-18 | 2026-09-20 | 1.0 | 1.0 | 0.0465 | 0.0465 | 0.0 | 0.0 | 0.0465 | 0.502 | 0.5153 | 2.657 |
| Scottish Premiership | standard | 726 | 2023-08-05 | 2026-09-20 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 | 0.5193 | 0.5551 | 2.817 |
| Scottish Championship | standard | 575 | 2023-08-04 | 2026-09-19 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 | 0.4783 | 0.48 | 2.541 |
