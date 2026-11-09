"""
1X2 (home / draw / away) model review on v9's repaired data (owner 2026-11-09: "check the 1x2 model,
it needs a look; the scores aren't good").

    python -m src.studies.onex2_review --extract <dir> [--out experiments/onex2_review_2026_11]

The inputs come from src/studies/onex2_extract_v9.py (run inside v9, offline, committed data):
matches, point-in-time features and REAL 1X2 prices joined by v9's resolver. This module reads
those files only; it never trains on anything else and never writes a serving file.

PRE-REGISTERED DESIGN (declared here before any candidate was scored; every value is reported)
  windows        walk-forward region WF = 2024-07-01..2026-03-31; HOLDOUT = the owner-approved
                 2026-04-01..2026-11-08 (the same window as the Phase 2 retrain)
  update rule    every rating model is REFIT AT EACH MONTH START on rows dated before that month
                 (a rolling 3-year window) and predicts that month only - each prediction uses only
                 earlier results. Hyperparameters, blend weights and selection rules are chosen on
                 WF only and frozen for the holdout. A FROZEN variant (one fit at 2026-04-01 for the
                 whole holdout) is also scored, because that is what a never-retrained model does.
  reference      dc180: the served model's own recipe (src.combo.dixon_coles, half-life 180 days),
                 retrained on the clean data and kept current
  candidates     dc_hl (half-life from {90, 365} if WF prefers it), elo_ord (per-league Elo + ordered
                 logit; K in {15, 25, 40}, a new team's entry offset in {0, 50, 100} below the league
                 mean, both chosen on WF), mnlogit (multinomial logistic on v9's Phase 2 feature list,
                 C = 0.5 as in v9's Phase 2 config, train-window median imputer with missing
                 indicators, league one-hot), blend (multinomial logistic on log p_model and log
                 p_market_ENTRY, fitted on 2025-07-01..2026-03-31, frozen; holdout only)
  benchmarks     market_entry (power de-vig of the football-data pre-match Avg, else the sharp
                 tracker's opening h2h) - bettable; market_close (football-data closing, else the
                 sharp tracker's last pre-kickoff snapshot) - a BENCHMARK ONLY, never bettable
  comparison     v9 config/phase2_retrain.json 'comparison' block (PG-1.0), reused not re-chosen:
                 common rows, one-sided paired bootstrap over match dates, Holm over the family
  selection      families below, chosen on WF, checked once on the holdout, Holm over every carried
                 configuration; PROVEN = >= 150 holdout bets and Holm p < 0.05 (owner's strict rule)
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.combo import dixon_coles as dc

ROOT = Path(__file__).resolve().parents[2]

WF_START = pd.Timestamp("2024-07-01")
HOLD_START = pd.Timestamp("2026-04-01")
HOLD_END = pd.Timestamp("2026-11-08")
FIT_WINDOW_DAYS = 3 * 365
REF_HALF_LIFE = dc.HALF_LIFE_DAYS
DC_HALF_LIVES = (90.0, 180.0, 365.0)
ELO_K = (15.0, 25.0, 40.0)
ELO_NEW_OFFSET = (0.0, 50.0, 100.0)
LOGISTIC_C = 0.5
BLEND_VALID = (pd.Timestamp("2025-07-01"), pd.Timestamp("2026-03-31"))
OUTCOMES = ("home", "draw", "away")

# Selection families (declared; every configuration is counted)
EV_T = (0.0, 0.03, 0.06, 0.10)
ODDS_CAP = (2.0, 3.0, 4.5)
SEL_MIN_N_WF = 100
PROVEN_MIN_N = 150


# ── market ──────────────────────────────────────────────────────────────────────────────────

def power_devig3(o: np.ndarray) -> np.ndarray:
    """Power de-vig of a 3-way price: p_i = (1/o_i)^k with k such that the p_i sum to 1.
    Rows with any non-price (<= 1 or NaN) give NaN - nothing is assumed."""
    o = np.asarray(o, dtype=float)
    out = np.full(o.shape, np.nan)
    ok = np.all(np.isfinite(o) & (o > 1.0), axis=1)
    q = 1.0 / o[ok]
    lo, hi = np.full(len(q), 0.2), np.full(len(q), 5.0)
    for _ in range(80):
        mid = (lo + hi) / 2
        s = (q ** mid[:, None]).sum(1)
        lo = np.where(s > 1.0, mid, lo)
        hi = np.where(s > 1.0, hi, mid)
    k = (lo + hi) / 2
    p = q ** k[:, None]
    out[ok] = p / p.sum(1, keepdims=True)
    return out


def market_frame(prices: pd.DataFrame) -> pd.DataFrame:
    """One row per row_id: m_entry_*, m_close_* (de-vigged), the bettable entry odds and their
    source. football-data first; the sharp tracker where football-data has no row."""
    def pick(classes):
        d = prices[prices["class"].isin(classes)].copy()
        d["_rank"] = d["class"].map({c: i for i, c in enumerate(classes)})
        return d.sort_values("_rank").drop_duplicates("row_id")
    e = pick(["FD_ENTRY", "SHARP_OPEN"])
    c = pick(["FD_CLOSE", "SHARP_CLOSE"])
    b = pick(["FD_BET365_ENTRY", "SHARP_OPEN"])
    m = pd.DataFrame({"row_id": e["row_id"].to_numpy()})
    pe = power_devig3(e[["o_home", "o_draw", "o_away"]].to_numpy())
    for i, k in enumerate(OUTCOMES):
        m[f"m_entry_{k}"] = pe[:, i]
    m["entry_class"] = e["class"].to_numpy()
    pc = power_devig3(c[["o_home", "o_draw", "o_away"]].to_numpy())
    mc = pd.DataFrame({"row_id": c["row_id"].to_numpy(), "close_class": c["class"].to_numpy()})
    for i, k in enumerate(OUTCOMES):
        mc[f"m_close_{k}"] = pc[:, i]
        mc[f"o_close_{k}"] = c[f"o_{k}"].to_numpy()
    bb = b[["row_id", "class", "o_home", "o_draw", "o_away"]].rename(
        columns={"class": "bet_class", "o_home": "bet_home", "o_draw": "bet_draw",
                 "o_away": "bet_away"})
    return m.merge(mc, on="row_id", how="outer").merge(bb, on="row_id", how="outer")


# ── Dixon-Coles, rolling ────────────────────────────────────────────────────────────────────

def months(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    return list(pd.date_range(start.to_period("M").to_timestamp(), end, freq="MS"))


def _dc_job(args):
    league, g, month, half_life, frozen_at = args
    fit_end = frozen_at if frozen_at is not None else month
    tr = g[(g["date"] < fit_end) & (g["date"] >= fit_end - pd.Timedelta(days=FIT_WINDOW_DAYS))]
    te = g[(g["date"] >= month) & (g["date"] < month + pd.offsets.MonthBegin(1))]
    if te.empty:
        return []
    m = dc.fit_league(tr.assign(_d=tr["date"]), half_life=half_life)
    if m is None:
        return []
    out = []
    for rid, h, a in zip(te["row_id"], te["home_team"].astype(str), te["away_team"].astype(str)):
        pr = dc.predict(m, h, a)
        if pr:
            out.append((rid, pr["p_home"], pr["p_draw"], pr["p_away"]))
    return out


def dc_rolling(matches: pd.DataFrame, half_life: float, start: pd.Timestamp, end: pd.Timestamp,
               frozen_at: pd.Timestamp | None = None, workers: int = 7) -> pd.DataFrame:
    jobs = []
    for lg, g in matches.groupby("league"):
        g = g.sort_values("date")
        for mo in months(start, end):
            jobs.append((lg, g, mo, half_life, frozen_at))
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(_dc_job, jobs, chunksize=4):
            rows.extend(r)
    return pd.DataFrame(rows, columns=["row_id", "p_home", "p_draw", "p_away"])


# ── Elo + ordered logit ─────────────────────────────────────────────────────────────────────

def elo_pre_match(matches: pd.DataFrame, k: float, new_offset: float) -> pd.Series:
    """Pre-match Elo difference (home - away) per row_id, per league, chronological. All matches of
    one DAY are rated before any of that day's results updates a rating (no same-day leakage).
    A team first seen in the league enters at the league's current mean minus `new_offset`."""
    out = {}
    for lg, g in matches.sort_values(["date", "row_id"]).groupby("league"):
        r: dict[str, float] = {}
        total = 0.0
        days = g["date"].to_numpy()
        rec = list(zip(g["row_id"], g["home_team"], g["away_team"], g["home_goals"], g["away_goals"]))
        i, n = 0, len(rec)
        while i < n:
            j = i
            while j < n and days[j] == days[i]:
                j += 1
            mean = total / len(r) if r else 0.0
            for _, h, a, _, _ in rec[i:j]:
                for t in (h, a):
                    if t not in r:
                        r[t] = mean - (new_offset if r else 0.0)
                        total += r[t]
            upd = []
            for rid, h, a, hg, ag in rec[i:j]:
                dlt0 = r[h] - r[a]
                out[rid] = dlt0
                e = 1.0 / (1.0 + 10 ** (-dlt0 / 400.0))
                s = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
                upd.append((h, a, k * (s - e)))
            for h, a, dlt in upd:          # updates are zero-sum, so the league total is unchanged
                r[h] += dlt
                r[a] -= dlt
            i = j
    return pd.Series(out, name="elo_diff")


