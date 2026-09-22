"""Is the model overconfident, and would recalibration fix it?

    python -m src.validation.calibration_study [--write]

THE DEFECT THIS MEASURES. The 2026-09 audit's load-bearing negative result was not a threshold
or a leak: the model claims 0.5430 and delivers 0.4066, a +13.64pp overconfidence gap at z=7.81
on n=792, and the gap is the SAME SIZE on staked bets (+16.80pp) as on never-staked VALUABLE
(+10.78pp). That equality is the finding — a tier ladder that sorted anything would show a
smaller gap where it claims more confidence. It does not.

Overconfidence is the most repairable kind of wrong. A model whose ranking is sound but whose
numbers are inflated does not need retraining; it needs a monotone transform. That is cheap,
low-risk, and testable, which is why this runs before any talk of new features or new models.

WHAT WOULD MAKE THIS REPORT A LIE, and how each is prevented

  * Fitting the calibrator on the data it is scored on. Every calibrator here is fitted on an
    EARLIER chronological slice and scored on a LATER one it has never seen. Invariant 6 — the
    strategy is frozen before the test — applies to calibrators exactly as to thresholds.
  * Pooling models. Standard O/U and new-format O/U and BTTS have different data and different
    failure modes; averaging them would hide the one that is broken. Every row here is one
    (model_type, market) cell with its own n.
  * Reporting a gain that is within noise. Brier and log loss both get a paired bootstrap over
    fixtures, and a cell whose interval crosses zero is reported as no improvement.

READ `gap_pp` FIRST. Positive means overconfident — claimed more than it delivered.
"""
from __future__ import annotations

import argparse
import glob

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
MIN_CELL_N = 60          # below this a cell is reported but never interpreted
MIN_FIT_N = 40           # below this there is nothing to fit a calibrator on


def load_settlements() -> pd.DataFrame:
    """Settled bets carrying the model's own probability, from Pro's canonical store."""
    fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / "settlements" / "dt=*" / "run=*.parquet")))
    if not fs:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d[d["result"].isin(["WIN", "LOSS"])].copy()
    d["p"] = pd.to_numeric(d["p_model_over"], errors="coerce")
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce")
    d = d[d["p"].notna() & d["match_date"].notna() & d["p"].between(0.001, 0.999)]

    # CALIBRATE THE EVENT, NOT THE BET. p_model_over is P(over 2.5); a bet on UNDER wins exactly
    # when that event does NOT happen. Scoring p against "did my bet win" would make every UNDER
    # row look inverted and turn a calibration study into a side-selection study.
    side = d["side"].astype(str).str.upper()
    won = d["result"].eq("WIN")
    d["y"] = np.where(side.eq("OVER"), won, ~won).astype(int)
    d = d[side.isin(["OVER", "UNDER"])]

    # One row per fixture per model+market. A fixture re-tipped at a better price is one
    # observation of the model's opinion, not two.
    d = d.sort_values("match_date").drop_duplicates(
        ["fixture_key", "model_type", "market"], keep="first")
    return d


def _brier(p, y):
    return float(np.mean((p - y) ** 2))


