"""The calibration-shadow decision rule (registered 2026-10-14) - pinned so it cannot drift."""
import numpy as np
import pandas as pd

from src.studies import calibration_shadow as cs


def _rows(n, shadow_shift, seed=0):
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.2, 0.8, n)
    y = (rng.uniform(size=n) < p).astype(float)
    return pd.DataFrame({"market": "sot", "date": pd.date_range("2026-10-15", periods=n, freq="h").strftime("%Y-%m-%d"),
                         "p_old": np.clip(p + shadow_shift, 0.01, 0.99), "p_logit_shadow": p, "y": y})


def test_rule_constants():
    assert cs.REGISTERED_ON == "2026-10-14"
    assert cs.N_MIN == {"team": 1000, "props": 2000}


def test_collecting_below_n_min():
    assert cs.grade(_rows(500, 0.15), "props")["sot"]["verdict"] == "COLLECTING"


def test_better_and_worse():
    assert cs.grade(_rows(3000, 0.15), "props")["sot"]["verdict"] == "SHADOW_BETTER"       # old is miscalibrated
    worse = _rows(3000, 0.15).rename(columns={"p_old": "p_logit_shadow", "p_logit_shadow": "p_old"})
    assert cs.grade(worse, "props")["sot"]["verdict"] == "SHADOW_WORSE"


def test_waiting_when_no_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "SHADOW_DIR", tmp_path)
    assert cs.build()["overall"] == "WAITING_FOR_SHADOW_ROWS"
