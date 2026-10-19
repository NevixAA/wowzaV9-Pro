"""Two-sided prop consensus: pairing never crosses lines, players, books or time tolerance."""
import pandas as pd
import pytest

from src.player_v3 import consensus as C


def _q(rows):
    d = pd.DataFrame(rows, columns=["snapshot_ts", "match_date", "league", "match", "player", "market",
                                    "side", "point", "bookmaker", "odds", "source"])
    d["ts"] = pd.to_datetime(d["snapshot_ts"], utc=True)
    d["side"] = d["side"].str.lower()
    d["odds"] = d["odds"].astype(float)
    d["point_key"] = d["point"].astype(str).replace({"nan": "", "None": ""})
    d["player_ok"] = ~d["player"].astype(str).str.contains(C._BROKEN)
    return d


T = "2026-10-20T10:00:00Z"
T5 = "2026-10-20T10:05:00Z"
T30 = "2026-10-20T10:30:00Z"


def test_devig_by_hand():
    d = _q([[T, "2026-10-21", "L", "A vs B", "John Smith", "sot", "over", 0.5, "BookX", 1.80, "s"],
            [T, "2026-10-21", "L", "A vs B", "John Smith", "sot", "under", 0.5, "BookX", 2.00, "s"]])
    p = C.pair(d)
    assert len(p) == 1
    ro, ru = 1 / 1.8, 1 / 2.0
    assert p["fair_pos"].iloc[0] == pytest.approx(ro / (ro + ru))
    assert p["overround"].iloc[0] == pytest.approx(ro + ru)


def test_different_lines_never_paired():
    d = _q([[T, "2026-10-21", "L", "A vs B", "John Smith", "sot", "over", 0.5, "BookX", 1.8, "s"],
            [T, "2026-10-21", "L", "A vs B", "John Smith", "sot", "under", 1.5, "BookX", 2.0, "s"]])
    assert C.pair(d).empty


def test_different_players_and_books_never_paired():
    d = _q([[T, "2026-10-21", "L", "A vs B", "John Smith", "sot", "over", 0.5, "BookX", 1.8, "s"],
            [T, "2026-10-21", "L", "A vs B", "Jon Smyth", "sot", "under", 0.5, "BookX", 2.0, "s"],
            [T, "2026-10-21", "L", "A vs B", "John Smith", "sot", "under", 0.5, "BookY", 2.0, "s"]])
    assert C.pair(d).empty


def test_time_tolerance_is_bounded():
    ok = _q([[T, "2026-10-21", "L", "A vs B", "John Smith", "goals", "yes", None, "Pinnacle", 3.0, "s"],
             [T5, "2026-10-21", "L", "A vs B", "John Smith", "goals", "no", None, "Pinnacle", 1.4, "s"]])
    far = _q([[T, "2026-10-21", "L", "A vs B", "John Smith", "goals", "yes", None, "Pinnacle", 3.0, "s"],
              [T30, "2026-10-21", "L", "A vs B", "John Smith", "goals", "no", None, "Pinnacle", 1.4, "s"]])
    assert len(C.pair(ok)) == 1 and C.pair(far).empty


def test_corrupted_names_excluded():
    d = _q([[T, "2026-10-21", "L", "A vs B", "Isaac Og e", "goals", "yes", None, "Bet365", 3.0, "s"],
            [T, "2026-10-21", "L", "A vs B", "Isaac Og e", "goals", "no", None, "Bet365", 1.4, "s"]])
    assert C.pair(d).empty


def test_v3_never_enables_real_staking(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "OUT", tmp_path)
    monkeypatch.setattr(C, "REG_DIR", tmp_path / "reg")
    monkeypatch.setattr(C, "load_quotes", lambda root=None: _q([]))
    r = C.run()
    assert r["SAFE_TO_PROMOTE_V3"] == "NO" and r["PLAYER_PROP_REAL_STAKING_ENABLED"] == "NO"
