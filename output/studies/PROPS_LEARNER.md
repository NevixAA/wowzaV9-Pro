# Props learner study — classic GradientBoosting vs HistGradientBoosting

Generated 2026-10-12 12:35 UTC. Rule (fixed in advance): PASS when the 95% block-bootstrap CI upper end of (challenger - incumbent) log loss is <= 1% of the incumbent's log loss; switch only if every market passes.

**DO NOT SWITCH — markets missing: sot4**

| Market | Test rows | Log loss now | Log loss fast | Diff (95% CI) | AUC now / fast | Fit time now / fast | Verdict |
|---|---:|---:|---:|---|---|---|---|
| goals | 171,346 | 0.25933 | 0.25862 | -0.00072 [-0.00089, -0.00053] | 0.7429 / 0.7442 | 33.0 / 0.5 min (x70.4) | PASS |
| goals2 | 171,346 | 0.04267 | 0.04232 | -0.00035 [-0.00052, -0.00016] | 0.8387 / 0.8412 | 53.8 / 0.7 min (x73.6) | PASS |
| assists | 171,346 | 0.21706 | 0.21706 | +0.00001 [-0.00020, +0.00022] | 0.6808 / 0.6812 | 45.4 / 0.6 min (x76.0) | PASS |
| sot | 171,346 | 0.47330 | 0.47304 | -0.00025 [-0.00042, -0.00009] | 0.7366 / 0.7369 | 41.8 / 0.6 min (x67.6) | PASS |
| sot2 | 171,346 | 0.18201 | 0.18100 | -0.00101 [-0.00126, -0.00078] | 0.8029 / 0.8039 | 44.9 / 0.6 min (x71.5) | PASS |
| sot3 | 171,346 | 0.06003 | 0.05937 | -0.00066 [-0.00086, -0.00047] | 0.8478 / 0.8518 | 46.0 / 0.7 min (x69.2) | PASS |
| cards | 171,346 | 0.37337 | 0.37336 | -0.00001 [-0.00012, +0.00010] | 0.6225 / 0.6217 | 40.8 / 0.6 min (x65.4) | PASS |

Negative diff = the fast learner is better. Recommendation only; v9 changes need the owner's approval.
