"""Weekly League Promotion — does any scouted league deserve to join the Wowza universe?

    python -m src.scout.promotion            # -> output/scout/weekly_promotion_review.json + per-league artifacts

Extends the existing scout (src/scout: collect -> report -> league_status.json); it is not a second
scout. Answers once a week: has a league become observable and modelable enough to graduate?
If not, it saves the review and does nothing else. That will be the answer for months: the scout
started capturing prices on 2026-10-08 and a league is READABLE only at 300 settled fixtures with a
captured close, which cannot be bought back.

LIFECYCLE (registry/league_lifecycle.json, committed, append-only history per league)
  DISCOVERED -> COLLECTING -> PRICING -> READABLE -> PROMOTION_CANDIDATE -> VALIDATING
             -> SHADOW_APPROVED -> WOWZA_SUPPORTED / PAPER_ACTIVE
  side exits: VALIDATION_FAILED, REJECTED_TEMPORARILY, DATA_QUALITY_BLOCKED (retried after 4 weeks)
  Advanced states are STICKY: running the review twice never promotes a league twice.

CANDIDATE GATE (fail closed; any unknown -> not a candidate)
  scout status READABLE (>= 300 settled with a GENUINE close); >= 300 historical results over
  >= 2 seasons; >= 40 settled this season; genuine-close coverage >= 80% of settled fixtures in the
  capture window for >= 2 key markets; a known API-Football league id; v9's league registry
  (config/leagues.json on v9 main, V9_LOCAL) READABLE and the id NOT in it — compared by
  api_football_id, never by name (Data Truth R1, 2026-11-10). Goal rate never enters the gate.

PRE-REGISTERED RESEARCH GATES (owner 2026-11-10). GATE, the score bands and the calibration limit
decide what to study and what to PROPOSE for onboarding. They are never a staking bar; nothing that
sizes or places a bet may read them (tests/test_scout_data_truth.py). A bar that bets is per league.

DATA QUALITY (Data Truth R2, 2026-11-10) runs on the RAW store, not on a de-duplicated copy, and
on every priced or frozen fixture, not only on stored results — the old duplicate and missing-result
checks read a frame that could not contain either defect.

VALIDATION (per candidate, independently)
  data quality  duplicates, missing results, impossible scores/dates, odds <= 1, outliers,
                freshness, closing coverage, team count -> any critical issue = DATA_QUALITY_BLOCKED
  predictive    frozen pre-match model vs base rate (Brier, log loss, AUC, calibration)
  market        V11-style, OUT OF SAMPLE: fit y ~ logit(close) [+ logit(model)] on the earlier half,
                score both on the later half (chronological); CLV-free because the scout does not bet
  robustness    halves, best month removed, matchday-block bootstrap of the OOS log-loss delta
  score 0-100   DATA 25 / PREDICTIVE 25 / MARKET 20 / ROBUSTNESS 15 / OPERATIONAL 15 — raw ROI
                is not a component
  states        <50 VALIDATION_FAILED · 50-64 REJECTED_TEMPORARILY (research) · 65-74 research/paper
                candidate · >= 75 SHADOW_APPROVED
  MULTIPLE-TESTING CONTROL (E3, 2026-10-26; src/scout/hypotheses.py)
                ~800 league x market cells are watched, so the best-looking ones are mostly noise. A
                score >= 75 now reaches SHADOW_APPROVED ONLY if at least one of the league's
                registered hypotheses is CONFIRMED: genuine close, block bootstrap, BH-FDR across
                every registered cell, confirmation on forward data after an immutable start,
                leave-one-period-out and concentration checks. Otherwise AWAITING_CONFIRMATION
                (re-checked weekly). Supported/paper markets are the CONFIRMED ones only, and the
                auto-onboard queue re-checks this, so a leaderboard can never promote itself.

INTEGRATION — FAIL CLOSED. v9's new-format model is ONE global model: adding a league changes every
new-format league's model. A league reaching SHADOW_APPROVED is therefore run through the
existing-league regression harness (src/scout/regression_harness.py, built 2026-10-14: champion vs
champion + new league, scored on existing leagues only). integration_route becomes
REGRESSION_PASSED_AUTO_ONBOARD (owner standing approval 2026-10-20) or REGRESSION_FAILED (any harness error fails closed). Either way an
onboarding proposal is written (exact v9 config entries, ids, season type) but NO PR is opened and NO
config changes. Money deployment is never decided here.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.scout import report as R

OUT = cfg.OUTPUT_DIR / "scout"
LIFECYCLE_FILE = cfg.REGISTRY_DIR / "league_lifecycle.json"
CALC_VERSION = "league_promotion-1.0.0"

STATES = ("DISCOVERED", "COLLECTING", "PRICING", "READABLE", "PROMOTION_CANDIDATE", "VALIDATING",
          "VALIDATION_FAILED", "SHADOW_APPROVED", "WOWZA_SUPPORTED", "PAPER_ACTIVE",
          "REJECTED_TEMPORARILY", "DATA_QUALITY_BLOCKED", "AWAITING_CONFIRMATION")
STICKY = {"SHADOW_APPROVED", "WOWZA_SUPPORTED", "PAPER_ACTIVE"}
RETRY_WEEKS = 4
#: AWAITING_CONFIRMATION is re-checked every week (the forward evidence grows weekly), but never twice
#: in one week, so a re-run stays idempotent.
CONFIRMATION_RETRY_WEEKS = 1
GATE = {"settled_with_close": 300, "results": 300, "history_seasons": 2, "current_season_settled": 40,
        "odds_coverage": 0.80, "key_markets_covered": 2}
KEY_MARKETS = ("ou25", "btts", "ou15")
#: The existing "> 2% of played fixtures have no result" tolerance, applied to every defect share
#: data_quality measures (one bar, not a new number per check).
MAX_DEFECT_SHARE = 0.02
RESEARCH_GATE_ONLY = True


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


# ── lifecycle store ───────────────────────────────────────────────────────────────────────────
def load_lifecycle() -> dict:
    return json.loads(LIFECYCLE_FILE.read_text(encoding="utf-8")) if LIFECYCLE_FILE.exists() else {}


def save_lifecycle(lc: dict) -> None:
    LIFECYCLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LIFECYCLE_FILE.write_text(json.dumps(lc, indent=1, sort_keys=True), encoding="utf-8")


def transition(lc: dict, lid, new: str, reason: str, week: str) -> str:
    """Record a state change; returns the previous state. No-op when unchanged."""
    assert new in STATES, new
    rec = lc.setdefault(str(lid), {"state": "DISCOVERED", "history": []})
    old = rec["state"]
    if old != new:
        rec["history"].append({"week": week, "from": old, "to": new, "reason": reason})
        rec["state"] = new
    return old


def scout_state(row: dict) -> str:
    st = row.get("status")
    return {"READABLE": "READABLE", "EARLY": "PRICING", "PRICING": "PRICING", "COLLECTING": "PRICING",
            "HISTORY_ONLY": "COLLECTING", "NOT_STARTED": "DISCOVERED"}.get(st, "DISCOVERED")


# ── candidate gate ────────────────────────────────────────────────────────────────────────────
def candidate_gate(row: dict, extra: dict, v9_ids: set[int] | None) -> tuple[bool, dict]:
    """extra: {current_season_settled, odds_coverage: {market: share}} from the store.
    v9_ids: every api_football_id in v9's config/leagues.json; None = could not be read (blocks)."""
    cov = extra.get("odds_coverage", {})
    lid = row.get("league_id")
    checks = {
        "scout READABLE (>= 300 settled with a close)": row.get("status") == "READABLE"
            and row.get("settled_with_close", 0) >= GATE["settled_with_close"],
        ">= 300 historical results": row.get("results", 0) >= GATE["results"],
        ">= 2 seasons of history": row.get("history_seasons", 0) >= GATE["history_seasons"],
        ">= 40 settled this season": extra.get("current_season_settled", 0) >= GATE["current_season_settled"],
        ">= 80% odds coverage on 2+ key markets":
            sum(1 for m in KEY_MARKETS if cov.get(m, 0) >= GATE["odds_coverage"]) >= GATE["key_markets_covered"],
        "known API-Football league id": isinstance(row.get("league_id"), int) and row.get("league_id", 0) > 0,
        "v9 league registry readable": v9_ids is not None,
        "not already a Wowza league (by API-Football id)": v9_ids is not None and isinstance(lid, int)
            and lid not in v9_ids,
    }
    distance = {
        "settled_with_close": max(0, GATE["settled_with_close"] - int(row.get("settled_with_close", 0))),
        "results": max(0, GATE["results"] - int(row.get("results", 0))),
        "history_seasons": max(0, GATE["history_seasons"] - int(row.get("history_seasons", 0))),
        "current_season_settled": max(0, GATE["current_season_settled"] - int(extra.get("current_season_settled", 0))),
    }
    return all(checks.values()), {"checks": checks, "distance": distance}


