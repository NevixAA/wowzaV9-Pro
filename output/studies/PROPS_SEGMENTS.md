# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **34**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 6 | 1 | 17% | 22% | -1.00u | -17% [-100%, +150%] | +2.0% (6) | COLLECTING (6/150) |
| ATT_MID | 1+ shot on target | 2 | 1 | 50% | 35% | +4.50u | +225% | +0.0% (2) | COLLECTING (2/150) |
| ATT_MID | Assist | 0 | | | | | | | COLLECTING (0/150) |
| CONTROL | Anytime scorer | 19 | 8 | 42% | 34% | +4.49u | +24% [-3%, +39%] | +0.0% (17) | COLLECTING (19/150) |
| CONTROL | 1+ shot on target | 6 | 2 | 33% | 57% | -2.82u | -47% [-100%, -17%] | +0.0% (6) | COLLECTING (6/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
