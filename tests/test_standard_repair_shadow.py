"""STD-V9R-SHADOW-2026Q4 forward shadow — integrity tests (small, synthetic, no network, no v9).

Covers: frozen registration, first-sight immutability (append-only, never rewritten), no post-kickoff
rows, no rows before registration, arms scored on identical rows, model version recorded and the
ledger immutable, POST_REPAIR_FORWARD label, synthetic / thin prices never in certified ROI / CLV,
change-log LOCF consensus, certified-close rule, and that the frozen MKT_RESID arms reproduce the
Phase-2 benchmark's candidates() exactly.
"""
import json

import numpy as np
import pandas as pd
import pytest

from src.studies.standard_repair import shadow as S
from src.studies.standard_repair import shadow_market as MK
from src.studies.standard_repair import shadow_models as SM
from src.studies.standard_repair import shadow_registry as R

NOW = pd.Timestamp("2026-11-03T12:00:00Z")
REG = R.load_registration()


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────
def _board(n=2, ko_hours=48):
    rows = []
    for i in range(n):
        ko = NOW + pd.Timedelta(hours=ko_hours + i)
        rows.append({"league": "Championship", "date": str(ko.date()), "home_team": f"Home{i} FC",
                     "away_team": f"Away{i} FC", "kickoff_utc": ko.strftime("%Y-%m-%d %H:%M:%S"),
                     "p_over25": 0.55, "p_btts": 0.52, "p_over15": 0.75, "generated_at": "2026-11-03T10:00:00Z",
                     "model_version": "v9-std-x", "model_version_btts": "v9-btts-x", "model_version_over15": "v9-o15-x"})
    return S.board_rows(pd.DataFrame(rows), REG["leagues"], NOW)


def _feats(board, no_form=False, resid=True):
    f = pd.DataFrame({"row_key": board["row_key"], "p_V9_REPAIRED_over25": 0.53, "p_V9_REPAIRED_btts": 0.5,
                      "p_V9_REPAIRED_over15": 0.74, "history_team_home": board["home_team"],
                      "history_team_away": board["away_team"], "no_form_data": no_form})
    f["p_MKT_RESID_LR"] = 0.51 if resid else np.nan
    f["p_MKT_RESID_HGB"] = 0.52
    return f


def _quotes(rk, market, books=4, ts=NOW - pd.Timedelta(hours=1), first=1.9, other=1.95):
    a, b = MK.FIRST_SIDE[market]
    rows = []
    for k in range(books):
        rows.append({"source": "ODDSAPI", "book": f"oddsapi:b{k}", "ts": ts, "market": market, "side": a, "odds": first})
        rows.append({"source": "ODDSAPI", "book": f"oddsapi:b{k}", "ts": ts, "market": market, "side": b, "odds": other})
    return pd.DataFrame(rows).assign(row_key=rk)


def _mkt(board, books=4):
    out = {}
    for rk in board["row_key"]:
        for m in REG["markets"]:
            out[(rk, m)] = MK.consensus(_quotes(rk, m, books), m, NOW)
    return out


CTX = {"model_version": "STDSHADOW-20261102-abcd1234", "v9_code_commit": "c0de", "v9_data_commit": "da7a"}


def _cands(board=None, **kw):
    board = _board() if board is None else board
    return S.build_candidates(board, _feats(board, **kw), _mkt(board), REG, NOW, CTX)


# ── registration / ledger ───────────────────────────────────────────────────────────────────────
def test_registration_is_frozen(tmp_path):
    assert REG["phase"] == "POST_REPAIR_FORWARD" and REG["experiment_id"] == "STD-V9R-SHADOW-2026Q4"
    bad = dict(REG, leagues=REG["leagues"][:3])
    p = tmp_path / "reg.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(R.RegistrationError):
        R.load_registration(p, aliases=None)


def test_mkt_resid_feature_manifest_matches_registration_and_benchmark():
    from src.studies.standard_repair.benchmark import GROUPS
    assert SM.GROUPS == GROUPS
    assert REG["frozen_inputs"]["feature_manifest"]["MKT_RESID"]["columns"] == [c for g in SM.GROUPS for c in SM.GROUPS[g]]


