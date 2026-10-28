# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **134**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 2 | 0 | 0% | 17% | -2.00u | -100% | +0.0% (2) | COLLECTING (2/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 28 | 4 | 14% | 25% | -11.92u | -43% [-100%, +63%] | +8.2% (27) | COLLECTING (28/150) |
| ATT_MID | 1+ shot on target | 12 | 4 | 33% | 46% | -0.89u | -7% [-100%, +290%] | +0.0% (12) | COLLECTING (12/150) |
| ATT_MID | Assist | 3 | 0 | 0% | 28% | -3.00u | -100% | +0.0% (3) | COLLECTING (3/150) |
| CONTROL | Anytime scorer | 66 | 24 | 36% | 33% | +25.63u | +39% [-1%, +69%] | +0.0% (59) | COLLECTING (66/150) |
| CONTROL | 1+ shot on target | 22 | 16 | 73% | 52% | +17.78u | +81% [-39%, +140%] | +0.0% (19) | COLLECTING (22/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
