"""Specials research tracker (src/specials). Synthetic data only."""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from src.combo import dixon_coles as dc
from src.specials import outcomes as O
from src.specials import study as ST
from src.specials import tracker as TR


def _league(name, n_seasons=3, teams=10, start="2021-08-01", seed=0, attack_boost=0.0):
    rng = np.random.default_rng(seed)
    ts = [f"{name} T{i}" for i in range(teams)]
    att = rng.normal(0, 0.25, teams) + attack_boost
    rows, d = [], pd.Timestamp(start)
    for s in range(n_seasons):
        for i in range(teams):
            for j in range(teams):
                if i == j:
                    continue
                lh = np.exp(0.25 + att[i] - att[j] * 0.3)
                la = np.exp(att[j] - att[i] * 0.3)
                rows.append({"date": d, "league": name, "home_team": ts[i], "away_team": ts[j],
                             "home_goals": int(rng.poisson(lh)), "away_goals": int(rng.poisson(la)),
                             "row_source": "synthetic"})
                d += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


# ── outcomes ────────────────────────────────────────────────────────────────────────────────────

def test_grid_sums_to_one_and_matches_bands():
    m = dc._matrix(1.6, 1.1, -0.05)
    p = O.matrix_probs(m)
    assert abs(sum(p[k] for k in O.GRID_KEYS) + p["cs_other"] - 1) < 1e-9
    assert abs(sum(p[k] for k in ("tot_0_1", "tot_2_3", "tot_4_5", "tot_6p")) - 1) < 1e-9
    margins = ("draw", "home_by1", "home_by2_3", "home_by4p", "away_by1", "away_by2_3", "away_by4p")
    assert abs(sum(p[k] for k in margins) - 1) < 1e-9
    assert abs(p["nil_nil"] - p["cs_0_0"]) < 1e-12 and abs(p["ge6"] - p["tot_6p"]) < 1e-12


def test_score_outcomes_settle_the_same_events():
    y = O.score_outcomes([0, 4, 7, 3], [0, 3, 0, 3])
    assert y["nil_nil"].tolist() == [1, 0, 0, 0]
    assert y["ge7"].tolist() == [0, 1, 1, 0]
    assert y["team_ge4"].tolist() == [0, 1, 1, 0]
    assert y["margin_ge4"].tolist() == [0, 0, 1, 0]
    assert y["cs_other"].tolist() == [0, 0, 1, 0]         # 7-0 is outside the 0..6 grid
    assert y["cs_3_3"].tolist() == [0, 0, 0, 1]


def test_base_rates_are_per_league_and_empty_history_has_none():
    a, b = _league("A", seed=1), _league("B", seed=2, attack_boost=0.6)
    ra, rb = O.base_rates(a.home_goals, a.away_goals), O.base_rates(b.home_goals, b.away_goals)
    assert ra["ge5"] != rb["ge5"]
    assert O.base_rates([], []) == {}


def test_unusual_pick_skips_scores_the_league_never_produced():
    p = {k: 0.01 for k in O.UNUSUAL_SCORES}
    base = {k: 0.0 for k in O.UNUSUAL_SCORES}
    base["cs_4_3"] = 0.002
    pick, ratio = O.unusual_pick(p, base)
    assert pick == "cs_4_3" and ratio == pytest.approx(5.0)
    assert O.unusual_pick(p, {k: 0.0 for k in O.UNUSUAL_SCORES})[0] is None


# ── study: no look-ahead ────────────────────────────────────────────────────────────────────────

def test_walk_forward_uses_only_earlier_matches(monkeypatch):
    h = _league("A", n_seasons=4, seed=3)
    fit_max, test_min = [], []
    real_fit, real_pred = ST._fit, ST.predict_rows

    def spy_fit(train):
        fit_max.append(train["date"].max())
        return real_fit(train)

    def spy_pred(model, rows, base):
        test_min.append(rows["date"].min())
        return real_pred(model, rows, base)
    monkeypatch.setattr(ST, "_fit", spy_fit)
    monkeypatch.setattr(ST, "predict_rows", spy_pred)
    pred, info = ST.walk_forward(h)
    assert len(pred) > 0 and info["leagues"]["A"]["fits"] == len(fit_max) == len(test_min)
    assert all(f < t for f, t in zip(fit_max, test_min))  # every fit ends before its month
    # every prediction's base rate equals the share before its month
    r = pred.iloc[-1]
    before = h[h["date"] < r["month"].to_timestamp()]
    assert r["base_ge5"] == pytest.approx(O.base_rates(before.home_goals, before.away_goals)["ge5"])


