"""H-EDGE2 v1 forward evaluator: frozen registration, forward rows only, no interim effect sizes,
config-hash guard, never CONFIRMED. Also: the H-GATE family_class marking is additive only."""
import json

import numpy as np
import pandas as pd

from src.studies import candidate_forward as CF
from src.studies import edge2_forward as E

REG = json.loads(E.REG.read_text(encoding="utf-8"))
HASHES = {"config_sha256_lf": REG["engine"]["config_sha256_lf"], "code_sha256_lf": REG["engine"]["code_sha256_lf"]}


def _row(i, pts, ko, market="OU25", track="new_format", src="MEDIAN_TWO_SIDED_BOOKS", state="NO_BET",
         side="OVER", pdec=0.55, pmkt=0.54):
    return {"selection_engine_version": "market_edge_v2", "prediction_ts": pts, "fixture_id": f"f{i}",
            "match_date": ko[:10], "kickoff_utc": ko, "league": "L", "home_team": f"H{i}", "away_team": f"A{i}",
            "model_type": track, "market": market, "decision_state": state, "side": side,
            "p_decision": pdec, "p_market_fair": pmkt, "market_source": src}


def _results(rows, goals):
    return pd.DataFrame([{"league": "L", "match_date": r["match_date"], "home_team": r["home_team"],
                          "away_team": r["away_team"], "home_goals": g[0], "away_goals": g[1],
                          "md": pd.Timestamp(r["match_date"])} for r, g in zip(rows, goals)])


def _ident(name, cands):
    return name if name in cands else None


def test_registration_is_frozen_and_pinned():
    assert E.sha256_lf(E.REG.read_bytes()) == E.REGISTRATION_SHA256
    assert REG["confirmed_assignable_here"] is False
    assert REG["forward_start"] == "2026-10-26T00:00:00Z" and REG["registered_at"] == "2026-10-25"
    assert pd.Timestamp(REG["forward_start"]) > pd.Timestamp(REG["registered_at"], tz="UTC")   # never backdated
    ids = [h["id"] for h in REG["hypotheses"]]
    assert {"H-EDGE2-NF-OU25-01", "H-EDGE2-NF-BTTS-01", "H-EDGE2-NF-O15-01", "H-EDGE2-STD-OU25-01"} <= set(ids)
    assert REG["engine"]["config_status_at_registration"] == "UNVALIDATED_DEFAULTS"


def test_pre_registration_rows_never_count():
    rows = [_row(1, "2026-10-25T09:25:00Z", "2026-10-30T20:00:00Z"),
            _row(2, "2026-10-26T09:25:00Z", "2026-10-30T20:00:00Z")]
    out = E.evaluate(REG, pd.DataFrame(rows), hashes=HASHES, now=pd.Timestamp("2026-11-01T00:00Z"))
    h = next(r for r in out if r["id"] == "H-EDGE2-NF-OU25-01")
    assert h["PRE_REGISTRATION_NOT_COUNTED"] == 1 and h["forward"]["logged"] == 1
    assert h["status"] == "ACCRUING" and h["metrics"] is None          # no interim effect size


def test_post_kickoff_rows_and_one_sided_rows_are_not_scored():
    rows = [_row(1, "2026-10-31T21:00:00Z", "2026-10-30T20:00:00Z"),               # logged after kickoff
            _row(2, "2026-10-27T09:00:00Z", "2026-10-30T20:00:00Z", src="ONE_SIDED")]
    res = _results(rows, [(2, 1), (2, 1)])
    out = E.evaluate(REG, pd.DataFrame(rows), res, _ident, HASHES, pd.Timestamp("2026-11-02T00:00Z"))
    h = next(r for r in out if r["id"] == "H-EDGE2-NF-OU25-01")
    assert h["forward"]["logged"] == 1 and h["forward"]["two_sided"] == 0


def test_registered_before_forward_start_and_blocked_on_config_drift():
    out = E.evaluate(REG, pd.DataFrame(), hashes=HASHES, now=pd.Timestamp("2026-10-25T12:00Z"))
    assert {r["status"] for r in out} == {"REGISTERED"}
    bad = dict(HASHES, config_sha256_lf="0" * 64)
    rows = [_row(1, "2026-10-27T09:00:00Z", "2026-10-30T20:00:00Z")]
    out = E.evaluate(REG, pd.DataFrame(rows), hashes=bad, now=pd.Timestamp("2026-11-01T00:00Z"))
    assert {r["status"] for r in out} == {"BLOCKED_CONFIG_CHANGED"}


