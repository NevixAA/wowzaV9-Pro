"""Bray / Bray Wanderers and Drogheda / Drogheda United (Data Truth audit 2026-11-01, row "BRAY").

Verified on v9's warehouse histories (output/fd_history.parquet, output/af_history.parquet):
both pairs are ONE club stored under a football-data spelling and an API-Football spelling, in the
same league identity. Every date on which both spellings appear is the same match (same side,
same score), and neither pair ever plays two different fixtures on one date.

Drogheda United -> Drogheda is already in the identity/1.0 map. Bray Wanderers -> Bray is NOT: v9's
evidence rule needs >= 2 duplicate dates and Bray has exactly one (the 2024-11-16 play-off, 1-3), so
the pair sits in rejected_pairs. The map is v9's serving map (Pro holds a byte-identical copy,
pinned by hash), so accepting the alias is a v9 identity-map change with a new IDENTITY_VERSION -
it is requested from the registry owner, not typed into Pro. These tests pin the EVIDENCE so that
decision can be made on data, and fail if the data stops supporting it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg  # noqa: E402
from src.data import canonical_identity as CI  # noqa: E402

LEAGUE = "Ireland Premier Division"
FD = cfg.V9_LOCAL / "output" / "fd_history.parquet"


def _side_rows(d: pd.DataFrame, name: str) -> pd.DataFrame:
    a = d[(d["home_team"] == name) | (d["away_team"] == name)].copy()
    home = a["home_team"] == name
    a["side"] = home.map({True: "H", False: "A"})
    a["gf"] = a["home_goals"].where(home, a["away_goals"])
    a["ga"] = a["away_goals"].where(home, a["home_goals"])
    return a[["date", "side", "gf", "ga"]]


@pytest.fixture(scope="module")
def ireland() -> pd.DataFrame:
    if not FD.exists():
        pytest.skip("needs a v9 checkout with output/fd_history.parquet")
    d = pd.read_parquet(FD)
    d = d[d["league"] == LEAGUE].copy()
    d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
    return d


@pytest.mark.parametrize("short,long_", [("Drogheda", "Drogheda United"), ("Bray", "Bray Wanderers")])
def test_two_spellings_are_one_club_in_the_data(ireland, short, long_):
    a, b = _side_rows(ireland, short), _side_rows(ireland, long_)
    assert len(a) and len(b), f"{short}/{long_} missing from {LEAGUE}"
    j = a.merge(b, on="date", suffixes=("_s", "_l"))
    assert len(j) >= 1, "the spellings never share a date - no evidence either way"
    # every shared date is the SAME match (side and score agree): duplicates, never two fixtures
    same = (j["side_s"] == j["side_l"]) & (j["gf_s"] == j["gf_l"]) & (j["ga_s"] == j["ga_l"])
    assert bool(same.all()), j[~same].to_string()
    # a club plays at most once a day under each spelling
    assert not a["date"].duplicated().any() and not b["date"].duplicated().any()


def test_identity_map_state_matches_the_evidence():
    """Drogheda is aliased; Bray is aliased since identity/1.1 (owner-accepted 2026-11-02, v9
    identity_repair v9r-identity-1.1) - refused under identity/1.0 on the >=2-date rule."""
    d = json.loads(CI.ALIAS_MAP_PATH.read_text(encoding="utf-8"))
    m = d["map"].get(LEAGUE, {})
    assert m.get("Drogheda United") == "Drogheda"
    rejected = [r for r in d.get("rejected_pairs", []) if r.get("league") == LEAGUE]
    assert any({r.get("a"), r.get("b")} == {"Bray", "Bray Wanderers"} for r in rejected) \
        or m.get("Bray Wanderers") == "Bray", "Bray pair must be either refused or aliased to 'Bray'"