def _entry(v="STDSHADOW-20261102-aaaa0000", trained="2026-11-02T03:00:00+00:00"):
    return {"model_version": v, "trained_at": trained, "training_cutoff": "2026-11-02", "v9_commit": "c0de",
            "release_tag": "std-shadow-x", "assets": {"a.pkl": {"sha256": "0" * 64, "bytes": 1}},
            "feature_manifest": {}, "libs": {"sklearn": "1.9.1"}, "recipe_versions": {}}


def test_ledger_versions_are_immutable(tmp_path):
    led = tmp_path / "ledger.json"
    R.append_version(_entry(), led)
    with pytest.raises(R.RegistrationError):
        R.append_version(_entry(), led)                       # same id again
    R.append_version(_entry("STDSHADOW-20261109-bbbb1111", "2026-11-09T03:00:00+00:00"), led)
    assert R.active_version("2026-11-05T00:00:00Z", led)["model_version"] == "STDSHADOW-20261102-aaaa0000"
    assert R.active_version("2026-11-10T00:00:00Z", led)["model_version"] == "STDSHADOW-20261109-bbbb1111"
    assert R.active_version("2026-11-01T00:00:00Z", led) is None
    d = json.loads(led.read_text(encoding="utf-8"))
    d["versions"][0]["training_cutoff"] = "2026-12-31"        # silent edit of an old version
    led.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(R.RegistrationError):
        R.load_ledger(led)


def test_payload_hash_mismatch_refused(tmp_path):
    (tmp_path / "a.pkl").write_bytes(b"x")
    with pytest.raises(R.RegistrationError):
        R.verify_assets(_entry(), tmp_path)


# ── first sight ─────────────────────────────────────────────────────────────────────────────────
def test_first_sight_append_only_and_immutable(tmp_path):
    fs = tmp_path / "fs.csv"
    c1 = _cands()
    new = S.append_first_sight(c1, REG, fs)
    assert len(new) == len(c1) == 6                           # 2 fixtures x 3 markets
    before = fs.read_bytes()
    c2 = c1.copy()
    c2["p_CURRENT_V9_SERVED"] = 0.99                          # a later sighting with a changed probability
    c2["scored_at"] = (NOW + pd.Timedelta(hours=3)).isoformat()
    assert S.append_first_sight(c2, REG, fs).empty
    assert fs.read_bytes() == before                          # nothing rewritten
    b3 = _board(3)
    S.append_first_sight(_cands(b3), REG, fs)
    after = fs.read_bytes()
    assert after.startswith(before) and len(after) > len(before)
    d = pd.read_csv(fs)
    assert d["row_id"].is_unique and len(d) == 9
    assert (d.loc[d["row_id"].isin(c1["row_id"]), "p_CURRENT_V9_SERVED"] != 0.99).all()


def test_no_post_kickoff_rows(tmp_path):
    b = _board(ko_hours=-1)                                   # kicked off an hour ago
    assert b.empty                                            # board_rows drops it
    c = _cands()
    c["kickoff_utc"] = (NOW - pd.Timedelta(minutes=5)).isoformat()
    with pytest.raises(S.Immutable):
        S.append_first_sight(c, REG, tmp_path / "fs.csv")


def test_rows_before_registration_refused(tmp_path):
    c = _cands()
    c["scored_at"] = "2026-10-28T11:00:00+00:00"              # before registered_at 11:45Z
    with pytest.raises(S.Immutable):
        S.append_first_sight(c, REG, tmp_path / "fs.csv")


def test_arms_scored_on_identical_rows(tmp_path):
    c = _cands(resid=False)                                   # MKT_RESID_LR missing for OU25
    ou = c[c["market"] == "OU25"]
    assert ou["status"].str.startswith("INCOMPLETE:ARM_MISSING").all()
    new = S.append_first_sight(c, REG, tmp_path / "fs.csv")
    assert set(new["market"]) == {"BTTS", "OU15"}             # OU25 waits until every arm exists
    bad = _cands()
    bad.loc[bad["market"] == "OU25", "p_V9_REPAIRED"] = np.nan  # COMPLETE but an arm missing
    with pytest.raises(S.Immutable):
        S.append_first_sight(bad, REG, tmp_path / "fs2.csv")


