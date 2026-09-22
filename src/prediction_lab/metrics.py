"""Scoring. The point of this module is that ACCURACY ALONE IS NOT A RESULT.

Under 3.5 goals happens in 71.6% of fixtures. A model that says "under" every single time is
71.6% accurate and knows nothing. So every accuracy here is reported next to the rock it has to
beat, and `lift_pp` -- the gap between them -- is the number that means something. A lift of
zero is the honest description of a model that has learned the base rate and nothing else.

THE ROCK IS COMPUTED ON THE TEST PERIOD ITSELF. That is deliberate and it is the hard version of
the test: the naive classifier is allowed to know which class was more common in the very period
it is being scored on, and the model still has to beat it. Computing the rock on the training
period instead would hand the model a free win whenever the base rate drifted.

PROBABILITY QUALITY IS TRACKED SEPARATELY AND MATTERS MORE. Two models can both say "over" while
one says 51% and the other says 80%; those are different predictions and only a proper scoring
rule can tell them apart. Log loss and Brier are proper -- they are minimised by telling the
truth -- so they, not accuracy, decide which model is better. Accuracy is reported because it is
the question that was asked, not because it is the best answer to it.

ECE is binned calibration error: bucket the predictions, compare the mean prediction in each
bucket with what actually happened, and average the gaps weighted by bucket size. It answers
"when this model says 65%, does it happen 65% of the time?", which is a different question from
"does it rank fixtures correctly" (AUC) and both are worth knowing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CALC_VERSION = "1.0.0"
EPS = 1e-15
N_BOOT = 2000


def _clip(p):
    return np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)


def log_loss(y, p) -> float:
    p = _clip(p)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y, p) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def auc(y, p) -> float:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    m = np.isfinite(p) & np.isfinite(y)
    y, p = y[m], p[m]
    if len(y) < 20 or y.min() == y.max():
        return float("nan")
    r = pd.Series(p).rank().to_numpy()
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def pr_auc(y, p) -> float:
    """Average precision. Worth having when the positive class is rare (Over 3.5 is 28%)."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    m = np.isfinite(p) & np.isfinite(y)
    y, p = y[m], p[m]
    if len(y) < 20 or y.sum() == 0:
        return float("nan")
    o = np.argsort(-p)
    y = y[o]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y).sum() / y.sum())


def ece(y, p, bins: int = 10) -> float:
    y = np.asarray(y, dtype=float)
    p = _clip(p)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        tot += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(tot)


def classification(y, p, thr: float = 0.5) -> dict:
    y = np.asarray(y, dtype=int)
    yhat = (np.asarray(p, dtype=float) >= thr).astype(int)
    tp = int(((yhat == 1) & (y == 1)).sum())
    fp = int(((yhat == 1) & (y == 0)).sum())
    fn = int(((yhat == 0) & (y == 1)).sum())
    tn = int(((yhat == 0) & (y == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec and rec and np.isfinite(prec + rec) else float("nan")
    return {"accuracy": (tp + tn) / len(y), "precision": prec, "recall": rec, "f1": f1,
            "balanced_accuracy": np.nanmean([rec, spec]), "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def evaluate(y, p, *, thr: float = 0.5, label: str = "", boot: bool = False,
             seed: int = 7) -> dict:
    """Everything, in one dict. `lift_pp` is the only accuracy number worth quoting alone."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    m = np.isfinite(p)
    y, p = y[m], p[m]
    base = float(y.mean()) if len(y) else float("nan")
    rock = max(base, 1 - base)
    c = classification(y, p, thr)
    out = {"label": label, "n": int(len(y)), "base_rate": base, "rock_accuracy": rock,
           "model_accuracy": c["accuracy"], "lift_pp": (c["accuracy"] - rock) * 100,
           "balanced_accuracy": c["balanced_accuracy"], "precision": c["precision"],
           "recall": c["recall"], "f1": c["f1"], "threshold": thr,
           "log_loss": log_loss(y, p), "brier": brier(y, p), "auc": auc(y, p),
           "pr_auc": pr_auc(y, p), "ece": ece(y, p),
           "rock_log_loss": log_loss(y, np.full(len(y), base)),
           "rock_brier": brier(y, np.full(len(y), base)),
           "calc_version": CALC_VERSION}
    out["log_loss_gain"] = out["rock_log_loss"] - out["log_loss"]
    out["brier_gain"] = out["rock_brier"] - out["brier"]
    if boot and len(y) >= 200:
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, len(y), (N_BOOT, len(y)))
        ll = np.array([log_loss(y[i], p[i]) for i in idx[:400]])
        out["log_loss_ci"] = [float(np.percentile(ll, 2.5)), float(np.percentile(ll, 97.5))]
        acc = ((p[idx] >= thr).astype(int) == y[idx]).mean(axis=1)
        out["accuracy_ci"] = [float(np.percentile(acc, 2.5)), float(np.percentile(acc, 97.5))]
    return out


def choose_threshold(y, p, *, objective: str = "balanced_accuracy") -> float:
    """Pick a decision threshold. MUST be called on validation data, never on test (rule 15).

    Returns 0.5 when nothing beats it, rather than a spuriously precise number chosen on noise.
    """
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    best, best_v = 0.5, classification(y, p, 0.5)[objective]
    for t in np.arange(0.30, 0.71, 0.01):
        v = classification(y, p, float(t))[objective]
        if np.isfinite(v) and v > best_v + 1e-6:
            best, best_v = float(t), v
    return best


def confidence_table(y, p, edges=(0.0, 0.5, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 1.01)) -> pd.DataFrame:
    """Does a higher stated probability actually happen more often? Rule 29."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum() == 0:
            continue
        rows.append({"bucket": f"{lo:.2f}-{hi:.2f}", "n": int(m.sum()),
                     "mean_predicted": float(p[m].mean()), "actual_rate": float(y[m].mean()),
                     "gap_pp": float((p[m].mean() - y[m].mean()) * 100),
                     "brier": brier(y[m], p[m])})
    return pd.DataFrame(rows)


def top_k_table(y, p, ks=(1, 5, 10, 25, 50, 100)) -> pd.DataFrame:
    """Accuracy on the most CONFIDENT k% of calls -- confidence meaning distance from a coin flip.

    A model can be useless on average and still know which of its own calls to trust. That is a
    separate and more useful skill than overall accuracy, and this is where it shows up.
    """
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    conf = np.abs(p - 0.5)
    order = np.argsort(-conf)
    call = (p >= 0.5).astype(int)
    rows = []
    for k in ks:
        n = max(1, len(y) * k // 100)
        sel = order[:n]
        rows.append({"k_pct": k, "n": n, "accuracy": float((call[sel] == y[sel]).mean()),
                     "base_rate_in_slice": float(y[sel].mean()),
                     "mean_confidence": float(conf[sel].mean())})
    return pd.DataFrame(rows)
