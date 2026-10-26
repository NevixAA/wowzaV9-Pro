"""Feature-group ablation for the market-residual model logit(p) = a + b*logit(p_market) + f(features).

CONTROLLED OPTIMISATION
  * the model family and ridge strength are fixed in advance (logistic residual, lam = 0.1),
  * each group is scored by (a) ADD-ONE: market + this group, and (b) LEAVE-ONE-OUT from all groups,
    walk-forward over the four VALIDATION quarters (refit before each quarter),
  * a group is KEPT only if add-one improves validation log loss AND the gain has the same sign in at
    least 3 of the 4 validation quarters (season-to-season stability); otherwise REMOVED,
  * the kept set is then scored ONCE on the untouched holdout and logged as its own experiment.
Market movement is not available historically without using the closing price, which would be
post-entry information, so it is not tested here (forward capture only).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.studies.standard_repair import candidates as C
from src.studies.standard_repair.data import load, logit
from src.studies.standard_repair.evaluate import OUT, SPLITS, _blocks, eval_rows, ll, paired

LAM = 0.1
GROUPS = {
    "rolling_goals": ["home_scored_last5", "away_scored_last5", "home_conceded_last5", "away_conceded_last5",
                      "home_over25_last5", "away_over25_last5"],
    "attack_defence_strength": ["home_attack_str", "away_attack_str", "home_defense_str", "away_defense_str"],
    "season_home_away_strength": ["home_season_goals_h", "away_season_goals_a", "home_season_conceded_h",
                                  "away_season_conceded_a", "home_cs_rate_h", "away_cs_rate_a"],
    "home_advantage": ["home_advantage", "away_home_adv_factor"],
    "rest_congestion": ["home_rest_days", "away_rest_days"],
    "shots_shot_quality": ["combined_sot_ratio", "home_insidebox_last5", "away_insidebox_last5"],
    "xg": ["home_xg_last5", "away_xg_last5"],
    "corners_fouls": ["home_corners_pg_roll", "away_corners_pg_roll", "home_fouls_pg_roll", "away_fouls_pg_roll"],
    "half_time": ["home_ht_scored_last5", "away_ht_scored_last5", "home_ht_conceded_last5", "away_ht_conceded_last5",
                  "home_ht_attack_str", "away_ht_attack_str", "combined_ht_goals_avg", "home_ht_over05_rate",
                  "away_ht_over05_rate", "home_ht_over15_rate", "away_ht_over15_rate"],
    "league_scoring_env": ["league_avg_goals", "env_goals", "env_gap_goals", "env_rate", "env_mktres"],
    "poisson_vs_market": ["pois_gap", "lh_gap", "la_gap"],
    "market_dispersion": ["book_dispersion", "n_books_ou"],
    "odds_band": ["ob_1", "ob_2", "ob_3", "ob_4"],
    "interactions": ["ix_att_def_home", "ix_att_def_away", "ix_lm_env"],
    "v9_residual": ["v9_gap"],
}


def _prep(d: pd.DataFrame, market: str) -> pd.DataFrame:
    d = pd.concat([d, C.derived(d, market)], axis=1)
    d["env_rate"] = d[{"OU25": "env_over25", "BTTS": "env_btts", "OU15": "env_over15"}[market]]
    d["env_mktres"] = d[f"env_mktres_{market}"]
    pm = d[C.anchor_col(market)]
    for k, (lo, hi) in enumerate([(0, .45), (.45, .5), (.55, .6), (.6, 1.01)], start=1):
        d[f"ob_{k}"] = ((pm >= lo) & (pm < hi)).astype(float)
    d["ix_att_def_home"] = d["home_attack_str"] * d["away_defense_str"]
    d["ix_att_def_away"] = d["away_attack_str"] * d["home_defense_str"]
    d["ix_lm_env"] = d["lm"] * d["env_gap_goals"]
    return d


def _walk(d, market, cols, period, need_v9):
    y = f"y_{market}"
    out = pd.Series(np.nan, index=d.index)
    for b0, b1 in _blocks(*SPLITS[period]):
        te = d[(d["date"] >= b0) & (d["date"] < b1)]
        if te.empty:
            continue
        tr = d[(d["date"] < b0) & d[y].notna()]
        if need_v9:
            tr = tr.dropna(subset=["v9_gap"])
        if cols:
            p = C.Prep(tr, cols)
            out.loc[te.index] = C._anchored(tr, te, market, p(tr), p(te), LAM)
        else:
            out.loc[te.index] = C._anchored(tr, te, market, None, None, LAM)
    return out


def run(markets=("OU25", "BTTS", "OU15")) -> dict:
    d0 = load()
    d0["date"] = pd.to_datetime(d0["date"])
    res = {"lam": LAM, "rule": __doc__.split("CONTROLLED OPTIMISATION")[1].split("Market movement")[0].strip(), "markets": {}}
    for market in markets:
        d = _prep(d0, market)
        E = eval_rows(d, market)
        val = E["date"] <= SPLITS["validation"][1]
        V = E[val]
        yv, wk = V[f"y_{market}"].to_numpy(), V["week"].to_numpy()
        q = pd.PeriodIndex(V["date"], freq="Q").astype(str).to_numpy()
        base = _walk(d, market, [], "validation", False).loc[V.index]
        lb = ll(base, yv)
        allcols = [c for g in GROUPS.values() for c in g]
        full = _walk(d, market, allcols, "validation", True).loc[V.index]
        lf = ll(full, yv)
        G = {}
        for g, cols in GROUPS.items():
            nv = g == "v9_residual"
            add = ll(_walk(d, market, cols, "validation", nv).loc[V.index], yv) - lb
            loo = lf - ll(_walk(d, market, [c for c in allcols if c not in cols], "validation", True).loc[V.index], yv)
            per_q = pd.Series(add).groupby(q).mean()
            stable = int((per_q < 0).sum())
            keep = bool(add.mean() < 0 and stable >= 3)
            G[g] = {"add_one_dLL_vs_market": paired(add, wk), "leave_one_out_dLL": round(float(loo.mean()), 6),
                    "quarters_improving": f"{stable}/{len(per_q)}", "decision": "KEEP" if keep else "REMOVE"}
        kept = [c for g, r in G.items() if r["decision"] == "KEEP" for c in GROUPS[g]]
        need_v9 = "v9_gap" in kept
        H = E[E["date"] >= SPLITS["holdout"][0]]
        yh = H[f"y_{market}"].to_numpy()
        ph = _walk(d, market, kept, "holdout", need_v9).loc[H.index]
        pb = _walk(d, market, [], "holdout", False).loc[H.index]
        res["markets"][market] = {"groups": G, "kept_groups": [g for g, r in G.items() if r["decision"] == "KEEP"],
                                  "all_groups_validation_dLL": round(float((lf - lb).mean()), 6),
                                  "kept_set_holdout_dLL_vs_market_cal": paired(ll(ph, yh) - ll(pb, yh), H["week"].to_numpy()),
                                  "n_holdout": int(len(H))}
        print(market, res["markets"][market]["kept_groups"], res["markets"][market]["kept_set_holdout_dLL_vs_market_cal"], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ablation.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    merge_into_results(res)
    return res


def merge_into_results(ab: dict) -> dict:
    """The ablation-selected model is one more validation-selected candidate per market, so it joins the
    multiplicity family: BH is recomputed over all model arms x markets PLUS these, and every arm's
    holdout q / beats_market is restated on that (larger, stricter) family."""
    from src.studies.standard_repair.evaluate import RULE, bh
    p = OUT / "results.json"
    res = json.loads(p.read_text(encoding="utf-8"))
    pv = {}
    for m, M in res["markets"].items():
        for a, r in M["arms"].items():
            if not a.startswith("MARKET") and a != M["market_baseline"]:
                pv[(m, a)] = r["holdout"]["dLL_vs_market"]["p_one_sided"]
    for m, A in ab["markets"].items():
        pv[(m, "ABLATION_SELECTED")] = A["kept_set_holdout_dLL_vs_market_cal"]["p_one_sided"]
    q = bh(pv)
    res["decision_rule"]["family"] = "all model arms x markets + ablation-selected model per market"
    res["ablation"] = {}
    for (m, a), qq in q.items():
        if a == "ABLATION_SELECTED":
            A = ab["markets"][m]
            d = A["kept_set_holdout_dLL_vs_market_cal"]
            d["bh_q"] = qq
            res["ablation"][m] = {"kept_groups": A["kept_groups"], "holdout_dLL_vs_market": d,
                                  "beats_market": bool(d["delta"] < 0 and d["ci95"][1] < 0 and qq <= RULE["bh_q"])}
        else:
            h = res["markets"][m]["arms"][a]["holdout"]
            h["dLL_vs_market"]["bh_q"] = qq
            ci = h["dLL_vs_market"]["ci95"]
            h["beats_market"] = bool(h["dLL_vs_market"]["delta"] < 0 and ci and ci[1] < 0 and qq <= RULE["bh_q"])
    for m, v in res["verdict"].items():
        v["beats_market"] = [a for a, r in res["markets"][m]["arms"].items() if r.get("holdout", {}).get("beats_market")]
        if res["ablation"].get(m, {}).get("beats_market"):
            v["beats_market"].append("ABLATION_SELECTED")
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    import pandas as pd
    c = pd.read_csv(OUT / "results.csv")
    for (m, a), qq in q.items():
        if a != "ABLATION_SELECTED":
            k = (c["market"] == m) & (c["arm"] == a) & (c["period"] == "holdout")
            c.loc[k, "bh_q"] = qq
            c.loc[k, "beats_market"] = res["markets"][m]["arms"][a]["holdout"]["beats_market"]
    extra = [{"market": m, "arm": "ABLATION_SELECTED", "period": "holdout", "baseline": res["markets"][m]["market_baseline"],
              "hp": json.dumps({"lam": LAM, "groups": A["kept_groups"]}), "dLL": A["holdout_dLL_vs_market"]["delta"],
              "dLL_ci95_lo": A["holdout_dLL_vs_market"]["ci95"][0], "dLL_ci95_hi": A["holdout_dLL_vs_market"]["ci95"][1],
              "p_one_sided": A["holdout_dLL_vs_market"]["p_one_sided"], "bh_q": A["holdout_dLL_vs_market"]["bh_q"],
              "beats_market": A["beats_market"]} for m, A in res["ablation"].items()]
    c = pd.concat([c[c["arm"] != "ABLATION_SELECTED"], pd.DataFrame(extra)], ignore_index=True)
    c.to_csv(OUT / "results.csv", index=False)
    return res


if __name__ == "__main__":
    run()
