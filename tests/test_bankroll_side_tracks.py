"""v9's O/U 2.5 policy tracks are split by SIDE (owner decision 2026-10-26): Pro's monthly review must
evaluate each side as its own track, under the unchanged rules (reductions-only while the allocator is
not walk-forward validated), keyed with v9's own track_key.

    python -m pytest tests/test_bankroll_side_tracks.py     (needs V9_LOCAL -> a post-split wowza-betting)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg  # noqa: E402


def _reader():
    if not (cfg.V9_LOCAL / "src" / "bankroll_policy.py").exists():
        return None
    from src.bankroll.data import v9_reader
    return v9_reader()


R = _reader()
pytestmark = pytest.mark.skipif(R is None or not hasattr(R, "track_key"),
                                reason="needs a v9 checkout with the O/U side split (src/bankroll_policy.track_key)")
SIDES = ("new_format|OU25_OVER", "new_format|OU25_UNDER")


@pytest.fixture(scope="module")
def pol():
    return R.load_policy(cfg.V9_LOCAL / "config" / "bankroll_policy.json")


def _bets(n_days=90, over_bias=0.15, under_bias=-0.30, seed=0):
    """NF O/U 2.5 record: OVER wins often, UNDER loses heavily - the two sides diverge."""
    from src.bankroll.data import track_key_fn
    tk = track_key_fn(R)
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_days):
        d = pd.Timestamp("2026-08-10") + pd.Timedelta(days=i)
        for j, (side, bias) in enumerate((("OVER", over_bias), ("UNDER", under_bias), ("OVER", over_bias))):
            win = rng.random() < 0.52 + bias
            rows.append({"date": d, "fixture": f"{d:%F}|{j}", "league": ["A", "B", "C"][j],
                         "model_type": "new_format", "market": "OU25", "side": side,
                         "signal_tier": "SNIPER", "odds": 2.0, "result": "WIN" if win else "LOSS",
                         "unit": 1.0 if win else -1.0, "clv": 0.01, "track": tk("new_format", "OU25", side),
                         "month": d.strftime("%Y-%m")})
    return pd.DataFrame(rows)


def test_evidence_is_keyed_per_side_with_v9s_function():
    from src.bankroll.data import track_key_fn
    tk = track_key_fn(R)
    assert tk("new_format", "OU25", "OVER") == "new_format|OU25_OVER"
    assert tk("standard", "OU25", "UNDER") == "standard|OU25_UNDER"
    assert tk("new_format", "BTTS", "YES") == "new_format|BTTS"
    assert tk("new_format", "OU25", "NAN") == "new_format|OU25_UNKNOWN_SIDE"      # never a real track


def test_policy_has_both_sides_and_no_parent(pol):
    for k in SIDES + ("standard|OU25_OVER", "standard|OU25_UNDER"):
        assert k in pol["tracks"]
    assert "new_format|OU25" not in pol["tracks"] and "standard|OU25" not in pol["tracks"]


def test_allocator_reviews_each_side_as_its_own_track(pol):
    from src.bankroll import allocator as A
    from src.bankroll.evidence import track_evidence
    b = _bets()
    ev = track_evidence(b, "2026-11-10")
    assert set(SIDES) <= set(ev) and ev[SIDES[0]]["n"] == 2 * ev[SIDES[1]]["n"]
    p, dec, _ = A.propose(pol, b, "2026-11-10")
    d = {x["track"]: x for x in dec}
    assert set(SIDES) <= set(d) and "new_format|OU25" not in d
    assert d["new_format|OU25_UNDER"]["decision"] in ("REDUCE", "STOP")             # the losing side only
    assert d["new_format|OU25_OVER"]["decision"] not in ("REDUCE", "STOP")
    assert d["new_format|OU25_OVER"]["n"] != d["new_format|OU25_UNDER"]["n"]
    assert A.validate(p) == []


def test_reductions_only_moves_only_the_losing_side(pol):
    from src.bankroll import allocator as A
    p, _, _ = A.propose(pol, _bets(), "2026-11-10")
    rec = A.reduce_only(pol, p)
    over, under = rec["tracks"]["new_format|OU25_OVER"], rec["tracks"]["new_format|OU25_UNDER"]
    assert over == pol["tracks"]["new_format|OU25_OVER"]                            # never raised here
    assert float(under["base_fraction"]) < float(pol["tracks"]["new_format|OU25_UNDER"]["base_fraction"])
    for k, t in rec["tracks"].items():                                              # nothing ever increases
        assert float(t.get("base_fraction", 0)) <= float(pol["tracks"][k].get("base_fraction", 0)) + 1e-12


def test_simulator_routes_ou25_by_side(pol):
    from src.bankroll import simulate as S
    b = _bets(n_days=3)
    plans = S.day_plans(b, pol)
    f = np.concatenate([plans[d][1.0] for d in sorted(plans)])
    assert (f > 0).any()                                   # O/U stakes exist: the side reached the sizer


def test_pre_split_policy_is_aligned_without_changing_a_value(pol):
    from src.bankroll.data import align_policy_keys
    legacy = {"tracks": {"new_format|OU25": {"state": "ACTIVE_LOW", "base_fraction": 0.005, "max_odds": 2.5},
                         "new_format|BTTS": {"state": "ACTIVE", "base_fraction": 0.0125}},
              "track_tier_multipliers": {"new_format|OU25": {"SNIPER": 1.0, "MARKSMAN": 1.0, "VALUABLE": 1.0}}}
    a = align_policy_keys(legacy, R)
    assert set(a["tracks"]) == {"new_format|OU25_OVER", "new_format|OU25_UNDER", "new_format|BTTS"}
    assert a["tracks"]["new_format|OU25_OVER"] == a["tracks"]["new_format|OU25_UNDER"] == legacy["tracks"]["new_format|OU25"]
    assert a["track_tier_multipliers"]["new_format|OU25_UNDER"] == legacy["track_tier_multipliers"]["new_format|OU25"]
    assert align_policy_keys(pol, R) == pol                                         # already split: unchanged
