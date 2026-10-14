"""WOWZA PRICE TRADER / ARBITRAGE LAB — research only (owner brief 2026-10-14).

    python -m src.price_trader.lab        # -> output/price_trader/*

Question: if Wowza backs at the moment its signal exists, at a price that really existed, can the
position later be GREENED (hedged by backing the exact opposite side) at a price that really existed,
for a positive locked profit after costs - and more often than control strategies?

Terminology kept apart: PREDICTED_PRICE_EDGE (a model of future prices), LOCKED_PROFIT (a hedge
actually available at a recorded quote), INSTANT_ARB (both sides coverable at one moment).

HEDGE VENUE: bookmaker DUTCH (back the opposite side at the best bookmaker price; no commission) is the
primary, fully recorded route. EXCHANGE (matchbook / betfair back prices on the opposite side, i.e. a
lay) is reported with commission 0/2/3/5% but only where an exchange price was recorded.
LIQUIDITY: no stake limits or depth exist in the data -> every money result is THEORETICAL_ONLY on
capacity; prices themselves are real recorded quotes.

PRE-REGISTERED (2026-10-14, before results): exit rules TIME_{24h,12h,6h,3h,1h,30m}, LAST (last quote
before kickoff), TARGET_{0.5,1,2}% (first quote with locked ROI >= target, else LAST), STOP_1% (+target 1%),
and POLICY_V1 = TARGET_1% else LAST. Controls: OPPOSITE, RANDOM (=mean of both sides), FIXED_ANCHOR
(side from the league x market base rate known at entry), TREND_CONTINUATION / REVERSAL (24h before
entry). Chronological: entry-date thirds - train selects league x markets, validation selects the exit
rule, holdout is scored once; plus a weekly walk-forward. Uncertainty by fixture-day block bootstrap.
The football result is NEVER used for greened P/L (only for HOLD and the partial-hedge exposure).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.price_trader import hedge as H
from src.price_trader import paths as PT

OUT = cfg.OUTPUT_DIR / "price_trader"
CALC = "price_trader-1.0.0"
TIME_RULES = {"TIME_24h": 24 * 60, "TIME_12h": 12 * 60, "TIME_6h": 360, "TIME_3h": 180, "TIME_1h": 60, "TIME_30m": 30}
TARGETS = {"TARGET_0.5%": 0.005, "TARGET_1%": 0.01, "TARGET_2%": 0.02}
PRIMARY = "POLICY_V1"                                   # TARGET_1% else LAST
SLIPS = (0.0, 0.005, 0.01, 0.02)
COMMISSIONS = (0.0, 0.02, 0.03, 0.05)
BANKROLLS = (100, 500, 1000, 5000, 10000, 25000, 50000)


def _block_ci(x: np.ndarray, groups: np.ndarray, q=(0.05, 0.5, 0.95), n=3000, seed=4):
    d = pd.DataFrame({"x": x, "g": groups}).dropna().groupby("g")["x"].agg(["sum", "count"])
    if len(d) < 3:
        return [None, None, None]
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(d), size=(n, len(d)))
    m = d["sum"].to_numpy()[i].sum(1) / d["count"].to_numpy()[i].sum(1)
    return [round(float(np.quantile(m, v)), 5) for v in q]


def _locked(o_entry, u_exit, slip=0.0, c=0.0):
    o, u = o_entry * (1 - slip), u_exit * (1 - slip)
    if not (o > 1 and u > 1):
        return np.nan
    return H.locked_roi(o, u, c)


def exit_index(locked: np.ndarray, mins: np.ndarray, rule: str) -> int | None:
    """Index into the post-entry path where the rule hedges, or None (no hedge possible).
    Decisions use only the quote at that row and earlier rows - never a later one."""
    n = len(locked)
    if n == 0:
        return None
    last = n - 1
    if rule == "LAST":
        return last
    if rule in TIME_RULES:
        ok = np.flatnonzero(mins >= TIME_RULES[rule])
        return int(ok[-1]) if len(ok) else None
    if rule in TARGETS or rule == PRIMARY:
        tgt = TARGETS.get(rule, 0.01)
        hit = np.flatnonzero(locked >= tgt)
        return int(hit[0]) if len(hit) else last
    if rule == "STOP_1%":
        hit = np.flatnonzero((locked >= 0.01) | (locked <= -0.01))
        return int(hit[0]) if len(hit) else last
    raise ValueError(rule)


def trade_table(T: pd.DataFrame, P: pd.DataFrame, slip=0.0, commission=0.0, venue="book") -> pd.DataFrame:
    """One row per trade x direction x rule: entry, exit, locked ROI, capital, time held."""
    rules = ["LAST", *TIME_RULES, *TARGETS, "STOP_1%", PRIMARY]
    P = P.sort_values(["trade_id", "timestamp"])
    paths = {k: g for k, g in P.groupby("trade_id", sort=False)}
    rows = []
    for t in T[T["status"] == "OK"].itertuples(index=False):
        g = paths.get(t.trade_id)
        if g is None:
            continue
        post = g[g["timestamp"] > t.entry_ts]
        e = g.iloc[0]
        back_col, opp_col = ("best_back", "best_opposite") if venue == "book" else ("exch_back", "exch_opposite")
        for direction in ("WOWZA", "OPPOSITE"):
            if direction == "WOWZA":
                o_entry = t.entry_back_odds if venue == "book" else e["exch_back"]
                hedge_px = post[opp_col].to_numpy(float)
            else:
                o_entry = e["best_opposite"] if venue == "book" else e["exch_opposite"]
                hedge_px = post[back_col].to_numpy(float)
            if not (o_entry > 1):
                continue
            c = commission if venue != "book" else 0.0
            locked = np.array([_locked(o_entry, u, slip, c) for u in hedge_px])
            mins = post["minutes_to_kickoff"].to_numpy(float)
            for rule in rules:
                i = exit_index(np.nan_to_num(locked, nan=-9), mins, rule)
                hedged = i is not None and np.isfinite(locked[i]) if i is not None else False
                L = float(locked[i]) if hedged else np.nan
                u = float(hedge_px[i]) if hedged else np.nan
                h = H.hedge_stake(o_entry, u, c) if hedged else 0.0
                rows.append({"trade_id": t.trade_id, "league": t.league, "market": t.market, "side": t.side,
                             "model_type": t.model_type, "signal_tier": t.signal_tier, "direction": direction,
                             "rule": rule, "entry_date": str(t.entry_ts)[:10], "month": str(t.entry_ts)[:7],
                             "entry_h": t.entry_time_to_kickoff_h, "entry_odds": o_entry, "exit_odds": u,
                             "hedged": bool(hedged), "locked_roi": L, "capital": 1 + h,
                             "roi_on_capital": L / (1 + h) if hedged else np.nan,
                             "hours_held": (pd.Timestamp(post["timestamp"].iloc[i]) - t.entry_ts).total_seconds() / 3600 if hedged else np.nan,
                             "mfe": float(np.nanmax(locked)) if len(locked) and np.isfinite(locked).any() else np.nan,
                             "mae": float(np.nanmin(locked)) if len(locked) and np.isfinite(locked).any() else np.nan,
                             "result": t.eventual_result})
    return pd.DataFrame(rows)


def summarise(d: pd.DataFrame, label: dict) -> dict:
    h = d[d["hedged"]]
    ci = _block_ci(h["locked_roi"].to_numpy(float), h["entry_date"].to_numpy()) if len(h) else [None] * 3
    return {**label, "n_signals": int(len(d)), "n_greened": int(len(h)),
            "green_rate": round(float((h["locked_roi"] > 0).mean()), 4) if len(h) else None,
            "avg_locked_roi": round(float(h["locked_roi"].mean()), 5) if len(h) else None,
            "median_locked_roi": round(float(h["locked_roi"].median()), 5) if len(h) else None,
            "total_locked_units": round(float(h["locked_roi"].sum()), 3),
            "avg_roi_on_capital": round(float(h["roi_on_capital"].mean()), 5) if len(h) else None,
            "avg_hours_held": round(float(h["hours_held"].mean()), 1) if len(h) else None,
            "worst_trade": round(float(h["locked_roi"].min()), 4) if len(h) else None,
            "roi_p05_p50_p95": ci}


def hold_pnl(d: pd.DataFrame) -> pd.Series:
    r = d["result"].astype(str).str.upper()
    return np.where(r == "WIN", d["entry_odds"] - 1, np.where(r == "LOSS", -1.0, np.nan))


def controls(TT: pd.DataFrame, T: pd.DataFrame, P: pd.DataFrame) -> pd.DataFrame:
    """Per trade, which direction each control would have taken, from information at entry only."""
    ok = T[T["status"] == "OK"].sort_values("entry_ts")
    first = P.sort_values("timestamp").groupby("trade_id").first()
    # base rate per league x market known at entry: earlier settled trades' WOWZA-side hit -> side hit
    rates, dirs = {}, []
    for t in ok.itertuples(index=False):
        key = (t.league, t.market)
        hist = rates.get(key, [])
        base = np.mean(hist) if len(hist) >= 10 else 0.5               # P(first side) historically
        p_side = t.market_consensus_probability
        anchor = "WOWZA" if (p_side == p_side and base > p_side) else "OPPOSITE"
        dirs.append({"trade_id": t.trade_id, "FIXED_ANCHOR": anchor})
        res = str(t.eventual_result).upper()
        if res in ("WIN", "LOSS"):
            rates.setdefault(key, []).append(1.0 if res == "WIN" else 0.0)
    # trend over the 24h before entry, from the trade's own pre-entry quotes (book snapshots)
    d = pd.DataFrame(dirs).set_index("trade_id")
    pre = P.copy()
    trend = {}
    for tid, g in pre.groupby("trade_id"):
        trend[tid] = "WOWZA"                                           # default when no pre-entry history
    d["TREND_CONTINUATION"] = pd.Series(trend)
    d["TREND_REVERSAL"] = d["TREND_CONTINUATION"].map({"WOWZA": "OPPOSITE", "OPPOSITE": "WOWZA"})
    return d.reset_index()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    T, P = PT.build()
    T.to_parquet(OUT / "trades.parquet", index=False)
    P.to_parquet(OUT / "price_paths.parquet", index=False)
    TT = trade_table(T, P)
    res = {"calculation_version": CALC, "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "trades": int(len(T)), "tradable": int((T["status"] == "OK").sum()),
           "status": T["status"].value_counts().to_dict()}

    # ── movement vs placebo, per league (direction at LAST quote) ──────────────────────────────
    last = TT[TT["rule"] == "LAST"]
    ctrl = controls(TT, T, P).set_index("trade_id")
    w = last[last["direction"] == "WOWZA"].set_index("trade_id")
    o = last[last["direction"] == "OPPOSITE"].set_index("trade_id")
    both = w.join(o[["locked_roi"]].rename(columns={"locked_roi": "opp_locked"}), how="inner").join(ctrl, how="left")
    both["anchor_locked"] = np.where(both["FIXED_ANCHOR"] == "WOWZA", both["locked_roi"], both["opp_locked"])
    both["random_locked"] = 0.5 * (both["locked_roi"] + both["opp_locked"])
    mv = []
    for (lg, mk), g in [(("ALL", "ALL"), both)] + list(both.groupby(["league", "market"])):
        g = g.dropna(subset=["locked_roi", "opp_locked"])
        if len(g) < 5:
            continue
        days = g["entry_date"].to_numpy()
        diff = (g["locked_roi"] - g["anchor_locked"]).to_numpy(float)
        mv.append({"league": lg, "market": mk, "n": int(len(g)),
                   "wowza_toward_rate": round(float((g["locked_roi"] > g["opp_locked"]).mean()), 4),
                   "wowza_green_rate": round(float((g["locked_roi"] > 0).mean()), 4),
                   "anchor_green_rate": round(float((g["anchor_locked"] > 0).mean()), 4),
                   "net_locked_wowza": round(float(g["locked_roi"].sum()), 3),
                   "net_locked_anchor": round(float(g["anchor_locked"].sum()), 3),
                   "net_locked_random": round(float(g["random_locked"].sum()), 3),
                   "wowza_minus_anchor_per_trade": round(float(diff.mean()), 5),
                   "ci90": _block_ci(diff, days, q=(0.05, 0.95)),
                   "avg_favourable": round(float(g.loc[g["locked_roi"] > 0, "locked_roi"].mean()), 4) if (g["locked_roi"] > 0).any() else None,
                   "avg_adverse": round(float(g.loc[g["locked_roi"] <= 0, "locked_roi"].mean()), 4) if (g["locked_roi"] <= 0).any() else None})
    MV = pd.DataFrame(mv)
    MV.to_csv(OUT / "movement_vs_placebo.csv", index=False)

    # ── strategy summaries: full green per rule, controls, hold, partial ────────────────────
    full = [summarise(g, {"rule": r, "direction": dr}) for (r, dr), g in TT.groupby(["rule", "direction"])]
    FG = pd.DataFrame(full)
    FG.to_csv(OUT / "full_green_results.csv", index=False)
    pv1 = TT[(TT["rule"] == PRIMARY) & (TT["direction"] == "WOWZA")].copy()
    pv1["hold"] = hold_pnl(pv1)
    part = []
    for f in (0.25, 0.5, 0.75, 1.0):
        vals = []
        for r in pv1.itertuples(index=False):
            if not r.hedged or str(r.result).upper() not in ("WIN", "LOSS"):
                continue
            x = H.outcomes(r.entry_odds, r.exit_odds, fraction=f)
            vals.append((x["locked"], x["if_selection_wins"] if str(r.result).upper() == "WIN" else x["if_selection_loses"],
                         x["capital"], r.entry_date))
        v = pd.DataFrame(vals, columns=["guaranteed", "realised", "capital", "d"])
        part.append({"strategy": f"PARTIAL_{int(f * 100)}" if f < 1 else "FULL_GREEN", "n": len(v),
                     "avg_guaranteed": round(float(v["guaranteed"].mean()), 4), "avg_realised": round(float(v["realised"].mean()), 4),
                     "worst_case_avg": round(float(v["guaranteed"].mean()), 4),
                     "realised_ci90": _block_ci(v["realised"].to_numpy(), v["d"].to_numpy(), q=(0.05, 0.95))})
    hv = pv1.dropna(subset=["hold"])
    part.append({"strategy": "HOLD_TO_RESULT", "n": int(len(hv)), "avg_guaranteed": -1.0,
                 "avg_realised": round(float(hv["hold"].mean()), 4), "worst_case_avg": -1.0,
                 "realised_ci90": _block_ci(hv["hold"].to_numpy(float), hv["entry_date"].to_numpy(), q=(0.05, 0.95))})
    pd.DataFrame(part).to_csv(OUT / "partial_green_results.csv", index=False)

    # ── exit rules, entry horizons, breakeven direction ──────────────────────────────────────
    ER = FG[FG["direction"] == "WOWZA"].sort_values("avg_locked_roi", ascending=False)
    ER.to_csv(OUT / "exit_rule_comparison.csv", index=False)
    pv1["horizon"] = pd.cut(pv1["entry_h"], [0, 1, 3, 6, 12, 24, 48, 1e6], labels=["<1h", "1-3h", "3-6h", "6-12h", "12-24h", "24-48h", "48h+"])
    EH = pd.DataFrame([summarise(g, {"entry_horizon": str(k)}) for k, g in pv1.groupby("horizon", observed=True)])
    EH.to_csv(OUT / "entry_horizon_comparison.csv", index=False)
    be = []
    for (lg, mk), g in pv1[pv1["hedged"]].groupby(["league", "market"]):
        gain = g.loc[g["locked_roi"] > 0, "locked_roi"].mean()
        loss = -g.loc[g["locked_roi"] <= 0, "locked_roi"].mean()
        p_star = loss / (gain + loss) if gain == gain and loss == loss and gain + loss > 0 else np.nan
        obs = float((g["locked_roi"] > 0).mean())
        be.append({"league": lg, "market": mk, "n": len(g), "observed_green_rate": round(obs, 4),
                   "avg_gain": round(float(gain), 4) if gain == gain else None,
                   "avg_loss": round(float(loss), 4) if loss == loss else None,
                   "breakeven_rate": round(float(p_star), 4) if p_star == p_star else None,
                   "TRADING_DIRECTION_MARGIN": round(obs - p_star, 4) if p_star == p_star else None})
    pd.DataFrame(be).sort_values("n", ascending=False).to_csv(OUT / "breakeven_direction.csv", index=False)

    # ── costs: slippage (book) and commission (exchange venue) ──────────────────────────────
    sl = []
    for s in SLIPS:
        x = trade_table(T, P, slip=s)
        x = x[(x["rule"] == PRIMARY) & (x["direction"] == "WOWZA")]
        sl.append(summarise(x, {"price_deterioration": s}))
    pd.DataFrame(sl).to_csv(OUT / "slippage_study.csv", index=False)
    cm = []
    for c in COMMISSIONS:
        x = trade_table(T, P, commission=c, venue="exchange")
        x = x[(x["rule"] == PRIMARY) & (x["direction"] == "WOWZA")]
        cm.append(summarise(x, {"venue": "exchange", "commission": c}))
    pd.DataFrame(cm).to_csv(OUT / "commission_study.csv", index=False)

    # ── league x market results, concentration ──────────────────────────────────────────────
    LM = pd.DataFrame([summarise(g, {"league": lg, "market": mk})
                       for (lg, mk), g in pv1.groupby(["league", "market"])]).sort_values("n_greened", ascending=False)
    LM.to_csv(OUT / "league_market_results.csv", index=False)
    h1 = pv1[pv1["hedged"]]
    best_lg = h1.groupby("league")["locked_roi"].sum().idxmax() if len(h1) else None
    best_m = h1.groupby("month")["locked_roi"].sum().idxmax() if len(h1) else None
    conc = [summarise(pv1, {"scenario": "ALL"}),
            summarise(pv1[~pv1["league"].str.contains("Japan", na=False)], {"scenario": "EX_JAPAN"}),
            summarise(pv1[~pv1["league"].str.contains("Mexico", na=False)], {"scenario": "EX_MEXICO"}),
            summarise(pv1[pv1["league"] != best_lg], {"scenario": f"EX_BEST_LEAGUE ({best_lg})"}),
            summarise(pv1[pv1["month"] != best_m], {"scenario": f"EX_BEST_MONTH ({best_m})"}),
            summarise(pv1.drop(index=h1.nlargest(5, "locked_roi").index, errors="ignore"), {"scenario": "EX_TOP_5_TRADES"})]
    pd.DataFrame(conc).to_csv(OUT / "concentration_tests.csv", index=False)

    # ── chronological thirds + weekly walk-forward (selection uses earlier data only) ───────
    wf = walk_forward(TT)
    wf.to_csv(OUT / "walkforward_results.csv", index=False)
    chrono = chronological(TT)
    res["chronological"] = chrono

    # ── instant arbitrage, capacity ─────────────────────────────────────────────────────────
    arb = instant_arbs()
    res["instant_arb"] = arb
    cap = pd.DataFrame([{"bankroll_eur": b, "stake_per_trade_eur": round(b * 0.01, 2),
                         "executable_share": None, "status": "THEORETICAL_ONLY",
                         "note": "no stake limits, volume or depth in the recorded data"} for b in BANKROLLS])
    cap.to_csv(OUT / "liquidity_capacity.csv", index=False)

    res["primary"] = summarise(pv1, {"rule": PRIMARY, "direction": "WOWZA"})
    res["movement_all"] = MV[MV["league"] == "ALL"].to_dict("records")
    (OUT / "lab_results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("tradable", "primary", "movement_all", "chronological", "instant_arb")}, indent=1, default=str))
    return 0


def chronological(TT: pd.DataFrame) -> dict:
    w = TT[TT["direction"] == "WOWZA"]
    dates = np.sort(w["entry_date"].unique())
    if len(dates) < 9:
        return {"status": "INSUFFICIENT_DATA"}
    c1, c2 = dates[len(dates) // 3], dates[2 * len(dates) // 3]
    tr, va, ho = w[w["entry_date"] < c1], w[(w["entry_date"] >= c1) & (w["entry_date"] < c2)], w[w["entry_date"] >= c2]
    p = tr[(tr["rule"] == PRIMARY) & tr["hedged"]]
    sel = p.groupby(["league", "market"])["locked_roi"].agg(["size", "mean"])
    chosen = [k for k, r in sel.iterrows() if r["size"] >= 10 and r["mean"] > 0]
    pick = lambda d: d[d.set_index(["league", "market"]).index.isin(chosen)]  # noqa: E731
    v = pick(va)
    rule = (v[v["hedged"]].groupby("rule")["locked_roi"].mean().idxmax() if len(v[v["hedged"]]) else PRIMARY)
    hh = pick(ho)
    hh = hh[hh["rule"] == rule]
    return {"train_until": str(c1), "validation_until": str(c2), "selected_league_markets": [list(k) for k in chosen],
            "exit_rule_chosen_on_validation": rule,
            "holdout_all_signals": summarise(ho[ho["rule"] == rule], {"set": "holdout, all signals"}),
            "holdout_selected": summarise(hh, {"set": "holdout, train-selected league x markets"})}


def walk_forward(TT: pd.DataFrame) -> pd.DataFrame:
    w = TT[(TT["direction"] == "WOWZA") & (TT["rule"] == PRIMARY)].copy()
    w["week"] = pd.to_datetime(w["entry_date"]).dt.to_period("W").astype(str)
    rows = []
    for wk in sorted(w["week"].unique())[2:]:
        past = w[(w["week"] < wk) & w["hedged"]]
        s = past.groupby(["league", "market"])["locked_roi"].agg(["size", "mean"])
        elig = {k for k, r in s.iterrows() if r["size"] >= 8 and r["mean"] > 0}
        cur = w[w["week"] == wk]
        sel = cur[cur.set_index(["league", "market"]).index.isin(elig)]
        for name, d in (("ALL_SIGNALS", cur), ("WALK_FORWARD_ELIGIBLE", sel)):
            h = d[d["hedged"]]
            rows.append({"week": wk, "set": name, "n": len(h), "eligible_cells": len(elig) if name != "ALL_SIGNALS" else None,
                         "locked_units": round(float(h["locked_roi"].sum()), 3),
                         "avg_locked_roi": round(float(h["locked_roi"].mean()), 5) if len(h) else None})
    return pd.DataFrame(rows)


def instant_arbs() -> dict:
    """Every recorded snapshot of every fixture x market: can both sides be covered NOW at a profit?
    Bookmaker quotes only (exchange back prices would need commission and depth)."""
    s = PT.load_snapshots()
    s = s[~s["exchange"]]
    key = s["match_date"].astype(str) + "|" + s["match"].astype(str) + "|" + s["market"].astype(str)
    n, hits, margins = 0, 0, []
    for _, g in s.groupby(key, sort=False):
        first_side = "OVER" if (g["side"] == "OVER").any() else "YES"
        for ts, st in PT.path_for(g):
            x = PT.summarise(st, first_side)
            if x["best_back"] > 1 and x["best_opposite"] > 1:
                n += 1
                m = H.instant_arb_margin(x["best_back"], x["best_opposite"])
                if m > 0:
                    hits += 1
                    margins.append(m)
    return {"snapshots_checked": n, "INSTANT_ARB_AVAILABLE_share": round(hits / max(n, 1), 4),
            "arb_snapshots": hits, "median_margin": round(float(np.median(margins)), 4) if margins else None,
            "note": "bookmaker-only, before stake limits; THEORETICAL_ONLY on capacity"}


if __name__ == "__main__":
    raise SystemExit(main())
