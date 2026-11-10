# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **317**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 3 | 0 | 0% | 17% | -3.00u | -100% [-100%, -100%] | +0.0% (3) | COLLECTING (3/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 57 | 10 | 18% | 25% | -19.30u | -34% [-76%, +25%] | +0.0% (55) | COLLECTING (57/150) |
| ATT_MID | 1+ shot on target | 23 | 6 | 26% | 46% | -8.42u | -37% [-91%, +62%] | +0.0% (23) | COLLECTING (23/150) |
| ATT_MID | Assist | 4 | 0 | 0% | 25% | -4.00u | -100% | +0.0% (4) | COLLECTING (4/150) |
| CONTROL | Anytime scorer | 188 | 60 | 32% | 31% | +29.86u | +16% [-12%, +41%] | +0.0% (171) | COLLECTING (188/150) |
| CONTROL | 1+ shot on target | 41 | 25 | 61% | 53% | +15.07u | +37% [-30%, +94%] | +0.0% (33) | COLLECTING (41/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
