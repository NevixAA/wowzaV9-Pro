"""R2 finding 26: league-aware season calendar, fail-closed on unknown leagues.

    python -m pytest tests/test_season_calendar.py -q
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data import season_calendar as SC  # noqa: E402
from src.prediction_lab import data as D  # noqa: E402
from src.prediction_lab import features as F  # noqa: E402


@pytest.mark.parametrize("league,when,label,api", [
    ("Championship", "2026-06-30", "2025/26", "2025"),
    ("Championship", "2026-07-01", "2026/27", "2026"),        # winter rollover
    ("USA MLS", "2025-12-31", "2025", "2025"),
    ("USA MLS", "2026-01-01", "2026", "2026"),                # calendar rollover
    ("USA MLS", "2026-08-15", "2026", "2026"),                # Aug-Jul bucket would say 2026/27
    ("Sweden Allsvenskan", "2026-03-30", "2026", "2026"),     # bucket would say 2025/26
    ("Japan J-League", "2025-11-01", "2025", "2025"),
    ("Japan J-League", "2026-03-01", "2026", "2026"),         # spring special tournament
    ("Japan J-League", "2026-11-01", "2026/27", "2027"),      # autumn-spring, END-year API id
    ("Brazil Serie A", "2021-02-10", "2020", "2020"),         # COVID-extended 2020 campaign
    ("Brazil Serie A", "2021-06-10", "2021", "2021"),
    ("Argentina Primera Division", "2020-02-01", "2019/20", "2019"),
    ("Argentina Primera Division", "2022-07-15", "2022", "2022"),
    ("Mexico Liga MX", "2027-02-01", "2026/27", "2026"),
])
def test_labels_and_api_seasons(league, when, label, api):
    r = SC.season_for(league, when)
    assert r.status == SC.RESOLVED
    assert r.label == label and r.api_football_season == api


def test_unknown_league_fails_closed():
    r = SC.season_for("Mystery League", "2026-11-01")
    assert r.status == SC.SEASON_UNKNOWN and r.label is None and r.api_football_season is None
    near = SC.season_for("USA  MLS", "2026-11-01")            # near-name variant: not guessed
    assert near.status == SC.SEASON_UNKNOWN


def test_aliases_resolve_to_one_canonical_league():
    assert SC.canonical_league("Danish Superliga") == "Denmark Superliga"
    assert SC.canonical_league("Austria Bundesliga") == "Austrian Bundesliga"


def test_every_lab_league_is_in_the_calendar_with_the_same_model_type():
    cal = SC.calendar()["leagues"]
    lab = D.STANDARD_FORMAT_LEAGUES | D.NEW_FORMAT_LEAGUES
    assert lab == set(cal)
    for lg in lab:
        assert cal[lg]["model_type"] == D.model_type_for_league(lg)


def _v9_config() -> Path | None:
    for c in (os.getenv("V9_LOCAL", ""), str(ROOT.parent / "v9")):
        if c and (Path(c) / "config.py").exists():
            return Path(c) / "config.py"
    return None


def _literal(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        tgt = (node.target if isinstance(node, ast.AnnAssign) else
               node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(tgt, ast.Name) and tgt.id == name:
            return ast.literal_eval(node.value)
    raise KeyError(name)


def test_api_season_matches_v9_config_today():
    """v9's API_FOOTBALL_SEASONS is hand-rolled; the calendar must agree with it on the date v9's
    values were last verified (2026-11-01). A disagreement means one of them is wrong."""
    p = _v9_config()
    if p is None:
        pytest.skip("no v9 checkout")
    v9 = _literal(p, "API_FOOTBALL_SEASONS")
    v9_std = _literal(p, "STANDARD_FORMAT_LEAGUES")
    v9_nf = _literal(p, "NEW_FORMAT_LEAGUES")
    assert set(D.STANDARD_FORMAT_LEAGUES) == set(v9_std)
    assert set(D.NEW_FORMAT_LEAGUES) == set(v9_nf)
    checked = 0
    for lg, season in v9.items():
        r = SC.season_for(lg, "2026-11-01")
        if r.status == SC.SEASON_UNKNOWN:
            assert lg not in (v9_std | v9_nf), lg            # only non-model leagues may be absent
            continue
        assert r.api_football_season == season, (lg, r.api_football_season, season)
        checked += 1
    # 28 model leagues (plus the Danish alias) agree. Five Standard TRAINING leagues have no
    # API_FOOTBALL_SEASONS entry in v9 and fall back to API_SEASON="2025" there -- a v9 gap
    # (R2 finding 6, owned by the registry workstream), not a calendar disagreement. The calendar
    # resolves them to "2026".
    missing = sorted((v9_std | v9_nf) - set(v9))
    assert missing == ["Belgian First Division A", "Dutch Eredivisie", "Portuguese Primeira Liga",
                       "Scottish Premiership", "Turkish Super Lig"] or not missing
    for lg in missing:
        assert SC.api_football_season(lg, "2026-11-01") == "2026"
    assert checked + len(missing) >= 32


def test_league_season_frame_preserves_rows_and_flags_unknown():
    lg = pd.Series(["USA MLS", "Nope", "Championship", "USA MLS"], index=[10, 11, 12, 13])
    dt = pd.Series(pd.to_datetime(["2026-08-01", "2026-08-01", "2026-08-01", "2026-08-01"]),
                   index=lg.index)
    f = SC.league_season_frame(lg, dt)
    assert list(f.index) == [10, 11, 12, 13]
    assert f.loc[10, "league_season"] == "2026" and f.loc[12, "league_season"] == "2026/27"
    assert f.loc[11, "season_status"] == SC.SEASON_UNKNOWN and pd.isna(f.loc[11, "league_season"])


def test_season_key_never_guesses_for_unknown_and_keeps_bucket_for_uncalendared():
    d = pd.DataFrame({"season_label": ["2026/27", "2026/27", "2026/27"],
                      "league_season": ["2026", None, None],
                      "season_status": [SC.RESOLVED, SC.SEASON_UNKNOWN, None]})
    k = F.season_key(d)
    assert k.iloc[0] == "2026" and pd.isna(k.iloc[1]) and k.iloc[2] == "2026/27"


def test_early_season_family_stays_inactive():
    assert "EARLY" not in F.FOOTBALL_FAMILIES
    assert F.EARLY_STATUS == "INACTIVE_PENDING_REBUILD"
