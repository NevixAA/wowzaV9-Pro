"""Frozen candidate forward tests: forward rows only, never CONFIRMED, definitions untouched."""
import json

import pandas as pd

from src.studies import candidate_forward as CF

H = {"id": "H-GATE-X", "league": "Mexico Liga MX", "market": "ou25", "model_type": "new_format",
     "candidate_gate": 0.09, "production_gates": {"sniper": 0.12}, "min_forward_n": 3, "required_matchdays": 2,
     "forward_start": "2026-10-21 00:00:00+00:00", "historical": {"fit_roi": 0.39}}


def _row(fid, gen, edge, result, pnl, clv=None):
    return {"fixture_id": fid, "generated_at": gen, "kickoff": "2026-10-25T20:00:00Z", "league": "Mexico Liga MX",
            "model_type": "new_format", "market": "over25", "side": "OVER", "raw_edge": edge, "result": result,
            "flat_pnl": pnl, "clv": clv}


def test_only_true_forward_rows_count():
    s = pd.DataFrame([_row("a", "2026-10-15T10:00:00Z", 12, "WIN", 1.0),        # post-discovery, before start
                      _row("b", "2026-10-22T10:00:00Z", 12, "WIN", 1.0),
                      _row("c", "2026-10-22T10:00:00Z", 5, "WIN", 1.0)])         # below the candidate gate
    r = CF.evaluate({"hypotheses": [H]}, s)[0]
    assert r["TRUE_FORWARD"]["n"] == 1 and r["status"] == "ACCRUING"


def test_confirmed_is_never_assigned_and_registry_is_frozen():
    s = pd.DataFrame([_row(f"f{i}", "2026-10-22T10:00:00Z", 12, "WIN", 1.0, 2.0) for i in range(10)])
    s["kickoff"] = [f"2026-10-{22 + i % 5}T20:00:00Z" for i in range(10)]
    r = CF.evaluate({"hypotheses": [H]}, s)[0]
    assert r["status"] in ("FORWARD_SUPPORTED", "ACCRUING") and r["status"] != "CONFIRMED"
    reg = json.loads(CF.REG.read_text(encoding="utf-8"))
    assert reg["confirmed_assignable_here"] is False
    assert all(h["forward_start"].startswith("2026-10-21") for h in reg["hypotheses"])
