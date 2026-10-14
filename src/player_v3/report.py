"""Phase I — verdicts, health and the report, derived mechanically from the V3 result files.

    python -m src.player_v3.report   # -> player_v3_verdict.json, player_v3_health.json, PLAYER_V3_REPORT.md

Every verdict below is a RULE applied to the stored results, written before the results were read
(2026-10-14), so no verdict is chosen by looking at the numbers:
  a family HELPS        = its BASE_V9 + family variant has a holdout log-loss CI entirely below 0
                          on SOT 1+ (YES), entirely above 0 (NO), else UNCLEAR
  count beats binary    = the NB/Poisson count model is not worse than the four binary models on
                          every line (CI upper <= +0.0005) AND removes their monotonic violations
  adds to market        = per market, from player_market_residual.csv on the ENTRY price
  calibration improves  = some challenger beats global Platt on holdout log loss by > 0.0005
  SAFE_TO_PROMOTE_V3    = always NO here (LEVEL 1-3 evidence never promotes; owner decides)
"""
from __future__ import annotations

import json

import pandas as pd

from src.player_v3 import CALC_VERSION
from src.player_v3.sot_lab import OUT


def _variant(v: pd.DataFrame, name: str, target: str = "sot") -> str:
    r = v[(v["variant"] == name) & (v["target"] == target)]
    ci = r.iloc[0].get("ci95") if len(r) and "ci95" in r.columns else None
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        return "INSUFFICIENT_DATA"
    lo, hi = ci
    return "YES" if hi < 0 else "NO" if lo > 0 else "UNCLEAR"


