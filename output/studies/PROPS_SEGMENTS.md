# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **232**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 2 | 0 | 0% | 17% | -2.00u | -100% | +0.0% (2) | COLLECTING (2/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 39 | 7 | 18% | 25% | -11.92u | -31% [-86%, +64%] | +0.0% (38) | COLLECTING (39/150) |
| ATT_MID | 1+ shot on target | 17 | 5 | 29% | 47% | -4.09u | -24% [-100%, +128%] | +0.0% (17) | COLLECTING (17/150) |
| ATT_MID | Assist | 4 | 0 | 0% | 25% | -4.00u | -100% | +0.0% (4) | COLLECTING (4/150) |
| CONTROL | Anytime scorer | 134 | 41 | 31% | 31% | +15.31u | +11% [-19%, +42%] | +0.0% (121) | COLLECTING (134/150) |
| CONTROL | 1+ shot on target | 35 | 23 | 66% | 53% | +17.69u | +51% [-22%, +113%] | +0.0% (27) | COLLECTING (35/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
