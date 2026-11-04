"""fixture_key v2 (Data Truth round 2): canonical league + v9 club identity, the v1 -> v2 migration,
and the identity rules that ride on it (team_form, player_v3 prop identity).

    python -m pytest tests/test_fixture_key_v2.py      (needs V9_LOCAL -> a wowza-betting checkout)
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg  # noqa: E402

pytestmark = pytest.mark.skipif(not (cfg.V9_LOCAL / "src" / "team_names.py").exists(),
                                reason="needs V9_LOCAL (v9's registry and resolver)")

from src.data import entities as ent  # noqa: E402
from src.data import fixture_key_v2 as fk2  # noqa: E402
from src.pipelines import migrate_fixture_key_v2 as mig  # noqa: E402


# ── the key ───────────────────────────────────────────────────────────────────────────────────

def test_two_spellings_of_one_club_give_one_key():
    # Spellings v9's resolver PROVES are one club: the alias store (Bayern Munich = Bayern München)
    # and the identity-token tier with club-form words removed (Freiburg = SC Freiburg).
    a = fk2.key_and_status("Bundesliga", "2026-10-03", "Bayern Munich", "Freiburg")
    b = fk2.key_and_status("Bundesliga", "2026-10-03T16:30:00Z", "FC Bayern München",
                           "SC Freiburg")
    assert a == b and a[1] == fk2.RESOLVED and a[0] is not None
    # v1 gave two keys for the same fixture - the reason v2 exists
    assert (ent.fixture_key_v1("Bundesliga", "2026-10-03", "Bayern Munich", "Freiburg")
            != ent.fixture_key_v1("Bundesliga", "2026-10-03", "FC Bayern München", "SC Freiburg"))


def test_unproven_spelling_is_not_merged():
    """Owner rule 2026-11-02 (v9 team_names: proven club identity only). The token-subset tier is
    gone, so a bare 'Dortmund' is NOT placed on 'Borussia Dortmund' without an alias: the row is
    CLUB_UNRESOLVED and keeps its own spelling, a different key from the canonical one."""
    k1, s1 = fk2.key_and_status("Bundesliga", "2026-10-03", "Bayern Munich", "Dortmund")
    k2, s2 = fk2.key_and_status("Bundesliga", "2026-10-03", "Bayern Munich", "Borussia Dortmund")
    assert s1 == fk2.CLUB_UNRESOLVED and s2 == fk2.RESOLVED and k1 is not None and k1 != k2


def test_entities_fixture_key_is_v2():
    assert ent.fixture_key("Bundesliga", "2026-10-03", "Bayern Munich", "Dortmund") == \
        fk2.fixture_key("Bundesliga", "2026-10-03", "Bayern Munich", "Dortmund")


def test_unknown_league_and_bad_date_give_no_key():
    assert fk2.key_and_status("Not A League", "2026-10-03", "A", "B") == (None, fk2.LEAGUE_UNKNOWN)
    assert fk2.key_and_status("Bundesliga", "03/10/2026", "Bayern Munich", "Dortmund") == \
        (None, fk2.DATE_UNPARSEABLE)
    assert fk2.key_and_status("Bundesliga", "2026-10-03", "", "Dortmund") == (None, fk2.CLUB_MISSING)


def test_unresolved_club_keeps_its_own_spelling_and_is_flagged():
    k1, s1 = fk2.key_and_status("Bundesliga", "2026-10-03", "Zzyzx Athletic", "Dortmund")
    k2, _ = fk2.key_and_status("Bundesliga", "2026-10-03", "Qwerty Rovers", "Dortmund")
    assert s1 == fk2.CLUB_UNRESOLVED and k1 is not None and k1 != k2   # never merged onto another


def test_explicit_date_formats_and_utc():
    assert fk2.match_day("2026-08-20T23:30:00-03:00") == "2026-08-20"         # day as written
    assert fk2.to_utc_iso("2026-08-20T23:30:00-03:00") == "2026-08-21T02:30:00Z"
    assert fk2.to_utc_iso("2026-08-20 15:00:00") == "2026-08-20T15:00:00Z"
    assert fk2.to_utc_iso("nan") is None and fk2.to_utc_iso("") is None
    assert fk2.parse_when("20 Aug 2026") is None                                # never inferred


def test_vocabulary_is_hash_pinned(tmp_path):
    import json
    d = json.loads(fk2.VOCAB_PATH.read_text(encoding="utf-8"))
    d["leagues"]["Bundesliga"] = d["leagues"]["Bundesliga"] + ["Invented FC"]
    p = tmp_path / "v.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(fk2.VocabularyError):
        fk2.vocabulary(p)


def test_add_fixture_key_writes_old_key_and_status():
    d = pd.DataFrame({"league": ["Bundesliga", "Nowhere"], "match_date": ["2026-10-03"] * 2,
                      "home_team": ["Bayern Munich", "A"], "away_team": ["Borussia Dortmund", "B"]})
    out = ent.add_fixture_key(d)
    assert list(out["fixture_key_status"]) == [fk2.RESOLVED, fk2.LEAGUE_UNKNOWN]
    assert out["fixture_key"].iloc[1] is None
    assert out["old_fixture_key"].iloc[0] == ent.fixture_key_v1("Bundesliga", "2026-10-03",
                                                                "Bayern Munich", "Borussia Dortmund")
    assert set(ent.KEY_META) <= set(out.columns)


# ── the migration: old and new rows still join ─────────────────────────────────────────────────

def _v1(lg, d, h, a):
    return ent.fixture_key_v1(lg, d, h, a)


def _fixture_frames():
    fx = pd.DataFrame({"league": ["Bundesliga", "Bundesliga"], "match_date": ["2026-10-03"] * 2,
                       "home_team": ["Bayern Munich", "FC Bayern München"],
                       "away_team": ["Freiburg", "SC Freiburg"]})
    fx["fixture_key"] = [_v1(*r) for r in fx[["league", "match_date", "home_team", "away_team"]].itertuples(index=False)]
    st = pd.DataFrame({"fixture_key": [fx["fixture_key"].iloc[0], fx["fixture_key"].iloc[1], "deadbeefdeadbeef"],
                       "league": ["Bundesliga"] * 3, "match_date": ["2026-10-03"] * 3,
                       "market": ["OU25"] * 3, "side": ["OVER"] * 3, "result": ["WIN", "WIN", "LOSS"]})
    return fx, st


def test_migration_rekeys_and_old_and_new_rows_join():
    fx, st = _fixture_frames()
    m: dict = {}
    k = fk2.add_keys(fx[["league", "match_date", "home_team", "away_team"]], log_unresolved=False)
    from collections import defaultdict
    m = defaultdict(dict)
    mig._add_to_map(m, fx["fixture_key"], k)
    fx2 = mig.migrate_frame(fx, "fixtures", m)
    st2 = mig.migrate_frame(st, "settlements", m)
    # both spellings now share one key, and the old keys are kept
    assert fx2["fixture_key"].nunique() == 1
    assert list(fx2["old_fixture_key"]) == list(fx["fixture_key"])
    # a migrated settlement joins the migrated fixture on the NEW key ...
    j_new = st2.merge(fx2[["fixture_key"]].drop_duplicates(), on="fixture_key")
    assert len(j_new) == 2
    # ... and the old key still joins old artifacts that only hold v1
    j_old = st2.merge(fx[["fixture_key"]].rename(columns={"fixture_key": "old_fixture_key"}),
                      on="old_fixture_key")
    assert len(j_old) == 2
    # a v1 key that no named row explains gets NO key, never the nearest one
    bad = st2[st2["old_fixture_key"] == "deadbeefdeadbeef"]
    assert bad["fixture_key"].isna().all() and (bad["fixture_key_status"] == "V1_UNMAPPED").all()


def test_ambiguous_v1_key_is_refused():
    m = {"aaaa": {"k1": fk2.RESOLVED, "k2": fk2.RESOLVED}}
    assert mig._status_from_map("aaaa", m) == (None, "V1_AMBIGUOUS")


def test_migration_is_rerunnable():
    fx, _ = _fixture_frames()
    from collections import defaultdict
    m = defaultdict(dict)
    mig._add_to_map(m, fx["fixture_key"], fk2.add_keys(fx, log_unresolved=False))
    once = mig.migrate_frame(fx, "fixtures", m)
    twice = mig.migrate_frame(once, "fixtures", m)
    pd.testing.assert_frame_equal(once, twice)


def test_combo_ids_are_reprefixed_and_old_ids_kept():
    fx, _ = _fixture_frames()
    v1 = fx["fixture_key"].iloc[0]
    cl = pd.DataFrame({"combo_id": [f"{v1}|abc123"], "fixture_key": [v1], "leg_index": [1]})
    from collections import defaultdict
    m = defaultdict(dict)
    mig._add_to_map(m, fx["fixture_key"], fk2.add_keys(fx, log_unresolved=False))
    out = mig.migrate_frame(cl, "combo_legs", m)
    new = out["fixture_key"].iloc[0]
    assert out["combo_id"].iloc[0] == f"{new}|abc123"
    assert out["old_combo_id"].iloc[0] == f"{v1}|abc123"


def test_paper_row_id_follows_the_new_key():
    from src.pipelines.paper_1x2 import _row_id
    fx, _ = _fixture_frames()
    r = fx.iloc[[0]].assign(row_id=_row_id(fx["fixture_key"].iloc[0], "", "", ""))
    out = mig.migrate_record(r, "paper_1x2.csv", {})
    assert out["row_id"].iloc[0] == _row_id(out["fixture_key"].iloc[0], "", "", "")
    assert out["old_row_id"].iloc[0] == r["row_id"].iloc[0]


def test_canonical_dedupe_drops_restored_copies_and_keeps_conflicts():
    base = {"fixture_key": "k", "market": "OU25", "side": "OVER", "bookmaker": "b",
            "snapshot_ts": "2026-10-01T10:00:00Z", "odds": 2.0}
    d = pd.DataFrame([{**base, "run_id": "r1", "ingested_at": "t1"},
                      {**base, "run_id": "r2", "ingested_at": "t2"},          # same observation
                      {**base, "odds": 2.1, "run_id": "r3", "ingested_at": "t3"},  # conflict
                      {**base, "fixture_key": None, "run_id": "r4", "ingested_at": "t4"},
                      {**base, "fixture_key": None, "run_id": "r5", "ingested_at": "t5"}])
    drop, conf = mig.dedupe_canonical(d, "book_odds_snapshots")
    assert list(drop) == [False, True, False, False, False]    # keyless rows never grain-deduped
    assert len(conf) == 2


# ── the migrated repo data ─────────────────────────────────────────────────────────────────────

def _read(table, cols):
    files = sorted((cfg.DATA_DIR / "season_2026_27" / table).glob("dt=*/run=*.parquet"))
    if not files:
        pytest.skip(f"no {table} data")
    return pd.concat([pd.read_parquet(f, columns=cols) for f in files], ignore_index=True)


def test_stored_warehouse_is_v2_and_old_new_keys_agree():
    fx = _read("fixtures", ["fixture_key", "old_fixture_key", "fixture_key_version"])
    sg = _read("signals", ["fixture_key", "old_fixture_key"])
    assert (fx["fixture_key_version"] == fk2.KEY_VERSION).all()
    # one old key -> one new key, in every table
    for d in (fx, sg):
        x = d.dropna(subset=["fixture_key"]).drop_duplicates()
        assert not x["old_fixture_key"].duplicated().any()
    # signals and fixtures join on the new key exactly where they joined on the old one
    old_pairs = set(sg["old_fixture_key"]) & set(fx["old_fixture_key"])
    new_pairs = set(sg["fixture_key"].dropna()) & set(fx["fixture_key"].dropna())
    o2n = dict(zip(fx["old_fixture_key"], fx["fixture_key"]))
    assert {o2n[k] for k in old_pairs if o2n.get(k) is not None} <= new_pairs


# ── team_form identity ─────────────────────────────────────────────────────────────────────────

def test_team_form_keys_by_id_then_canonical_club():
    from src.features import team_form as tf
    t = pd.DataFrame({"league": ["Bundesliga"] * 6,
                      "team": ["Bayern Munich", "FC Bayern München", "Freiburg", "Zzyzx Athletic",
                               "SC Freiburg", "Dortmund"],
                      "team_id": ["157", None, None, None, None, None]})
    k = tf.team_keys(t)
    assert k.iloc[0] == "id:157"
    assert k.iloc[1] == "id:157"                  # same canonical club, its one id
    assert k.iloc[2].startswith("c:Bundesliga|")  # no id anywhere: canonical club within league
    assert k.iloc[3].startswith("u:")             # unresolved: own spelling, never another club
    assert k.iloc[4] == k.iloc[2]                 # two spellings, one canonical club
    assert k.iloc[5].startswith("u:")             # unproven spelling (owner 2026-11-02): not merged


def test_team_ids_attach_by_fixture_id_and_refuse_conflicts():
    from src.data.team_ids import attach_team_ids
    stats = pd.DataFrame({"fixture_id": ["1", "2", "3"], "home_team_id": [None, None, "9"],
                          "away_team_id": [None, None, "8"]})
    frames = {"scout_results": pd.DataFrame({"fixture_id": [1, 2, 3], "home_id": [10, 20, 99],
                                             "away_id": [11, 21, 98]}),
              "live_odds_snapshots": pd.DataFrame({"fixture_id": ["2"], "home_team_id": ["22"],
                                                   "away_team_id": ["21"]})}
    out = attach_team_ids(stats, frames)
    assert list(out["home_team_id"]) == ["10", None, "9"]     # 2: sources disagree -> refused
    assert list(out["away_team_id"]) == ["11", None, "8"]     # 3: an existing id is never overwritten


# ── player_v3 prop identity ────────────────────────────────────────────────────────────────────

def test_ambiguous_initial_surname_is_refused():
    from src.player_v3.market import ambiguous_name_groups
    h = pd.DataFrame({"match_date": ["d"] * 4, "league": ["L"] * 4,
                      "k": ["j|smith", "j|smith", "a|jones", "a|jones"],
                      "player": ["James Smith", "John Smith", "A. Jones", "Adam Jones"]})
    amb = ambiguous_name_groups(h, ["match_date", "league", "k"])
    assert list(amb) == [True, True, False, False]


def test_settle_uses_player_id_when_the_price_has_it():
    from src.player_v3 import market as M
    X = pd.DataFrame({"player_id": [7, 8], "fixture_id": [1, 1],
                      "date": pd.to_datetime(["2026-10-03"] * 2), "league": ["Bundesliga"] * 2,
                      "player_name": ["John Smith", "James Smith"], "position": ["F", "F"],
                      "target_goals": [1, 0]})
    items = pd.DataFrame({"match_date": ["2026-10-03", "2026-10-03"], "league": ["Bundesliga"] * 2,
                          "k": ["id:8", "j|smith"], "market": ["goals", "goals"]})
    m = M.settle(items, X)
    # the id row settles to player 8; the name row is refused (two J. Smiths that day)
    assert list(m["player_id"]) == [8] and list(m["y"]) == [0]
