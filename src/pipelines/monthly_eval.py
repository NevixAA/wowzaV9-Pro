"""
Monthly out-of-sample evaluation.
=================================
    python -m src.pipelines.monthly_eval [--json path]

Tests the hypotheses in docs/PREREGISTERED_HYPOTHESES.md against fixtures that did NOT exist when
those hypotheses were formed, and reports how close CLV is to unblocking a real BET.

WHY THE CONSTANTS BELOW ARE LITERALS. H1 predicts that the model's information is concentrated
where it disagrees with the price, above |p_model - p_market| >= 0.123. That 0.123 was the Q4
boundary of the n=564 in-sample data. If this script instead recomputed quartiles on the new
sample, the boundary would move and it would be silently testing a DIFFERENT hypothesis that
happens to share a name — the exact retrospective-tuning failure invariant 6 forbids. Same for
w=0.20: tuning the blend weight on the evaluation sample and then reporting the improvement it
produces is the in-sample error that made v9's ensemble AUC meaningless.

So every number here is copied from the pre-registration and must only change by amending that
document with a new hypothesis, never by editing these values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg
from src.pipelines.shadow import build_dataset
from src.validation.multiple_testing import paired_bootstrap_p

# ── frozen from docs/PREREGISTERED_HYPOTHESES.md § H1 ────────────────────────
H1_CUTS = (0.031, 0.065, 0.123)     # strata boundaries on |p_model - p_market|
H1_HIGH_CUT = 0.123                 # the stratum the hypothesis is about
H1_WEIGHT = 0.20                    # blend weight, NOT tuned here
H1_MIN_N = 150                      # below this the verdict is INSUFFICIENT, not REFUTED
H1_ALPHA = 0.05
H1_HOLDOUT_AFTER = "2026-08-18"     # data behind the hypothesis ends here
MIN_CLV_N = 150                     # v11's config.MIN_CLV_N — the BET gate

# ── what makes a CLV observation CLEAN ───────────────────────────────────────
# ROOT CAUSE, already fixed upstream. This guard exists for the HISTORICAL residue.
#
# v9 commit c19ca31 (2026-08-10): the O/U parser matched ANY bet name containing "Over/Under", so
# NON-GOAL markets — corners, cards, team totals — leaked their "Over 2.5" price into the goal
# `over25` key, and BTTS prices were copied into `over25`/`under25`. Those prices sit around
# 1.20-1.30, so an entry of 1.96 against a "closing" of 1.20 manufactures clv_pct +63 from nothing.
#
# Confirmed: 22 contaminated ledger rows have a closing price exactly equal to an archived BTTS
# price, and ZERO clean rows do. Timeline matches — contamination runs through July (81% of rows)
# and 1-9 August (45%), then stops dead at match_date 2026-08-09, the day before the fix.
#
# Two earlier diagnoses of mine were WRONG and are kept here because each looked convincing:
#   1. "mis-joined market" — refuted: the archived over25/under25 pair is coherent, overround
#      median 1.016 across 3,446 fixtures. A real market, just not the goals one.
#   2. "in-play prices used as the close" — the leaked prices mimic a 0-0 second half almost
#      perfectly, but predict already skips kicked-off fixtures, and no in-play goals price would
#      land exactly on a BTTS quote.
#
# Also worth stating plainly: over25 and under25 are NOT different markets. They are the two
# bettable sides of ONE line from one model probability, which is why "wrong market" could never
# explain a 46% -> 80% move in the first place.
#
# c19ca31 cleaned data GOING FORWARD and explicitly left "existing archive rows unchanged... a
# one-time historical re-filter can be done separately if wanted". This IS that re-filter, applied
# at READ time rather than by rewriting history.
#
# Effect: unfiltered mean CLV reads +22.9% against a median of +2.45%, and this script's first run
# duly reported new_format READY to bet on +26.26%. Clean it is -0.015% — no edge at all. v11's
# `_rolling_clv_stats` called its output `clean_n` while only dropping NaN, so the inflated mean fed
# the gate that certifies a BET. Both filtered and raw figures are reported below so the effect of
# this choice stays visible.
CLV_PLAUSIBLE_ABS = 25.0


def _logloss_diff(g: pd.DataFrame, w: float):
    """Per-fixture (market log-loss - blend log-loss). Positive = blend is better."""
    y = g["y"].to_numpy(dtype=float)
    pm = g["p_market"].to_numpy(dtype=float)
    pb = w * g["p_model"].to_numpy(dtype=float) + (1 - w) * pm
    lm = -(y * np.log(pm) + (1 - y) * np.log(1 - pm))
    lb = -(y * np.log(pb) + (1 - y) * np.log(1 - pb))
    return lb, lm


def _test(g: pd.DataFrame, w: float = H1_WEIGHT) -> dict:
    if len(g) < 20:
        return {"n": len(g), "diff": None, "p": None, "ci": None}
    lb, lm = _logloss_diff(g, w)
    p, diff, ci = paired_bootstrap_p(lb, lm, n_boot=4000, block=5)
    return {"n": int(len(g)), "diff": float(diff), "p": float(p),
            "ci": [float(ci[0]), float(ci[1])]}


def evaluate_h1(df: pd.DataFrame) -> dict:
    """H1 on the held-out slice only."""
    d = df.copy()
    d["match_date"] = d["match_date"].astype(str).str[:10]
    hold = d[d["match_date"] > H1_HOLDOUT_AFTER].copy()
    out = {"holdout_after": H1_HOLDOUT_AFTER, "n_holdout": int(len(hold)),
           "weight": H1_WEIGHT, "cuts": list(H1_CUTS), "high_cut": H1_HIGH_CUT}
    if hold.empty:
        out.update(verdict="INSUFFICIENT",
                   note="no fixtures after the registration cut-off yet")
        return out
    hold["gap"] = (hold["p_model"] - hold["p_market"]).abs()
    high = hold[hold["gap"] >= H1_HIGH_CUT]
    low = hold[hold["gap"] < H1_HIGH_CUT]
    out["high"] = _test(high)
    out["low"] = _test(low)
    # Per-stratum, using the FROZEN cut points
    edges = [0.0, *H1_CUTS, 1.0]
    out["strata"] = []
    for i in range(4):
        lo, hi = edges[i], edges[i + 1]
        g = hold[(hold["gap"] >= lo) & (hold["gap"] < hi)]
        r = _test(g)
        r["range"] = [lo, hi]
        out["strata"].append(r)

    h = out["high"]
    if h["n"] < H1_MIN_N:
        out["verdict"] = "INSUFFICIENT"
        out["note"] = (f"high stratum has {h['n']} fixtures, needs {H1_MIN_N}. "
                       f"Absence of significance at small n is not evidence of absence.")
    elif h["diff"] is not None and h["diff"] > 0 and h["p"] is not None and h["p"] < H1_ALPHA:
        lo_ok = (out["low"]["p"] is None or out["low"]["p"] >= H1_ALPHA
                 or (out["low"]["diff"] or 0) <= 0)
        out["verdict"] = "SUPPORTED" if lo_ok else "REFUTED"
        out["note"] = ("high stratum improves significantly and the low stratum does not"
                       if lo_ok else
                       "high stratum improves BUT so does the low stratum — the effect is not "
                       "about disagreement, so the stratification was noise-fitting")
    else:
        out["verdict"] = "REFUTED"
        out["note"] = "high stratum shows no significant improvement at n >= MIN_N"
    return out


def evaluate_clv() -> dict:
    """H2: how far is CLV from unblocking a BET, per segment."""
    from src.data import v9_source as v9
    out = {"min_clv_n": MIN_CLV_N, "segments": []}
    led = v9.fetch_csv("output/bets_ledger.csv", required=False)
    if led.empty:
        out["note"] = "bets_ledger unreadable"
        return out
    clv_col = next((c for c in led.columns if "clv" in c.lower()), None)
    if not clv_col:
        out["note"] = "no CLV column in the ledger"
        return out
    led["_clv"] = pd.to_numeric(led[clv_col], errors="coerce")
    seg_col = next((c for c in ("model_type", "league") if c in led.columns), None)
    present = led[led["_clv"].notna()]
    clean = present[present["_clv"].abs() <= CLV_PLAUSIBLE_ABS]
    out["plausible_abs_limit"] = CLV_PLAUSIBLE_ABS
    out["total_rows"] = int(len(led))
    out["clv_present"] = int(len(present))
    out["clv_clean"] = int(len(clean))
    out["clv_rejected_implausible"] = int(len(present) - len(clean))
    out["coverage_clean"] = round(len(clean) / max(1, len(led)), 4)
    # Raw figures kept alongside, so the effect of the filter is visible rather than assumed.
    if len(present):
        out["mean_clv_raw"] = round(float(present["_clv"].mean()), 4)
        out["median_clv_raw"] = round(float(present["_clv"].median()), 4)
    if len(clean):
        out["mean_clv_clean"] = round(float(clean["_clv"].mean()), 4)
    if seg_col:
        for seg, g in clean.groupby(clean[seg_col].astype(str)):
            allseg = present[present[seg_col].astype(str) == seg]
            out["segments"].append({
                "segment": seg, "n_clean": int(len(g)),
                "n_present": int(len(allseg)),
                "n_rejected": int(len(allseg) - len(g)),
                "mean_clv_pct": round(float(g["_clv"].mean()), 4),
                "mean_clv_unfiltered": round(float(allseg["_clv"].mean()), 4),
                "ready": bool(len(g) >= MIN_CLV_N and g["_clv"].mean() > 0),
            })
        out["segments"].sort(key=lambda s: -s["n_clean"])
    return out


def run(json_path: str | None = None) -> int:
    now = pd.Timestamp.now(tz="UTC")
    print(f"[eval] {now:%Y-%m-%d %H:%M UTC}")
    print("[eval] thresholds are LITERALS from docs/PREREGISTERED_HYPOTHESES.md — "
          "recomputing them on this sample would change the test")
    df = build_dataset()
    print(f"[eval] full dataset: {len(df)} settled fixtures")

    h1 = evaluate_h1(df)
    print(f"\n=== H1: information concentrated where the model DISAGREES ===")
    print(f"  holdout: match_date > {h1['holdout_after']}   n = {h1['n_holdout']}")
    if h1["n_holdout"]:
        for nm in ("high", "low"):
            r = h1.get(nm, {})
            lbl = (f"gap >= {H1_HIGH_CUT}" if nm == "high" else f"gap < {H1_HIGH_CUT}")
            if r.get("diff") is None:
                print(f"  {lbl:18} n={r.get('n', 0):4}  (too small to test)")
            else:
                print(f"  {lbl:18} n={r['n']:4}  C-vs-B {r['diff']:+.5f}  p={r['p']:.4f}  "
                      f"90%CI[{r['ci'][0]:+.5f},{r['ci'][1]:+.5f}]")
        for i, s in enumerate(h1.get("strata", []), 1):
            if s.get("diff") is None:
                print(f"    Q{i} {str(s['range']):16} n={s['n']:4}  (too small)")
            else:
                print(f"    Q{i} {str(s['range']):16} n={s['n']:4}  {s['diff']:+.5f}  "
                      f"p={s['p']:.4f}")
    print(f"  VERDICT: {h1['verdict']}  — {h1.get('note','')}")

    clv = evaluate_clv()
    print(f"\n=== H2: CLV readiness (gate is {clv['min_clv_n']} clean obs per segment) ===")
    print(f"  rows with a CLV value : {clv.get('clv_present', 0):,} of "
          f"{clv.get('total_rows', 0):,}")
    print(f"  CLEAN (|clv| <= {clv.get('plausible_abs_limit')}%): {clv.get('clv_clean', 0):,}  "
          f"REJECTED as implausible: {clv.get('clv_rejected_implausible', 0):,}")
    if "mean_clv_raw" in clv:
        print(f"  mean CLV raw {clv['mean_clv_raw']:+.2f}%  median raw "
              f"{clv['median_clv_raw']:+.2f}%  mean CLEAN "
              f"{clv.get('mean_clv_clean', float('nan')):+.2f}%")
        print(f"  -> the gap between raw mean and median is the contamination; the median is "
              f"believable, the mean is not")
    ready = [s for s in clv.get("segments", []) if s["ready"]]
    for s in clv.get("segments", [])[:8]:
        flag = "READY" if s["ready"] else f"needs {max(0, clv['min_clv_n'] - s['n_clean'])} more"
        print(f"    {s['segment'][:20]:20} clean n={s['n_clean']:5} "
              f"(rejected {s['n_rejected']:4})  mean {s['mean_clv_pct']:+.3f}%  "
              f"[unfiltered {s['mean_clv_unfiltered']:+.2f}%]  {flag}")
    print(f"  segments cleared to BET: {len(ready)}")
    if not ready:
        print("  -> every v11 signal stays PAPER. This, not model quality, is the binding "
              "constraint.")

    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "n_fixtures": int(len(df)), "h1": h1, "h2_clv": clv}
    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"\n[eval] written -> {json_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(cfg.OUTPUT_DIR / "monthly_eval.json"))
    return run(json_path=ap.parse_args().json)


if __name__ == "__main__":
    raise SystemExit(main())
