"""Pre-registered FORWARD test of the V3 prop market-residual rule (owner-approved 2026-10-14).

    python -m src.player_v3.forward          # freeze once if needed, then score the forward window

THE CLAIM UNDER TEST (from PLAYER_V3_REPORT.md): market + Wowza predicts props better than the market,
and bets chosen by a fixed rule beat the closing price. That evidence came from a period the models
had not seen but the RULE was chosen while looking at it. This file judges it on props that did not
exist when it was written.

FROZEN on first run (registry/player_v3_forward/registration.json + models/player_v3_forward/*.pkl):
  markets       goals, sot (1+), sot2, sot3
  model         HGB on BASE_V9 + all V3 families except expected minutes (= p_model_v3 in market.py),
                fit on matches < 2025-07-01, log-odds Platt on 2025-07-01 .. 2026-06-27
  combination   logit p = a + b*logit(1/entry_best) + c*logit(p_model), fit on ALL settled priced props
                with match_date <= REGISTERED_ON
  bet rule      p_final * entry_best > 1.05 (flat 1 unit at the best ENTRY price)
  cell (exploratory, its own line)  goals, position F, 1/entry_best < 0.30, p_model - 1/entry_best > 0.05
WINDOW: props on matches dated >= WINDOW_FROM only. Nothing above may change after registration;
a change is a new registration with a new date (a test pins this).
VERDICT per market and for the cell: EDGE needs >= 150 bets AND a positive 90% matchday-block ROI lower
bound AND median CLV > 0 AND CLV above the window's all-props baseline; NO_EDGE when >= 150 bets and
the ROI upper bound < 0; else COLLECTING (n/150). Paper only.
"""
from __future__ import annotations

import json
import pickle

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.player_v3 import CALC_VERSION
from src.player_v3 import features as F
from src.player_v3.market import TARGET, prop_items, settle
from src.player_v3.sot_lab import OUT, _usable, load_features

REGISTERED_ON = "2026-10-14"
WINDOW_FROM = "2026-10-15"
MARKETS = ("goals", "sot", "sot2", "sot3")
FIT_BEFORE, CAL_FROM, CAL_TO = "2025-07-01", "2025-07-01", "2026-06-27"
EV_BAR = 1.05
N_MIN = 150
REG_DIR = cfg.REGISTRY_DIR / "player_v3_forward"
MODEL_DIR = cfg.BASE_DIR / "models" / "player_v3_forward"
FAMS = ("FORM_MH", "FORM_SHRUNK", "USAGE_SHARE", "TEAM_ENV", "OPP_PERSONNEL", "MATCHUP_RAW", "ROLE")


