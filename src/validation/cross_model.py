"""Cross-model correlation study — does requiring two models to AGREE help?

    python -m src.validation.cross_model [--write] [--min-n 20]

WHAT THIS IS FOR

Every model in the estate is trained and backtested SEPARATELY, and that does not change: a
standard O/U 2.5 model and a BTTS model are different populations with different data
constraints, and pooling their results hides more than it reveals (invariant 1). This module
asks a question that only exists ACROSS models, on the settled record:

    when two models both fire on the same fixture, does that tell you anything
    you could not have got from either one alone?

Three ways the answer can be "no", and all three are common:

  * They rarely co-occur. A pair that overlaps on eleven fixtures has nothing to say, however
    good the eleven look.
  * They co-occur but their ERRORS are correlated. Two models that are wrong on the same
    fixtures do not diversify anything; requiring agreement just bets less on the same view.
  * They co-occur, errors are independent, and agreement still does not pay — because the
    filter throws away good bets along with bad ones.

WHAT IT DELIBERATELY DOES NOT DO

It does not build a blended model, tune a weight, or propose a combined tier. It measures
whether the raw material for one exists. Building the blend first and measuring afterwards is
how the estate ended up with an `over15` market certified on invented prices.

It also does not pool. Every row is one ORDERED pair on its own sample with its own n, and n is
printed beside every number. `A_given_B` and `B_given_A` are different questions — "how does
BTTS do on fixtures where O/U also fired" is not "how does O/U do where BTTS also fired",
because the two models fire on different numbers of fixtures.

MULTIPLICITY IS THE MAIN RISK HERE

Six models make thirty ordered pairs. At alpha=0.05 roughly one and a half will look
significant on noise alone, and the tempting reading — "look, THIS pair works" — is exactly the
false discovery this estate has already paid for twice. So every p-value goes through
Benjamini-Hochberg jointly (`src/validation/multiple_testing.benjamini_hochberg`) and the
`bh_significant` column, not the raw p, is the one to read. The count of hypotheses tested is
recorded in the output so a later reader can re-derive the correction.
"""
from __future__ import annotations

import argparse
from itertools import permutations

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import v9_source as v9
from src.validation.multiple_testing import benjamini_hochberg

# Tiers that represent an actual opinion. VALUABLE is included because it is a real tracked
# position even though it is not individually alerted; AVOID and NO_PRICE are not opinions.
OPINION_TIERS = ("SNIPER", "MARKSMAN", "VALUABLE")

# Below this many co-fired settled fixtures a pair is reported but never interpreted. Chosen to
# be visibly too small rather than quietly too small.
MIN_PAIR_N = 20

CALC_VERSION = "1.0.0"


def _fixture_key(d: pd.DataFrame) -> pd.Series:
    """League + UTC date + both teams. The ledgers carry no fixture_id, so this is the join."""
    return (d["league"].astype(str).str.strip() + "|"
            + d["match_date"].astype(str).str[:10] + "|"
            + d["home_team"].astype(str).str.strip() + "|"
            + d["away_team"].astype(str).str.strip())


def _norm(d: pd.DataFrame, model: str, *, tier_col: str = "signal_tier") -> pd.DataFrame:
    """Reduce one ledger to the six columns this study needs."""
    if d.empty:
        return pd.DataFrame()
    need = {"league", "match_date", "home_team", "away_team", "result", "pnl"}
    if not need.issubset(d.columns):
        return pd.DataFrame()
    out = pd.DataFrame({
        "fixture_key": _fixture_key(d),
        "model": model,
        "tier": d.get(tier_col, pd.Series("", index=d.index)).astype(str),
        "pnl": pd.to_numeric(d["pnl"], errors="coerce"),
        "result": d["result"].astype(str),
        "league": d["league"].astype(str),
        "match_date": pd.to_datetime(d["match_date"], errors="coerce"),
    })
    if "source" in d.columns:
        out = out[d["source"].astype(str).values == "live"]
    # Settled only, and an actual opinion only.
    out = out[out["result"].isin(["WIN", "LOSS"]) & out["pnl"].notna()
              & out["tier"].isin(OPINION_TIERS)]
    # One row per fixture per model. A model can appear twice on a fixture (two markets, or a
    # re-tip); keep the FIRST by date so the unit stays "this model's opinion on this fixture".
    return out.sort_values("match_date").drop_duplicates(["fixture_key", "model"], keep="first")