def _ordered_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray | None:
    """y: 0 away, 1 draw, 2 home; latent = b * x. Returns (b, c1, c2) or None."""
    if len(y) < 100 or len(set(y)) < 3:
        return None

    def nll(p):
        b, c1, d = p
        c2 = c1 + np.exp(d)
        z = b * x
        p0 = 1 / (1 + np.exp(-(c1 - z)))
        p01 = 1 / (1 + np.exp(-(c2 - z)))
        pr = np.where(y == 0, p0, np.where(y == 1, p01 - p0, 1 - p01))
        return -np.sum(np.log(np.clip(pr, 1e-12, None)))
    res = minimize(nll, np.array([0.5, -0.5, 0.0]), method="L-BFGS-B")
    b, c1, d = res.x
    return np.array([b, c1, c1 + np.exp(d)])


def _ordered_predict(par: np.ndarray, x: np.ndarray) -> np.ndarray:
    b, c1, c2 = par
    z = b * x
    p0 = 1 / (1 + np.exp(-(c1 - z)))
    p01 = 1 / (1 + np.exp(-(c2 - z)))
    return np.column_stack([1 - p01, p01 - p0, p0])        # home, draw, away


def elo_rolling(matches: pd.DataFrame, elo: pd.Series, start, end, frozen_at=None) -> pd.DataFrame:
    d = matches.join(elo, on="row_id").dropna(subset=["elo_diff"])
    d["y"] = np.where(d["home_goals"] > d["away_goals"], 2,
                      np.where(d["home_goals"] == d["away_goals"], 1, 0))
    rows = []
    for lg, g in d.groupby("league"):
        for mo in months(start, end):
            fe = frozen_at if frozen_at is not None else mo
            tr = g[(g["date"] < fe) & (g["date"] >= fe - pd.Timedelta(days=FIT_WINDOW_DAYS))]
            te = g[(g["date"] >= mo) & (g["date"] < mo + pd.offsets.MonthBegin(1))]
            if te.empty:
                continue
            par = _ordered_fit(tr["elo_diff"].to_numpy() / 100.0, tr["y"].to_numpy())
            if par is None:
                continue
            p = _ordered_predict(par, te["elo_diff"].to_numpy() / 100.0)
            rows.append(pd.DataFrame({"row_id": te["row_id"].to_numpy(), "p_home": p[:, 0],
                                      "p_draw": p[:, 1], "p_away": p[:, 2]}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["row_id", "p_home", "p_draw", "p_away"])


# ── multinomial logistic on v9's Phase 2 features ───────────────────────────────────────────

def feature_list(v9_root: str) -> tuple[list[str], list[str]]:
    c = json.loads((Path(v9_root) / "config" / "phase2_retrain.json").read_text(encoding="utf-8"))
    f = c["features"]
    never = set(f.get("never_model_inputs") or [])
    cols = [x for g in f["groups"].values() if g.get("include") for x in g.get("columns", [])
            if x not in never]
    req = list(c["data"].get("require_present") or [])
    return cols, req


def mnlogit_rolling(feat: pd.DataFrame, cols: list[str], start, end, frozen_at=None):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    d = feat.copy()
    d["y"] = np.where(d["home_goals"] > d["away_goals"], 0,
                      np.where(d["home_goals"] == d["away_goals"], 1, 2))
    lg = pd.get_dummies(d["league"], prefix="lg", dtype=float)
    X = pd.concat([d[cols].apply(pd.to_numeric, errors="coerce"), lg], axis=1)
    rows = []
    for mo in months(start, end):
        fe = frozen_at if frozen_at is not None else mo
        tr = (d["date"] < fe) & (d["date"] >= fe - pd.Timedelta(days=FIT_WINDOW_DAYS))
        te = (d["date"] >= mo) & (d["date"] < mo + pd.offsets.MonthBegin(1))
        if not te.any() or tr.sum() < 1000:
            continue
        Xtr = X[tr]
        keep = [c for c in Xtr.columns if Xtr[c].notna().any()]   # no training value -> dropped
        pipe = make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                             StandardScaler(), LogisticRegression(C=LOGISTIC_C, max_iter=2000))
        pipe.fit(Xtr[keep], d.loc[tr, "y"])
        print(f"[1x2] mnlogit {mo:%Y-%m}: {int(tr.sum())} train rows, "
              f"{int(pipe[-1].n_iter_[0])} iterations", flush=True)
        p = pipe.predict_proba(X.loc[te, keep])
        cls = list(pipe.classes_)
        rows.append(pd.DataFrame({"row_id": d.loc[te, "row_id"].to_numpy(),
                                  "p_home": p[:, cls.index(0)], "p_draw": p[:, cls.index(1)],
                                  "p_away": p[:, cls.index(2)]}))
    return pd.concat(rows, ignore_index=True)


