"""League scout report: which leagues' markets look soft, on evidence.

    python -m src.scout.report

Writes output/scout/report.json and output/scout/REPORT.md. Read-only on the store.

FOR EACH LEAGUE x MARKET, on settled fixtures that had a pre-kickoff price:

  market skill   Brier of the de-vigged CLOSING price against the result, compared with the
                 league's own base rate. A sharp market sits well below the base rate; a market
                 barely better than the base rate is pricing little beyond the league average.
  model vs market
                 Brier of the frozen baseline model, and the RESIDUAL test: logistic regression
                 of the result on logit(market) and logit(model). A model coefficient reliably
                 above zero means the model knows something the closing price did not. This, not
                 standalone accuracy, is the test that matters (CLAUDE.md, v11 residual test).
  paper bets     where the frozen model beat Bet365's price at freeze time by more than 5 points:
                 flat-stake ROI at that price, and closing-line value against the reference close.

REFERENCE PRICE: Pinnacle where it quotes the market; otherwise the cross-book median. Pinnacle
does not offer BTTS through API-Football, so BTTS always uses the median.

NOTHING HERE IS A VERDICT UNTIL A LEAGUE HAS VOLUME. Status per league x market:
    COLLECTING  < 100 settled fixtures with a close
    EARLY       100 - 299
    READABLE    >= 300
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store
from src.scout import leagues as reg

OUT = cfg.OUTPUT_DIR / "scout"
EDGE_BAR = 0.05
STATUS = ((300, "READABLE"), (100, "EARLY"), (0, "COLLECTING"))
SIDE = {"ou15": ("over", "under"), "ou25": ("over", "under"), "ou35": ("over", "under"),
        "btts": ("yes", "no")}
MODEL_COL = {"ou15": "p_ou15_over", "ou25": "p_ou25_over", "ou35": "p_ou35_over",
             "btts": "p_btts_yes"}


def outcome(market: str, hg, ag):
    tg = hg + ag
    return {"ou15": tg > 1.5, "ou25": tg > 2.5, "ou35": tg > 3.5,
            "btts": (hg > 0) & (ag > 0)}[market].astype(float)


def fair_prob(q: pd.DataFrame) -> pd.DataFrame:
    """Proportional de-vig of each (fixture, market, book) pair -> P(first side)."""
    w = q.pivot_table(index=["fixture_id", "market", "bookmaker"], columns="selection",
                      values="odds", aggfunc="last").reset_index()
    rows = []
    for m, (a, b) in SIDE.items():
        s = w[w["market"] == m]
        if s.empty or a not in s or b not in s:
            continue
        ia, ib = 1 / s[a], 1 / s[b]
        rows.append(pd.DataFrame({"fixture_id": s["fixture_id"], "market": m,
                                  "bookmaker": s["bookmaker"], "p": ia / (ia + ib),
                                  "odds_first": s[a]}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def closing(odds: pd.DataFrame) -> pd.DataFrame:
    """Last pre-kickoff observation per (fixture, market, selection, book). The table is a
    change-log, so the last row IS the carried-forward price at kickoff."""
    o = odds[odds["minutes_to_kickoff"] > 0].sort_values("snapshot_ts")
    return o.drop_duplicates(["fixture_id", "market", "selection", "bookmaker"], keep="last")


def asof(odds: pd.DataFrame, when: pd.DataFrame) -> pd.DataFrame:
    """Price per key as it stood at each fixture's freeze time (carry-forward)."""
    o = odds.merge(when[["fixture_id", "frozen_ts"]], on="fixture_id")
    o = o[o["snapshot_ts"] <= o["frozen_ts"]].sort_values("snapshot_ts")
    return o.drop_duplicates(["fixture_id", "market", "selection", "bookmaker"], keep="last")