def load_models(*, cutoff: str | None = None) -> pd.DataFrame:
    """All models' settled opinions, one row per (fixture, model)."""
    cutoff = cutoff or str(getattr(cfg, "PERFORMANCE_CUTOFF_DATE", "2026-08-10"))
    frames: list[pd.DataFrame] = []

    main = v9.fetch_csv("output/bets_ledger.csv", required=False)
    if not main.empty:
        # Split the main ledger by TRACK — standard and new-format are different models and
        # must never be one row type here (invariant 1).
        mt = main.get("model_type", pd.Series("", index=main.index)).astype(str).str.strip()
        blank = mt.isin(["", "nan", "None"])
        if blank.any() and "league" in main.columns:
            try:
                import config as v9cfg  # v9's own config, if importable
                mt = mt.mask(blank, main.loc[:, "league"].map(v9cfg.model_type_for_league))
            except Exception:
                pass
        for track, label in (("standard", "ou25_standard"), ("new_format", "ou25_newformat")):
            frames.append(_norm(main[mt.values == track], label))

    side = v9.fetch_csv("output/side_bets_ledger.csv", required=False)
    if not side.empty and "market" in side.columns:
        for mk in sorted(side["market"].dropna().astype(str).unique()):
            frames.append(_norm(side[side["market"].astype(str) == mk], mk))

    for rel, label in (("output/ht_ledger.csv", "ht"),
                       ("output/sharp_ledger.csv", "sharp")):
        f = v9.fetch_csv(rel, required=False)
        if not f.empty:
            frames.append(_norm(f, label))

    all_ = [f for f in frames if not f.empty]
    if not all_:
        return pd.DataFrame()
    d = pd.concat(all_, ignore_index=True)
    return d[d["match_date"] >= pd.Timestamp(cutoff)]


def _phi(a: np.ndarray, b: np.ndarray) -> float:
    """Matthews/phi correlation between two win-indicator vectors.

    This is the number that says whether agreement DIVERSIFIES. Near zero means the two models
    are wrong on different fixtures, which is what makes combining them worth anything. Near +1
    means they are wrong on the same fixtures and a combination is one view wearing two names.
    """
    if len(a) < 4 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a.astype(float), b.astype(float))[0, 1])