def test_candidate_cutoff_uses_earlier_months_only(monkeypatch):
    monkeypatch.setitem(ST.RULE, "min_prior_preds", 50)
    h = _league("A", n_seasons=5, seed=4)
    pred, _ = ST.walk_forward(h)
    d = ST.flag_candidates(pred, 0.9)
    months = sorted(d["month"].unique())
    for m in months:
        g = d[d["month"] == m]
        if g["cut_ge5"].notna().any():
            prior = d.loc[d["month"] < m, "p_ge5"].dropna()
            assert g["cut_ge5"].iloc[0] == pytest.approx(np.quantile(prior, 0.9))
    first = d[d["month"] == months[0]]
    assert first["cut_ge5"].isna().all()                  # no earlier predictions -> no cutoff


def test_cutoffs_are_per_league(monkeypatch):
    monkeypatch.setitem(ST.RULE, "min_prior_preds", 50)
    h = pd.concat([_league("A", n_seasons=4, seed=5), _league("B", n_seasons=4, seed=6, attack_boost=0.7)])
    pred, _ = ST.walk_forward(h)
    c = ST.cutoffs(pred, 0.9)
    assert set(c) == {"A", "B"} and c["A"]["ge5"]["cutoff"] != c["B"]["ge5"]["cutoff"]


def test_insufficient_label_below_event_floor(monkeypatch):
    d = pd.DataFrame({"league": "A", "date": pd.Timestamp("2025-01-01"), "cand_ge7": [1.0] * 5,
                      "y_ge7": [1, 0, 0, 0, 0], "base_ge7": [0.02] * 5, "p_ge7": [0.1] * 5})
    assert ST.candidate_eval(d, "ge7", 0.9)["verdict"] == "INSUFFICIENT"


def test_holm_is_monotone():
    adj = ST.holm([0.01, 0.04, 0.03])
    assert adj[0] == pytest.approx(0.03) and max(adj) <= 1


# ── tracker: first sight, no invented price, settlement ────────────────────────────────────────

class _TN:
    @staticmethod
    def resolve(name, cands):
        return name if name in cands else None
    resolve_result = resolve


def _fixtures(now, league, home, away, hours=24):
    ko = pd.Timestamp(now) + pd.Timedelta(hours=hours)
    return pd.DataFrame([{"fixture_key": f"k-{home}-{away}", "league": league,
                          "match_date": ko.strftime("%Y-%m-%d"), "home_team": home, "away_team": away,
                          "kickoff_utc": ko.strftime("%Y-%m-%d %H:%M:%S"), "_ko": ko}])


def test_log_row_has_grid_bands_and_league_base_and_no_invented_price():
    h = _league("A", n_seasons=4, seed=7)
    now = dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc)
    fx = _fixtures(now, "A", "A T1", "A T2")
    rows, counts = TR.build_rows(h, fx, now, {}, pd.DataFrame(), _TN, lambda x: x)
    assert len(rows) == 1
    r = rows.iloc[0]
    for k in O.GRID_KEYS + ["cs_other", "tot_6p", "away_by4p", "nil_nil"]:
        assert 0 <= r[f"p_{k}"] <= 1 and f"base_{k}" in rows.columns
    past = h[h["date"] < pd.Timestamp(now.date())]
    assert r["base_ge6"] == pytest.approx(O.base_rates(past.home_goals, past.away_goals)["ge6"], abs=1e-6)
    assert r["cand_status"] == "NO_CUTOFF" and np.isnan(r["cand_ge6"])
    assert r["price_status"] == "NO_PRICE_FILE" and pd.isna(r["price_under15"])   # never a number
    assert r["special_price_status"] == "NO_PRICE_FILE" and pd.isna(r["price_ge6_best"])
    assert r["price_margin_ge4"] == "NOT_CAPTURED"
    assert r["cal_status"] == "NO_CALIBRATION" and np.isnan(r["p_cal_ge6"])
    assert set(TR.SPECIAL_PRICE_KEYS + TR.V9_PRICE_KEYS) <= set(rows.columns)       # fixed schema


# ── calibration ─────────────────────────────────────────────────────────────────────────────────

