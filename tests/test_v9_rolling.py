"""v9 rolling odds logs (v9 src/rolling_store.py, 2026-10-22): Pro's full-history readers must see
archive + live, and a plain (never-rolled) file must read exactly as before."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data import v9_source as v9  # noqa: E402

REL = "output/book_odds_snapshots.csv"


def _rows(md, n=2):
    return pd.DataFrame([{"snapshot_ts": f"{md}T1{i}:00:00Z", "league": "L", "match_date": md,
                          "kickoff_utc": f"{md}T19:00:00Z", "match": "A vs B", "bookmaker": "bk",
                          "market": "OU25", "side": "OVER", "odds": 1.9 + i / 10}
                         for i in range(n)])


def test_plain_file_reads_exactly_like_read_csv(tmp_path):
    (tmp_path / "output").mkdir()
    d = pd.concat([_rows("2026-10-30"), _rows("2026-10-30")])      # exact dups kept, as before
    d.to_csv(tmp_path / REL, index=False)
    got = v9.read_v9_all(REL, tmp_path)
    pd.testing.assert_frame_equal(got, pd.read_csv(tmp_path / REL))


def test_archive_plus_live_is_the_full_history(tmp_path):
    adir = tmp_path / v9.archive_rel_dir(REL)
    adir.mkdir(parents=True)
    _rows("2026-10-01").to_csv(adir / "2026-10-01.csv", index=False)
    _rows("2026-10-02").to_csv(adir / "2026-10-02.csv", index=False)
    (adir / "notes.csv").write_text("x\n1\n")                     # non-date files ignored
    pd.concat([_rows("2026-10-30"), _rows("2026-10-02")]) \
        .to_csv(tmp_path / REL, index=False)                     # a union-merge duplicate
    got = v9.read_v9_all(REL, tmp_path)
    assert len(got) == 6
    assert sorted(got["match_date"].unique()) == ["2026-10-01", "2026-10-02", "2026-10-30"]


def test_archive_only_and_missing(tmp_path, monkeypatch):
    assert v9.read_v9_all(REL, tmp_path).empty
    adir = tmp_path / v9.archive_rel_dir(REL)
    adir.mkdir(parents=True)
    _rows("2026-10-01").to_csv(adir / "2026-10-01.csv", index=False)
    assert len(v9.read_v9_all(REL, tmp_path)) == 2
    monkeypatch.setattr(v9.cfg, "V9_LOCAL", tmp_path)
    got = v9.fetch_csv_all(REL, required=False)
    assert len(got) == 2 and list(got["odds"]) == ["1.9", "2.0"]   # str, like fetch_csv


def test_snapshot_coverage_reads_the_archive(tmp_path, monkeypatch):
    from src.monitoring import snapshot_coverage as sc
    adir = tmp_path / v9.archive_rel_dir(REL)
    adir.mkdir(parents=True)
    _rows("2026-10-01", 3).to_csv(adir / "2026-10-01.csv", index=False)
    (tmp_path / "output" / "book_odds_snapshots.csv").write_text(
        ",".join(_rows("2026-10-01").columns) + "\n")
    monkeypatch.setattr(sc.cfg, "V9_LOCAL", tmp_path)
    assert sc.measure(REL, ("match", "market", "side"))["rows"] == 3


def test_archive_dir_naming_matches_v9():
    assert v9.archive_rel_dir("output/player_prop_odds_history.csv") == \
        "output/player_prop_odds_history_archive"
    assert v9.archive_rel_dir(REL) == "output/book_odds_snapshots_archive"
