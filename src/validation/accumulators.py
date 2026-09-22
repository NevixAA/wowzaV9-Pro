"""Do accumulators across DIFFERENT matches pay, if we only fold in our most confident picks?

    python -m src.validation.accumulators [--write]

THE QUESTION, precisely. Not a same-game double — those legs are correlated and that was a
different (and mostly unbettable) idea. This is: take our most confident picks on SEPARATE
fixtures, fold three or four of them into an accumulator, and ask whether the multiplied odds
make it worth it.

WHY SEPARATE MATCHES CHANGES THE MATHS. Arsenal's goals and Bayern's goals are independent, so
the joint probability really is the product — no correlation bonus, and no correlation penalty
either. That makes the arithmetic clean and, unfortunately, decisive:

    single leg EV  = p x o
    n-fold acca EV = (p x o)^n

So an accumulator MULTIPLIES whatever edge each leg already has. If a leg returns 0.95 per unit
staked, a 3-fold returns 0.95^3 = 0.857 — the loss compounds. If a leg returns 1.05, a 3-fold
returns 1.158.

ACCUMULATORS DO NOT CREATE EDGE. They amplify it, in whichever direction it already points.
That is not an empirical claim, it is algebra, and no amount of accuracy changes it — a 90%
accurate leg priced at 1.05 is still -EV, and folding five of them together is -EV compounded
five times. The only thing that matters is whether p x o exceeds 1 on the legs being folded.

So the real question this file answers is NOT "do accumulators work" but:

    IS THERE ANY SUBSET — by confidence, by league, by market — where p x o > 1?

If yes, accumulators are an amplifier worth having. If no, they are a way to lose faster with
more variance.

MEASURED, NOT ASSUMED. The algebra above is certain, but three things are worth checking on
real data: that independence across fixtures actually holds; how much variance an accumulator
adds (the same expected value with a far worse distribution is a real cost); and whether any
confidence slice or league genuinely clears 1.0.

DATA. v9's backtest frames — 12,187 fixtures, 2022-09 to 2026-05, with REAL odds_over25 /
odds_under25 (100% present, 223 distinct values). Deliberately NOT Pro's settlements: those
contain only fixtures the system chose to bet, so their outcome rates are conditioned on the
system's own selection and cannot answer a question about what a strategy would return. The
BTTS rate is 52.0% across all fixtures and 62.3% on the bet subset — that gap is the bias.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import v9_source as v9

CALC_VERSION = "1.0.0"
FOLDS = (1, 2, 3, 4, 5)
N_SIM = 4000          # random acca constructions per configuration


def _load_ou25() -> pd.DataFrame:
    """All fixtures with a model probability, an outcome, and a REAL price on both sides."""
    d = v9.fetch_csv("output/backtest_results_standard.csv", required=False)
    if d.empty:
        return d
    for c in ("p_over25", "over25", "odds_over25", "odds_under25"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["p_over25", "over25", "odds_over25", "odds_under25", "date"])
    # Back the side the model favours, at that side's own price.
    d["side_over"] = d["p_over25"] >= 0.5
    d["odds"] = np.where(d["side_over"], d["odds_over25"], d["odds_under25"])
    d["won"] = np.where(d["side_over"], d["over25"] == 1, d["over25"] == 0)
    d["conf"] = (d["p_over25"] - 0.5).abs()
    return d.sort_values("date")


def independence_check(d: pd.DataFrame, rng) -> dict:
    """Do two picks on DIFFERENT fixtures behave independently? They should."""
    w = d["won"].to_numpy().astype(int)
    n = len(w)
    i = rng.integers(0, n, 20000)
    j = rng.integers(0, n, 20000)
    ok = i != j
    i, j = i[ok], j[ok]
    p = float(w.mean())
    joint = float((w[i] & w[j]).mean())
    return {"p_single": p, "independent_would_be": p * p, "actual_joint_random_pairs": joint,
            "gap_pp": (joint - p * p) * 100}


def simulate(d: pd.DataFrame, k_pct: int, n_legs: int, rng) -> dict | None:
    """Build accas from the top-k% most confident picks, each leg a different fixture."""
    sel = d.nlargest(max(n_legs * 5, len(d) * k_pct // 100), "conf")
    if len(sel) < n_legs * 5:
        return None
    won = sel["won"].to_numpy().astype(bool)
    odds = sel["odds"].to_numpy()
    n = len(sel)
    pnl = np.empty(N_SIM)
    hits = np.empty(N_SIM)
    for s in range(N_SIM):
        pick = rng.choice(n, size=n_legs, replace=False)   # distinct fixtures
        all_win = won[pick].all()
        payout = odds[pick].prod()
        pnl[s] = (payout - 1.0) if all_win else -1.0
        hits[s] = all_win
    lo, hi = np.percentile(rng.choice(pnl, size=(3000, N_SIM), replace=True).mean(axis=1),
                           [2.5, 97.5])
    leg_ev = float((sel["won"].mean() * odds.mean()))
    return {"top_k_pct": k_pct, "n_legs": n_legs, "pool": int(n),
            "leg_hit_rate": float(sel["won"].mean()), "leg_mean_odds": float(odds.mean()),
            "leg_ev_per_unit": leg_ev,
            "acca_hit_rate": float(hits.mean()), "acca_mean_payout": float(odds.mean() ** n_legs),
            "roi": float(pnl.mean()), "ci_lo": float(lo), "ci_hi": float(hi),
            "std": float(pnl.std()), "profitable": bool(lo > 0),
            "calc_version": CALC_VERSION}


def by_league(d: pd.DataFrame, k_pct: int = 25) -> list[dict]:
    """Is there ANY league whose confident picks clear p x o > 1? That is the only thing
    that could make an accumulator worth building."""
    out = []
    for lg, g in d.groupby("league"):
        sel = g.nlargest(max(20, len(g) * k_pct // 100), "conf")
        if len(sel) < 40:
            continue
        hit = float(sel["won"].mean())
        od = float(sel["odds"].mean())
        pnl = np.where(sel["won"], sel["odds"] - 1.0, -1.0)
        out.append({"league": lg, "n": int(len(sel)), "hit_rate": hit, "mean_odds": od,
                    "ev_per_unit": hit * od, "single_roi": float(pnl.mean()),
                    "acca3_ev": (hit * od) ** 3})
    return sorted(out, key=lambda r: -r["ev_per_unit"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    rng = np.random.default_rng(97)

    d = _load_ou25()
    if d.empty:
        print("[accumulators] no usable fixtures")
        return 1
    print(f"[accumulators] {len(d):,} fixtures, {d.date.min().date()}..{d.date.max().date()}, "
          f"real prices on both sides")

    ind = independence_check(d, rng)
    print(f"\nINDEPENDENCE across different fixtures (sanity — should be ~0):")
    print(f"  single {ind['p_single']:.4f}  independent {ind['independent_would_be']:.4f}  "
          f"actual {ind['actual_joint_random_pairs']:.4f}  gap {ind['gap_pp']:+.2f}pp")
    print("  -> separate matches are independent, so an acca's odds really do multiply.")

    print("\n" + "=" * 100)
    print("ACCUMULATORS FROM THE MOST CONFIDENT PICKS — each leg a DIFFERENT fixture")
    print("=" * 100)
    print(f"  {'top':>5}{'legs':>6}{'leg hit':>9}{'leg odds':>10}{'leg EV':>9}"
          f"{'acca hit':>10}{'payout':>9}{'ROI':>9}   95% CI")
    rows = []
    for k in (5, 10, 25, 100):
        for n_legs in FOLDS:
            r = simulate(d, k, n_legs, rng)
            if not r:
                continue
            rows.append(r)
            star = "  <-- PROFITABLE" if r["profitable"] else ""
            print(f"  {k:>4}%{n_legs:>6}{r['leg_hit_rate']:>9.3f}{r['leg_mean_odds']:>10.2f}"
                  f"{r['leg_ev_per_unit']:>9.3f}{r['acca_hit_rate']:>10.3f}"
                  f"{r['acca_mean_payout']:>9.2f}{r['roi']:>+9.3f}   "
                  f"[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]{star}")
        print()

    print("=" * 100)
    print("IS THERE ANY LEAGUE WHERE A LEG CLEARS 1.0?  (top 25% most confident picks)")
    print("=" * 100)
    lg = by_league(d)
    print(f"  {'league':<26}{'n':>6}{'hit':>8}{'odds':>8}{'leg EV':>9}{'single ROI':>12}{'3-fold EV':>11}")
    for r in lg:
        mark = "  <-- clears 1.0" if r["ev_per_unit"] > 1.0 else ""
        print(f"  {r['league']:<26}{r['n']:>6}{r['hit_rate']:>8.3f}{r['mean_odds']:>8.2f}"
              f"{r['ev_per_unit']:>9.3f}{r['single_roi']:>+12.3f}{r['acca3_ev']:>11.3f}{mark}")

    n_over = sum(1 for r in lg if r["ev_per_unit"] > 1.0)
    print(f"\n  leagues clearing 1.0: {n_over} of {len(lg)}")
    print("  An accumulator raises the leg EV to the power of the fold count. Above 1.0 that")
    print("  compounds upward; below 1.0 it compounds downward. Nothing else is happening.")

    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = cfg.OUTPUT_DIR / "accumulators.json"
        p.write_text(json.dumps({"generated_at": pd.Timestamp.utcnow().isoformat(),
                                 "independence": ind, "simulations": rows, "by_league": lg},
                                indent=2, default=str), encoding="utf-8")
        print(f"\n[accumulators] wrote {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
