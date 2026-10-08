"""Market-anchored O/U 2.5 challenger: start from the market, add the model only as a fitted residual.

    python -m src.studies.ou_challenger

    logit p_challenger = a + b * logit(p_market) + c * logit(p_v9)

WHY. On every priced fixture since 2026-08-10, v9's P(over) is compressed near 52% (sd 0.059 vs
the market's 0.092, AUC 0.528 vs 0.581), and adding it to the market improves nothing out of
sample. Its "UNDER edges" are matches the market rates high-scoring — and the market is right
(src/studies/ou_studies.py). A challenger anchored on the market lets the model speak only as
much as it has EARNED: the weight c is refitted each week on settled fixtures, and if the model
knows nothing, c goes to zero and so do its edges.

NO LOOKAHEAD, by construction:
  - decision time = the first v9 model snapshot at which 3+ books had ALREADY priced the fixture;
    the market used is each book's last quote at or before that moment, de-vigged (power) and
    medianed. Never the close.
  - weights are fitted only on fixtures whose match date is before the week being predicted.
  - the price a simulated tip is taken at is the median raw book price at decision time.

FORWARD RECORD. Every run also scores upcoming fixtures and appends them to
output/studies/ou_challenger_forward.csv, first sight only, never revised — the prospective
evidence a backtest cannot provide.

Research only: nothing here changes v9. A switch is an owner decision after the forward record.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store
from src.data import v9_config
from src.studies import common as C

START = "2026-08-10"
EDGE_BAR = 0.05                     # the bot's team-market bar, for a like-for-like tip comparison
MIN_TRAIN = 150
FORWARD = cfg.OUTPUT_DIR / "studies" / "ou_challenger_forward.csv"


def decision_panel() -> pd.DataFrame:
    ms = store.read("model_snapshots")
    ms = ms[ms["market"] == "OU25"].copy()
    ms["ts"] = pd.to_datetime(ms["observed_at"], utc=True, errors="coerce")
    bo = store.read("book_odds_snapshots")
    bo = bo[(bo["market"] == "OU25") & ~bo["is_post_kickoff"].astype(bool)].copy()
    bo["ts"] = pd.to_datetime(bo["snapshot_ts"], utc=True, errors="coerce")
    bo = bo.sort_values("ts")
    rows = []
    for fk, b in bo.groupby("fixture_key"):
        m = ms[ms["fixture_key"] == fk].sort_values("ts")
        if m.empty:
            continue
        for _, snap in m.iterrows():
            t = snap["ts"]
            q = b[b["ts"] <= t].drop_duplicates(["bookmaker", "side"], keep="last")
            w = q.pivot_table(index="bookmaker", columns="side", values="odds", aggfunc="last")
            if not {"OVER", "UNDER"} <= set(w.columns):
                continue
            w = w.dropna()
            if len(w) < 3:
                continue
            fair = [C.power_devig(o, u) for o, u in zip(w["OVER"], w["UNDER"])]
            fair = [f for f in fair if f is not None]
            if len(fair) < 3:
                continue
            # closing consensus, for CLV only (never used to decide)
            qc = b.drop_duplicates(["bookmaker", "side"], keep="last")
            wc = qc.pivot_table(index="bookmaker", columns="side", values="odds", aggfunc="last").dropna()
            fc = [C.power_devig(o, u) for o, u in zip(wc.get("OVER", []), wc.get("UNDER", []))]
            fc = [f for f in fc if f is not None]
            rows.append({"fixture_key": fk, "decision_ts": t, "match_date": snap["match_date"],
                         "league": snap["league"], "model_type": snap["model_type"],
                         "p_v9": float(snap["model_prob"]), "p_market": float(np.median(fair)),
                         "n_books": len(fair), "odds_over": float(w["OVER"].median()),
                         "odds_under": float(w["UNDER"].median()),
                         "p_market_close": float(np.median(fc)) if len(fc) >= 3 else np.nan})
            break
    D = pd.DataFrame(rows)
    names = store.read("market_snapshots").dropna(subset=["home_team", "away_team"]) \
        .drop_duplicates("fixture_key")[["fixture_key", "home_team", "away_team"]]
    return D.merge(names, on="fixture_key", how="left")


def _fit(train: pd.DataFrame, return_raw: bool = False):
    """Fit a, b, c with c >= 0. The model may ADD to the market, never be bet against.

    Measured 2026-10-08: the unconstrained c was negative in every one of six weekly refits
    (-0.18 to -0.88) — given the market, v9's lean pointed the wrong way. Letting a negative c
    through would turn the challenger into "fade Wowza", a strategy nobody designed and that would
    be fitted to the same small sample that produced it. So a negative fit means the model gets no
    say (c = 0, market recalibrated only); the raw value is still reported as a warning signal.
    """
    b, _ = C.fit_logistic(np.column_stack([C.logit(train["p_market"]), C.logit(train["p_v9"])]), train["y"])
    raw = b.copy()
    if b[2] < 0:
        b0, _ = C.fit_logistic(C.logit(train["p_market"])[:, None], train["y"])
        b = np.array([b0[0], b0[1], 0.0])
    return (b, raw) if return_raw else b


def _apply(b, d):
    return C.predict_logistic(b, np.column_stack([C.logit(d["p_market"]), C.logit(d["p_v9"])]))


def _tips(d: pd.DataFrame, pcol: str) -> pd.DataFrame:
    """Simulated tips: the side whose probability beats the median price by more than EDGE_BAR."""
    e_over = d[pcol] - 1 / d["odds_over"]
    e_under = (1 - d[pcol]) - 1 / d["odds_under"]
    side = np.where(e_over >= e_under, "OVER", "UNDER")
    edge = np.maximum(e_over, e_under)
    t = d.assign(side=side, edge=edge)
    t = t[t["edge"] > EDGE_BAR].copy()
    win = np.where(t["side"] == "OVER", t["y"] == 1, t["y"] == 0)
    odds = np.where(t["side"] == "OVER", t["odds_over"], t["odds_under"])
    t["u"] = np.where(win, odds - 1, -1.0)
    # CLV: fair probability of the chosen side at close minus the price's implied probability
    p_close_side = np.where(t["side"] == "OVER", t["p_market_close"], 1 - t["p_market_close"])
    t["clv_pp"] = (p_close_side - 1 / odds) * 100
    return t


def _summ(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"n": 0}
    return {"n": int(len(t)), "under_share": round(float((t["side"] == "UNDER").mean()), 3),
            "units": round(float(t["u"].sum()), 2), "roi": round(float(t["u"].mean()), 4),
            "roi_ci90": C.block_ci(t["u"], t["match_date"]),
            "mean_clv_pp": round(float(t["clv_pp"].mean()), 2) if t["clv_pp"].notna().any() else None,
            "avg_odds_taken": round(float(np.where(t["side"] == "OVER", t["odds_over"], t["odds_under"]).mean()), 3)}


def run() -> dict:
    today = pd.Timestamp.now(tz="UTC").normalize()
    D = decision_panel()
    D = D[D["match_date"] >= START].copy()
    R = C.results(START, (today - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), v9_config.league_ids())
    j = C.match_frames(D, R)
    S = D[j.notna()].copy()
    rr = R.loc[j[j.notna()].astype(int).to_numpy()].reset_index(drop=True)
    S = S.reset_index(drop=True)
    S["y"] = C.outcome("OU25", rr["hg"], rr["ag"])
    S["week"] = pd.to_datetime(S["match_date"]).dt.to_period("W-SUN").astype(str)

    # walk-forward by week
    preds, coefs = [], []
    for wk in sorted(S["week"].unique()):
        train = S[S["week"] < wk]
        test = S[S["week"] == wk]
        if len(train) < MIN_TRAIN:
            continue
        b, raw = _fit(train, return_raw=True)
        coefs.append({"week": wk, "n_train": int(len(train)), "a": round(float(b[0]), 3),
                      "b_market": round(float(b[1]), 3), "c_model": round(float(b[2]), 3),
                      "c_model_unconstrained": round(float(raw[2]), 3)})
        preds.append(test.assign(p_ch=_apply(b, test)))
    P = pd.concat(preds) if preds else pd.DataFrame()
    out = {"window_from": START, "decision_fixtures": int(len(D)), "settled_matched": int(len(S)),
           "oos_fixtures": int(len(P)), "weekly_coefficients": coefs}
    if not P.empty:
        out["probabilistic_oos"] = {
            k: {"logloss": round(float(C.logloss(P[c], P["y"]).mean()), 5),
                "brier": round(float(C.brier(P[c], P["y"]).mean()), 5)}
            for k, c in (("market", "p_market"), ("v9", "p_v9"), ("challenger", "p_ch"))}
        dll = C.logloss(P["p_ch"], P["y"]) - C.logloss(P["p_v9"], P["y"])
        out["challenger_minus_v9_logloss"] = {"mean": round(float(dll.mean()), 5),
                                              "ci90": C.block_ci(dll, P["match_date"])}
        out["tips_at_5pct_edge"] = {"v9": _summ(_tips(P, "p_v9")), "challenger": _summ(_tips(P, "p_ch"))}
        out["tips_by_track"] = {tr: {"v9": _summ(_tips(g, "p_v9")), "challenger": _summ(_tips(g, "p_ch"))}
                                for tr, g in P.groupby("model_type")}

    # forward record: upcoming fixtures, scored with weights fitted on everything settled
    if len(S) >= MIN_TRAIN:
        b, raw = _fit(S, return_raw=True)
        out["current_weights"] = {"a": round(float(b[0]), 3), "b_market": round(float(b[1]), 3),
                                  "c_model": round(float(b[2]), 3),
                                  "c_model_unconstrained": round(float(raw[2]), 3), "n_train": int(len(S))}
        up = D[pd.to_datetime(D["match_date"]) >= today.tz_localize(None)].copy()
        if len(up):
            up["p_challenger"] = _apply(b, up)
            up["logged_at"] = cfg.utc_now_iso()
            up["weights"] = f"a={b[0]:.3f} b={b[1]:.3f} c={b[2]:.3f}"
            t = _tips(up.assign(y=np.nan, p_market_close=np.nan), "p_challenger")
            up["challenger_tip"] = up["fixture_key"].map(dict(zip(t["fixture_key"], t["side"])))
            up["challenger_edge"] = up["fixture_key"].map(dict(zip(t["fixture_key"], t["edge"].round(4))))
            cols = ["fixture_key", "logged_at", "decision_ts", "match_date", "league", "model_type",
                    "home_team", "away_team", "p_v9", "p_market", "p_challenger", "n_books",
                    "odds_over", "odds_under", "challenger_tip", "challenger_edge", "weights"]
            prev = pd.read_csv(FORWARD) if FORWARD.exists() else pd.DataFrame(columns=cols)
            new = up[~up["fixture_key"].isin(set(prev["fixture_key"]))][cols]
            FORWARD.parent.mkdir(parents=True, exist_ok=True)
            pd.concat([prev, new], ignore_index=True).to_csv(FORWARD, index=False)
            out["forward_logged_this_run"] = int(len(new))
    return out


if __name__ == "__main__":
    import json
    r = run()
    C.write("ou_challenger", r)
    print(json.dumps({k: v for k, v in r.items() if k != "weekly_coefficients"}, indent=1, default=str))
    print("weights by week (used, unconstrained):", [(c["week"][:10], c["c_model"], c["c_model_unconstrained"]) for c in r.get("weekly_coefficients", [])])
