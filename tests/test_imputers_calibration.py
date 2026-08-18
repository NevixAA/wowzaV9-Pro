"""
Phase 3 remainder. Covers the Prompt 1 required test "inference imputation uses training
stats", plus the shrinkage property that stops tiny-sample league corrections doing harm.

    python -m tests.test_imputers_calibration
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.features.imputers import (apply_imputer, batch_median_would_differ,  # noqa: E402
                                   fit_imputer, ImputerManifest)
from src.models.calibration import (CalibrationModel, calibration_table,  # noqa: E402
                                    fit_calibration)
from src.validation.market_relative import brier, log_loss  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def main() -> int:
    print("\n== imputation uses TRAINING stats, not the batch ==")
    train = pd.DataFrame({
        "match_date": pd.date_range("2025-01-01", periods=100).astype(str),
        "form": np.r_[np.full(50, 1.0), np.full(50, 3.0)],       # training median 2.0
        "shots": np.linspace(0, 10, 100),
    })
    man = fit_imputer(train, ["form", "shots"], required=["form"])
    check("training median captured", man.features["form"].median == 2.0,
          str(man.features["form"].median))
    check("quantiles captured", man.features["shots"].q95 is not None)
    check("missing rate captured", man.features["form"].missing_rate == 0.0)
    check("fitted row count recorded", man.fitted_on_rows == 100)

    # A serving batch whose own median is far from training's.
    serve = pd.DataFrame({"form": [99.0, 99.0, np.nan, 99.0], "shots": [1, 2, 3, 4]})
    out, degraded, rep = apply_imputer(serve, man)
    filled = out.loc[2, "form"]
    check("gap filled from TRAINING median (2.0), not batch median (99)",
          filled == 2.0, str(filled))
    check("imputation counted", rep.imputed_counts.get("form") == 1)

    print("\n== out-of-range serving values are clipped to the training range ==")
    check("99 clipped down to the training max (3.0)",
          out.loc[0, "form"] == 3.0, str(out.loc[0, "form"]))

    print("\n== a row missing a REQUIRED feature is flagged, not silently scored ==")
    check("the imputed row is flagged degraded", bool(degraded.loc[2]), str(degraded.tolist()))
    check("rows with the feature present are not flagged", not bool(degraded.loc[0]))
    check("degraded count reported", rep.degraded_rows == 1, str(rep.degraded_rows))
    check("which required feature was missing is recorded",
          rep.missing_required.get("form") == 1, str(rep.missing_required))
    check("the row is RETAINED, not dropped", len(out) == len(serve),
          "Prompt 2 forbids dropping observations")

    print("\n== a declared feature absent entirely at serving ==")
    out2, deg2, rep2 = apply_imputer(pd.DataFrame({"shots": [1, 2]}), man)
    check("absent feature reported", "form" in rep2.unknown_features, str(rep2.unknown_features))
    check("every row degraded when a required feature is absent",
          rep2.degraded_rows == 2, str(rep2.degraded_rows))
    check("column still created so the matrix is complete", "form" in out2.columns)

    print("\n== the manifest round-trips ==")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "imp.json"
        man.to_json(p)
        back = ImputerManifest.from_json(p)
        check("median survives serialisation",
              back.features["form"].median == man.features["form"].median)
        check("required flag survives", back.features["form"].required is True)
        o2, _, _ = apply_imputer(serve, back)
        check("reloaded manifest imputes identically", o2.loc[2, "form"] == 2.0)

    print("\n== the diagnostic shows what batch imputation would have cost ==")
    diff = batch_median_would_differ(serve, man)
    check("gap between batch and training median surfaced", len(diff) > 0)
    check("the worst offender is named",
          diff.iloc[0]["feature"] == "form", str(diff.iloc[0].to_dict()))

    print("\n== calibration: global fit improves a miscalibrated model ==")
    rng = np.random.default_rng(11)
    n = 4000
    truth = rng.random(n)
    y = (rng.random(n) < truth).astype(int)
    # Systematically overconfident: pushed away from 0.5.
    p_bad = np.clip(0.5 + (truth - 0.5) * 1.8, 0.01, 0.99)
    cal = pd.DataFrame({"y": y, "p": p_bad, "league": rng.choice(["A", "B"], n),
                        "match_date": pd.date_range("2025-01-01", periods=n, freq="h").astype(str)})
    m = fit_calibration(cal, y_col="y", p_col="p", league_col=None)
    p_cal = m.apply(p_bad)
    check("log loss improves after calibration",
          log_loss(y, p_cal) < log_loss(y, p_bad),
          f"{log_loss(y, p_cal):.4f} vs {log_loss(y, p_bad):.4f}")
    check("brier improves after calibration", brier(y, p_cal) < brier(y, p_bad))

    print("\n== a tiny league is SHRUNK toward global, not fitted freely ==")
    big = pd.DataFrame({"y": y[:3000], "p": p_bad[:3000], "league": "BIG",
                        "match_date": cal["match_date"][:3000]})
    tiny = pd.DataFrame({"y": [1, 0, 1, 0, 1, 1, 0, 1], "p": [0.9] * 8, "league": "TINY",
                         "match_date": cal["match_date"][:8]})
    m2 = fit_calibration(pd.concat([big, tiny], ignore_index=True),
                         y_col="y", p_col="p", league_col="league")
    lt, lb = m2.leagues["TINY"], m2.leagues["BIG"]
    check("tiny league gets a small shrink weight", lt.shrink_weight < 0.05,
          str(lt.shrink_weight))
    check("tiny league is labelled as shrunk", lt.label == "SHRUNK_TO_GLOBAL", lt.label)
    check("tiny league's APPLIED params are near global",
          abs(lt.a - m2.a_global) < abs(lt.a_raw - m2.a_global) or lt.a_raw == m2.a_global,
          f"applied={lt.a:.4f} raw={lt.a_raw:.4f} global={m2.a_global:.4f}")
    check("big league is trusted more than the tiny one",
          lb.shrink_weight > lt.shrink_weight, f"{lb.shrink_weight} vs {lt.shrink_weight}")

    print("\n== single-class league cannot produce a runaway fit ==")
    one = pd.DataFrame({"y": [1, 1, 1, 1], "p": [0.6] * 4, "league": "ONECLASS",
                        "match_date": cal["match_date"][:4]})
    m3 = fit_calibration(pd.concat([big, one], ignore_index=True),
                         y_col="y", p_col="p", league_col="league")
    oc = m3.leagues["ONECLASS"]
    check("single-class league uses global params exactly",
          oc.a == m3.a_global and oc.b == m3.b_global, str(oc))

    print("\n== unseen league falls back to global ==")
    got = m2.apply([0.7], league=["NEVER_SEEN"])
    want = m2.apply([0.7])
    check("unseen league gets the global calibration", abs(got[0] - want[0]) < 1e-12)

    print("\n== calibration round-trips and is auditable ==")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cal.json"
        m2.to_json(p)
        b2 = CalibrationModel.from_json(p)
        check("params survive serialisation",
              abs(b2.a_global - m2.a_global) < 1e-12
              and b2.leagues["TINY"].shrink_weight == lt.shrink_weight)
    tbl = calibration_table(m2)
    check("table shows raw vs applied per league",
          {"a_raw", "a", "shrink_weight", "n"} <= set(tbl.columns))
    check("global row present", "__global__" in set(tbl["league"]))

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
