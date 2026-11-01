"""R2-B repaired challengers (owner brief 2026-11-01) - collect the CI benchmark into a verdict.

    python -m src.studies.r2_repaired_challengers <dir with v9 benchmark outputs>
        -> output/studies/r2_repaired_challengers/{verdict.csv, regimes.csv, coldstart.csv,
           summary.json} and registry/r2/r2b_repaired_challengers.json (results block only)

The benchmark runs inside v9 (branch r2/repaired-challengers, scripts/train_repaired_challengers.py)
on GitHub Actions. This module only READS its JSON files. RETROSPECTIVE evidence only: nothing here
is forward evidence, nothing is promotable, no threshold is read or tuned.

Verdict per experiment x track, rule FROZEN 2026-11-01 before any result was read:
  primary  served-probability holdout log loss, challenger minus CHAMPION_LEGACY_REPRO, 95% matchday
           block-bootstrap CI:  < 0 entirely -> REPAIRED_BETTER_RETROSPECTIVE
                                > 0 entirely -> REPAIRED_WORSE_RETROSPECTIVE
                                otherwise    -> NO_DIFFERENCE_RETROSPECTIVE
  caveat   the champion's meta-logistic is fitted ON the holdout (legacy bug 6), so its holdout
           number is optimistic; CHAMPION_BASEMEAN (no meta) is reported as the clean legacy
           reference and the verdict against it is given too.
  market   only where genuine two-sided entry prices exist; otherwise NOT_EVALUABLE.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR / "studies" / "r2_repaired_challengers"
REGISTRY = Path(cfg.OUTPUT_DIR).parent / "registry" / "r2" / "r2b_repaired_challengers.json"
CHAMP, BASE = "CHAMPION_LEGACY_REPRO", "CHAMPION_BASEMEAN"
#: experiment id -> (task, track, challenger arm)
EXPERIMENTS = {
    "NF-R2-OU25": ("nf_ou25", "newformat", "CHALLENGER_NEWFORMAT"),
    "SIDE-R2-BTTS-STD": ("side_btts", "standard", "CHALLENGER_STANDARD"),
    "SIDE-R2-BTTS-NF": ("side_btts", "newformat", "CHALLENGER_NEWFORMAT"),
    "SIDE-R2-O15-STD": ("side_over15", "standard", "CHALLENGER_STANDARD"),
    "SIDE-R2-O15-NF": ("side_over15", "newformat", "CHALLENGER_NEWFORMAT"),
    "SIDE-R2-O35-STD": ("side_over35", "standard", "CHALLENGER_STANDARD"),
    "SIDE-R2-O35-NF": ("side_over35", "newformat", "CHALLENGER_NEWFORMAT"),
    "HT-R2-O05": ("ht_over05", None, "CHALLENGER_POOLED"),
    "HT-R2-O15": ("ht_over15", None, "CHALLENGER_POOLED"),
}


def verdict(ci) -> str:
    if not ci or ci[0] is None:
        return "NOT_EVALUABLE"
    if ci[1] < 0:
        return "REPAIRED_BETTER_RETROSPECTIVE"
    if ci[0] > 0:
        return "REPAIRED_WORSE_RETROSPECTIVE"
    return "NO_DIFFERENCE_RETROSPECTIVE"


def _load(src: Path, name: str) -> dict | None:
    f = src / f"{name}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _row(eid, task, track, arm, r, tr) -> dict:
    a = (tr.get("arms") or {})
    ch, c0, cb = a.get(arm, {}), a.get(CHAMP, {}), a.get(BASE, {})
    mk = tr.get("market") or {}
    res = (mk.get("arms_on_priced_rows") or {}).get(arm, {}).get("residual_vs_market") or {}
    out = {"experiment": eid, "task": task, "track": track, "status": "OK", "n": tr.get("n"),
           "holdout": "..".join(tr.get("dates") or []), "holdout_start": r.get("holdout_start"),
           "champion_ll": c0.get("log_loss"), "champion_basemean_ll": cb.get("log_loss"),
           "challenger_ll": ch.get("log_loss"),
           "delta_ll_vs_champion": ch.get(f"delta_ll_vs_{CHAMP}"),
           "delta_ll_ci95": ch.get(f"delta_ll_vs_{CHAMP}_ci95"),
           "verdict_vs_champion": verdict(ch.get(f"delta_ll_vs_{CHAMP}_ci95")),
           "champion_brier": c0.get("brier"), "challenger_brier": ch.get("brier"),
           "champion_ece": c0.get("ece"), "champion_basemean_ece": cb.get("ece"),
           "challenger_ece": ch.get("ece"),
           "champion_auc": c0.get("auc"), "challenger_auc": ch.get("auc"),
           "challenger_cal_slope": ch.get("cal_slope"), "champion_cal_slope": c0.get("cal_slope"),
           "base_rate": ch.get("base_rate"), "challenger_mean_p": ch.get("mean_p"),
           "market_status": mk.get("status"), "market_n": mk.get("n_priced"),
           "market_ll": (mk.get("market") or {}).get("log_loss"),
           "residual_gain_vs_market": res.get("gain"), "residual_gain_ci95": res.get("gain_ci95")}
    if cb and ch and c0:
        # delta vs the clean legacy reference (no holdout-fitted meta), point estimate only
        out["delta_ll_vs_basemean"] = (round(ch["log_loss"] - cb["log_loss"], 5)
                                       if ch.get("log_loss") is not None and cb.get("log_loss") is not None else None)
    tvp = tr.get("track_vs_pooled") or {}
    if tvp:
        out["delta_ll_track_minus_pooled"] = tvp.get("delta_ll_vs_CHALLENGER_POOLED")
        out["delta_ll_track_minus_pooled_ci95"] = tvp.get("delta_ll_vs_CHALLENGER_POOLED_ci95")
        out["pooled_vs_track_verdict"] = verdict(tvp.get("delta_ll_vs_CHALLENGER_POOLED_ci95")).replace(
            "REPAIRED", "TRACK_ONLY")
    return out


def collect(src: Path) -> dict:
    rows, regimes, cold, raw = [], [], [], {}
    for eid, (task, track, arm) in EXPERIMENTS.items():
        r = _load(src, f"{task}__core")
        if r is None:
            rows.append({"experiment": eid, "task": task, "status": "MISSING (infra or job failure)"})
            continue
        raw[f"{task}__core"] = {k: v for k, v in r.items() if k != "arms_metadata"}
        tracks = [track] if track else [t for t in ("standard", "newformat") if t in r["tracks"]]
        for t in tracks:
            tr = r["tracks"].get(t) or {}
            if "arms" not in tr or arm not in tr["arms"]:
                rows.append({"experiment": eid, "task": task, "track": t,
                             "status": tr.get("status") or (r.get("skipped") or {}).get(arm) or "NOT_EVALUABLE"})
                continue
            rows.append(_row(eid, task, t, arm, r, tr))
    for f in sorted(src.glob("*__regimes__*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        raw[f.stem] = {k: v for k, v in r.items() if k != "arms_metadata"}
        t = r.get("track")
        tr = (r.get("tracks") or {}).get(t) or {}
        srep = (r.get("source_report") or {}).get(t) or {}
        for arm, m in (tr.get("arms") or {}).items():
            regimes.append({"task": r["task"], "track": t, "regime": arm, "n": m.get("n"),
                            "training_rows": (r.get("regime_rows") or {}).get(arm),
                            "log_loss": m.get("log_loss"), "brier": m.get("brier"), "ece": m.get("ece"),
                            "auc": m.get("auc"), "cal_slope": m.get("cal_slope"),
                            "delta_ll_vs_recency_weighted": m.get("delta_ll_vs_RECENCY_WEIGHTED"),
                            "delta_ll_ci95": m.get("delta_ll_vs_RECENCY_WEIGHTED_ci95"),
                            "verdict_vs_recency_weighted": verdict(m.get("delta_ll_vs_RECENCY_WEIGHTED_ci95"))
                            .replace("REPAIRED", "REGIME") if arm != "RECENCY_WEIGHTED" else "REFERENCE",
                            "source_predictable_auc": srep.get("source_predictable_from_missingness_auc"),
                            "rows_by_source": json.dumps(srep.get("rows_by_source")),
                            "target_rate_by_source": json.dumps(srep.get("target_rate_by_source"))})
    c = _load(src, "std_ou25__coldstart")
    if c:
        raw["std_ou25__coldstart"] = {k: v for k, v in c.items() if k != "arms_metadata"}
        tr = (c.get("tracks") or {}).get("standard") or {}
        for arm, m in (tr.get("arms") or {}).items():
            cold.append({"arm": arm, "n": m.get("n"), "log_loss": m.get("log_loss"), "brier": m.get("brier"),
                         "ece": m.get("ece"), "auc": m.get("auc"),
                         "delta_ll_vs_A": m.get("delta_ll_vs_A_CURRENT_PRIORS"),
                         "delta_ll_ci95": m.get("delta_ll_vs_A_CURRENT_PRIORS_ci95"),
                         "verdict_vs_A": verdict(m.get("delta_ll_vs_A_CURRENT_PRIORS_ci95")).replace(
                             "REPAIRED", "ABLATION") if arm != "A_CURRENT_PRIORS" else "REFERENCE"})
    ident = src / "identity_health.json"
    return {"verdict": pd.DataFrame(rows), "regimes": pd.DataFrame(regimes),
            "coldstart": pd.DataFrame(cold), "raw": raw,
            "identity": json.loads(ident.read_text(encoding="utf-8")) if ident.exists() else None}


def update_registry(v: pd.DataFrame, generated: str) -> None:
    if not REGISTRY.exists():
        return
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for e in reg["experiments"]:
        sub = v[v["experiment"] == e["id"]]
        e["retrospective_results"] = {"generated_at": generated,
                                      "rows": json.loads(sub.to_json(orient="records"))}
        e["lifecycle_stage"] = "RETROSPECTIVE_REPLAY"     # never advanced by this collector
    REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    src = Path((argv or sys.argv[1:])[0])
    res = collect(src)
    OUT.mkdir(parents=True, exist_ok=True)
    res["verdict"].to_csv(OUT / "verdict.csv", index=False)
    res["regimes"].to_csv(OUT / "regimes.csv", index=False)
    res["coldstart"].to_csv(OUT / "coldstart.csv", index=False)
    gen = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    (OUT / "summary.json").write_text(json.dumps({"generated_at": gen, "evidence_class": "RETROSPECTIVE",
                                                  "identity": res["identity"], "raw": res["raw"]},
                                                 indent=1, default=str), encoding="utf-8")
    update_registry(res["verdict"], gen)
    cols = [c for c in ("experiment", "track", "status", "n", "champion_ll", "champion_basemean_ll",
                        "challenger_ll", "delta_ll_ci95", "verdict_vs_champion", "challenger_ece",
                        "champion_ece", "market_status") if c in res["verdict"].columns]
    print("## R2-B repaired challengers (RETROSPECTIVE)\n")
    print(res["verdict"][cols].to_string(index=False) if len(res["verdict"]) else "(no rows)")
    if len(res["regimes"]):
        print("\n## Source regimes\n")
        print(res["regimes"][["task", "track", "regime", "training_rows", "log_loss", "ece",
                              "delta_ll_ci95", "verdict_vs_recency_weighted"]].to_string(index=False))
    if len(res["coldstart"]):
        print("\n## Standard cold-start ablation (research only)\n")
        print(res["coldstart"].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
