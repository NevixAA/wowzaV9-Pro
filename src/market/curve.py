"""
The odds curve: opening -> moving -> closing, locked before kick-off. Live kept separate.
========================================================================================
One definition, applied identically to every model and every market. The market key (`OU25`,
`BTTS`, `OVER15`, a player prop) never changes the rule — only the rows it is applied to.

    THE RULE
      closing  = the LAST snapshot at or before (kickoff - LOCK_SECONDS)     <- locked, 1 min
      opening  = the FIRST snapshot within HISTORY_DAYS before kickoff
      moving   = everything strictly between them
      live     = anything after the lock. NEVER part of the curve. Returned separately.

WHY THE LOCK EXISTS. v9 has no lock, and it cost us a false edge. `update_results` resolves the
close as the LAST archived snapshot for a fixture with no comparison against kickoff, so an in-play
price silently becomes "the close". Measured 2026-08-19 in `bets_ledger.csv`: 170 of 366 CLV rows
affected, and `new_format` mean CLV read **+26.26%** when it is actually **-0.015%**. That inflated
number fed v11's BET gate. The apparent CLV edge was entirely in-play prices.

The tell is worth remembering, because "wrong market" was the wrong diagnosis and looked plausible:
`over25` and `under25` are not different markets, they are the two bettable sides of ONE line from
one model probability. The archived pair at the bad moment is a perfectly coherent market —
overround median 1.016 across 3,446 fixtures. The prices were real, just late. With no goals scored
yet UNDER shortens and OVER lengthens together, which is why the error is one-directional per side
instead of scattered like genuine volatility.

LIVE ODDS ARE NOT GARBAGE. They are valuable — in-play drift, the live scanner, second-half models
— and they are only harmful when they masquerade as a close. So `split()` returns them rather than
discarding them, for a caller to persist to its own table. Nothing here deletes data.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Lock the close one minute before kick-off. Not zero: a snapshot stamped at the kickoff minute is
# ambiguous — clocks drift between the odds source and the fixture feed, and a "kickoff" timestamp
# is itself a scheduled value that can be a minute or two out. One minute of margin costs nothing,
# because the market barely moves in the final 60 seconds, and it removes the whole class of
# off-by-a-clock contamination.
LOCK_SECONDS = 60

# How far back a curve reaches. Prices more than a week out are thin, frequently unposted, and for
# most competitions simply absent, so they add noise rather than signal.
HISTORY_DAYS = 7


@dataclass
class Curve:
    """One fixture-market's pre-kick-off price path, plus the in-play rows kept aside."""
    market: str = ""
    opening: float | None = None
    closing: float | None = None
    n_points: int = 0
    first_ts: pd.Timestamp | None = None
    closing_ts: pd.Timestamp | None = None
    seconds_to_kickoff_at_close: float | None = None
    pre: pd.DataFrame = field(default_factory=pd.DataFrame)
    live: pd.DataFrame = field(default_factory=pd.DataFrame)
    reason: str = "ok"

    @property
    def drift(self) -> float | None:
        """closing / opening - 1. Positive means the price drifted OUT (longer)."""
        if self.opening in (None, 0) or self.closing is None:
            return None
        return self.closing / self.opening - 1.0

    @property
    def has_curve(self) -> bool:
        """More than one pre-kickoff point. One point is an ENTRY PRICE, not a curve."""
        return self.n_points > 1


def lock_time(kickoff: pd.Timestamp, lock_seconds: int = LOCK_SECONDS) -> pd.Timestamp:
    return kickoff - pd.Timedelta(seconds=lock_seconds)


def split(snapshots: pd.DataFrame, kickoff, *, ts_col: str = "snapshot_ts",
          odds_col: str = "odds", market: str = "", lock_seconds: int = LOCK_SECONDS,
          history_days: int = HISTORY_DAYS) -> Curve:
    """Split one fixture-market's snapshots into a pre-kick-off curve and live rows.

    An unparseable or missing kickoff yields NO curve and NO live rows, deliberately: without a
    kickoff there is no way to tell a closing price from an in-play one, and guessing is exactly
    how the contamination happened. Better to report `no_kickoff` and let the caller decide.
    """
    c = Curve(market=market)
    if snapshots is None or snapshots.empty:
        c.reason = "no_snapshots"
        return c
    ko = pd.to_datetime(kickoff, errors="coerce", utc=True)
    if ko is None or pd.isna(ko):
        c.reason = "no_kickoff"
        return c

    d = snapshots.copy()
    d["_ts"] = pd.to_datetime(d[ts_col], errors="coerce", utc=True)
    d["_odds"] = pd.to_numeric(d[odds_col], errors="coerce")
    d = d[d["_ts"].notna() & (d["_odds"] > 1.0)].sort_values("_ts")
    if d.empty:
        c.reason = "no_valid_rows"
        return c

    lock = lock_time(ko, lock_seconds)
    window_start = ko - pd.Timedelta(days=history_days)
    pre = d[(d["_ts"] <= lock) & (d["_ts"] >= window_start)]
    c.live = d[d["_ts"] > lock].drop(columns=["_ts", "_odds"], errors="ignore")
    if pre.empty:
        # Every snapshot is in-play (or older than the window). This is the case v9 silently
        # treated as a close.
        c.reason = "only_live" if len(c.live) else "outside_window"
        return c

    c.pre = pre.drop(columns=["_ts", "_odds"], errors="ignore")
    c.opening = float(pre["_odds"].iloc[0])
    c.closing = float(pre["_odds"].iloc[-1])
    c.n_points = int(len(pre))
    c.first_ts = pre["_ts"].iloc[0]
    c.closing_ts = pre["_ts"].iloc[-1]
    c.seconds_to_kickoff_at_close = float((ko - c.closing_ts).total_seconds())
    return c


def split_many(snapshots: pd.DataFrame, kickoffs: dict, *, key_cols: list[str],
               ts_col: str = "snapshot_ts", odds_col: str = "odds",
               market_col: str | None = "market", **kw) -> dict[tuple, Curve]:
    """Apply `split` per group. `kickoffs` maps the group key (minus market) to a kickoff time."""
    if snapshots is None or snapshots.empty:
        return {}
    out: dict[tuple, Curve] = {}
    for key, g in snapshots.groupby(key_cols, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        ko = kickoffs.get(key)
        if ko is None and len(key) > 1:
            ko = kickoffs.get(key[:-1])          # allow a kickoff keyed without the market
        mkt = str(g[market_col].iloc[0]) if market_col and market_col in g.columns else ""
        out[key] = split(g, ko, ts_col=ts_col, odds_col=odds_col, market=mkt, **kw)
    return out


def clv_pct(entry_odds: float, closing_odds: float) -> float | None:
    """CLV in percent: entry/closing - 1. Positive means a better price than the close.

    Only ever call this with a `Curve.closing`, never with "the last price we saw" — that
    substitution is the whole bug this module exists to prevent.
    """
    try:
        e, c = float(entry_odds), float(closing_odds)
    except (TypeError, ValueError):
        return None
    if e <= 1.0 or c <= 1.0:
        return None
    return (e / c - 1.0) * 100.0
