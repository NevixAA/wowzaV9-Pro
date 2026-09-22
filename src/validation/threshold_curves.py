"""Per-league threshold curves — what edge bar would each league have needed?

    python -m src.validation.threshold_curves [--write]

THE QUESTION, and why it is the right one. Three leagues carry most of the O/U loss (USA MLS
-23.0u, League One -13.1u, League Two -11.6u). The tempting response is to stop betting them.
That is explicitly NOT the policy — "do not shut down any league, we are still learning" (Nevo,
2026-09-22), and v9's own live-test policy already says the same: every league is tracked live
this season including the losing ones, because a league you stopped collecting is a league you
can never learn about.

So the lever is the THRESHOLD, not the league list. This module asks, per cell: at what minimum
edge would this league have been worth betting, and does the record support moving its bar at
all?

INVARIANT 6 IS THE WHOLE DIFFICULTY. "No retrospective tuning" — the strategy is frozen before
the test. Picking the threshold that maximises ROI on the data you are judging it by is not
analysis, it is drawing the target around the arrow, and at these sample sizes it will always
find something. Every league here has 15-77 settled bets; the best of six thresholds on 20 bets
is noise with a confidence interval.

So the curve is built ONE WAY ONLY:

    fit window   = the earlier 60% of that cell's settled bets, chronologically
    test window  = the later 40%, which the choice never saw

The threshold is chosen on the fit window; what is REPORTED is what that choice then did on the
test window. A cell whose test window is too small to say anything returns INSUFFICIENT_DATA,
which is the honest answer for most of them and must be printed rather than smoothed away.

WHAT A VERDICT MEANS
  HIGHER            the fit window chose a bar above the current one AND it held up out of sample
  LOWER             likewise, below
  UNCHANGED         the chosen bar is the current one, or the change did not survive the test
  INSUFFICIENT_DATA not enough settled bets to fit and test honestly — the default, and expected
"""
from __future__ import annotations

import argparse
import glob

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
GRID = (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.5, 15.0)   # edge_pct points
MIN_FIT = 25
MIN_TEST = 15
MIN_BETS_AT_THRESHOLD = 5


