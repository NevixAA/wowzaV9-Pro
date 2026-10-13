# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **0**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | 1+ shot on target | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Assist | 0 | | | | | | | COLLECTING (0/150) |
| CONTROL | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| CONTROL | 1+ shot on target | 0 | | | | | | | COLLECTING (0/150) |
| CONTROL | Assist | 0 | | | | | | | COLLECTING (0/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
