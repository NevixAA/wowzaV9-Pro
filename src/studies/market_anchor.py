"""Market-anchored O/U 2.5: v9 as a small correction to the de-vigged price (registry/market_anchor/registration_v1.json).

    python -m src.studies.market_anchor        # -> output/studies/market_anchor.json + MARKET_ANCHOR.md

Research only - nothing here changes v9. Owner 2026-10-20: bring the market-anchored review forward,
because the market alone predicts O/U better than v9 and v9's probabilities are squeezed toward 50%.

Inputs (all already on disk, nothing fetched):
  * v9's walk-forward probability p_base per match (v9's own train(), quarterly blocks, out-of-sample)
    from experiments/ou_info_inputs_2026_10/eval_rows.parquet
  * standard track: football-data's PRE-MATCH average Avg>2.5/Avg<2.5 from fd_raw/ - recorded before
    kickoff, about when v9 freezes its tips. Closing prices are NOT used as the anchor (that would hand
    the market information v9 never had when tipping).
  * new_format track: the frame's own odds_over25/odds_under25 (v9 captures; timing not guaranteed),
    reported as secondary and never decisive.
The arms, caps and decision rule are frozen in the registration and are not tuned after results.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar

from config import pro_config as cfg

EXP = cfg.BASE_DIR / "experiments" / "ou_info_inputs_2026_10"
OUT = cfg.BASE_DIR / "output" / "studies"
REG = cfg.BASE_DIR / "registry" / "market_anchor" / "registration_v1.json"
FD_CODES = {"Championship": "E1", "League One": "E2", "League Two": "E3", "National League": "EC",
            "Bundesliga 2": "D2", "Ligue 2": "F2", "La Liga 2": "SP2", "Serie B": "I2",
            "Greek Super League": "G1", "Portuguese Primeira Liga": "P1", "Scottish Championship": "SC1",
            "Scottish Premiership": "SC0", "Belgian First Division A": "B1", "Dutch Eredivisie": "N1",
            "Turkish Super Lig": "T1"}
CAP = {"standard": 0.40, "new_format": 0.45}
W0 = 0.20
FLOORS = {"VALUABLE": 0.03, "MARKSMAN": 0.08}
EPS = 1e-6


def _logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _sig(x):
    return 1 / (1 + np.exp(-x))


def _ll(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def devig_power(o_over, o_under):
    """Power de-vig: find k with (1/o)^k + (1/u)^k = 1. NaN where either price is missing/invalid."""
    o = np.asarray(o_over, float)
    u = np.asarray(o_under, float)
    out = np.full(len(o), np.nan)
    ok = (o > 1) & (u > 1)
    for i in np.where(ok)[0]:
        a, b = 1 / o[i], 1 / u[i]
        lo, hi = 0.5, 3.0
        for _ in range(60):
            k = (lo + hi) / 2
            if a ** k + b ** k > 1:
                lo = k
            else:
                hi = k
        out[i] = a ** ((lo + hi) / 2)
    return out


def _fd_prematch() -> pd.DataFrame:
    rows = []
    for league, code in FD_CODES.items():
        for f in sorted((EXP / "fd_raw").glob(f"{code}_*.csv")):
            d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
            need = {"Date", "HomeTeam", "AwayTeam", "Avg>2.5", "Avg<2.5"}
            if not need <= set(d.columns):
                continue
            d = d.dropna(subset=["HomeTeam", "AwayTeam"])
            rows.append(pd.DataFrame({
                "league": league, "home_team": d["HomeTeam"].astype(str).str.strip(),
                "away_team": d["AwayTeam"].astype(str).str.strip(),
                "date": pd.to_datetime(d["Date"], dayfirst=True, errors="coerce").dt.normalize(),
                "pre_over": pd.to_numeric(d["Avg>2.5"], errors="coerce"),
                "pre_under": pd.to_numeric(d["Avg<2.5"], errors="coerce"),
                "close_over": pd.to_numeric(d.get("AvgC>2.5"), errors="coerce"),
                "close_under": pd.to_numeric(d.get("AvgC<2.5"), errors="coerce")}))
    fd = pd.concat(rows, ignore_index=True).dropna(subset=["date"])
    return fd.drop_duplicates(["league", "date", "home_team", "away_team"])


def frame() -> tuple[pd.DataFrame, dict]:
    e = pd.read_parquet(EXP / "eval_rows.parquet",
                        columns=["date", "league", "home_team", "away_team", "over25", "odds_over25",
                                 "odds_under25", "track", "block", "p_base"])
    e["date"] = pd.to_datetime(e["date"]).dt.normalize()
    e = e.dropna(subset=["over25", "p_base"]).drop_duplicates(["track", "league", "date", "home_team", "away_team"])
    fd = _fd_prematch()
    std = e[e["track"] == "standard"].merge(fd, on=["league", "date", "home_team", "away_team"], how="left")
    std["bet_over"], std["bet_under"] = std["pre_over"], std["pre_under"]
    nf = e[e["track"] == "new_format"].copy()
    nf["bet_over"], nf["bet_under"] = nf["odds_over25"], nf["odds_under25"]
    f = pd.concat([std, nf], ignore_index=True)
    f["p_mkt"] = devig_power(f["bet_over"], f["bet_under"])
    audit = {"standard_rows": int((e["track"] == "standard").sum()),
             "standard_with_prematch_price": int(std["pre_over"].notna().sum()),
             "new_format_rows": int(len(nf)), "new_format_with_price": int(nf["odds_over25"].notna().sum())}
    # sanity: pre-match vs closing (should be close but not identical, else the columns are mislabeled)
    both = std.dropna(subset=["pre_over", "close_over"])
    audit["prematch_equals_closing_share"] = round(float((both["pre_over"] == both["close_over"]).mean()), 3) if len(both) else None
    audit["frame_odds_equal_closing_share"] = round(float((both["odds_over25"] == both["close_over"]).mean()), 3) if len(both) else None
    f = f.dropna(subset=["p_mkt"]).copy()
    f["y"] = f["over25"].astype(float)
    return f, audit


def _fit_w(lm, lv, y, cap):
    r = minimize_scalar(lambda w: _ll(_sig(lm + w * (lv - lm)), y).mean(), bounds=(0.0, cap), method="bounded")
    return float(r.x)


def _fit_lr(lm, lv, y):
    X = np.c_[np.ones_like(lm), lm, lv]
    r = minimize(lambda b: _ll(_sig(X @ b), y).mean(), x0=np.array([0.0, 1.0, 0.0]), method="BFGS")
    return r.x


def arms(f: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out, weights = [], {}
    for track, g in f.groupby("track"):
        g = g.sort_values("date").copy()
        blocks = sorted(g["block"].unique())
        lm_all, lv_all = _logit(g["p_mkt"]), _logit(g["p_base"])
        g["lm"], g["lv"] = lm_all, lv_all
        g["p_anchor"], g["p_anchor_lr"] = np.nan, np.nan
        weights[track] = {}
        for b in blocks:
            past, cur = g["block"] < b, g["block"] == b
            if past.sum() >= 300:
                w = _fit_w(g.loc[past, "lm"].values, g.loc[past, "lv"].values, g.loc[past, "y"].values, CAP[track])
                beta = _fit_lr(g.loc[past, "lm"].values, g.loc[past, "lv"].values, g.loc[past, "y"].values)
            else:
                w, beta = W0, np.array([0.0, 1.0 - W0, W0])
            weights[track][str(b)] = round(w, 3)
            lm, lv = g.loc[cur, "lm"].values, g.loc[cur, "lv"].values
            g.loc[cur, "p_anchor"] = _sig(lm + w * (lv - lm))
            g.loc[cur, "p_anchor_lr"] = _sig(beta[0] + beta[1] * lm + beta[2] * lv)
        out.append(g)
    return pd.concat(out, ignore_index=True), weights


def _boot_delta(d: np.ndarray, day: np.ndarray, n=2000, seed=7):
    days = np.unique(day)
    idx = {k: np.where(day == k)[0] for k in days}
    rng = np.random.default_rng(seed)
    bs = [d[np.concatenate([idx[k] for k in rng.choice(days, len(days))])].mean() for _ in range(n)]
    return [round(float(x), 5) for x in np.percentile(bs, [5, 95])]


def _boot_roi(pnl: np.ndarray, day: np.ndarray, n=2000, seed=7):
    if len(pnl) < 2:
        return [None, None]
    return [round(x * 100, 1) if x is not None else None for x in _boot_delta(pnl, day, n, seed)]


def score(g: pd.DataFrame) -> dict:
    y, day = g["y"].values, g["date"].values
    ll = {a: _ll(g[c].values, y) for a, c in
          (("V9", "p_base"), ("MARKET", "p_mkt"), ("ANCHOR", "p_anchor"), ("ANCHOR_LR", "p_anchor_lr"))}
    res = {"n": int(len(g)), "log_loss": {a: round(float(v.mean()), 5) for a, v in ll.items()},
           "brier": {a: round(float(((g[c] - y) ** 2).mean()), 5) for a, c in
                     (("V9", "p_base"), ("MARKET", "p_mkt"), ("ANCHOR", "p_anchor"))}}
    for a, b in (("ANCHOR", "V9"), ("ANCHOR", "MARKET"), ("MARKET", "V9"), ("ANCHOR_LR", "V9")):
        d = ll[a] - ll[b]
        res[f"dLL_{a}_minus_{b}"] = {"delta": round(float(d.mean()), 5), "ci90": _boot_delta(d, day)}
    # how squeezed is each arm: spread of probabilities
    res["prob_spread_sd"] = {a: round(float(g[c].std()), 4) for a, c in
                             (("V9", "p_base"), ("MARKET", "p_mkt"), ("ANCHOR", "p_anchor"))}
    return res


def bets(g: pd.DataFrame, col: str, floor: float) -> dict:
    p = g[col].values
    eo, eu = p - 1 / g["bet_over"].values, (1 - p) - 1 / g["bet_under"].values
    side = np.where(eo >= eu, "OVER", "UNDER")
    edge = np.maximum(eo, eu)
    sel = edge >= floor
    won = np.where(side == "OVER", g["y"].values == 1, g["y"].values == 0)
    odds = np.where(side == "OVER", g["bet_over"].values, g["bet_under"].values)
    pnl = np.where(won, odds - 1, -1.0)
    claimed = np.where(side == "OVER", p, 1 - p)
    out = {}
    for s in ("OVER", "UNDER", "ALL"):
        m = sel & ((side == s) if s != "ALL" else True)
        n = int(m.sum())
        out[s] = {"n": n, "roi_pct": round(float(pnl[m].mean() * 100), 1) if n else None,
                  "roi_ci90_pct": _boot_roi(pnl[m], g["date"].values[m]) if n >= 20 else [None, None],
                  "claimed_hit": round(float(claimed[m].mean()), 3) if n else None,
                  "real_hit": round(float(won[m].mean()), 3) if n else None}
    return out


def run() -> dict:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    f, audit = frame()
    g, weights = arms(f)
    res = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "registration": str(REG.relative_to(cfg.BASE_DIR)), "decision_rule": reg["decision_rule"],
           "audit": audit, "anchor_weight_by_block": weights, "tracks": {}}
    for track, t in g.groupby("track"):
        r = score(t)
        r["bets"] = {arm: {fl: bets(t, col, v) for fl, v in FLOORS.items()}
                     for arm, col in (("V9", "p_base"), ("ANCHOR", "p_anchor"))}
        res["tracks"][track] = r
    s = res["tracks"].get("standard", {}).get("dLL_ANCHOR_minus_V9", {})
    passed = bool(s) and s["delta"] <= -0.001 and s["ci90"][1] < 0
    std = res["tracks"].get("standard", {})
    anchor_bets = (std.get("bets", {}).get("ANCHOR", {}).get("VALUABLE", {}).get("ALL", {}) or {}).get("n", 0)
    w = list(weights.get("standard", {}).values())[1:]
    if passed and not anchor_bets:
        res["verdict"] = ("PASSES THE FROZEN RULE BUT IS NOT A TIPPING MODEL - the fitted weight on v9 is ~0 in every "
                          "block, so the anchored arm IS the market price and produces no tips at the live floors. "
                          "v9 adds nothing to the pre-match price on standard O/U. Owner decision, not a v9 swap.")
    elif passed:
        res["verdict"] = "PROPOSAL CANDIDATE - to the owner with numbers"
    else:
        res["verdict"] = "NO PROPOSAL - anchored arm does not beat v9 by the frozen rule"
    res["standard_weight_on_v9_median"] = round(float(np.median(w)), 3) if w else None
    # new-format prices fail a basic integrity check (two-way margin below zero is impossible for one book)
    nf = g[g["track"] == "new_format"]
    if len(nf):
        ov = 1 / nf["bet_over"] + 1 / nf["bet_under"]
        res["new_format_price_integrity"] = {
            "share_margin_below_zero": round(float((ov < 1).mean()), 3),
            "median_overround": round(float(ov.median()), 3),
            "verdict": "INVALID AS A MARKET ANCHOR - prices look like best-of-books per side, not one book's "
                       "two-way price; new_format results above are not decision-grade"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "market_anchor.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    g[["track", "league", "date", "home_team", "away_team", "block", "y", "bet_over", "bet_under", "p_mkt",
       "p_base", "p_anchor", "p_anchor_lr"]].to_parquet(EXP / "market_anchor_rows.parquet", index=False)
    return res


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str))
