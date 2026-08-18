"""
Phase 3 validation layer. Covers the Prompt 1 required tests:
train/calibration/meta/final-holdout are chronological, and the meta model never trains on the
final holdout.

    python -m tests.test_validation
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.validation.market_relative import (auc, brier, compare, compare_by,  # noqa: E402
                                            ece, log_loss, sample_label)
from src.validation.multiple_testing import (benjamini_hochberg,  # noqa: E402
                                             bonferroni, paired_bootstrap_p)
from src.validation.splits import (Blocks, FinalHoldoutGuard,  # noqa: E402
                                   LeakageError, assert_no_leakage,
                                   chronological_blocks)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def frame(n=1000, start="2024-01-01"):
    d = pd.date_range(start, periods=n, freq="D")
    rng = np.random.default_rng(1)
    return pd.DataFrame({"match_date": d.astype(str), "y": rng.integers(0, 2, n)})


def main() -> int:
    print("\n== four chronological blocks ==")
    df = frame()
    b = chronological_blocks(df)
    check("all four blocks non-empty", all(v > 0 for v in b.sizes.values()), str(b.sizes))
    check("blocks partition the rows",
          sum(b.sizes.values()) == len(df), f"{sum(b.sizes.values())} vs {len(df)}")
    check("no row appears twice",
          len(set(b.train) | set(b.calibration) | set(b.meta_train) | set(b.final_holdout))
          == len(df))
    d = pd.to_datetime(df["match_date"])
    check("train ends before calibration starts",
          d.loc[b.train].max() < d.loc[b.calibration].min())
    check("calibration ends before meta starts",
          d.loc[b.calibration].max() < d.loc[b.meta_train].min())
    check("meta ends before the final holdout starts",
          d.loc[b.meta_train].max() < d.loc[b.final_holdout].min(),
          "this is the v9 defect: the meta model must never see the holdout")
    check("holdout is the LATEST data",
          d.loc[b.final_holdout].min() > d.loc[b.train].max())
    print(f"    {b.describe()}")

    print("\n== leakage is refused, not warned about ==")
    bad = Blocks(train=np.array([0, 5]), calibration=np.array([1]), meta_train=np.array([2]),
                 final_holdout=np.array([3]), bounds=("", "", "", "", ""))
    small = pd.DataFrame({"match_date": ["2024-01-01", "2024-01-02", "2024-01-03",
                                         "2024-01-04", "2024-01-05", "2024-06-01"],
                          "y": [0, 1, 0, 1, 0, 1]})
    try:
        assert_no_leakage(small, bad)
        check("a train block reaching past later blocks is rejected", False, "accepted")
    except LeakageError:
        check("a train block reaching past later blocks is rejected", True)

    overlap = Blocks(train=np.array([0, 1]), calibration=np.array([1, 2]),
                     meta_train=np.array([3]), final_holdout=np.array([4]),
                     bounds=("", "", "", "", ""))
    try:
        assert_no_leakage(small, overlap)
        check("shared rows between blocks rejected", False, "accepted")
    except LeakageError:
        check("shared rows between blocks rejected", True)

    empty = Blocks(train=np.array([0]), calibration=np.array([], dtype=int),
                   meta_train=np.array([2]), final_holdout=np.array([3]),
                   bounds=("", "", "", "", ""))
    try:
        assert_no_leakage(small, empty)
        check("an empty block is rejected", False, "accepted")
    except LeakageError:
        check("an empty block is rejected", True)

    print("\n== one fixture date cannot straddle two blocks ==")
    # 400 rows over only 8 distinct dates: naive fraction cuts would split a date.
    dup = pd.DataFrame({"match_date": np.repeat(
        pd.date_range("2024-01-01", periods=8, freq="7D").astype(str), 50), "y": 0})
    bd = chronological_blocks(dup)
    dd = pd.to_datetime(dup["match_date"])
    shared = set(dd.loc[bd.train]) & set(dd.loc[bd.calibration])
    check("no date in both train and calibration", not shared, str(shared))

    print("\n== bad dates are refused rather than guessed ==")
    nd = frame(50)
    nd.loc[10, "match_date"] = "not-a-date"
    try:
        chronological_blocks(nd)
        check("unparseable date rejected", False, "accepted")
    except LeakageError:
        check("unparseable date rejected", True)

    print("\n== the final holdout can be read once ==")
    g = FinalHoldoutGuard()
    g.reveal(np.array([1, 0]))
    check("first read allowed", g.used)
    try:
        g.reveal(np.array([1, 0]))
        check("second read refused", False, "allowed")
    except FinalHoldoutGuard.HoldoutAlreadyUsed:
        check("second read refused", True)

    print("\n== metrics behave ==")
    y = np.array([1, 1, 0, 0])
    check("perfect forecast -> brier 0", brier(y, [1, 1, 0, 0]) == 0.0)
    check("worst forecast -> brier 1", brier(y, [0, 0, 1, 1]) == 1.0)
    check("logloss punishes confident errors",
          log_loss(y, [0.01, 0.99, 0.01, 0.99]) > log_loss(y, [0.6, 0.6, 0.4, 0.4]))
    check("auc of a perfect ranker is 1", auc(y, [0.9, 0.8, 0.2, 0.1]) == 1.0)
    check("auc of a coin flip is 0.5", auc(y, [0.5, 0.5, 0.5, 0.5]) == 0.5)
    check("auc undefined with one class", auc([1, 1], [0.5, 0.6]) is None)
    check("ece 0 for a calibrated constant",
          abs(ece(np.array([1, 0, 1, 0]), np.array([0.5] * 4))) < 1e-9)

    print("\n== market-relative: the answer must be C vs B ==")
    rng = np.random.default_rng(3)
    n = 2000
    truth = rng.random(n)
    yy = (rng.random(n) < truth).astype(int)
    mk = np.clip(truth + rng.normal(0, 0.06, n), 0.02, 0.98)      # market: good
    useless = np.clip(rng.random(n), 0.02, 0.98)                  # model: noise
    c = compare(yy, mk, useless, weight=0.30)
    check("a noise model does NOT improve on the market",
          c.logloss_improvement < 0 and c.verdict == "MARKET_DOMINATES",
          f"{c.logloss_improvement} {c.verdict}")

    informative = np.clip(truth + rng.normal(0, 0.05, n), 0.02, 0.98)
    c2 = compare(yy, mk, informative, weight=0.30)
    check("a genuinely informative model DOES improve on the market",
          c2.logloss_improvement > 0 and c2.brier_improvement > 0,
          f"{c2.logloss_improvement} {c2.verdict}")
    check("verdict recorded", c2.verdict.startswith("MODEL_ADDS_INFORMATION"), c2.verdict)

    print("\n== sample-size honesty ==")
    check("tiny n -> INSUFFICIENT_SAMPLE", sample_label(10) == "INSUFFICIENT_SAMPLE")
    check("100 -> EARLY_SIGNAL", sample_label(100) == "EARLY_SIGNAL")
    check("500 -> RESEARCH_ONLY", sample_label(500) == "RESEARCH_ONLY")
    check("5000 -> VALIDATED", sample_label(5000) == "VALIDATED")
    tiny = compare(yy[:30], mk[:30], informative[:30])
    check("a tiny sample cannot claim a discovery",
          tiny.verdict == "INSUFFICIENT_SAMPLE", tiny.verdict)

    print("\n== per-segment reporting ==")
    seg = pd.DataFrame({"y": yy, "m": mk, "o": informative,
                        "league": rng.choice(["A", "B", "C"], n)})
    res = compare_by(seg, y_col="y", market_col="m", model_col="o", by="league", weight=0.30)
    check("overall plus one row per segment", len(res) == 4, str(len(res)))
    check("every row carries n and a label",
          res["n"].notna().all() and res["sample_label"].notna().all())

    print("\n== multiple testing ==")
    ps = [0.001, 0.008, 0.02, 0.04, 0.2, 0.5, 0.9]
    bh = benjamini_hochberg(ps, q=0.05)
    check("BH keeps input order and length", len(bh) == len(ps))
    check("BH is less strict than Bonferroni",
          int(bh["significant"].sum()) >= int(bonferroni(ps)["significant"].sum()))
    check("adjusted p is monotone in raw p",
          bool((np.diff(bh.sort_values("p_raw")["p_adjusted"].to_numpy()) >= -1e-12).all()))
    check("hypothesis count persisted", int(bh["n_hypotheses"].iloc[0]) == len(ps))
    noise = benjamini_hochberg(list(np.linspace(0.05, 0.99, 200)), q=0.05)
    check("200 pure-noise segments yield no discoveries",
          int(noise["significant"].sum()) == 0, str(int(noise["significant"].sum())))
    nan_in = benjamini_hochberg([0.01, float("nan"), 0.4])
    check("NaN p carried through as not significant",
          len(nan_in) == 3 and not bool(nan_in["significant"].iloc[1]))

    print("\n== paired bootstrap ==")
    la = rng.normal(0.50, 0.10, 1500)
    lb = la + rng.normal(0.03, 0.10, 1500)      # b genuinely worse
    p, diff, ci = paired_bootstrap_p(la, lb, n_boot=2000, block=5)
    check("detects a real difference", p < 0.05, f"p={p}")
    check("difference sign says a is better", diff > 0, str(diff))
    check("CI excludes zero", ci[0] > 0, str(ci))
    p2, d2, _ = paired_bootstrap_p(la, la.copy(), n_boot=2000)
    check("identical losses -> no difference", abs(d2) < 1e-12 and p2 > 0.5, f"p={p2}")

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
