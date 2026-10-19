"""Longshot v1 is frozen: its gate logic may not change under the same registration."""
import json

from src.analytics import longshot_forward as LF


def test_gate_logic_matches_frozen_registration():
    reg = json.loads(LF.REG.read_text(encoding="utf-8"))
    assert reg["version"] == "longshot-1.0.0"
    assert reg["gate_logic_sha256"] == LF._src_sha(), (
        "longshot_plan.py changed after the freeze - create registration_v2 and a new forward window")


def test_forward_window_starts_after_freeze():
    reg = json.loads(LF.REG.read_text(encoding="utf-8"))
    assert reg["forward_from_month"] >= "2026-11" and reg["min_forward_months_before_production_use"] >= 6
