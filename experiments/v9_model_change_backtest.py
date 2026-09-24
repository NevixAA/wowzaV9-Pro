"""Did the 2026-09-23 data restoration make the live model BETTER, or just LOUDER?

    python experiments/v9_model_change_backtest.py

THE QUESTION. Commit d25ff411 un-froze four seasons of corners, half-time goals and O/U price
that a cache regression had been excluding from training. The next scheduled retrain rebuilt
the live model on it, and the model's behaviour changed enormously: the spread of p(over 2.5)
doubled (std 0.109 -> 0.207), 19 of 57 upcoming fixtures crossed the Over/Under boundary, and a
single predict run produced five real-money SNIPER tips with edges up to 29.5% where the week
before produced none above 11%.

WHY THE REPORTED METRICS DO NOT ANSWER IT. The retrain's own numbers went AUC 0.534 -> 0.709,
which looks conclusive and is not: n_test went 3,570 -> 5,558 at the same time, because adding
rows moved the chronological split. Those are two different test sets, so the two AUCs are not
comparable quantities. 0.709 is also above the 0.57-0.64 band Pro's prediction lab established
for these markets, which is a reason for suspicion rather than celebration.

WHAT THIS DOES INSTEAD. Walk forward month by month over the leagues we actually bet, and at
each step fit BOTH feature sets on identical training rows and score them on identical test
fixtures. Same rows, same split, same everything except whether the restored families are
available. That isolates the one thing that changed.

CALIBRATION IS THE POINT, NOT DISCRIMINATION. The estate's load-bearing negative result is that
v9 is overconfident by +13.64pp and that its tier ladder carries no information. A model whose
spread has doubled can easily be MORE wrong in money terms while scoring better on AUC, because
AUC only cares about ranking and staking cares about the number. So this reports log loss,
Brier and ECE alongside AUC, and then simulates flat-stake P&L at the thresholds production
actually runs -- which are the env values in predict.yml, not the config.py defaults.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

V9 = Path(__file__).resolve().parents[2] / "v9"
sys.path.insert(0, str(V9))
os.chdir(V9)                      # data_loader resolves several paths relatively

from src.data_loader import load_all_matches          # noqa: E402
from src.feature_engineering import build_features    # noqa: E402
from src.model import train, predict_proba, FEATURE_COLS  # noqa: E402
import config as C                                    # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

# The families the fix restored. Everything else was present before and after.
RESTORED = [c for c in FEATURE_COLS
            if "corners" in c.lower() or "ht_" in c.lower()]
OLD_COLS = [c for c in FEATURE_COLS if c not in RESTORED]

N_FOLDS = 8           # trailing months to walk
MIN_TRAIN = 3000
MIN_TEST = 60


def _ece(y, p, bins=10):
    """Expected calibration error: mean |predicted - realised| weighted by bin size."""
    idx = np.clip((p * bins).astype(int), 0, bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        tot += m.sum() / len(p) * abs(p[m].mean() - y[m].mean())
    return tot


def _metrics(y, p):
    from sklearn.metrics import roc_auc_score
    q = np.clip(p, 1e-15, 1 - 1e-15)
    return {
        "n": int(len(y)),
        "log_loss": float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean()),
        "brier": float(((p - y) ** 2).mean()),
        "auc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan"),
        "ece": float(_ece(y, p)),
        "mean_pred": float(p.mean()),
        "realised": float(y.mean()),
        "std_pred": float(p.std()),
    }


def _pnl(test, p, floor):
    """Flat 1u at the given edge floor, best side only. Returns (bets, units, roi)."""
    if "odds_over25" not in test.columns or "odds_under25" not in test.columns:
        return 0, float("nan"), float("nan")
    o_over = pd.to_numeric(test["odds_over25"], errors="coerce").to_numpy()
    o_und = pd.to_numeric(test["odds_under25"], errors="coerce").to_numpy()
    y = test["over25"].to_numpy(dtype=float)
    e_over = p - 1.0 / o_over
    e_und = (1.0 - p) - 1.0 / o_und
    take_over = (e_over >= e_und) & (e_over >= floor) & np.isfinite(o_over)
    take_und = (e_und > e_over) & (e_und >= floor) & np.isfinite(o_und)
    units = 0.0
    n = int(take_over.sum() + take_und.sum())
    if take_over.any():
        units += np.where(y[take_over] == 1, o_over[take_over] - 1.0, -1.0).sum()
    if take_und.any():
        units += np.where(y[take_und] == 0, o_und[take_und] - 1.0, -1.0).sum()
    return n, float(units), (float(units) / n if n else float("nan"))


def _payload(results: dict, target: str = "over25") -> dict:
    """train() returns {name: {model, metrics, feature_cols}}; predict_proba wants the SAVED
    shape. save_models() does this transform on its way to disk, so doing it here keeps the
    comparison entirely in memory -- no .pkl is written, and production models are untouched."""
    return {
        "target": target,
        "models": {k: v["model"] for k, v in results.items()},
        "feature_cols": results[next(iter(results))]["feature_cols"],
        "metrics": {k: v["metrics"] for k, v in results.items()},
    }


def _frame() -> pd.DataFrame:
    """Build the feature frame once and cache it.

    load_all_matches() performs LIVE API-Football shot enrichment as a side effect -- the
    first run of this script spent about 4,000 calls re-fetching shots for the newly added
    leagues. That is a real cost against a shared daily quota that production depends on, and
    it must not be paid again on every re-run of an experiment.
    """
    cache = OUT / "feature_frame.parquet"
    if cache.exists():
        print(f"[load] cached frame {cache.name} (no API calls)")
        return pd.read_parquet(cache)
    print("[load] building the training frame from v9 (this hits the API once) ...")
    f = build_features(load_all_matches())
    f.to_parquet(cache, index=False)
    return f


def main() -> int:
    feat = _frame()
    feat["date"] = pd.to_datetime(feat["date"], errors="coerce")

    # Invariant 1 (never mix tracks) and invariant 7 (bet leagues, not training-only ones).
    std_bet = [l for l in C.ENABLED_LEAGUES
               if C.model_type_for_league(l) == "standard"]
    d = feat[feat["league"].isin(std_bet)].dropna(subset=["over25", "date"])
    d = d.sort_values("date").reset_index(drop=True)
    print(f"[scope] {len(d):,} fixtures across {d['league'].nunique()} standard bet leagues "
          f"({d['date'].min().date()} .. {d['date'].max().date()})")
    print(f"[spec]  restored families: {len(RESTORED)} features  |  "
          f"OLD set {len(OLD_COLS)}  NEW set {len(FEATURE_COLS)}")

    months = sorted(d["date"].dt.to_period("M").unique())[-(N_FOLDS + 1):]
    rows, pnl_rows = [], []

    for mon in months[1:]:
        ms, me = mon.to_timestamp(), (mon + 1).to_timestamp()
        tr = d[d["date"] < ms]
        te = d[(d["date"] >= ms) & (d["date"] < me)]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            print(f"  {mon}: skipped (train {len(tr)}, test {len(te)})")
            continue
        y = te["over25"].to_numpy(dtype=float)
        preds = {}
        for name, cols in (("OLD", OLD_COLS), ("NEW", FEATURE_COLS)):
            results = train(tr, target="over25", feature_cols=cols)
            p = predict_proba(te, payload=_payload(results)).to_numpy(dtype=float)
            preds[name] = p
            rows.append({"month": str(mon), "spec": name, **_metrics(y, p)})
            for floor in (0.03, 0.08, 0.12):
                n, u, roi = _pnl(te, p, floor)
                pnl_rows.append({"month": str(mon), "spec": name, "edge_floor": floor,
                                 "bets": n, "units": round(u, 3),
                                 "roi": round(roi, 4) if n else None})
        print(f"  {mon}: train {len(tr):,} test {len(te):,}  "
              f"logloss OLD {rows[-2]['log_loss']:.5f} -> NEW {rows[-1]['log_loss']:.5f}")

    if not rows:
        print("nothing evaluated")
        return 1

    m = pd.DataFrame(rows)
    piv = m.pivot_table(index="spec", values=["log_loss", "brier", "auc", "ece",
                                              "mean_pred", "realised", "std_pred"])
    print("\n" + "=" * 72)
    print("ACCURACY — identical training rows, identical test fixtures")
    print("(log_loss / brier / ece: LOWER is better. auc: higher.)")
    print(piv.round(5).to_string())

    # Paired per-month comparison — the honest test, since folds differ in difficulty.
    w = m.pivot_table(index="month", columns="spec", values="log_loss")
    w["delta"] = w["NEW"] - w["OLD"]
    wins = int((w["delta"] < 0).sum())
    print(f"\nper-month log loss, NEW minus OLD (negative = NEW better):")
    print(w.round(5).to_string())
    print(f"\nmonths where NEW beat OLD: {wins} of {len(w)}")

    # Overconfidence, the failure mode that actually costs money.
    print("\nCALIBRATION — mean predicted vs realised (gap = overconfidence)")
    for spec in ("OLD", "NEW"):
        s = m[m.spec == spec]
        gap = (s["mean_pred"] - s["realised"]).mean()
        print(f"   {spec}: predicted {s['mean_pred'].mean():.4f}  "
              f"realised {s['realised'].mean():.4f}  gap {gap:+.4f}  "
              f"ECE {s['ece'].mean():.4f}  spread {s['std_pred'].mean():.4f}")

    p = pd.DataFrame(pnl_rows)
    agg = p.groupby(["spec", "edge_floor"]).agg(bets=("bets", "sum"),
                                                units=("units", "sum")).reset_index()
    agg["roi"] = (agg["units"] / agg["bets"]).round(4)
    print("\nFLAT 1u P&L at production edge floors "
          "(0.03 VALUABLE / 0.08 MARKSMAN / 0.12 SNIPER cap)")
    print(agg.to_string(index=False))

    m.to_csv(OUT / "model_change_accuracy.csv", index=False)
    p.to_csv(OUT / "model_change_pnl.csv", index=False)
    print(f"\n[write] {OUT/'model_change_accuracy.csv'}")
    print(f"[write] {OUT/'model_change_pnl.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
