"""Frozen, persistable versions of the Phase-2 market-anchored residual arms (OU25 only).

The benchmark (benchmark.candidates) fits MKT_RESID_LR / MKT_RESID_HGB inside its walk-forward
loop and never keeps the fitted object. The forward shadow needs the SAME arms as objects that are
fitted once (TRAIN, rows strictly before the training cutoff), pickled, hashed and then applied
unchanged to live fixtures. `fit_resid` / `predict_resid` reproduce candidates() exactly for one
block (tests/test_standard_repair_shadow.py proves it on synthetic data):

  MKT_RESID_LR   logit p = a + b*logit(p_market) + ridge(lam 0.02) on standardised GROUPS features
                 + league intercepts; train medians / means / sds persisted (no batch statistics).
  MKT_RESID_HGB  HistGradientBoosting(150, lr .03, depth 3, leaf 300, l2 5) on GROUPS + league
                 dummies + logit(p_market), fitted on the first 80% of training rows by date, then
                 a two-term Platt blend [logit m, raw - logit m] on the last 20%.

Feature inputs are v9's REPAIRED as-of features (src/features_repaired.py, the one builder used for
history AND the live board), plus three Pro-side as-of columns computed identically at train and
serve time: form_pois_OU25 (benchmark._features), form_gap = logit(form_pois) - logit(p_market),
env_rate = mean OU2.5 rate of the league's last 80 played matches dated strictly before the fixture.

The anchor is p_market: training = football-data PRE-MATCH OU2.5 consensus (median of power de-vig
over Avg / Bet365 / Pinnacle / Betfair-exchange, class FD_PREMATCH_APPROX, never a closing column);
serving = the genuine forward two-sided consensus at first sight. That source difference is a
declared train/serve skew of the anchor (registration: frozen_inputs.market_source).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.studies.standard_repair.candidates import Prep, _pred, pen_logit
from src.studies.standard_repair.data import ENV_N, logit, poisson_market_probs, power_devig

#: identical to benchmark.GROUPS (copied, not imported, so a later benchmark edit cannot move a
#: frozen forward arm; the parity test asserts the two are still equal at registration time).
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
LR_LAM = 0.02
HGB_PARAMS = dict(max_iter=150, learning_rate=0.03, max_depth=3, min_samples_leaf=300, l2_regularization=5.0,
                  random_state=7)
RESID_ARMS = ("MKT_RESID_LR", "MKT_RESID_HGB")
MIN_TRAIN = 1500                     # benchmark.candidates refuses a block with fewer training rows


# ── as-of derived columns ───────────────────────────────────────────────────────────────────
def form_pois(d: pd.DataFrame) -> pd.Series:
    """benchmark._features: P(over 2.5) from season/last-5 goal rates, independent Poisson."""
    lh = ((d["home_season_goals_h"].fillna(d["home_scored_last5"])
           + d["away_season_conceded_a"].fillna(d["away_conceded_last5"])) / 2).clip(0.2, 5)
    la = ((d["away_season_goals_a"].fillna(d["away_scored_last5"])
           + d["home_season_conceded_h"].fillna(d["home_conceded_last5"])) / 2).clip(0.2, 5)
    return pd.Series(poisson_market_probs(lh.to_numpy(float), la.to_numpy(float))["OU25"], index=d.index)


def env_rate_history(d: pd.DataFrame, y: str) -> pd.Series:
    """benchmark._env_rate, verbatim: training rows (all played)."""
    out = pd.Series(np.nan, index=d.index)
    for _, g in d.sort_values("date").groupby("league"):
        r = g[y].shift(1).rolling(ENV_N, min_periods=20).mean()
        out.loc[g.index] = r.groupby(g["date"]).transform("first")
    return out


def env_rate_asof(played: pd.DataFrame, upcoming: pd.DataFrame, y: str) -> pd.Series:
    """Serving: mean of `y` over the league's last ENV_N PLAYED matches dated strictly before the
    fixture (min 20). Equal to env_rate_history on played history (parity test); unaffected by
    other fixtures on the board (they are unplayed and never enter a window)."""
    p = played.dropna(subset=[y]).sort_values("date", kind="mergesort")
    by = {lg: (g["date"].to_numpy(), g[y].to_numpy(float)) for lg, g in p.groupby("league")}
    out = []
    for lg, dt in zip(upcoming["league"], pd.to_datetime(upcoming["date"])):
        if lg not in by:
            out.append(np.nan)
            continue
        dates, ys = by[lg]
        k = int(np.searchsorted(dates, np.datetime64(dt), side="left"))
        w = ys[max(0, k - ENV_N):k]
        out.append(float(w.mean()) if len(w) >= 20 else np.nan)
    return pd.Series(out, index=upcoming.index)


def add_derived(d: pd.DataFrame, pm_col: str = "pm_OU25") -> pd.DataFrame:
    x = d.copy()
    x["form_pois_OU25"] = form_pois(x)
    x["form_gap"] = logit(x["form_pois_OU25"]) - logit(x[pm_col])
    return x


def feature_columns(d: pd.DataFrame) -> list[str]:
    return [c for g in GROUPS for c in GROUPS[g] if c in d.columns]


# ── fit / predict (one frozen object per arm) ─────────────────────────────────────────────────
def _dummies(d: pd.DataFrame, lv: list[str]) -> np.ndarray:
    return np.column_stack([(d["league"].astype(str) == l).to_numpy(float) for l in lv])


def fit_resid(tr: pd.DataFrame, arm: str, cols: list[str], y: str = "y_OU25", pm: str = "pm_OU25") -> dict:
    tr = tr[tr[pm].notna() & tr[y].notna()]
    if len(tr) < MIN_TRAIN:
        raise ValueError(f"{arm}: {len(tr)} training rows < {MIN_TRAIN}")
    lv = sorted(tr["league"].astype(str).unique())
    pay = {"arm": arm, "market": "OU25", "cols": list(cols), "leagues": lv, "n_train": int(len(tr)),
           "train_dates": [str(tr["date"].min())[:10], str(tr["date"].max())[:10]]}
    if arm == "MKT_RESID_LR":
        p = Prep(tr, cols)
        X = np.column_stack([logit(tr[pm])[:, None], p(tr), _dummies(tr, lv)])
        pay.update(prep={"med": p.med.to_dict(), "mu": p.mu.to_dict(), "sd": p.sd.to_dict()},
                   coef=pen_logit(X, tr[y], n_free=1, lam=LR_LAM).tolist(), lam=LR_LAM)
    elif arm == "MKT_RESID_HGB":
        from sklearn.ensemble import HistGradientBoostingClassifier
        t = tr.sort_values("date")
        cut = int(len(t) * 0.8)
        A, C = t.iloc[:cut], t.iloc[cut:]
        m = HistGradientBoostingClassifier(**HGB_PARAMS)
        Xc = lambda z: np.column_stack([z[cols].astype(float).to_numpy(), _dummies(z, lv)])
        m.fit(np.column_stack([Xc(A), logit(A[pm])]), A[y].astype(int))
        raw = logit(m.predict_proba(np.column_stack([Xc(C), logit(C[pm])]))[:, 1])
        bc = pen_logit(np.column_stack([logit(C[pm]), raw - logit(C[pm])]), C[y], n_free=2)
        pay.update(model=m, platt=bc.tolist(), hgb_params=HGB_PARAMS, split="first 80% fit / last 20% blend")
    else:
        raise ValueError(arm)
    return pay


def _prep_apply(pay: dict, d: pd.DataFrame) -> np.ndarray:
    cols = pay["cols"]
    med, mu, sd = (pd.Series(pay["prep"][k]) for k in ("med", "mu", "sd"))
    X = d[cols].astype(float).fillna(med[cols])
    return ((X - mu[cols]) / sd[cols]).fillna(0.0).to_numpy()


def predict_resid(pay: dict, d: pd.DataFrame, pm: str = "pm_OU25") -> np.ndarray:
    """P(OVER 2.5). Rows without a market anchor return NaN (never an imputed market)."""
    out = np.full(len(d), np.nan)
    ok = d[pm].notna().to_numpy()
    if not ok.any():
        return out
    z = d[ok]
    lv = pay["leagues"]
    if pay["arm"] == "MKT_RESID_LR":
        X = np.column_stack([logit(z[pm])[:, None], _prep_apply(pay, z), _dummies(z, lv)])
        out[ok] = _pred(np.asarray(pay["coef"]), X)
    else:
        m = pay["model"]
        Xc = np.column_stack([z[pay["cols"]].astype(float).to_numpy(), _dummies(z, lv)])
        raw = logit(m.predict_proba(np.column_stack([Xc, logit(z[pm])]))[:, 1])
        out[ok] = _pred(np.asarray(pay["platt"]), np.column_stack([logit(z[pm]), raw - logit(z[pm])]))
    return out


# ── training anchor: football-data PRE-MATCH OU2.5 consensus ────────────────────────────────────
def fd_anchor(fd_dir, leagues_codes: dict, amap: dict) -> pd.DataFrame:
    """One row per (league, date, home, away) with pm_OU25 = median power de-vig over the
    pre-match Avg / B365 / Pinnacle / BFE pairs (benchmark.market_table's formula). Closing
    columns are never read here."""
    from pathlib import Path
    from src.studies.standard_repair import prices as PR
    ou = PR.fd_ou25_rows(Path(fd_dir), leagues_codes)
    if ou.empty:
        return pd.DataFrame(columns=["league", "date", "home_team", "away_team", "pm_OU25", "anchor_books"])
    for c in ("home_team", "away_team"):
        ou[c] = [amap.get(lg, {}).get(t, t) for lg, t in zip(ou["league"], ou[c])]
    P = np.column_stack([power_devig(ou[f"o_{b}"], ou[f"u_{b}"]) for b in ("AVG", "B365", "PIN", "BFE")])
    with np.errstate(all="ignore"):
        ou["pm_OU25"] = np.nanmedian(np.where(np.isfinite(P), P, np.nan), axis=1)
    ou["anchor_books"] = np.isfinite(P).sum(1)
    k = ["league", "date", "home_team", "away_team"]
    return ou[k + ["pm_OU25", "anchor_books"]].dropna(subset=["pm_OU25"]).drop_duplicates(k)


def attach_anchor(frame: pd.DataFrame, anchor: pd.DataFrame) -> pd.DataFrame:
    """Exact (league, date, name) join first; the rest by league + date +-1 day + token club match
    (refusing ambiguity) — v9's canonicaliser may spell a club differently from football-data."""
    from src.studies.common import match_frames
    f = frame.copy()
    f["date"] = pd.to_datetime(f["date"]).dt.normalize()
    a = anchor.copy()
    a["date"] = pd.to_datetime(a["date"]).dt.normalize()
    k = ["league", "date", "home_team", "away_team"]
    f = f.drop(columns=[c for c in ("pm_OU25", "anchor_books") if c in f]).merge(a, on=k, how="left")
    # fallback only inside football-data's price coverage (older archive rows have no file at all)
    miss = f["pm_OU25"].isna() & (f["date"] >= a["date"].min()) & f["league"].isin(set(a["league"]))
    if miss.any():
        L = f.loc[miss, k].assign(match_date=lambda z: z["date"].dt.strftime("%Y-%m-%d"))
        R = a.assign(match_date=a["date"].dt.strftime("%Y-%m-%d")).reset_index(drop=True)
        R = R[R["league"].isin(set(L["league"]))].reset_index(drop=True)
        hit = match_frames(L, R)
        ok = hit.notna()
        idx = hit[ok].astype(int).to_numpy()
        f.loc[L.index[ok.to_numpy()], "pm_OU25"] = R.loc[idx, "pm_OU25"].to_numpy()
        f.loc[L.index[ok.to_numpy()], "anchor_books"] = R.loc[idx, "anchor_books"].to_numpy()
    return f