def residual(y, p_mkt, p_mod) -> dict:
    """Logistic regression y ~ a + b*logit(p_mkt) + c*logit(p_mod), Newton-Raphson.
    Returns c, its standard error and z. Positive c reliably above zero = model adds signal."""
    lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731
    cols = [np.ones(len(y)), lg(p_mkt), lg(p_mod)]
    # A market that quotes one price for every fixture is collinear with the intercept; it then
    # carries no information and is dropped rather than making the fit singular.
    if np.std(cols[1]) < 1e-9:
        cols.pop(1)
    X = np.column_stack(cols)
    beta = np.zeros(X.shape[1])
    if X.shape[1] == 3:
        beta[1] = 1.0
    for _ in range(50):
        mu = 1 / (1 + np.exp(-X @ beta))
        W = mu * (1 - mu)
        H = X.T @ (X * W[:, None])
        try:
            step = np.linalg.solve(H, X.T @ (y - mu))
        except np.linalg.LinAlgError:
            return {"coef": None, "se": None, "z": None}
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    try:
        se = float(np.sqrt(np.linalg.inv(H)[-1, -1]))
    except np.linalg.LinAlgError:
        return {"coef": None, "se": None, "z": None}
    return {"coef": round(float(beta[-1]), 4), "se": round(se, 4), "z": round(float(beta[-1]) / se, 2)}


def build() -> dict:
    res = store.read("scout_results")
    odds = store.read("scout_odds")
    mdl = store.read("scout_model")
    names = {x["id"]: (x["country"], x["name"], x["priority"]) for x in reg.load()}
    out = {"generated_at": cfg.utc_now_iso(), "status_rule": "COLLECTING <100, EARLY 100-299, "
           "READABLE >=300 settled fixtures with a pre-kickoff close",
           "totals": {"results": 0 if res.empty else int(res["fixture_id"].nunique()),
                      "odds_rows": int(len(odds)), "fixtures_priced": 0 if odds.empty else
                      int(odds["fixture_id"].nunique()),
                      "fixtures_frozen": 0 if mdl.empty else int(mdl["fixture_id"].nunique())},
           "cells": []}
    if res.empty or odds.empty:
        return out
    res = res.sort_values("ingested_at").drop_duplicates("fixture_id", keep="last")
    res = res.dropna(subset=["home_goals", "away_goals"])
    hist_rate = {}                                         # league base rates from history
    for (lid), g in res.groupby("league_id"):
        hg, ag = g["home_goals"].astype(float), g["away_goals"].astype(float)
        hist_rate[lid] = {m: float(outcome(m, hg, ag).mean()) for m in SIDE}

    close = fair_prob(closing(odds))
    settled = res[res["fixture_id"].isin(close["fixture_id"])]
    if mdl.empty:
        mdl = pd.DataFrame(columns=["fixture_id", "frozen_ts"])
    mdl = mdl.sort_values("frozen_ts").drop_duplicates("fixture_id", keep="first")

    for m in SIDE:
        c = close[close["market"] == m]
        ref = c[c["bookmaker"] == "pinnacle"].set_index("fixture_id")["p"]
        med = c[c["bookmaker"] == "median"].set_index("fixture_id")["p"]
        ref = ref.combine_first(med)
        s = settled.set_index("fixture_id")
        s = s[s.index.isin(ref.index)]
        if s.empty:
            continue
        s = s.assign(y=outcome(m, s["home_goals"].astype(float), s["away_goals"].astype(float)),
                     p_ref=ref.reindex(s.index))
        for lid, g in s.groupby("league_id"):
            n = len(g)
            base = hist_rate.get(lid, {}).get(m, float(g["y"].mean()))
            cell = {"league_id": int(lid), "country": names.get(lid, ("?",))[0],
                    "league": names.get(lid, ("", "?"))[1],
                    "priority": names.get(lid, ("", "", 9))[2], "market": m, "n": n,
                    "status": next(lab for lim, lab in STATUS if n >= lim),
                    "rate": round(float(g["y"].mean()), 4),
                    "brier_base_rate": round(float(((base - g["y"]) ** 2).mean()), 4),
                    "brier_market_close": round(float(((g["p_ref"] - g["y"]) ** 2).mean()), 4),
                    "reference": "pinnacle" if m != "btts" else "median"}
            cell["market_skill_vs_base"] = (round(1 - cell["brier_market_close"] / cell["brier_base_rate"], 4)
                                            if cell["brier_base_rate"] > 0 else None)
            gm = g.join(mdl.set_index("fixture_id")[[MODEL_COL[m]]], how="inner")
            if len(gm) >= 30:
                cell["n_model"] = len(gm)
                cell["brier_model"] = round(float(((gm[MODEL_COL[m]] - gm["y"]) ** 2).mean()), 4)
                cell["residual"] = residual(gm["y"].to_numpy(), gm["p_ref"].to_numpy(),
                                            gm[MODEL_COL[m]].to_numpy())
            # paper bets on Bet365 at freeze time, both sides
            if len(gm):
                bets = gm.join(raw_two_sided(odds, m, gm.index, mdl), how="inner")
                if len(bets):
                    pm = bets[MODEL_COL[m]]
                    take_first = (pm - 1 / bets["o_first"]) > EDGE_BAR
                    take_second = (((1 - pm) - 1 / bets["o_second"]) > EDGE_BAR) & ~take_first
                    ret = np.where(take_first, np.where(bets["y"] == 1, bets["o_first"] - 1, -1.0),
                                   np.where(take_second,
                                            np.where(bets["y"] == 0, bets["o_second"] - 1, -1.0),
                                            np.nan))
                    ret = pd.Series(ret).dropna()
                    if len(ret):
                        cell["paper_bets"] = int(len(ret))
                        cell["paper_roi"] = round(float(ret.mean()), 4)
                        # one-sidedness is the failure signature to watch for (v9's MLS: 100% UNDER)
                        cell["paper_first_side_share"] = round(float(take_first.sum() / len(ret)), 3)
            out["cells"].append(cell)
    out["cells"].sort(key=lambda r: (r["priority"], -r["n"]))
    return out