# ── blend on ENTRY prices ───────────────────────────────────────────────────────────────────

def blend(model: pd.DataFrame, mkt: pd.DataFrame, labels: pd.DataFrame):
    """Multinomial logistic on [log p_model, log p_market_entry], fitted on BLEND_VALID only;
    applied to holdout rows with an entry price. Returns (holdout predictions, coefficients)."""
    from sklearn.linear_model import LogisticRegression
    d = model.merge(mkt[["row_id"] + [f"m_entry_{k}" for k in OUTCOMES]], on="row_id") \
             .merge(labels, on="row_id").dropna()
    feats = [f"p_{k}" for k in OUTCOMES] + [f"m_entry_{k}" for k in OUTCOMES]
    X = np.log(np.clip(d[feats].to_numpy(), 1e-6, 1))
    fit = (d["date"] >= BLEND_VALID[0]) & (d["date"] <= BLEND_VALID[1])
    hold = (d["date"] >= HOLD_START) & (d["date"] <= HOLD_END)
    if fit.sum() < 300:
        return pd.DataFrame(columns=["row_id"] + [f"p_{k}" for k in OUTCOMES]), {"n_fit": int(fit.sum())}
    lr = LogisticRegression(C=1.0, max_iter=2000).fit(X[fit], d.loc[fit, "y"])
    p = lr.predict_proba(X[hold])
    cls = list(lr.classes_)
    out = pd.DataFrame({"row_id": d.loc[hold, "row_id"].to_numpy(),
                        "p_home": p[:, cls.index(0)], "p_draw": p[:, cls.index(1)],
                        "p_away": p[:, cls.index(2)]})
    return out, {"n_fit": int(fit.sum()), "coef": lr.coef_.round(4).tolist(), "classes": cls}


