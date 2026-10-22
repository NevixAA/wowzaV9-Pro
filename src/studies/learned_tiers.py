"""Learned per-league tiers - a CHALLENGER to v9's edge-size tier ladder (owner 2026-10-22).

    python -m src.studies.learned_tiers            # walk-forward + prospective scoring -> output/studies/learned_tiers/

Owner: "start with tiers -> learn and retrain -> swap if another tier wins" and "it must be per league -
no way 2 different leagues have the same gates". On OU25 the raw edge does not rank outcomes, so a ladder
on raw edge cannot work. This learns WHICH candidates win instead:

  model   one per (model_type, market): L2-regularised logistic regression of WIN on
          logit(fair market p), logit(model p), raw edge, log odds, side, and LEAGUE (one-hot) plus
          LEAGUE x raw-edge. The L2 penalty is the shrinkage: a league's own effect and its own edge slope
          move away from the track's only as far as its data supports -> every league gets its own gate.
  tiers   from predicted EV = p_hat * odds - 1, with cut-offs FIXED here before any result:
          SNIPER >= +6%, MARKSMAN +3..6%, VALUABLE 0..3%, else AVOID.
  data    every FIRST-SIGHT candidate, not only sent tips: the settled snapshot record
          (experiments/valuable_2026_10/all_fixture_settled.parquet, 2026-08-15 ->) plus the Pro
          low-edge shadow once its rows settle (output/valuable_shadow, 2026-10-21 ->).
  test    weekly walk-forward: each week is scored by a model fitted ONLY on earlier weeks, then
          compared with v9's production tier on the same rows. Frozen in
          registry/learned_tiers/registration_v1.json; the swap rule there decides, not this file.

Research only - v9's selection, tiers and stakes are untouched.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from config import pro_config as cfg

OUT = cfg.BASE_DIR / "output" / "studies" / "learned_tiers"
HIST = cfg.BASE_DIR / "experiments" / "valuable_2026_10" / "all_fixture_settled.parquet"
SHADOW = cfg.BASE_DIR / "output" / "valuable_shadow" / "valuable_shadow.csv"
CUTS = {"SNIPER": 0.06, "MARKSMAN": 0.03, "VALUABLE": 0.0}          # predicted-EV cut-offs, frozen
C = 0.5                                                              # L2 strength, frozen (no tuning)
MIN_TRAIN = 150
MARKETS = ("ou25", "btts")
EPS = 1e-4


def _logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def load() -> pd.DataFrame:
    """First-sight candidates with outcome, one per fixture x market (v9's chosen side on OU25)."""
    h = pd.read_parquet(HIST)
    h = h.rename(columns={"p_market_fair": "p_fair"})[["fx", "league", "model_type", "market", "side", "gen", "md",
                                                      "p_model", "p_fair", "odds", "raw_edge", "prod_tier", "won", "pnl"]]
    h["source"] = "SNAPSHOT_HISTORY"
    parts = [h]
    if SHADOW.exists():
        s = pd.read_csv(SHADOW, low_memory=False)
        s = s[s["result"].isin(["WIN", "LOSS"]) & s["market"].isin(MARKETS)].copy()
        if len(s):
            s = s[(s["market"] != "btts") | (s["side"] == "YES")]
            s = s.sort_values("raw_edge", ascending=False).drop_duplicates(["fixture_id", "market"])  # v9's side
            s["gen"] = pd.to_datetime(s["generated_at"], utc=True)
            parts.append(pd.DataFrame({
                "fx": s["fixture_id"], "league": s["league"], "model_type": s["model_type"], "market": s["market"],
                "side": s["side"], "gen": s["gen"], "md": pd.to_datetime(s["kickoff"], utc=True).dt.tz_convert(None).dt.normalize(),
                "p_model": s["model_probability"], "p_fair": s["fair_market_probability"], "odds": s["odds"],
                "raw_edge": s["raw_edge"] / 100, "prod_tier": s["production_tier"].fillna("AVOID"),
                "won": (s["result"] == "WIN").astype(float), "pnl": s["flat_pnl"].astype(float), "source": "PRO_SHADOW"}))
    d = pd.concat(parts, ignore_index=True)
    d = d[d["market"].isin(MARKETS)].dropna(subset=["p_model", "p_fair", "odds", "won"])
    d["prod_tier"] = d["prod_tier"].astype(str).str.upper().replace({"VALUE": "VALUABLE", "NAN": "AVOID"})
    d["week"] = d["md"].dt.to_period("W").dt.start_time
    return d.sort_values("gen").drop_duplicates(["fx", "market"], keep="first").reset_index(drop=True)


def _design(d: pd.DataFrame, leagues: list[str]) -> np.ndarray:
    base = np.c_[_logit(d["p_fair"]), _logit(d["p_model"]), d["raw_edge"].to_numpy(float),
                 np.log(d["odds"].to_numpy(float)), (d["side"].isin(["UNDER", "NO"])).to_numpy(float)]
    lg = np.stack([(d["league"] == l).to_numpy(float) for l in leagues], axis=1) if leagues else np.zeros((len(d), 0))
    return np.c_[base, lg, lg * d["raw_edge"].to_numpy(float)[:, None]]


def fit(train: pd.DataFrame):
    leagues = sorted(train["league"].unique())
    m = LogisticRegression(C=C, max_iter=2000)
    m.fit(_design(train, leagues), train["won"].astype(int))
    return m, leagues


def predict_ev(model, leagues, d: pd.DataFrame) -> np.ndarray:
    p = model.predict_proba(_design(d, leagues))[:, 1]
    return p * d["odds"].to_numpy(float) - 1


def tier_of(ev: np.ndarray) -> np.ndarray:
    return np.select([ev >= CUTS["SNIPER"], ev >= CUTS["MARKSMAN"], ev >= CUTS["VALUABLE"]],
                     ["SNIPER", "MARKSMAN", "VALUABLE"], "AVOID")


def walk_forward(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (mt, mk), g in d.groupby(["model_type", "market"]):
        weeks = sorted(g["week"].unique())
        for w in weeks:
            tr, te = g[g["week"] < w], g[g["week"] == w]
            if len(tr) < MIN_TRAIN or te.empty or tr["won"].nunique() < 2:
                continue
            m, lg = fit(tr)
            ev = predict_ev(m, lg, te)
            rows.append(te.assign(ev_hat=ev, learned_tier=tier_of(ev)))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _boot(pnl: np.ndarray, days: np.ndarray, n=2000, seed=7):
    if len(pnl) < 10:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    u = np.unique(days)
    idx = {k: np.where(days == k)[0] for k in u}
    b = [pnl[np.concatenate([idx[k] for k in rng.choice(u, len(u))])].mean() for _ in range(n)]
    return tuple(np.round(np.percentile(b, [5, 95]) * 100, 1))


def _summ(x: pd.DataFrame) -> dict:
    if not len(x):
        return {"n": 0}
    lo, hi = _boot(x["pnl"].to_numpy(float), x["md"].values)
    return {"n": int(len(x)), "roi_pct": round(float(x["pnl"].mean() * 100), 1), "ci90": [lo, hi],
            "hit_pct": round(float(x["won"].mean() * 100), 1), "pnl": round(float(x["pnl"].sum()), 1)}


#: Amendment v1.1 (owner 2026-10-22): the learned tiers never switch a league off. Leagues listed here
#: have PASSED the league-off test (registry/learned_tiers/amendment_v1_1.json) and been approved by the
#: owner; it is empty until then.
LEAGUES_OFF_APPROVED: set[tuple[str, str, str]] = set()


def protect_leagues(d: pd.DataFrame) -> pd.Series:
    """LEARNED_LEAGUE_PROTECTED: the learned tier, except that a candidate the model would AVOID in a
    league not approved for switching off keeps v9's production tier - re-rank inside, never switch off."""
    off = [(l, m, t) in LEAGUES_OFF_APPROVED for l, m, t in zip(d["league"], d["market"], d["model_type"])]
    keep_prod = (d["learned_tier"] == "AVOID") & ~pd.Series(off, index=d.index)
    return d["learned_tier"].where(~keep_prod, d["prod_tier"])


def compare(wf: pd.DataFrame) -> dict:
    out = {}
    wf = wf.assign(protected_tier=protect_leagues(wf))
    for (mt, mk), g in wf.groupby(["model_type", "market"]):
        r = {"weeks_scored": int(g["week"].nunique()), "rows": int(len(g))}
        for scheme, col in (("PRODUCTION", "prod_tier"), ("LEARNED", "learned_tier"),
                            ("LEARNED_LEAGUE_PROTECTED", "protected_tier")):
            r[scheme] = {t: _summ(g[g[col] == t]) for t in ("SNIPER", "MARKSMAN", "VALUABLE")}
            r[scheme]["ALL_TIPS"] = _summ(g[g[col].isin(["SNIPER", "MARKSMAN", "VALUABLE"])])
            rois = [r[scheme][t].get("roi_pct") for t in ("SNIPER", "MARKSMAN", "VALUABLE")]
            r[scheme]["ordered_S>M>V"] = bool(all(v is not None for v in rois) and rois[0] > rois[1] > rois[2])
        out[f"{mt}|{mk}"] = r
    return out


def league_gates(d: pd.DataFrame) -> pd.DataFrame:
    """The raw edge each league needs for predicted EV >= each cut, at its median odds/prices -
    the per-league gates the learned model implies (fitted on ALL settled rows; descriptive)."""
    rows = []
    for (mt, mk), g in d.groupby(["model_type", "market"]):
        if len(g) < MIN_TRAIN:
            continue
        m, lg = fit(g)
        for league, x in g.groupby("league"):
            proto = x.median(numeric_only=True)
            grid = np.linspace(-0.05, 0.25, 121)
            probe = pd.DataFrame({"league": league, "side": x["side"].mode().iloc[0], "odds": proto["odds"],
                                  "p_fair": proto["p_fair"], "raw_edge": grid,
                                  "p_model": np.clip(1 / proto["odds"] + grid, 0.01, 0.99)})
            ev = predict_ev(m, lg, probe)
            gate = {t: (round(float(grid[np.argmax(ev >= c)] * 100), 1) if (ev >= c).any() else None)
                    for t, c in CUTS.items()}
            rows.append({"model_type": mt, "market": mk, "league": league, "n": int(len(x)),
                         **{f"raw_edge_needed_{t}": v for t, v in gate.items()}})
    return pd.DataFrame(rows)


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    d = load()
    wf = walk_forward(d)
    cmp_ = compare(wf) if len(wf) else {}
    gates = league_gates(d)
    gates.to_csv(OUT / "league_gates.csv", index=False)
    if len(wf):
        wf[["fx", "league", "model_type", "market", "side", "md", "odds", "raw_edge", "prod_tier", "learned_tier",
            "ev_hat", "won", "pnl", "source"]].to_csv(OUT / "walk_forward_rows.csv", index=False)
    res = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "registration": "registry/learned_tiers/registration_v1.json", "cuts_ev": CUTS, "C": C,
           "data": {"rows": int(len(d)), "by_source": d["source"].value_counts().to_dict(),
                    "first": str(d["md"].min().date()), "last": str(d["md"].max().date())},
           "comparison": cmp_, "production_changed": "NO"}
    (OUT / "learned_tiers.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = run()
    for k, v in r["comparison"].items():
        print(k, "weeks", v["weeks_scored"], "rows", v["rows"])
        for s in ("PRODUCTION", "LEARNED", "LEARNED_LEAGUE_PROTECTED"):
            print("  ", s, {t: (v[s][t].get("n"), v[s][t].get("roi_pct")) for t in ("SNIPER", "MARKSMAN", "VALUABLE", "ALL_TIPS")},
                  "ordered", v[s]["ordered_S>M>V"])