def pair_table(d: pd.DataFrame, *, min_n: int = MIN_PAIR_N,
               n_boot: int = 4000, seed: int = 29) -> pd.DataFrame:
    """One row per ORDERED pair: how model A did on fixtures where B also fired."""
    rng = np.random.default_rng(seed)
    models = sorted(d["model"].unique())
    by = {m: g.set_index("fixture_key") for m, g in d.groupby("model")}
    rows = []
    for a, b in permutations(models, 2):
        ga, gb = by[a], by[b]
        both = ga.index.intersection(gb.index)
        a_all = ga["pnl"].to_numpy()
        a_both = ga.loc[both, "pnl"].to_numpy()
        a_alone = ga.loc[ga.index.difference(both), "pnl"].to_numpy()

        # Does B's agreement change A's outcome? Unpaired bootstrap on the difference of means,
        # because the two subsets are different fixtures.
        p = float("nan")
        if len(a_both) >= 8 and len(a_alone) >= 8:
            obs = a_both.mean() - a_alone.mean()
            pool = np.concatenate([a_both, a_alone])
            n1 = len(a_both)
            draws = np.empty(n_boot)
            for i in range(n_boot):
                s = rng.permutation(pool)
                draws[i] = s[:n1].mean() - s[n1:].mean()
            p = float((np.abs(draws) >= abs(obs)).mean())

        lo = hi = float("nan")
        if len(a_both) >= 8:
            bs = rng.choice(a_both, size=(n_boot, len(a_both)), replace=True).mean(axis=1)
            lo, hi = np.percentile(bs, [2.5, 97.5])

        rows.append({
            "model_a": a, "model_b": b,
            "n_a_total": len(a_all),
            "n_both": len(both),
            "n_a_alone": len(a_alone),
            "roi_a_overall": a_all.mean() if len(a_all) else np.nan,
            "roi_a_when_b_fired": a_both.mean() if len(a_both) else np.nan,
            "roi_a_when_b_silent": a_alone.mean() if len(a_alone) else np.nan,
            "lift_pp": (a_both.mean() - a_alone.mean()) * 100
                       if len(a_both) and len(a_alone) else np.nan,
            "ci_lo_roi_both": lo, "ci_hi_roi_both": hi,
            "error_corr_phi": _phi((ga.loc[both, "pnl"].to_numpy() > 0),
                                   (gb.loc[both, "pnl"].to_numpy() > 0)) if len(both) else np.nan,
            "pnl_a_when_b_fired": a_both.sum() if len(a_both) else 0.0,
            "p_value": p,
            "interpretable": len(both) >= min_n,
            "calc_version": CALC_VERSION,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    # Joint correction over every pair actually testable. This is the guard against reading the
    # best of thirty comparisons as a discovery.
    testable = out["p_value"].notna() & out["interpretable"]
    out["bh_significant"] = False
    out["bh_q"] = np.nan
    if testable.any():
        bh = benjamini_hochberg(out.loc[testable, "p_value"].to_numpy(), q=0.05)
        col = "significant" if "significant" in bh.columns else bh.columns[-1]
        out.loc[testable, "bh_significant"] = bh[col].to_numpy()
        if "q_value" in bh.columns:
            out.loc[testable, "bh_q"] = bh["q_value"].to_numpy()
    out["n_hypotheses"] = int(testable.sum())
    return out.sort_values("lift_pp", ascending=False, na_position="last")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=MIN_PAIR_N)
    ap.add_argument("--boot", type=int, default=4000)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    d = load_models()
    if d.empty:
        print("[cross_model] no settled opinions found in any ledger — nothing to correlate")
        return 1

    print("=" * 96)
    print("PER-MODEL BASELINE (each model on its own — never pooled)")
    print("=" * 96)
    print(f"  {'model':<18}{'fixtures':>9}{'win%':>8}{'P/L':>10}{'ROI':>9}")
    for m, g in d.groupby("model"):
        print(f"  {m:<18}{len(g):>9}{100 * (g.pnl > 0).mean():>7.1f}%"
              f"{g.pnl.sum():>+10.2f}{g.pnl.mean():>+9.3f}")
    print(f"\n  fixtures carrying >=2 models' opinions: "
          f"{int((d.groupby('fixture_key')['model'].nunique() >= 2).sum())}")

    t = pair_table(d, min_n=a.min_n, n_boot=a.boot)
    if t.empty:
        print("[cross_model] no pairs to report")
        return 1

    print("\n" + "=" * 96)
    print("DOES AGREEMENT HELP?  'A when B also fired' vs 'A when B stayed silent'")
    print("=" * 96)
    show = t[t["interpretable"]]
    if show.empty:
        print(f"  NOTHING INTERPRETABLE: no ordered pair reaches {a.min_n} co-fired settled")
        print(f"  fixtures. That is the finding — the models barely overlap, so there is no")
        print(f"  cross-model signal to mine yet. Below is the full table anyway, unread.")
        show = t.head(12)
    print(f"  {'A':<17}{'B':<17}{'n_both':>7}{'ROI both':>10}{'ROI alone':>11}"
          f"{'lift pp':>9}{'phi':>7}{'p':>7}  BH")
    for _, r in show.head(20).iterrows():
        bh = "YES" if r.get("bh_significant") else ""
        print(f"  {r['model_a']:<17}{r['model_b']:<17}{int(r['n_both']):>7}"
              f"{r['roi_a_when_b_fired']:>+10.3f}{r['roi_a_when_b_silent']:>+11.3f}"
              f"{r['lift_pp']:>+9.1f}{r['error_corr_phi']:>+7.2f}{r['p_value']:>7.3f}  {bh}")

    n_sig = int(t["bh_significant"].sum())
    print(f"\n  hypotheses tested jointly: {int(t['n_hypotheses'].iloc[0])}   "
          f"surviving Benjamini-Hochberg at q=0.05: {n_sig}")
    if n_sig == 0:
        print("  -> NO PAIR SURVIVES CORRECTION. Requiring two models to agree is not currently")
        print("     supported by the record. Read the raw p-values as noise, not as candidates.")

    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = cfg.OUTPUT_DIR / "cross_model_correlation.csv"
        t.to_csv(p, index=False, encoding="utf-8")
        print(f"\n[cross_model] wrote {p.name} ({len(t)} ordered pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
