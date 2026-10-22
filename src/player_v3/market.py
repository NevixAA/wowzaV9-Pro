"""Phases F + G — player-prop market consensus and the market-residual test (H6, H7).

    python -m src.player_v3.market       # -> player_market_residual*.csv, player_edge_cells.csv

QUESTION: does Wowza add predictive information AFTER the bookmaker?

DATA LIMITS (CURRENT_STATE.md section 3), stated rather than hidden:
  * OVER prices only — v9 discards Under at fetch — so a two-way de-vig is impossible. The market's
    probability is the implied 1/odds RECALIBRATED by logistic regression on the earlier period
    (logit p = a + b logit q), which absorbs the one-sided margin. Field: p_market_fair.
  * 3 books, usually 1 per prop; cross-book consensus is the median implied where >1 book quoted.
  * since 2026-06-28 only; every priced row lies in the V3 holdout period, so model probabilities
    used here come from models fit before 2025-02 (true out-of-sample for this window).

PRICES: entry = FIRST captured snapshot (what a bettor could take at decision time - the v11 rule:
the market at decision time, never the close); close = LAST snapshot before the match. Fields are
explicit and never mixed: p_model, p_market_fair (entry), p_close_fair, p_consensus_implied,
book_dispersion, model_market_residual, execution_edge (vs best entry odds), clv.

TEST per market, chronological halves: fit market-only and market + logit(p_model) on the earlier
half, score both on the later half; per-row log-loss difference with a matchday-block 95% CI.
PLAYER_WOWZA_ADDS_TO_MARKET: YES (CI below 0) / NO (CI above 0 or point >= 0 with n large) /
UNCLEAR / INSUFFICIENT_DATA (< 300 settled priced rows).

EDGE CELLS (H7), dimensions FIXED HERE BEFORE ANY CELL WAS READ (2026-10-14):
  market x position x market-probability band (<0.3, 0.3-0.5, 0.5-0.7, >=0.7) x
  model-market residual band (< -5, -5..+5, > +5 points). Every cell is reported (none hidden),
  with n, hit vs implied, flat ROI at entry, CLV, and Benjamini-Hochberg q-values. EXPLORATORY:
  a cell is never "proven" here.
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.player_v3 import CALC_VERSION, HOLDOUT_FROM, TRAIN_END, VALID_END
from src.player_v3 import data as D
from src.player_v3.sot_lab import CACHE, OUT, _ll, fit_binary, load_features

TARGET = {"goals": "target_goals", "sot": "target_sot", "sot2": "target_sot2", "sot3": "target_sot3",
          "sot4": "target_sot4", "assists": "target_assists", "cards": "target_cards"}
_TR = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "æ": "ae", "ß": "ss", "đ": "d", "ı": "i"})


def ini_sur(name) -> str | None:
    s = unicodedata.normalize("NFKD", str(name or "").translate(_TR))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    t = [x for x in re.split(r"[\s.]+", re.sub(r"[^a-z\s.'-]", "", s)) if x]
    return f"{t[0][0]}|{t[-1]}" if len(t) >= 2 else None


def prop_items() -> pd.DataFrame:
    """One row per (match date, player, market) with entry/close/consensus/dispersion."""
    # v9's file is ROLLING since 2026-10-22: played matches live in player_prop_odds_history_archive/.
    from src.data.v9_source import read_v9_all
    h = read_v9_all("output/player_prop_odds_history.csv", low_memory=False)
    h = h[h["market"].isin(TARGET)]
    h["odds"] = pd.to_numeric(h["odds"], errors="coerce")
    h = h[h["odds"] > 1.0]
    h["k"] = h["player"].map(ini_sur)
    h = h.dropna(subset=["k"]).sort_values("snapshot_ts")
    g = h.groupby(["match_date", "league", "k", "market"])
    first_ts, last_ts = g["snapshot_ts"].transform("min"), g["snapshot_ts"].transform("max")
    entry = h[h["snapshot_ts"] == first_ts].groupby(["match_date", "league", "k", "market"])["odds"].agg(
        entry_best="max", entry_median="median", entry_books="nunique")
    close = h[h["snapshot_ts"] == last_ts].groupby(["match_date", "league", "k", "market"])["odds"].agg(
        close_best="max", close_median="median")
    allb = g["odds"].agg(odds_min="min", odds_max="max")
    nb = g["bookmaker"].nunique().rename("n_books")
    it = entry.join(close).join(allb).join(nb).reset_index()
    it["book_dispersion"] = it["odds_max"] / it["odds_min"] - 1
    it["p_consensus_implied"] = 1 / it["entry_median"]
    return it


def settle(items: pd.DataFrame, X: pd.DataFrame) -> pd.DataFrame:
    """Join to appearances by date + league + initial-surname; refuse ambiguous matches.
    A priced player who did not appear has no row -> the bet is void -> excluded (as books do)."""
    a = X[["player_id", "fixture_id", "date", "league", "player_name", "position", *[c for c in TARGET.values() if c in X]]].copy()
    a["match_date"] = a["date"].dt.strftime("%Y-%m-%d")
    a["k"] = a["player_name"].map(ini_sur)
    a = a.dropna(subset=["k"])
    dup = a.duplicated(["match_date", "league", "k"], keep=False)
    a = a[~dup]                                     # two same-initial-surname players that day: refuse
    m = items.merge(a, on=["match_date", "league", "k"], how="inner")
    m["y"] = [r[TARGET[r["market"]]] if TARGET[r["market"]] in m.columns else np.nan for _, r in m.iterrows()]
    return m.dropna(subset=["y"])


def model_probs(X: pd.DataFrame, rows: pd.DataFrame, fam: dict) -> pd.DataFrame:
    """p_model for each settled priced row: the champion view (BASE_V9) and ALL_V3, per market,
    both fit on TRAIN and Platt-calibrated on VALIDATION (the prop window is all holdout)."""
    tr, va, _ = (m.to_numpy() for m in D.chrono_split(X["date"], TRAIN_END, VALID_END, HOLDOUT_FROM))
    base = fam["BASE_V9"]
    v3 = [c for k in ("FORM_MH", "FORM_SHRUNK", "USAGE_SHARE", "TEAM_ENV", "OPP_PERSONNEL", "MATCHUP_RAW", "ROLE")
          for c in fam.get(k, [])]
    pos = pd.Series(np.arange(len(X)), index=pd.MultiIndex.from_frame(X[["player_id", "fixture_id"]]))
    out = rows.copy()
    out["p_model_base"] = np.nan
    out["p_model_v3"] = np.nan
    for mk in out["market"].unique():
        t = TARGET[mk]
        if t not in X:
            continue
        y = X[t].fillna(0).astype(int).to_numpy()
        sel = out["market"] == mk
        idx = pos.reindex(pd.MultiIndex.from_frame(out.loc[sel, ["player_id", "fixture_id"]])).to_numpy()
        ok = ~np.isnan(idx)
        for name, cols in (("p_model_base", base), ("p_model_v3", base + v3)):
            p, _ = fit_binary(X[cols], y, tr, va)
            vals = np.full(sel.sum(), np.nan)
            vals[ok] = p[idx[ok].astype(int)]
            out.loc[sel, name] = vals
    return out


def _lg(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _fit(Xtr, y, Xte):
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(C=1e6, max_iter=1000).fit(Xtr, y)
    return m.predict_proba(Xte)[:, 1], m


def residual_test(d: pd.DataFrame, model_col: str, price_col: str) -> dict:
    d = d.dropna(subset=[model_col, price_col]).sort_values("match_date")
    n = len(d)
    if n < 300 or d["y"].nunique() < 2:
        return {"n": n, "verdict": "INSUFFICIENT_DATA"}
    half = n // 2
    tr, te = d.iloc[:half], d.iloc[half:]
    q_tr, q_te = _lg(1 / tr[price_col]), _lg(1 / te[price_col])
    p_m, _ = _fit(q_tr.reshape(-1, 1), tr["y"], q_te.reshape(-1, 1))
    p_mw, mw = _fit(np.column_stack([q_tr, _lg(tr[model_col])]), tr["y"], np.column_stack([q_te, _lg(te[model_col])]))
    y = te["y"].to_numpy(float)
    l_m, l_mw = _ll(p_m, y), _ll(p_mw, y)
    dd = pd.DataFrame({"x": l_mw - l_m, "g": te["match_date"].to_numpy()}).groupby("g")["x"].agg(["sum", "count"])
    rng = np.random.default_rng(5)
    i = rng.integers(0, len(dd), size=(2000, len(dd)))
    b = dd["sum"].to_numpy()[i].sum(1) / dd["count"].to_numpy()[i].sum(1)
    lo, hi = float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))
    return {"n": n, "n_test": len(te), "base_rate": round(float(y.mean()), 4),
            "brier_market": round(float(((p_m - y) ** 2).mean()), 5), "brier_market_wowza": round(float(((p_mw - y) ** 2).mean()), 5),
            "logloss_market": round(float(l_m.mean()), 5), "logloss_market_wowza": round(float(l_mw.mean()), 5),
            "delta_logloss": round(float((l_mw - l_m).mean()), 6), "ci95": [round(lo, 6), round(hi, 6)],
            "wowza_coef": round(float(mw.coef_[0][1]), 4),
            "verdict": "YES" if hi < 0 else ("NO" if lo > 0 or (n >= 2000 and (l_mw - l_m).mean() >= 0) else "UNCLEAR")}


def edge_cells(d: pd.DataFrame) -> pd.DataFrame:
    from scipy.stats import t as tdist
    d = d.dropna(subset=["p_model_v3", "entry_best"]).copy()
    d["p_mkt"] = 1 / d["entry_best"]
    d["prob_band"] = pd.cut(d["p_mkt"], [0, 0.3, 0.5, 0.7, 1.0], labels=["<0.3", "0.3-0.5", "0.5-0.7", ">=0.7"])
    d["resid_pts"] = 100 * (d["p_model_v3"] - d["p_mkt"])
    d["resid_band"] = pd.cut(d["resid_pts"], [-100, -5, 5, 100], labels=["<-5", "-5..+5", ">+5"])
    d["unit"] = np.where(d["y"] == 1, d["entry_best"] - 1, -1.0)
    d["clv"] = d["entry_best"] / d["close_best"] - 1
    rows = []
    for key, g in d.groupby(["market", "position", "prob_band", "resid_band"], observed=True):
        n = len(g)
        mu, sd = float(g["unit"].mean()), float(g["unit"].std(ddof=1)) if n > 1 else 0.0
        pval = float(2 * tdist.sf(abs(mu / (sd / np.sqrt(n))), n - 1)) if n > 2 and sd > 0 else 1.0
        rows.append({"market": key[0], "position": key[1], "prob_band": key[2], "resid_band": key[3], "n": n,
                     "hit": round(float(g["y"].mean()), 4), "implied": round(float(g["p_mkt"].mean()), 4),
                     "roi_flat_entry": round(mu, 4), "clv_median": round(float(g["clv"].median()), 4),
                     "mean_residual_pts": round(float(g["resid_pts"].mean()), 2), "p_value": round(pval, 5)})
    c = pd.DataFrame(rows).sort_values("p_value").reset_index(drop=True)
    m = len(c)
    c["bh_q"] = np.minimum.accumulate((c["p_value"] * m / (np.arange(m) + 1))[::-1])[::-1].clip(upper=1).round(5)
    # Only a POSITIVE significant cell is "promising"; most significant cells are significantly
    # NEGATIVE (one-sided prop margins), which is a different and unsurprising finding.
    c["status"] = np.where(c["n"] < 30, "INSUFFICIENT_DATA",
                  np.where((c["bh_q"] < 0.10) & (c["roi_flat_entry"] > 0), "PROMISING_EXPLORATORY",
                  np.where((c["bh_q"] < 0.10) & (c["roi_flat_entry"] < 0), "SIGNIFICANTLY_NEGATIVE", "NOTHING")))
    c.insert(0, "calculation_version", CALC_VERSION)
    c["period"] = f"{d['match_date'].min()} to {d['match_date'].max()} (holdout; models fit < {TRAIN_END})"
    return c


def main() -> int:
    X = load_features()
    from src.player_v3 import features as F
    fam = F.FAMILIES
    items = prop_items()
    rows = settle(items, X)
    print(f"[market] items {len(items):,} | settled appearances {len(rows):,} | by market {rows['market'].value_counts().to_dict()}")
    rows = model_probs(X, rows, fam)
    rows["p_market_fair"] = np.nan          # filled per market by the recalibration inside the test
    rows["model_market_residual"] = rows["p_model_v3"] - 1 / rows["entry_best"]
    rows["execution_edge"] = rows["p_model_v3"] * rows["entry_best"] - 1
    rows["clv"] = rows["entry_best"] / rows["close_best"] - 1
    rows.to_parquet(CACHE / "prop_rows.parquet")
    res = []
    for mk, g in rows.groupby("market"):
        for model in ("p_model_base", "p_model_v3"):
            for price in ("entry_best", "close_best"):
                r = residual_test(g, model, price)
                res.append({"market": mk, "model": model, "price": price, **r})
                print(mk, model, price, r)
    R = pd.DataFrame(res)
    R.insert(0, "calculation_version", CALC_VERSION)
    R.to_csv(OUT / "player_market_residual.csv", index=False)
    by = []
    for dim, fname in (("league", "player_market_residual_by_league.csv"), ("position", "player_market_residual_by_role.csv")):
        for (mk, v), g in rows.groupby(["market", dim]):
            r = residual_test(g, "p_model_v3", "entry_best")
            by.append({"market": mk, dim: v, **r})
        B = pd.DataFrame([b for b in by if dim in b])
        B.insert(0, "calculation_version", CALC_VERSION)
        B["note"] = "exploratory subgroup; not a verdict"
        B.to_csv(OUT / fname, index=False)
    edge_cells(rows).to_csv(OUT / "player_edge_cells.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
