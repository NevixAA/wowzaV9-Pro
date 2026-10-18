"""Best leagues - results separated by league, stored week by week (owner 2026-10-18).

    python -m src.studies.league_results     # -> output/studies/league_results_weekly.csv + LEAGUE_RESULTS.md

Every settled live tip (O/U 2.5 + side markets, SNIPER / MARKSMAN / VALUABLE, paper leagues out - the
same rows as src/studies/tip_ranker.load), per league, over two windows: the last 30 days and the season
(since SEASON_FROM). Per league: tips, hit rate, AVERAGE ODDS (a hit rate means nothing without the
price), flat-1u ROI with a 90% CI by bootstrap over match days, a SHRUNK ROI (pulled toward the all-league
average by SHRINK_N pseudo-tips, so 10 lucky tips cannot top the table) and the league's best market.

The table is ranked by shrunk ROI. Labels, fixed here:
  PROVEN        >= 100 tips and the ROI interval entirely above zero at a BONFERRONI-corrected level
                (one-sided 5% / number of leagues in the window) - 18 leagues tested at a plain 90% would
                make roughly two "proven" by luck alone (corrected 2026-10-18 before first use)
  PROMISING     >= 40 tips and shrunk ROI > 0
  LOSING        ROI interval entirely below zero at the same corrected level
  NOT_ENOUGH    < 40 tips
  NEUTRAL       otherwise (cannot be told apart from break-even yet)
One row per (ISO week, window, league); the current week refreshes each run, earlier weeks are kept.
Research only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies import tip_ranker as TR

OUT = cfg.OUTPUT_DIR / "studies"
CSV = OUT / "league_results_weekly.csv"
SEASON_FROM = "2026-08-01"
SHRINK_N = 50
MARKET_LABEL = {"OU25_OVER": "Over 2.5", "OU25_UNDER": "Under 2.5", "btts": "BTTS", "over15": "Over 1.5",
                "over35": "Over 3.5"}
RNG = np.random.default_rng(20261018)


def _ci(x: pd.DataFrame, q: float = 0.05) -> list:
    s = x.groupby("day")["ret"].agg(["sum", "size"])
    if len(s) < 5:
        return [None, None]
    idx = RNG.integers(0, len(s), size=(4000, len(s)))
    m = s["sum"].to_numpy()[idx].sum(1) / s["size"].to_numpy()[idx].sum(1)
    return [round(float(np.quantile(m, q)), 3), round(float(np.quantile(m, 1 - q)), 3)]


def table(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame()
    d = d.assign(ret=np.where(d["win"] == 1, d["odds"] - 1.0, -1.0))
    prior = float(d["ret"].mean())
    q_bonf = 0.05 / max(1, d["league"].nunique())                  # one-sided 5%, Bonferroni over leagues
    rows = []
    for lg, x in d.groupby("league"):
        n = len(x)
        roi = float(x["ret"].mean())
        ci = _ci(x)
        cb = _ci(x, q_bonf)
        shrunk = (n * roi + SHRINK_N * prior) / (n + SHRINK_N)
        bm = x.groupby("market").filter(lambda g: len(g) >= 15).groupby("market")["ret"].mean()
        best = f"{MARKET_LABEL.get(bm.idxmax(), bm.idxmax())} ({bm.max():+.0%})" if len(bm) else "—"
        if cb[0] is not None and cb[0] > 0 and n >= 100:
            label = "PROVEN"
        elif cb[1] is not None and cb[1] < 0:
            label = "LOSING"
        elif n < 40:
            label = "NOT_ENOUGH"
        elif shrunk > 0:
            label = "PROMISING"
        else:
            label = "NEUTRAL"
        rows.append({"league": lg, "tips": n, "hit_rate": round(float(x["win"].mean()), 3),
                     "avg_odds": round(float(x["odds"].mean()), 2), "roi": round(roi, 3), "roi_ci90": ci,
                     "shrunk_roi": round(shrunk, 3), "best_market": best, "label": label})
    return pd.DataFrame(rows).sort_values("shrunk_roi", ascending=False).reset_index(drop=True)


RATINGS_JSON = OUT / "league_ratings.json"


def rating(shrunk_roi: float, label: str) -> int:
    """League rating 1-10 (owner 2026-10-18: 10 = best league = max bet allowed, 1 = worst = min bet).

    Base: 5.5 + shrunk ROI / 4 points, i.e. every +4% of shrunk ROI is one step (shrunk -18% -> 1,
    +18% -> 10). Evidence gates on top, so a rating cannot outrun the data:
      PROVEN      at least 8          (only a proven league can reach 10)
      PROMISING   at most 9
      NOT_ENOUGH  at most 5           (no league earns a big stake on thin data)
      NEUTRAL     between 3 and 6
      LOSING      at most 2
    Consumers (v9 stake plan, wowza-exec) only scale stakes DOWN from today's maximum: 10 = today's max."""
    r = int(np.clip(np.floor(5.5 + shrunk_roi / 0.04 + 0.5), 1, 10))
    if label == "PROVEN":
        r = max(r, 8)
    elif label == "PROMISING":
        r = min(r, 9)
    elif label == "NOT_ENOUGH":
        r = min(r, 5)
    elif label == "NEUTRAL":
        r = int(np.clip(r, 3, 6))
    elif label == "LOSING":
        r = min(r, 2)
    return min(r, 9) if label != "PROVEN" else r


def write_ratings(cur: pd.DataFrame, now: pd.Timestamp) -> dict:
    s = cur[cur["window"] == "season"]
    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "window": f"season since {SEASON_FROM}",
           "method": "5.5 + shrunk ROI/4pts, gated by label (see src/studies/league_results.rating)",
           "ratings": {r["league"]: {"rating": int(r["rating"]), "label": r["label"], "tips": int(r["tips"]),
                                     "shrunk_roi": float(r["shrunk_roi"]), "roi": float(r["roi"]),
                                     "avg_odds": float(r["avg_odds"])}
                       for _, r in s.iterrows()}}
    RATINGS_JSON.write_text(__import__("json").dumps(out, indent=1), encoding="utf-8")
    return out


def build(now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = now or pd.Timestamp.now(tz="UTC")
    week = now.strftime("%G-W%V")
    d = TR.load()
    last30 = (now.tz_localize(None).normalize() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    parts = []
    for window, x in (("season", d[d["day"] >= SEASON_FROM]), ("last_30_days", d[d["day"] >= last30])):
        t = table(x)
        if len(t):
            t["rating"] = [rating(s, lab) for s, lab in zip(t["shrunk_roi"], t["label"])]
            parts.append(t.assign(window=window, rank=range(1, len(t) + 1)))
    cur = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    cur.insert(0, "week", week)
    cur["roi_ci90"] = cur["roi_ci90"].astype(str)
    cur["updated_at"] = now.strftime("%Y-%m-%d %H:%M UTC")
    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame(columns=cur.columns)
    return pd.concat([old[old["week"] != week], cur], ignore_index=True)


def to_md(hist: pd.DataFrame) -> str:
    week = hist["week"].max()
    cur = hist[hist["week"] == week]
    L = [f"# Best leagues — results by league ({week}, updated {cur['updated_at'].iloc[0]})", "",
         f"All settled live tips, paper leagues out. Ranked by shrunk ROI (pulled toward the all-league average "
         f"by {SHRINK_N} pseudo-tips). The 90% CI is shown for reading; PROVEN / LOSING need the interval clear "
         f"of zero at a Bonferroni-corrected level (one-sided 5% / number of leagues), and PROVEN >= 100 tips.", ""]
    for window, title in (("season", f"Season (since {SEASON_FROM})"), ("last_30_days", "Last 30 days")):
        t = cur[cur["window"] == window].sort_values("rank")
        L += [f"## {title}", "", "| # | League | Rating | Tips | Hit | Avg odds | ROI | 90% CI | Shrunk ROI | Best market | Label |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        L += [f"| {int(r['rank'])} | {r['league']} | {int(r['rating']) if pd.notna(r.get('rating')) else '—'}/10 | "
              f"{int(r['tips'])} | {r['hit_rate']:.0%} | {r['avg_odds']:.2f} | "
              f"{r['roi']:+.0%} | {r['roi_ci90']} | {r['shrunk_roi']:+.0%} | {r['best_market']} | {r['label']} |"
              for _, r in t.iterrows()]
        L.append("")
    return "\n".join(L) + "\n"


def main() -> int:
    now = pd.Timestamp.now(tz="UTC")
    hist = build(now)
    OUT.mkdir(parents=True, exist_ok=True)
    hist.to_csv(CSV, index=False)
    write_ratings(hist[hist["week"] == hist["week"].max()], now)
    (OUT / "LEAGUE_RESULTS.md").write_text(to_md(hist), encoding="utf-8")
    print(to_md(hist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
