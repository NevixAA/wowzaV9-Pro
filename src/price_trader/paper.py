"""PAPER trading engine + verdict + report for the Price Trader lab (no money, no messages).

    python -m src.price_trader.paper      # after src.price_trader.lab -> paper_trades.csv, verdict, report

PAPER POLICY V1 (owner brief 36, frozen 2026-10-14): enter at the Wowza signal at the best bookmaker
back price then available; GREEN (dutch the opposite side at the best then-available price) the first
time the locked ROI reaches +1%; otherwise close at the last quote at or after 30 minutes before kickoff.
Prospective from PAPER_FROM: every decision uses only quotes recorded up to that moment.
States: OPEN, GREENED, STOPPED (closed below target), EXPIRED_NO_HEDGE (no later quote), DATA_FAILURE.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.price_trader import hedge as H
from src.price_trader.lab import OUT

PAPER_FROM = "2026-10-15"
TARGET = 0.01
CLOSE_MIN = 30


def paper_trades() -> pd.DataFrame:
    T = pd.read_parquet(OUT / "trades.parquet")
    P = pd.read_parquet(OUT / "price_paths.parquet").sort_values(["trade_id", "timestamp"])
    T = T[pd.to_datetime(T["signal_ts"], utc=True) >= pd.Timestamp(PAPER_FROM, tz="UTC")]
    now = pd.Timestamp.now(tz="UTC")
    paths = {k: g for k, g in P.groupby("trade_id", sort=False)}
    rows = []
    for t in T.itertuples(index=False):
        base = {"trade_id": t.trade_id, "league": t.league, "market": t.market, "side": t.side,
                "signal_ts": t.signal_ts, "kickoff": getattr(t, "kickoff", None)}
        if t.status != "OK":
            rows.append({**base, "state": "DATA_FAILURE", "reason": t.status})
            continue
        g = paths.get(t.trade_id)
        post = g[g["timestamp"] > t.entry_ts] if g is not None else pd.DataFrame()
        state, ts, u, L = "OPEN", None, np.nan, np.nan
        for r in post.itertuples(index=False):
            if not (r.best_opposite > 1):
                continue
            lr = H.locked_roi(t.entry_back_odds, r.best_opposite)
            if lr >= TARGET:
                state, ts, u, L = "GREENED", r.timestamp, r.best_opposite, lr
                break
        if state == "OPEN":
            ko = pd.Timestamp(t.kickoff) if pd.notna(getattr(t, "kickoff", None)) else None
            if ko is not None and ko <= now:
                last = post[(post["minutes_to_kickoff"] >= CLOSE_MIN) & (post["best_opposite"] > 1)]
                last = last if len(last) else post[post["best_opposite"] > 1]
                if len(last):
                    r = last.iloc[-1]
                    state, ts, u = "STOPPED", r["timestamp"], r["best_opposite"]
                    L = H.locked_roi(t.entry_back_odds, u)
                else:
                    state = "EXPIRED_NO_HEDGE"
        rows.append({**base, "state": state, "entry_back": t.entry_back_odds, "exit_ts": ts, "exit_opposite": u,
                     "locked_roi": L, "PAPER": True})
    return pd.DataFrame(rows)


def verdict(res: dict) -> dict:
    mv = (res.get("movement_all") or [{}])[0]
    pr = res.get("primary", {})
    ex = pd.read_csv(OUT / "commission_study.csv")
    sl = pd.read_csv(OUT / "slippage_study.csv")
    conc = pd.read_csv(OUT / "concentration_tests.csv")
    ex0 = ex[ex["commission"] == 0].iloc[0]
    ci = mv.get("ci90") or [None, None]
    toward = mv.get("wowza_toward_rate")
    positive = lambda v: v is not None and v == v and v > 0  # noqa: E731
    return {
        "calculation_version": res.get("calculation_version"), "generated_at": res.get("generated_at"),
        "MOVEMENT_SIGNAL_EXISTS": "NO" if toward is not None and toward <= 0.5 else "UNCLEAR",
        "MOVEMENT_BEATS_PLACEBO": "NO" if ci[1] is not None and ci[1] < 0 else ("YES" if ci[0] is not None and ci[0] > 0 else "UNCLEAR"),
        "EXECUTABLE_PRICE_DATA_SUFFICIENT": "NO",
        "FULL_GREEN_PROFITABLE_AFTER_COSTS": "YES" if positive(pr.get("avg_locked_roi")) else "NO",
        "PARTIAL_GREEN_BETTER_THAN_FULL_GREEN": "UNCLEAR",
        "TRADING_BEATS_HOLD": "NO",
        "BEST_ENTRY_HORIZON": "12-48h (highest green rate, still negative)",
        "BEST_EXIT_RULE": "NONE PROFITABLE (least bad: TIME_30m / LAST)",
        "BEST_LEAGUES": [], "BEST_MARKETS": [],
        "MAX_SUPPORTED_STAKE_BY_LIQUIDITY": {"status": "THEORETICAL_ONLY"},
        "EDGE_SURVIVES_EX_BEST_LEAGUE": "NO" if not positive(conc.iloc[3]["avg_locked_roi"]) else "YES",
        "EDGE_SURVIVES_SLIPPAGE": "NO" if not positive(sl.iloc[0]["avg_locked_roi"]) else "UNCLEAR",
        "EDGE_SURVIVES_COMMISSION": "NO" if not positive(ex0["avg_locked_roi"]) else "UNCLEAR",
        "PROSPECTIVE_CONFIRMATION": "INSUFFICIENT_DATA",
        "INSTANT_ARB": res.get("instant_arb"),
        "PRODUCTION_SELECTION_CHANGED": "NO", "REAL_TRADING_ENABLED": "NO", "CURRENT_STAKING_CHANGED": "NO",
    }


def main() -> int:
    res = json.loads((OUT / "lab_results.json").read_text(encoding="utf-8"))
    pt = paper_trades()
    pt.to_csv(OUT / "paper_trades.csv", index=False)
    v = verdict(res)
    (OUT / "price_trader_verdict.json").write_text(json.dumps(v, indent=1, default=str), encoding="utf-8")
    health = {"generated_at": res.get("generated_at"), "trades": res.get("trades"), "tradable": res.get("tradable"),
              "status_counts": res.get("status"), "paper_trades": int(len(pt)),
              "paper_states": pt["state"].value_counts().to_dict() if len(pt) else {},
              "exchange_lay_ladder": False, "liquidity_data": False}
    (OUT / "price_trader_health.json").write_text(json.dumps(health, indent=1, default=str), encoding="utf-8")
    print(json.dumps(v, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
