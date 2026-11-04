"""The October 2026 studies: the statistics must behave before their verdicts are trusted.

    python -m pytest tests/test_studies.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.studies import common as C  # noqa: E402
from src.studies import evidence as E  # noqa: E402


# Data Truth 2026-11-01: league names, paper leagues, model types and the club resolver are read
# from v9's league registry, so these tests need a v9 checkout (CI sets V9_LOCAL).
def _v9_present() -> bool:
    from config import pro_config as _cfg
    return (_cfg.V9_LOCAL / "config.py").exists()


needs_v9 = pytest.mark.skipif(not _v9_present(), reason="needs a v9 checkout (V9_LOCAL)")



@needs_v9
def test_matcher_accepts_abbreviations_and_refuses_ambiguity():
    """Matching is v9's league-scoped result resolver on a CANONICAL league (Data Truth)."""
    assert C.same_club("Atl. Tucuman", "Atletico Tucuman")
    assert C.same_club("Dep. Riestra", "Deportivo Riestra")
    assert not C.same_club("Real Madrid", "Real Sociedad")
    lg = "Argentina Primera Division"
    left = pd.DataFrame([{"league": lg, "match_date": "2026-09-01", "home_team": "Gimnasia La Plata",
                          "away_team": "Boca Juniors"}])
    right = pd.DataFrame([
        {"league": lg, "match_date": "2026-09-02", "home_team": "Gimnasia L.P.", "away_team": "Boca Juniors"},
        {"league": lg, "match_date": "2026-09-01", "home_team": "Gimnasia Mendoza", "away_team": "Boca Juniors"}])
    # the alias store proves Gimnasia La Plata = Gimnasia L.P.; Gimnasia Mendoza is another club
    assert C.match_frames(left, right).iloc[0] == 0, "a UTC date one day later still matches"
    two = pd.concat([right.iloc[:1], right.iloc[:1].assign(match_date="2026-09-01")], ignore_index=True)
    assert pd.isna(C.match_frames(left, two).iloc[0]), "two candidates must be refused, not guessed"
    # Owner rule 2026-11-02 (v9 team_names, proven club identity only): a bare 'Gimnasia' / 'Boca'
    # is not provably either club, so it matches nothing - never the nearest spelling.
    bare = left.assign(home_team="Gimnasia", away_team="Boca")
    assert pd.isna(C.match_frames(bare, right).iloc[0]) and pd.isna(C.match_frames(bare, right.iloc[:1]).iloc[0])
    # A league the registry does not know never matches - no raw-string league join.
    assert pd.isna(C.match_frames(left.assign(league="Not A League"),
                                  right.assign(league="Not A League")).iloc[0])


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


def test_challenger_never_bets_against_the_model():
    """An anti-informative model must get weight 0, not a negative weight."""
    from src.studies import ou_challenger as OC
    rng = np.random.default_rng(5)
    p_true = rng.uniform(0.3, 0.7, 3000)
    y = (rng.random(3000) < p_true).astype(float)
    p_market = np.clip(p_true + rng.normal(0, 0.02, 3000), 0.05, 0.95)
    p_v9 = np.clip(1 - p_true + rng.normal(0, 0.02, 3000), 0.05, 0.95)   # points the wrong way
    b, raw = OC._fit(pd.DataFrame({"p_market": p_market, "p_v9": p_v9, "y": y}), return_raw=True)
    assert raw[2] < 0 and b[2] == 0.0


def test_challenger_keeps_a_useful_model():
    from src.studies import ou_challenger as OC
    rng = np.random.default_rng(6)
    p_true = rng.uniform(0.3, 0.7, 4000)
    y = (rng.random(4000) < p_true).astype(float)
    p_market = np.full(4000, 0.5)                                   # market knows nothing
    b = OC._fit(pd.DataFrame({"p_market": p_market + rng.normal(0, 0.01, 4000), "p_v9": p_true, "y": y}))
    assert b[2] > 0.5
