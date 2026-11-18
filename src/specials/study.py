"""
Specials HISTORY STUDY - walk-forward over v9's repaired history. A study, never live rows.

    python -m src.specials.study [--out output/specials] [--predictions-out PATH]

QUESTION. Does the Dixon-Coles score model spot high-scoring (5+/6+/7+ goals, a side scoring 4+,
4+ margin), 0-0 / low-scoring and unusual-exact-score matches better than the LEAGUE'S OWN base rate?
If it cannot, the tracker can never become a tip; if it can, the live tracker is how that is proven
forward.

PROTOCOL (rule SPC-1, every parameter below is declared in RULE and written into every output)
  * Per league, refit monthly: the model for calendar month M is fitted only on that league's matches
    dated before M's first day (src/combo/dixon_coles.fit_league, unchanged), and predicts M's matches.
  * The league base rate for every outcome is the share of that league's matches before M's first
    day - the same data the model saw. Per league, never a pooled or global rate.
  * A fixture is a CANDIDATE for special S when its model probability is above the league's
    `candidate_quantile` of that league's own EARLIER out-of-sample predictions for S (months before
    M only); with fewer than `min_prior_preds` earlier predictions the league has no cutoff yet.
  * Skill: Brier skill score of the model against the league base rate on every out-of-sample row,
    and the candidates' hit rate minus their base rate, each with a block bootstrap over match dates.
    Holm correction across every pooled (special x quantile) candidate test.
  * A candidate verdict needs `min_candidate_events` events among the candidates; below it the
    verdict is INSUFFICIENT whatever the numbers look like.
"""
from __future__ import annotations

import argparse
import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from src.combo import dixon_coles as dc
from src.specials import outcomes as O

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "output" / "specials"

RULE = {
    "version": "SPC-1",
    "refit": "calendar month, expanding window (all earlier matches, Dixon-Coles time decay)",
    "min_league_matches": dc.MIN_MATCHES_PER_LEAGUE,
    "min_team_matches": dc.MIN_MATCHES_PER_TEAM,
    "half_life_days": dc.HALF_LIFE_DAYS,
    "candidate_quantile": 0.90,
    "sensitivity_quantiles": [0.95],
    "min_prior_preds": 200,
    "min_candidate_events": 30,
    "bootstrap": 2000,
    "family_alpha": 0.05,
}
CANDIDATE_KEYS = list(O.SPECIALS) + ["cs_unusual"]


# ── walk-forward predictions ────────────────────────────────────────────────────────────────────

def _fit(train: pd.DataFrame) -> dict | None:
    return dc.fit_league(train.assign(_d=train["date"]))


def predict_rows(model: dict, rows: pd.DataFrame, base: dict) -> tuple[list[dict], int]:
    """One record per row the model can rate: lambdas, p_<key>, base_<key>, the unusual pick."""
    out, unrated = [], 0
    for idx, home, away in zip(rows["_idx"], rows["home_team"], rows["away_team"]):
        pr = dc.predict(model, home, away)
        if not pr:
            unrated += 1
            continue
        p = O.matrix_probs(pr["matrix"])
        pick, ratio = O.unusual_pick(p, base)
        rec = {"lam_home": pr["lam_home"], "lam_away": pr["lam_away"], "rho": float(model["rho"]),
               "cs_unusual_pick": pick, "p_cs_unusual_ratio": ratio,
               "p_cs_unusual": p[pick] if pick else np.nan,
               "base_cs_unusual": base.get(pick, np.nan) if pick else np.nan}
        rec.update({f"p_{k}": v for k, v in p.items()})
        rec.update({f"base_{k}": base.get(k, np.nan) for k in O.OUTCOME_KEYS})
        rec["_idx"] = idx
        out.append(rec)
    return out, unrated