def _overconfident(n=12000, leagues=("A", "B"), seed=11):
    rng = np.random.default_rng(seed)
    rows = []
    months = pd.period_range("2022-01", periods=24, freq="M")
    for i in range(n):
        lg = leagues[i % len(leagues)]
        true = rng.uniform(0.02, 0.2) * (1.4 if lg == "B" else 1.0)
        p = min(0.95, true * 1.7)                          # the model says 1.7x what really happens
        y = int(rng.random() < true)
        rows.append({"league": lg, "month": months[i * len(months) // n], "p_ge6": p, "y_ge6": y,
                     "base_ge6": 0.1})
    d = pd.DataFrame(rows)
    d["date"] = d["month"].dt.to_timestamp()
    return d


def test_calibration_corrects_overconfidence_and_learns_league_weights(monkeypatch):
    from src.specials import calibration as CAL
    monkeypatch.setitem(CAL.CAL_RULE, "min_pooled_rows", 1000)
    d = _overconfident()
    prm = CAL.fit(d, "ge6")
    assert prm is not None and set(prm["leagues"]) == {"A", "B"}
    for v in prm["leagues"].values():
        assert 0 <= v["weight"] <= 1
    cal = CAL.walk_forward(d, keys=["ge6"])
    ok = cal["p_cal_ge6"].notna()
    t = cal[ok]
    assert ((t.p_cal_ge6 - t.y_ge6) ** 2).mean() < ((t.p_ge6 - t.y_ge6) ** 2).mean()
    assert cal.loc[cal["month"] == cal["month"].min(), "p_cal_ge6"].isna().all()   # no earlier data


def test_calibration_uses_earlier_months_only(monkeypatch):
    from src.specials import calibration as CAL
    monkeypatch.setitem(CAL.CAL_RULE, "min_pooled_rows", 1000)
    d = _overconfident()
    seen = []
    real = CAL.fit

    def spy(train, key):
        seen.append(train["month"].max())
        return real(train, key)
    monkeypatch.setattr(CAL, "fit", spy)
    months = sorted(d["month"].unique())
    CAL.walk_forward(d, keys=["ge6"])
    assert len(seen) == len(months) and pd.isna(seen[0])     # month 1: nothing earlier to fit on
    assert all(s < m for s, m in zip(seen[1:], months[1:]))


def test_league_without_its_own_data_gets_no_calibrated_probability(monkeypatch):
    from src.specials import calibration as CAL
    monkeypatch.setitem(CAL.CAL_RULE, "min_pooled_rows", 1000)
    prm = CAL.fit(_overconfident(), "ge6")
    assert np.isnan(CAL.apply(prm, "Z", 0.1))                 # never a pooled stand-in
    assert 0 < CAL.apply(prm, "A", 0.1) < 1


# ── prices: proven link, kept bets, budget floor ───────────────────────────────────────────────

def test_odds_rows_keep_only_full_time_special_bets_and_real_prices():
    from src.specials import prices as PR
    resp = [{"fixture": {"id": 7, "timestamp": 2_000_000_000}, "update": "2030-01-01T10:00:00+00:00",
             "bookmakers": [{"id": 8, "name": "Bet365", "bets": [
                 {"name": "Goals Over/Under", "values": [{"value": "Over 5.5", "odd": "9.0"},
                                                         {"value": "Under 5.5", "odd": "1.05"},
                                                         {"value": "Over 2.5", "odd": "1.9"}]},
                 {"name": "Goals Over/Under First Half", "values": [{"value": "Over 4.5", "odd": "40"}]},
                 {"name": "Exact Score", "values": [{"value": "0:0", "odd": "11"}, {"value": "4:3", "odd": "1.01"}]},
                 {"name": "Total - Home", "values": [{"value": "Over 3.5", "odd": "13"}]}]}]}]
    rows = PR.odds_rows(resp, {"fixture_key": "k"}, "2030-01-01T11:00:00Z", 1_900_000_000)
    got = {(r["bet"], r["selection"]) for r in rows}
    assert got == {("Goals Over/Under", "Over 5.5"), ("Goals Over/Under", "Under 5.5"),
                   ("Exact Score", "0:0"), ("Total - Home", "Over 3.5")}
    assert all(r["bookmaker"] == "Bet365" and r["fixture_key"] == "k" for r in rows)
    assert PR.odds_rows(resp, {}, "x", 2_100_000_000) == []        # kicked off -> nothing


def test_link_requires_one_proven_fixture():
    from src.specials import prices as PR
    pro = pd.DataFrame({"fixture_key": ["k1", "k2"], "home_team": ["H", "X"], "away_team": ["W", "Y"],
                        "_ko": pd.to_datetime(["2030-01-02T15:00Z", "2030-01-02T15:00Z"], utc=True),
                        "_lg": "A"})
    ts = int(pd.Timestamp("2030-01-02T15:00Z").timestamp())
    af = [{"fixture_id": 1, "kickoff_ts": ts, "home_team": "H", "away_team": "W"},
          {"fixture_id": 2, "kickoff_ts": ts, "home_team": "H", "away_team": "Nobody"},
          {"fixture_id": 3, "kickoff_ts": ts + 86400, "home_team": "X", "away_team": "Y"}]
    links, c = PR.link_fixtures(pro, af, _TN)
    assert set(links) == {1} and links[1]["fixture_key"] == "k1"
    assert c["linked"] == 1 and c["unproven"] == 2


class _Client:
    def __init__(self, remaining):
        self.remaining, self.calls = remaining, []

    def get(self, ep, params):
        self.calls.append(ep)
        if ep == "/status":
            return {"response": {"requests": {"current": 75_000 - self.remaining, "limit_day": 75_000}}}
        return {"response": []}


def test_price_run_stops_at_the_quota_floor():
    from src.specials import prices as PR
    fx = pd.DataFrame({"fixture_key": ["k1"], "league": ["A"], "home_team": ["H"], "away_team": ["W"],
                       "_ko": pd.to_datetime(["2030-01-02T15:00Z"], utc=True)})
    c = _Client(remaining=PR.MIN_REMAINING)
    rows, run = PR.collect(dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc), c, _TN, lambda x: x,
                           {"A": 1}, lambda lg, d: "2029", fx, log=lambda *a: None)
    assert run["status"].startswith("STOPPED") and c.calls == ["/status"] and rows.empty
    c = _Client(remaining=PR.MIN_REMAINING + 1)            # budget for exactly one call
    rows, run = PR.collect(dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc), c, _TN, lambda x: x,
                           {"A": 1}, lambda lg, d: "2029", fx, log=lambda *a: None)
    assert run["calls_fixtures"] + run["calls_odds"] <= 1


