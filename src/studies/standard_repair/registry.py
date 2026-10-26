"""EXPERIMENT REGISTRY and per-track LEARNING JOURNEY — write-once, append-only.

registry/standard_repair/experiments.json
    One entry per experiment ID. An ID, once written, is NEVER modified: a material change to a
    hypothesis, feature set, model or window is a NEW ID (…-V2). Failed experiments stay, with what was
    tried, why it failed, what changed in our understanding and the next hypothesis.
registry/standard_repair/journey.jsonl
    Append-only history per track (V1, V2, ...). Lines are never rewritten.
registry/standard_repair/registration_v1.json
    Written ONLY if a candidate beats the market on holdout under the frozen rule (evaluate.RULE).
"""
from __future__ import annotations

import json

import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair import candidates as C
from src.studies.standard_repair.evaluate import RULE, SPLITS

REG = cfg.REGISTRY_DIR / "standard_repair"
FEATURES = {
    "MKT_SIMPLE": "SIMPLE", "MKT_NO_NOISY": "NO_NOISY", "MKT_FULL": "FULL", "MKT_SIMPLE_RECENCY": "SIMPLE",
    "MKT_POISSON": "pois_gap, lh_gap, la_gap", "MKT_ENV": "env_goals, env_gap_goals, env_rate, env_mktres + league",
    "MKT_KITCHEN": "SIMPLE + Poisson + env + v9_gap", "MKT_V9_RESID": "v9_gap", "MKT_V9_BANDS": "v9_gap bands",
    "MKT_LEAGUE": "league dummies", "MKT_LEAGUE_SLOPE": "league dummies x logit(market)",
    "LGBM_RESID_SIMPLE": "SIMPLE + Poisson + env", "LGBM_RESID_FULL": "FULL + Poisson + env",
    "HGB_ANCHOR_CAL": "SIMPLE + Poisson + env + logit(market)", "HGB_ABS_CAL": "FULL (no market)",
    "LR_ABS_SIMPLE": "SIMPLE (no market)", "V9": "v9 champion 42 columns", "V9_CAL": "v9 champion 42 columns"}


def _decision(v: dict, h: dict) -> tuple[str, str, str]:
    dv, dh = v["dLL_vs_market"]["delta"], h["dLL_vs_market"]["delta"]
    ci = h["dLL_vs_market"]["ci95"]
    if h.get("beats_market"):
        return "BEATS_MARKET_HOLDOUT", "passes the frozen rule", "register a forward first-sight test"
    if ci and ci[0] > 0:
        return ("REJECTED_BELOW_MARKET", f"holdout dLL {dh} with CI95 {ci} entirely above zero: worse than the price",
                "drop absolute-probability scoring; only market-anchored residuals are worth testing")
    if dv < 0 and dh < 0:
        return ("NO_INCREMENTAL_SIGNAL_CONSISTENT_SIGN",
                f"negative on validation ({dv}) and holdout ({dh}) but CI95 {ci} includes zero and BH q {h['dLL_vs_market'].get('bh_q')}",
                "re-test unchanged on the next untouched quarter (no re-tuning) to see if the small gain persists")
    if dv < 0 <= dh or dh < 0 <= dv:
        return ("REJECTED_INCONSISTENT", f"sign flips between validation ({dv}) and holdout ({dh})",
                "treat as noise / regime-dependent; do not pursue without a new mechanism")
    return ("REJECTED_NO_INCREMENTAL_SIGNAL", f"holdout dLL {dh}, CI95 {ci}", "drop")


