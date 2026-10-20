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
  scout status READABLE (>= 300 settled with a captured close); >= 300 historical results over
  >= 2 seasons; >= 40 settled this season; odds coverage >= 80% of settled fixtures in the capture
  window for >= 2 key markets; a known API-Football league id; not already a Wowza league.
  Goal rate never enters the gate.

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
          "REJECTED_TEMPORARILY", "DATA_QUALITY_BLOCKED")
STICKY = {"SHADOW_APPROVED", "WOWZA_SUPPORTED", "PAPER_ACTIVE"}
RETRY_WEEKS = 4
GATE = {"settled_with_close": 300, "results": 300, "history_seasons": 2, "current_season_settled": 40,
        "odds_coverage": 0.80, "key_markets_covered": 2}
KEY_MARKETS = ("ou25", "btts", "ou15")


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
def candidate_gate(row: dict, extra: dict, wowza_leagues: set[str]) -> tuple[bool, dict]:
    """extra: {current_season_settled, odds_coverage: {market: share}} from the store."""
    cov = extra.get("odds_coverage", {})
    checks = {
        "scout READABLE (>= 300 settled with a close)": row.get("status") == "READABLE"
            and row.get("settled_with_close", 0) >= GATE["settled_with_close"],
        ">= 300 historical results": row.get("results", 0) >= GATE["results"],
        ">= 2 seasons of history": row.get("history_seasons", 0) >= GATE["history_seasons"],
        ">= 40 settled this season": extra.get("current_season_settled", 0) >= GATE["current_season_settled"],
        ">= 80% odds coverage on 2+ key markets":
            sum(1 for m in KEY_MARKETS if cov.get(m, 0) >= GATE["odds_coverage"]) >= GATE["key_markets_covered"],
        "known API-Football league id": isinstance(row.get("league_id"), int) and row.get("league_id", 0) > 0,
        "not already a Wowza league": f"{row.get('country')} {row.get('league')}".strip() not in wowza_leagues
            and str(row.get("league")) not in wowza_leagues,
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
    from src.data import season_store as store
    res, odds, mdl = store.read("scout_results"), store.read("scout_odds"), store.read("scout_model")
    if not res.empty:
        res = res.sort_values("ingested_at").drop_duplicates("fixture_id", keep="last")
    return res, odds, mdl


def league_extra(lid: int, res: pd.DataFrame, odds: pd.DataFrame) -> dict:
    r = res[res["league_id"] == lid] if not res.empty else res
    if r.empty:
        return {"current_season_settled": 0, "odds_coverage": {}}
    r = r.dropna(subset=["home_goals", "away_goals"])
    cur = r["season"].max() if "season" in r.columns else None
    cur_n = int((r["season"] == cur).sum()) if cur is not None else 0
    cov = {}
    o = odds[odds["league_id"] == lid] if not odds.empty else odds
    if len(o):
        start = pd.to_datetime(o["snapshot_ts"], utc=True, errors="coerce").min()
        when = pd.to_datetime(r.get("kickoff_ts", r.get("date")), unit="s" if "kickoff_ts" in r else None,
                              utc=True, errors="coerce")
        window = r[when >= start]
        for m in KEY_MARKETS:
            got = set(o[o["market"] == m]["fixture_id"])
            cov[m] = round(len(set(window["fixture_id"]) & got) / max(len(window), 1), 3)
    return {"current_season": None if cur is None else str(cur), "current_season_settled": cur_n,
            "odds_coverage": cov}


def data_quality(lid: int, res: pd.DataFrame, odds: pd.DataFrame) -> dict:
    r = res[res["league_id"] == lid] if not res.empty else res
    o = odds[odds["league_id"] == lid] if not odds.empty else odds
    now = pd.Timestamp.now(tz="UTC")
    dates = pd.to_datetime(r.get("kickoff_ts"), unit="s", utc=True, errors="coerce") if "kickoff_ts" in r else \
        pd.to_datetime(r.get("date"), utc=True, errors="coerce")
    teams = set(r.get("home_id", pd.Series(dtype=float)).dropna()) | set(r.get("away_id", pd.Series(dtype=float)).dropna())
    hg, ag = pd.to_numeric(r.get("home_goals"), errors="coerce"), pd.to_numeric(r.get("away_goals"), errors="coerce")
    played = dates < now
    od = pd.to_numeric(o.get("odds"), errors="coerce") if len(o) else pd.Series(dtype=float)
    checks = {
        "fixture_count": int(r["fixture_id"].nunique()) if len(r) else 0,
        "date_span": [str(dates.min())[:10], str(dates.max())[:10]] if len(r) else None,
        "seasons": sorted(map(str, r["season"].dropna().unique())) if "season" in r else [],
        "team_count": len(teams),
        "duplicate_fixtures": int(r["fixture_id"].duplicated().sum()) if len(r) else 0,
        "missing_results_played": int((played & (hg.isna() | ag.isna())).sum()) if len(r) else 0,
        "impossible_scores": int(((hg < 0) | (ag < 0) | (hg > 15) | (ag > 15)).sum()) if len(r) else 0,
        "impossible_dates": int((dates > now + pd.Timedelta(days=400)).sum() + (dates < "1990-01-01").sum()) if len(r) else 0,
        "odds_le_1": int((od <= 1.0).sum()) if len(o) else 0,
        "odds_outliers_gt_50": int((od > 50).sum()) if len(o) else 0,
        "last_result": str(dates[hg.notna()].max())[:10] if len(r) else None,
    }
    crit = []
    if checks["duplicate_fixtures"]: crit.append("duplicate fixtures")
    if checks["impossible_scores"]: crit.append("impossible scores")
    if checks["impossible_dates"]: crit.append("impossible dates")
    if checks["odds_le_1"]: crit.append("odds <= 1")
    if checks["fixture_count"] and checks["missing_results_played"] / checks["fixture_count"] > 0.02:
        crit.append("> 2% of played fixtures have no result")
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


def market_matrix(lid: int, res, odds, mdl, seed: int = 3) -> pd.DataFrame:
    close = R.fair_prob(R.closing(odds[odds["league_id"] == lid]))
    r = res[(res["league_id"] == lid)].dropna(subset=["home_goals", "away_goals"])
    m0 = mdl.sort_values("frozen_ts").drop_duplicates("fixture_id", keep="first") if not mdl.empty else mdl
    rows = []
    for m in R.SIDE:
        c = close[close["market"] == m]
        ref = c[c["bookmaker"] == "pinnacle"].set_index("fixture_id")["p"].combine_first(
            c[c["bookmaker"] == "median"].set_index("fixture_id")["p"])
        g = r.set_index("fixture_id").join(ref.rename("p_mkt"), how="inner")
        g = g.join(m0.set_index("fixture_id")[[R.MODEL_COL[m]]].rename(columns={R.MODEL_COL[m]: "p_mod"}), how="inner")
        if len(g) < 60:
            rows.append({"league_id": lid, "market": m, "n": len(g), "verdict": "INSUFFICIENT_DATA"})
            continue
        g = g.assign(y=R.outcome(m, g["home_goals"].astype(float), g["away_goals"].astype(float)))
        g = g.sort_values("kickoff_ts" if "kickoff_ts" in g else "frozen_ts")
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


def validate(row: dict, extra: dict, res, odds, mdl, week: str) -> dict:
    lid = int(row["league_id"])
    out_dir = OUT / "promotions" / slug(f"{row['country']} {row['league']}")
    out_dir.mkdir(parents=True, exist_ok=True)
    dq = data_quality(lid, res, odds)
    (out_dir / "league_onboarding_data_quality.json").write_text(json.dumps(dq, indent=1, default=str), encoding="utf-8")
    if dq["verdict"] != "PASS":
        return {"new_state": "DATA_QUALITY_BLOCKED", "data_quality": "FAIL", "reason": dq["critical"]}
    mm = market_matrix(lid, res, odds, mdl)
    mm.insert(0, "league", f"{row['country']} {row['league']}")
    mm.to_csv(out_dir / "model_matrix.csv", index=False)
    score, parts = promotion_score(dq, mm, extra, row)
    hard = []
    if len(mm) and (mm["verdict"] == "INSUFFICIENT_DATA").all():
        hard.append("no market has enough settled fixtures with model + close")
    if len(mm) and "calibration_gap" in mm and mm["calibration_gap"].abs().max() > 0.15:
        hard.append("pathological model calibration (gap > 15 pts)")
    new = ("VALIDATION_FAILED" if hard or score < 50 else "REJECTED_TEMPORARILY" if score < 75 else "SHADOW_APPROVED")
    supported = [r["market"] for _, r in mm.iterrows() if r.get("verdict") in ("MODEL_ADDS_TO_MARKET", "MODEL_PREDICTS_MARKET_BETTER")]
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
    }
    (out_dir / "onboarding_proposal.json").write_text(json.dumps(proposal, indent=1, default=str), encoding="utf-8")
    (out_dir / "PROMOTION_REPORT.md").write_text(report_md(row, extra, dq, mm, proposal), encoding="utf-8")
    return {"new_state": new, "data_quality": "PASS", "promotion_score": score, "score_parts": parts,
            "supported_markets": supported, "paper_markets": supported, "hard_fails": hard,
            "integration_route": route, "reason": hard or [f"score {score}"]}


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