def walk_forward(hist: pd.DataFrame, leagues=None, log=print) -> tuple[pd.DataFrame, dict]:
    """Out-of-sample predictions for every league-month after the league has enough history."""
    h = hist.reset_index(drop=True).copy()
    h["_idx"] = np.arange(len(h))
    h["month"] = h["date"].dt.to_period("M")
    recs, info = [], {"leagues": {}}
    for lg, g in h.groupby("league", sort=True):
        if leagues and lg not in leagues:
            continue
        months = sorted(g["month"].unique())
        n_fit = n_unrated = n_pred = 0
        for m in months:
            start = m.to_timestamp()
            train = g[g["date"] < start]
            if len(train) < RULE["min_league_matches"]:
                continue
            test = g[g["month"] == m]
            model = _fit(train)
            if model is None:
                continue
            n_fit += 1
            base = O.base_rates(train["home_goals"], train["away_goals"])
            rows, unrated = predict_rows(model, test, base)
            for rec in rows:
                rec["n_train"] = len(train)
            recs.extend(rows)
            n_unrated += unrated
            n_pred += len(rows)
        info["leagues"][lg] = {"fits": n_fit, "predictions": n_pred, "unrated_team": n_unrated}
        log(f"[specials study] {lg}: {n_fit} monthly fits, {n_pred} predictions, {n_unrated} unrated")
    if not recs:
        return pd.DataFrame(), info
    p = pd.DataFrame(recs).set_index("_idx")
    base_cols = h.loc[p.index, ["league", "date", "month", "home_team", "away_team",
                                "home_goals", "away_goals"]]
    pred = base_cols.join(p)
    y = O.score_outcomes(pred["home_goals"], pred["away_goals"])
    for k, v in y.items():
        pred[f"y_{k}"] = v
    # the unusual pick happened?
    pick = pred["cs_unusual_pick"]
    pred["y_cs_unusual"] = [int(pred.at[i, f"y_{k}"]) if isinstance(k, str) else np.nan
                            for i, k in zip(pred.index, pick)]
    return pred.reset_index(drop=True), info


# ── candidate rule ───────────────────────────────────────────────────────────────────────────────

def _stat_col(key: str) -> str:
    return "p_cs_unusual_ratio" if key == "cs_unusual" else f"p_{key}"


def flag_candidates(pred: pd.DataFrame, quantile: float) -> pd.DataFrame:
    """cand_<key> (True/False/NaN) and cut_<key> per row, from the league's EARLIER months only."""
    d = pred.copy()
    league = d["league"].to_numpy()
    month = d["month"].to_numpy()
    new = {}
    for key in CANDIDATE_KEYS:
        stat = pd.to_numeric(d[_stat_col(key)], errors="coerce").to_numpy(float)
        cut = np.full(len(d), np.nan)
        for lg in pd.unique(league):
            li = np.flatnonzero(league == lg)
            lm, lv = month[li], stat[li]
            for m in sorted(pd.unique(lm)):
                prior = lv[(lm < m) & ~np.isnan(lv)]
                if len(prior) < RULE["min_prior_preds"]:
                    continue
                cut[li[lm == m]] = float(np.quantile(prior, quantile))
        cand = np.where(np.isnan(cut) | np.isnan(stat), np.nan, (stat > cut).astype(float))
        new[f"cut_{key}"], new[f"cand_{key}"] = cut, cand
    return pd.concat([d.drop(columns=[c for c in new if c in d.columns]),
                      pd.DataFrame(new, index=d.index)], axis=1)


# ── evaluation ──────────────────────────────────────────────────────────────────────────────────

def _boot_mean(values: np.ndarray, dates: np.ndarray, seed: int, n: int) -> np.ndarray:
    """Block bootstrap over match dates of the mean of `values`."""
    df = pd.DataFrame({"v": values, "d": dates})
    g = df.groupby("d")["v"].agg(["sum", "count"])
    s, c = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(seed)
    k = len(s)
    out = np.empty(n)
    for b in range(n):
        i = rng.integers(0, k, k)
        out[b] = s[i].sum() / c[i].sum()
    return out


def _seed(*parts) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode())


def skill(pred: pd.DataFrame, key: str) -> dict:
    """Model vs the league base rate on every out-of-sample row: Brier, log loss, Brier skill."""
    p, b, y = pred.get(f"p_{key}"), pred.get(f"base_{key}"), pred.get(f"y_{key}")
    if p is None or b is None or y is None:
        return {"n": 0}
    ok = p.notna() & b.notna() & y.notna()
    p, b, y, dts = p[ok].to_numpy(float), b[ok].to_numpy(float), y[ok].to_numpy(float), \
        pred.loc[ok, "date"].to_numpy()
    if len(y) == 0:
        return {"n": 0}
    bm, bb = (p - y) ** 2, (b - y) ** 2
    eps = 1e-12
    llm = -(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1)))
    llb = -(y * np.log(np.clip(b, eps, 1)) + (1 - y) * np.log(np.clip(1 - b, eps, 1)))
    diff = bm - bb                                         # < 0 = model better
    bs = _boot_mean(diff, dts, _seed("skill", key), RULE["bootstrap"])
    return {"n": int(len(y)), "events": int(y.sum()), "rate": float(y.mean()),
            "mean_p": float(p.mean()), "mean_base": float(b.mean()),
            "brier_model": float(bm.mean()), "brier_base": float(bb.mean()),
            "brier_skill": float(1 - bm.mean() / bb.mean()) if bb.mean() > 0 else None,
            "brier_diff": float(diff.mean()),
            "brier_diff_ci95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))],
            "logloss_diff": float((llm - llb).mean())}


