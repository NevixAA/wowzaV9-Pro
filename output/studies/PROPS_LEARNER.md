# Props learner study — classic GradientBoosting vs HistGradientBoosting

Generated 2026-10-22 12:36 UTC. Rule (fixed in advance): PASS when the 95% block-bootstrap CI upper end of (challenger - incumbent) log loss is <= 1% of the incumbent's log loss; switch only if every market passes.

**SWITCH CANDIDATE — every market non-inferior; needs owner approval**

| Market | Test rows | Log loss now | Log loss fast | Diff (95% CI) | AUC now / fast | Fit time now / fast | Verdict |
|---|---:|---:|---:|---|---|---|---|
| goals | 173,258 | 0.26117 | 0.26046 | -0.00071 [-0.00092, -0.00050] | 0.7409 / 0.7423 | 49.8 / 0.7 min (x70.3) | PASS |
| goals2 | 173,258 | 0.04273 | 0.04253 | -0.00020 [-0.00034, -0.00005] | 0.8382 / 0.8401 | 50.8 / 0.7 min (x76.0) | PASS |
| assists | 173,258 | 0.21864 | 0.21836 | -0.00028 [-0.00048, -0.00009] | 0.6805 / 0.6814 | 52.8 / 0.7 min (x75.2) | PASS |
| sot | 173,258 | 0.47509 | 0.47510 | +0.00002 [-0.00024, +0.00028] | 0.7352 / 0.7348 | 51.5 / 0.7 min (x73.8) | PASS |
| sot2 | 173,258 | 0.18329 | 0.18246 | -0.00083 [-0.00107, -0.00060] | 0.8012 / 0.8023 | 48.5 / 0.7 min (x68.3) | PASS |
| sot3 | 173,258 | 0.06068 | 0.05967 | -0.00101 [-0.00125, -0.00078] | 0.8467 / 0.8524 | 50.2 / 0.7 min (x73.6) | PASS |
| sot4 | 172,177 | 0.01829 | 0.01829 | -0.00000 [-0.00000, +0.00000] | 0.8867 / 0.8887 | 42.3 / 0.6 min (x70.4) | PASS |
| cards | 173,258 | 0.37261 | 0.37249 | -0.00012 [-0.00023, -0.00002] | 0.6203 / 0.6202 | 54.8 / 0.7 min (x78.2) | PASS |

Negative diff = the fast learner is better. Recommendation only; v9 changes need the owner's approval.
