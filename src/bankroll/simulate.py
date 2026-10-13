"""Chronological bankroll replay + resampled risk, sizing every day with v9's own reader.

replay(bets, policy)       -> per-day path and summary metrics (start = 100)
risk(bets, policy)         -> matchday-block and week-block bootstrap risk estimates
stress(bets, policy)       -> the brief's stress scenarios

A day's bets are sized from the START-of-day bankroll and settled together at day end (football
slates settle within the day; this is the conservative reading of "current bankroll").
Drawdown throttle: the reader is given the high-water mark; a reduced level is held as a FLOOR
and lifted one step only at a month boundary once drawdown is back under the previous boundary.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.bankroll.data import v9_reader

LEVELS = (1.0, 0.75, 0.50, 0.0)


def _unit_return(b: pd.DataFrame, haircut: float = 0.0) -> np.ndarray:
    """P/L per unit staked; a haircut lowers the price paid on wins: odds*(1-h) - 1."""
    u = b["unit"].to_numpy(float)
    if haircut:
        win = b["result"].eq("WIN").to_numpy() & (u > 0)
        u = u.copy()
        u[win] = b["odds"].to_numpy(float)[win] * (1 - haircut) - 1
    return u


def day_plans(bets: pd.DataFrame, policy: dict) -> dict:
    """{date: {level: fractions array}} — sizing at each throttle level, computed once."""
    R = v9_reader()
    plans = {}
    for d, g in bets.groupby("date", sort=True):
        sel = g[["fixture", "league", "model_type", "market", "signal_tier", "odds"]]
        plans[d] = {lv: R.size_day(sel, policy, bankroll=100.0, peak=100.0,
                                   dd_floor=lv)["final_fraction"].to_numpy(float) for lv in LEVELS}
    return plans


def _throttle(policy: dict, dd: float) -> float:
    m = 1.0
    for thr, mult in sorted(policy.get("drawdown_throttle", []), key=lambda x: x[0]):
        if dd >= thr:
            m = float(mult)
    return m


def _run(days, plans, rets, policy, start=100.0, months=None):
    bank, peak, floor = start, start, 1.0
    path = []
    last_month = None
    for i, d in enumerate(days):
        dd = 1 - bank / peak
        lvl_now = _throttle(policy, dd)
        mon = None if months is None else months[i]
        if mon is not None and mon != last_month and last_month is not None:
            # review cycle: lift the floor one level if drawdown is back under its boundary
            if lvl_now > floor:
                floor = min(lvl_now, LEVELS[max(LEVELS.index(floor) - 1, 0)])
        last_month = mon
        floor = min(floor, lvl_now)
        f = plans[i][floor] if floor in plans[i] else plans[i][min(plans[i], key=lambda k: abs(k - floor))]
        exp = float(f.sum())
        pnl = float((f * rets[i]).sum()) * bank
        bank += pnl
        peak = max(peak, bank)
        path.append((d, bank, exp, int((f > 0).sum()), floor))
    return pd.DataFrame(path, columns=["date", "bankroll", "exposure", "bets", "throttle"])


def metrics(path: pd.DataFrame, start: float = 100.0) -> dict:
    if path.empty:
        return {"end": start, "return_pct": 0.0, "max_dd": 0.0, "bets": 0}
    b = path["bankroll"].to_numpy(float)
    peak = np.maximum.accumulate(np.r_[start, b])[1:]
    dd = 1 - b / peak
    daily = np.diff(np.r_[start, b]) / np.r_[start, b][:-1]
    lose = (daily < 0).astype(int)
    streak = max((len(s) for s in "".join(map(str, lose)).split("0")), default=0)
    p = path.assign(r=daily, d=pd.to_datetime(path["date"]))
    wk = p.groupby(p["d"].dt.to_period("W"))["r"].apply(lambda x: float(np.prod(1 + x) - 1))
    mo = p.groupby(p["d"].dt.to_period("M"))["r"].apply(lambda x: float(np.prod(1 + x) - 1))
    down = daily[daily < 0]
    logg = float(np.log(b[-1] / start))
    mdd = float(dd.max())
    return {"end": round(float(b[-1]), 2), "return_pct": round(100 * (b[-1] / start - 1), 2),
            "log_growth": round(logg, 4), "max_dd": round(mdd, 4),
            "longest_losing_days": int(streak), "worst_day": round(float(daily.min()), 4),
            "worst_week": round(float(wk.min()), 4), "worst_month": round(float(mo.min()), 4),
            "avg_daily_exposure": round(float(path["exposure"].mean()), 4),
            "max_daily_exposure": round(float(path["exposure"].max()), 4),
            "bets": int(path["bets"].sum()), "days": int(len(path)),
            "volatility": round(float(daily.std()), 4),
            "sortino": round(float(daily.mean() / down.std()) if len(down) > 1 and down.std() > 0 else 0.0, 4),
            "return_over_maxdd": round(float((b[-1] / start - 1) / mdd) if mdd > 0 else 0.0, 3)}


def replay(bets: pd.DataFrame, policy: dict, haircut: float = 0.0, plans: dict | None = None):
    if bets.empty:
        return pd.DataFrame(columns=["date", "bankroll"]), metrics(pd.DataFrame())
    plans = plans or day_plans(bets, policy)
    days = sorted(plans)
    g = {d: x for d, x in bets.groupby("date", sort=True)}
    rets = [_unit_return(g[d], haircut) for d in days]
    months = [pd.Timestamp(d).strftime("%Y-%m") for d in days]
    path = _run(days, [plans[d] for d in days], rets, policy, months=months)
    return path, metrics(path)


def risk(bets: pd.DataFrame, policy: dict, n_paths: int = 2000, block: str = "day",
         seed: int = 11, plans: dict | None = None) -> dict:
    """Resample whole days (matchday block) or whole weeks (market-regime block) with
    replacement to the same length, replay with the policy's own throttle."""
    if bets.empty:
        return {}
    plans = plans or day_plans(bets, policy)
    days = sorted(plans)
    g = {d: x for d, x in bets.groupby("date", sort=True)}
    rets = {d: _unit_return(g[d]) for d in days}
    if block == "week":
        wk = pd.Series(days).map(lambda d: pd.Timestamp(d).to_period("W"))
        units = [list(np.array(days, dtype=object)[wk.to_numpy() == w]) for w in wk.unique()]
    else:
        units = [[d] for d in days]
    rng = np.random.default_rng(seed)
    ends, mdds = [], []
    for _ in range(n_paths):
        seq = []
        while len(seq) < len(days):
            seq += units[int(rng.integers(len(units)))]
        seq = seq[:len(days)]
        path = _run(seq, [plans[d] for d in seq], [rets[d] for d in seq], policy,
                    months=[k // 22 for k in range(len(seq))])
        b = path["bankroll"].to_numpy(float)
        ends.append(b[-1])
        mdds.append(float((1 - b / np.maximum.accumulate(np.r_[100.0, b])[1:]).max()))
    ends, mdds = np.array(ends), np.array(mdds)
    return {"block": block, "paths": n_paths,
            "p_maxdd_gt_10": round(float((mdds > 0.10).mean()), 4),
            "p_maxdd_gt_20": round(float((mdds > 0.20).mean()), 4),
            "p_below_75": round(float((ends < 75).mean()), 4),
            "p_below_50": round(float((ends < 50).mean()), 4),
            "end_p05": round(float(np.quantile(ends, 0.05)), 2),
            "end_median": round(float(np.median(ends)), 2),
            "end_p95": round(float(np.quantile(ends, 0.95)), 2)}


def stress(bets: pd.DataFrame, policy: dict) -> list[dict]:
    """The brief's stress scenarios; each replays the policy on a modified record."""
    base_path, base = replay(bets, policy)
    out = [{"scenario": "NORMAL_HISTORY", **base}]
    if bets.empty:
        return out
    plans = day_plans(bets, policy)
    stake = []
    for d, x in bets.groupby("date", sort=True):
        f = plans[d][1.0]
        stake.append(x.assign(_f=f))
    s = pd.concat(stake)
    s["_pl"] = s["_f"] * s["unit"]
    best_league = s.groupby("league")["_pl"].sum().idxmax() if s["_pl"].abs().sum() else None
    best_month = s.groupby("month")["_pl"].sum().idxmax() if s["_pl"].abs().sum() else None
    top5 = s[s["_f"] > 0].nlargest(5, "_pl").index
    tight = {"OU25": 2.30, "BTTS": 2.40, "OVER15": 1.80}
    tight_pol = {**policy, "tracks": {k: ({**v, "max_odds": min(v.get("max_odds", 9), tight.get(k.split("|")[-1], 9))}
                                          if isinstance(v, dict) else v) for k, v in policy["tracks"].items()}}
    scen = [("EX_ARGENTINA", bets[~bets["league"].str.contains("Argentina", na=False)], policy, 0.0),
            (f"EX_BEST_LEAGUE ({best_league})", bets[bets["league"] != best_league], policy, 0.0),
            (f"EX_BEST_MONTH ({best_month})", bets[bets["month"] != best_month], policy, 0.0),
            ("EX_5_LARGEST_WINS", bets.drop(index=top5, errors="ignore"), policy, 0.0),
            ("HAIRCUT_2.5PCT", bets, policy, 0.025), ("HAIRCUT_5PCT", bets, policy, 0.05),
            ("ODDS_CAPPED_TIGHTER", bets, tight_pol, 0.0)]
    for name, b, pol, h in scen:
        _, m = replay(b, pol, haircut=h)
        out.append({"scenario": name, **m})
    return out