def candidate_eval(d: pd.DataFrame, key: str, quantile: float) -> dict:
    c = d[d.get(f"cand_{key}") == 1.0]
    yk, bk = f"y_{key}", f"base_{key}"
    c = c[c[yk].notna() & c[bk].notna()]
    out = {"quantile": quantile, "candidates": int(len(c))}
    if len(c) == 0:
        out["verdict"] = "INSUFFICIENT"
        return out
    y, b = c[yk].to_numpy(float), c[bk].to_numpy(float)
    bs = _boot_mean(y - b, c["date"].to_numpy(), _seed("cand", key, quantile), RULE["bootstrap"])
    p_one = float((np.sum(bs <= 0) + 1) / (len(bs) + 1))
    out.update({"events": int(y.sum()), "hit_rate": float(y.mean()), "mean_base": float(b.mean()),
                "lift": float(y.mean() / b.mean()) if b.mean() > 0 else None,
                "mean_p": float(c[_stat_col(key) if key != "cs_unusual" else "p_cs_unusual"].mean()),
                "hit_minus_base": float((y - b).mean()),
                "hit_minus_base_ci95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))],
                "p_one_sided": p_one,
                "leagues": int(c["league"].nunique())})
    out["verdict"] = ("INSUFFICIENT" if out["events"] < RULE["min_candidate_events"] else "PENDING_HOLM")
    return out


def holm(pvals: list[float]) -> list[float]:
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i])
        adj[i] = min(1.0, run)
    return adj.tolist()


def calibration_grid(pred: pd.DataFrame) -> pd.DataFrame:
    """Per league and exact score (0-0..6-6 and other): mean predicted vs actual frequency."""
    rows = []
    keys = O.GRID_KEYS + ["cs_other"]
    for lg, g in list(pred.groupby("league")) + [("ALL", pred)]:
        for k in keys:
            p, y = g[f"p_{k}"], g[f"y_{k}"]
            ok = p.notna() & y.notna()
            if not ok.any():
                continue
            rows.append({"league": lg, "score": k[3:].replace("_", "-") if k != "cs_other" else "other",
                         "n": int(ok.sum()), "events": int(y[ok].sum()),
                         "mean_p": float(p[ok].mean()), "actual": float(y[ok].mean()),
                         "base_mean": float(g.loc[ok, f"base_{k}"].mean())})
    return pd.DataFrame(rows)


