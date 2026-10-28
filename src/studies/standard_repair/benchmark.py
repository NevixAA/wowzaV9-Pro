"""STANDARD v9 FORENSIC REPAIR — Phase 2: repaired benchmark (owner brief 2026-10-28, P1).

    python -m src.studies.standard_repair benchmark [--skip-wf] [--arms a,b]

Gate: forensic.require_data_quality() — no model research without a PASS, CURRENT data_quality.json.

IDENTICAL CHRONOLOGICAL BLOCKS. Quarterly blocks from EVAL_START; every arm's block is scored by a model
fitted only on rows dated before the block. DISCOVERY = blocks before CONFIRM_START, CONFIRMATION =
blocks from CONFIRM_START. Every arm is scored on the SAME rows (the benchmark frame's standard rows that
have a genuine two-sided pre-match OU2.5 price and a prediction from every arm).

ARMS
  MARKET            OU25: genuine pre-match two-sided consensus (power de-vig, median of Avg/B365/Pinnacle/
                    Betfair-exchange, football-data non-closing columns = FD_PREMATCH_APPROX).
                    BTTS / OU15: SYNTHETIC_MARKET_PROXY — the market's goal expectation inverted from the
                    pre-match OU2.5 + 1X2 (independent Poisson). Conclusions say "did / did not improve
                    the synthetic proxy", never "beat the BTTS market".
  LEGACY_V9_REPRO   v9's own trainer, legacy recipe, on v9's legacy frame (duplicates and all), side
                    models pooled Std+NF as served; scored in ISO-week batches (batch-median imputation).
  LEGACY_ON_CANON   the same legacy recipe on the identity-repaired frame (isolates the identity fix).
  V9_REPAIRED       R1's repaired recipe (persisted train-only imputer, parity fixes, weights, stacking,
                    no closing contamination) on the identity-repaired frame, track-specific side models.
  MKT_RESID_LR      logit(p) = logit(p_market) + f(features): ridge logistic on clean football features,
                    pooled with league intercepts (partial pooling through the ridge penalty).
  MKT_RESID_HGB     the same anchor with a shallow gradient-boosted residual (init_score = logit p_market).
  BASE_RATE         league as-of base rate.  POISSON_FORM  form Poisson, Platt-calibrated on train.
Market-feature experiment: legacy recipe with bookmaker_overround from CLOSING (as v9) vs TRUE_ASOF
(pre-match) vs NONE. History windows: all / modern / recent3 / recent2 / weighted.

STATISTICS. Paired log-loss and Brier differences vs MARKET, matchday-week block bootstrap (2000), N,
independent gameweeks and CI everywhere; BH-FDR over the discovery family; a cell is CONFIRMED only when
its confirmation-period difference has the same sign and a one-sided bootstrap p < 0.05. NO threshold
is optimised anywhere. ROI and CLV only for OU25 against FD_PREMATCH_APPROX entries and FD_CLOSING closes;
BTTS/OU15 ROI/CLV columns are blank = NOT CERTIFIABLE.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair import fingerprint as FP
from src.studies.standard_repair import forensic as F
from src.studies.standard_repair import identity as ID
from src.studies.standard_repair import prices as PR
from src.studies.standard_repair.candidates import Prep, pen_logit, _pred
from src.studies.standard_repair.data import (FD_CODES, X12_BOOKS, logit, market_goal_split, poisson_market_probs,
                                              power_devig, prop_devig3, sig)
from src.studies.standard_repair.evaluate import bh, block_boot, calib, ll, paired

OUT = F.OUT
WF = F.REBUILD / "wf"
EVAL_START = "2024-07-01"
CONFIRM_START = "2026-01-01"
MARKETS = {"OU25": "over25", "BTTS": "btts", "OU15": "over15"}
SIDES = {"OU25": ("OVER", "UNDER"), "BTTS": ("YES", "NO"), "OU15": ("OVER", "UNDER")}
GROUPS = {
    "form_goals": ["home_scored_last5", "away_scored_last5", "home_conceded_last5", "away_conceded_last5",
                   "home_over25_last5", "away_over25_last5"],
    "attack_defence": ["home_attack_str", "away_attack_str", "home_defense_str", "away_defense_str"],
    "season_venue": ["home_season_goals_h", "away_season_goals_a", "home_season_conceded_h", "away_season_conceded_a",
                     "home_cs_rate_h", "away_cs_rate_a"],
    "shots_sot": ["combined_sot_ratio", "home_sot_last5", "away_sot_last5", "home_shots_last5", "away_shots_last5"],
    "corners_fouls": ["home_corners_pg_roll", "away_corners_pg_roll", "home_fouls_pg_roll", "away_fouls_pg_roll"],
    "halftime": ["home_ht_scored_last5", "away_ht_scored_last5", "home_ht_conceded_last5", "away_ht_conceded_last5",
                 "combined_ht_goals_avg", "home_ht_over05_rate", "away_ht_over05_rate"],
    "venue_adv": ["home_advantage", "away_home_adv_factor"],
    "rest": ["home_rest_days", "away_rest_days"],
    "poisson": ["p_over25_poisson_dc", "form_gap"],
    "league_env": ["league_avg_goals", "env_rate"],
}
LEGACY_THRESH = {"SNIPER": 0.10, "MARKSMAN": 0.08}       # only used to REPRODUCE legacy selection


# ── market table ────────────────────────────────────────────────────────────────────────────────
def _fd_1x2(fd_dir: Path) -> pd.DataFrame:
    rows = []
    for league, code in FD_CODES.items():
        for f in sorted(fd_dir.glob(f"{code}_*.csv")):
            try:
                d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
            except UnicodeDecodeError:
                d = pd.read_csv(f, encoding="latin-1", low_memory=False)
            if not {"Date", "HomeTeam", "AwayTeam"} <= set(d.columns):
                continue
            d = d.dropna(subset=["HomeTeam", "AwayTeam"])
            r = pd.DataFrame({"league": league, "date": pd.to_datetime(d["Date"], dayfirst=True, errors="coerce").dt.normalize(),
                              "home_team": d["HomeTeam"].astype(str).str.strip(), "away_team": d["AwayTeam"].astype(str).str.strip()})
            for bk, (h, x, a) in X12_BOOKS.items():
                for c, s in (("h", h), ("d", x), ("a", a)):
                    r[f"{c}_{bk}"] = pd.to_numeric(d.get(s), errors="coerce")
            rows.append(r)
    return pd.concat(rows, ignore_index=True).dropna(subset=["date"]).drop_duplicates(["league", "date", "home_team", "away_team"])


def market_table(std: pd.DataFrame, amap: dict) -> pd.DataFrame:
    fd_dir = F._fd_dir()
    ou = PR.fd_ou25_rows(fd_dir, FD_CODES)
    x12 = _fd_1x2(fd_dir)
    for f in (ou, x12):
        for c in ("home_team", "away_team"):
            f[c] = [amap.get(lg, {}).get(t, t) for lg, t in zip(f["league"], f[c])]
    ou = ou.drop(columns=["file"]).drop_duplicates(["league", "date", "home_team", "away_team"])
    x12 = x12.drop_duplicates(["league", "date", "home_team", "away_team"])
    k = ["league", "date", "home_team", "away_team"]
    m = std[k].merge(ou, on=k, how="left").merge(x12, on=k, how="left")
    books = ["AVG", "B365", "PIN", "BFE"]
    P = np.column_stack([power_devig(m[f"o_{b}"], m[f"u_{b}"]) for b in books])
    with np.errstate(all="ignore"):
        m["pm_OU25"] = np.nanmedian(np.where(np.isfinite(P), P, np.nan), axis=1)
    m["n_books"] = np.isfinite(P).sum(1)
    m["pclose_OU25"] = power_devig(m["o_AVGC"], m["u_AVGC"])
    m["entry_over"] = m["o_AVG"].fillna(m["o_B365"])
    m["entry_under"] = m["u_AVG"].where(m["o_AVG"].notna(), m["u_B365"])
    m["close_over"], m["close_under"] = m["o_AVGC"], m["u_AVGC"]
    ph, pdr, pa = [], [], []
    for bk in X12_BOOKS:
        h, x, a = prop_devig3(m[f"h_{bk}"], m[f"d_{bk}"], m[f"a_{bk}"])
        ph.append(h), pdr.append(x), pa.append(a)
    with np.errstate(all="ignore"):
        m["p1x2_h"], m["p1x2_a"] = np.nanmedian(np.vstack(ph), 0), np.nanmedian(np.vstack(pa), 0)
    lh, la = market_goal_split(m["pm_OU25"].to_numpy(), m["p1x2_h"].to_numpy(), m["p1x2_a"].to_numpy())
    pois = poisson_market_probs(lh, la)
    m["pm_BTTS"], m["pm_OU15"] = pois["BTTS"], pois["OU15"]
    m["market_class_OU25"] = np.where(m["pm_OU25"].notna(), "GENUINE_PREMATCH_TWO_SIDED", None)
    m["market_class_BTTS"] = m["market_class_OU15"] = np.where(m["pm_BTTS"].notna(), "SYNTHETIC_MARKET_PROXY", None)
    keep = k + ["pm_OU25", "n_books", "pclose_OU25", "entry_over", "entry_under", "close_over", "close_under",
                "pm_BTTS", "pm_OU15", "market_class_OU25", "market_class_BTTS", "market_class_OU15"]
    return m[keep]


# ── v9 walk-forward runs (v9's own trainer, in the v9 checkout) ───────────────────────────────────
def run_wf(name: str, frame: Path, recipe: str = "legacy_v9", side_scope: str = "pooled", window: str = "all",
           drop: str = "", targets: str = "over25,btts,over15", force: bool = False, price_mode: str = "none") -> Path:
    out = WF / f"{name}.parquet"
    if out.exists() and not force:
        return out
    WF.mkdir(parents=True, exist_ok=True)
    # the repaired recipe lives in R1's v9 worktree (V9_REPAIRED_LOCAL); legacy arms use the plain v9 checkout
    v9 = Path((os.getenv("V9_REPAIRED_LOCAL") if recipe != "legacy_v9" else None) or os.getenv("V9_LOCAL") or cfg.V9_LOCAL)
    py = os.getenv("V9_PYTHON") or sys.executable
    cmd = [py, str(Path(__file__).resolve().parent / "v9_wf.py"), "--frame", str(frame), "--out", str(out),
           "--start", EVAL_START, "--recipe", recipe, "--side-scope", side_scope, "--train-window", window,
           "--targets", targets, "--price-mode", price_mode]
    if drop:
        cmd += ["--drop-features", drop]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(cmd, cwd=str(v9), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-3000:] + "\n" + r.stderr[-6000:])
        raise F.IntegrityError(f"walk-forward {name} failed")
    return out


def frame_variant(src: Path, name: str, std_mt: pd.DataFrame | None = None, mode: str = "closing") -> Path:
    """Market-feature experiment frames: bookmaker_overround from CLOSING (v9 as-is), TRUE_ASOF
    (pre-match entry prices) or NONE (feature dropped at train time instead)."""
    out = F.REBUILD / f"frame_{name}.parquet"
    if out.exists():
        return out
    fr = pd.read_parquet(src)
    if mode == "asof":
        fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
        k = ["league", "date", "home_team", "away_team"]
        j = fr[k].merge(std_mt[k + ["entry_over", "entry_under"]], on=k, how="left")
        ov = (1 / j["entry_over"] + 1 / j["entry_under"] - 1).clip(lower=0)
        # standard rows: pre-match overround where known, else NaN (never the closing value)
        isstd = fr["track"].astype(str) == "standard"
        fr.loc[isstd, "bookmaker_overround"] = ov[isstd.to_numpy()].to_numpy()
    fr.to_parquet(out, index=False)
    return out


# ── Pro-side candidates (same blocks) ────────────────────────────────────────────────────────────
def _blocks(d: pd.DataFrame):
    end = d["date"].max() + pd.Timedelta(days=1)
    b = list(pd.date_range(EVAL_START, end, freq="QS")) + [end]
    return list(zip(b[:-1], b[1:]))


def _features(d: pd.DataFrame) -> pd.DataFrame:
    x = d.copy()
    lh = ((x["home_season_goals_h"].fillna(x["home_scored_last5"]) + x["away_season_conceded_a"].fillna(x["away_conceded_last5"])) / 2).clip(0.2, 5)
    la = ((x["away_season_goals_a"].fillna(x["away_scored_last5"]) + x["home_season_conceded_h"].fillna(x["home_conceded_last5"])) / 2).clip(0.2, 5)
    x["form_lh"], x["form_la"] = lh, la
    fp = poisson_market_probs(lh.to_numpy(), la.to_numpy())
    for m in MARKETS:
        x[f"form_pois_{m}"] = fp[m]
    return x


def _env_rate(d: pd.DataFrame, y: str) -> pd.Series:
    out = pd.Series(np.nan, index=d.index)
    for _, g in d.sort_values("date").groupby("league"):
        r = g[y].shift(1).rolling(80, min_periods=20).mean()
        out.loc[g.index] = r.groupby(g["date"]).transform("first")
    return out


def candidates(d: pd.DataFrame, market: str, groups: list[str] | None = None, window: str = "all",
               arms=("MKT_RESID_LR", "MKT_RESID_HGB", "BASE_RATE", "POISSON_FORM")) -> pd.DataFrame:
    y = f"y_{market}"
    pm = f"pm_{market}"
    d = d.copy()
    d["form_gap"] = logit(d[f"form_pois_{market}"]) - logit(d[pm])
    d["env_rate"] = _env_rate(d, y)
    cols = [c for g in (groups or list(GROUPS)) for c in GROUPS[g] if c in d.columns]
    res = pd.DataFrame(index=d.index)
    for b0, b1 in _blocks(d):
        tr = d[(d["date"] < b0) & d[pm].notna() & d[y].notna()]
        if window == "modern":
            tr = tr[tr["row_source"].astype(str).str.startswith("FOOTBALL_DATA")]
        elif window in ("recent3", "recent2"):
            tr = tr[tr["date"] >= b0 - pd.Timedelta(days=365 * int(window[-1]))]
        te = d[(d["date"] >= b0) & (d["date"] < b1) & d[pm].notna()]
        if len(tr) < 1500 or te.empty:
            continue
        w = 0.5 ** ((b0 - tr["date"]).dt.days.to_numpy() / 365.0) if window == "weighted" else None
        lv = sorted(tr["league"].unique())
        L = lambda z: np.column_stack([(z["league"] == l).to_numpy(float) for l in lv])
        if "MKT_RESID_LR" in arms:
            p = Prep(tr, cols)
            Xtr, Xte = np.column_stack([logit(tr[pm])[:, None], p(tr), L(tr)]), np.column_stack([logit(te[pm])[:, None], p(te), L(te)])
            bcoef = pen_logit(Xtr, tr[y], n_free=1, lam=0.02, w=w)
            res.loc[te.index, "MKT_RESID_LR"] = _pred(bcoef, Xte)
        if "MKT_RESID_HGB" in arms:
            from sklearn.ensemble import HistGradientBoostingClassifier
            t = tr.sort_values("date")
            Xc = lambda z: np.column_stack([z[cols].astype(float).to_numpy(), L(z)])
            m = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.03, max_depth=3, min_samples_leaf=300,
                                               l2_regularization=5.0, random_state=7)
            # residual boosting around the market: fit on the market's logit as an offset by
            # augmenting with logit(p_market) and recalibrating the blend chronologically
            cut = int(len(t) * 0.8)
            A, C = t.iloc[:cut], t.iloc[cut:]
            m.fit(np.column_stack([Xc(A), logit(A[pm])]), A[y].astype(int), sample_weight=None)
            raw = lambda z: logit(m.predict_proba(np.column_stack([Xc(z), logit(z[pm])]))[:, 1])
            bc = pen_logit(np.column_stack([logit(C[pm]), raw(C) - logit(C[pm])]), C[y], n_free=2)
            res.loc[te.index, "MKT_RESID_HGB"] = _pred(bc, np.column_stack([logit(te[pm]), raw(te) - logit(te[pm])]))
        if "BASE_RATE" in arms:
            r = te["env_rate"].fillna(tr[y].mean())
            res.loc[te.index, "BASE_RATE"] = r.clip(0.02, 0.98).to_numpy()
        if "POISSON_FORM" in arms:
            fpc = f"form_pois_{market}"
            t2 = tr.dropna(subset=[fpc])
            bcoef = pen_logit(logit(t2[fpc])[:, None], t2[y], n_free=1)
            x_te = logit(te[fpc].fillna(t2[fpc].median()))
            res.loc[te.index, "POISSON_FORM"] = _pred(bcoef, x_te[:, None])
    return res


# ── evaluation ─────────────────────────────────────────────────────────────────────────────────
def _metrics(p, y, pm, weeks) -> dict:
    p, y, pm = np.asarray(p, float), np.asarray(y, float), np.asarray(pm, float)
    dll = ll(p, y) - ll(pm, y)
    dbr = (p - y) ** 2 - (pm - y) ** 2
    out = {"n": int(len(y)), "gameweeks": int(pd.Series(weeks).nunique()),
           "log_loss": round(float(ll(p, y).mean()), 5), "brier": round(float(((p - y) ** 2).mean()), 5)}
    if len(y) >= 30:
        out.update(calib(p, y))
    pr = paired(dll, weeks)
    out.update({"dLL_vs_market": pr["delta"], "dLL_ci95": pr["ci95"], "dLL_p_one_sided": pr["p_one_sided"]})
    pb = paired(dbr, weeks)
    out.update({"dBrier_vs_market": pb["delta"], "dBrier_ci95": pb["ci95"]})
    return out


def _side_money(g: pd.DataFrame, side_over: bool) -> dict:
    """OU25 only: flat 1u at the FD_PREMATCH_APPROX entry of the side the arm leans to; CLV against the
    FD_CLOSING de-vigged probability. No threshold."""
    odds = np.where(side_over, g["entry_over"], g["entry_under"])
    won = np.where(side_over, g["y"] == 1, g["y"] == 0)
    ok = np.isfinite(odds) & (odds > 1)
    pnl = np.where(won, odds - 1, -1.0)[ok]
    pe = np.where(side_over, g["pm"], 1 - g["pm"])
    pc = np.where(side_over, g["pclose_OU25"], 1 - g["pclose_OU25"])
    clv = (pc - pe)[ok & np.isfinite(pc)]
    r = {"roi": round(float(pnl.mean()), 4) if len(pnl) else None, "roi_n": int(ok.sum()),
         "clv_prob_pp": round(float(clv.mean()) * 100, 3) if len(clv) else None, "clv_n": int(len(clv))}
    if len(pnl) >= 20:
        bs = block_boot(pnl, g["week"].to_numpy()[ok])
        r["roi_ci95"] = [round(float(q), 4) for q in np.quantile(bs, [0.025, 0.975])] if bs is not None else None
    return r


def evaluate(E: pd.DataFrame, arms: list[str], market: str) -> tuple[list, list, list]:
    """E: one row per fixture with y, pm, week, league, period and one column per arm (identical rows)."""
    comp, lg_rows, side_rows = [], [], []
    for period, P in (("ALL", E), ("DISCOVERY", E[E["period"] == "DISCOVERY"]), ("CONFIRMATION", E[E["period"] == "CONFIRMATION"])):
        if P.empty:
            continue
        for arm in arms + ["MARKET"]:
            p = P["pm"] if arm == "MARKET" else P[arm]
            comp.append({"market": market, "arm": arm, "period": period, "scope": "ALL",
                         **_metrics(p, P["y"], P["pm"], P["week"])})
            for lg, g in P.groupby("league"):
                pp = g["pm"] if arm == "MARKET" else g[arm]
                lg_rows.append({"market": market, "arm": arm, "period": period, "league": lg,
                                **_metrics(pp, g["y"], g["pm"], g["week"])})
            if arm == "MARKET":
                continue
            for lg, g in list(P.groupby("league")) + [("ALL", P)]:
                over = (g[arm] > g["pm"]).to_numpy()
                for s_i, side in enumerate(SIDES[market]):
                    msk = over if s_i == 0 else ~over
                    h = g[msk]
                    if len(h) < 10:
                        continue
                    row = {"market": market, "arm": arm, "period": period, "league": lg, "side": side,
                           **_metrics(h[arm], h["y"], h["pm"], h["week"])}
                    if market == "OU25":
                        row.update(_side_money(h.assign(y=h["y"]), s_i == 0))
                        row["price_status"] = "CERTIFIABLE_FD_PREMATCH_APPROX"
                    else:
                        row.update({"roi": None, "clv_prob_pp": None, "price_status": "NOT_CERTIFIABLE_SYNTHETIC_MARKET_PROXY"})
                    side_rows.append(row)
    return comp, lg_rows, side_rows


def rank_test(E: pd.DataFrame, arm: str, market: str) -> list:
    """Per league x ISO week: rank fixtures by |p_arm - p_market|; Top1/2/3/5 (each a superset)."""
    out = []
    d = E.copy()
    d["gap"] = (d[arm] - d["pm"]).abs()
    d["rk"] = d.groupby(["league", "week"])["gap"].rank(ascending=False, method="first")
    for k in (1, 2, 3, 5):
        h = d[d["rk"] <= k]
        if len(h) < 20:
            continue
        r = {"market": market, "arm": arm, "top_k": k, **_metrics(h[arm], h["y"], h["pm"], h["week"])}
        if market == "OU25":
            over = (h[arm] > h["pm"]).to_numpy()
            mo, mu = _side_money(h[over], True), _side_money(h[~over], False)
            n = mo["roi_n"] + mu["roi_n"]
            r["roi"] = round(((mo["roi"] or 0) * mo["roi_n"] + (mu["roi"] or 0) * mu["roi_n"]) / n, 4) if n else None
            r["roi_n"] = n
            cn = mo["clv_n"] + mu["clv_n"]
            r["clv_prob_pp"] = round(((mo["clv_prob_pp"] or 0) * mo["clv_n"] + (mu["clv_prob_pp"] or 0) * mu["clv_n"]) / cn, 3) if cn else None
        out.append(r)
    return out
