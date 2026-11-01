# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **209**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 2 | 0 | 0% | 17% | -2.00u | -100% | +0.0% (2) | COLLECTING (2/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 37 | 7 | 19% | 25% | -9.92u | -27% [-85%, +79%] | +2.0% (36) | COLLECTING (37/150) |
| ATT_MID | 1+ shot on target | 15 | 5 | 33% | 47% | -2.09u | -14% [-100%, +179%] | +0.0% (15) | COLLECTING (15/150) |
| ATT_MID | Assist | 4 | 0 | 0% | 25% | -4.00u | -100% | +0.0% (4) | COLLECTING (4/150) |
| CONTROL | Anytime scorer | 117 | 38 | 32% | 32% | +21.01u | +18% [-20%, +49%] | +0.0% (105) | COLLECTING (117/150) |
| CONTROL | 1+ shot on target | 33 | 22 | 67% | 54% | +17.86u | +54% [-19%, +115%] | +0.0% (26) | COLLECTING (33/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
