# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **242**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 3 | 0 | 0% | 17% | -3.00u | -100% [-100%, -100%] | +0.0% (3) | COLLECTING (3/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 40 | 7 | 18% | 24% | -12.92u | -32% [-87%, +59%] | +0.0% (39) | COLLECTING (40/150) |
| ATT_MID | 1+ shot on target | 19 | 5 | 26% | 45% | -6.09u | -32% [-100%, +95%] | +0.0% (19) | COLLECTING (19/150) |
| ATT_MID | Assist | 4 | 0 | 0% | 25% | -4.00u | -100% | +0.0% (4) | COLLECTING (4/150) |
| CONTROL | Anytime scorer | 139 | 43 | 31% | 31% | +16.26u | +12% [-19%, +40%] | +0.0% (126) | COLLECTING (139/150) |
| CONTROL | 1+ shot on target | 36 | 23 | 64% | 53% | +16.69u | +46% [-28%, +105%] | +0.0% (28) | COLLECTING (36/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
