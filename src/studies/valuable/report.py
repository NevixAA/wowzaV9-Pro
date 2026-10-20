"""Build the VALUABLE deep-dive workbook + shadow status from output/valuable_deep_dive/*.csv.

    python -m src.studies.valuable.report      # after deep_dive -> WOWZA_VALUABLE_Deep_Dive_<date>.xlsx
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd

from config import pro_config as cfg

OUT = cfg.BASE_DIR / "output" / "valuable_deep_dive"
SH = cfg.BASE_DIR / "output" / "valuable_shadow"

SHEETS = {
    "TIER_COMPARISON": "valuable_tier_comparison.csv", "VALUABLE_OVERVIEW": "valuable_summary.csv",
    "EDGE_BANDS": "valuable_edge_bands.csv", "RAW_VS_FAIR_EDGE": "valuable_fair_edge_bands.csv",
    "MODEL_MARKET": "valuable_monotonicity.csv", "LEAGUE_MARKET": "valuable_league_market.csv",
    "TIER_LEAGUE_MARKET": "valuable_all_cells.csv", "SIDE_ANALYSIS": "valuable_side.csv",
    "ODDS_INTERACTION": "valuable_odds_interaction.csv", "REGIME_ANALYSIS": "valuable_regime_analysis.csv",
    "V11_CONVERGENCE": "valuable_v11_convergence.csv", "WALK_FORWARD": "valuable_walk_forward.csv",
    "SHADOW_1_TO_3": "valuable_low_edge_snapshot.csv", "UPGRADE_EFFECT": "valuable_upgrade_effect.csv",
    "FIRST_SIGHT_TIERS": "valuable_first_sight_tiers.csv", "DRIFT_X_TIER": "valuable_drift_explanation.csv",
    "CALIBRATION": "valuable_calibration.csv", "DATA_QUALITY": "valuable_data_quality.csv",
}


def shadow_status() -> dict:
    st = json.loads((SH / "valuable_shadow_state.json").read_text(encoding="utf-8")) if (SH / "valuable_shadow_state.json").exists() else {}
    out = {"file": "output/valuable_shadow/valuable_shadow.csv", "registered_start": "2026-10-21T00:00:00Z",
           "capture": "daily, .github/workflows/pro_valuable_shadow.yml, from v9's committed predictions.csv history",
           "rows": st.get("rows", 0), "settled": st.get("settled", 0), "last_snapshot": st.get("last_snapshot"),
           "status": "ACCRUING" if st.get("rows") else "REGISTERED - first rows after the first v9 predict commit on/after 2026-10-21",
           "historical_equivalent": "experiments/valuable_2026_10/prematch_snapshots.parquet (2026-08-15..10-20, never bet) -> SHADOW_1_TO_3 sheet",
           "notified": "NO", "bet": "NO"}
    (OUT / "valuable_shadow_status.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def workbook() -> str:
    path = OUT / f"WOWZA_VALUABLE_Deep_Dive_{date.today():%Y-%m-%d}.xlsx"
    res = json.loads((OUT / "valuable_results.json").read_text(encoding="utf-8"))
    hyp = json.loads((OUT / "valuable_candidate_hypotheses.json").read_text(encoding="utf-8"))
    cells = pd.read_csv(OUT / "valuable_league_market.csv")
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        exec_rows = [("PRODUCTION_SELECTION_CHANGED", "NO"), ("TIER_THRESHOLDS_CHANGED", "NO"), ("STAKING_CHANGED", "NO"),
                     ("BET_ENABLED_CHANGED", "NO")] + [(k, json.dumps(v, default=str)) for k, v in res.items()
                                                       if k in ("integrity", "ou25_raw_vs_fair", "btts_production_vs_fair",
                                                                "low_edge_snapshot_meta")]
        pd.DataFrame(exec_rows, columns=["item", "value"]).to_excel(xw, sheet_name="EXEC_SUMMARY", index=False)
        for sheet, f in SHEETS.items():
            if (OUT / f).exists():
                pd.read_csv(OUT / f).to_excel(xw, sheet_name=sheet[:31], index=False)
        cells[cells.ROI_shrunk_pct > 0].sort_values("ROI_shrunk_pct", ascending=False).to_excel(xw, sheet_name="POSITIVE_CELLS", index=False)
        cells[cells.ROI_shrunk_pct <= 0].sort_values("ROI_shrunk_pct").to_excel(xw, sheet_name="NEGATIVE_CELLS", index=False)
        conc = []
        for w, c in res["concentration"].items():
            for k, v in c.items():
                conc.append({"window": w, "cut": k, **(v if isinstance(v, dict) and "N" in v else {"value": json.dumps(v)})})
        pd.DataFrame(conc).to_excel(xw, sheet_name="CONCENTRATION", index=False)
        pd.DataFrame(hyp["hypotheses"]).astype(str).to_excel(xw, sheet_name="CANDIDATE_HYPOTHESES", index=False)
        pd.DataFrame({"METHODOLOGY": [l for l in (OUT / "VALUABLE_DEEP_DIVE.md").read_text(encoding="utf-8").split("\n")
                                      if l.strip()][:400]}).to_excel(xw, sheet_name="METHODOLOGY", index=False)
    return str(path)


if __name__ == "__main__":
    print(shadow_status())
    print(workbook())