def load() -> pd.DataFrame:
    fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / "settlements" / "dt=*" / "run=*.parquet")))
    if not fs:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d[d["result"].isin(["WIN", "LOSS"])].copy()
    for c in ("edge_pct", "pnl", "clv_pct"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce")
    d = d[d["edge_pct"].notna() & d["pnl"].notna() & d["match_date"].notna()]
    return d.sort_values("match_date").drop_duplicates(
        ["fixture_key", "model_type", "market", "side"], keep="first")


def _curve(g: pd.DataFrame) -> list[dict]:
    """ROI at each candidate threshold on one slice."""
    out = []
    for t in GRID:
        s = g[g["edge_pct"] >= t]
        if len(s) < MIN_BETS_AT_THRESHOLD:
            out.append({"threshold": t, "n": len(s), "roi": np.nan, "pnl": np.nan, "clv": np.nan})
            continue
        out.append({"threshold": t, "n": len(s), "roi": float(s["pnl"].mean()),
                    "pnl": float(s["pnl"].sum()),
                    "clv": float(s["clv_pct"].mean()) if s["clv_pct"].notna().any() else np.nan})
    return out


def study(d: pd.DataFrame, *, n_boot: int = 3000, seed: int = 53) -> tuple:
    rng = np.random.default_rng(seed)
    rows, curves = [], []
    for (mt, mk, lg), g in d.groupby(["model_type", "market", "league"]):
        if mt == "unknown":
            continue
        g = g.sort_values("match_date")
        cut = int(len(g) * 0.6)
        fit, test = g.iloc[:cut], g.iloc[cut:]

        for slice_name, sl in (("all", g), ("fit", fit), ("test", test)):
            for c in _curve(sl):
                curves.append({"model_type": mt, "market": mk, "league": lg,
                               "slice": slice_name, **c, "calc_version": CALC_VERSION})

        base = {"model_type": mt, "market": mk, "league": lg, "n_total": len(g),
                "n_fit": len(fit), "n_test": len(test),
                "roi_all": float(g["pnl"].mean()), "pnl_all": float(g["pnl"].sum()),
                "calc_version": CALC_VERSION}

        if len(fit) < MIN_FIT or len(test) < MIN_TEST:
            rows.append({**base, "verdict": "INSUFFICIENT_DATA", "chosen_threshold": np.nan,
                         "roi_test_at_chosen": np.nan, "roi_test_at_zero": np.nan,
                         "improvement_pp": np.nan, "holds_oos": False})
            continue

        fc = [c for c in _curve(fit) if not np.isnan(c["roi"])]
        if not fc:
            rows.append({**base, "verdict": "INSUFFICIENT_DATA", "chosen_threshold": np.nan,
                         "roi_test_at_chosen": np.nan, "roi_test_at_zero": np.nan,
                         "improvement_pp": np.nan, "holds_oos": False})
            continue

        chosen = max(fc, key=lambda c: c["roi"])["threshold"]
        t_sel = test[test["edge_pct"] >= chosen]
        t_all = test
        if len(t_sel) < MIN_BETS_AT_THRESHOLD:
            rows.append({**base, "verdict": "INSUFFICIENT_DATA", "chosen_threshold": chosen,
                         "roi_test_at_chosen": np.nan, "roi_test_at_zero": float(t_all["pnl"].mean()),
                         "improvement_pp": np.nan, "holds_oos": False})
            continue

        roi_sel, roi_base = float(t_sel["pnl"].mean()), float(t_all["pnl"].mean())
        # Did raising the bar actually help OUT OF SAMPLE? Bootstrap the difference.
        bs = (rng.choice(t_sel["pnl"].to_numpy(), size=(n_boot, len(t_sel)), replace=True).mean(axis=1)
              - rng.choice(t_all["pnl"].to_numpy(), size=(n_boot, len(t_all)), replace=True).mean(axis=1))
        lo, hi = np.percentile(bs, [2.5, 97.5])
        holds = bool(lo > 0)
        if not holds:
            verdict = "UNCHANGED"
        elif chosen > 4.0:
            verdict = "HIGHER"
        elif chosen < 4.0:
            verdict = "LOWER"
        else:
            verdict = "UNCHANGED"
        rows.append({**base, "verdict": verdict, "chosen_threshold": chosen,
                     "roi_test_at_chosen": roi_sel, "roi_test_at_zero": roi_base,
                     "improvement_pp": (roi_sel - roi_base) * 100,
                     "ci_lo": float(lo), "ci_hi": float(hi), "holds_oos": holds,
                     "n_test_at_chosen": len(t_sel)})
    return pd.DataFrame(rows), pd.DataFrame(curves)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=3000)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    d = load()
    if d.empty:
        print("[thresholds] no settled rows — nothing to curve")
        return 1
    print(f"[thresholds] {len(d):,} settled bets, {d.match_date.min().date()} .. "
          f"{d.match_date.max().date()}\n")

    verdicts, curves = study(d, n_boot=a.boot)

    print("=" * 104)
    print("PER-LEAGUE VERDICTS — threshold chosen on the earlier 60%, judged on the later 40%")
    print("=" * 104)
    print(f"  {'model':<11}{'mkt':<6}{'league':<26}{'n':>5}{'ROI all':>9}"
          f"{'chosen':>8}{'ROI@chosen':>12}{'vs base':>9}  verdict")
    for _, r in verdicts.sort_values("pnl_all").iterrows():
        ch = "—" if np.isnan(r["chosen_threshold"]) else f"{r['chosen_threshold']:.1f}%"
        rc = "—" if np.isnan(r.get("roi_test_at_chosen", np.nan)) else f"{r['roi_test_at_chosen']:+.3f}"
        im = "—" if np.isnan(r.get("improvement_pp", np.nan)) else f"{r['improvement_pp']:+.1f}pp"
        print(f"  {r['model_type']:<11}{r['market']:<6}{r['league']:<26}{int(r['n_total']):>5}"
              f"{r['roi_all']:>+9.3f}{ch:>8}{rc:>12}{im:>9}  {r['verdict']}")

    act = verdicts[verdicts["holds_oos"]] if "holds_oos" in verdicts.columns else verdicts.iloc[0:0]
    print(f"\n  cells where a threshold change SURVIVED out-of-sample: {len(act)} of {len(verdicts)}")
    if act.empty:
        print("  -> NO league's threshold change holds up. At 15-77 settled bets per league that")
        print("     is the expected answer, and it is the one invariant 6 exists to protect. Keep")
        print("     every league running and collecting; revisit when the cells are bigger.")

    print("\n" + "=" * 104)
    print("THE CURVES (full record — descriptive only, NOT a basis for choosing)")
    print("=" * 104)
    big = verdicts.nlargest(6, "n_total")[["model_type", "market", "league"]].values
    for mt, mk, lg in big:
        c = curves[(curves.model_type == mt) & (curves.market == mk)
                   & (curves.league == lg) & (curves.slice == "all")]
        cells = "  ".join(f"{r['threshold']:.0f}%:{r['roi']:+.2f}(n{int(r['n'])})"
                          for _, r in c.iterrows() if not np.isnan(r["roi"]))
        print(f"  {mt}/{mk}/{lg}\n     {cells}")

    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        verdicts.to_csv(cfg.OUTPUT_DIR / "threshold_verdicts.csv", index=False, encoding="utf-8")
        curves.to_csv(cfg.OUTPUT_DIR / "threshold_curves.csv", index=False, encoding="utf-8")
        print("\n[thresholds] wrote threshold_verdicts.csv + threshold_curves.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
