"""Does Wowza actually get better at predicting football as it accumulates experience?

    python -m src.shadow_learning.walkforward --write
    python -m src.shadow_learning.walkforward --variants canonical,frozen --write

Sections 46-79. A month-by-month reconstruction of how a learning system would have behaved:
train on everything known by the last day of month M-1, predict EVERY eligible fixture in month
M, then let those results become training data and repeat.

THE CONTROL IS THE WHOLE EXPERIMENT. An improving curve proves nothing on its own, because later
football may simply be easier to predict -- base rates drift, coverage improves, leagues change.
So `frozen` trains once at the start and never retrains again. If the retrained model's curve
falls and the frozen model's curve falls by the same amount, nothing was learned and the period
just got easier. Only the GAP between them is evidence. Section 57 calls this optional; it is
not, and it is run by default here.

THE SECOND CONTROL IS THE BASELINE. Section 63: if Over 1.5 accuracy rises from 72% to 76% while
the majority class also rises from 72% to 76%, that is not learning. Every month therefore also
scores a contemporaneous base-rate predictor -- the league's own rate computed from data
available at that time -- and the metric that matters is the model's margin over it, not its
absolute value.

LEAKAGE. Features come from `src.prediction_lab.features`, which is perturbation-tested:
randomise every result from a cutoff onward, rebuild, and every earlier value is bit-identical.
On top of that, training rows are filtered to `date < month_start` and the month's own fixtures
are never in the fit. The feature matrix is built ONCE per universe rather than per month, which
is safe precisely because the features are as-of by construction -- a fixture's rolling form
never sees its own match or any later one.

WHAT IS SIMULATED AND WHAT IS NOT. The promotion gate is simulated (section 65): each month a
challenger is trained, judged against the sitting champion on a pre-month validation slice, and
promoted or rejected -- and then the month is revealed so the decision can be marked right or
wrong. Nothing is written to any model file; no production model is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.prediction_lab import data as D
from src.prediction_lab import features as F
from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M
from src.shadow_learning import datasets as DS
from src.shadow_learning import experiments as X

CALC_VERSION = "1.0.0"
TARGETS = ("btts", "over15", "over25", "over35")
MIN_TRAIN = 6000            # below this a month is skipped; the model would be noise
MIN_TEST = 60               # months with fewer eligible fixtures are recorded but not trended
GATE_TOL = 0.005            # mirrors v9's TRAIN_MAX_LOGLOSS_RISE
VAL_MONTHS = 3              # validation slice for the simulated gate


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_universe_frames() -> dict:
    """One feature matrix per data path. Built once; as-of features make that safe."""
    U = X.universes()
    base = X._prepare(U["_can_frame"])
    out = {}
    v9_keys = U["v9"]
    out["canonical"] = F.build(base)
    out["v9_path"] = F.build(base[base["fixture_key"].isin(v9_keys)].reset_index(drop=True))
    return out


def _months(dates: pd.Series, start: str | None) -> list[pd.Period]:
    p = pd.PeriodIndex(pd.to_datetime(dates).dt.to_period("M").unique()).sort_values()
    if start:
        p = p[p >= pd.Period(start, freq="M")]
    return list(p)


def _fit(frame: pd.DataFrame, cols: list[str], target: str, rows: np.ndarray,
         weights=None):
    zoo = FO.model_zoo(fast=True)
    X_ = frame[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    y = frame[target].to_numpy(dtype=int)
    keep = np.array([X_[rows, j][np.isfinite(X_[rows, j])].size >= 200
                     and np.unique(X_[rows, j][np.isfinite(X_[rows, j])]).size >= 3
                     for j in range(X_.shape[1])])
    if not keep.any() or len(np.unique(y[rows])) < 2:
        return None, None
    m = zoo["hgb"]()
    try:
        m.fit(X_[np.ix_(rows, np.flatnonzero(keep))], y[rows], sample_weight=weights)
    except TypeError:
        m.fit(X_[np.ix_(rows, np.flatnonzero(keep))], y[rows])
    return m, keep


def _predict(model, keep, frame, cols, rows) -> np.ndarray:
    X_ = frame[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return model.predict_proba(X_[np.ix_(rows, np.flatnonzero(keep))])[:, 1]


def _hash(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12]


def run(variants: list[str], *, start: str | None = "2022-08",
        window_years: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames = _build_universe_frames()
    window_years = window_years or {}
    ledger, preds, gate_log = [], [], []

    for vname in variants:
        path = "v9_path" if vname == "v9_path" else "canonical"
        frame = frames[path]
        cols = F.feature_columns(frame, F.FOOTBALL_FAMILIES)
        dates = pd.to_datetime(frame["date"])
        months = _months(dates, start)
        print(f"\n[wf] {vname}: {len(frame):,} fixtures, {len(months)} months "
              f"{months[0]}..{months[-1]}")

        frozen = {}          # target -> (model, keep, dataset_id) for the frozen control
        champion = {}        # target -> (model, keep, dataset_id, promoted_month)
        prev_train_n = {}

        for mi, mon in enumerate(months):
            m_start = mon.to_timestamp()
            m_end = (mon + 1).to_timestamp()
            te = np.flatnonzero((dates >= m_start) & (dates < m_end))
            tr = np.flatnonzero(dates < m_start)
            if window_years.get(vname):
                cut = m_start - pd.DateOffset(years=window_years[vname])
                tr = tr[dates.to_numpy()[tr] >= np.datetime64(cut)]
            if len(tr) < MIN_TRAIN or len(te) == 0:
                continue
            ds_id = _hash(vname, str(mon), len(tr))
            retrain_id = f"{vname}:{mon}"

            for t in TARGETS:
                y_te = frame[t].to_numpy(dtype=int)[te]
                if len(np.unique(y_te)) < 2:
                    continue

                # CONTEMPORANEOUS BASELINE (section 63): the league's own rate from data
                # available BEFORE this month. Not the global rate, and never the month's own.
                prior = frame.iloc[tr].groupby("league")[t].mean()
                glob = float(frame[t].to_numpy()[tr].mean())
                p_base = frame["league"].to_numpy()[te]
                p_base = np.array([prior.get(l, glob) for l in p_base], dtype=float)

                if vname == "frozen":
                    if t not in frozen:
                        mdl, keep = _fit(frame, cols, t, tr)
                        if mdl is None:
                            continue
                        frozen[t] = (mdl, keep, ds_id, str(mon))
                    mdl, keep, fds, fmon = frozen[t]
                    p = _predict(mdl, keep, frame, cols, te)
                    active_ds, model_age = fds, mi
                    gate_decision = "frozen_never_retrains"
                else:
                    # Challenger trained on everything before this month.
                    cand, ckeep = _fit(frame, cols, t, tr)
                    if cand is None:
                        continue
                    # SIMULATED GATE (section 65): judge on a pre-month validation slice.
                    vstart = m_start - pd.DateOffset(months=VAL_MONTHS)
                    va = tr[dates.to_numpy()[tr] >= np.datetime64(vstart)]
                    if t in champion and len(va) >= 200:
                        ch_m, ch_k, ch_ds, ch_mon = champion[t]
                        try:
                            ll_ch = M.log_loss(frame[t].to_numpy()[va],
                                               _predict(ch_m, ch_k, frame, cols, va))
                            ll_cd = M.log_loss(frame[t].to_numpy()[va],
                                               _predict(cand, ckeep, frame, cols, va))
                        except Exception:
                            ll_ch = ll_cd = float("nan")
                        promote = not (ll_cd > ll_ch + GATE_TOL)
                    else:
                        ll_ch = ll_cd = float("nan")
                        promote = True
                    if promote:
                        champion[t] = (cand, ckeep, ds_id, str(mon))
                    ch_m, ch_k, active_ds, ch_mon = champion[t]
                    p = _predict(ch_m, ch_k, frame, cols, te)
                    # What WOULD the rejected challenger have scored? That is the only way to
                    # know whether the gate's decision was right.
                    p_cand = _predict(cand, ckeep, frame, cols, te)
                    gate_log.append({
                        "variant": vname, "month": str(mon), "target": t,
                        "val_logloss_champion": ll_ch, "val_logloss_challenger": ll_cd,
                        "decision": "PROMOTE" if promote else "REJECT",
                        "next_month_logloss_active": M.log_loss(y_te, p),
                        "next_month_logloss_challenger": M.log_loss(y_te, p_cand),
                        "decision_was_correct": bool(
                            (promote and M.log_loss(y_te, p_cand) <= M.log_loss(y_te, p) + 1e-12)
                            or (not promote and M.log_loss(y_te, p) <= M.log_loss(y_te, p_cand))),
                        "champion_month": ch_mon, "train_rows": int(len(tr))})
                    gate_decision = "PROMOTE" if promote else "REJECT"
                    model_age = mi - months.index(pd.Period(ch_mon, freq="M"))

                base_rate = float(y_te.mean())
                rock = max(base_rate, 1 - base_rate)
                acc = float(((p >= 0.5).astype(int) == y_te).mean())
                ledger.append({
                    "variant": vname, "month": str(mon), "target": t,
                    "dataset_id": active_ds, "retrain_id": retrain_id,
                    "train_start": str(dates.iloc[tr].min())[:10],
                    "train_end": str(dates.iloc[tr].max())[:10],
                    "n_train": int(len(tr)), "n_test": int(len(te)),
                    "target_prevalence": round(base_rate, 4),
                    "majority_accuracy": round(rock, 4),
                    "accuracy": round(acc, 4),
                    "accuracy_lift": round((acc - rock) * 100, 3),
                    "auc": round(M.auc(y_te, p), 4), "pr_auc": round(M.pr_auc(y_te, p), 4),
                    "brier": round(M.brier(y_te, p), 5),
                    "log_loss": round(M.log_loss(y_te, p), 5),
                    "ece": round(M.ece(y_te, p), 5),
                    "baseline_log_loss": round(M.log_loss(y_te, p_base), 5),
                    "baseline_brier": round(M.brier(y_te, p_base), 5),
                    "margin_vs_baseline_ll": round(
                        M.log_loss(y_te, p_base) - M.log_loss(y_te, p), 5),
                    "mean_predicted": round(float(p.mean()), 4),
                    "mean_actual": round(base_rate, 4),
                    "model_age_months": int(model_age),
                    "gate_decision": gate_decision,
                    "interpretable": bool(len(te) >= MIN_TEST),
                })
                preds.append(pd.DataFrame({
                    "fixture_key": frame["fixture_key"].to_numpy()[te],
                    "date": frame["date"].to_numpy()[te],
                    "league": frame["league"].to_numpy()[te],
                    "target": t, "actual": y_te, "p": p,
                    "variant": vname, "month": str(mon), "dataset_id": active_ds}))
            if mi % 6 == 0:
                print(f"   {mon}  train={len(tr):,}  test={len(te):,}")
            prev_train_n[vname] = len(tr)

    return (pd.DataFrame(ledger), pd.concat(preds, ignore_index=True) if preds
            else pd.DataFrame(), pd.DataFrame(gate_log))


def trends(ledger: pd.DataFrame) -> pd.DataFrame:
    """Section 62: is the trend real, or is it a line drawn through noise?

    Theil-Sen slope with a bootstrap interval rather than ordinary least squares, because a
    monthly metric series has heavy tails -- one chaotic month should not set the direction of a
    four-year conclusion.
    """
    from scipy import stats as st
    rows = []
    for (v, t), g in ledger[ledger.interpretable].groupby(["variant", "target"]):
        g = g.sort_values("month")
        x = np.arange(len(g), dtype=float)
        for metric, better in (("log_loss", "down"), ("brier", "down"), ("ece", "down"),
                               ("auc", "up"), ("accuracy_lift", "up"),
                               ("margin_vs_baseline_ll", "up")):
            y = g[metric].to_numpy(dtype=float)
            ok = np.isfinite(y)
            if ok.sum() < 8:
                continue
            slope, inter, lo, hi = st.theilslopes(y[ok], x[ok], 0.95)
            tau, pval = st.kendalltau(x[ok], y[ok])
            improving = (slope < 0) if better == "down" else (slope > 0)
            # "Clear" means the confidence interval EXCLUDES ZERO, in EITHER direction.
            #
            # The first version asked only whether the interval sat on the improving side, so a
            # clearly DEGRADING series came back FLAT -- the smoke test produced exactly that:
            # over35 log loss rising 0.0073/month, CI [+0.0004, +0.0147], p=0.045, reported as
            # FLAT. That is the failure mode section 77 warns about, where the expected shape of
            # the answer quietly filters the evidence. A trend test that can only find good news
            # is not a test.
            clear = bool(pval < 0.05 and (hi < 0 or lo > 0))
            rows.append({"variant": v, "target": t, "metric": metric,
                         "months": int(ok.sum()), "slope_per_month": round(float(slope), 6),
                         "ci_lo": round(float(lo), 6), "ci_hi": round(float(hi), 6),
                         "kendall_tau": round(float(tau), 4), "p_value": round(float(pval), 5),
                         "direction": "IMPROVING" if improving else "DEGRADING",
                         "statistically_clear": clear,
                         "verdict": ("IMPROVING" if (improving and clear) else
                                     "DEGRADING" if ((not improving) and clear) else "FLAT")})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="v9_path,canonical,frozen,rolling_3y")
    ap.add_argument("--start", default="2022-08")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    vs = [v.strip() for v in a.variants.split(",") if v.strip()]
    led, pr, gate = run(vs, start=a.start, window_years={"rolling_3y": 3})
    if led.empty:
        print("no months evaluated")
        return 1
    print(f"\n[wf] {len(led):,} month x target rows, {len(pr):,} stored predictions")

    print("\nMEAN OOS BY VARIANT (all months, interpretable only)")
    g = led[led.interpretable].groupby(["variant", "target"])[
        ["log_loss", "brier", "auc", "accuracy_lift", "margin_vs_baseline_ll"]].mean()
    print(g.round(5).to_string())

    tr = trends(led)
    if not tr.empty:
        print("\nLEARNING TREND (Theil-Sen, Kendall tau) — log loss only")
        print(tr[tr.metric == "log_loss"][
            ["variant", "target", "months", "slope_per_month", "ci_lo", "ci_hi",
             "p_value", "verdict"]].to_string(index=False))

    if not gate.empty:
        print(f"\nSIMULATED PROMOTION GATE: {len(gate):,} decisions")
        print(gate.groupby(["variant", "decision"])["decision_was_correct"]
              .agg(["size", "mean"]).round(3).to_string())

    if a.write:
        led.to_csv(O() / "monthly_walkforward_performance.csv", index=False)
        tr.to_csv(O() / "walkforward_trends.csv", index=False)
        if not gate.empty:
            gate.to_csv(O() / "retrain_gate_backtest.csv", index=False)
        pr.to_parquet(O() / "walkforward_predictions.parquet", index=False)
        print(f"\n[wf] wrote ledger, trends, gate backtest and the prediction store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