# ── store-derived facts ───────────────────────────────────────────────────────────────────────
def _store():
    """The RAW scout tables (Data Truth R2: checks run on what is stored, not on a cleaned copy)."""
    from src.data import season_store as store
    return store.read("scout_results"), store.read("scout_odds"), store.read("scout_model")


def _aux():
    """(scout_results_ft90, scout_fixture_status): corrections and reasons stored beside the raw rows."""
    from src.data import season_store as store
    return store.read("scout_results_ft90"), store.read("scout_fixture_status")


def _lg(df: pd.DataFrame | None, lid: int, ids: set | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    if "league_id" in df.columns:
        return df[df["league_id"] == lid]
    return df[df["fixture_id"].isin(ids or set())]


def league_extra(lid: int, res: pd.DataFrame, odds: pd.DataFrame, mdl: pd.DataFrame | None = None,
                 ft90: pd.DataFrame | None = None) -> dict:
    from src.scout import truth as T
    r = _lg(res, lid)
    if r.empty:
        return {"current_season_settled": 0, "odds_coverage": {}}
    served = T.results(r, _lg(ft90, lid, set(r["fixture_id"]))).dropna(subset=["home_goals", "away_goals"])
    cur = served["season"].max() if "season" in served.columns and len(served) else None
    cur_n = int((served["season"] == cur).sum()) if cur is not None else 0
    cov = {}
    o = _lg(odds, lid)
    if len(o):
        start = pd.to_datetime(o["snapshot_ts"], utc=True, errors="coerce").min()
        window = served[pd.to_datetime(served["kickoff_ts"], unit="s", utc=True, errors="coerce") >= start]
        s = T.settled(r, o, _lg(mdl, lid), _lg(ft90, lid, set(r["fixture_id"])))
        for m in KEY_MARKETS:                       # GENUINE closes only (Data Truth R7)
            got = set(s[s["market"] == m]["fixture_id"]) if len(s) else set()
            cov[m] = round(len(set(window["fixture_id"]) & got) / max(len(window), 1), 3)
    return {"current_season": None if cur is None else str(cur), "current_season_settled": cur_n,
            "odds_coverage": cov}


def data_quality(lid: int, res: pd.DataFrame, odds: pd.DataFrame, mdl: pd.DataFrame | None = None,
                 ft90: pd.DataFrame | None = None, status: pd.DataFrame | None = None,
                 now: pd.Timestamp | None = None) -> dict:
    """On the RAW store (Data Truth R2). Every check here can fail (tests/test_scout_data_truth.py)."""
    from src.scout import truth as T
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    r, o, m = _lg(res, lid), _lg(odds, lid), _lg(mdl, lid)
    ids = (set(r["fixture_id"]) if len(r) else set()) | (set(o["fixture_id"]) if len(o) else set()) \
        | (set(m["fixture_id"]) if len(m) else set())
    f9 = _lg(ft90, lid, ids)
    st = status[status["fixture_id"].isin(ids)] if status is not None and len(status) else status
    a = T.audit(r, o, m, f9, st, now) if len(r) else {}
    served = T.results(r, f9) if len(r) else r
    dates = (pd.to_datetime(served["kickoff_ts"], unit="s", utc=True, errors="coerce") if len(served)
             else pd.Series(dtype="datetime64[ns, UTC]"))
    teams = (set(served["home_id"].dropna()) | set(served["away_id"].dropna())) if len(served) else set()
    hg = pd.to_numeric(served.get("home_goals"), errors="coerce") if len(served) else pd.Series(dtype=float)
    ag = pd.to_numeric(served.get("away_goals"), errors="coerce") if len(served) else pd.Series(dtype=float)
    od = pd.to_numeric(o.get("odds"), errors="coerce") if len(o) else pd.Series(dtype=float)
    priced = int(a.get("settled_settled_priced", a.get("settled_priced", 0)) or 0)
    mfx = int(a.get("model_fixtures", 0) or 0)
    checks = {
        "fixture_count": int(served["fixture_id"].nunique()) if len(served) else 0,
        "date_span": [str(dates.min())[:10], str(dates.max())[:10]] if len(served) else None,
        "seasons": sorted(map(str, served["season"].dropna().unique())) if "season" in served else [],
        "team_count": len(teams),
        "raw_result_rows": int(a.get("result_rows", 0)),
        "duplicate_fixtures": int(a.get("result_duplicate_fixtures", 0)),
        "conflicting_duplicate_fixtures": int(a.get("result_conflicting_duplicates", 0)),
        "due_fixtures": int(a.get("due_fixtures", 0)),
        "due_without_result": int(a.get("due_without_result", 0)),
        "due_without_result_unexplained": int(a.get("due_without_result_unexplained", 0)),
        "aet_pen_missing_90": int(a.get("aet_pen_missing_90", 0)),
        "odds_duplicate_groups": int(a.get("odds_dup_groups", 0)),
        "odds_conflict_fixtures": int(a.get("odds_conflict_fixtures", 0)),
        "priced_fixtures": int(o["fixture_id"].nunique()) if len(o) else 0,
        "settled_priced": priced,
        "rescheduled_void": int(a.get("settled_rescheduled_void", 0)),
        "team_id_mismatches": int(a.get("settled_model_identity_mismatch", 0)),
        "model_frozen_after_actual_kickoff": int(a.get("settled_model_frozen_after_actual_kickoff", 0)),
        "model_fixtures": mfx,
        "stale_or_thin_close": int(a.get("settled_stale_or_thin_close", 0)),
        "impossible_scores": int(((hg < 0) | (ag < 0) | (hg > 15) | (ag > 15)).sum()) if len(served) else 0,
        "impossible_dates": int((dates > now + pd.Timedelta(days=400)).sum() + (dates < "1990-01-01").sum()) if len(served) else 0,
        "odds_le_1": int((od <= 1.0).sum()) if len(o) else 0,
        "odds_outliers_gt_50": int((od > 50).sum()) if len(o) else 0,
        "last_result": str(dates[hg.notna()].max())[:10] if len(served) else None,
    }
    share = lambda k, n: (checks[k] / n) if n else 0.0                    # noqa: E731
    bar, close_bar = MAX_DEFECT_SHARE, 1 - GATE["odds_coverage"]
    crit = []
    if checks["conflicting_duplicate_fixtures"]: crit.append("duplicate fixtures with conflicting content")
    if checks["impossible_scores"]: crit.append("impossible scores")
    if checks["impossible_dates"]: crit.append("impossible dates")
    if checks["odds_le_1"]: crit.append("odds <= 1")
    if checks["model_frozen_after_actual_kickoff"]: crit.append("model frozen after the actual kickoff")
    if share("due_without_result_unexplained", checks["due_fixtures"]) > bar:
        crit.append(f"> {bar:.0%} of due fixtures have no result and no recorded reason")
    if share("aet_pen_missing_90", checks["fixture_count"]) > bar:
        crit.append(f"> {bar:.0%} of results lack their 90-minute score")
    if share("odds_conflict_fixtures", checks["priced_fixtures"]) > bar:
        crit.append(f"> {bar:.0%} of priced fixtures carry conflicting duplicate quotes")
    if share("rescheduled_void", priced) > bar:
        crit.append(f"> {bar:.0%} of settled priced fixtures moved > {T.RESCHEDULE_VOID_HOURS} h")
    if share("team_id_mismatches", mfx) > bar:
        crit.append(f"> {bar:.0%} of frozen fixtures do not match the result's teams")
    if share("stale_or_thin_close", priced) > close_bar:
        crit.append(f"> {close_bar:.0%} of settled priced fixtures have no genuine close")
    if checks["last_result"] and (now - pd.Timestamp(checks["last_result"], tz="UTC")).days > 21:
        crit.append("no result in 21 days (feed stale or off-season)")
    if checks["team_count"] < 8: crit.append("fewer than 8 teams")
    return {**checks, "critical": crit, "verdict": "FAIL" if crit else "PASS"}


# ── predictive / market / robustness, per market ──────────────────────────────────────────────
def _ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _fit_predict(Xtr, ytr, Xte):
    X = np.column_stack([np.ones(len(Xtr)), Xtr])
    b = np.zeros(X.shape[1])
    for _ in range(60):
        mu = 1 / (1 + np.exp(-X @ b))
        H = X.T @ (X * (mu * (1 - mu))[:, None]) + 1e-6 * np.eye(len(b))
        step = np.linalg.solve(H, X.T @ (ytr - mu))
        b += step
        if np.abs(step).max() < 1e-9:
            break
    return 1 / (1 + np.exp(-np.column_stack([np.ones(len(Xte)), Xte]) @ b))


def market_matrix(lid: int, res, odds, mdl, seed: int = 3, ft90: pd.DataFrame | None = None) -> pd.DataFrame:
    """Settled fixtures with a GENUINE close and an eligible frozen model (src/scout/truth.settled:
    the one close rule, freeze before the actual kickoff, league + team ids matched, >48h void)."""
    from src.scout import truth as T
    r = _lg(res, lid)
    s = T.settled(r, _lg(odds, lid), _lg(mdl, lid), _lg(ft90, lid, set(r["fixture_id"]) if len(r) else set()))
    rows = []
    for m in R.SIDE:
        g = (s[(s["market"] == m) & s["p_model"].notna()]
             .rename(columns={"p_close": "p_mkt", "p_model": "p_mod"}).set_index("fixture_id")
             if len(s) else pd.DataFrame(columns=["p_mkt", "p_mod", "y", "kickoff_ts"]))
        if len(g) < 60:
            rows.append({"league_id": lid, "market": m, "n": len(g), "verdict": "INSUFFICIENT_DATA"})
            continue
        g = g.sort_values("kickoff_ts")
        half = len(g) // 2
        tr, te = g.iloc[:half], g.iloc[half:]
        lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731
        p_m = _fit_predict(lg(tr["p_mkt"].to_numpy())[:, None], tr["y"].to_numpy(), lg(te["p_mkt"].to_numpy())[:, None])
        p_mw = _fit_predict(np.column_stack([lg(tr["p_mkt"]), lg(tr["p_mod"])]), tr["y"].to_numpy(),
                            np.column_stack([lg(te["p_mkt"]), lg(te["p_mod"])]))
        y = te["y"].to_numpy()
        d = _ll(p_mw, y) - _ll(p_m, y)
        days = pd.to_datetime(te.get("kickoff_ts", te.index.to_series()), unit="s", errors="coerce").dt.date.astype(str).to_numpy() \
            if "kickoff_ts" in te else np.arange(len(te)).astype(str)
        dd = pd.DataFrame({"d": d, "g": days}).groupby("g")["d"].agg(["sum", "count"])
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, len(dd), size=(2000, len(dd)))
        boot = dd["sum"].to_numpy()[idx].sum(1) / dd["count"].to_numpy()[idx].sum(1)
        base = float(tr["y"].mean())
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(y, te["p_mod"])) if len(set(y)) > 1 else None
        rows.append({
            "league_id": lid, "market": m, "n": len(g), "n_train": half, "n_holdout": len(te),
            "base_rate": round(base, 4), "brier_base": round(float(((base - y) ** 2).mean()), 4),
            "brier_model": round(float(((te["p_mod"] - y) ** 2).mean()), 4),
            "logloss_model": round(float(_ll(te["p_mod"].to_numpy(), y).mean()), 4),
            "auc_model": None if auc is None else round(auc, 4),
            "calibration_gap": round(float(te["p_mod"].mean() - y.mean()), 4),
            "market_brier": round(float(((p_m - y) ** 2).mean()), 4),
            "market_logloss": round(float(_ll(p_m, y).mean()), 4),
            "wowza_plus_market_brier": round(float(((p_mw - y) ** 2).mean()), 4),
            "wowza_plus_market_logloss": round(float(_ll(p_mw, y).mean()), 4),
            "oos_logloss_delta": round(float(d.mean()), 5),
            "delta_ci90": [round(float(np.quantile(boot, 0.05)), 5), round(float(np.quantile(boot, 0.95)), 5)],
            "halves_agree": bool(np.sign(d[: len(d) // 2].mean()) == np.sign(d[len(d) // 2:].mean())),
        })
        rr = rows[-1]
        rr["verdict"] = ("MODEL_ADDS_TO_MARKET" if rr["delta_ci90"][1] < 0 else
                         "MODEL_PREDICTS_MARKET_BETTER" if rr["brier_model"] < rr["brier_base"] else "NO_SIGNAL")
    return pd.DataFrame(rows)


def promotion_score(dq: dict, mm: pd.DataFrame, extra: dict, row: dict) -> tuple[float, dict]:
    ok = mm[mm.get("verdict", pd.Series(dtype=str)) != "INSUFFICIENT_DATA"] if len(mm) else mm
    data = 25.0 * (1.0 if dq["verdict"] == "PASS" else 0.0)
    pred = 25.0 * (float((ok["brier_model"] < ok["brier_base"]).mean()) if len(ok) else 0.0)
    mkt = 20.0 * (float((ok["oos_logloss_delta"] < 0).mean()) if len(ok) else 0.0)
    rob = 15.0 * (float(ok["halves_agree"].mean()) if len(ok) else 0.0)
    cov = extra.get("odds_coverage", {})
    oper = 15.0 * min(1.0, np.mean([cov.get(m, 0) for m in KEY_MARKETS]) / GATE["odds_coverage"]) if cov else 0.0
    parts = {"data_quality": round(data, 1), "predictive": round(pred, 1), "market_relative": round(mkt, 1),
             "robustness": round(rob, 1), "operational": round(oper, 1)}
    return round(sum(parts.values()), 1), parts


def validate(row: dict, extra: dict, res, odds, mdl, week: str, mtc: dict | None = None,
             ft90: pd.DataFrame | None = None, status: pd.DataFrame | None = None) -> dict:
    """mtc: this league's multiple-testing summary from src.scout.hypotheses.review
    ({confirmed_markets, confirming_markets, states}). None or empty -> nothing is confirmed."""
    lid = int(row["league_id"])
    mtc = mtc or {}
    confirmed = list(mtc.get("confirmed_markets") or [])
    out_dir = OUT / "promotions" / slug(f"{row['country']} {row['league']}")
    out_dir.mkdir(parents=True, exist_ok=True)
    dq = data_quality(lid, res, odds, mdl, ft90, status)
    (out_dir / "league_onboarding_data_quality.json").write_text(json.dumps(dq, indent=1, default=str), encoding="utf-8")
    if dq["verdict"] != "PASS":
        return {"new_state": "DATA_QUALITY_BLOCKED", "data_quality": "FAIL", "reason": dq["critical"]}
    mm = market_matrix(lid, res, odds, mdl, ft90=ft90)
    mm.insert(0, "league", f"{row['country']} {row['league']}")
    mm.to_csv(out_dir / "model_matrix.csv", index=False)
    score, parts = promotion_score(dq, mm, extra, row)
    hard = []
    if len(mm) and (mm["verdict"] == "INSUFFICIENT_DATA").all():
        hard.append("no market has enough settled fixtures with model + close")
    if len(mm) and "calibration_gap" in mm and mm["calibration_gap"].abs().max() > 0.15:
        hard.append("pathological model calibration (gap > 15 pts)")
    new = ("VALIDATION_FAILED" if hard or score < 50 else "REJECTED_TEMPORARILY" if score < 75 else "SHADOW_APPROVED")
    # E3: the score is descriptive; promotion needs a statistically CONFIRMED league-market hypothesis.
    if new == "SHADOW_APPROVED" and not confirmed:
        new = "AWAITING_CONFIRMATION"
    raw_supported = [r["market"] for _, r in mm.iterrows() if r.get("verdict") in ("MODEL_ADDS_TO_MARKET", "MODEL_PREDICTS_MARKET_BETTER")]
    supported = [m for m in raw_supported if m in confirmed]
    # Existing-league regression harness (src/scout/regression_harness.py, built 2026-10-14): v9's
    # new-format model is ONE global model, so a league that passes here must also not hurt the leagues
    # already in it. Runs only for SHADOW_APPROVED leagues (~5-8 min each). Any error fails closed.
    route, regression = "NONE", None
    if new == "SHADOW_APPROVED":
        try:
            from src.scout import regression_harness as RH
            regression = RH.run(lid)
            RH.save(regression)
            route = {"PASS": "REGRESSION_PASSED_AUTO_ONBOARD",
                     "FAIL": "REGRESSION_FAILED"}.get(regression["verdict"], "REGRESSION_" + regression["verdict"])
        except Exception as e:                                       # noqa: BLE001 - fail closed
            route, regression = "REGRESSION_HARNESS_ERROR", {"error": f"{type(e).__name__}: {e}"}
    proposal = {
        "league_id": lid, "league": f"{row['country']} {row['league']}", "week": week,
        "promotion_score": score, "score_parts": parts, "state": new,
        "integration_route": route,
        "regression": {k: v for k, v in (regression or {}).items() if k != "targets"} or None,
        "integration_note": "v9 new-format is one global model; the existing-league regression harness "
                            "(output/scout/regression/<id>.md) must PASS. OWNER STANDING APPROVAL 2026-10-20: a "
                            "league that passes every gate is queued (output/scout/auto_onboard_queue.json) and "
                            "v9's weekly auto_onboard job makes it a tips generator.",
        "v9_config_entries_needed": {"NEW_FORMAT_LEAGUES": True, "API_FOOTBALL_ONLY_LEAGUES": True,
                                     "ENABLED_LEAGUES": True, "PAPER_LEAGUES": False,
                                     "api_football_id": lid, "current_season": extra.get("current_season")},
        "deployment": {"WOWZA_SUPPORTED": "NO" if new != "SHADOW_APPROVED" else "PENDING",
                       "TIPS": "YES once onboarded (owner 2026-10-20)",
                       "REAL_MONEY": "NO",
                       "STAKE": "league rating rules - a new league has no rating, so the minimum scale"},
        "country": row.get("country"), "current_season": extra.get("current_season"),
        "market_states": {m: ("PAPER" if m in supported else "RESEARCH") for m in R.SIDE},
        "hard_fails": hard,
        "multiple_testing": {"confirmed_markets": confirmed,
                             "confirming_markets": list(mtc.get("confirming_markets") or []),
                             "hypothesis_states": mtc.get("states", {}),
                             "raw_supported_markets_not_confirmed": [m for m in raw_supported if m not in confirmed],
                             "registry": "registry/scout_hypotheses.json"},
    }
    (out_dir / "onboarding_proposal.json").write_text(json.dumps(proposal, indent=1, default=str), encoding="utf-8")
    (out_dir / "PROMOTION_REPORT.md").write_text(report_md(row, extra, dq, mm, proposal), encoding="utf-8")
    reason = hard or ([f"score {score}; no CONFIRMED league-market hypothesis (multiple-testing control)"]
                      if new == "AWAITING_CONFIRMATION" else [f"score {score}"])
    return {"new_state": new, "data_quality": "PASS", "promotion_score": score, "score_parts": parts,
            "supported_markets": supported, "paper_markets": supported, "hard_fails": hard,
            "confirmed_markets": confirmed, "integration_route": route, "reason": reason}


def _md_table(df: pd.DataFrame) -> str:
    """Plain markdown table (pandas.to_markdown needs `tabulate`, which CI does not install)."""
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join("" if (isinstance(v, float) and v != v) else str(v) for v in r) + " |")
    return "\n".join(out)


def report_md(row, extra, dq, mm, p) -> str:
    L = [f"# Promotion report — {p['league']} (API-Football {p['league_id']})", "",
         f"Week {p['week']} · score **{p['promotion_score']}** {p['score_parts']} · state **{p['state']}**", "",
         "## Why scout flagged it", f"READABLE: {row.get('settled_with_close')} settled fixtures with a captured close.", "",
         "## Data we have", f"{row.get('results')} results, {row.get('history_seasons')} seasons, current season "
         f"{extra.get('current_season')} with {extra.get('current_season_settled')} settled; odds coverage {extra.get('odds_coverage')}", "",
         "## Data quality", f"{dq['verdict']} — critical: {dq['critical'] or 'none'}", "",
         "## Models tested / backtest / market comparison (chronological, earlier half -> later half)", "",
         _md_table(mm) if len(mm) else "none", "",
         "## Robustness", "halves_agree per market above; matchday-block 90% CI on the OOS log-loss delta.", "",
         "## Supported / unsupported markets", f"{p['market_states']}", "",
         "## Risks", "- scout model is a baseline goals model, not v9's; v9 performance must be re-tested after onboarding",
         "- one global new-format model: integration needs the existing-league regression test", "",
         "## Config changes required (NOT applied)", f"{p['v9_config_entries_needed']}", "",
         "## Final verdict", f"{p['state']} · integration {p['integration_route']} · REAL_MONEY = NO · PAPER_ONLY = YES"]
    return "\n".join(L) + "\n"


def v9_league_ids() -> set[int] | None:
    """Every api_football_id in v9's league registry, config/leagues.json (v9 main, checked out at
    V9_LOCAL by the workflow) — the source of truth since v9 R2-A. None when it cannot be read or
    reads implausibly small: the candidate gate then BLOCKS (fail closed, Data Truth R1). The old
    name-regex over config.py matched nothing after R2-A and let every league through."""
    from src.scout.registry import MIN_V9_LEAGUES
    try:
        v = json.loads((cfg.V9_LOCAL / "config" / "leagues.json").read_text(encoding="utf-8"))
        lg = v["leagues"]
        recs = lg.values() if isinstance(lg, dict) else lg
        ids = {int(x["api_football_id"]) for x in recs if x.get("api_football_id") is not None}
    except Exception as e:                                             # noqa: BLE001
        print(f"[promotion] v9 league registry unreadable ({type(e).__name__}: {e}) - gate blocks")
        return None
    if len(ids) < MIN_V9_LEAGUES // 2:
        print(f"[promotion] v9 league registry has only {len(ids)} ids - gate blocks")
        return None
    return ids


def run(status: dict | None = None, week: str | None = None) -> dict:
    status = status or json.loads((OUT / "league_status.json").read_text(encoding="utf-8"))
    week = week or pd.Timestamp.now(tz="UTC").strftime("%G-W%V")
    lc = load_lifecycle()
    have = v9_league_ids()
    # E3: every registered league x market hypothesis is reviewed every week — discovery evidence
    # can open a confirmation window long before a league is READABLE. Fail closed: any error
    # leaves nothing confirmed.
    res, odds, mdl = _store()
    ft90, fstatus = _aux()
    try:
        from src.scout import hypotheses as H
        watch = [{"id": int(r["league_id"]), "country": r.get("country", ""), "name": r.get("league", "")}
                 for r in status.get("leagues", []) if r.get("league_id") is not None]
        mtc_all = H.review(res, odds, mdl, leagues=watch, week=week, ft90=ft90)
        mtc_error = None
    except Exception as e:                                           # noqa: BLE001
        mtc_all, mtc_error = {}, f"{type(e).__name__}: {e}"
    review = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "week": week,
              "calculation_version": CALC_VERSION, "leagues_monitored": len(status.get("leagues", [])),
              "new_candidates": [], "promoted": [], "failed": [], "blocked": [], "still_collecting": [],
              "awaiting_confirmation": [], "details": {}}
    for row in status.get("leagues", []):
        lid = str(row["league_id"])
        name = f"{row['country']} {row['league']}"
        cur = lc.get(lid, {}).get("state", "DISCOVERED")
        if cur in STICKY:
            review["details"][name] = {"previous_state": cur, "new_state": cur, "reason": ["already approved - sticky"]}
            continue
        if cur in ("DATA_QUALITY_BLOCKED", "VALIDATION_FAILED", "REJECTED_TEMPORARILY", "AWAITING_CONFIRMATION"):
            wait = CONFIRMATION_RETRY_WEEKS if cur == "AWAITING_CONFIRMATION" else RETRY_WEEKS
            last = next((h for h in reversed(lc[lid]["history"]) if h["to"] == cur), None)
            if last and _weeks_between(last["week"], week) < wait:
                review["details"][name] = {"previous_state": cur, "new_state": cur,
                                           "reason": [f"retry after {wait} week(s)"]}
                continue
        base = scout_state(row)
        if base != "READABLE":
            transition(lc, lid, base, f"scout status {row.get('status')}", week)
            review["still_collecting"].append(name)
            # distance to the candidate gate from the scout's own counts (no store read needed)
            review["details"][name] = {"previous_state": cur, "new_state": base, "scout_status": row.get("status"),
                                       "distance": {
                "settled_with_close": max(0, GATE["settled_with_close"] - int(row.get("settled_with_close", 0))),
                "results": max(0, GATE["results"] - int(row.get("results", 0))),
                "history_seasons": max(0, GATE["history_seasons"] - int(row.get("history_seasons", 0)))}}
            continue
        extra = league_extra(int(row["league_id"]), res, odds, mdl, ft90)
        ok, gate = candidate_gate(row, extra, have)
        if not ok:
            transition(lc, lid, "READABLE", "candidate gate not met", week)
            review["still_collecting"].append(name)
            review["details"][name] = {"previous_state": cur, "new_state": "READABLE", **gate}
            continue
        transition(lc, lid, "PROMOTION_CANDIDATE", "candidate gate met", week)
        review["new_candidates"].append(name)
        transition(lc, lid, "VALIDATING", "validation started", week)
        v = validate(row, extra, res, odds, mdl, week, mtc_all.get(int(row["league_id"])), ft90, fstatus)
        transition(lc, lid, v["new_state"], "; ".join(map(str, v.get("reason", []))), week)
        review["details"][name] = {"previous_state": cur, **v}
        bucket = {"SHADOW_APPROVED": "promoted", "DATA_QUALITY_BLOCKED": "blocked",
                  "AWAITING_CONFIRMATION": "awaiting_confirmation"}.get(v["new_state"], "failed")
        review[bucket].append(name)
    save_lifecycle(lc)
    review["counts"] = {k: len(review[k]) for k in ("new_candidates", "promoted", "failed", "blocked",
                                                    "still_collecting", "awaiting_confirmation")}
    review["multiple_testing"] = {
        "error": mtc_error,
        "leagues_with_confirmed_market": sorted(int(k) for k, v in mtc_all.items() if v.get("confirmed_markets")),
        "leagues_confirming": sorted(int(k) for k, v in mtc_all.items() if v.get("confirming_markets")),
        "registry": "registry/scout_hypotheses.json",
        "rule": "SHADOW_APPROVED and the auto-onboard queue require >= 1 CONFIRMED league-market hypothesis"}
    review["v9_league_registry"] = ("unreadable - every candidate blocked" if have is None
                                    else f"{len(have)} api_football_ids from V9_LOCAL/config/leagues.json")
    review["EXISTING_PRODUCTION_SELECTION_CHANGED"] = "NO"
    review["EXISTING_LEAGUE_MODELS_RETRAINED"] = "NO"
    review["NEW_LEAGUES_PROMOTED"] = review["promoted"]
    review["NEW_LEAGUES_DEPLOYMENT"] = "AUTO_ONBOARD_QUEUE (owner standing approval 2026-10-20)"
    review["auto_onboard_queue"] = write_auto_onboard_queue()
    (OUT / "weekly_promotion_review.json").write_text(json.dumps(review, indent=1, default=str), encoding="utf-8")
    return review


def write_auto_onboard_queue() -> list[str]:
    """Every league whose LATEST proposal passed all gates AND the existing-league regression harness.
    v9's weekly auto_onboard job reads this file (owner standing approval 2026-10-20: 'if a new league
    is ready to become a tips generator, go'). Fail closed: only an explicit PASS route is queued."""
    q = []
    for f in sorted((OUT / "promotions").glob("*/onboarding_proposal.json")):
        try:
            pr = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                               # noqa: BLE001
            continue
        # E3: a proposal without a CONFIRMED multiple-testing-controlled market (including every
        # proposal written before the control existed) is never queued.
        if (pr.get("state") == "SHADOW_APPROVED" and pr.get("integration_route") == "REGRESSION_PASSED_AUTO_ONBOARD"
                and (pr.get("regression") or {}).get("verdict") == "PASS" and not pr.get("hard_fails")
                and (pr.get("multiple_testing") or {}).get("confirmed_markets")):
            q.append({"league_id": int(pr["league_id"]), "league": pr["league"], "country": pr.get("country"),
                      "current_season": pr.get("current_season") or (pr.get("v9_config_entries_needed") or {}).get(
                          "current_season"), "week": pr.get("week"), "promotion_score": pr.get("promotion_score")})
    (OUT / "auto_onboard_queue.json").write_text(json.dumps(
        {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "leagues": q}, indent=1),
        encoding="utf-8")
    return [x["league"] for x in q]


def _weeks_between(a: str, b: str) -> int:
    try:
        da = pd.Timestamp.fromisocalendar(int(a[:4]), int(a[6:]), 1)
        db = pd.Timestamp.fromisocalendar(int(b[:4]), int(b[6:]), 1)
        return int((db - da).days // 7)
    except Exception:
        return 99


def summary(r: dict) -> str:
    L = ["WOWZA WEEKLY LEAGUE SCOUT REVIEW", "", f"Week: {r['week']}", "",
         f"{r['leagues_monitored']} leagues monitored", f"New promotion candidates: {r['counts']['new_candidates']}",
         f"Promoted (shadow): {r['counts']['promoted']}", f"Still collecting: {r['counts']['still_collecting']}",
         f"Blocked: {r['counts']['blocked']}", f"Failed: {r['counts']['failed']}",
         f"Awaiting multiple-testing confirmation: {r['counts'].get('awaiting_confirmation', 0)}", ""]
    for name in r["promoted"]:
        d = r["details"][name]
        L += [f"PROMOTED (SHADOW): {name}", f"  Score: {d.get('promotion_score')}", f"  Paper markets: {d.get('paper_markets')}",
              f"  Deployment: PAPER · existing-league regression: {d.get('integration_route', '?')}", ""]
    near = sorted(((n, d) for n, d in r["details"].items() if "distance" in d),
                  key=lambda kv: sum(kv[1]["distance"].values()))[:5]
    if near:
        L.append("Closest to the candidate gate:")
        L += [f"  {n}: needs {d['distance']}" for n, d in near]
    L += ["", f"EXISTING_PRODUCTION_SELECTION_CHANGED = NO", f"EXISTING_LEAGUE_MODELS_RETRAINED = NO",
          f"NEW_LEAGUES_PROMOTED = {r['promoted']}", "NEW_LEAGUES_DEPLOYMENT = PAPER/SHADOW"]
    return "\n".join(L) + "\n"


def main() -> int:
    r = run()
    s = summary(r)
    (OUT / "WEEKLY_PROMOTION_REVIEW.md").write_text(s, encoding="utf-8")
    print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
