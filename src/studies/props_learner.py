"""Props learner study: can v9's player-prop models switch to a FAST learner without getting worse?

    python -m src.studies.props_learner --market goals          # one market -> props_learner_goals.json
    python -m src.studies.props_learner --merge                 # all markets -> props_learner.json + .md
    python -m src.studies.props_learner --market goals --max-rows 20000   # local smoke test only

WHY (2026-10-12). v9's weekly props retrain stopped completing after 2026-09-20: player_history
grew from 302,456 to 855,014 rows and the learner is sklearn's classic GradientBoostingClassifier,
single-threaded and linear in rows (measured 20k rows 61s, 60k rows 204s per fit). It was moved to
its own 340-minute job, but GitHub caps a job at 360 minutes and the history keeps growing, so
that buys months, not a fix. HistGradientBoostingClassifier is the same idea (boosted depth-limited
trees) on binned features and all cores: typically 10-50x faster. Changing the algorithm is an
ARCHITECTURAL change to v9, so it is measured here first.

FAIR COMPARISON. Everything except the learner is v9's own: v9's feature list and target map
(imported read-only from the v9 checkout), v9's n_prev_games filter, chronological sort, the 68/12/20
fit/calibration/test split, median fill, and Platt scaling fitted on the calibration block. Both
learners see identical rows. Only the GradientBoosting half of v9's pair is swapped; the logistic
half is untouched by either outcome.

DECISION RULE — fixed before any result was seen:
    per market, d = log loss(challenger) - log loss(incumbent) per test row,
    95% CI by matchday block bootstrap (dates resampled, 2,000 draws).
    PASS   the CI's upper end is <= 1% of the incumbent's own log loss -> no meaningful loss
           (relative, so a rare market like sot4, log loss ~0.03, is held to the same standard
           as goals, ~0.26; a fixed 0.002 would have been a 7% allowance on sot4)
    FAIL   otherwise.
    The switch is recommended only if EVERY market passes. Speed is reported, never traded for skill.
Recommendation only. Promotion into v9 needs the owner's explicit approval.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

NON_INFERIORITY_REL = 0.01
N_BOOT = 2000
OUT = Path("output/studies")
MARKETS = ["goals", "goals2", "assists", "sot", "sot2", "sot3", "sot4", "cards"]


def _v9_dir() -> Path:
    for p in (os.getenv("V9_LOCAL"), "_v9", "../v9"):
        if p and (Path(p) / "player_model").is_dir():
            return Path(p).resolve()
    raise SystemExit("v9 checkout not found: set V9_LOCAL")


def _v9_modules():
    v9 = _v9_dir()
    if str(v9) not in sys.path:
        sys.path.insert(0, str(v9))
    from player_model import config as pc            # read-only: feature list and paths
    from player_model.model import TARGETS, _prep
    return v9, pc, TARGETS, _prep


def _usable(col: np.ndarray) -> bool:
    """HGB's binner crashes on an all-NaN or single-valued column (sklearn 1.9). Train-only."""
    v = col[~np.isnan(col)]
    return v.size > 1 and np.nanmax(v) > np.nanmin(v)


def _platt(raw_cal, y_cal):
    from sklearn.linear_model import LogisticRegression
    return LogisticRegression(C=1.0, max_iter=1000).fit(raw_cal.reshape(-1, 1), y_cal)


def _ll_rows(y, p):
    p = np.clip(p, 0.001, 0.999)                      # the same clip v9's calibrated model applies
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _block_ci(d: np.ndarray, dates: np.ndarray, seed: int = 0) -> tuple[float, float]:
    keys, inv = np.unique(dates, return_inverse=True)
    sums = np.bincount(inv, weights=d)
    cnts = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(N_BOOT, len(keys)))
    boot = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))


