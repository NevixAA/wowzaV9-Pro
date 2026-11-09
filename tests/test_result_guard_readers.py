"""Every reader of stored RESULTS goes through the kickoff guard (owner 2026-11-09).

API-Football has marked return fixtures FT with the first leg's score; three such rows sit in
team_match_stats (output/corrections/team_match_stats_unplayed.csv). result_guard.drop_unplayed /
played_team_results remove them. A module that reads team_match_stats results without the guard
would train or settle on a match that has not been played, so this test fails on it.
"""
import re
from pathlib import Path

import pandas as pd

from src.data import result_guard as rg

ROOT = Path(__file__).resolve().parents[1]

#: files that mention team_match_stats but do not read RESULTS from it, with the reason
NOT_RESULT_READERS = {
    "src/data/season_store.py": "the store itself",
    "src/data/result_guard.py": "the guard itself",
    "src/pipelines/team_stats.py": "the writer; uses unplayed_mask for its own skip list",
    "src/pipelines/data_quality.py": "audits raw tables, flags rows, settles nothing",
    "src/pipelines/fixture_key_v2_vocab.py": "club-name vocabulary only",
    "src/pipelines/migrate_fixture_key_v2.py": "re-keys rows in place, reads no score",
    "src/analytics/model_lineage.py": "counts partitions for lineage",
    "src/monitoring/manifest.py": "table description only",
    "src/schemas.py": "schema only",
    "src/data/fixture_key_v2.py": "docstring mention",
    "src/data/team_ids.py": "attaches club ids, reads no score",
}

READ = re.compile(r"read\(\s*[\"']team_match_stats[\"']\s*\)|[\"']team_match_stats[\"']\s*\)\s*\.rglob|"
                  r"for t in \(\s*[\"']team_match_stats[\"']|[\"']team_match_stats[\"']\s*/\s*[\"']\*\*")
GUARD = re.compile(r"drop_unplayed|played_team_results")


def test_every_result_reader_applies_the_kickoff_guard():
    offenders = []
    for f in sorted((ROOT / "src").rglob("*.py")):
        rel = f.relative_to(ROOT).as_posix()
        if rel in NOT_RESULT_READERS:
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        if READ.search(t) and not GUARD.search(t):
            offenders.append(rel)
    assert not offenders, f"read team_match_stats results without result_guard: {offenders}"


def test_the_guard_drops_a_score_stored_before_kickoff():
    d = pd.DataFrame({"fixture_id": ["a", "b"], "home_goals": [1, 0], "away_goals": [0, 1],
                      "kickoff_utc": ["2026-10-25T15:00:00+00:00", "2026-11-28T17:00:00+00:00"],
                      "observed_at": ["2026-10-25T19:19:02Z", "2026-10-25T19:19:02Z"]})
    kept = rg.drop_unplayed(d, "t", now=pd.Timestamp("2026-11-09", tz="UTC"))
    assert list(kept["fixture_id"]) == ["a"]


def test_corrections_file_lists_the_three_known_rows():
    c = pd.read_csv(ROOT / "output" / "corrections" / "team_match_stats_unplayed.csv",
                    dtype={"fixture_id": str})
    assert set(c["fixture_id"]) == {"1555431", "1555438", "1565640"}
    assert (c["status"] == "EXCLUDED_NOT_PLAYED").all()