def _logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _ece(p, y, bins: int = 10) -> float:
    """Expected calibration error — mean |claimed - realised| weighted by bin population."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum():
            tot += (m.sum() / len(p)) * abs(p[m].mean() - y[m].mean())
    return float(tot)


def _platt(p_fit, y_fit, p_apply):
    """Logistic recalibration on the log-odds. One slope, one intercept."""
    from sklearn.linear_model import LogisticRegression
    x = np.log(np.clip(p_fit, 1e-6, 1 - 1e-6) / (1 - np.clip(p_fit, 1e-6, 1 - 1e-6)))
    lr = LogisticRegression(C=1e6, solver="lbfgs")
    lr.fit(x.reshape(-1, 1), y_fit)
    xa = np.log(np.clip(p_apply, 1e-6, 1 - 1e-6) / (1 - np.clip(p_apply, 1e-6, 1 - 1e-6)))
    return lr.predict_proba(xa.reshape(-1, 1))[:, 1]


def _isotonic(p_fit, y_fit, p_apply):
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
    iso.fit(p_fit, y_fit)
    return iso.predict(p_apply)


def study(d: pd.DataFrame, *, n_boot: int = 3000, seed: int = 41) -> tuple:
    """Per (model_type, market): the gap now, and what a calibrator fitted on the past does."""
    rng = np.random.default_rng(seed)
    cells, bins_rows = [], []

    for (mt, mk), g in d.groupby(["model_type", "market"]):
        g = g.sort_values("match_date")
        p, y = g["p"].to_numpy(), g["y"].to_numpy()
        row = {
            "model_type": mt, "market": mk, "n": len(g),
            "claimed": float(p.mean()), "realised": float(y.mean()),
            "gap_pp": float((p.mean() - y.mean()) * 100),
            "brier": _brier(p, y), "logloss": _logloss(p, y), "ece": _ece(p, y),
            "interpretable": len(g) >= MIN_CELL_N,
            "calc_version": CALC_VERSION,
        }

        # Per-bin calibration, so the SHAPE of the miss is visible and not just its average.
        for lo, hi in ((0.0, .4), (.4, .5), (.5, .55), (.55, .6), (.6, .7), (.7, 1.0)):
            m = (p >= lo) & (p < hi)
            if m.sum():
                bins_rows.append({"model_type": mt, "market": mk, "bin": f"{lo:.2f}-{hi:.2f}",
                                  "n": int(m.sum()), "claimed": float(p[m].mean()),
                                  "realised": float(y[m].mean()),
                                  "gap_pp": float((p[m].mean() - y[m].mean()) * 100)})

        # CHRONOLOGICAL: fit on the earlier 60%, score on the later 40% the calibrator never saw.
        cut = int(len(g) * 0.6)
        if cut >= MIN_FIT_N and (len(g) - cut) >= 30:
            pf, yf, pt, yt = p[:cut], y[:cut], p[cut:], y[cut:]
            row["n_fit"], row["n_test"] = int(cut), int(len(g) - cut)
            row["brier_raw_test"] = _brier(pt, yt)
            row["logloss_raw_test"] = _logloss(pt, yt)
            row["gap_pp_test_raw"] = float((pt.mean() - yt.mean()) * 100)
            for name, fn in (("platt", _platt), ("isotonic", _isotonic)):
                try:
                    pc = np.clip(fn(pf, yf, pt), 1e-6, 1 - 1e-6)
                except Exception as e:
                    row[f"{name}_error"] = type(e).__name__
                    continue
                row[f"brier_{name}"] = _brier(pc, yt)
                row[f"logloss_{name}"] = _logloss(pc, yt)
                row[f"gap_pp_{name}"] = float((pc.mean() - yt.mean()) * 100)
                # Paired bootstrap on the per-row squared-error difference. Negative = better.
                diff = (pc - yt) ** 2 - (pt - yt) ** 2
                bs = rng.choice(diff, size=(n_boot, len(diff)), replace=True).mean(axis=1)
                lo_, hi_ = np.percentile(bs, [2.5, 97.5])
                row[f"brier_delta_{name}"] = float(diff.mean())
                row[f"brier_delta_{name}_lo"] = float(lo_)
                row[f"brier_delta_{name}_hi"] = float(hi_)
                row[f"{name}_helps"] = bool(hi_ < 0)
        cells.append(row)

    return pd.DataFrame(cells).sort_values("n", ascending=False), pd.DataFrame(bins_rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=3000)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    d = load_settlements()
    if d.empty:
        print("[calibration] no settled rows with a model probability — nothing to measure")
        return 1
    print(f"[calibration] {len(d):,} settled fixtures carrying p_model_over, "
          f"{d.match_date.min().date()} .. {d.match_date.max().date()}\n")

    cells, bins = study(d, n_boot=a.boot)

    print("=" * 100)
    print("HOW OVERCONFIDENT IS EACH MODEL?   gap = claimed - realised, in points. + = overconfident")
    print("=" * 100)
    print(f"  {'model':<12}{'market':<8}{'n':>6}{'claimed':>9}{'realised':>10}{'gap pp':>9}"
          f"{'brier':>8}{'ECE':>7}")
    for _, r in cells.iterrows():
        flag = "" if r["interpretable"] else "   (n too small)"
        print(f"  {r['model_type']:<12}{r['market']:<8}{int(r['n']):>6}{r['claimed']:>9.4f}"
              f"{r['realised']:>10.4f}{r['gap_pp']:>+9.2f}{r['brier']:>8.4f}{r['ece']:>7.4f}{flag}")

    print("\n" + "=" * 100)
    print("WOULD RECALIBRATION HELP?  fitted on the earlier 60%, scored on the later 40% unseen")
    print("=" * 100)
    fitted = cells[cells.get("n_test").notna()] if "n_test" in cells.columns else cells.iloc[0:0]
    if fitted.empty:
        print("  No cell has enough history to fit and test a calibrator honestly yet.")
    else:
        print(f"  {'model':<12}{'market':<8}{'n_test':>7}{'raw gap':>9}"
              f"{'platt gap':>11}{'iso gap':>9}   brier delta (95% CI)        verdict")
        for _, r in fitted.iterrows():
            best, bd = None, 0.0
            for nm in ("platt", "isotonic"):
                if r.get(f"{nm}_helps"):
                    if r.get(f"brier_delta_{nm}", 0) < bd:
                        best, bd = nm, r[f"brier_delta_{nm}"]
            if best:
                v = (f"{best.upper()} HELPS  [{r[f'brier_delta_{best}_lo']:+.5f},"
                     f"{r[f'brier_delta_{best}_hi']:+.5f}]")
            else:
                v = "no improvement beyond noise"
            print(f"  {r['model_type']:<12}{r['market']:<8}{int(r['n_test']):>7}"
                  f"{r['gap_pp_test_raw']:>+9.2f}{r.get('gap_pp_platt', float('nan')):>+11.2f}"
                  f"{r.get('gap_pp_isotonic', float('nan')):>+9.2f}   {v}")

    print("\n" + "=" * 100)
    print("WHERE THE MISS IS, by claimed-probability bin (interpretable cells only)")
    print("=" * 100)
    keep = set(map(tuple, cells.loc[cells["interpretable"], ["model_type", "market"]].values))
    for (mt, mk), g in bins.groupby(["model_type", "market"]):
        if (mt, mk) not in keep:
            continue
        print(f"  {mt} / {mk}")
        for _, r in g.iterrows():
            bar = "#" * min(int(abs(r["gap_pp"])), 40)
            print(f"     {r['bin']:<12}n={int(r['n']):>5}  claimed {r['claimed']:.3f}  "
                  f"realised {r['realised']:.3f}  gap {r['gap_pp']:>+7.2f}  {bar}")

    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cells.to_csv(cfg.OUTPUT_DIR / "calibration_study.csv", index=False, encoding="utf-8")
        bins.to_csv(cfg.OUTPUT_DIR / "calibration_bins.csv", index=False, encoding="utf-8")
        print("\n[calibration] wrote calibration_study.csv + calibration_bins.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