def test_unknown_league_and_unresolved_team_are_counted_not_guessed():
    h = _league("A", n_seasons=4, seed=8)
    now = dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc)
    fx = pd.concat([_fixtures(now, "Z", "Z1", "Z2"), _fixtures(now, "A", "Nobody FC", "A T2")])
    rows, counts = TR.build_rows(h, fx, now, {}, None, _TN, lambda x: x)
    assert rows.empty and counts["no_league_model"] == 1 and counts["unresolved_team"] == 1


def test_price_is_the_last_quote_before_kickoff():
    now = pd.Timestamp("2024-09-01T12:00:00Z")
    ko = pd.Timestamp("2024-09-02T15:00:00Z")
    pr = pd.DataFrame({"league": "A", "match_date": "2024-09-02", "home": "H", "away": "W",
                       "market": ["under15", "over15", "under15", "under15"],
                       "odds": [3.1, 1.35, 3.0, 9.0],
                       "snap": pd.to_datetime(["2024-09-01T08:00Z", "2024-09-01T08:00Z",
                                               "2024-09-01T11:00Z", "2024-09-02T16:00Z"], utc=True),
                       "price_source": "x"})
    out = TR.attach_price(pr, "A", "2024-09-02", "H", "W", ko, now, _TN)
    assert out["price_status"] == "QUOTED" and out["price_under15"] == 3.0
    assert np.isnan(out["price_over15"])                   # not quoted in that snapshot -> missing


def test_first_sight_append_never_rewrites_and_refuses_after_kickoff(tmp_path):
    p = tmp_path / "log.csv"
    now = dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc)
    a = pd.DataFrame([{"row_id": "r1", "kickoff_utc": "2024-09-02T15:00:00Z", "p_ge6": 0.1}])
    assert TR.append_first_sight(a, p, now) == 1
    b = a.assign(p_ge6=0.9)
    assert TR.append_first_sight(b, p, now) == 0           # same fixture again: ignored
    late = pd.DataFrame([{"row_id": "r2", "kickoff_utc": "2024-08-31T15:00:00Z", "p_ge6": 0.2}])
    assert TR.append_first_sight(late, p, now) == 0         # already kicked off
    d = pd.read_csv(p)
    assert d["p_ge6"].tolist() == [0.1]


def test_settlement_uses_the_unique_history_match():
    h = pd.DataFrame([{"date": pd.Timestamp("2024-09-02"), "league": "A", "home_team": "H",
                       "away_team": "W", "home_goals": 4, "away_goals": 3, "row_source": "x"}])
    log = pd.DataFrame([{"row_id": "r1", "league": "A", "kickoff_utc": "2024-09-02T15:00:00Z",
                         "model_home": "H", "model_away": "W", "cs_unusual_pick": "cs_4_3"}])
    now = dt.datetime(2024, 9, 3, tzinfo=dt.timezone.utc)
    s = TR.settle_rows(log, pd.DataFrame(), h, now, _TN)
    assert len(s) == 1 and s.iloc[0]["y_ge7"] == 1 and s.iloc[0]["y_cs_unusual"] == 1
    assert TR.settle_rows(log, s, h, now, _TN).empty        # settled once


def test_no_global_rate_constant_in_the_module_source():
    import inspect
    for mod in (O, ST, TR):
        src = inspect.getsource(mod).lower()
        assert "global_rate" not in src and "default_rate" not in src
