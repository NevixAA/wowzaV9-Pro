"""The benchmark arms. Every arm is `fit_predict(train, test, market, hp) -> P(OVER / YES)` for the test rows.

Fitting discipline: an arm sees only `train` (rows dated strictly before the test block). Imputation
medians, scaling, bin edges, calibration maps and hyperparameters-in-use all come from `train` alone.
Hyperparameter GRIDS are chosen on the validation period by evaluate.py, never on the holdout.

Arm families (the brief's directions, each a separate testable arm):
  MARKET_*         market-only baselines (per-book / consensus de-vig, walk-forward Platt)
  V9, V9_CAL       v9's recipe reproduced walk-forward (its own trainer), raw and Platt-recalibrated
  MKT_LEAGUE*      market + league intercepts (partial pooling = ridge toward the global fit), +slopes
  MKT_V9_RESID     market + lightweight Wowza residual: a + b*logit(m) + c*(logit(v9) - logit(m)), c ridge
  MKT_V9_BANDS     market + disagreement bands as FEATURES (dummies of the v9-vs-market gap), not thresholds
  MKT_SIMPLE/NO_NOISY/FULL   market + goal-only / v9-minus-shots-corners-HT-xG / all v9 inputs (ridge)
  MKT_POISSON      market + Poisson-from-form vs market goal expectation gaps
  MKT_ENV          market + dynamic league scoring environment (as-of rolling realised vs market-implied)
  MKT_KITCHEN      market + SIMPLE + POISSON + ENV + v9 residual (ridge)
  MKT_SIMPLE_RECENCY  MKT_SIMPLE with exponential recency weights
  LGBM_RESID_*     LightGBM on the MARKET-RESIDUAL target (init_score = logit(market)), heavy regularisation
  HGB_ANCHOR_CAL   HistGradientBoosting with logit(market) as a feature, Platt-calibrated on a later slice
  HGB_ABS_CAL      HistGradientBoosting absolute probability, no market (v9-style), calibrated
  LR_ABS_SIMPLE    logistic absolute probability on SIMPLE features, no market
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.studies.standard_repair.data import feature_lists, logit, sig

FL = feature_lists()
ENV = {"OU25": ["env_goals", "env_gap_goals", "env_over25", "env_mktres_OU25"],
       "BTTS": ["env_goals", "env_gap_goals", "env_btts", "env_mktres_BTTS"],
       "OU15": ["env_goals", "env_gap_goals", "env_over15", "env_mktres_OU15"]}


def anchor_col(market: str) -> str:
    return "pm_OU25_CONS_power" if market == "OU25" else f"pm_{market}_POIS"


# ── penalised logistic with offset and unpenalised columns ─────────────────────────────────────
def pen_logit(X, y, offset=None, n_free: int = 0, lam: float = 0.0, w=None, iters: int = 50):
    """min mean_w NLL(y, sig(offset + [1, X] b)) + lam/2 * ||b_pen||^2.
    Column 0 (intercept) and the first `n_free` columns of X are unpenalised."""
    X = np.column_stack([np.ones(len(X)), np.asarray(X, float)])
    y = np.asarray(y, float)
    off = np.zeros(len(y)) if offset is None else np.asarray(offset, float)
    w = np.ones(len(y)) if w is None else np.asarray(w, float)
    w = w / w.mean()
    pen = np.ones(X.shape[1]) * lam
    pen[: 1 + n_free] = 0.0
    pen += 1e-8
    b = np.zeros(X.shape[1])
    n = len(y)
    for _ in range(iters):
        mu = sig(off + X @ b)
        g = X.T @ (w * (mu - y)) / n + pen * b
        H = (X.T * (w * mu * (1 - mu))) @ X / n + np.diag(pen)
        step = np.linalg.solve(H, g)
        b -= step
        if np.abs(step).max() < 1e-8:
            break
    return b


def _pred(b, X, offset=None):
    X = np.column_stack([np.ones(len(X)), np.asarray(X, float)])
    off = 0.0 if offset is None else np.asarray(offset, float)
    return sig(off + X @ b)


class Prep:
    """Median-impute + standardise with TRAIN statistics only."""

    def __init__(self, tr: pd.DataFrame, cols):
        self.cols = list(cols)
        X = tr[self.cols].astype(float)
        self.med = X.median()
        Xf = X.fillna(self.med)
        self.mu, self.sd = Xf.mean(), Xf.std().replace(0, 1).fillna(1)

    def __call__(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self.cols].astype(float).fillna(self.med)
        return ((X - self.mu) / self.sd).fillna(0.0).to_numpy()


def _league_dummies(tr, te):
    lv = sorted(tr["league"].unique())
    f = lambda d: np.column_stack([(d["league"] == l).to_numpy(float) for l in lv])
    return f(tr), f(te)


def _recency_w(tr, half_life_days):
    if not half_life_days:
        return None
    age = (tr["date"].max() - tr["date"]).dt.days.to_numpy(float)
    return 0.5 ** (age / half_life_days)


# ── extra derived columns (pure functions of as-of inputs) ────────────────────────────────────
def derived(df: pd.DataFrame, market: str) -> pd.DataFrame:
    a = logit(df[anchor_col(market)])
    out = pd.DataFrame(index=df.index)
    out["lm"] = a
    if f"p_v9_{market}" in df:
        out["v9_gap"] = logit(df[f"p_v9_{market}"]) - a
    out["pois_gap"] = logit(df[f"form_pois_{market}"]) - a
    return out


def _with_derived(df, market):
    return pd.concat([df, derived(df, market)], axis=1)


# ── arms ──────────────────────────────────────────────────────────────────────────────────────
def arm_market_col(col):
    """A single book / variant; where that book is missing the consensus fills in (so every arm is
    scored on the same rows)."""
    def f(tr, te, market, hp):
        return te[col].fillna(te["pm_OU25_CONS_power"]).to_numpy(float)
    return f


def arm_market_cal(tr, te, market, hp):
    col = anchor_col(market)
    b = pen_logit(logit(tr[col])[:, None], tr[f"y_{market}"], n_free=1)
    return _pred(b, logit(te[col])[:, None])


def arm_v9(tr, te, market, hp):
    return te[f"p_v9_{market}"].to_numpy(float)


def arm_v9_cal(tr, te, market, hp):
    t = tr.dropna(subset=[f"p_v9_{market}"])
    b = pen_logit(logit(t[f"p_v9_{market}"])[:, None], t[f"y_{market}"], n_free=1)
    return _pred(b, logit(te[f"p_v9_{market}"])[:, None])


def _anchored(tr, te, market, extra_tr, extra_te, lam, w=None):
    """a + b*logit(m) unpenalised, extra columns ridge-penalised."""
    lm_tr, lm_te = logit(tr[anchor_col(market)])[:, None], logit(te[anchor_col(market)])[:, None]
    Xtr = np.column_stack([lm_tr, extra_tr]) if extra_tr is not None else lm_tr
    Xte = np.column_stack([lm_te, extra_te]) if extra_te is not None else lm_te
    b = pen_logit(Xtr, tr[f"y_{market}"], n_free=1, lam=lam, w=w)
    return _pred(b, Xte)


def arm_mkt_league(tr, te, market, hp):
    dtr, dte = _league_dummies(tr, te)
    return _anchored(tr, te, market, dtr, dte, hp["lam"])


def arm_mkt_league_slope(tr, te, market, hp):
    dtr, dte = _league_dummies(tr, te)
    ltr, lte = logit(tr[anchor_col(market)])[:, None], logit(te[anchor_col(market)])[:, None]
    return _anchored(tr, te, market, np.column_stack([dtr, dtr * ltr]), np.column_stack([dte, dte * lte]), hp["lam"])


def _cols_arm(cols_fn, need_v9=False, recency=None, league=False):
    def f(tr, te, market, hp):
        t = tr.dropna(subset=[f"p_v9_{market}"]) if need_v9 else tr
        T, E = _with_derived(t, market), _with_derived(te, market)
        cols = cols_fn(market)
        p = Prep(T, cols)
        xtr, xte = p(T), p(E)
        if league:
            dtr, dte = _league_dummies(T, E)
            xtr, xte = np.column_stack([xtr, dtr]), np.column_stack([xte, dte])
        return _anchored(T, E, market, xtr, xte, hp["lam"], w=_recency_w(T, recency))
    return f


def arm_v9_bands(tr, te, market, hp):
    t = tr.dropna(subset=[f"p_v9_{market}"])
    gt, ge = derived(t, market)["v9_gap"].to_numpy(), derived(te, market)["v9_gap"].to_numpy()
    edges = np.quantile(gt, [0.1, 0.3, 0.7, 0.9])
    D = lambda g: np.column_stack([(np.digitize(g, edges) == k).astype(float) for k in (0, 1, 3, 4)])
    return _anchored(t, te, market, D(gt), D(ge), hp["lam"])


def _lgbm_arm(cols_fn):
    def f(tr, te, market, hp):
        import lightgbm as lgb
        T, E = _with_derived(tr, market), _with_derived(te, market)
        cols = cols_fn(market)
        m = lgb.LGBMClassifier(n_estimators=hp["n"], learning_rate=0.02, num_leaves=7, max_depth=3,
                               min_child_samples=300, reg_lambda=10.0, subsample=0.8, subsample_freq=1,
                               colsample_bytree=0.8, random_state=7, verbose=-1)
        m.fit(T[cols].astype(float), T[f"y_{market}"].astype(int), init_score=T["lm"].to_numpy())
        raw = m.predict(E[cols].astype(float), raw_score=True)
        return sig(E["lm"].to_numpy() + raw)
    return f


def _hgb_arm(cols_fn, with_market: bool):
    def f(tr, te, market, hp):
        from sklearn.ensemble import HistGradientBoostingClassifier
        T, E = _with_derived(tr, market), _with_derived(te, market)
        cols = cols_fn(market) + (["lm"] if with_market else [])
        T = T.sort_values("date")
        cut = int(len(T) * 0.8)                 # chronological: fit on first 80%, calibrate on last 20%
        A, C = T.iloc[:cut], T.iloc[cut:]
        m = HistGradientBoostingClassifier(max_iter=hp["n"], learning_rate=0.05, max_depth=3, min_samples_leaf=200,
                                           l2_regularization=1.0, random_state=7)
        m.fit(A[cols].astype(float), A[f"y_{market}"].astype(int))
        pc = m.predict_proba(C[cols].astype(float))[:, 1]
        b = pen_logit(logit(pc)[:, None], C[f"y_{market}"], n_free=1)
        return _pred(b, logit(m.predict_proba(E[cols].astype(float))[:, 1])[:, None])
    return f


def arm_lr_abs_simple(tr, te, market, hp):
    p = Prep(tr, FL["SIMPLE"])
    b = pen_logit(p(tr), tr[f"y_{market}"], lam=hp["lam"])
    return _pred(b, p(te))


LAM = [{"lam": x} for x in (0.001, 0.01, 0.1)]
NTREE = [{"n": x} for x in (100, 300)]
POIS = ["pois_gap", "lh_gap", "la_gap"]

#: name -> (fn, hyperparameter grid, needs v9 OOS rows in training, description)
ARMS = {
    "MARKET_AVG_power": (arm_market_col("pm_OU25_AVG_power"), [{}], False, "average-of-books price, power de-vig"),
    "MARKET_AVG_prop": (arm_market_col("pm_OU25_AVG_prop"), [{}], False, "average-of-books price, proportional de-vig"),
    "MARKET_B365_power": (arm_market_col("pm_OU25_B365_power"), [{}], False, "Bet365, power de-vig"),
    "MARKET_CONS_power": (arm_market_col("pm_OU25_CONS_power"), [{}], False, "median over books quoting both sides, power"),
    "MARKET_POIS": (None, [{}], False, "market goal expectation from pre-match 1X2 + O/U 2.5, independent Poisson"),
    "MARKET_CAL": (arm_market_cal, [{}], False, "consensus market, walk-forward Platt recalibration"),
    "V9": (arm_v9, [{}], True, "v9's recipe, v9's own trainer, walk-forward"),
    "V9_CAL": (arm_v9_cal, [{}], True, "v9 walk-forward, Platt-recalibrated"),
    "MKT_LEAGUE": (arm_mkt_league, LAM, False, "market + league intercepts (ridge partial pooling)"),
    "MKT_LEAGUE_SLOPE": (arm_mkt_league_slope, LAM, False, "market + league intercepts and slopes (per-league calibration)"),
    "MKT_V9_RESID": (_cols_arm(lambda m: ["v9_gap"], need_v9=True), LAM, True, "market + v9 logit residual (lightweight Wowza residual)"),
    "MKT_V9_BANDS": (arm_v9_bands, LAM, True, "market + v9-vs-market disagreement bands as features"),
    "MKT_SIMPLE": (_cols_arm(lambda m: FL["SIMPLE"]), LAM, False, "market + goal-only team features"),
    "MKT_NO_NOISY": (_cols_arm(lambda m: FL["NO_NOISY"]), LAM, False, "market + v9 inputs minus shots/corners/fouls/xG/HT"),
    "MKT_FULL": (_cols_arm(lambda m: FL["FULL"]), LAM, False, "market + all v9 inputs (odds-derived removed)"),
    "MKT_POISSON": (_cols_arm(lambda m: POIS), LAM, False, "market + Poisson-from-form vs market goal gaps"),
    "MKT_ENV": (_cols_arm(lambda m: ENV[m], league=True), LAM, False, "market + dynamic league scoring environment + league"),
    "MKT_KITCHEN": (_cols_arm(lambda m: FL["SIMPLE"] + POIS + ENV[m] + ["v9_gap"], need_v9=True), LAM, True,
                    "market + SIMPLE + Poisson + environment + v9 residual"),
    "MKT_SIMPLE_RECENCY": (_cols_arm(lambda m: FL["SIMPLE"], recency=365), LAM, False, "MKT_SIMPLE, recency half-life 365 d"),
    "LGBM_RESID_SIMPLE": (_lgbm_arm(lambda m: FL["SIMPLE"] + POIS + ENV[m]), NTREE, False,
                          "LightGBM on market-residual target, goal + Poisson + environment features"),
    "LGBM_RESID_FULL": (_lgbm_arm(lambda m: FL["FULL"] + POIS + ENV[m]), NTREE, False,
                        "LightGBM on market-residual target, all v9 inputs + Poisson + environment"),
    "HGB_ANCHOR_CAL": (_hgb_arm(lambda m: FL["SIMPLE"] + POIS + ENV[m], True), NTREE, False,
                       "HGB with market logit as a feature, Platt on a later slice"),
    "HGB_ABS_CAL": (_hgb_arm(lambda m: FL["FULL"], False), NTREE, False, "HGB absolute probability, no market, calibrated"),
    "LR_ABS_SIMPLE": (arm_lr_abs_simple, LAM, False, "logistic absolute probability, goal-only features, no market"),
}
ARMS["MARKET_POIS"] = (lambda tr, te, market, hp: te[anchor_col(market)].to_numpy(float), [{}], False,
                       ARMS["MARKET_POIS"][3])
MARKET_VARIANTS = {"OU25": ["MARKET_AVG_power", "MARKET_AVG_prop", "MARKET_B365_power", "MARKET_CONS_power", "MARKET_CAL"],
                   "BTTS": ["MARKET_POIS", "MARKET_CAL"], "OU15": ["MARKET_POIS", "MARKET_CAL"]}


def arms_for(market: str) -> list[str]:
    skip = {"MARKET_AVG_power", "MARKET_AVG_prop", "MARKET_B365_power", "MARKET_CONS_power"} if market != "OU25" \
        else {"MARKET_POIS"}
    return [a for a in ARMS if a not in skip]
