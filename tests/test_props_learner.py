"""Props learner study: the decision machinery, without fitting anything.

    python -m pytest tests/test_props_learner.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.studies import props_learner as PL  # noqa: E402


def test_block_ci_brackets_the_mean_and_is_date_blocked():
    rng = np.random.default_rng(1)
    d = rng.normal(0.01, 0.05, size=4000)
    dates = np.repeat(np.arange(40), 100).astype(str)
    lo, hi = PL._block_ci(d, dates)
    assert lo < d.mean() < hi
    # one date carrying everything: blocks make the interval wider than row-level noise suggests
    d2 = np.where(dates == "0", 1.0, 0.0)
    lo2, hi2 = PL._block_ci(d2, dates)
    assert hi2 - lo2 > 0.02


def test_merge_refuses_to_recommend_with_a_market_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(PL, "OUT", tmp_path)
    row = {"market": "goals", "n_test": 10, "incumbent_logloss": 0.26, "challenger_logloss": 0.259,
           "logloss_diff": -0.001, "diff_ci_low": -0.002, "diff_ci_high": 0.0,
           "incumbent_auc": 0.7, "challenger_auc": 0.7, "incumbent_fit_seconds": 600,
           "challenger_fit_seconds": 20, "speedup": 30, "verdict": "PASS"}
    (tmp_path / "props_learner_goals.json").write_text(json.dumps(row), encoding="utf-8")
    r = PL.merge()
    assert r["recommendation"].startswith("DO NOT SWITCH") and "sot4" in r["missing"]


def test_hgb_guard_rejects_empty_and_constant_columns():
    assert not PL._usable(np.full(50, np.nan))
    assert not PL._usable(np.ones(50))
    assert PL._usable(np.arange(50, dtype=float))