def test_no_form_and_stale_board_not_first_sighted():
    assert _cands(no_form=True)["status"].eq("INCOMPLETE:NO_FORM_DATA").all()
    b = _board()
    b["generated_at"] = "2026-11-01T00:00:00Z"
    c = S.build_candidates(b, _feats(b), _mkt(b), REG, NOW, CTX)
    assert c["status"].eq("INCOMPLETE:STALE_BOARD").all()


def test_model_version_and_phase_recorded(tmp_path):
    fs = tmp_path / "fs.csv"
    S.append_first_sight(_cands(), REG, fs)
    d = pd.read_csv(fs)
    assert (d["model_version"] == CTX["model_version"]).all()
    assert (d["phase"] == "POST_REPAIR_FORWARD").all() and (d["experiment_id"] == "STD-V9R-SHADOW-2026Q4").all()
    assert d["v9_served_model_version"].notna().all()


# ── prices ──────────────────────────────────────────────────────────────────────────────────────
def test_thin_market_is_not_genuine():
    b = _board(1)
    c = S.build_candidates(b, _feats(b), {(b["row_key"][0], m): MK.consensus(_quotes(b["row_key"][0], m, books=2), m, NOW)
                                          for m in REG["markets"]}, REG, NOW, CTX)
    assert c["status"].eq("INCOMPLETE:NO_GENUINE_PRICE").all()


def test_locf_consensus_uses_change_log():
    t0 = NOW - pd.Timedelta(days=2)
    q = pd.concat([_quotes("k", "OU25", books=2, ts=t0, first=2.0, other=1.85),        # quoted once, unchanged since
                   _quotes("k", "OU25", books=1, ts=NOW - pd.Timedelta(hours=1), first=1.8, other=2.05).assign(book="oddsapi:late")])
    c = MK.consensus(q, "OU25", NOW)
    assert c["n_books"] == 3 and c["price_is_real"]
    assert MK.consensus(q, "OU25", t0 - pd.Timedelta(minutes=1))["n_books"] == 0      # nothing before the first quote


def test_close_certification():
    ko = NOW
    fresh = _quotes("k", "OU25", books=3, ts=ko - pd.Timedelta(minutes=10))
    stale = _quotes("k", "OU25", books=3, ts=ko - pd.Timedelta(hours=5))
    post = _quotes("k", "OU25", books=3, ts=ko + pd.Timedelta(minutes=5), first=5.0, other=1.1)
    assert MK.closing(pd.concat([fresh, post]), "OU25", ko)["close_status"] == "CERTIFIED_T30"
    assert MK.closing(stale, "OU25", ko)["close_status"] == "UNCERTIFIED_STALE"
    assert MK.closing(post, "OU25", ko)["close_status"] == "NO_CLOSE"                   # post-kickoff never a close


def test_synthetic_or_unreal_price_never_in_certified_roi_clv():
    g = pd.DataFrame({"p_V9_REPAIRED": [0.6] * 30, "p_MARKET": [0.5] * 30, "y": [1.0] * 30,
                      "entry_odds_first": [2.0] * 30, "entry_odds_other": [2.0] * 30, "p_close": [0.55] * 30,
                      "close_status": ["CERTIFIED_T30"] * 30, "week": ["2026-W45"] * 30,
                      "price_is_real": [False] * 30, "market_class": ["SYNTHETIC_MARKET_PROXY"] * 30})
    m = S.money(g, "V9_REPAIRED", "OU25")
    assert m["roi_n"] == 0 and m["clv_n"] == 0 and m["roi"] is None
    g2 = g.assign(price_is_real=True, market_class="GENUINE_FORWARD_TWO_SIDED")
    m2 = S.money(g2, "V9_REPAIRED", "OU25")
    assert m2["roi_n"] == 30 and m2["roi"] == pytest.approx(1.0) and m2["clv_pp"] == pytest.approx(5.0)
    g3 = g2.assign(close_status="UNCERTIFIED_STALE")
    assert S.money(g3, "V9_REPAIRED", "OU25")["clv_n"] == 0


