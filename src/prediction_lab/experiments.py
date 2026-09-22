"""The engine every experiment in the lab runs through.

One function does the work -- `walk_forward` -- and everything else is a question posed to it by
varying one thing: the feature families, the model family, the training window, the league
subset. Keeping a single evaluation path is what makes the comparisons honest; two experiments
that each built their own loop would differ in a dozen invisible ways and the difference in
their numbers would not mean what it appears to mean.

WHAT COMES BACK. `walk_forward` returns out-of-sample probabilities for EVERY test row across
EVERY fold, tagged with the fold that produced them. Nothing in the returned frame was seen by
the model that predicted it. That frame is the raw material for accuracy, calibration, the
confidence curve, the league breakdown and -- importantly -- for the cross-market track, which
needs honest OOS probabilities for all four markets on the same fixtures.

THE THRESHOLD IS CHOSEN ON VALIDATION, PER FOLD. It is then applied unchanged to that fold's
test rows. A threshold picked on the test period would make every accuracy number here a
best-case fiction (rule 15).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M

CALC_VERSION = "1.0.0"
MIN_MINORITY_COUNT = 100        # for a two-valued column, how often the rarer value must appear


def _usable(col: np.ndarray) -> bool:
    """Is this column safe and worth giving to the model, judged on TRAINING data only?

    Stricter than "does it vary", and it has to be. sklearn 1.9.0's HistGradientBoosting bins each
    feature by calling `sliding_window_view(distinct_values, 2)`, which raises "window shape
    cannot be larger than input array shape" when a column arrives with a single distinct value.
    A >= 2 distinct check is not enough to prevent that, because HGB splits the training block
    again for early stopping and bins on ITS OWN 88% slice -- a column with two distinct values
    where one appears a handful of times can reach the binner with one. So a two-valued column
    (`is_weekend` and friends, which are genuinely useful) is kept only when BOTH values are
    common; anything rarer carries no information at this sample size anyway.
    """
    v = col[np.isfinite(col)]
    if v.size < 200:
        return False
    u, c = np.unique(v, return_counts=True)
    if u.size >= 3:
        return True
    return bool(u.size == 2 and c.min() >= MIN_MINORITY_COUNT)


def walk_forward(df: pd.DataFrame, target: str, feat_cols: list[str], *,
                 model: str = "hgb", n_folds: int = FO.DEFAULT_N_FOLDS,
                 halflife_days: float | None = None,
                 train_window_days: int | None = None,
                 fold_list: list[FO.Fold] | None = None,
                 zoo: dict | None = None) -> pd.DataFrame:
    """Out-of-sample probabilities for every test row, across rolling chronological folds.

    `train_window_days` truncates training to a rolling window instead of an expanding one --
    the "how much old football should we remember?" experiment (rule 20).
    """
    zoo = zoo or FO.model_zoo()
    if model not in zoo:
        raise KeyError(f"unknown model {model!r}; have {sorted(zoo)}")
    fl = fold_list or FO.rolling_folds(df, n_folds=n_folds)
    X = df[feat_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=int)
    dates = pd.to_datetime(df["date"]).to_numpy()

    out = []
    for f in fl:
        tr = f.train
        if train_window_days:
            cut = dates[tr].max() - np.timedelta64(int(train_window_days), "D")
            tr = tr[dates[tr] >= cut]
        if len(tr) < 500 or len(np.unique(y[tr])) < 2:
            continue
        # Drop columns that are constant or entirely missing IN THIS FOLD'S TRAINING BLOCK.
        #
        # Necessary, not merely tidy. sklearn 1.9.0's HistGradientBoosting binner does
        # `sliding_window_view(distinct_values, 2)` and raises "window shape cannot be larger
        # than input array shape" when a column has exactly one distinct value -- which happens
        # the moment an experiment is restricted to a subset of leagues where, say, card data
        # does not exist at all. Deciding usability from TRAIN ONLY keeps this from becoming a
        # leak of its own: which columns are usable must not depend on the test period.
        keep = np.array([_usable(X[tr, j]) for j in range(X.shape[1])])
        if not keep.any():
            continue
        Xtr, Xv, Xte = X[np.ix_(tr, np.flatnonzero(keep))], X[:, keep][f.val], X[:, keep][f.test]
        w = FO.recency_weights(dates[tr], halflife_days=halflife_days)
        p_val, p_test = FO.fit_predict(zoo[model], Xtr, y[tr], [Xv, Xte], sample_weight=w)
        # TWO thresholds, both chosen on VALIDATION, never on test.
        #
        # They answer different questions and conflating them is how an imbalanced target gets
        # a fake negative result. Over 1.5 happens 74.4% of the time: a threshold tuned for
        # BALANCED accuracy deliberately calls "under" more often to pick up the rare class,
        # which is correct for that objective and costs raw accuracy several points. Scoring
        # lift-over-the-rock at that threshold then reports the model as worse than a coin that
        # always says "over" -- a statement about the threshold, not about the model.
        # So: `threshold` is accuracy-optimal and drives the headline lift; `threshold_bal` is
        # balanced-accuracy-optimal and drives precision/recall/F1/balanced accuracy.
        ok = len(f.val) >= 300
        thr_acc = M.choose_threshold(y[f.val], p_val, objective="accuracy") if ok else 0.5
        thr_bal = M.choose_threshold(y[f.val], p_val, objective="balanced_accuracy") if ok else 0.5
        out.append(pd.DataFrame({
            "fixture_key": df["fixture_key"].to_numpy()[f.test],
            "date": dates[f.test], "league": df["league"].to_numpy()[f.test],
            "model_type": df["model_type"].to_numpy()[f.test],
            "fold": f.name, "target": target, "model": model,
            "p": p_test, "y": y[f.test],
            "threshold": thr_acc, "threshold_bal": thr_bal}))
    if not out:
        return pd.DataFrame()
    return pd.concat(out, ignore_index=True)


def score(oof: pd.DataFrame, *, label: str = "", boot: bool = False) -> dict:
    """Pooled OOS scoring, using each fold's own validation-chosen thresholds.

    The headline `model_accuracy` / `lift_pp` use the ACCURACY-optimal threshold, so the model
    gets its best honest shot at the rock. The balanced-accuracy family of metrics uses the
    balanced threshold. Both were fitted on validation; neither ever saw the test period.
    """
    if oof.empty:
        return {"label": label, "n": 0}
    y = oof["y"].to_numpy()
    p = oof["p"].to_numpy()
    thr = oof["threshold"].to_numpy()
    thr_b = oof["threshold_bal"].to_numpy() if "threshold_bal" in oof.columns else thr
    base = float(y.mean())
    rock = max(base, 1 - base)
    yhat = (p >= thr).astype(int)
    acc = float((yhat == y).mean())
    r = M.evaluate(y, p, thr=0.5, label=label, boot=boot)
    r.update({"model_accuracy": acc, "lift_pp": (acc - rock) * 100,
              "threshold": float(np.mean(thr)), "threshold_bal": float(np.mean(thr_b)),
              "accuracy_at_p50": float(((p >= 0.5).astype(int) == y).mean())})
    yb = (p >= thr_b).astype(int)
    tp = int(((yb == 1) & (y == 1)).sum()); fp = int(((yb == 1) & (y == 0)).sum())
    fn = int(((yb == 0) & (y == 1)).sum()); tn = int(((yb == 0) & (y == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    r.update({"precision": prec, "recall": rec,
              "f1": (2 * prec * rec / (prec + rec)
                     if np.isfinite(prec + rec) and (prec + rec) else float("nan")),
              "balanced_accuracy": float(np.nanmean([rec, spec])),
              "tp": tp, "fp": fp, "fn": fn, "tn": tn})
    return r


def per_fold(oof: pd.DataFrame) -> pd.DataFrame:
    """Fold-by-fold, so "won once, lost three times" cannot hide inside a pooled average."""
    rows = []
    for fd, g in oof.groupby("fold", sort=True):
        r = score(g, label=fd)
        r["fold"] = fd
        r["t_start"] = str(pd.Timestamp(g["date"].min()).date())
        r["t_end"] = str(pd.Timestamp(g["date"].max()).date())
        rows.append(r)
    return pd.DataFrame(rows)


def baseline_league_prior(df: pd.DataFrame, target: str,
                          fold_list: list[FO.Fold] | None = None) -> pd.DataFrame:
    """MODEL A: the league's own historical rate, and nothing else. The number to beat.

    This is not a strawman. Knowing that the Eredivisie produces 3.18 goals a game and La Liga 2
    produces 2.47 is real football knowledge, and a model loaded with 150 features that cannot
    beat it has not learned anything the league table does not already say.
    """
    fl = fold_list or FO.rolling_folds(df)
    col = f"league_prior_{target}"
    p_all = pd.to_numeric(df[col], errors="coerce").to_numpy() if col in df.columns else None
    y = df[target].to_numpy(dtype=int)
    dates = pd.to_datetime(df["date"]).to_numpy()
    out = []
    for f in fl:
        p = p_all[f.test].copy() if p_all is not None else np.full(len(f.test), np.nan)
        # A league with no prior history falls back to the global prior from TRAIN only.
        p = np.where(np.isfinite(p), p, float(y[f.train].mean()))
        out.append(pd.DataFrame({
            "fixture_key": df["fixture_key"].to_numpy()[f.test], "date": dates[f.test],
            "league": df["league"].to_numpy()[f.test],
            "model_type": df["model_type"].to_numpy()[f.test],
            "fold": f.name, "target": target, "model": "league_prior",
            "p": p, "y": y[f.test], "threshold": 0.5, "threshold_bal": 0.5}))
    return pd.concat(out, ignore_index=True)


def baseline_majority(df: pd.DataFrame, target: str,
                      fold_list: list[FO.Fold] | None = None) -> pd.DataFrame:
    """MODEL 0: the rock. Always call the class that was more common IN TRAINING."""
    fl = fold_list or FO.rolling_folds(df)
    y = df[target].to_numpy(dtype=int)
    dates = pd.to_datetime(df["date"]).to_numpy()
    out = []
    for f in fl:
        base = float(y[f.train].mean())
        out.append(pd.DataFrame({
            "fixture_key": df["fixture_key"].to_numpy()[f.test], "date": dates[f.test],
            "league": df["league"].to_numpy()[f.test],
            "model_type": df["model_type"].to_numpy()[f.test],
            "fold": f.name, "target": target, "model": "majority",
            "p": np.full(len(f.test), base), "y": y[f.test],
            "threshold": 0.5, "threshold_bal": 0.5}))
    return pd.concat(out, ignore_index=True)


def by_league(oof: pd.DataFrame, *, min_n: int = 150) -> pd.DataFrame:
    """Per-league OOS. Leagues below `min_n` are reported but flagged uninterpretable."""
    rows = []
    for lg, g in oof.groupby("league"):
        r = score(g, label=str(lg))
        r["league"] = lg
        r["interpretable"] = bool(len(g) >= min_n)
        rows.append(r)
    return pd.DataFrame(rows).sort_values("lift_pp", ascending=False)


def learning_curve(df: pd.DataFrame, target: str, feat_cols: list[str], *, model: str = "hgb",
                   sizes=(3000, 6000, 12000, 24000, 40000)) -> pd.DataFrame:
    """Is more data making this better, or has it plateaued? (rule 35)

    The TEST period is held fixed across every size -- only the amount of history used to train
    varies. Growing both at once would confound "more data helps" with "that year was easier".
    """
    d = df.sort_values("date", kind="mergesort").reset_index(drop=True)
    n = len(d)
    test_start = int(n * 0.85)
    dates = pd.to_datetime(d["date"]).to_numpy()
    while test_start < n and dates[test_start] == dates[test_start - 1]:
        test_start += 1
    X = d[feat_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    y = d[target].to_numpy(dtype=int)
    te = np.arange(test_start, n)
    zoo = FO.model_zoo()
    rows = []
    for s in sizes:
        if s > test_start - 200:
            continue
        tr = np.arange(test_start - s, test_start)      # the s most RECENT pre-test matches
        (p,) = FO.fit_predict(zoo[model], X[tr], y[tr], [X[te]])
        r = M.evaluate(y[te], p, label=f"n={s}")
        r["train_n"] = s
        r["test_n"] = len(te)
        rows.append(r)
    return pd.DataFrame(rows)
