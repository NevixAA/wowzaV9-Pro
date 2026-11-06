# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **262**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 3 | 0 | 0% | 17% | -3.00u | -100% [-100%, -100%] | +0.0% (3) | COLLECTING (3/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 42 | 7 | 17% | 25% | -14.92u | -36% [-90%, +50%] | +0.0% (41) | COLLECTING (42/150) |
| ATT_MID | 1+ shot on target | 21 | 6 | 29% | 46% | -6.42u | -31% [-88%, +91%] | +0.0% (21) | COLLECTING (21/150) |
| ATT_MID | Assist | 4 | 0 | 0% | 25% | -4.00u | -100% | +0.0% (4) | COLLECTING (4/150) |
| CONTROL | Anytime scorer | 151 | 45 | 30% | 32% | +12.43u | +8% [-22%, +37%] | +0.0% (138) | COLLECTING (151/150) |
| CONTROL | 1+ shot on target | 40 | 24 | 60% | 52% | +14.52u | +36% [-32%, +96%] | +0.0% (32) | COLLECTING (40/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
