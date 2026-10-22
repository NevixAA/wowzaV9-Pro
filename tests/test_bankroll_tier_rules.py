"""Per-track tier rule (2026-10-22): equal tiers where the edge does not rank outcomes, ladder where it does."""
import numpy as np
import pandas as pd

from src.bankroll import allocator as A
from src.bankroll.data import staked, tier_multiplier

POLICY = {"tier_multipliers": {"SNIPER": 1.1, "MARKSMAN": 0.9},
          "tracks": {"nf|OU25": {"state": "ACTIVE_LOW"}, "nf|BTTS": {"state": "ACTIVE"}, "std|BTTS": {"state": "PAPER"}}}


def _bets(track, n, ranks, seed=0):
    rng = np.random.default_rng(seed)
    edge = rng.uniform(3, 15, n)
    unit = np.where(edge > 9, 1.0, -1.0) if ranks else rng.choice([1.0, -1.0], n)
    tier = np.where(edge >= 12, "SNIPER", np.where(edge >= 8, "MARKSMAN", "VALUABLE"))
    return pd.DataFrame({"track": track, "edge": edge, "unit": unit, "signal_tier": tier,
                         "date": pd.Timestamp("2026-09-01")})


def test_non_ranking_track_gets_equal_tiers_ranking_track_keeps_ladder():
    b = pd.concat([_bets("nf|OU25", 300, ranks=False), _bets("nf|BTTS", 300, ranks=True), _bets("std|BTTS", 40, False)])
    rules, rows = A.derive_tier_rules(b, POLICY, "2026-10-22")
    assert rules["nf|OU25"] == {"SNIPER": 1.0, "MARKSMAN": 1.0, "VALUABLE": 1.0}
    assert "nf|BTTS" not in rules
    assert {r["track"]: r["rule"] for r in rows}["std|BTTS"].startswith("KEEP")


def test_existing_override_is_kept_without_evidence():
    pol = {**POLICY, "track_tier_multipliers": {"std|BTTS": {"SNIPER": 1.0, "MARKSMAN": 1.0, "VALUABLE": 1.0}}}
    rules, _ = A.derive_tier_rules(_bets("std|BTTS", 20, False), pol, "2026-10-22")
    assert rules["std|BTTS"]["VALUABLE"] == 1.0


def test_staked_follows_the_override_and_the_ladder():
    pol = {**POLICY, "track_tier_multipliers": {"nf|OU25": {"SNIPER": 1.0, "MARKSMAN": 1.0, "VALUABLE": 1.0}}}
    assert tier_multiplier(pol, "nf|OU25", "VALUABLE") == 1.0
    assert tier_multiplier(pol, "nf|BTTS", "VALUABLE") == 0.0
    b = pd.concat([_bets("nf|OU25", 50, False), _bets("nf|BTTS", 50, False)])
    s = staked(b, pol)
    assert (s[s.track == "nf|BTTS"].signal_tier != "VALUABLE").all()
    assert (s[s.track == "nf|OU25"].signal_tier == "VALUABLE").any()


def test_validate_bounds_track_overrides():
    pol = {"portfolio": {"single_bet_cap": 0.02, "fixture_cap": 0.02, "daily_cap": 0.06, "league_daily_cap": 0.03,
                         "league_market_daily_cap": 0.03},
           "tier_multipliers": {"SNIPER": 1.1, "MARKSMAN": 0.9}, "convergence": {"multiplier": 1.15},
           "tracks": {}, "paper_leagues": ["USA MLS"],
           "track_tier_multipliers": {"nf|OU25": {"SNIPER": 1.0, "MARKSMAN": 1.0, "VALUABLE": 1.5}}}
    assert any("VALUABLE" in v for v in A.validate(pol))