def wowza_leagues() -> set[str]:
    try:
        txt = (cfg.V9_LOCAL / "config.py").read_text(encoding="utf-8")
        names = set()
        for var in ("STANDARD_FORMAT_LEAGUES", "NEW_FORMAT_LEAGUES", "ENABLED_LEAGUES"):
            m = re.search(var + r"\s*=\s*\{(.*?)\n\}", txt, re.S)
            if m:
                names |= set(re.findall(r'^\s*"([^"]+)"', m.group(1), re.M))
                names |= set(re.findall(r'"([^"]+)"\s*,', m.group(1)))
        return names
    except Exception:
        return set()


def run(status: dict | None = None, week: str | None = None) -> dict:
    status = status or json.loads((OUT / "league_status.json").read_text(encoding="utf-8"))
    week = week or pd.Timestamp.now(tz="UTC").strftime("%G-W%V")
    lc = load_lifecycle()
    have = wowza_leagues()
    res = odds = mdl = None
    review = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "week": week,
              "calculation_version": CALC_VERSION, "leagues_monitored": len(status.get("leagues", [])),
              "new_candidates": [], "promoted": [], "failed": [], "blocked": [], "still_collecting": [],
              "details": {}}
    for row in status.get("leagues", []):
        lid = str(row["league_id"])
        name = f"{row['country']} {row['league']}"
        cur = lc.get(lid, {}).get("state", "DISCOVERED")
        if cur in STICKY:
            review["details"][name] = {"previous_state": cur, "new_state": cur, "reason": ["already approved - sticky"]}
            continue
        if cur in ("DATA_QUALITY_BLOCKED", "VALIDATION_FAILED", "REJECTED_TEMPORARILY"):
            last = next((h for h in reversed(lc[lid]["history"]) if h["to"] == cur), None)
            if last and _weeks_between(last["week"], week) < RETRY_WEEKS:
                review["details"][name] = {"previous_state": cur, "new_state": cur,
                                           "reason": [f"retry after {RETRY_WEEKS} weeks"]}
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
        if res is None:
            res, odds, mdl = _store()
        extra = league_extra(int(row["league_id"]), res, odds)
        ok, gate = candidate_gate(row, extra, have)
        if not ok:
            transition(lc, lid, "READABLE", "candidate gate not met", week)
            review["still_collecting"].append(name)
            review["details"][name] = {"previous_state": cur, "new_state": "READABLE", **gate}
            continue
        transition(lc, lid, "PROMOTION_CANDIDATE", "candidate gate met", week)
        review["new_candidates"].append(name)
        transition(lc, lid, "VALIDATING", "validation started", week)
        v = validate(row, extra, res, odds, mdl, week)
        transition(lc, lid, v["new_state"], "; ".join(map(str, v.get("reason", []))), week)
        review["details"][name] = {"previous_state": cur, **v}
        bucket = {"SHADOW_APPROVED": "promoted", "DATA_QUALITY_BLOCKED": "blocked"}.get(v["new_state"], "failed")
        review[bucket].append(name)
    save_lifecycle(lc)
    review["counts"] = {k: len(review[k]) for k in ("new_candidates", "promoted", "failed", "blocked", "still_collecting")}
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
        if (pr.get("state") == "SHADOW_APPROVED" and pr.get("integration_route") == "REGRESSION_PASSED_AUTO_ONBOARD"
                and (pr.get("regression") or {}).get("verdict") == "PASS" and not pr.get("hard_fails")):
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
         f"Blocked: {r['counts']['blocked']}", f"Failed: {r['counts']['failed']}", ""]
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