def experiments(res: dict, sc: dict) -> dict:
    REG.mkdir(parents=True, exist_ok=True)
    p = REG / "experiments.json"
    reg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"note": __doc__.strip().splitlines()[0],
                                                                         "experiments": {}}
    E = reg["experiments"]
    now = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    for market, M in res["markets"].items():
        for arm, r in M["arms"].items():
            if arm.startswith("MARKET"):
                continue
            eid = f"STD-REPAIR-POOLED-{market}-{arm}-V1"
            if eid in E:
                continue                                    # write-once
            dec, why, nxt = _decision(r["validation"], r["holdout"])
            E[eid] = {"created": now, "scope": "all Standard leagues pooled (never with New Format)", "market": market,
                      "hypothesis": f"{C.ARMS[arm][3]} adds information after conditioning on the de-vigged market",
                      "features": FEATURES.get(arm), "model": arm, "hyperparameters_selected_on_validation": M["selected_hp"].get(arm),
                      "windows": SPLITS, "primary_metric": "paired log loss vs " + M["market_baseline"],
                      "results": {"validation": r["validation"].get("dLL_vs_market"), "holdout": r["holdout"].get("dLL_vs_market"),
                                  "holdout_cal_slope": r["holdout"].get("cal_slope")},
                      "decision": dec, "reason": why, "what_changed_in_understanding": _learning(arm, dec),
                      "next_hypothesis": nxt}
    for market, A in (res.get("ablation") or {}).items():
        eid = f"STD-REPAIR-POOLED-{market}-ABLATION_SELECTED-V1"
        if eid in E:
            continue
        d = A["holdout_dLL_vs_market"]
        E[eid] = {"created": now, "scope": "all Standard leagues pooled", "market": market,
                  "hypothesis": "the feature groups that improve validation log loss stably (>=3 of 4 quarters) add information after the market",
                  "features": A["kept_groups"], "model": "market-anchored logistic residual, lam 0.1", "windows": SPLITS,
                  "primary_metric": "paired log loss vs " + res["markets"][market]["market_baseline"],
                  "results": {"holdout": d}, "decision": "BEATS_MARKET_HOLDOUT" if A["beats_market"] else
                  ("NO_INCREMENTAL_SIGNAL_AFTER_MULTIPLICITY" if d["delta"] < 0 else "REJECTED_NO_INCREMENTAL_SIGNAL"),
                  "reason": f"holdout dLL {d['delta']} CI95 {d['ci95']} BH q {d.get('bh_q')} (rule q<=0.05)",
                  "what_changed_in_understanding": "only the league scoring environment (and, for OU15/BTTS, team goal form) "
                  "survives as a stable residual input; shots, corners, xG, HT, rest, dispersion and v9's residual are noise after the price"
                  + ("; NOTE the BTTS/OU15 baseline is a Poisson inversion of 1X2 + O/U 2.5, not a quoted price, so a gain here may be "
                     "a gain over the proxy rather than over the real BTTS/OU15 market" if market != "OU25" else ""),
                  "next_hypothesis": "score this exact frozen model on 2026-Q4 (untouched) and on real first-sight quotes; "
                                     "no re-selection"}
    for t in sc["tracks"]:
        eid = t["experiment_id"]
        if eid in E or not t["historical"]:
            continue
        h = t["historical"]["challenger_holdout"]
        E[eid] = {"created": now, "scope": f"{t['league']} {t['market']} {t['side']}",
                  "hypothesis": f"pooled validation-selected challenger {t['current_challenger']} improves on the market on this track",
                  "features": FEATURES.get(t["current_challenger"]), "model": t["current_challenger"], "windows": SPLITS,
                  "primary_metric": "paired log loss vs market on rows the model leans to this side",
                  "results": {"challenger_holdout": h.get("dLL_vs_market"), "v9_holdout": t["historical"]["v9_holdout"].get("dLL_vs_market"),
                              "n": h.get("n")},
                  "decision": "CONTINUE_RESEARCH" if any(d["code"] == "SIDE_SPECIFIC_EDGE" for d in t["diagnosis"]) else "NO_EDGE_YET",
                  "reason": "; ".join(f"{d['code']}: {d['evidence']}" for d in t["diagnosis"]),
                  "what_changed_in_understanding": "per-track samples are too small for a decisive verdict; pooled result governs",
                  "next_hypothesis": t["next_experiment"]}
    p.write_text(json.dumps(reg, indent=1, default=str), encoding="utf-8")
    return reg


def _learning(arm: str, dec: str) -> str:
    if arm.startswith("V9"):
        return "v9's absolute probabilities are compressed (sd ~0.02) and lose to the price; recalibration cannot add information the model does not have"
    if arm in ("HGB_ABS_CAL", "LR_ABS_SIMPLE"):
        return "absolute-probability models (no market) lose to the price regardless of learner: the information is in the price"
    if "V9" in arm:
        return "v9's disagreement with the market carries ~zero weight once the market is known"
    if dec.startswith("NO_INCREMENTAL"):
        return "team-goal / environment features move log loss by <0.1% at best; signal, if any, is below what 4k holdout rows can confirm"
    return "no reliable incremental information over the market on holdout"


def journey(sc: dict, res: dict) -> int:
    """Append one V1 line per track (and per pooled market) if not already present."""
    REG.mkdir(parents=True, exist_ok=True)
    p = REG / "journey.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                j = json.loads(line)
                seen.add((j["track_id"], j["version"], j["event"]))
    now = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    new = []
    for t in sc["tracks"]:
        k = (t["track_id"], "V1", "BENCHMARK_2026_10")
        if k in seen or not t["historical"]:
            continue
        new.append({"track_id": t["track_id"], "version": "V1", "event": "BENCHMARK_2026_10", "date": now,
                    "status": t["research_status"], "diagnosis": [d["code"] for d in t["diagnosis"]],
                    "challenger": t["current_challenger"],
                    "challenger_holdout_dLL": (t["historical"]["challenger_holdout"].get("dLL_vs_market") or {}).get("delta"),
                    "v9_holdout_dLL": (t["historical"]["v9_holdout"].get("dLL_vs_market") or {}).get("delta"),
                    "summary": "first chronological benchmark; no arm beats the market under the frozen rule",
                    "next": t["next_experiment"]})
    if new:
        with p.open("a", encoding="utf-8") as fh:
            for j in new:
                fh.write(json.dumps(j, default=str) + "\n")
    return len(new)


def maybe_register(res: dict) -> dict:
    """Write registration_v1.json only for arms that beat the market on holdout. Never overwrites."""
    winners = {m: v["beats_market"] for m, v in res["verdict"].items() if v["beats_market"]}
    p = REG / "registration_v1.json"
    if not winners:
        return {"registered": False, "reason": "no arm beats the de-vigged market on holdout under the frozen rule "
                                               f"({res.get('decision_rule', RULE)}); nothing registered"}
    if p.exists():
        return {"registered": True, "reason": "registration_v1.json already exists; frozen, not modified"}
    reg = {"id": "STD-REPAIR-FORWARD-V1", "frozen_at": pd.Timestamp.now(tz="UTC").isoformat(),
           "forward_start_utc": "2026-10-27T00:00:00Z", "arms": winners,
           "primary_metric": "paired log loss vs de-vigged market consensus on first-sight rows (forward.py)",
           "min_n": 300, "min_matchday_weeks": 12, "multiplicity": "Benjamini-Hochberg across registered arms, q<=0.05",
           "outcomes": ["SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE"], "never": "CONFIRMED",
           "modification_policy": "frozen; any change is a new registration id"}
    p.write_text(json.dumps(reg, indent=1), encoding="utf-8")
    return {"registered": True, "arms": winners}