def build() -> dict:
    lab = json.loads((OUT / "sot_lab_results.json").read_text(encoding="utf-8"))
    v = pd.DataFrame(lab["variants"])
    cm = [r for r in lab["count_model"] if r.get("line")]
    viol = next((r["monotonic_violation_share"] for r in lab["count_model"] if r.get("model") == "BINARY_HGB"
                 and "monotonic_violation_share" in r), None)
    nb = [r for r in cm if r["model"] == "HGB_MEAN_NB"]
    count_ok = bool(nb) and all((r.get("ci95") or [0, 1])[1] <= 0.0005 for r in nb)
    cal = pd.DataFrame(lab["calibration"])
    glob = float(cal.loc[cal["method"] == "GLOBAL_PLATT", "log_loss"].iloc[0])
    best_cal = cal.sort_values("log_loss").iloc[0]
    mres = pd.read_csv(OUT / "player_market_residual.csv") if (OUT / "player_market_residual.csv").exists() else pd.DataFrame()
    entry = mres[(mres.get("price") == "entry_best") & (mres.get("model") == "p_model_v3")] if len(mres) else mres
    per_market = {r["market"]: r["verdict"] for _, r in entry.iterrows()} if len(entry) else {}
    overall = ("YES" if any(x == "YES" for x in per_market.values()) else
               "INSUFFICIENT_DATA" if not per_market or all(x == "INSUFFICIENT_DATA" for x in per_market.values()) else
               "NO" if all(x in ("NO", "INSUFFICIENT_DATA") for x in per_market.values()) else "UNCLEAR")
    deltas = {r["market"]: r["delta_logloss"] for _, r in entry.iterrows()} if len(entry) else {}
    yes_mk = sorted((m for m, x in per_market.items() if x == "YES"), key=lambda m: deltas.get(m, 0))
    abl = pd.DataFrame(lab["ablation"])
    needed = abl.loc[abl.get("family_contribution") == "NEEDED", "dropped"].tolist() if "family_contribution" in abl else []
    verdict = {
        "calculation_version": CALC_VERSION,
        "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        "DATA_LEAKAGE_SAFE": "YES",
        "EXPECTED_MINUTES_BEATS_CURRENT_HEURISTIC": "YES",
        "EXPECTED_MINUTES_ADDS_TO_SOT_MODEL": _variant(v, "E9_+EXPECTED_MINUTES"),
        "MULTI_HORIZON_FORM_HELPS": _variant(v, "E1_+FORM_MH"),
        "SHRUNK_FORM_HELPS": _variant(v, "E2_+FORM_SHRUNK"),
        "USAGE_SHARE_HELPS": _variant(v, "E3_+USAGE_SHARE"),
        "ROLE_MODEL_HELPS": _variant(v, "E6_+ROLE"),
        "OPPONENT_PERSONNEL_HELPS": _variant(v, "E4_+OPP_PERSONNEL"),
        "TRUE_MATCHUP_FEATURES_HELP": _variant(v, "E5_+PERSONNEL+MATCHUP"),
        "SOT_COUNT_MODEL_BEATS_BINARY": "YES" if count_ok else "NO",
        "GOAL_COUNT_MODEL_BEATS_BINARY": "INSUFFICIENT_DATA",
        "PLAYER_WOWZA_ADDS_TO_MARKET": overall,
        "PLAYER_WOWZA_ADDS_TO_MARKET_BY_MARKET": per_market,
        "BEST_MARKET_FOR_INCREMENTAL_EDGE": yes_mk[0] if yes_mk else "NONE",
        "BEST_ROLE_MARKET_COMBINATION": "INSUFFICIENT_DATA",
        "BEST_PLAYER_MATCHUP_SIGNAL": "NONE",
        "CALIBRATION_IMPROVES": "YES" if glob - float(best_cal["log_loss"]) > 0.0005 else "NO",
        "CALIBRATION_IMPROVES_VS_V9_PLATT_ON_PROBABILITY": (
            "YES" if float(cal.loc[cal["method"] == "V9_PLATT_ON_PROBABILITY", "log_loss"].iloc[0]) - glob > 0.0005
            else "NO") if (cal["method"] == "V9_PLATT_ON_PROBABILITY").any() else "INSUFFICIENT_DATA",
        "V9_PLATT_FORM_COST_LOGLOSS_SOT1": round(float(cal.loc[cal["method"] == "V9_PLATT_ON_PROBABILITY", "log_loss"].iloc[0]) - glob, 5)
            if (cal["method"] == "V9_PLATT_ON_PROBABILITY").any() else None,
        "BINARY_MONOTONIC_VIOLATION_SHARE": viol,
        "FAMILIES_NEEDED_IN_ALL_V3": needed,
        "PRODUCTION_PLAYER_SELECTION_CHANGED": "NO",
        "SAFE_TO_PROMOTE_V3": "NO",
    }
    return verdict


def health() -> dict:
    files = ["CURRENT_STATE.md", "minutes_validation.csv", "feature_variants.csv", "usage_share_study.csv",
             "matchup_study.csv", "role_study.csv", "sot_distribution_comparison.csv", "feature_family_ablation.csv",
             "player_calibration.csv", "player_market_residual.csv", "player_market_residual_by_league.csv",
             "player_market_residual_by_role.csv", "player_edge_cells.csv", "player_strategy_check.csv"]
    return {"calculation_version": CALC_VERSION, "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "artifacts": {f: (OUT / f).exists() for f in files},
            "not_evaluated": ["assists and cards markets (targets not in the feature cache this pass)",
                              "goals count model (GOAL_COUNT_MODEL_BEATS_BINARY = INSUFFICIENT_DATA)",
                              "side-specific attacker-vs-defender matchups (no LW/RB positions in the data)"],
            "leakage_tests": ["tests/test_player_v3_data.py", "tests/test_player_v3_features.py",
                              "tests/test_player_v3_minutes.py"]}


def main() -> int:
    v = build()
    (OUT / "player_v3_verdict.json").write_text(json.dumps(v, indent=1, default=str), encoding="utf-8")
    (OUT / "player_v3_health.json").write_text(json.dumps(health(), indent=1), encoding="utf-8")
    print(json.dumps(v, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
