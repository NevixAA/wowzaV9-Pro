"""R2 finding 11: the Prediction Lab must group by canonical, league-scoped club identity.

    python -m pytest tests/test_lab_identity.py -q

Equivalence with v9 is PROVEN, not asserted: when a v9 checkout is available (V9_LOCAL or a
sibling ../v9) the tests load v9's own identity_repair.py and the stage-1 functions from v9's
data_loader.py and compare outputs row for row.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data import canonical_identity as CI  # noqa: E402
from src.prediction_lab import data as D  # noqa: E402


def _v9_dir() -> Path | None:
    for c in (os.getenv("V9_LOCAL", ""), str(ROOT.parent / "v9")):
        if c and (Path(c) / "src" / "identity_repair.py").exists():
            return Path(c)
    return None


def _fx(rows):
    return pd.DataFrame(rows, columns=["date", "league", "home_team", "away_team",
                                       "home_goals", "away_goals", "home_shots"]).assign(
        date=lambda d: pd.to_datetime(d["date"]))


# ---------------------------------------------------------------- the map itself

def test_alias_map_hash_is_pinned_and_structurally_valid():
    amap = CI.load_alias_map()
    assert CI.map_sha256(amap) == CI.ALIAS_MAP_SHA256
    st = CI.validate_alias_map(amap)
    assert st["aliases"] == 142 and st["leagues"] == 18


def test_alias_map_is_identical_to_v9_serving_map():
    v9 = _v9_dir()
    if v9 is None:
        pytest.skip("no v9 checkout")
    d = json.loads((v9 / "config" / "standard_ou25_identity_aliases.json").read_text(encoding="utf-8"))
    assert CI.map_sha256(d["map"]) == CI.ALIAS_MAP_SHA256


def test_edited_map_fails_closed(tmp_path):
    d = json.loads(CI.ALIAS_MAP_PATH.read_text(encoding="utf-8"))
    d["map"]["League One"]["Some New Name"] = "Bolton"
    p = tmp_path / "m.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(CI.IdentityMapError):
        CI.load_alias_map(p)


@pytest.mark.parametrize("bad", [
    {"L": {"A": "B", "B": "A"}},        # cycle
    {"L": {"A": "B", "B": "C"}},        # chain
    {"L": {"A": "A"}},                  # self
])
def test_cycles_chains_and_self_aliases_are_rejected(bad):
    with pytest.raises(CI.IdentityMapError):
        CI.validate_alias_map(bad)


# ---------------------------------------------------------------- behaviour

AMAP = {"L1": {"Hull": "Hull City"}}


def test_two_spellings_of_one_match_become_one_fixture_and_one_team():
    raw = _fx([("2024-01-06", "L1", "Hull", "Leeds", 1, 0, 10),
               ("2024-01-06", "L1", "Hull City", "Leeds", 1, 0, np.nan),
               ("2024-01-13", "L1", "Leeds", "Hull City", 2, 2, 8)])
    out, rep = CI.canonicalise_fixtures(raw, AMAP)
    assert len(out) == 2 and rep["duplicate_rows_removed"] == 1
    assert set(out.home_team) | set(out.away_team) == {"Hull City", "Leeds"}
    # richest copy kept (the one WITH shots)
    assert out.loc[out.date == "2024-01-06", "home_shots"].iloc[0] == 10


def test_alias_is_league_scoped():
    raw = _fx([("2024-01-06", "L2", "Hull", "York", 1, 0, 1)])
    out, _ = CI.canonicalise_fixtures(raw, AMAP)
    assert out.home_team.iloc[0] == "Hull"


def test_score_conflict_is_quarantined_not_guessed():
    raw = _fx([("2024-01-06", "L1", "Hull", "Leeds", 1, 0, 1),
               ("2024-01-06", "L1", "Hull City", "Leeds", 2, 0, 1)])
    out, rep = CI.canonicalise_fixtures(raw, AMAP)
    assert out.empty and rep["quarantined_fixtures"] == 2


def test_affix_stage_unifies_within_league_only():
    raw = _fx([("2024-04-01", "SWE", "BK Hacken", "AIK", 1, 1, 1),
               ("2024-04-01", "SWE", "Hacken", "AIK", 1, 1, 1),
               ("2024-04-08", "SWE", "Hacken", "Malmo FF", 0, 2, 1),
               ("2024-04-08", "OTHER", "BK Hacken", "X", 0, 0, 1)])
    out, rep = CI.canonicalise_fixtures(raw, {})
    swe = out[out.league == "SWE"]
    assert len(swe) == 2 and set(swe.home_team) == {"Hacken"}
    assert out[out.league == "OTHER"].home_team.iloc[0] == "BK Hacken"


def test_no_two_different_clubs_collapse_in_reconciliation():
    raw = _fx([("2024-01-06", "L1", "Hull", "Leeds", 1, 0, 1),
               ("2024-01-06", "L1", "Hull City", "Leeds", 1, 0, 1),
               ("2024-01-06", "L1", "York", "Bury", 0, 0, 1)])
    out, rep = CI.canonicalise_fixtures(raw, AMAP)
    r = CI.reconcile(raw, out, rep, AMAP)
    assert r["same_day_team_collisions_before"] == 1
    assert r["same_day_team_collisions_after"] == 0
    assert r["collapsed_clubs"] == []
    bad = {"L1": {"Leeds": "Hull City"}}          # an alias joining two clubs that MEET
    assert CI.collapse_check(_fx([("2024-01-06", "L1", "Leeds", "Hull City", 1, 0, 1)]), bad)


def test_af_enrichment_never_expands_rows_and_is_league_scoped():
    fd = _fx([("2024-01-06", "L1", "Hull City", "Leeds", 1, 0, 1),
              ("2024-01-06", "L2", "Hull City", "Leeds", 3, 3, 1)])
    af = pd.DataFrame({"league": ["L1", "L1", "L2"], "date": pd.to_datetime(["2024-01-06"] * 3),
                       "home_team": ["Hull", "Hull City", "Hull City"],
                       "away_team": ["Leeds", "Leeds", "Leeds"],
                       "home_yellow": [2.0, 9.0, 4.0]})
    out, st = D._join_af_canonical(fd, af, AMAP)
    assert len(out) == len(fd)
    assert st["af_duplicate_keys_dropped"] == 1           # Hull -> Hull City duplicates a key
    assert out.set_index("league").loc["L2", "home_yellow"] == 4.0   # never borrowed across leagues


# ---------------------------------------------------------------- proof against v9's own code

def _v9_stage1(v9: Path):
    """Extract _AFFIX_RE, _norm_club and _canonicalise_clubs from v9's data_loader.py verbatim."""
    src = (v9 / "src" / "data_loader.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    want = {"_AFFIX_RE", "_norm_club", "_canonicalise_clubs"}
    parts = []
    for node in tree.body:
        name = (node.name if isinstance(node, ast.FunctionDef) else
                node.targets[0].id if isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name) else None)
        if name in want:
            parts.append(ast.get_source_segment(src, node))
    import logging
    ns = {"re": re, "pd": pd, "np": np, "unicodedata": unicodedata,
          "log": logging.getLogger("v9stage1")}
    exec("\n\n".join(parts), ns)                       # noqa: S102 - trusted local repo source
    return ns["_canonicalise_clubs"]