def band_calibration(pred: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lg, g in list(pred.groupby("league")) + [("ALL", pred)]:
        for k in list(O.BAND_FUNCS) + list(O.SPECIAL_FUNCS):
            p, y = g[f"p_{k}"], g[f"y_{k}"]
            ok = p.notna() & y.notna()
            if ok.any():
                rows.append({"league": lg, "outcome": k, "n": int(ok.sum()), "events": int(y[ok].sum()),
                             "mean_p": float(p[ok].mean()), "actual": float(y[ok].mean()),
                             "base_mean": float(g.loc[ok, f"base_{k}"].mean())})
    return pd.DataFrame(rows)


def cutoffs(pred: pd.DataFrame, quantile: float) -> dict:
    """Live cutoffs per league x candidate key, from EVERY out-of-sample prediction in the study."""
    out = {}
    for lg, g in pred.groupby("league"):
        for key in CANDIDATE_KEYS:
            v = g[_stat_col(key)].dropna()
            if len(v) < RULE["min_prior_preds"]:
                continue
            out.setdefault(lg, {})[key] = {"cutoff": float(np.quantile(v.to_numpy(), quantile)),
                                           "n_preds": int(len(v)),
                                           "data_end": str(g["date"].max().date())}
    return out


def evaluate(pred: pd.DataFrame) -> dict:
    res = {"rule": RULE, "rows": int(len(pred)), "leagues": int(pred["league"].nunique()),
           "date_min": str(pred["date"].min().date()), "date_max": str(pred["date"].max().date()),
           "skill": {}, "candidates": {}, "per_league": {}}
    for k in O.SPECIALS:
        res["skill"][k] = skill(pred, k)
    tests = []
    for q in [RULE["candidate_quantile"]] + RULE["sensitivity_quantiles"]:
        d = flag_candidates(pred, q)
        for k in CANDIDATE_KEYS:
            ce = candidate_eval(d, k, q)
            res["candidates"][f"{k}@{q}"] = ce
            if "p_one_sided" in ce:
                tests.append(f"{k}@{q}")
            if q == RULE["candidate_quantile"]:
                for lg, g in d.groupby("league"):
                    res["per_league"].setdefault(lg, {})[k] = {
                        **candidate_eval(g, k, q), "skill_brier_diff": skill(g, k).get("brier_diff")}
    adj = holm([res["candidates"][t]["p_one_sided"] for t in tests]) if tests else []
    for t, a in zip(tests, adj):
        ce = res["candidates"][t]
        ce["p_holm"] = a
        if ce["verdict"] == "PENDING_HOLM":
            ce["verdict"] = ("SKILL_SHOWN" if a < RULE["family_alpha"] and ce["hit_minus_base"] > 0
                             else "NO_SKILL_SHOWN")
    res["family_size"] = len(tests)
    for lg, ks in res["per_league"].items():
        for k, ce in ks.items():
            if ce.get("verdict") == "PENDING_HOLM":
                ce["verdict"] = "PER_LEAGUE_UNCORRECTED"   # per-league cells are descriptive only
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Specials history study (walk-forward, research)")
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--history", help="a parquet of v9's repaired history (else exported from V9_LOCAL)")
    ap.add_argument("--predictions-out", help="where to write the full out-of-sample predictions")
    ap.add_argument("--leagues", help="comma list (default: every league)")
    ap.add_argument("--predictions-in", help="re-use a saved --predictions-out parquet (skips the walk-forward)")
    ap.add_argument("--history-info", help="with --predictions-in: the study_summary.json whose history/"
                                           "walk_forward blocks describe those predictions")
    a = ap.parse_args(argv)
    from src.specials import calibration as CAL
    from src.specials import history as HI
    if a.predictions_in:
        pred = pd.read_parquet(a.predictions_in)
        pred["month"] = pd.PeriodIndex(pred["month"].astype(str), freq="M")
        pred["date"] = pd.to_datetime(pred["date"])
        prior = json.loads(Path(a.history_info).read_text(encoding="utf-8")) if a.history_info else {}
        hinfo, winfo = prior.get("history", {"source": a.predictions_in}), prior.get("walk_forward", {})
    else:
        if a.history:
            hist, hinfo = HI.clean_history(pd.read_parquet(a.history))
            hinfo["source"] = a.history
        else:
            hist, hinfo = HI.export_v9_history()
            hinfo["source"] = "v9 data_loader (offline)"
        pred, winfo = walk_forward(hist, leagues=a.leagues.split(",") if a.leagues else None)
    if pred.empty:
        print("[specials study] no predictions")
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = evaluate(pred)
    res["history"] = hinfo
    res["walk_forward"] = winfo
    # calibration, walk-forward (earlier months only), raw and calibrated side by side
    calp = CAL.walk_forward(flag_candidates(pred, RULE["candidate_quantile"]))
    res["calibration"] = {"rule": CAL.CAL_RULE, "before_after": CAL.before_after(calp)}
    live_cal = CAL.final_params(pred)
    (out / "calibration.json").write_text(json.dumps(
        {"rule": CAL.CAL_RULE, "history_end": hinfo.get("date_max"), "v9_sha": hinfo.get("v9_sha"),
         "outcomes": live_cal}, indent=2), encoding="utf-8")
    (out / "study_summary.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    calibration_grid(pred).to_csv(out / "study_calibration_grid.csv", index=False)
    band_calibration(pred).to_csv(out / "study_calibration_bands.csv", index=False)
    cut = {"rule": RULE, "quantile": RULE["candidate_quantile"], "history_end": hinfo.get("date_max"),
           "v9_sha": hinfo.get("v9_sha"), "leagues": cutoffs(pred, RULE["candidate_quantile"])}
    (out / "cutoffs.json").write_text(json.dumps(cut, indent=2), encoding="utf-8")
    if a.predictions_out:
        pred.assign(month=pred["month"].astype(str)).to_parquet(a.predictions_out)
    print(f"[specials study] {len(pred)} out-of-sample predictions, {res['leagues']} leagues -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
