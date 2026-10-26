"""Weekly loop and monthly deep review for the Standard repair programme. Never changes production.

weekly()   forward first-sight rows -> scorecard -> output/standard_repair_weekly.json + WEEKLY.md,
           and one compact line per track appended to output/standard_repair/scorecard_history.jsonl
monthly()  output/standard_repair/monthly_YYYY-MM.json + .md: improved / degraded tracks, models beating
           the market, selection rules with positive CLV, tracks ready for forward promotion, experiments
           to kill.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair import forward as F
from src.studies.standard_repair import scorecard as S
from src.studies.standard_repair.evaluate import ll, paired

OUT = cfg.OUTPUT_DIR / "standard_repair"
WEEKLY = cfg.OUTPUT_DIR / "standard_repair_weekly.json"
HIST = OUT / "scorecard_history.jsonl"


def _now():
    return pd.Timestamp.now(tz="UTC")


def _fwd_market_summary(fwd: pd.DataFrame) -> dict:
    out = {}
    if fwd is None or fwd.empty:
        return out
    for m, g in fwd.groupby("market"):
        s = g.dropna(subset=["p_market", "y"])
        r = {"n_first_sight": int(len(g)), "price_coverage": round(float(g["p_market"].notna().mean()), 3),
             "n_settled_priced": int(len(s)), "gameweeks": int(s["week"].nunique()) if len(s) else 0}
        if len(s) >= 20:
            r["served_v9_dLL_vs_market"] = paired(ll(s["p_model"], s["y"]) - ll(s["p_market"], s["y"]), s["week"].to_numpy())
        # CLV of the side the served model leans to, at first-sight median odds vs the closing consensus
        lean_first = g["p_model"] > g["p_market"]
        odds = np.where(lean_first, g["odds_first"], g["odds_other"])
        close = np.where(lean_first, g["close_first"], g["close_other"])
        clv = odds / close - 1
        ok = np.isfinite(clv)
        r["clv_lean_side"] = {"coverage": round(float(ok.mean()), 3), "mean": round(float(np.nanmean(clv)), 4) if ok.any() else None}
        out[m] = r
    return out


def weekly() -> dict:
    prev = json.loads(WEEKLY.read_text(encoding="utf-8")) if WEEKLY.exists() else {}
    prev_sc = json.loads((OUT / "scorecard.json").read_text(encoding="utf-8")) if (OUT / "scorecard.json").exists() else {}
    prev_fwd = F.load()
    try:
        fwd = F.build()
        fwd_err = None
    except Exception as e:                                                   # noqa: BLE001 - tolerant loop
        fwd, fwd_err = prev_fwd, f"{type(e).__name__}: {e}"
    since = prev.get("generated_at")
    res = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    sc = S.build(res=res, fwd=fwd)
    new_obs = int((pd.to_datetime(fwd["first_seen_at"], utc=True) > pd.Timestamp(since)).sum()) \
        if since and not fwd.empty else int(len(fwd))
    settled_now = int(fwd["y"].notna().sum()) if not fwd.empty else 0
    settled_prev = int(prev_fwd["y"].notna().sum()) if not prev_fwd.empty else 0
    old = {t["track_id"]: t for t in prev_sc.get("tracks", [])}
    changes = []
    for t in sc["tracks"]:
        a = [d["code"] for d in old.get(t["track_id"], {}).get("diagnosis", [])]
        b = [d["code"] for d in t["diagnosis"]]
        if old and a != b:
            changes.append({"track_id": t["track_id"], "from": a, "to": b})
        if old and old.get(t["track_id"], {}).get("research_status") not in (None, t["research_status"]):
            changes.append({"track_id": t["track_id"], "status_from": old[t["track_id"]]["research_status"],
                            "status_to": t["research_status"]})
    P = S.rank_panel()
    rank = {}
    if not P.empty and "settle_status" in P:
        s = P[P["settle_status"].astype(str) == "SETTLED"]
        for (m, sd), g in s.groupby(["market", "side"]):
            rank[f"{m} {sd}"] = {"n_settled": int(len(g)), "hit_rate": round(float(pd.to_numeric(g["won"], errors="coerce").mean()), 3),
                                 "flat_roi": round(float(pd.to_numeric(g["flat_pnl"], errors="coerce").mean()), 3),
                                 "clv_coverage": round(float(pd.to_numeric(g["clv_pct"], errors="coerce").notna().mean()), 3)}
    w = {"generated_at": _now().strftime("%Y-%m-%d %H:%M UTC"), "previous_run": since,
         "production_change": "NONE - research only; nothing here is read by v9",
         "new_observations_first_sight": new_obs, "new_settlements": settled_now - settled_prev,
         "forward_error": fwd_err, "model_vs_market_forward": _fwd_market_summary(fwd),
         "best_challenger_by_market": {m: {"validation_selected": S.challenger_for(res, m),
                                           "best_on_holdout": v["best_holdout_arm"], "beats_market": v["beats_market"]}
                                       for m, v in res["verdict"].items()},
         "rank_panel": rank, "state_changes": changes,
         "new_evidence": [c for c in changes if "to" in c and any(x in c["to"] for x in ("SIDE_SPECIFIC_EDGE", "RANKING_PROMISING"))],
         "next_actions": _next_actions(sc, res)}
    WEEKLY.write_text(json.dumps(w, indent=1, default=str), encoding="utf-8")
    (OUT / "WEEKLY.md").write_text(_weekly_md(w, sc), encoding="utf-8")
    with HIST.open("a", encoding="utf-8") as fh:
        for t in sc["tracks"]:
            fh.write(json.dumps({"date": w["generated_at"][:10], "track_id": t["track_id"], "status": t["research_status"],
                                 "diagnosis": [d["code"] for d in t["diagnosis"]],
                                 "forward_n_settled": t["forward"].get("n_settled"),
                                 "forward_dLL": (t["forward"].get("dLL_vs_market") or {}).get("delta")}) + "\n")
    return w


def _next_actions(sc, res) -> list[str]:
    acts = []
    if not any(v["beats_market"] for v in res["verdict"].values()):
        acts.append("No forward registration: keep collecting first-sight quotes; re-run the benchmark when 2026-Q4 completes "
                    "and score the frozen validation-selected arms on it as a fresh holdout (no re-tuning).")
    n_price = sum(1 for t in sc["tracks"] if any(d["code"] == "PRICE_QUALITY_PROBLEM" for d in t["diagnosis"]))
    if n_price:
        acts.append(f"{n_price} tracks lack usable two-sided prices (BTTS/OU15 history; OU15 forward): price capture is the "
                    "binding constraint, not modelling.")
    acts.append("Never change v9 thresholds or enable anything from these numbers.")
    return acts


def _weekly_md(w, sc) -> str:
    L = [f"# Standard repair - weekly ({w['generated_at']})", "", f"Production change: **{w['production_change']}**", "",
         f"New first-sight observations: {w['new_observations_first_sight']}; new settlements: {w['new_settlements']}.", "",
         "## Served model vs market (first sight, forward)", "", "| market | n settled | weeks | dLL (v9 - market) | CI95 | CLV lean side | CLV coverage |",
         "|---|---|---|---|---|---|---|"]
    for m, r in w["model_vs_market_forward"].items():
        d = r.get("served_v9_dLL_vs_market") or {}
        L.append(f"| {m} | {r['n_settled_priced']} | {r['gameweeks']} | {d.get('delta')} | {d.get('ci95')} | "
                 f"{r['clv_lean_side']['mean']} | {r['clv_lean_side']['coverage']} |")
    L += ["", "## Tracks", "", "| track | diagnosis | forward n | forward dLL | next |", "|---|---|---|---|---|"]
    for t in sc["tracks"]:
        L.append(f"| {t['track_id']} | {', '.join(d['code'] for d in t['diagnosis'])} | {t['forward'].get('n_settled')} | "
                 f"{(t['forward'].get('dLL_vs_market') or {}).get('delta')} | {t['next_experiment']} |")
    L += ["", "## State changes", ""] + ([f"- {c}" for c in w["state_changes"]] or ["- none"])
    L += ["", "## Next actions", ""] + [f"- {a}" for a in w["next_actions"]]
    return "\n".join(L) + "\n"


def monthly() -> dict:
    sc = json.loads((OUT / "scorecard.json").read_text(encoding="utf-8"))
    reg_p = cfg.REGISTRY_DIR / "standard_repair" / "experiments.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8")) if reg_p.exists() else {"experiments": {}}
    hist = pd.DataFrame([json.loads(x) for x in HIST.read_text(encoding="utf-8").splitlines() if x.strip()]) \
        if HIST.exists() else pd.DataFrame()
    now = _now()
    improved, degraded = [], []
    if not hist.empty:
        hist["date"] = pd.to_datetime(hist["date"])
        cur = hist[hist["date"] == hist["date"].max()].set_index("track_id")
        old_d = hist[hist["date"] <= hist["date"].max() - pd.Timedelta(days=28)]
        if not old_d.empty:
            old = old_d[old_d["date"] == old_d["date"].max()].set_index("track_id")
            for tid in cur.index.intersection(old.index):
                a, b = old.at[tid, "forward_dLL"], cur.at[tid, "forward_dLL"]
                if pd.notna(a) and pd.notna(b):
                    (improved if b < a - 0.002 else degraded if b > a + 0.002 else []).append(
                        {"track_id": tid, "forward_dLL_from": a, "to": b})
    rules = []
    for t in sc["tracks"]:
        for b in (t["historical"].get("v9_holdout", {}) or {}).get("disagreement_bands", []) or []:
            if b.get("clv") is not None and b["clv"] > 0 and b["n"] >= 50:
                rules.append({"track_id": t["track_id"], "band_pp": b["band_pp"], "n": b["n"], "clv": b["clv"], "roi": b.get("roi")})
    m = {"generated_at": now.strftime("%Y-%m-%d %H:%M UTC"), "production_change": "NONE",
         "improved_tracks": improved, "degraded_tracks": degraded,
         "models_consistently_beating_market": [k for k, v in sc["pooled_verdict"].items() if v["beats_market"]],
         "selection_rules_with_positive_clv_historical": rules,
         "tracks_ready_for_forward_promotion": [t["track_id"] for t in sc["tracks"] if t["research_status"] != "RESEARCH_REPAIR"],
         "experiments_to_kill": sorted(k for k, v in reg["experiments"].items() if str(v.get("decision", "")).startswith("REJECTED"))}
    name = f"monthly_{now.strftime('%Y-%m')}"
    (OUT / f"{name}.json").write_text(json.dumps(m, indent=1, default=str), encoding="utf-8")
    md = [f"# Standard repair - monthly deep review {now.strftime('%Y-%m')}", "", "Production change: **NONE**", "",
          f"- Improved tracks: {len(improved)}; degraded: {len(degraded)}",
          f"- Models consistently beating the market: {m['models_consistently_beating_market'] or 'none'}",
          f"- Historical OU25 selection bands with positive CLV (n>=50): {len(rules)} (diagnostic only; not a selection rule until preregistered)",
          f"- Tracks ready for forward promotion: {m['tracks_ready_for_forward_promotion'] or 'none'}",
          f"- Experiments to kill ({len(m['experiments_to_kill'])}):"] + [f"  - {k}" for k in m["experiments_to_kill"]]
    (OUT / f"{name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return m