# ── scoring ─────────────────────────────────────────────────────────────────────────────────

def row_ll(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None))


def row_brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1.0
    return ((p - oh) ** 2).sum(1)


def row_rps(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1.0
    return ((np.cumsum(p, 1) - np.cumsum(oh, 1))[:, :2] ** 2).sum(1) / 2.0


def paired_bootstrap(delta: np.ndarray, dates: np.ndarray, n_boot: int, seed: int):
    """One-sided p that mean(delta) < 0 (candidate better), resampling match DATES."""
    df = pd.DataFrame({"d": delta, "t": dates}).groupby("t")["d"].agg(["sum", "count"])
    s, c = df["sum"].to_numpy(), df["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    means = s[idx].sum(1) / c[idx].sum(1)
    k = int((means >= 0).sum())
    return (k + 1) / (n_boot + 1), np.percentile(means, [2.5, 97.5]).tolist()


def holm(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    out = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    idx = np.where(ok)[0]
    if not len(idx):
        return out
    order = idx[np.argsort(p[idx])]
    m = len(order)
    run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * p[i]))
        out[i] = run
    return out


def ROI_bootstrap(pnl: np.ndarray, dates: np.ndarray, n_boot: int, seed: int):
    """(one-sided p that ROI <= 0, 95% CI) by a match-date block bootstrap."""
    df = pd.DataFrame({"x": pnl, "t": dates}).groupby("t")["x"].agg(["sum", "count"])
    s, c = df["sum"].to_numpy(), df["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    means = s[idx].sum(1) / c[idx].sum(1)
    return (int((means <= 0).sum()) + 1) / (n_boot + 1), np.percentile(means, [2.5, 97.5]).tolist()


# ── selection families ──────────────────────────────────────────────────────────────────────

def candidate_bets(p: pd.DataFrame, rule: dict) -> pd.DataFrame:
    """Bets one rule would place. p has p_*, bet_* (bettable odds), y, date, league."""
    P = p[[f"p_{k}" for k in OUTCOMES]].to_numpy()
    O = p[[f"bet_{k}" for k in OUTCOMES]].to_numpy()
    fam = rule["family"]
    if fam == "league_wide":
        i = OUTCOMES.index(rule["outcome"])
        m = (p["league"] == rule["league"]).to_numpy() & np.isfinite(O[:, i])
        sel = np.where(m, i, -1)
    else:
        ev = P * O - 1.0
        if fam == "favourite":
            i = np.nanargmin(np.where(np.isfinite(O), O, np.inf), axis=1)
            sel = np.where(ev[np.arange(len(i)), i] >= rule["t"], i, -1)
        elif fam == "draw":
            sel = np.where(ev[:, 1] >= rule["t"], 1, -1)
        else:                                    # best_ev / best_ev_cap
            evm = np.where(np.isfinite(ev), ev, -np.inf)
            if fam == "best_ev_cap":
                evm = np.where(O <= rule["cap"], evm, -np.inf)
            i = np.argmax(evm, axis=1)
            sel = np.where(evm[np.arange(len(i)), i] >= rule["t"], i, -1)
    take = sel >= 0
    b = p.loc[take, ["row_id", "date", "league", "y"]].copy()
    ii = sel[take]
    b["pick"] = ii
    b["odds"] = O[take][np.arange(len(ii)), ii]
    b["pnl"] = np.where(b["y"].to_numpy() == ii, b["odds"] - 1.0, -1.0)
    if "o_close_home" in p.columns:
        C = p.loc[take, [f"o_close_{k}" for k in OUTCOMES]].to_numpy()
        b["clv"] = b["odds"].to_numpy() / C[np.arange(len(ii)), ii] - 1.0
    return b


def rule_grid(leagues: list[str]) -> list[dict]:
    g = [{"family": "best_ev", "t": t} for t in EV_T]
    g += [{"family": "best_ev_cap", "t": t, "cap": c} for t in EV_T for c in ODDS_CAP]
    g += [{"family": "favourite", "t": t} for t in EV_T]
    g += [{"family": "draw", "t": t} for t in EV_T]
    g += [{"family": "league_wide", "league": lg, "outcome": o} for lg in leagues for o in OUTCOMES]
    return g


def rule_name(r: dict) -> str:
    return "|".join(f"{k}={v}" for k, v in r.items())


# ── main ────────────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True)
    ap.add_argument("--v9", default=os.getenv("V9_LOCAL", ""))
    ap.add_argument("--out", default=str(ROOT / "experiments" / "onex2_review_2026_11"))
    ap.add_argument("--workers", type=int, default=7)
    a = ap.parse_args(argv)
    ex, out = Path(a.extract), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((ex / "extract.json").read_text(encoding="utf-8"))
    cmp_cfg = json.loads((Path(a.v9) / "config" / "phase2_retrain.json")
                         .read_text(encoding="utf-8"))["comparison"]
    M = pd.read_parquet(ex / "matches.parquet")
    M["date"] = pd.to_datetime(M["date"])
    F = pd.read_parquet(ex / "features.parquet")
    F["date"] = pd.to_datetime(F["date"])
    PR = pd.read_parquet(ex / "prices.parquet")
    mkt = market_frame(PR)
    M["y"] = np.where(M["home_goals"] > M["away_goals"], 0,
                      np.where(M["home_goals"] == M["away_goals"], 1, 2))
    lab = M[["row_id", "date", "league", "y"]]
    report: dict = {"extract": meta, "comparison_rules": cmp_cfg,
                    "design": {"wf": [str(WF_START.date()), str((HOLD_START - pd.Timedelta(days=1)).date())],
                               "holdout": [str(HOLD_START.date()), str(HOLD_END.date())],
                               "fit_window_days": FIT_WINDOW_DAYS, "dc_half_lives": DC_HALF_LIVES,
                               "elo_k": ELO_K, "elo_new_offset": ELO_NEW_OFFSET,
                               "logistic_C": LOGISTIC_C,
                               "blend_valid": [str(BLEND_VALID[0].date()), str(BLEND_VALID[1].date())]}}
    preds: dict[str, pd.DataFrame] = {}
    cache = out / "pred_cache"
    cache.mkdir(exist_ok=True)
    tag = f"{meta.get('frame_hash')}_{meta.get('v9_commit', '')[:8]}"

    def cached(name, fn):
        """Predictions are cached per (name, frame hash, v9 commit), so a rerun of the SAME inputs
        reuses them; any change of the extract recomputes everything."""
        f = cache / f"{name}__{tag}.parquet"
        if f.exists():
            return pd.read_parquet(f)
        p = fn()
        p.to_parquet(f)
        return p

    # rating models, rolling
    for hl in DC_HALF_LIVES:
        preds[f"dc{int(hl)}"] = cached(f"dc{int(hl)}", lambda hl=hl: dc_rolling(
            M, hl, WF_START, HOLD_END, workers=a.workers))
        print(f"[1x2] dc{int(hl)}: {len(preds[f'dc{int(hl)}'])} predictions", flush=True)
    preds["dc180_frozen"] = cached("dc180_frozen", lambda: dc_rolling(
        M, REF_HALF_LIFE, HOLD_START, HOLD_END, frozen_at=HOLD_START, workers=a.workers))
    elo_scores = {}
    elos = {}
    for k in ELO_K:
        for off in ELO_NEW_OFFSET:
            e = elo_pre_match(M, k, off)
            elos[(k, off)] = e
            p = elo_rolling(M, e, WF_START, HOLD_START - pd.Timedelta(days=1))
            j = p.merge(lab, on="row_id")
            elo_scores[(k, off)] = float(row_ll(j[["p_home", "p_draw", "p_away"]].to_numpy(),
                                                j["y"].to_numpy()).mean())
    kbest = min(elo_scores, key=elo_scores.get)
    report["elo_choice"] = {"wf_logloss": {f"K{k}_off{o}": round(v, 5) for (k, o), v in elo_scores.items()},
                            "chosen": {"K": kbest[0], "new_offset": kbest[1]}}
    preds["elo_ord"] = cached("elo_ord", lambda: elo_rolling(M, elos[kbest], WF_START, HOLD_END))
    print("[1x2] elo done", flush=True)
    cols, req = feature_list(a.v9)
    Fe = F.dropna(subset=req) if req else F
    Fe = Fe.join(elos[kbest], on="row_id")
    preds["mnlogit"] = cached("mnlogit", lambda: mnlogit_rolling(Fe, cols + ["elo_diff"], WF_START, HOLD_END))
    print("[1x2] mnlogit done", flush=True)

    # half-life choice on WF (reference stays dc180)
    wf_ll = {}
    for hl in DC_HALF_LIVES:
        j = preds[f"dc{int(hl)}"].merge(lab, on="row_id")
        j = j[(j["date"] >= WF_START) & (j["date"] < HOLD_START)]
        wf_ll[int(hl)] = float(row_ll(j[["p_home", "p_draw", "p_away"]].to_numpy(),
                                      j["y"].to_numpy()).mean())
    hl_best = min(wf_ll, key=wf_ll.get)
    report["dc_half_life_choice"] = {"wf_logloss": wf_ll, "chosen": hl_best}
    cand = {"elo_ord": preds["elo_ord"], "mnlogit": preds["mnlogit"]}
    if hl_best != int(REF_HALF_LIFE):
        cand["dc_hl"] = preds[f"dc{hl_best}"]

    # best deployable model on WF (for the blend and the selection) - chosen on WF only, by the mean
    # log-loss difference against the reference on COMMON rows (the models cover different rows, so
    # comparing each one's own-row log loss would rank row sets, not models: the first run of this
    # study did that and picked dc_hl; corrected 2026-11-09, both runs are in the report).
    ref180 = preds["dc180"]
    wf_delta = {"dc180": 0.0}
    for n, p in cand.items():
        j = ref180.merge(p, on="row_id", suffixes=("_r", "_c")).merge(lab, on="row_id")
        j = j[(j["date"] >= WF_START) & (j["date"] < HOLD_START)]
        y = j["y"].to_numpy()
        wf_delta[n] = float((row_ll(j[[f"p_{k}_c" for k in OUTCOMES]].to_numpy(), y)
                             - row_ll(j[[f"p_{k}_r" for k in OUTCOMES]].to_numpy(), y)).mean())
    best = min(wf_delta, key=wf_delta.get)
    best_pred = preds["dc180"] if best == "dc180" else cand[best]
    report["best_model_on_wf"] = {"wf_delta_logloss_vs_dc180_common_rows": wf_delta, "chosen": best}
    bl, binfo = blend(best_pred, mkt, lab)
    report["blend"] = binfo
    cand["blend_entry"] = bl
    mk_e = mkt[["row_id"] + [f"m_entry_{k}" for k in OUTCOMES]].dropna().rename(
        columns={f"m_entry_{k}": f"p_{k}" for k in OUTCOMES})
    mk_c = mkt[["row_id"] + [f"m_close_{k}" for k in OUTCOMES]].dropna().rename(
        columns={f"m_close_{k}": f"p_{k}" for k in OUTCOMES})
    cand["market_entry"] = mk_e
    cand["market_close_BENCHMARK"] = mk_c
    cand["dc180_frozen_at_holdout_start"] = preds["dc180_frozen"]
    served = served_model_predictions(M)
    if served is not None:
        cand["served_model_1x2_json"] = served

    # comparisons vs the reference, both stages
    ref = preds["dc180"]
    rows = []
    for stage, lo, hi in (("walk_forward", WF_START, HOLD_START - pd.Timedelta(days=1)),
                          ("holdout", HOLD_START, HOLD_END)):
        for n, p in cand.items():
            j = ref.merge(p, on="row_id", suffixes=("_r", "_c")).merge(lab, on="row_id")
            j = j[(j["date"] >= lo) & (j["date"] <= hi)]
            r = {"stage": stage, "candidate": n, "n_common": int(len(j)),
                 "matchdays": int(j["date"].nunique()) if len(j) else 0}
            if len(j) < 30:
                r["verdict"] = "NOT_COMPARABLE"
                rows.append(r)
                continue
            y = j["y"].to_numpy()
            Pr = j[[f"p_{k}_r" for k in OUTCOMES]].to_numpy()
            Pc = j[[f"p_{k}_c" for k in OUTCOMES]].to_numpy()
            dl = row_ll(Pc, y) - row_ll(Pr, y)
            db = row_brier(Pc, y) - row_brier(Pr, y)
            pv, ci = paired_bootstrap(dl, j["date"].to_numpy(), cmp_cfg["n_boot"], cmp_cfg["seed"])
            r.update({"ll_ref": float(row_ll(Pr, y).mean()), "ll_cand": float(row_ll(Pc, y).mean()),
                      "delta_ll": float(dl.mean()), "ci95_delta_ll": ci, "delta_brier": float(db.mean()),
                      "rps_ref": float(row_rps(Pr, y).mean()), "rps_cand": float(row_rps(Pc, y).mean()),
                      "p_one_sided": pv,
                      "mean_p_draw_ref": float(Pr[:, 1].mean()), "mean_p_draw_cand": float(Pc[:, 1].mean()),
                      "observed_draw": float((y == 1).mean())})
            rows.append(r)
    C = pd.DataFrame(rows)
    deployable = ~C["candidate"].isin(["market_close_BENCHMARK", "served_model_1x2_json",
                                       "dc180_frozen_at_holdout_start"])
    fam = C["p_one_sided"].notna() & deployable
    C.loc[fam, "p_holm"] = holm(C.loc[fam, "p_one_sided"].to_numpy())

    def verdict(r):
        if r.get("verdict") == "NOT_COMPARABLE":
            return "NOT_COMPARABLE"
        if not np.isfinite(r.get("p_holm", np.nan)):
            return "BENCHMARK_ONLY"
        if r["n_common"] < cmp_cfg["min_n_rows"] or r["matchdays"] < cmp_cfg["min_matchdays"]:
            return "INSUFFICIENT_N"
        ok = (r["p_holm"] < cmp_cfg["family_alpha"] and -r["delta_ll"] >= cmp_cfg["min_effect_logloss"]
              and r["delta_brier"] <= cmp_cfg["max_brier_worsening"])
        return "BETTER_THAN_REFERENCE" if ok else "NOT_SHOWN_BETTER"
    C["verdict"] = C.apply(verdict, axis=1)
    C.to_csv(out / "comparison.csv", index=False)

    # Against the BETTABLE market (entry price), holdout: does the best model or the blend know
    # something the entry price does not? Own Holm family (2 tests), same bootstrap.
    vm = []
    for n in (best, "blend_entry"):
        p = preds["dc180"] if n == "dc180" else cand.get(n)
        if p is None or not len(p):
            continue
        j = mk_e.merge(p, on="row_id", suffixes=("_m", "_c")).merge(lab, on="row_id")
        j = j[(j["date"] >= HOLD_START) & (j["date"] <= HOLD_END)]
        if len(j) < 30:
            continue
        y = j["y"].to_numpy()
        dl = (row_ll(j[[f"p_{k}_c" for k in OUTCOMES]].to_numpy(), y)
              - row_ll(j[[f"p_{k}_m" for k in OUTCOMES]].to_numpy(), y))
        pv, ci = paired_bootstrap(dl, j["date"].to_numpy(), cmp_cfg["n_boot"], cmp_cfg["seed"])
        vm.append({"candidate": n, "reference": "market_entry", "n_common": int(len(j)),
                   "matchdays": int(j["date"].nunique()), "delta_ll": float(dl.mean()),
                   "ci95_delta_ll": ci, "p_one_sided": pv})
    V = pd.DataFrame(vm)
    if len(V):
        V["p_holm"] = holm(V["p_one_sided"].to_numpy())
    V.to_csv(out / "vs_entry_market.csv", index=False)

    # model vs market per league (holdout, rows with both entry and close)
    pl = []
    allp = {"dc180": ref, **{k: v for k, v in cand.items()}}
    H = lab[(lab["date"] >= HOLD_START) & (lab["date"] <= HOLD_END)]
    for lg, g in H.groupby("league"):
        base = g.merge(mk_e, on="row_id").merge(mk_c, on="row_id", suffixes=("_e", "_c"))
        r = {"league": lg, "holdout_rows": int(len(g)), "rows_with_entry_and_close": int(len(base))}
        if len(base) >= 30:
            y = base["y"].to_numpy()
            r["ll_market_entry"] = float(row_ll(base[[f"p_{k}_e" for k in OUTCOMES]].to_numpy(), y).mean())
            r["ll_market_close"] = float(row_ll(base[[f"p_{k}_c" for k in OUTCOMES]].to_numpy(), y).mean())
            for n in ("dc180", best, "blend_entry"):
                p = allp.get(n)
                if p is None:
                    continue
                jj = base[["row_id", "y"]].merge(p, on="row_id")
                if len(jj) >= 30:
                    r[f"ll_{n}"] = float(row_ll(jj[[f"p_{k}" for k in OUTCOMES]].to_numpy(),
                                                jj["y"].to_numpy()).mean())
                    r[f"n_{n}"] = int(len(jj))
        pl.append(r)
    pd.DataFrame(pl).to_csv(out / "per_league_vs_market.csv", index=False)

    # diagnosis tables
    report["diagnosis"] = diagnose(M, ref, served, lab)

    # selection families on bettable entry odds, chosen on WF, checked once on the holdout
    sel_src = best_pred.merge(lab, on="row_id").merge(
        mkt[["row_id", "bet_class"] + [f"bet_{k}" for k in OUTCOMES] + [f"o_close_{k}" for k in OUTCOMES]],
        on="row_id")
    wf = sel_src[(sel_src["date"] >= WF_START) & (sel_src["date"] < HOLD_START)]
    ho = sel_src[(sel_src["date"] >= HOLD_START) & (sel_src["date"] <= HOLD_END)]
    grid = rule_grid(sorted(sel_src["league"].unique()))
    wf_res = []
    for r in grid:
        b = candidate_bets(wf, r)
        wf_res.append({"rule": rule_name(r), **r, "wf_n": int(len(b)),
                       "wf_roi": float(b["pnl"].mean()) if len(b) else np.nan})
    W = pd.DataFrame(wf_res)
    carried = []
    for famname, g in W[W["family"] != "league_wide"].groupby("family"):
        g = g[g["wf_n"] >= SEL_MIN_N_WF]
        if len(g):
            carried.append(g.sort_values(["wf_roi"], ascending=False).iloc[0]["rule"])
    lw = W[(W["family"] == "league_wide") & (W["wf_n"] >= SEL_MIN_N_WF) & (W["wf_roi"] > 0)]
    carried += lw["rule"].tolist()
    hres = []
    for r in grid:
        name = rule_name(r)
        if name not in carried:
            continue
        b = candidate_bets(ho, r)
        rec = {"rule": name, **r, "hold_n": int(len(b))}
        if len(b):
            pv, ci = ROI_bootstrap(b["pnl"].to_numpy(), b["date"].to_numpy(), cmp_cfg["n_boot"], cmp_cfg["seed"])
            rec.update({"hold_roi": float(b["pnl"].mean()), "hold_ci95": ci, "p_one_sided": pv,
                        "hold_clv_mean": float(b["clv"].mean()) if "clv" in b and b["clv"].notna().any() else np.nan,
                        "mean_odds": float(b["odds"].mean())})
        hres.append(rec)
    Hd = pd.DataFrame(hres)
    if len(Hd) and "p_one_sided" in Hd:
        Hd["p_holm"] = holm(Hd["p_one_sided"].to_numpy())
        roi = Hd["hold_roi"] if "hold_roi" in Hd.columns else pd.Series(np.nan, index=Hd.index)
        clv = Hd["hold_clv_mean"] if "hold_clv_mean" in Hd.columns else pd.Series(np.nan, index=Hd.index)
        Hd["verdict"] = np.where((Hd["hold_n"] >= PROVEN_MIN_N) & (Hd["p_holm"] < 0.05), "PROVEN",
                                 np.where((roi > 0) & (clv > 0), "PROMISING", "UNPROVEN"))
    W.to_csv(out / "selection_wf.csv", index=False)
    Hd.merge(W[["rule", "wf_n", "wf_roi"]], on="rule", how="left").to_csv(out / "selection_holdout.csv", index=False)
    report["selection"] = {"configs_searched_on_wf": int(len(W)), "carried_to_holdout": int(len(Hd)),
                           "probability_used": best, "bettable_price": "football-data B365 pre-match; "
                           "sharp tracker opening h2h where football-data has none (book not recorded)"}
    (out / "review.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(C[C["stage"] == "holdout"][["candidate", "n_common", "delta_ll", "p_holm", "verdict"]].to_string())
    return 0


def served_model_predictions(M: pd.DataFrame) -> pd.DataFrame | None:
    """The committed output/model_1x2.json (what paper_1x2 serves), scored on the holdout by the
    exact names it was fitted on; rows it cannot rate are absent (that IS its coverage)."""
    f = ROOT / "output" / "model_1x2.json"
    if not f.exists():
        return None
    from src.data import v9_config
    raw = (json.loads(f.read_text(encoding="utf-8")) or {}).get("leagues", {}) or {}
    models = {}
    for k, v in raw.items():
        c = v9_config.canonical_league(k)
        if c is not None:
            models[c] = v
    H = M[(M["date"] >= HOLD_START) & (M["date"] <= HOLD_END)]
    rows = []
    for lg, h, a, rid in zip(H["league"], H["home_team"].astype(str), H["away_team"].astype(str), H["row_id"]):
        m = models.get(lg)
        if not m:
            continue
        pr = dc.predict(m, h, a)
        if pr:
            rows.append((rid, pr["p_home"], pr["p_draw"], pr["p_away"]))
    return pd.DataFrame(rows, columns=["row_id", "p_home", "p_draw", "p_away"])


def diagnose(M, ref, served, lab) -> dict:
    H = M[(M["date"] >= HOLD_START) & (M["date"] <= HOLD_END)]
    d = {"holdout_rows": int(len(H))}
    if served is not None:
        meta = json.loads((ROOT / "output" / "model_1x2.json").read_text(encoding="utf-8"))
        d["served_model"] = {"trained_at_cutoff": meta.get("trained_at_cutoff"),
                             "leagues": len(meta.get("leagues", {})),
                             "holdout_rows_rated": int(len(served)),
                             "holdout_coverage": round(len(served) / max(len(H), 1), 4)}
    # home advantage and draw rate by season-year, observed
    M2 = M.assign(yr=M["date"].dt.year)
    d["observed_by_year"] = M2.groupby("yr").apply(
        lambda g: {"n": int(len(g)), "home": round(float((g["y"] == 0).mean()), 4),
                   "draw": round(float((g["y"] == 1).mean()), 4),
                   "away": round(float((g["y"] == 2).mean()), 4)}).to_dict()
    j = ref.merge(lab, on="row_id")
    j = j[(j["date"] >= HOLD_START) & (j["date"] <= HOLD_END)]
    d["dc180_holdout_calibration_by_outcome"] = {
        k: {"mean_p": round(float(j[f"p_{k}"].mean()), 4),
            "observed": round(float((j["y"] == i).mean()), 4)} for i, k in enumerate(OUTCOMES)}
    bins = pd.cut(j["p_draw"], [0, .2, .24, .27, .3, .35, 1])
    d["dc180_draw_reliability"] = {
        str(k): {"n": int(len(g)), "mean_p": round(float(g["p_draw"].mean()), 4),
                 "observed": round(float((g["y"] == 1).mean()), 4)}
        for k, g in j.groupby(bins, observed=True)}
    return d


if __name__ == "__main__":
    raise SystemExit(main())
