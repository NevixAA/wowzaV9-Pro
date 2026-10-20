# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **27**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 5 | 1 | 20% | 20% | +0.00u | +0% | +3.9% (5) | COLLECTING (5/150) |
| ATT_MID | 1+ shot on target | 2 | 1 | 50% | 35% | +4.50u | +225% | +0.0% (2) | COLLECTING (2/150) |
| ATT_MID | Assist | 0 | | | | | | | COLLECTING (0/150) |
| CONTROL | Anytime scorer | 15 | 6 | 40% | 33% | +4.22u | +28% [-6%, +50%] | +0.0% (14) | COLLECTING (15/150) |
| CONTROL | 1+ shot on target | 5 | 2 | 40% | 54% | -1.82u | -36% [-100%, -13%] | +0.0% (5) | COLLECTING (5/150) |
| CONTROL | Assist | 0 | | | | | | | COLLECTING (0/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