def _lg(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _cols(fam: dict) -> list[str]:
    return fam["BASE_V9"] + [c for k in FAMS for c in fam.get(k, [])]


def freeze(X: pd.DataFrame, rows: pd.DataFrame) -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    import sklearn
    from src.player_v3.sot_lab import HGB
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REG_DIR.mkdir(parents=True, exist_ok=True)
    cols = _cols(F.FAMILIES)
    fit = (X["date"] < FIT_BEFORE).to_numpy()
    cal = ((X["date"] >= CAL_FROM) & (X["date"] <= CAL_TO)).to_numpy()
    reg = {"registered_on": REGISTERED_ON, "window_from": WINDOW_FROM, "ev_bar": EV_BAR, "n_min": N_MIN,
           "fit_before": FIT_BEFORE, "calibration": [CAL_FROM, CAL_TO], "sklearn": sklearn.__version__,
           "calculation_version": CALC_VERSION, "markets": {}}
    for mk in MARKETS:
        y = X[TARGET[mk]].fillna(0).astype(int).to_numpy()
        use = _usable(X.loc[fit, cols])
        m = HistGradientBoostingClassifier(**HGB).fit(X.loc[fit, use], y[fit])
        raw = m.predict_proba(X.loc[cal, use])[:, 1]
        platt = LogisticRegression(max_iter=1000).fit(_lg(raw).reshape(-1, 1), y[cal])
        with open(MODEL_DIR / f"{mk}.pkl", "wb") as fh:
            pickle.dump({"model": m, "platt": platt, "cols": use}, fh)
        r = rows[(rows["market"] == mk) & (rows["match_date"] <= REGISTERED_ON)].copy()
        r["p_model"] = score_rows(X, r, mk)
        r = r.dropna(subset=["p_model", "entry_best"])
        comb = LogisticRegression(C=1e6, max_iter=1000).fit(
            np.column_stack([_lg(1 / r["entry_best"]), _lg(r["p_model"])]), r["y"])
        mkt_only = LogisticRegression(C=1e6, max_iter=1000).fit(_lg(1 / r["entry_best"]).reshape(-1, 1), r["y"])
        reg["markets"][mk] = {"n_fit_props": int(len(r)), "a": float(comb.intercept_[0]),
                              "b_market": float(comb.coef_[0][0]), "c_wowza": float(comb.coef_[0][1]),
                              "market_only_a": float(mkt_only.intercept_[0]), "market_only_b": float(mkt_only.coef_[0][0])}
        print(f"[forward] froze {mk}: {reg['markets'][mk]}")
    (REG_DIR / "registration.json").write_text(json.dumps(reg, indent=1), encoding="utf-8")
    return reg


def score_rows(X: pd.DataFrame, rows: pd.DataFrame, mk: str) -> np.ndarray:
    with open(MODEL_DIR / f"{mk}.pkl", "rb") as fh:
        art = pickle.load(fh)
    key = pd.MultiIndex.from_frame(X[["player_id", "fixture_id"]])
    pos = pd.Series(np.arange(len(X)), index=key)
    idx = pos.reindex(pd.MultiIndex.from_frame(rows[["player_id", "fixture_id"]])).to_numpy()
    out = np.full(len(rows), np.nan)
    ok = ~np.isnan(idx)
    if ok.any():
        sub = X.iloc[idx[ok].astype(int)]
        raw = art["model"].predict_proba(sub[art["cols"]])[:, 1]
        out[ok] = art["platt"].predict_proba(_lg(raw).reshape(-1, 1))[:, 1]
    return out


def _roi_ci(unit: np.ndarray, days: np.ndarray, n=3000, seed=2):
    d = pd.DataFrame({"u": unit, "g": days}).groupby("g")["u"].agg(["sum", "count"])
    if len(d) < 3:
        return [None, None]
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(d), size=(n, len(d)))
    b = d["sum"].to_numpy()[i].sum(1) / d["count"].to_numpy()[i].sum(1)
    return [round(float(np.quantile(b, 0.05)), 4), round(float(np.quantile(b, 0.95)), 4)]


def judge(b: pd.DataFrame, base_clv: float, base_beat: float) -> dict:
    n = len(b)
    if n == 0:
        return {"bets": 0, "verdict": f"COLLECTING (0/{N_MIN})"}
    unit = np.where(b["y"] == 1, b["entry_best"] - 1, -1.0)
    clv = (b["entry_best"] / b["close_best"] - 1).to_numpy()
    lo, hi = _roi_ci(unit, b["match_date"].to_numpy())
    med = float(np.median(clv))
    out = {"bets": n, "days": int(b["match_date"].nunique()), "hit": round(float(b["y"].mean()), 4),
           "avg_odds": round(float(b["entry_best"].mean()), 2), "units": round(float(unit.sum()), 2),
           "roi": round(float(unit.mean()), 4), "roi_ci90": [lo, hi], "clv_median": round(med, 4),
           "clv_beat_share": round(float((clv > 0).mean()), 3), "baseline_clv_median": round(base_clv, 4),
           "baseline_beat_share": round(base_beat, 3)}
    if n >= N_MIN and lo is not None and lo > 0 and med > 0 and out["clv_beat_share"] > base_beat:
        out["verdict"] = "EDGE"
    elif n >= N_MIN and hi is not None and hi < 0:
        out["verdict"] = "NO_EDGE"
    else:
        out["verdict"] = f"COLLECTING ({n}/{N_MIN})"
    return out


