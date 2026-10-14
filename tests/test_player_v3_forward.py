"""The V3 forward test is pre-registered: its rules and its frozen artifacts must not drift.

    python -m pytest tests/test_player_v3_forward.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.player_v3 import forward as FW  # noqa: E402


def test_registration_is_frozen():
    assert FW.REGISTERED_ON == "2026-10-14" and FW.WINDOW_FROM == "2026-10-15"
    assert FW.MARKETS == ("goals", "sot", "sot2", "sot3") and FW.EV_BAR == 1.05 and FW.N_MIN == 150
    assert (FW.FIT_BEFORE, FW.CAL_FROM, FW.CAL_TO) == ("2025-07-01", "2025-07-01", "2026-06-27")


def test_frozen_artifacts_exist_and_match_registration():
    reg = json.loads((FW.REG_DIR / "registration.json").read_text(encoding="utf-8"))
    assert reg["registered_on"] == FW.REGISTERED_ON and reg["window_from"] == FW.WINDOW_FROM
    for mk in FW.MARKETS:
        assert (FW.MODEL_DIR / f"{mk}.pkl").exists()
        assert reg["markets"][mk]["c_wowza"] > 0          # Wowza enters with a positive weight


def test_judge_needs_sample_profit_and_clv():
    n = 200
    days = [f"2026-11-{1 + i % 28:02d}" for i in range(n)]
    good = pd.DataFrame({"y": ([1] * 120 + [0] * 80), "entry_best": 2.2, "close_best": 2.0, "match_date": days})
    assert FW.judge(good, 0.0, 0.45)["verdict"] == "EDGE"
    no_clv = good.assign(close_best=2.4)                   # profitable but never beat the close
    assert FW.judge(no_clv, 0.0, 0.45)["verdict"].startswith("COLLECTING")
    bad = good.assign(y=[1] * 40 + [0] * 160)
    assert FW.judge(bad, 0.0, 0.45)["verdict"] == "NO_EDGE"
    assert FW.judge(good.head(30), 0.0, 0.45)["verdict"] == "COLLECTING (30/150)"
