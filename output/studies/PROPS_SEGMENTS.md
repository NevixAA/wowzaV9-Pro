# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **155**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 2 | 0 | 0% | 17% | -2.00u | -100% | +0.0% (2) | COLLECTING (2/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 31 | 4 | 13% | 25% | -14.92u | -48% [-100%, +37%] | +7.0% (30) | COLLECTING (31/150) |
| ATT_MID | 1+ shot on target | 12 | 4 | 33% | 46% | -0.89u | -7% [-100%, +290%] | +0.0% (12) | COLLECTING (12/150) |
| ATT_MID | Assist | 3 | 0 | 0% | 28% | -3.00u | -100% | +0.0% (3) | COLLECTING (3/150) |
| CONTROL | Anytime scorer | 80 | 28 | 35% | 32% | +24.53u | +31% [-9%, +61%] | +0.0% (71) | COLLECTING (80/150) |
| CONTROL | 1+ shot on target | 26 | 19 | 73% | 54% | +18.45u | +71% [-19%, +129%] | +0.0% (22) | COLLECTING (26/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