def evaluate(X: pd.DataFrame, rows: pd.DataFrame, reg: dict) -> dict:
    w = rows[rows["match_date"] >= WINDOW_FROM].copy()
    res = {"registered_on": REGISTERED_ON, "window_from": WINDOW_FROM, "calculation_version": CALC_VERSION,
           "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "props_in_window": int(len(w)), "markets": {}}
    for mk in MARKETS:
        g = w[w["market"] == mk].copy()
        if g.empty:
            res["markets"][mk] = {"settled_props": 0, "rule": judge(g, 0.0, 0.0)}
            continue
        g["p_model"] = score_rows(X, g, mk)
        g = g.dropna(subset=["p_model", "entry_best", "close_best"])
        c = reg["markets"][mk]
        z = c["a"] + c["b_market"] * _lg(1 / g["entry_best"]) + c["c_wowza"] * _lg(g["p_model"])
        g["p_final"] = 1 / (1 + np.exp(-z))
        zm = c["market_only_a"] + c["market_only_b"] * _lg(1 / g["entry_best"])
        g["p_market"] = 1 / (1 + np.exp(-zm))
        clv_all = (g["entry_best"] / g["close_best"] - 1)
        base_clv, base_beat = float(clv_all.median()) if len(g) else 0.0, float((clv_all > 0).mean()) if len(g) else 0.0
        y = g["y"].to_numpy(float)
        ll = lambda p: float(-(y * np.log(np.clip(p, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-6, 1))).mean())  # noqa: E731
        bets = g[g["p_final"] * g["entry_best"] > EV_BAR]
        entry = {"settled_props": int(len(g)),
                 "logloss_market_frozen": round(ll(g["p_market"].to_numpy()), 5) if len(g) else None,
                 "logloss_market_wowza_frozen": round(ll(g["p_final"].to_numpy()), 5) if len(g) else None,
                 "rule": judge(bets, base_clv, base_beat)}
        if mk == "goals":
            impl = 1 / g["entry_best"]
            cell = g[(g["position"] == "F") & (impl < 0.30) & (g["p_model"] - impl > 0.05)]
            entry["exploratory_cell"] = judge(cell, base_clv, base_beat)
        res["markets"][mk] = entry
    return res


def to_md(r: dict) -> str:
    L = ["# Player V3 forward test (pre-registered)", "",
         f"Registered {r['registered_on']}; counts props on matches from {r['window_from']}. Rules frozen in "
         f"src/player_v3/forward.py and registry/player_v3_forward/registration.json. EDGE needs >= {N_MIN} bets, "
         "a positive 90% ROI lower bound, positive median CLV and a beat-the-close share above the all-props baseline.", "",
         f"Settled priced props in the window: **{r['props_in_window']}** · generated {r['generated_at']}", "",
         "| Market | Props | Log loss market / +Wowza | Bets | Hit | ROI (90%) | CLV median | Beat close (baseline) | Verdict |",
         "|---|---:|---|---:|---:|---|---:|---|---|"]
    for mk, e in r["markets"].items():
        for label, j in (("rule", e.get("rule")), ("cell: F, scorer, <30%, +5pts", e.get("exploratory_cell"))):
            if not j:
                continue
            name = mk if label == "rule" else f"{mk} {label}"
            ci = j.get("roi_ci90") or [None, None]
            L.append(f"| {name} | {e.get('settled_props', 0)} | {e.get('logloss_market_frozen')} / "
                     f"{e.get('logloss_market_wowza_frozen')} | {j.get('bets', 0)} | {j.get('hit', '')} | "
                     f"{j.get('roi', '')} {ci} | {j.get('clv_median', '')} | {j.get('clv_beat_share', '')} "
                     f"({j.get('baseline_beat_share', '')}) | {j['verdict']} |")
    L += ["", "Paper only. Props stay paper-only in v9 whatever this shows; money needs a separate owner decision."]
    return "\n".join(L) + "\n"


def main() -> int:
    X = load_features()
    rows = settle(prop_items(), X)
    reg_f = REG_DIR / "registration.json"
    if reg_f.exists() and all((MODEL_DIR / f"{m}.pkl").exists() for m in MARKETS):
        reg = json.loads(reg_f.read_text(encoding="utf-8"))
    else:
        reg = freeze(X, rows)
    r = evaluate(X, rows, reg)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "forward_test.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (OUT / "FORWARD_TEST.md").write_text(to_md(r), encoding="utf-8")
    print(to_md(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
