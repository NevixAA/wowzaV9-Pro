# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **80**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 2 | 0 | 0% | 17% | -2.00u | -100% | +0.0% (2) | COLLECTING (2/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 17 | 2 | 12% | 23% | -9.00u | -53% [-100%, +88%] | +8.2% (17) | COLLECTING (17/150) |
| ATT_MID | 1+ shot on target | 6 | 3 | 50% | 48% | +3.46u | +58% [-100%, +550%] | +2.1% (6) | COLLECTING (6/150) |
| ATT_MID | Assist | 0 | | | | | | | COLLECTING (0/150) |
| CONTROL | Anytime scorer | 43 | 16 | 37% | 33% | +11.83u | +28% [+9%, +70%] | +1.7% (38) | COLLECTING (43/150) |
| CONTROL | 1+ shot on target | 11 | 6 | 55% | 48% | +5.89u | +54% [-100%, +142%] | +0.0% (9) | COLLECTING (11/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
