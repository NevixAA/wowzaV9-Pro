"""Rolling chronological folds, and the model wrappers that get fitted inside them.

WHY ROLLING AND NOT ONE SPLIT. A single train/test cut gives one number, and one number cannot
distinguish "this model is better" from "this model got a good year". Rule 33: a model that wins
one fold and loses three is not better. So every experiment here runs several folds, each
training on everything before a date and testing on the window after it, and a result has to
survive most of them to count.

THE SHAPE OF ONE FOLD:

    |<---------------- TRAIN ---------------->|<- VAL ->|<-- TEST -->|
    oldest                                              T           T+w

TRAIN fits the model. VAL is the last slice of the pre-T data and is where the decision
threshold and any calibration are chosen. TEST is never touched until the numbers are final.
This is what makes rule 15 structural rather than a promise: `choose_threshold` is only ever
handed validation indices, so there is no code path in which the test period can tune anything.

PREPROCESSING IS FITTED ON TRAIN ONLY (rule 23). Median imputation for the linear models uses
the training medians, reused verbatim on validation and test. Computing a median over the whole
column -- the natural, wrong thing -- leaks the test period's distribution into the fit.

THE MODEL ZOO. HistGradientBoosting and LightGBM take NaN natively, which matters enormously
here: a standard-format league genuinely has no card data, and imputing a zero would tell the
model "no cards were shown". The linear and forest models cannot, so they get a train-fitted
median and are reported knowing that handicap.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CALC_VERSION = "1.0.0"
DEFAULT_N_FOLDS = 4
VAL_FRACTION = 0.15          # of the pre-T rows, taken from the END of that period


@dataclass
class Fold:
    name: str
    train: np.ndarray
    val: np.ndarray
    test: np.ndarray
    t_start: str
    t_end: str

    def describe(self) -> str:
        return (f"{self.name}: train {len(self.train):,} / val {len(self.val):,} / "
                f"test {len(self.test):,}  [{self.t_start} .. {self.t_end}]")


def rolling_folds(df: pd.DataFrame, *, date_col: str = "date", n_folds: int = DEFAULT_N_FOLDS,
                  min_train: int = 4000) -> list[Fold]:
    """Expanding-window folds. Fold k trains on all data before T_k and tests on [T_k, T_k+1).

    Boundaries are snapped to date changes so one fixture-date can never straddle two blocks --
    a match in both TRAIN and TEST is leakage even though the rows differ.
    """
    d = pd.to_datetime(df[date_col])
    order = np.argsort(d.to_numpy(), kind="mergesort")
    dates = d.to_numpy()[order]
    n = len(order)
    if n < min_train + 500:
        raise ValueError(f"only {n} rows; need at least {min_train + 500}")

    starts = np.linspace(max(min_train, int(n * 0.45)), int(n * 0.90), n_folds + 1).astype(int)
    folds = []
    for k in range(n_folds):
        c0, c1 = int(starts[k]), int(starts[k + 1])
        while c0 < n and dates[c0] == dates[c0 - 1]:
            c0 += 1
        while c1 < n and dates[c1] == dates[c1 - 1]:
            c1 += 1
        if c1 - c0 < 200:
            continue
        pre = order[:c0]
        v = max(1, int(len(pre) * VAL_FRACTION))
        cut = len(pre) - v
        while cut > 1 and dates[cut] == dates[cut - 1]:
            cut -= 1
        folds.append(Fold(name=f"fold{k + 1}", train=pre[:cut], val=pre[cut:],
                          test=order[c0:c1],
                          t_start=str(pd.Timestamp(dates[c0]).date()),
                          t_end=str(pd.Timestamp(dates[c1 - 1]).date())))
    _assert_chronological(d.to_numpy(), folds)
    return folds


def _assert_chronological(dates: np.ndarray, folds: list[Fold]) -> None:
    """Loud failure beats a quiet leak. Every train/val date must precede every test date."""
    for f in folds:
        if len(f.test) == 0 or len(f.train) == 0:
            raise ValueError(f"{f.name} has an empty block")
        if dates[f.train].max() >= dates[f.test].min():
            raise AssertionError(f"{f.name}: train overlaps test in time")
        if len(f.val) and dates[f.val].max() >= dates[f.test].min():
            raise AssertionError(f"{f.name}: validation overlaps test in time")
        if len(f.val) and dates[f.train].max() > dates[f.val].min():
            raise AssertionError(f"{f.name}: train runs past the start of validation")


# ---------------------------------------------------------------------------------------------
# Model zoo
# ---------------------------------------------------------------------------------------------

class _Imputed:
    """Wrap a model that cannot take NaN. Medians come from TRAIN and are reused everywhere."""

    def __init__(self, est, scale: bool = False):
        self.est = est
        self.scale = scale
        self.med_: np.ndarray | None = None
        self.mu_: np.ndarray | None = None
        self.sd_: np.ndarray | None = None

    def fit(self, X, y, sample_weight=None):
        X = np.asarray(X, dtype=float)
        self.med_ = np.nanmedian(X, axis=0)
        self.med_ = np.where(np.isfinite(self.med_), self.med_, 0.0)
        Z = self._apply(X, fit=True)
        try:
            self.est.fit(Z, y, sample_weight=sample_weight)
        except TypeError:
            self.est.fit(Z, y)
        return self

    def _apply(self, X, *, fit: bool = False):
        Z = np.where(np.isfinite(X), X, self.med_)
        if self.scale:
            if fit:
                self.mu_ = Z.mean(axis=0)
                self.sd_ = np.where(Z.std(axis=0) > 1e-9, Z.std(axis=0), 1.0)
            Z = (Z - self.mu_) / self.sd_
        return Z

    def predict_proba(self, X):
        return self.est.predict_proba(self._apply(np.asarray(X, dtype=float)))


def model_zoo(*, fast: bool = False) -> dict:
    """Name -> factory. Neural networks are absent on purpose: 58k rows of 150 tabular features
    is squarely gradient-boosting territory, and adding an MLP to look thorough would be a worse
    experiment, not a bigger one (rule 19)."""
    from sklearn.ensemble import (HistGradientBoostingClassifier, RandomForestClassifier,
                                  GradientBoostingClassifier)
    from sklearn.linear_model import LogisticRegression

    zoo = {
        "logreg": lambda: _Imputed(LogisticRegression(max_iter=2000, C=1.0), scale=True),
        "hgb": lambda: HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=40,
            l2_regularization=1.0, early_stopping=True, validation_fraction=0.12,
            random_state=0),
    }
    if not fast:
        zoo["random_forest"] = lambda: _Imputed(RandomForestClassifier(
            n_estimators=300, min_samples_leaf=20, n_jobs=-1, random_state=0))
        # STOCHASTIC gradient boosting, and deliberately small. sklearn's GradientBoostingClassifier
        # is the exact-split ancestor of HistGradientBoosting and is ~50x slower on 39k x 145 --
        # a full-size configuration ran for over an hour on one target without finishing. It is
        # kept in the zoo because rule 19 asks for the family, not because it is expected to win;
        # subsample + sqrt features make it affordable without changing what it is.
        zoo["gboost"] = lambda: _Imputed(GradientBoostingClassifier(
            n_estimators=120, learning_rate=0.08, max_depth=3, subsample=0.5,
            max_features="sqrt", random_state=0))
        try:
            import lightgbm as lgb
            zoo["lightgbm"] = lambda: lgb.LGBMClassifier(
                n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=40,
                subsample=0.9, colsample_bytree=0.8, random_state=0, verbose=-1)
        except Exception:
            pass
    return zoo


def fit_predict(factory, X_tr, y_tr, Xs, *, sample_weight=None) -> list[np.ndarray]:
    """Fit once, predict several frames. Returns P(y=1) for each frame in `Xs`."""
    m = factory()
    try:
        m.fit(X_tr, y_tr, sample_weight=sample_weight)
    except TypeError:
        m.fit(X_tr, y_tr)
    out = []
    for X in Xs:
        p = m.predict_proba(X)
        out.append(p[:, 1] if p.ndim == 2 else p)
    return out


def recency_weights(dates: np.ndarray, *, halflife_days: float | None) -> np.ndarray | None:
    """Exponential decay on age. None means "weight every season the same", which is the
    baseline the recency experiment has to beat."""
    if halflife_days is None:
        return None
    d = pd.to_datetime(pd.Series(dates))
    age = (d.max() - d).dt.days.to_numpy().astype(float)
    return np.power(0.5, age / float(halflife_days))