def test_eligible_needs_n_and_gameweeks_and_never_confirms():
    rng = np.random.default_rng(3)
    rows, goals = [], []
    for i in range(420):
        ko = (pd.Timestamp("2026-10-27T18:00Z") + pd.Timedelta(days=int(i // 7))).strftime("%Y-%m-%dT%H:%M:%SZ")
        pts = (pd.Timestamp(ko) - pd.Timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append(_row(i, pts, ko, pdec=0.5, pmkt=0.5))
        goals.append((2, 1) if rng.uniform() < 0.5 else (0, 0))
    res = _results(rows, goals)
    out = E.evaluate(REG, pd.DataFrame(rows), res, _ident, HASHES, pd.Timestamp("2027-06-01T00:00Z"))
    h = next(r for r in out if r["id"] == "H-EDGE2-NF-OU25-01")
    assert h["forward"]["settled_two_sided"] == 420 and h["forward"]["gameweeks"] >= 8
    assert h["status"] == "ELIGIBLE_FOR_REVIEW"
    assert h["metrics"]["ll_diff_mean"] == 0.0                          # identical probabilities
    assert h["criteria_met"]["PROBABILITY_LAYER_SUPPORTED"] is False
    assert all(r["status"] != "CONFIRMED" for r in out)


def test_side_a_conversion():
    s = pd.DataFrame([_row(1, "a", "b", side="UNDER", pdec=0.6, pmkt=0.58), _row(2, "a", "b", market="BTTS", side="NO",
                                                                                  pdec=0.45, pmkt=0.44)])
    assert np.allclose(E.side_a(s, "p_decision"), [0.4, 0.55])


def test_hgate_entries_marked_additively_and_evaluator_unchanged():
    reg = json.loads(CF.REG.read_text(encoding="utf-8"))
    assert all(h["family_class"] == "LEGACY_RAW_EDGE_FORWARD_TEST" for h in reg["hypotheses"])
    assert all(h["forward_start"].startswith("2026-10-21") for h in reg["hypotheses"])
    stripped = {**reg, "hypotheses": [{k: v for k, v in h.items() if k != "family_class"} for h in reg["hypotheses"]]}
    stripped.pop("family_class_note")
    shadow = pd.DataFrame([{"fixture_id": "a", "generated_at": "2026-10-22T10:00:00Z", "kickoff": "2026-10-25T20:00:00Z",
                            "league": h["league"], "model_type": h["model_type"],
                            "market": CF.MARKET.get(h["market"], h["market"]), "side": "OVER", "raw_edge": 30,
                            "result": "WIN", "flat_pnl": 1.0, "clv": 1.0} for h in reg["hypotheses"]])
    assert json.dumps(CF.evaluate(reg, shadow), default=str) == json.dumps(CF.evaluate(stripped, shadow), default=str)


def test_descriptive_is_counts_only_and_secondary_waits_for_eligibility():
    """Dashboard report fields (owner brief 2026-10-26 part D): counts are published while ACCRUING,
    outcome metrics (secondary) only at ELIGIBLE_FOR_REVIEW - the registry's interim policy."""
    rows = [_row(1, "2026-10-26T09:00:00Z", "2026-10-30T20:00:00Z", state="QUALIFIED", side="OVER"),
            _row(2, "2026-10-26T09:00:00Z", "2026-10-31T20:00:00Z", state="NO_BET", side="UNDER"),
            _row(3, "2026-10-26T09:00:00Z", "2026-10-31T20:00:00Z", state="STRONG", side="UNDER",
                 src="ONE_SIDED")]
    for r, o in zip(rows, (2.1, 1.8, 3.4)):
        r["odds"] = o
    res = _results(rows, [(2, 1), (0, 0), (1, 1)])
    out = E.evaluate(REG, pd.DataFrame(rows), res, _ident, HASHES, pd.Timestamp("2026-11-02T00:00Z"))
    h = next(r for r in out if r["id"] == "H-EDGE2-NF-OU25-01")
    assert h["status"] == "ACCRUING" and h["metrics"] is None and h["secondary"] is None
    d = h["descriptive"]
    assert d["matchdays"] == 2                          # settled two-sided rows on 30/10 and 31/10
    assert d["selection_rate"] == round(2 / 3, 3) and d["sides_selected"] == {"OVER": 1, "UNDER": 1}
    assert d["odds_bands_selected"]["(1.9, 2.2]"] == 1 and d["odds_bands_selected"]["(3.0, 99.0]"] == 1
    assert d["top_league"] == "L" and d["top_league_share"] == 1.0 and d["two_sided_share"] == round(2 / 3, 3)
    assert not {"roi", "clv", "log_loss", "brier"} & set(d)     # nothing outcome-derived


def test_secondary_metrics_at_eligibility():
    rng = np.random.default_rng(5)
    rows, goals = [], []
    for i in range(420):
        ko = (pd.Timestamp("2026-10-27T18:00Z") + pd.Timedelta(days=int(i // 7))).strftime("%Y-%m-%dT%H:%M:%SZ")
        pts = (pd.Timestamp(ko) - pd.Timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = _row(i, pts, ko, state="QUALIFIED" if i % 3 == 0 else "NO_BET", pdec=0.5, pmkt=0.5)
        r["odds"], r["p_model_raw"] = 2.0, 0.6
        rows.append(r)
        goals.append((2, 1) if rng.uniform() < 0.5 else (0, 0))
    res = _results(rows, goals)
    out = E.evaluate(REG, pd.DataFrame(rows), res, _ident, HASHES, pd.Timestamp("2027-06-01T00:00Z"))
    h = next(r for r in out if r["id"] == "H-EDGE2-NF-OU25-01")
    assert h["status"] == "ELIGIBLE_FOR_REVIEW"
    sec = h["secondary"]
    y = np.array([1.0 if g == (2, 1) else 0.0 for g in goals])
    assert sec["probability_quality"]["market"]["brier"] == round(float(((0.5 - y) ** 2).mean()), 6)
    assert sec["probability_quality"]["model"]["brier"] == round(float(((0.6 - y) ** 2).mean()), 6)
    sel = y[::3]
    assert sec["selection"]["n"] == len(sel)
    assert sec["selection"]["roi"] == round(float(np.where(sel == 1, 1.0, -1.0).mean()), 4)
    lo, hi = sec["selection"]["roi_ci95"]
    assert lo <= sec["selection"]["roi"] <= hi
    assert sec["clv"]["coverage"] == 0.0 and sec["clv"]["mean"] is None