def _v9_identity_repair(v9: Path):
    spec = importlib.util.spec_from_file_location("v9_identity_repair", v9 / "src" / "identity_repair.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _compare(raw: pd.DataFrame, amap: dict, v9: Path):
    stage1 = _v9_stage1(v9)
    ir = _v9_identity_repair(v9)
    ref, _ = ir.canonicalise_and_dedupe(stage1(raw), amap, derive=False)
    mine, _ = CI.canonicalise_fixtures(raw, amap)
    cols = ["date", "league", "home_team", "away_team", "home_goals", "away_goals"]
    a = ref[cols].sort_values(cols).reset_index(drop=True)
    b = mine[cols].sort_values(cols).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_identical_to_v9_on_synthetic_frame():
    v9 = _v9_dir()
    if v9 is None:
        pytest.skip("no v9 checkout")
    raw = _fx([("2024-01-06", "L1", "Hull", "Leeds", 1, 0, 10),
               ("2024-01-06", "L1", "Hull City", "Leeds", 1, 0, np.nan),
               ("2024-01-07", "L1", "FC Bury", "York", 0, 0, 1),
               ("2024-01-07", "L1", "Bury", "York", 0, 0, 1),
               ("2024-01-08", "L1", "Hull", "York", 2, 0, 1),
               ("2024-01-08", "L1", "Hull City", "York", 3, 0, 1)])
    _compare(raw, AMAP, v9)


def test_identical_to_v9_on_real_history_sample():
    v9 = _v9_dir()
    p = v9 / "output" / "fd_history.parquet" if v9 else None
    if p is None or not p.exists():
        pytest.skip("no v9 fd_history")
    fd = pd.read_parquet(p)
    fd = fd[fd["league"].isin(["Sweden Allsvenskan", "Bundesliga 2", "League Two", "Ireland Premier Division"])]
    fd["date"] = pd.to_datetime(fd["date"], errors="coerce")
    fd = fd.dropna(subset=["date", "home_goals", "away_goals"])
    _compare(fd.reset_index(drop=True), CI.load_alias_map(), v9)
