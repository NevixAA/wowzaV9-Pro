# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **128**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 2 | 0 | 0% | 17% | -2.00u | -100% | +0.0% (2) | COLLECTING (2/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 26 | 4 | 15% | 24% | -9.92u | -38% [-100%, +73%] | +8.2% (25) | COLLECTING (26/150) |
| ATT_MID | 1+ shot on target | 11 | 4 | 36% | 45% | +0.11u | +1% [-79%, +388%] | +0.0% (11) | COLLECTING (11/150) |
| ATT_MID | Assist | 3 | 0 | 0% | 28% | -3.00u | -100% | +0.0% (3) | COLLECTING (3/150) |
| CONTROL | Anytime scorer | 64 | 24 | 38% | 33% | +27.63u | +43% [+14%, +75%] | +0.0% (57) | COLLECTING (64/150) |
| CONTROL | 1+ shot on target | 21 | 15 | 71% | 51% | +16.98u | +81% [-51%, +145%] | +0.0% (18) | COLLECTING (21/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
