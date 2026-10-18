"""Weekly Top-picks table - how each list is doing, stored week by week (owner 2026-10-18).

    python -m src.studies.top_picks_weekly     # -> output/studies/top_picks_weekly.csv + TOP_PICKS_WEEKLY.md

Two kinds of numbers per list, kept side by side because they answer different questions:
  LIVE      the picks users were actually shown: v9 output/top_picks_log.csv (frozen each morning), graded
            from the ledgers. The truth; starts with the first frozen day.
  BACKTEST  the walk-forward test of src/studies/tip_ranker.py re-run on all history, newest days
            included - does the advantage over random 5 / the current order hold as data grows?
One row per (ISO week, list, kind). The CURRENT week's rows are refreshed on every run; earlier weeks
are never rewritten, so the file is a weekly history. Lists: BEST_BETS, SAFEST (live = 5 shortest
prices; backtest row = SHORTEST_ODDS, the same rule), VALUE, plus RANDOM_5 and CURRENT as the
baselines in the backtest. Research only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies import tip_ranker as TR

OUT = cfg.OUTPUT_DIR / "studies"
CSV = OUT / "top_picks_weekly.csv"
LIVE_LISTS = ("BEST_BETS", "SAFEST", "VALUE")
BACKTEST_MAP = {"BEST_BETS": "BEST_BETS", "SAFEST": "SHORTEST_ODDS", "VALUE": "VALUE",
                "RANDOM_5": "RANDOM_5", "CURRENT": "CURRENT"}
LABEL = {"BEST_BETS": "Best bets", "SAFEST": "Safest", "VALUE": "Value", "RANDOM_5": "Random 5",
         "CURRENT": "Current order"}


def live_rows(week: str) -> list[dict]:
    p = cfg.V9_LOCAL / "output" / "top_picks_log.csv"
    if not p.exists():
        return []
    f = pd.read_csv(p)
    f["day"] = f["day"].astype(str)
    res = TR.load()[["day", "home_team", "away_team", "market", "win"]]
    g = f.merge(res, on=["day", "home_team", "away_team", "market"], how="inner")      # settled picks only
    if g.empty:
        return []
    g["ret"] = np.where(g["win"] == 1, g["odds"] - 1.0, -1.0)
    g["week"] = pd.to_datetime(g["day"]).dt.strftime("%G-W%V")
    rows = []
    for name in LIVE_LISTS:
        for scope, x in (("this_week", g[(g["list"] == name) & (g["week"] == week)]), ("to_date", g[g["list"] == name])):
            if x.empty:
                continue
            per_day = x.groupby("day")["win"].sum()
            rows.append({"list": name, "kind": f"live_{scope}", "days": int(per_day.size), "picks": int(len(x)),
                         "hit_rate": round(float(x["win"].mean()), 3), "roi": round(float(x["ret"].mean()), 3),
                         "avg_odds": round(float(x["odds"].mean()), 2),
                         "zero_days": round(float((per_day == 0).mean()), 3)})
    return rows


def backtest_rows() -> list[dict]:
    r = TR.build()
    rows = []
    for name, src in BACKTEST_MAP.items():
        e = r["lists"].get(src)
        if not e:
            continue
        rows.append({"list": name, "kind": "backtest", "days": e["days"], "picks": e["picks"],
                     "hit_rate": e["hit_rate"], "roi": e["roi"], "zero_days": e["zero_days"],
                     "avg_odds": e.get("avg_odds")})
    return rows


def build(now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = now or pd.Timestamp.now(tz="UTC")
    week = now.strftime("%G-W%V")
    cur = pd.DataFrame(live_rows(week) + backtest_rows())
    cur.insert(0, "week", week)
    cur["updated_at"] = now.strftime("%Y-%m-%d %H:%M UTC")
    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame(columns=cur.columns)
    hist = pd.concat([old[old["week"] != week], cur], ignore_index=True)       # earlier weeks never rewritten
    return hist.sort_values(["week", "kind", "list"]).reset_index(drop=True)


def _fmt(r) -> str:
    odds = f", avg odds {r['avg_odds']:.2f}" if pd.notna(r.get("avg_odds")) else ""
    return (f"{r['hit_rate']:.0%} hit{odds}, {r['roi']:+.0%} ROI, {r['zero_days']:.0%} 0/5 days "
            f"({int(r['days'])} days, {int(r['picks'])} picks)")


def to_md(hist: pd.DataFrame) -> str:
    week = hist["week"].max()
    cur = hist[hist["week"] == week]
    L = [f"# Top picks — weekly table ({week}, updated {cur['updated_at'].iloc[0]})", "",
         "| List | How it's ranked | Live, this week | Live, to date | Backtest (all days with >= 10 tips) |",
         "|---|---|---|---|---|"]
    how = {"BEST_BETS": "most expected profit, at least a 45% chance", "SAFEST": "the 5 shortest prices",
           "VALUE": "most expected profit", "RANDOM_5": "5 random tips (what users did before)",
           "CURRENT": "tier, then edge (the old order)"}
    for name in ("BEST_BETS", "SAFEST", "VALUE", "RANDOM_5", "CURRENT"):
        cell = {}
        for kind in ("live_this_week", "live_to_date", "backtest"):
            x = cur[(cur["list"] == name) & (cur["kind"] == kind)]
            cell[kind] = _fmt(x.iloc[0]) if len(x) else "—"
        L.append(f"| {LABEL[name]} | {how[name]} | {cell['live_this_week']} | {cell['live_to_date']} | {cell['backtest']} |")
    L += ["", "## Week by week (live picks)", "", "| Week | List | Hit | Avg odds | ROI | 0/5 days | Picks |", "|---|---|---|---|---|---|---|"]
    lw = hist[hist["kind"] == "live_this_week"].sort_values(["week", "list"], ascending=[False, True])
    L += [f"| {r.week} | {LABEL[r.list]} | {r.hit_rate:.0%} | {r.avg_odds:.2f} | {r.roi:+.0%} | {r.zero_days:.0%} | {int(r.picks)} |"
          for r in lw.itertuples()] or ["| — | live record starts with the first frozen day | | | | |"]
    L += ["", "Live = the lists users were shown (frozen each morning), graded from results. Backtest = the "
              "walk-forward test re-run on all history; it moves as new days arrive."]
    return "\n".join(L) + "\n"


def main() -> int:
    hist = build()
    OUT.mkdir(parents=True, exist_ok=True)
    hist.to_csv(CSV, index=False)
    (OUT / "TOP_PICKS_WEEKLY.md").write_text(to_md(hist), encoding="utf-8")
    print(to_md(hist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
