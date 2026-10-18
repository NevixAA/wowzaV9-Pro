"""Tip ranker — which 5 of the day's tips should a person take? (owner brief 2026-10-18)

    python -m src.studies.tip_ranker       # -> output/studies/tip_ranker.json + TIP_RANKER.md

THE PROBLEM. Some days carry 60+ tips. Nobody bets 68 singles by hand; people take a few, and two users
picking 5 at random from the same list get 0/5 and 5/5. The ORDER of the list is the product.

THREE LISTS (owner's choice), each the top 5 of the day:
  BEST_BETS  highest expected profit among tips with P(win) >= HIT_FLOOR
  SAFEST     highest P(win)
  VALUE      highest expected profit
All three need an HONEST P(win) per tip. The raw model probability cannot be used - it is overconfident
by ~13.6 points (2026-09-10 audit). So P(win) is LEARNED from our own settled tips: a regularised
logistic regression of the result on logit(1/odds), logit(model probability) and the market (O/U 2.5
over / under, BTTS, O1.5, O3.5) and model track. Expected profit = P(win) x odds - 1.

WALK-FORWARD, never in-sample: for each match day the ranker is fitted only on tips settled on EARLIER
days, then ranks that day. Days are scored only once MIN_TRAIN tips exist before them.

BASELINES it must beat, scored on the same days:
  CURRENT       today's order: tier (SNIPER > MARKSMAN > VALUABLE), then edge
  RANDOM_5      what users effectively do now: expected result of 5 random tips from the day's list
  SHORTEST_ODDS the no-ML "safest": 5 lowest prices
Metrics per list: hits out of 5 per day, hit rate, flat-1u ROI, share of 0/5 days, share of 4+/5 days;
differences vs RANDOM_5 and CURRENT with 90% CIs by bootstrap over days. Only days with >= 10 tips
count - below that there is little to choose between.

This is retrospective and exploratory: it decides whether a ranker is worth shipping. The real test
is the forward log v9 will keep once lists go live (frozen at selection time, graded, per-list
scoreboard). Research only; v9 is not changed here.
"""
from __future__ import annotations

import json
from math import comb

import numpy as np
import pandas as pd

from config import pro_config as cfg

TIERS = ("SNIPER", "MARKSMAN", "VALUABLE")
TOP_K = 5
HIT_FLOOR = 0.45
MIN_DAY_TIPS = 10
MIN_TRAIN = 300
OUT = cfg.OUTPUT_DIR / "studies"
RNG = np.random.default_rng(20261018)


