"""
Does the price move AFTER the team news is public? The test Pro's thesis needs.
==============================================================================
    python -m src.pipelines.news_impact [--window 60]

THE QUESTION. Pro's premise is that the market absorbs some information late. Everything else
tested this season says our models hold no information the market lacks — the O/U 2.5 residual
test and the BTTS market-relative test both come out at zero even after the inputs were fixed. So
the only remaining direction is information the market does not yet have, and lineups are the
obvious candidate: they publish ~1h before kickoff and they change the goal distribution.

WHAT CAN AND CANNOT BE CLAIMED. `team_news.first_seen_ts` is OUR first observation, not a
publication time — neither /fixtures/lineups nor /injuries carries one. So this cannot show "we
knew before the market". It answers the weaker question that still decides the thesis:

    once the team news was publicly available, did the price still move?

If prices have already finished moving by first_seen, there is no window and the thesis dies
cheaply. If they move substantially afterwards, there is something to investigate.

────────────────────────────────────────────────────────────────────────────────
THE CONTROL, WITHOUT WHICH THIS MEASURES NOTHING

Prices drift toward kickoff regardless of news — liquidity concentrates, stakes arrive, the book
tightens. Measured earlier this season: the market moves ~45x faster per unit time inside the last
hour than it does beyond 24h. So "the price moved after the lineup appeared" is the expected
outcome even if lineups carry no information at all, and reporting it as news response would
repeat the exact error that produced a confident 58% toward-Wowza rate fully explained by a
constant.

So every measurement here is a COMPARISON against the same fixture's own drift in an equivalent
earlier window:

    news window     first_seen  ->  first_seen + W
    control window  first_seen - W  ->  first_seen        (same length, same fixture, no news)

If |move| in the news window is not larger than in the control window, the lineup added nothing to
the price beyond ordinary pre-kickoff drift.

────────────────────────────────────────────────────────────────────────────────
FEASIBILITY, checked before writing this rather than assumed. Using book_odds_snapshots (the main
O/U market, per bookmaker), of 175 kicked-off fixtures with pre-match snapshots:

    T-120..60m  (before lineups)   140  80.0%
    T-60..0m    (after lineups)    160  91.4%
    BOTH sides of the moment       135  77.1%   <- the usable sample

The side-market archives cannot support this: they reach T-10m on 0.8% of series against the main
market's 35.4%. So this test runs on O/U 2.5 and says nothing about BTTS or the side markets.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store

DEFAULT_WINDOW_MIN = 60.0
MIN_BOOKS = 2

# OVERROUND BOUNDS, SET FROM THE DATA rather than guessed. Measured over 12,121 per-book
# two-sided OU25 quotes in book_odds_snapshots.csv:
#
#     p1 1.0057   median 1.0669   p99 1.1384   max 1.1471
#     above 1.15: 0 quotes        below 0.98: 0 quotes
#
# Nothing real exceeds 1.1471, so a 1.20 ceiling excludes no genuine quote while rejecting pairs
# that cannot be a coherent two-way market. My first version used 1.25, which admits values that
# do not occur — and a pair with a 25% margin entering the median would drag the consensus without
# being obviously wrong in any summary statistic. The widest-margin book observed is pmu_fr at a
# 1.1371 median, which stays comfortably inside.
OVERROUND_LO, OVERROUND_HI = 0.98, 1.20


def _devig(over: float, under: float) -> float | None:
    """Proportional de-vig -> P(over). None if the pair is not a coherent two-way market."""
    try:
        io, iu = 1.0 / float(over), 1.0 / float(under)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    s = io + iu
    if not (OVERROUND_LO <= s <= OVERROUND_HI):
        return None
    return io / s


def _consensus_series(snaps: pd.DataFrame) -> pd.DataFrame:
    """Per (fixture, snapshot_ts): de-vigged consensus P(over) across books.

    Median across books, not the best price. Conflating consensus with best-executable is how an
    edge gets manufactured out of a single generous quote.
    """
    d = snaps.copy()
    d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    piv = (d.pivot_table(index=["match", "kickoff_utc", "snapshot_ts", "bookmaker"],
                         columns="side", values="odds", aggfunc="last")
           .reset_index())
    if not {"OVER", "UNDER"} <= set(piv.columns):
        return pd.DataFrame()
    piv["p"] = [_devig(o, u) for o, u in zip(piv["OVER"], piv["UNDER"])]
    piv = piv.dropna(subset=["p"])
    g = (piv.groupby(["match", "kickoff_utc", "snapshot_ts"])
         .agg(p_market=("p", "median"), n_books=("p", "size")).reset_index())
    return g[g["n_books"] >= MIN_BOOKS]


def _p_at(series: pd.DataFrame, at: pd.Timestamp, tol_min: float = 25.0) -> float | None:
    """Consensus nearest to `at`, within tolerance. None rather than an extrapolation.

    A tolerance is required and must be stated: taking the nearest snapshot at any distance would
    silently compare a price from three hours earlier and attribute the difference to the news.
    """
    if series.empty:
        return None
    d = (series["_ts"] - at).abs()
    i = d.idxmin()
    if d.loc[i] > pd.Timedelta(minutes=tol_min):
        return None
    return float(series.loc[i, "p_market"])


def run(window_min: float = DEFAULT_WINDOW_MIN, quiet: bool = False) -> dict:
    try:
        news = store.read("team_news")
    except Exception as e:                                        # noqa: BLE001
        print(f"[news_impact] team_news unreadable: {e}")
        return {}
    if news is None or news.empty:
        print("[news_impact] team_news is empty — nothing observed yet. This table is "
              "FORWARD-ONLY: lineups carry no publication timestamp, so the past cannot be "
              "reconstructed and the sample can only accumulate from the day collection started.")
        return {"n": 0, "status": "NO_DATA_YET"}

    from src.data import v9_source as v9
    snaps = v9.fetch_csv("output/book_odds_snapshots.csv", required=False)
    if snaps.empty:
        print("[news_impact] no book_odds_snapshots available")
        return {"n": 0, "status": "NO_ODDS"}
    snaps = snaps[snaps["market"].astype(str).str.upper().str.contains("OU25|OVER|UNDER|2.5",
                                                                      regex=True, na=False)] \
        if "market" in snaps.columns else snaps
    cons = _consensus_series(snaps)
    if cons.empty:
        print("[news_impact] no usable two-sided consensus series")
        return {"n": 0, "status": "NO_CONSENSUS"}
    cons["_ts"] = pd.to_datetime(cons["snapshot_ts"], errors="coerce", utc=True)
    cons = cons.dropna(subset=["_ts"])

    # One observation per FIXTURE: the earliest first_seen across its two teams, because the
    # first lineup to appear is when the information became available.
    n = news.copy()
    n["_seen"] = pd.to_datetime(n["first_seen_ts"], errors="coerce", utc=True)
    n = n.dropna(subset=["_seen"])
    key = "match" if "match" in n.columns else None
    if key is None:
        n["match"] = n["home_team"].astype(str) + " vs " + n["away_team"].astype(str)
        key = "match"
    fx = n.groupby(key).agg(first_seen=("_seen", "min"),
                            minutes_to_kickoff=("minutes_to_kickoff", "max")).reset_index()

    W = pd.Timedelta(minutes=window_min)
    rows = []
    for _, r in fx.iterrows():
        s = cons[cons["match"] == r[key]]
        if s.empty:
            continue
        t0 = r["first_seen"]
        p_pre = _p_at(s, t0 - W)
        p_at = _p_at(s, t0)
        p_post = _p_at(s, t0 + W)
        if p_at is None or (p_pre is None and p_post is None):
            continue
        rows.append({
            "match": r[key], "first_seen": t0,
            "minutes_to_kickoff_at_news": r["minutes_to_kickoff"],
            "p_before": p_pre, "p_at_news": p_at, "p_after": p_post,
            # News window vs the fixture's OWN drift in an equal earlier window.
            "move_news_pp": None if p_post is None else (p_post - p_at) * 100.0,
            "move_control_pp": None if p_pre is None else (p_at - p_pre) * 100.0,
        })

    d = pd.DataFrame(rows)
    out = {"n": int(len(d)), "window_min": window_min}
    if d.empty:
        print("[news_impact] no fixture had a consensus price near its news moment")
        out["status"] = "NO_OVERLAP"
        return out

    both = d.dropna(subset=["move_news_pp", "move_control_pp"])
    out["n_paired"] = int(len(both))
    if len(both) >= 20:
        news_abs = both["move_news_pp"].abs()
        ctrl_abs = both["move_control_pp"].abs()
        diff = news_abs - ctrl_abs
        rng = np.random.default_rng(20260826)
        boot = np.array([diff.sample(len(diff), replace=True, random_state=int(rng.integers(1e9)))
                         .mean() for _ in range(2000)])
        lo, hi = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
        out.update({
            "mean_abs_move_news_pp": round(float(news_abs.mean()), 4),
            "mean_abs_move_control_pp": round(float(ctrl_abs.mean()), 4),
            "excess_pp": round(float(diff.mean()), 4),
            "excess_ci_lo": round(lo, 4), "excess_ci_hi": round(hi, 4),
            "verdict": ("NEWS MOVES THE PRICE BEYOND ORDINARY DRIFT" if lo > 0 else
                        "no excess movement over ordinary drift" if hi < 0 else "INCONCLUSIVE"),
        })
    else:
        out["verdict"] = "INSUFFICIENT_PAIRED_SAMPLE"

    if not quiet:
        print(f"[news_impact] window +/-{window_min:.0f}m; {out['n']} fixture(s), "
              f"{out.get('n_paired', 0)} with BOTH windows")
        if "excess_pp" in out:
            print(f"  mean |move| AFTER the news    : {out['mean_abs_move_news_pp']:.3f}pp")
            print(f"  mean |move| in control window : {out['mean_abs_move_control_pp']:.3f}pp")
            print(f"  excess {out['excess_pp']:+.3f}pp  95% CI "
                  f"[{out['excess_ci_lo']:+.3f}, {out['excess_ci_hi']:+.3f}]")
            print(f"  -> {out['verdict']}")
        else:
            print(f"  -> {out['verdict']}")
        print("  NOTE: first_seen_ts is OUR observation, not publication. This measures whether "
              "the price moved AFTER the news was available, never whether we knew first.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Did the price move after the team news?")
    ap.add_argument("--window", type=float, default=DEFAULT_WINDOW_MIN)
    a = ap.parse_args()
    run(window_min=a.window)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
