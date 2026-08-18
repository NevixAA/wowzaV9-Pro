"""
Chronological four-block splits, and the leakage assertions that make them worth having.
========================================================================================
Prompt 1 section 1. This exists because of a confirmed defect in v9/src/model.py:235-249:

    meta_X = np.column_stack([results[n]["model"].predict_proba(X_test)[:,1] for n in results])
    meta_clf.fit(meta_X, y_test)
    meta_proba = meta_clf.predict_proba(meta_X)[:, 1]        # scored on its own training data
    log.info(f"meta_logistic auc={roc_auc_score(y_test, meta_proba)}")

with the comment "The test split was never seen by any base model, so there is no leakage".
That is true of the BASE models and irrelevant to the META model, which is fit on
(meta_X, y_test) and then evaluated on exactly those rows. Three separate problems:

  * the reported ensemble AUC is IN-SAMPLE, so it is a training-fit statistic;
  * the comment asserts a safety that does not hold, so a reader trusts the number;
  * there is NO final holdout at all — the split is three blocks and the last does triple
    duty as base-model eval, meta training set and meta eval.

That blend is also in v9's live predict path, so production probabilities come from weights
fitted on one small slice with zero validation.

FOUR blocks, strictly ordered in time, each used for exactly one purpose:

    |---- TRAIN ----|-- CALIBRATION --|-- META-TRAIN --|-- FINAL HOLDOUT --|
     base models     Platt/isotonic     meta learner     reported metrics
     fit here        fit here           fit here         ONLY read here

The final holdout is touched once, to report. Nothing is fitted on it, ever — no base model,
no calibrator, no meta learner, no threshold search. `assert_no_leakage` enforces the ordering
and `FinalHoldoutGuard` makes a second read of it a programming error rather than a habit.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


class LeakageError(AssertionError):
    """Raised when a split would let information travel backwards in time."""


@dataclass(frozen=True)
class Blocks:
    """Row indices for each block, plus the date boundaries that produced them."""
    train: np.ndarray
    calibration: np.ndarray
    meta_train: np.ndarray
    final_holdout: np.ndarray
    bounds: tuple[str, str, str, str, str]      # min, t/c, c/m, m/f, max

    @property
    def sizes(self) -> dict[str, int]:
        return {"train": len(self.train), "calibration": len(self.calibration),
                "meta_train": len(self.meta_train), "final_holdout": len(self.final_holdout)}

    def describe(self) -> str:
        b = self.bounds
        return (f"TRAIN {b[0]}..{b[1]} ({len(self.train)})  "
                f"CAL {b[1]}..{b[2]} ({len(self.calibration)})  "
                f"META {b[2]}..{b[3]} ({len(self.meta_train)})  "
                f"HOLDOUT {b[3]}..{b[4]} ({len(self.final_holdout)})")


def chronological_blocks(
    df: pd.DataFrame,
    *,
    date_col: str = "match_date",
    fractions: tuple[float, float, float, float] = (0.60, 0.15, 0.10, 0.15),
) -> Blocks:
    """Split by TIME, never by row shuffling.

    Fractions are of row count, not of the date range, so a busy month does not get more
    weight than a quiet one purely because it is busy. Boundaries are then snapped to date
    changes so a single fixture-date can never straddle two blocks — a match appearing in both
    TRAIN and CALIBRATION is leakage even if the rows differ.
    """
    if abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError(f"fractions must sum to 1.0, got {sum(fractions)}")
    if df.empty:
        raise ValueError("cannot split an empty frame")
    if date_col not in df.columns:
        raise ValueError(f"missing date column {date_col!r}")

    d = df.copy()
    d["_d"] = pd.to_datetime(d[date_col], errors="coerce")
    if d["_d"].isna().any():
        raise LeakageError(
            f"{int(d['_d'].isna().sum())} row(s) have an unparseable {date_col}. A row with no "
            f"date cannot be placed in time, and guessing puts future data in the past."
        )
    d = d.sort_values("_d", kind="mergesort")          # stable: ties keep input order
    n = len(d)

    # Cut points, then pushed forward to the next date change.
    raw = np.cumsum([int(round(f * n)) for f in fractions[:3]])
    dates = d["_d"].to_numpy()
    cuts = []
    for r in raw:
        r = min(max(int(r), 1), n - 1)
        while r < n and dates[r] == dates[r - 1]:
            r += 1                                     # do not split inside one fixture date
        cuts.append(min(r, n))
    c1, c2, c3 = cuts

    pos = d.index.to_numpy()
    blocks = Blocks(
        train=pos[:c1], calibration=pos[c1:c2], meta_train=pos[c2:c3],
        final_holdout=pos[c3:],
        bounds=(str(dates[0])[:10], str(dates[min(c1, n - 1)])[:10],
                str(dates[min(c2, n - 1)])[:10], str(dates[min(c3, n - 1)])[:10],
                str(dates[-1])[:10]),
    )
    assert_no_leakage(df, blocks, date_col=date_col)
    return blocks


def assert_no_leakage(df: pd.DataFrame, b: Blocks, *, date_col: str = "match_date") -> None:
    """Every block must be strictly later than the one before it, and disjoint.

    Checked on DATES, not indices: two blocks can be index-disjoint and still overlap in time,
    which is the leak that matters.
    """
    names = ["train", "calibration", "meta_train", "final_holdout"]
    idx = [b.train, b.calibration, b.meta_train, b.final_holdout]

    for name, i in zip(names, idx):
        if len(i) == 0:
            raise LeakageError(f"block {name!r} is empty — a four-block split needs all four")

    seen: set = set()
    for name, i in zip(names, idx):
        dup = seen.intersection(i.tolist())
        if dup:
            raise LeakageError(f"block {name!r} shares {len(dup)} row(s) with an earlier block")
        seen.update(i.tolist())

    d = pd.to_datetime(df[date_col], errors="coerce")
    for (n1, i1), (n2, i2) in zip(list(zip(names, idx))[:-1], list(zip(names, idx))[1:]):
        last, first = d.loc[i1].max(), d.loc[i2].min()
        if first < last:
            raise LeakageError(
                f"{n2} starts {first.date()} but {n1} runs to {last.date()} — later data would "
                f"be used to fit something evaluated on earlier data"
            )
        if first == last:
            raise LeakageError(
                f"{n1} and {n2} both contain {first.date()} — one fixture date cannot appear in "
                f"two blocks"
            )


class FinalHoldoutGuard:
    """Makes a second use of the final holdout a loud error.

    The holdout stops being a holdout the moment it is consulted twice: the first look reports
    a metric, the second look starts tuning against it. Nothing in the code prevents that, so
    this does.

        guard = FinalHoldoutGuard()
        y, p = guard.reveal(y_true, y_pred)     # allowed once
        guard.reveal(...)                       # HoldoutAlreadyUsed
    """

    class HoldoutAlreadyUsed(RuntimeError):
        pass

    def __init__(self, label: str = "final_holdout") -> None:
        self.label = label
        self._used = False

    @property
    def used(self) -> bool:
        return self._used

    def reveal(self, *arrays):
        if self._used:
            raise self.HoldoutAlreadyUsed(
                f"{self.label} has already been read once. Reading it again means tuning "
                f"against it, which makes every metric it produces optimistic. Use the "
                f"meta_train block for anything iterative."
            )
        self._used = True
        return arrays if len(arrays) != 1 else arrays[0]