def _lg(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def load() -> pd.DataFrame:
    paper = set(getattr(cfg, "PAPER_LEAGUES", ()) or ())
    m = pd.read_csv(cfg.V9_LOCAL / "output" / "bets_ledger.csv", low_memory=False)
    m = m[m["source"].fillna("live").astype(str).eq("live")]
    m["market"] = "OU25_" + m["side"].astype(str).str.upper()
    s = pd.read_csv(cfg.V9_LOCAL / "output" / "side_bets_ledger.csv", low_memory=False)
    s["market"] = s["market"].astype(str).str.lower()
    d = pd.concat([m, s], ignore_index=True)
    d = d[d["signal_tier"].isin(TIERS) & d["result"].isin(["WIN", "LOSS"]) & ~d["league"].isin(paper)].copy()
    d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    d = d[d["odds"] > 1.01]
    d["implied"] = 1.0 / d["odds"]
    e = pd.to_numeric(d["edge_pct"], errors="coerce")
    e = np.where(e.abs().median() > 1.0, e / 100.0, e) if len(e) else e    # stored as % or as a fraction
    mp = pd.to_numeric(d.get("model_prob"), errors="coerce")
    d["model_p"] = mp.where(mp.notna(), d["implied"] + pd.Series(e, index=d.index)).clip(0.02, 0.98)
    d["edge"] = d["model_p"] - d["implied"]
    d["win"] = (d["result"] == "WIN").astype(int)
    d["day"] = d["match_date"].astype(str).str[:10]
    d["model_type"] = d["model_type"].fillna("unknown").astype(str)
    d["tier_rank"] = d["signal_tier"].map({t: i for i, t in enumerate(TIERS)})
    # one tip per fixture x market (first tip stands, as the ledgers' flip guard does)
    d = d.sort_values("generated_at", kind="mergesort").drop_duplicates(
        ["day", "home_team", "away_team", "market"], keep="first")
    return d.sort_values(["day", "generated_at"], kind="mergesort").reset_index(drop=True)


def design(d: pd.DataFrame, markets: list[str], tracks: list[str]) -> np.ndarray:
    cols = [_lg(d["implied"]), _lg(d["model_p"])]
    cols += [(d["market"] == m).astype(float).to_numpy() for m in markets[1:]]
    cols += [(d["model_type"] == t).astype(float).to_numpy() for t in tracks[1:]]
    return np.column_stack(cols)


def walk_forward(d: pd.DataFrame) -> pd.DataFrame:
    """P(win) for every tip from a model fitted only on earlier days."""
    from sklearn.linear_model import LogisticRegression
    markets, tracks = sorted(d["market"].unique()), sorted(d["model_type"].unique())
    d = d.copy()
    d["p_hat"] = np.nan
    for day in sorted(d["day"].unique()):
        tr = d["day"] < day
        if tr.sum() < MIN_TRAIN:
            continue
        lr = LogisticRegression(C=1.0, max_iter=2000).fit(design(d[tr], markets, tracks), d.loc[tr, "win"])
        te = d["day"] == day
        d.loc[te, "p_hat"] = lr.predict_proba(design(d[te], markets, tracks))[:, 1]
    d["ev"] = d["p_hat"] * d["odds"] - 1.0
    return d


def _pick(g: pd.DataFrame, how: str) -> pd.DataFrame:
    if how == "BEST_BETS":
        return g[g["p_hat"] >= HIT_FLOOR].nlargest(TOP_K, "ev")
    if how == "SAFEST":
        return g.nlargest(TOP_K, "p_hat")
    if how == "VALUE":
        return g.nlargest(TOP_K, "ev")
    if how == "CURRENT":
        return g.sort_values(["tier_rank", "edge"], ascending=[True, False]).head(TOP_K)
    if how == "SHORTEST_ODDS":
        return g.nsmallest(TOP_K, "odds")
    raise ValueError(how)


def _random_day(g: pd.DataFrame) -> dict:
    """Exact expectation of 5 random picks from the day (hypergeometric), no simulation noise."""
    n, w, k = len(g), int(g["win"].sum()), min(TOP_K, len(g))
    p0 = comb(n - w, k) / comb(n, k) if n - w >= k else 0.0
    p4 = sum(comb(w, j) * comb(n - w, k - j) for j in range(4, k + 1) if j <= w and k - j <= n - w) / comb(n, k)
    ret = np.where(g["win"] == 1, g["odds"] - 1, -1.0).mean()
    return {"hits": k * w / n, "n": k, "zero": p0, "four_plus": p4, "units": k * ret}


def score_days(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for day, g in d[d["p_hat"].notna()].groupby("day"):
        if len(g) < MIN_DAY_TIPS:
            continue
        r = {"day": day, "n_tips": len(g)}
        for how in ("BEST_BETS", "SAFEST", "VALUE", "CURRENT", "SHORTEST_ODDS"):
            p = _pick(g, how)
            u = np.where(p["win"] == 1, p["odds"] - 1, -1.0)
            r.update({f"{how}_n": len(p), f"{how}_hits": int(p["win"].sum()), f"{how}_units": float(u.sum()),
                      f"{how}_zero": float(len(p) > 0 and p["win"].sum() == 0),
                      f"{how}_four_plus": float(p["win"].sum() >= 4)})
        rr = _random_day(g)
        r.update({"RANDOM_5_n": rr["n"], "RANDOM_5_hits": rr["hits"], "RANDOM_5_units": rr["units"],
                  "RANDOM_5_zero": rr["zero"], "RANDOM_5_four_plus": rr["four_plus"]})
        rows.append(r)
    return pd.DataFrame(rows)


def _boot(x: np.ndarray, n: int = 4000) -> list:
    if len(x) < 5:
        return [None, None]
    idx = RNG.integers(0, len(x), size=(n, len(x)))
    m = x[idx].mean(1)
    return [round(float(np.quantile(m, 0.05)), 3), round(float(np.quantile(m, 0.95)), 3)]


def summarise(S: pd.DataFrame) -> dict:
    out = {}
    for how in ("BEST_BETS", "SAFEST", "VALUE", "CURRENT", "SHORTEST_ODDS", "RANDOM_5"):
        n = S[f"{how}_n"].sum()
        e = {"days": int(len(S)), "picks": float(n),
             "hit_rate": round(float(S[f"{how}_hits"].sum() / n), 3) if n else None,
             "roi": round(float(S[f"{how}_units"].sum() / n), 3) if n else None,
             "zero_days": round(float(S[f"{how}_zero"].mean()), 3),
             "four_plus_days": round(float(S[f"{how}_four_plus"].mean()), 3),
             "hits_per_day": round(float(S[f"{how}_hits"].mean()), 2)}
        if how not in ("RANDOM_5",):
            per_pick = lambda c: (S[f"{c}_hits"] / S[f"{c}_n"].replace(0, np.nan)).fillna(0).to_numpy()  # noqa: E731
            roi_pp = lambda c: (S[f"{c}_units"] / S[f"{c}_n"].replace(0, np.nan)).fillna(0).to_numpy()  # noqa: E731
            e["hit_vs_random_ci90"] = _boot(per_pick(how) - per_pick("RANDOM_5"))
            e["roi_vs_random_ci90"] = _boot(roi_pp(how) - roi_pp("RANDOM_5"))
            e["hit_vs_current_ci90"] = _boot(per_pick(how) - per_pick("CURRENT"))
            e["roi_vs_current_ci90"] = _boot(roi_pp(how) - roi_pp("CURRENT"))
        out[how] = e
    return out


def calibration(d: pd.DataFrame) -> dict:
    t = d[d["p_hat"].notna()]
    brier = lambda p: float(((p - t["win"]) ** 2).mean())  # noqa: E731
    return {"n": int(len(t)), "brier_ranker": round(brier(t["p_hat"]), 4),
            "brier_implied": round(brier(t["implied"]), 4), "brier_model": round(brier(t["model_p"]), 4),
            "mean_p_hat": round(float(t["p_hat"].mean()), 3), "mean_model_p": round(float(t["model_p"].mean()), 3),
            "realised": round(float(t["win"].mean()), 3)}


def build() -> dict:
    d = walk_forward(load())
    S = score_days(d)
    return {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "tips": int(len(d)), "days_scored": int(len(S)),
            "settings": {"top_k": TOP_K, "hit_floor": HIT_FLOOR, "min_day_tips": MIN_DAY_TIPS, "min_train": MIN_TRAIN},
            "calibration": calibration(d), "lists": summarise(S) if len(S) else {}}


def to_md(r: dict) -> str:
    c = r["calibration"]
    L = [f"# Tip ranker — which 5 should a person take? ({r['generated_at']})", "",
         f"{r['tips']:,} settled tips; {r['days_scored']} match days with >= {r['settings']['min_day_tips']} tips scored "
         f"walk-forward (ranker fitted on earlier days only).", "",
         f"Honest P(win): Brier ranker {c['brier_ranker']} · bookmaker price alone {c['brier_implied']} · raw model "
         f"{c['brier_model']} (lower is better). Mean P(win) {c['mean_p_hat']} vs raw model {c['mean_model_p']}; "
         f"realised {c['realised']}.", "",
         "| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for k, e in r["lists"].items():
        L.append(f"| {k} | {e['hit_rate']:.1%} | {e['roi']:+.1%} | {e['hits_per_day']} | {e['zero_days']:.0%} | "
                 f"{e['four_plus_days']:.0%} | {e.get('hit_vs_random_ci90', '—')} | {e.get('roi_vs_random_ci90', '—')} | "
                 f"{e.get('hit_vs_current_ci90', '—')} | {e.get('roi_vs_current_ci90', '—')} |")
    L += ["", "RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero "
              "means the list beat that baseline across days, not just on average."]
    return "\n".join(L) + "\n"


def main() -> int:
    r = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tip_ranker.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (OUT / "TIP_RANKER.md").write_text(to_md(r), encoding="utf-8")
    print(to_md(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
