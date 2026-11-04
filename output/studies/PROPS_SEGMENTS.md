# Props segments — pre-registered forward test

Registered 2026-10-13; counts tips made from 2026-10-14. Rules frozen in src/studies/props_segments.py. EDGE needs n >= 150, a positive ROI lower bound (one-sided, Bonferroni over 6 cells) AND a positive median CLV.

Qualifying tips so far: **251**

| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| ATT_DEF | Anytime scorer | 0 | | | | | | | COLLECTING (0/150) |
| ATT_DEF | 1+ shot on target | 3 | 0 | 0% | 17% | -3.00u | -100% [-100%, -100%] | +0.0% (3) | COLLECTING (3/150) |
| ATT_DEF | Assist | 0 | | | | | | | COLLECTING (0/150) |
| ATT_MID | Anytime scorer | 41 | 7 | 17% | 24% | -13.92u | -34% [-89%, +51%] | +0.0% (40) | COLLECTING (41/150) |
| ATT_MID | 1+ shot on target | 21 | 6 | 29% | 46% | -6.42u | -31% [-88%, +83%] | +0.0% (21) | COLLECTING (21/150) |
| ATT_MID | Assist | 4 | 0 | 0% | 25% | -4.00u | -100% | +0.0% (4) | COLLECTING (4/150) |
| CONTROL | Anytime scorer | 142 | 44 | 31% | 31% | +14.93u | +11% [-20%, +39%] | +0.0% (129) | COLLECTING (142/150) |
| CONTROL | 1+ shot on target | 39 | 24 | 62% | 52% | +15.52u | +40% [-31%, +96%] | +0.0% (31) | COLLECTING (39/150) |
| CONTROL | Assist | 1 | 0 | 0% | 43% | -1.00u | -100% |  | COLLECTING (1/150) |

CONTROL = every other priced prop where the model beats the price. A segment only matters if it beats its control AND the market's closing price. Paper only.
