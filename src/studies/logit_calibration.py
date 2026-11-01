"""Log-odds calibration challenger (owner 2026-11-01) - collect the CI benchmark into a verdict.

    python -m src.studies.logit_calibration <dir with v9 benchmark outputs>
        -> output/studies/logit_calibration/{verdict.csv, per_league.csv, summary.json}

The benchmark itself runs inside v9 (research/logit-calibration-2026-11,
scripts/logit_calibration_benchmark.py): champion = calibration_space "prob" (what serves),
challenger = "logit", both trained on the SAME four chronological blocks, scored on the untouched
holdout (newest 20%), per track, never pooled. This module only reads those JSON files.

Verdict per track x market, fixed before results were read:
  LOGIT_BETTER   holdout log-loss delta (logit - prob) 95% CI entirely below 0
  LOGIT_WORSE    CI entirely above 0
  NO_DIFFERENCE  otherwise
League levels are judged separately: league_slope 1.0 = the model's league averages move one
for one with reality; > 1 = squashed. Research only - nothing here is promotable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR / "studies" / "logit_calibration"
TASKS = ("std_ou25", "nf_ou25", "side_btts", "side_over15", "side_over35")
MARKET = {"std_ou25": "O/U 2.5", "nf_ou25": "O/U 2.5", "side_btts": "BTTS", "side_over15": "Over 1.5",
          "side_over35": "Over 3.5"}


def verdict(ci) -> str:
    if not ci or ci[0] is None:
        return "NOT_EVALUABLE"
    if ci[1] < 0:
        return "LOGIT_BETTER"
    if ci[0] > 0:
        return "LOGIT_WORSE"
    return "NO_DIFFERENCE"


def collect(src: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rows, leagues, raw = [], [], {}
    for t in TASKS:
        f = src / f"{t}.json"
        if not f.exists():
            rows.append({"task": t, "market": MARKET[t], "status": "MISSING"})
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        raw[t] = r
        for track, v in r["tracks"].items():
            if "holdout" not in v:
                rows.append({"task": t, "market": MARKET[t], "track": track, "status": v.get("status")})
                continue
            for window in ("holdout", "live_from_2026_09_01"):
                e = v.get(window)
                if not e:
                    continue
                lv = e["league_level"]
                rows.append({
                    "task": t, "market": MARKET[t], "track": track, "window": window, "n": e["n"],
                    "matchdays": e["matchdays"], "dates": " .. ".join(e["dates"]),
                    "ll_prob": e["prob"]["log_loss"], "ll_logit": e["logit"]["log_loss"],
                    "ll_market": (e.get("market") or {}).get("log_loss"),
                    "delta_ll": e["delta_log_loss_logit_minus_prob"], "delta_ll_ci95": e["delta_log_loss_ci95"],
                    "brier_prob": e["prob"]["brier"], "brier_logit": e["logit"]["brier"],
                    "delta_brier_ci95": e["delta_brier_ci95"],
                    "cal_slope_prob": e["prob"]["calibration"]["slope"], "cal_slope_logit": e["logit"]["calibration"]["slope"],
                    "cal_int_prob": e["prob"]["calibration"]["intercept"], "cal_int_logit": e["logit"]["calibration"]["intercept"],
                    "sd_p_prob": e["prob"]["sd_p"], "sd_p_logit": e["logit"]["sd_p"],
                    "league_sd_actual": lv["sd_actual"], "league_sd_prob": lv["sd_prob"],
                    "league_sd_logit": lv["sd_logit"], "league_sd_market": lv["sd_market"],
                    "league_slope_prob": lv.get("league_slope_prob"), "league_slope_logit": lv.get("league_slope_logit"),
                    "league_err_prob_pp": lv.get("mean_abs_league_error_prob_pp"),
                    "league_err_logit_pp": lv.get("mean_abs_league_error_logit_pp"),
                    "resid_gain_prob": e["prob"]["residual_vs_market"].get("gain"),
                    "resid_gain_prob_ci95": e["prob"]["residual_vs_market"].get("gain_ci95"),
                    "resid_gain_logit": e["logit"]["residual_vs_market"].get("gain"),
                    "resid_gain_logit_ci95": e["logit"]["residual_vs_market"].get("gain_ci95"),
                    "market_class": r["market_class"], "pooled_training": r["pooled_training"],
                    "verdict": verdict(e["delta_log_loss_ci95"]) if window == "holdout" else "DESCRIPTIVE"})
                if window == "holdout":
                    for x in e["per_league"]:
                        leagues.append({"task": t, "market": MARKET[t], "track": track, **x})
    return pd.DataFrame(rows), pd.DataFrame(leagues), raw


def main(argv=None) -> int:
    src = Path((argv or sys.argv[1:])[0])
    v, lg, raw = collect(src)
    OUT.mkdir(parents=True, exist_ok=True)
    v.to_csv(OUT / "verdict.csv", index=False)
    lg.to_csv(OUT / "per_league.csv", index=False)
    summary = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
               "champion": "calibration_space=prob (serving)", "challenger": "calibration_space=logit",
               "promotable": False, "production_changed": "NO",
               "verdicts": v[v.get("window", pd.Series(dtype=str)) == "holdout"][["task", "track", "verdict"]].to_dict("records")
               if "window" in v else [], "tasks": raw}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    cols = [c for c in ("task", "track", "window", "n", "delta_ll", "delta_ll_ci95", "league_slope_prob",
                        "league_slope_logit", "verdict") if c in v.columns]
    print(v[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
