"""Standard v9 forensic repair (owner brief 2026-10-28) — data-side tests.

Brief test numbers covered here: 11 (entry != closing), 12 (synthetic/constant side odds never in a
certified ROI), 13 (Std and NF side rows cannot silently pool), 14 (aliases cannot split rolling
history - identity side), 15 (fingerprint -> STALE), 16 (failed core workflow -> FAILED), 17 (old
Standard outputs unchanged and auditable), 18 (repaired experiments first-sight immutable), plus the
identity / provenance / price-label logic. Model-side tests 1-10 belong to the v9 recipe repair.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.studies.standard_repair import fingerprint as FP
from src.studies.standard_repair import identity as ID
from src.studies.standard_repair import prices as PR
from src.studies.standard_repair import provenance as PV
from src.studies.standard_repair import trusted as TR
from src.studies.standard_repair import v9r_registry as VR

ROOT = Path(__file__).resolve().parents[1]


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────
def _season(league, teams, start="2024-08-03", alias=None, dup_alias_share=1.0, seed=0):
    """Double round robin; optionally a second copy of each match where `alias` = {name: other spelling}."""
    rng = np.random.default_rng(seed)
    rows, d0 = [], pd.Timestamp(start)
    pairs = [(h, a) for h in teams for a in teams if h != a]
    rng.shuffle(pairs)
    per_day = len(teams) // 2
    day = 0
    while pairs:
        used, today = set(), []
        for p in list(pairs):
            if p[0] not in used and p[1] not in used:
                today.append(p)
                used |= set(p)
                pairs.remove(p)
            if len(today) == per_day:
                break
        for h, a in today:
            hg, ag = int(rng.integers(0, 4)), int(rng.integers(0, 4))
            rows.append({"league": league, "date": d0 + pd.Timedelta(days=7 * day), "home_team": h, "away_team": a,
                         "home_goals": hg, "away_goals": ag, "track": "standard"})
            if alias and (h in alias or a in alias) and rng.random() < dup_alias_share:
                rows.append({"league": league, "date": d0 + pd.Timedelta(days=7 * day),
                             "home_team": alias.get(h, h), "away_team": alias.get(a, a),
                             "home_goals": hg, "away_goals": ag, "track": "standard"})
        day += 1
    return pd.DataFrame(rows)


# ── identity ────────────────────────────────────────────────────────────────────────────────────
def test_identity_alias_is_derived_from_evidence_and_merges():
    teams = ["Hull", "Stoke", "Leeds", "Derby", "Wigan", "Bolton"]
    s = _season("Championship", teams, alias={"Hull": "Hull City"})
    aud = ID.audit(s)
    assert aud["same_day_collision_fixtures"] > 0                    # the split is visible
    res = ID.derive_aliases(s)
    assert res["map"]["Championship"] in ({"Hull City": "Hull"}, {"Hull": "Hull City"})
    fixed = ID.apply_aliases(s, res["map"]).drop_duplicates(["league", "date", "home_team", "away_team"])
    assert ID.audit(fixed)["same_day_collision_fixtures"] == 0


def test_identity_distinct_clubs_never_merged():
    """Two real clubs (they meet each other, play different matches on the same day) are never aliased."""
    teams = ["Sheffield Utd", "Sheffield Weds", "Leeds", "Derby"]
    s = _season("Championship", teams)
    res = ID.derive_aliases(s)
    assert res["map"] == {}


def test_identity_score_conflict_is_quarantined_not_guessed():
    s = pd.DataFrame([
        {"league": "L", "date": pd.Timestamp("2025-01-04"), "home_team": "A", "away_team": "B", "home_goals": 1, "away_goals": 0, "track": "standard"},
        {"league": "L", "date": pd.Timestamp("2025-01-04"), "home_team": "A", "away_team": "B FC", "home_goals": 2, "away_goals": 2, "track": "standard"},
        {"league": "L", "date": pd.Timestamp("2025-01-04"), "home_team": "C", "away_team": "D", "home_goals": 0, "away_goals": 0, "track": "standard"},
    ])
    aud = ID.audit(s)
    assert aud["score_conflicts"] == 1
    clean, q = ID.quarantine(s)
    assert len(q) == 2 and set(clean["home_team"]) == {"C"}


def test_aliases_cannot_split_rolling_history():
    """Brief test 14 (identity side): after the alias map, each club has ONE name, so a per-club
    rolling window sees every match the club played."""
    teams = ["Hull", "Stoke", "Leeds", "Derby"]
    s = _season("Championship", teams, alias={"Hull": "Hull City"}, dup_alias_share=0.5, seed=3)
    res = ID.derive_aliases(s)
    fixed = ID.apply_aliases(s, res["map"]).drop_duplicates(["league", "date", "home_team", "away_team"])
    names = set(fixed["home_team"]) | set(fixed["away_team"])
    assert not ({"Hull", "Hull City"} <= names)
    canon = "Hull" if "Hull" in names else "Hull City"
    n_matches = ((fixed["home_team"] == canon) | (fixed["away_team"] == canon)).sum()
    assert n_matches == 6                                           # 3 opponents x home/away


def test_rolling_order_leak_detects_alphabetical_league_order():
    """v9 sorts a club's rows by [team, league, date]: League One rows after Championship rows, so a
    club relegated LATER leaks its Championship future into its earlier League One window."""
    rows = []
    for i in range(6):   # 2024 in League One, 2025 in Championship (promoted)
        rows.append({"date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=7 * i), "league": "League One",
                     "home_team": "X", "away_team": f"o{i}", "track": "standard"})
        rows.append({"date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=7 * i), "league": "Championship",
                     "home_team": "X", "away_team": f"p{i}", "track": "standard"})
    r = ID.rolling_order_leak(pd.DataFrame(rows))
    assert r["per_league"]["League One"]["future"] >= 1
    assert r["per_league"]["Championship"]["future"] == 0


# ── provenance ──────────────────────────────────────────────────────────────────────────────────
def test_source_predictable_from_missingness():
    n = 400
    rng = np.random.default_rng(1)
    d = pd.DataFrame({"row_source": ["BACKTEST_ARCHIVE"] * n + ["FOOTBALL_DATA_ARCHIVE"] * n,
                      "season": ["2022/23"] * n + ["2023/24"] * n, "league": "L",
                      "f1": rng.normal(size=2 * n), "ht_home_goals": [np.nan] * n + list(rng.integers(0, 3, n))})
    r = PV.source_predictability(d, ["f1"])
    assert r["auc_missingness_all_inputs"] > 0.95 and r["verdict"] == "SOURCE_REGIME_DETECTABLE"
    d["ht_home_goals"] = 1.0
    assert PV.source_predictability(d, ["f1"])["verdict"] == "SOURCE_NOT_DETECTABLE"


# ── prices ──────────────────────────────────────────────────────────────────────────────────────
def _fd(**kw):
    base = {"league": "L", "date": pd.Timestamp("2025-02-01"), "home_team": "A", "away_team": "B", "file": "x"}
    for nm in ("AVG", "B365", "PIN", "BFE", "AVGC", "B365C", "PINC", "MAXC"):
        base[f"o_{nm}"], base[f"u_{nm}"] = np.nan, np.nan
    base.update(kw)
    return pd.DataFrame([base])


def _std(odds_over25, src="FOOTBALL_DATA"):
    return pd.DataFrame([{"league": "L", "date": pd.Timestamp("2025-02-01"), "home_team": "A", "away_team": "B",
                          "row_source": "FOOTBALL_DATA_ARCHIVE", "odds_over25": odds_over25, "odds_under25": 1.9,
                          "_ou25_src": src}])


def test_entry_is_never_a_closing_column():
    """Brief test 11: entry (pre-match) and closing are separate fields; a closing price never becomes
    an entry, even when it is the only price."""
    lab = PR.label_frame_ou25(_std(2.10), _fd(o_AVG=2.00, u_AVG=1.85, o_AVGC=2.10, u_AVGC=1.76))
    r = lab.iloc[0]
    assert r["entry_over25"] == 2.00 and r["entry_class"] == "FD_PREMATCH_APPROX"
    assert r["close_over25"] == 2.10 and r["close_class"] == "FD_CLOSING"
    assert r["frame_price_class"] == "FD_CLOSING" and not r["frame_price_usable_as_entry"]
    only_close = PR.label_frame_ou25(_std(2.10), _fd(o_AVGC=2.10, u_AVGC=1.76)).iloc[0]
    assert pd.isna(only_close["entry_over25"]) and only_close["entry_class"] is None


def test_fallback_and_synthetic_side_odds_never_certified():
    """Brief test 12."""
    df = pd.DataFrame({"odds": [1.85, 1.85, 1.91, 2.40, 1.40],
                       "won": [1, 1, 1, 1, 1],
                       "price_is_real": [False, True, True, True, False],
                       "price_source": ["FALLBACK_CONSTANT", "V9_CAPTURE", "PRO_BOOK_SNAPSHOT", "SYNTHETIC_MARKET_PROXY", "V9_CAPTURE"],
                       "price_class": ["FD_PREMATCH_APPROX", "BACKFILL_DATE_ONLY", "FIRST_SIGHT_SNAPSHOT", "FIRST_SIGHT_SNAPSHOT", "FIRST_SIGHT_SNAPSHOT"]})
    r = PR.certified_roi(df, "BTTS")
    assert r["n_certified"] == 1 and abs(r["roi"] - 0.91) < 1e-9          # only the timed 1.91
    assert PR.certified_roi(df.iloc[[0]], "BTTS")["status"] == "NOT_CERTIFIABLE"
    assert PR.is_fallback("OU15", [1.40, 1.41]).tolist() == [True, False]


def test_btts_first_half_filter_on_read():
    raw = pd.DataFrame({"market": ["btts_yes", "btts_yes", "btts_no", "btts_yes"], "odds": [1.9, 5.5, 3.6, 3.2]})
    kept, removed = PR.contamination_filter_btts(raw, "market", None, "odds")
    assert removed["odds"].tolist() == [5.5] and len(kept) == 3          # NO side and 3.20 itself kept
    pro = pd.DataFrame({"market": ["BTTS", "BTTS"], "side": ["YES", "NO"], "odds": [6.0, 6.0]})
    k2, r2 = PR.contamination_filter_btts(pro, "market", "side", "odds")
    assert len(r2) == 1 and k2["side"].tolist() == ["NO"]


def test_certified_t30_close_uses_locf_and_min_books():
    ko = pd.Timestamp("2026-10-01T15:00:00Z")
    rows = []
    for b in ("b1", "b2", "b3"):
        for side, o in (("OVER", 1.9), ("UNDER", 1.9)):        # posted at T-5h, unchanged (change-log)
            rows.append({"league": "L", "market": "OU25", "fixture_key": "f", "bookmaker": b, "side": side, "odds": o,
                         "snapshot_ts": (ko - pd.Timedelta(hours=5)).isoformat(), "minutes_to_kickoff": 300.0,
                         "is_post_kickoff": False})
    # one book moves at T-20m -> a capture ran inside the window; the other books carry forward
    rows.append({"league": "L", "market": "OU25", "fixture_key": "f", "bookmaker": "b1", "side": "OVER", "odds": 1.85,
                 "snapshot_ts": (ko - pd.Timedelta(minutes=20)).isoformat(), "minutes_to_kickoff": 20.0, "is_post_kickoff": False})
    agg, _ = PR.forward_coverage(pd.DataFrame(rows), {"L"})
    assert int(agg.loc[0, "certified_t30_close"]) == 1
    agg2, _ = PR.forward_coverage(pd.DataFrame(rows[:-1]), {"L"})           # nothing inside T-30m
    assert int(agg2.loc[0, "certified_t30_close"]) == 0


# ── track isolation ─────────────────────────────────────────────────────────────────────────────
def test_std_and_nf_side_rows_cannot_silently_pool():
    """Brief test 13 (data side)."""
    d = pd.DataFrame({"track": ["standard", "new_format", "standard"], "btts": [1, 0, 1]})
    assert len(VR.select_track(d, "standard")) == 2
    with pytest.raises(ValueError):
        VR.assert_single_track(d, "standard")
    with pytest.raises(ValueError):
        VR.select_track(d.drop(columns=["track"]), "standard")


# ── fingerprints / staleness ────────────────────────────────────────────────────────────────────
def _frame(n=10, start="2026-09-01"):
    return pd.DataFrame({"date": pd.date_range(start, periods=n, freq="D"), "league": "L", "home_team": [f"h{i}" for i in range(n)],
                         "away_team": [f"a{i}" for i in range(n)], "home_goals": 1, "away_goals": 0, "track": "standard"})


def test_fingerprint_stale_on_v9_data_or_code_change():
    """Brief test 15."""
    man = {"inputs_sha256": {"src/feature_engineering.py": "fe1", "src/team_names.py": "t1", "src/data_loader.py": "d1",
                             "output/backtest_all_leagues.csv": "arch1"}, "serving_feature_cols": ["x"], "live_season_start": 2026}
    fr = _frame()
    stamped = FP.current(fr, man)
    assert FP.compare(stamped, FP.current(fr, man, data_cutoff=stamped["data_cutoff"]))["status"] == "CURRENT"
    # new fixtures after the cutoff only -> BEHIND, not STALE
    grown = pd.concat([fr, _frame(3, "2026-10-01")], ignore_index=True)
    assert FP.compare(stamped, FP.current(grown, man, data_cutoff=stamped["data_cutoff"]))["status"] == "BEHIND"
    # a historical row changed -> STALE
    edited = fr.copy()
    edited.loc[0, "home_goals"] = 3
    c = FP.compare(stamped, FP.current(edited, man, data_cutoff=stamped["data_cutoff"]))
    assert c["status"] == "STALE" and "frame_hash_at_cutoff" in c["mismatched"]
    # v9 code (feature builder / canonicaliser) changed -> STALE
    man2 = json.loads(json.dumps(man))
    man2["inputs_sha256"]["src/data_loader.py"] = "d2"
    c2 = FP.compare(stamped, FP.current(fr, man2, data_cutoff=stamped["data_cutoff"]))
    assert c2["status"] == "STALE" and "team_canon_version" in c2["mismatched"]
    # recipe / imputer change -> STALE; missing stamp -> STALE
    assert FP.compare(stamped, FP.current(fr, man, data_cutoff=stamped["data_cutoff"], imputer_version="persisted_train_only"))["status"] == "STALE"
    assert FP.compare(None, stamped)["status"] == "STALE"


def test_failed_core_workflow_returns_failed(tmp_path, monkeypatch):
    """Brief test 16: scientific steps carry no `|| echo` / `|| true`; a missing benchmark raises
    (non-zero exit); a failed job marks everything STALE."""
    wf = yaml.safe_load((ROOT / ".github/workflows/pro_standard_repair.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["repair"]["steps"]
    sci = [s for s in steps if s.get("name", "").startswith(("Forensic", "Weekly PRE_REPAIR"))]
    assert len(sci) == 2
    # the heavy phase-2 benchmark (manual, GitHub Actions only): every step that runs science must fail
    # loudly, it never commits to main, and an incomplete arm set fails the run
    bw = yaml.safe_load((ROOT / ".github/workflows/pro_standard_repair_benchmark.yml").read_text(encoding="utf-8"))
    on = bw.get("on", bw.get(True))
    assert set(on) == {"workflow_dispatch"}
    for job in bw["jobs"].values():
        for st in job["steps"]:
            run = st.get("run", "")
            if "python" in run and any(k in run for k in ("standard_repair", "standard_feature_audit")):
                assert "|| echo" not in run and "|| true" not in run and "continue-on-error" not in st, st.get("name")
    text = (ROOT / ".github/workflows/pro_standard_repair_benchmark.yml").read_text(encoding="utf-8")
    assert "main|master" in text and 'b["status"] == "COMPLETE"' in text
    for s in sci:
        assert "|| echo" not in s["run"] and "|| true" not in s["run"], s["name"]
        assert "continue-on-error" not in s
    for s in steps:
        if "checkout" in str(s.get("uses", "")) and "repository" not in s.get("with", {}):
            assert s["with"]["ref"] == "main"
    from src.studies.standard_repair import forensic as F
    monkeypatch.setattr(F, "CANON", tmp_path / "nope")
    with pytest.raises(F.IntegrityError):
        F.load_benchmark_frame()
    monkeypatch.setattr(F, "OUT", tmp_path)
    monkeypatch.setattr(F, "HEALTH", tmp_path / "repair_health.json")
    h = F.write_health()
    assert h["STANDARD_REPAIR_BENCHMARK"] == "STALE"
    # a run that failed after the rebuild still ends STALE
    monkeypatch.setenv("JOB_STATUS", "failure")
    fr = _frame()
    (tmp_path / "nope").mkdir()
    fr.to_parquet(tmp_path / "nope" / "frame_benchmark.parquet")
    (tmp_path / "nope" / "frame_manifest.json").write_text("{}", encoding="utf-8")
    now = FP.current(fr, {})
    (tmp_path / "data_quality.json").write_text(json.dumps(FP.stamp_obj({"status": "PASS"}, now)), encoding="utf-8")
    h2 = F.write_health()
    assert h2["STANDARD_REPAIR_BENCHMARK"] == "STALE" and h2["artifacts"]["data_quality.json"]["status"] == "STALE"


def test_old_standard_outputs_frozen_and_auditable():
    """Brief test 17."""
    from src.studies.standard_repair import pre_repair
    man = json.loads((pre_repair.FROZEN / "MANIFEST.json").read_text(encoding="utf-8"))
    assert man["status"] == "PRE_REPAIR" and "NOT FINAL" in man["note"]
    names = {Path(e["frozen_copy"]).name for e in man["files"]}
    assert {"results.json", "ablation.json", "registry__experiments.json"} <= names
    assert pre_repair.verify() == []
    assert man["legacy_v9_backtest"].get("status") in (None, "LEGACY_BACKTEST_UNVERIFIED")


def test_repaired_experiments_first_sight_immutable(tmp_path):
    """Brief test 18."""
    reg, fs = tmp_path / "reg.json", tmp_path / "fs.csv"
    spec = {"experiment_id": "STD-V9R-TEST-OU25-2026Q4", "league": "League One", "market": "OU25", "side": "OVER",
            "model_version": "m1", "feature_manifest": "f1", "imputer": "i1", "calibrator": "c1",
            "selection_rule": "none", "market_source": "pro_book_odds_snapshots", "min_n": 150,
            "min_matchdays": 10, "primary_metric": "dLL_vs_market", "frozen_at": "2026-10-28T00:00:00Z"}
    VR.register(spec, reg)
    VR.register(dict(spec), reg)                                   # identical: no-op
    with pytest.raises(VR.Immutable):
        VR.register(dict(spec, selection_rule="top3"), reg)
    row = pd.DataFrame([{"experiment_id": spec["experiment_id"], "fixture_key": "k1", "market": "OU25", "side": "OVER",
                         "first_seen_at": "2026-10-29T10:00:00Z", "p_model": 0.55}])
    assert VR.append_first_sight(row, fs, reg) == 1
    later = row.assign(first_seen_at="2026-10-30T10:00:00Z", p_model=0.70)
    assert VR.append_first_sight(later, fs, reg) == 0              # a later look is not a first sight
    assert pd.read_csv(fs)["p_model"].tolist() == [0.55]
    with pytest.raises(VR.Immutable):
        VR.append_first_sight(row.assign(fixture_key="k2", first_seen_at="2026-10-01T00:00:00Z"), fs, reg)


def test_trusted_from_and_forward_phase():
    assert TR.trusted_from("STANDARD_LIVE_SETTLEMENT_AND_ENTRY_PRICE") >= "2026-09-01"
    assert TR.trusted_from("STANDARD_SERVED_MODEL_INPUTS").startswith("2026-09-24")
    assert TR.table()["STANDARD_HISTORICAL_SIDE_MARKET_ROI"]["trusted_from"].startswith("NEVER")
    assert TR.forward_phase("2026-10-01", None) == "PRE_REPAIR_FORWARD"
    assert TR.forward_phase("2026-11-02", "2026-11-01T00:00:00Z") == "POST_REPAIR_FORWARD"


# ── genuine BTTS prices (owner follow-up 2026-10-28) ──────────────────────────────────────────
def _capture_csv(tmp_path):
    rows = [
        # historical backfill, two-sided, 00Z
        ("2025-01-04", "2025-01-04T00:00:00Z", "2025-01-04", "", "Serie B", "Hellas Verona vs Bari", "btts_yes", 1.90),
        ("2025-01-04", "2025-01-04T00:00:00Z", "2025-01-04", "", "Serie B", "Hellas Verona vs Bari", "btts_no", 1.90),
        # one-sided only -> dropped
        ("2025-01-05", "2025-01-05T00:00:00Z", "2025-01-05", "", "Serie B", "Pisa vs Como", "btts_yes", 1.80),
        # forward, first-half mislabel (YES 5.5) -> removed, so not two-sided
        ("2026-08-10", "2026-08-10T09:00:00Z", "2026-08-10", "2026-08-10T18:00:00Z", "Serie B", "Pisa vs Bari", "btts_yes", 5.50),
        ("2026-08-10", "2026-08-10T09:00:00Z", "2026-08-10", "2026-08-10T18:00:00Z", "Serie B", "Pisa vs Bari", "btts_no", 1.20),
        # forward after TRUSTED_FROM: earliest pre-kickoff quote per side is the entry
        ("2026-09-06", "2026-09-06T08:00:00Z", "2026-09-06", "2026-09-06T14:00:00Z", "Serie B", "Bari vs Pisa", "btts_yes", 2.00),
        ("2026-09-06", "2026-09-06T08:00:00Z", "2026-09-06", "2026-09-06T14:00:00Z", "Serie B", "Bari vs Pisa", "btts_no", 1.80),
        ("2026-09-06", "2026-09-06T13:00:00Z", "2026-09-06", "2026-09-06T14:00:00Z", "Serie B", "Bari vs Pisa", "btts_yes", 1.70),
    ]
    p = tmp_path / "cap.csv"
    pd.DataFrame(rows, columns=["snapshot_date", "snapshot_ts", "match_date", "kickoff_utc", "league", "match",
                                "market", "odds"]).to_csv(p, index=False)
    return p


def test_btts_real_quotes_classes_and_filters(tmp_path):
    from src.studies.standard_repair import btts_real as BR
    q, meta = BR.load_quotes(_capture_csv(tmp_path))
    assert meta["btts_1h_rows_removed"] == 1
    assert set(q["match"]) == {"Hellas Verona vs Bari", "Bari vs Pisa"}          # one-sided / 1H rows gone
    h = q.set_index("match")
    assert h.loc["Hellas Verona vs Bari", "price_class"] == BR.HIST_CLASS
    assert h.loc["Bari vs Pisa", "price_class"] == BR.FWD_CLASS
    assert h.loc["Bari vs Pisa", "btts_yes"] == 2.00                             # earliest, not the later 1.70


def test_btts_real_attach_matches_and_labels(tmp_path):
    from src.studies.standard_repair import btts_real as BR
    q, _ = BR.load_quotes(_capture_csv(tmp_path))
    std = pd.DataFrame({"league": "Serie B", "date": pd.to_datetime(["2025-01-04", "2026-09-06", "2026-09-13"]),
                        "home_team": ["Verona", "Bari", "Como"], "away_team": ["Bari", "Pisa", "Pisa"]})
    amap = {"Serie B": {"Hellas Verona": "Verona"}}
    resolve = lambda nm, cands: nm if nm in cands else None
    s, rep = BR.attach(std, amap, quotes=q, resolve=resolve)
    assert rep["matched"] == 2 and rep["match_rate"] == 1.0
    assert abs(s.loc[0, "pm_BTTS_REAL"] - 0.5) < 1e-9 and s.loc[0, "btts_price_class"] == BR.HIST_CLASS
    assert pd.isna(s.loc[2, "pm_BTTS_REAL"]) and pd.isna(s.loc[2, "market_class_BTTS_REAL"])
    assert s.loc[1, "market_class_BTTS_REAL"] == BR.REAL_CLASS


def test_btts_real_money_uses_real_side_price():
    from src.studies.standard_repair.benchmark import _side_money
    g = pd.DataFrame({"y": [1, 0, 1, 0], "pm": [0.5] * 4, "week": ["w1", "w1", "w2", "w2"],
                      "btts_yes_odds": [2.0, 2.0, 1.8, 1.8], "btts_no_odds": [1.8, 1.8, 2.0, 2.0]})
    yes = _side_money(g, True, "BTTS_REAL")
    assert yes["roi_n"] == 4 and abs(yes["roi"] - ((1.0 - 1 + 0.8 - 1) / 4)) < 1e-9 and yes["clv_prob_pp"] is None
