# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **122**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 2 | 0 | 0% | 17% | -2.00u | -100% | +0.0% (2) | COLLECTING (2/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 22 | 2 | 9% | 23% | -14.00u | -64% [-100%, +39%] | +4.9% (22) | COLLECTING (22/150) |
| ATT_MID | 1+ shot on target | 11 | 4 | 36% | 45% | +0.11u | +1% [-79%, +388%] | +0.0% (11) | COLLECTING (11/150) |
| ATT_MID | Assist | 3 | 0 | 0% | 28% | -3.00u | -100% | +0.0% (3) | COLLECTING (3/150) |
| CONTROL | Anytime scorer | 64 | 24 | 38% | 33% | +27.63u | +43% [+14%, +74%] | +0.0% (57) | COLLECTING (64/150) |
| CONTROL | 1+ shot on target | 19 | 13 | 68% | 52% | +13.48u | +71% [-64%, +128%] | +0.0% (17) | COLLECTING (19/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
