"""League-level input (A) and market-anchored (B) challengers (owner 2026-11-01) - collect the CI benchmark.

    python -m src.studies.league_anchor <dir with v9 benchmark outputs>
        -> output/studies/league_anchor/{verdict.csv, tips.csv, summary.json}

The benchmark runs inside v9 (research/league-level-and-anchor-2026-11,
scripts/league_anchor_benchmark.py): CHAMPION (as served), A_LEAGUE (+ as-of league-level features),
B_CHAMP / B_LEAGUE (logistic on logit(entry market price) + logit(model), refitted monthly on earlier
rows only), MARKET (de-vigged two-sided ENTRY price). Same chronological blocks, untouched newest-20%
holdout, per track, never pooled. This module only reads the JSON files.

Verdicts, fixed before results were read (95% matchday-block CI of the per-row log-loss difference):
  A_vs_CHAMPION   BETTER (CI < 0) / WORSE (CI > 0) / NO_DIFFERENCE, on ALL holdout rows
  X_vs_MARKET     BEATS_MARKET (CI < 0) / LOSES_TO_MARKET (CI > 0) / TIES_MARKET, on priced rows
  NO_REAL_PRICE   no real two-sided entry price for this track x market - B and tips not evaluated
Research only - nothing here is promotable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR / "studies" / "league_anchor"
TASKS = ("std_ou25", "nf_ou25", "side_btts", "side_over15", "side_over35")
MARKET = {"std_ou25": "O/U 2.5", "nf_ou25": "O/U 2.5", "side_btts": "BTTS", "side_over15": "Over 1.5",
          "side_over35": "Over 3.5"}
ARMS = ("CHAMPION", "A_LEAGUE", "B_CHAMP", "B_LEAGUE")


def _v(ci, better="BETTER", worse="WORSE", same="NO_DIFFERENCE") -> str:
    if not ci or ci[0] is None:
        return "NOT_EVALUABLE"
    return better if ci[1] < 0 else worse if ci[0] > 0 else same


def collect(src: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rows, tips, raw = [], [], {}
    for t in TASKS:
        f = src / f"{t}.json"
        if not f.exists():
            rows.append({"task": t, "market": MARKET[t], "status": "MISSING"})
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        raw[t] = r
        for track, v in r["tracks"].items():
            for window in ("holdout", "live_from_2026_09_01"):
                e = v.get(window)
                if not e:
                    continue
                al, lv = e["all_rows"], e["league_level_all_rows"]
                d = e["delta_A_minus_CHAMPION_all_rows"]
                row = {"task": t, "market": MARKET[t], "track": track, "window": window, "n": e["n"],
                       "n_priced": e["n_priced"], "price_coverage": v.get("price_coverage"),
                       "ll_champion": al["CHAMPION"].get("log_loss"), "ll_A": al["A_LEAGUE"].get("log_loss"),
                       "delta_A": d.get("delta_ll"), "delta_A_ci95": d.get("ci95"),
                       "A_vs_CHAMPION": _v(d.get("ci95")),
                       "slope_champion": al["CHAMPION"].get("calibration", {}).get("slope"),
                       "slope_A": al["A_LEAGUE"].get("calibration", {}).get("slope"),
                       "league_sd_actual": lv.get("sd_actual"), "league_sd_champion": lv.get("sd_p_CHAMPION"),
                       "league_sd_A": lv.get("sd_p_A_LEAGUE"),
                       "league_err_champion_pp": lv.get("mean_abs_league_error_p_CHAMPION_pp"),
                       "league_err_A_pp": lv.get("mean_abs_league_error_p_A_LEAGUE_pp")}
                pr = e.get("priced_rows", {})
                if "p_mkt" in pr or "mkt" in pr:
                    row["ll_market"] = pr["mkt"].get("log_loss")
                    for arm in ARMS:
                        dm = e["delta_vs_market"].get(arm, {})
                        row[f"ll_{arm}_priced"] = pr.get(arm, {}).get("log_loss")
                        row[f"{arm}_vs_MARKET"] = _v(dm.get("ci95"), "BEATS_MARKET", "LOSES_TO_MARKET", "TIES_MARKET")
                        row[f"{arm}_minus_market"] = dm.get("delta_ll")
                    for arm in ("CHAMPION", "A_LEAGUE"):
                        rs = e["residual_vs_market"].get(arm, {})
                        row[f"residual_gain_{arm}"] = rs.get("gain")
                        row[f"residual_gain_{arm}_ci95"] = rs.get("gain_ci95")
                    for arm, s in e["tips"].items():
                        tips.append({"task": t, "market": MARKET[t], "track": track, "window": window, "arm": arm, **s})
                else:
                    row["market_status"] = pr.get("status", "NO_REAL_TWO_SIDED_PRICE")
                rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(tips), raw


def main(argv=None) -> int:
    src = Path((argv or sys.argv[1:] or ["_in"])[0])
    v, tp, raw = collect(src)
    OUT.mkdir(parents=True, exist_ok=True)
    v.to_csv(OUT / "verdict.csv", index=False)
    tp.to_csv(OUT / "tips.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps({"verdict": v.to_dict("records"), "tips": tp.to_dict("records"),
                                                  "meta": {t: {k: r.get(k) for k in ("blocks", "price_sources", "thresholds",
                                                                                        "league_features", "pooled_training")}
                                                           for t, r in raw.items()}}, indent=1, default=str), encoding="utf-8")
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        print(v.to_string(index=False))
        print(tp.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