def raw_two_sided(odds, m, fixtures, mdl) -> pd.DataFrame:
    """Bet365's two prices at freeze time, as columns o_first / o_second."""
    o = asof(odds[(odds["market"] == m) & (odds["bookmaker"] == "bet365")
                  & odds["fixture_id"].isin(fixtures)], mdl)
    w = o.pivot_table(index="fixture_id", columns="selection", values="odds", aggfunc="last")
    a, b = SIDE[m]
    if a not in w or b not in w:
        return pd.DataFrame(columns=["o_first", "o_second"])
    return w.rename(columns={a: "o_first", b: "o_second"})[["o_first", "o_second"]].dropna()


def to_md(r: dict) -> str:
    t = r["totals"]
    lines = [f"# League scout — {r['generated_at'][:16]} UTC", "",
             f"Results stored: {t['results']:,} · fixtures priced: {t['fixtures_priced']:,} · "
             f"model frozen: {t['fixtures_frozen']:,}", "", r["status_rule"], ""]
    if not r["cells"]:
        lines.append("No settled fixtures with a captured close yet. The first ones settle within "
                     "days of collection starting; verdicts need weeks.")
        return "\n".join(lines)
    lines += ["| P | League | Market | n | Status | Market skill vs base rate | Model resid. z | Paper ROI (n) |",
              "|---|---|---|---|---|---|---|---|"]
    for c in r["cells"]:
        z = (c.get("residual") or {}).get("z")
        pr = f"{c['paper_roi']:+.1%} ({c['paper_bets']})" if "paper_roi" in c else "–"
        sk = "–" if c["market_skill_vs_base"] is None else f"{c['market_skill_vs_base']:+.3f}"
        lines.append(f"| {c['priority']} | {c['country']} {c['league']} | {c['market']} | {c['n']} | "
                     f"{c['status']} | {sk} | {'–' if z is None else z} | {pr} |")
    return "\n".join(lines)


def main() -> int:
    r = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (OUT / "REPORT.md").write_text(to_md(r), encoding="utf-8")
    print(f"[scout report] {len(r['cells'])} league x market cell(s); totals {r['totals']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
