"""The October 2026 studies: the statistics must behave before their verdicts are trusted.

    python -m pytest tests/test_studies.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.studies import common as C  # noqa: E402
from src.studies import evidence as E  # noqa: E402


def test_matcher_accepts_abbreviations_and_refuses_ambiguity():
    assert C.same_club("Atl. Tucuman", "Atletico Tucuman")
    assert C.same_club("Dep. Riestra", "Deportivo Riestra")
    assert not C.same_club("Real Madrid", "Real Sociedad")
    left = pd.DataFrame([{"league": "L", "match_date": "2026-09-01", "home_team": "Gimnasia", "away_team": "Boca"}])
    right = pd.DataFrame([
        {"league": "L", "match_date": "2026-09-02", "home_team": "Gimnasia L.P.", "away_team": "Boca Juniors"},
        {"league": "L", "match_date": "2026-09-01", "home_team": "Gimnasia Mendoza", "away_team": "Boca Juniors"}])
    assert pd.isna(C.match_frames(left, right).iloc[0]), "two candidates must be refused, not guessed"
    right = right.iloc[:1]
    assert C.match_frames(left, right).iloc[0] == 0, "a UTC date one day later still matches"


def test_confidence_sequence_covers_the_true_mean():
    misses = 0
    rng = np.random.default_rng(1)
    for _ in range(200):
        x = rng.normal(0.0, 5.0, 300)
        cs = E.confidence_sequence(x)
        misses += cs["first_bet_lcb_above_0"] is not None or cs["first_bet_ucb_below_0"] is not None
    assert misses / 200 <= 0.15, f"anytime error rate {misses / 200} exceeds alpha by too much"


def test_confidence_sequence_detects_a_real_edge():
    x = np.random.default_rng(2).normal(2.0, 5.0, 600)
    assert E.confidence_sequence(x)["first_bet_lcb_above_0"] is not None


def test_cusum_alarms_on_a_drop_and_not_on_noise():
    rng = np.random.default_rng(3)
    assert not E.cusum_down(rng.normal(0, 1, 300))["alarm"]
    assert E.cusum_down(np.r_[rng.normal(0, 1, 50), rng.normal(-1.5, 1, 100)])["alarm"]


def test_logistic_recovers_a_known_coefficient():
    rng = np.random.default_rng(4)
    x = rng.normal(0, 1, 5000)
    y = (rng.random(5000) < 1 / (1 + np.exp(-(0.3 + 1.2 * x)))).astype(float)
    b, _ = C.fit_logistic(x[:, None], y)
    assert abs(b[1] - 1.2) < 0.1 and abs(b[0] - 0.3) < 0.1
