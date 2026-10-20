"""Per-league calibration of v9 O/U 2.5 (registry/league_calibration/registration_v1.json).

    python -m src.studies.league_calibration    # -> output/studies/league_calibration.json

Owner 2026-10-20: "it can't be global values... it must be per league". v9 trains one model per track and
its probabilities sit near one global level in every league, so a league that really scores more (or
less) than average shows up as a fake edge on every match. This tests the smallest fix: re-map v9's own
probability per league, fitted ONLY on earlier quarters, shrunk to the global map when a league has
little history. Research only - nothing changes in v9.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from config import pro_config as cfg
from src.studies import market_anchor as MA

OUT = cfg.BASE_DIR / "output" / "studies"
K = 300
FLOORS = {"VALUABLE": 0.03, "MARKSMAN": 0.08}


def _fit(lv, y, x0=(0.0, 1.0)):
    r = minimize(lambda b: MA._ll(MA._sig(b[0] + b[1] * lv), y).mean(), x0=np.array(x0), method="BFGS")
    return r.x


def arms(f: pd.DataFrame) -> pd.DataFrame:
    out = []
    for track, g in f.groupby("track"):
        g = g.sort_values("date").copy()
        g["lv"] = MA._logit(g["p_base"])
        g["p_global"], g["p_league"] = np.nan, np.nan
        for b in sorted(g["block"].unique()):
            past, cur = g["block"] < b, g["block"] == b
            if past.sum() < 300:
                g.loc[cur, "p_global"] = g.loc[cur, "p_base"]
                g.loc[cur, "p_league"] = g.loc[cur, "p_base"]
                continue
            bg = _fit(g.loc[past, "lv"].values, g.loc[past, "y"].values)
            g.loc[cur, "p_global"] = MA._sig(bg[0] + bg[1] * g.loc[cur, "lv"])
            for lg, idx in g[cur].groupby("league").groups.items():
                pl = past & (g["league"] == lg)
                n = int(pl.sum())
                if n >= 30:
                    bl = _fit(g.loc[pl, "lv"].values, g.loc[pl, "y"].values, x0=tuple(bg))
                    w = n / (n + K)
                    a, s = w * bl[0] + (1 - w) * bg[0], w * bl[1] + (1 - w) * bg[1]
                else:
                    a, s = bg
                g.loc[idx, "p_league"] = MA._sig(a + s * g.loc[idx, "lv"])
        out.append(g)
    return pd.concat(out, ignore_index=True)


def run() -> dict:
    reg = json.loads((cfg.BASE_DIR / "registry" / "league_calibration" / "registration_v1.json").read_text(encoding="utf-8"))
    e = pd.read_parquet(MA.EXP / "eval_rows.parquet",
                        columns=["date", "league", "home_team", "away_team", "over25", "track", "block", "p_base"])
    e["date"] = pd.to_datetime(e["date"]).dt.normalize()
    e = e.dropna(subset=["over25", "p_base"]).drop_duplicates(["track", "league", "date", "home_team", "away_team"])
    e["y"] = e["over25"].astype(float)
    g = arms(e)
    fd = MA._fd_prematch()
    res = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "decision_rule": reg["decision_rule"], "tracks": {}}
    for track, t in g.groupby("track"):
        y, day = t["y"].values, t["date"].values
        ll = {a: MA._ll(t[c].values, y) for a, c in (("V9", "p_base"), ("GLOBAL_CAL", "p_global"), ("PER_LEAGUE_CAL", "p_league"))}
        r = {"n": int(len(t)), "log_loss": {a: round(float(v.mean()), 5) for a, v in ll.items()}}
        for a, b in (("PER_LEAGUE_CAL", "V9"), ("GLOBAL_CAL", "V9"), ("PER_LEAGUE_CAL", "GLOBAL_CAL")):
            d = ll[a] - ll[b]
            r[f"dLL_{a}_minus_{b}"] = {"delta": round(float(d.mean()), 5), "ci90": MA._boot_delta(d, day)}
        lvl = t.groupby("league").agg(n=("y", "size"), real_over=("y", "mean"), v9=("p_base", "mean"),
                                      per_league_cal=("p_league", "mean"))
        r["level_by_league"] = lvl.round(3).reset_index().to_dict("records")
        pl, pv = r["dLL_PER_LEAGUE_CAL_minus_V9"], r["dLL_PER_LEAGUE_CAL_minus_GLOBAL_CAL"]
        r["verdict"] = ("PROPOSAL CANDIDATE" if pl["delta"] <= -0.001 and pl["ci90"][1] < 0 and pv["delta"] <= 0
                        else "NO PROPOSAL")
        if track == "standard":
            s = t.merge(fd, on=["league", "date", "home_team", "away_team"], how="inner")
            s["bet_over"], s["bet_under"] = s["pre_over"], s["pre_under"]
            s = s.dropna(subset=["bet_over", "bet_under"])
            r["bets_at_prematch_price"] = {arm: {fl: MA.bets(s, col, v) for fl, v in FLOORS.items()}
                                           for arm, col in (("V9", "p_base"), ("PER_LEAGUE_CAL", "p_league"))}
        res["tracks"][track] = r
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "league_calibration.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = run()
    for tr, x in r["tracks"].items():
        print(tr, x["n"], x["log_loss"], x["dLL_PER_LEAGUE_CAL_minus_V9"], x["dLL_GLOBAL_CAL_minus_V9"], x["verdict"])
        for row in x["level_by_league"]:
            print("   ", row)
        if "bets_at_prematch_price" in x:
            for arm, v in x["bets_at_prematch_price"].items():
                for fl, b in v.items():
                    print("   bets", arm, fl, {k: (q["n"], q["roi_pct"], q["roi_ci90_pct"]) for k, q in b.items()})