# ── frozen arms == benchmark arms ───────────────────────────────────────────────────────────────
def _synthetic_frame(n=2400, seed=3):
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"date": pd.Timestamp("2023-01-02") + pd.to_timedelta(np.sort(rng.integers(0, 640, n)), unit="D"),
                      "league": rng.choice(["Championship", "League One", "Serie B"], n)})
    for g in SM.GROUPS.values():
        for c in g:
            if c not in ("form_gap", "env_rate"):
                d[c] = rng.normal(1.3, 0.4, n)
    d.loc[rng.random(n) < 0.05, "home_shots_last5"] = np.nan
    d["pm_OU25"] = np.clip(rng.normal(0.52, 0.07, n), 0.2, 0.85)
    d["y_OU25"] = (rng.random(n) < d["pm_OU25"] + 0.02 * (d["home_scored_last5"] - 1.3)).astype(float)
    return d


def test_frozen_resid_arms_reproduce_benchmark_candidates():
    from src.studies.standard_repair import benchmark as B
    d = _synthetic_frame()
    d["form_pois_OU25"] = SM.form_pois(d)
    ref = B.candidates(d.copy(), "OU25", arms=("MKT_RESID_LR", "MKT_RESID_HGB"))
    b0 = pd.Timestamp(B.EVAL_START)
    x = d.copy()
    x["env_rate"] = SM.env_rate_history(x, "y_OU25")
    x = SM.add_derived(x)
    tr = x[(x["date"] < b0)]
    te = x[(x["date"] >= b0) & (x["date"] < b0 + pd.offsets.QuarterBegin(startingMonth=1))]
    cols = SM.feature_columns(x)
    for arm in SM.RESID_ARMS:
        got = SM.predict_resid(SM.fit_resid(tr, arm, cols), te)
        assert np.allclose(got, ref.loc[te.index, arm].to_numpy(), atol=1e-10), arm


def test_env_rate_asof_matches_history_and_is_batch_invariant():
    d = _synthetic_frame(800)
    hist = d[d["date"] < "2024-06-01"]
    up = d[d["date"] >= "2024-06-01"].head(5)[["league", "date"]].reset_index(drop=True)
    got = SM.env_rate_asof(hist, up, "y_OU25")
    # batch invariance: scoring a fixture alone or with others gives the same value
    first = up.iloc[[0]]
    assert got.iloc[0] == pytest.approx(SM.env_rate_asof(hist, first, "y_OU25").iloc[0])
    lg_hist = hist[hist["league"] == up.at[0, "league"]].sort_values("date")
    assert got.iloc[0] == pytest.approx(lg_hist["y_OU25"].tail(80).mean())


# ── settle + report smoke ──────────────────────────────────────────────────────────────────────
def test_settle_and_report_end_to_end(tmp_path):
    fs = tmp_path / "fs.csv"
    S.append_first_sight(_cands(), REG, fs)
    d = pd.read_csv(fs)
    res = pd.DataFrame({"league": "Championship", "date": d["match_date"].iloc[0], "home_team": d["history_home"].iloc[0],
                        "away_team": d["history_away"].iloc[0], "home_goals": 2, "away_goals": 1}, index=[0])
    later = NOW + pd.Timedelta(days=4)
    q = pd.concat([_quotes(rk, m, ts=later - pd.Timedelta(days=2, minutes=10)) for rk in d["fixture_key"].unique()
                   for m in REG["markets"]])
    st = S.settle_rows(d, pd.DataFrame(), res, q, later)
    one = st[st["fixture_key"] == d["fixture_key"].iloc[0]]
    assert (one["settle_status"] == "SETTLED").all()
    assert one.set_index("market")["y"].to_dict() == {"OU25": 1.0, "BTTS": 1.0, "OU15": 1.0}
    assert (st.loc[st["fixture_key"] != d["fixture_key"].iloc[0], "settle_status"] == "PENDING").all()
    # a SETTLED row is carried forward unchanged even if a later result source disagrees
    st2 = S.settle_rows(d, st, res.assign(home_goals=0, away_goals=0), q, later + pd.Timedelta(days=1))
    assert st2.set_index("row_id").loc[one["row_id"], "y"].tolist() == one["y"].tolist()
    rep = S.build_report(d, st2, REG, None, later)
    assert rep["status"] == "COLLECTING" and rep["phase"] == "POST_REPAIR_FORWARD"
    assert rep["primary"]["H1"]["decision"] == "COLLECTING" and rep["primary"]["H1"]["n"] == 1
    assert rep["coverage"]["settled"] == 3
