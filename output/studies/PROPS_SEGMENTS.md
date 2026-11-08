# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **286**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 3 | 0 | 0% | 17% | -3.00u | -100% [-100%, -100%] | +0.0% (3) | COLLECTING (3/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 48 | 8 | 17% | 25% | -16.92u | -35% [-83%, +34%] | +0.0% (47) | COLLECTING (48/150) |
| ATT_MID | 1+ shot on target | 23 | 6 | 26% | 46% | -8.42u | -37% [-92%, +58%] | +0.0% (23) | COLLECTING (23/150) |
| ATT_MID | Assist | 4 | 0 | 0% | 25% | -4.00u | -100% | +0.0% (4) | COLLECTING (4/150) |
| CONTROL | Anytime scorer | 166 | 51 | 31% | 31% | +22.67u | +14% [-17%, +42%] | +0.0% (151) | COLLECTING (166/150) |
| CONTROL | 1+ shot on target | 41 | 25 | 61% | 53% | +15.07u | +37% [-29%, +93%] | +0.0% (33) | COLLECTING (41/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
