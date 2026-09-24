"""Where does Wowza learn, and where does it not? League, season phase, and model age.

    python -m src.shadow_learning.breakdowns --write

Sections 17, 51, 66, 68-71. The walk-forward answered the global question -- retraining beats a
frozen model on all four markets. A global answer can hide the opposite happening somewhere:
one league improving strongly while another degrades leaves a flattering average and a policy
that is wrong for half the estate.

EVERY COMPARISON IS AGAINST THE FROZEN CONTROL, not against the league's own past. "Championship
Over 2.5 got better" is not a finding on its own, because the Championship may simply have
become more predictable. "Championship Over 2.5 got better AND the frozen model on the same
fixtures did not" is.

STATISTICAL RULES ARE FIXED BEFORE THE NUMBERS ARE LOOKED AT (section 37). A league-target cell
is:

    IMPROVED      retrained beats frozen, paired bootstrap CI excludes zero
    DEGRADED      frozen beats retrained, CI excludes zero
    UNCLEAR       CI includes zero, with at least the minimum sample
    INSUFFICIENT  fewer than MIN_N predictions -- reported, never interpreted

No subjective labels, and INSUFFICIENT is a real category rather than a quiet omission: a
league with 200 predictions genuinely cannot answer the question and saying so is the honest
result.

SEASON PHASE IS MEASURED IN MATCHES PLAYED, NOT IN CALENDAR MONTHS. Leagues start at different
times and several in this estate run on calendar years, so "August" means mid-season in Brazil
and opening day in England. Phase is therefore each fixture's position within its own
league-season, which is comparable across all of them.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.prediction_lab import metrics as M

CALC_VERSION = "1.0.0"
MIN_N = 400              # below this a league-target cell is not interpreted
TARGETS = ("btts", "over15", "over25", "over35")


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _preds() -> pd.DataFrame:
    p = O() / "walkforward_predictions.parquet"
    if not p.exists():
        raise RuntimeError("walkforward_predictions.parquet missing — run the walk-forward")
    d = pd.read_parquet(p)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["month"] = d["month"].astype(str)
    return d


def _paired(a_loss: np.ndarray, b_loss: np.ndarray) -> tuple[float, float, float, bool]:
    """(mean diff, ci_lo, ci_hi, significant). Positive diff = `a` is better."""
    from src.validation.multiple_testing import paired_bootstrap_p
    p, obs, ci = paired_bootstrap_p(a_loss, b_loss, n_boot=1500, block=8)
    return obs, ci[0], ci[1], bool(ci[0] > 0 or ci[1] < 0)


def _loss(g: pd.DataFrame) -> np.ndarray:
    p = np.clip(g["p"].to_numpy(float), 1e-15, 1 - 1e-15)
    y = g["actual"].to_numpy(float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def league_target(d: pd.DataFrame, *, challenger="canonical", control="frozen") -> pd.DataFrame:
    rows = []
    ch = d[d.variant == challenger]
    fr = d[d.variant == control]
    for (lg, t), g in ch.groupby(["league", "target"]):
        f = fr[(fr.league == lg) & (fr.target == t)]
        if f.empty:
            continue
        # Align on fixture so the two models are scored on identical matches.
        m = g[["fixture_key", "actual", "p"]].merge(
            f[["fixture_key", "p"]], on="fixture_key", suffixes=("_ch", "_fr"))
        if m.empty:
            continue
        lc = _loss(m.rename(columns={"p_ch": "p"}))
        lf = _loss(m.rename(columns={"p_fr": "p"}))
        n = len(m)
        base = float(m["actual"].mean())
        if n < MIN_N:
            verdict, diff, lo, hi, sigf = "INSUFFICIENT", np.nan, np.nan, np.nan, False
        else:
            diff, lo, hi, sigf = _paired(lc, lf)
            verdict = ("IMPROVED" if sigf and diff > 0 else
                       "DEGRADED" if sigf and diff < 0 else "UNCLEAR")
        rows.append({
            "league": lg, "target": t, "n_test": int(n), "base_rate": round(base, 4),
            "challenger_logloss": round(float(lc.mean()), 5),
            "control_logloss": round(float(lf.mean()), 5),
            "delta": round(float(lf.mean() - lc.mean()), 5),
            "ci_lo": round(lo, 5) if np.isfinite(lo) else None,
            "ci_hi": round(hi, 5) if np.isfinite(hi) else None,
            "challenger_brier": round(M.brier(m["actual"], m["p_ch"]), 5),
            "control_brier": round(M.brier(m["actual"], m["p_fr"]), 5),
            "challenger_auc": round(M.auc(m["actual"], m["p_ch"]), 4),
            "significant": sigf, "verdict": verdict})
    return pd.DataFrame(rows).sort_values(["target", "delta"], ascending=[True, False])


def season_phase(d: pd.DataFrame, *, challenger="canonical", control="frozen",
                 bins: int = 5) -> pd.DataFrame:
    """Is early-season prediction worse, and does retraining help more or less there?

    Phase is each fixture's position within its OWN league-season, not the calendar month --
    several leagues here run February to November, so a calendar split would compare opening
    day in England against mid-season in Brazil and call the difference a season effect.
    """
    d = d.copy()
    y = d["date"].dt.year
    d["season_key"] = (d["league"].astype(str) + "|"
                       + np.where(d["date"].dt.month >= 7, y, y - 1).astype(str))
    d = d.sort_values("date", kind="mergesort")
    d["phase"] = (d.groupby(["season_key", "target", "variant"]).cumcount()
                  / d.groupby(["season_key", "target", "variant"])["p"].transform("size"))
    d["phase_bin"] = pd.cut(d["phase"], bins=bins, labels=[
        "opening 20%", "early-mid", "mid", "late-mid", "closing 20%"][:bins])
    rows = []
    for (t, ph), g in d[d.variant == challenger].groupby(["target", "phase_bin"],
                                                         observed=True):
        f = d[(d.variant == control) & (d.target == t) & (d.phase_bin == ph)]
        m = g[["fixture_key", "actual", "p"]].merge(
            f[["fixture_key", "p"]], on="fixture_key", suffixes=("_ch", "_fr"))
        if len(m) < MIN_N:
            continue
        lc, lf = _loss(m.rename(columns={"p_ch": "p"})), _loss(m.rename(columns={"p_fr": "p"}))
        rows.append({"target": t, "phase": str(ph), "n": int(len(m)),
                     "base_rate": round(float(m["actual"].mean()), 4),
                     "challenger_logloss": round(float(lc.mean()), 5),
                     "control_logloss": round(float(lf.mean()), 5),
                     "retraining_gain": round(float(lf.mean() - lc.mean()), 5)})
    return pd.DataFrame(rows)


def model_age(ledger: pd.DataFrame) -> pd.DataFrame:
    """Does a model decay as it sits? Section 66."""
    d = ledger[ledger.interpretable & (ledger.variant != "frozen")].copy()
    if "model_age_months" not in d.columns:
        return pd.DataFrame()
    d["age_bucket"] = pd.cut(d["model_age_months"], [-0.1, 0.5, 1.5, 3.5, 100],
                             labels=["fresh (0m)", "1 month", "2-3 months", "4+ months"])
    return (d.groupby(["target", "age_bucket"], observed=True)
             .agg(months=("month", "nunique"), n_test=("n_test", "sum"),
                  log_loss=("log_loss", "mean"), brier=("brier", "mean"),
                  margin=("margin_vs_baseline_ll", "mean"))
             .round(5).reset_index())


def scorecard(d: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    """Section 70: first six months against the latest six, per target."""
    rows = []
    led = ledger[ledger.interpretable]
    for v in sorted(led.variant.unique()):
        for t in TARGETS:
            g = led[(led.variant == v) & (led.target == t)].sort_values("month")
            if len(g) < 18:
                continue
            e, l = g.head(6), g.tail(6)
            rows.append({
                "variant": v, "target": t, "months": int(len(g)),
                "matches_predicted": int(g.n_test.sum()),
                "first6_logloss": round(float(e.log_loss.mean()), 5),
                "last6_logloss": round(float(l.log_loss.mean()), 5),
                "delta_logloss": round(float(l.log_loss.mean() - e.log_loss.mean()), 5),
                "first6_brier": round(float(e.brier.mean()), 5),
                "last6_brier": round(float(l.brier.mean()), 5),
                "first6_auc": round(float(e.auc.mean()), 4),
                "last6_auc": round(float(l.auc.mean()), 4),
                "first6_margin": round(float(e.margin_vs_baseline_ll.mean()), 5),
                "last6_margin": round(float(l.margin_vs_baseline_ll.mean()), 5),
                "delta_margin": round(float(l.margin_vs_baseline_ll.mean()
                                            - e.margin_vs_baseline_ll.mean()), 5)})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    d = _preds()
    led = pd.read_csv(O() / "monthly_walkforward_performance.csv")
    print(f"[breakdowns] {len(d):,} stored predictions, "
          f"{d.league.nunique()} leagues, {d.variant.nunique()} variants")

    lt = league_target(d)
    print(f"\nLEAGUE x TARGET — retrained vs FROZEN on identical fixtures")
    print(lt["verdict"].value_counts().to_string())
    ok = lt[lt.verdict != "INSUFFICIENT"]
    print(f"\n  best 12 cells (positive delta = retraining helps):")
    print(ok.head(12)[["league", "target", "n_test", "challenger_logloss",
                       "control_logloss", "delta", "verdict"]].to_string(index=False))
    bad = ok[ok.verdict == "DEGRADED"]
    print(f"\n  cells where retraining HURT: {len(bad)}")
    if len(bad):
        print(bad[["league", "target", "n_test", "delta", "ci_lo", "ci_hi"]].to_string(index=False))

    sp = season_phase(d)
    print("\nSEASON PHASE (position inside each league's own season)")
    if not sp.empty:
        print(sp.pivot_table(index="phase", columns="target",
                             values=["challenger_logloss", "retraining_gain"]).round(5).to_string())

    ma = model_age(led)
    print("\nMODEL AGE — does a model decay while it sits?")
    if not ma.empty:
        print(ma.pivot_table(index="age_bucket", columns="target",
                             values="log_loss", observed=True).round(5).to_string())

    sc = scorecard(d, led)
    print("\nSCORECARD — first 6 months vs latest 6")
    print(sc[["variant", "target", "first6_logloss", "last6_logloss", "delta_logloss",
              "first6_margin", "last6_margin", "delta_margin"]].to_string(index=False))

    if a.write:
        lt.to_csv(O() / "league_target_comparison.csv", index=False)
        sp.to_csv(O() / "season_phase.csv", index=False)
        ma.to_csv(O() / "model_age.csv", index=False)
        sc.to_csv(O() / "learning_scorecard.csv", index=False)
        print(f"\n[breakdowns] wrote 4 artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