def run_market(market: str, max_rows: int | None = None) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier
    from sklearn.metrics import brier_score_loss, roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    v9, pc, TARGETS, _prep = _v9_modules()
    df = pd.read_parquet(v9 / "player_history.parquet")
    # v9 train(): same filter, same order
    if "n_prev_games" in df.columns:
        df = df[df["n_prev_games"] >= 1]
    elif "appearances" in df.columns:
        df = df[df["appearances"] >= pc.MIN_APPEARANCES]
    df = df.sort_values("date").reset_index(drop=True)
    if max_rows:
        df = df.tail(max_rows).reset_index(drop=True)
    tcol = TARGETS[market]
    y = df[tcol].astype(int).to_numpy()
    X, cols = _prep(df)
    Xv = X.to_numpy(dtype=float)
    n = len(df)
    split = int(n * 0.80)
    cal = int(split * 0.85)
    fit, cb, te = slice(0, cal), slice(cal, split), slice(split, n)

    out = {"market": market, "rows": n, "n_fit": cal, "n_cal": split - cal, "n_test": n - split,
           "features": len(cols), "test_from": str(df["date"].iloc[split])[:10],
           "test_to": str(df["date"].iloc[-1])[:10], "base_rate_test": float(y[te].mean())}
    preds = {}

    t = time.time()
    inc = Pipeline([("scaler", StandardScaler()),
                    ("clf", GradientBoostingClassifier(n_estimators=300, max_depth=3, learning_rate=0.05,
                                                       subsample=0.8, min_samples_leaf=20,
                                                       random_state=42))]).fit(Xv[fit], y[fit])
    out["incumbent_fit_seconds"] = round(time.time() - t, 1)
    pl = _platt(inc.predict_proba(Xv[cb])[:, 1], y[cb])
    preds["incumbent"] = pl.predict_proba(inc.predict_proba(Xv[te])[:, 1].reshape(-1, 1))[:, 1]

    keep = [j for j in range(Xv.shape[1]) if _usable(Xv[fit, j])]
    t = time.time()
    ch = HistGradientBoostingClassifier(max_iter=300, max_depth=3, learning_rate=0.05,
                                        min_samples_leaf=20, early_stopping=False,
                                        random_state=42).fit(Xv[fit][:, keep], y[fit])
    out["challenger_fit_seconds"] = round(time.time() - t, 1)
    out["challenger_features_dropped"] = len(cols) - len(keep)
    pl = _platt(ch.predict_proba(Xv[cb][:, keep])[:, 1], y[cb])
    preds["challenger"] = pl.predict_proba(ch.predict_proba(Xv[te][:, keep])[:, 1].reshape(-1, 1))[:, 1]

    yt = y[te]
    for k, p in preds.items():
        p = np.clip(p, 0.001, 0.999)
        out[f"{k}_logloss"] = round(float(_ll_rows(yt, p).mean()), 6)
        out[f"{k}_brier"] = round(float(brier_score_loss(yt, p)), 6)
        out[f"{k}_auc"] = round(float(roc_auc_score(yt, p)), 4) if len(set(yt)) > 1 else None
    d = _ll_rows(yt, preds["challenger"]) - _ll_rows(yt, preds["incumbent"])
    lo, hi = _block_ci(d, pd.to_datetime(df["date"].iloc[split:]).dt.strftime("%Y-%m-%d").to_numpy())
    margin = NON_INFERIORITY_REL * out["incumbent_logloss"]
    out.update({"logloss_diff": round(float(d.mean()), 6), "diff_ci_low": round(lo, 6),
                "diff_ci_high": round(hi, 6), "non_inferiority_margin": round(margin, 6),
                "verdict": "PASS" if hi <= margin else "FAIL",
                "speedup": round(out["incumbent_fit_seconds"] / max(out["challenger_fit_seconds"], 0.1), 1),
                "smoke_test": bool(max_rows)})
    return out


def merge() -> dict:
    rows = []
    for m in MARKETS:
        f = OUT / f"props_learner_{m}.json"
        if f.exists():
            rows.append(json.loads(f.read_text(encoding="utf-8")))
    missing = [m for m in MARKETS if m not in {r["market"] for r in rows}]
    all_pass = bool(rows) and not missing and all(r["verdict"] == "PASS" for r in rows)
    res = {"generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "rule": f"PASS when the 95% block-bootstrap CI upper end of (challenger - incumbent) "
                   f"log loss is <= {NON_INFERIORITY_REL:.0%} of the incumbent's log loss; "
                   f"switch only if every market passes",
           "markets": rows, "missing": missing,
           "recommendation": ("SWITCH CANDIDATE — every market non-inferior; needs owner approval"
                              if all_pass else
                              "DO NOT SWITCH — " + ("markets missing: " + ", ".join(missing) if missing
                                                    else "at least one market fails non-inferiority"))}
    (OUT / "props_learner.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    lines = ["# Props learner study — classic GradientBoosting vs HistGradientBoosting", "",
             f"Generated {res['generated']}. Rule (fixed in advance): {res['rule']}.", "",
             f"**{res['recommendation']}**", "",
             "| Market | Test rows | Log loss now | Log loss fast | Diff (95% CI) | AUC now / fast | Fit time now / fast | Verdict |",
             "|---|---:|---:|---:|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['market']} | {r['n_test']:,} | {r['incumbent_logloss']:.5f} | "
                     f"{r['challenger_logloss']:.5f} | {r['logloss_diff']:+.5f} "
                     f"[{r['diff_ci_low']:+.5f}, {r['diff_ci_high']:+.5f}] | "
                     f"{r['incumbent_auc']} / {r['challenger_auc']} | "
                     f"{r['incumbent_fit_seconds'] / 60:.1f} / {r['challenger_fit_seconds'] / 60:.1f} min "
                     f"(x{r['speedup']}) | {r['verdict']} |")
    lines += ["", "Negative diff = the fast learner is better. Recommendation only; v9 changes need "
                  "the owner's approval."]
    (OUT / "PROPS_LEARNER.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=MARKETS)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--max-rows", type=int, default=None, help="local smoke test only")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.merge:
        r = merge()
        print((OUT / "PROPS_LEARNER.md").read_text(encoding="utf-8"))
        return 0
    if not a.market:
        ap.error("--market or --merge")
    r = run_market(a.market, a.max_rows)
    (OUT / f"props_learner_{a.market}.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
