"""Does the player model learn too — and did recovering 30,919 stranded rows help?

    python -m src.shadow_learning.player_walkforward --write

Sections 52 and 72. The match walk-forward showed Wowza learns. Player prediction is a different
problem with different failure modes, so it gets its own chronology rather than being folded
into a shared metric.

WHY IT CANNOT SHARE THE MATCH ANALYSIS. Players score in about 8% of appearances. At that
prevalence accuracy is meaningless -- "nobody scores" is 92% accurate -- and even log loss is
dominated by the easy negatives. PR-AUC is the metric that moves when the model gets better at
the rare event, so it is reported alongside, and the naive baseline is not the global rate but
each POSITION's rate computed from data available at the time. A model that merely learns
"strikers score more than full-backs" has learned nothing worth having.

THE THREE ARMS.

    current    player_history.parquet as production has it
    canonical  the same, plus the 30,919 rows recovered from fixture_player_cache whose
               fixtures were date-resolved against the provider
    frozen     trained once at the start, never retrained -- the control, same as the match side

If `canonical` beats `current` on the same future appearances, the recovery was worth doing. If
it does not, the recovery was still worth doing for completeness but must not be sold as a
prediction gain, and the report has to say so.

ELIGIBILITY (section 24). Only rows whose fixture DATE is known can be placed in time, so the
unresolved ones are excluded by construction. Within that, the population is players with prior
appearances -- selection on their own history, never on the match being predicted.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M

CALC_VERSION = "1.0.0"
MIN_TRAIN = 8000
MIN_TEST = 200
WINDOWS = (5, 10)


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _A() -> Path:
    return cfg.OUTPUT_DIR / "architecture"


def load() -> pd.DataFrame:
    p = _A() / "canonical_player_history.parquet"
    if not p.exists():
        raise RuntimeError("canonical_player_history.parquet missing")
    d = pd.read_parquet(p)
    d = d[d["training_eligible"]].copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date", "player_id"])
    return d.sort_values(["player_id", "date"], kind="mergesort").reset_index(drop=True)


def featurize(d: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Prior-only rolling features per player. Shift precedes every window, always."""
    base = [c for c in ("minutes", "goals", "assists", "shots_total", "shots_on_target",
                        "started", "rating") if c in d.columns]
    g = d.groupby("player_id", sort=False)
    sh = g[base].shift(1)
    sh["player_id"] = d["player_id"].to_numpy()
    out = d[["fixture_id", "player_id", "date", "league", "team", "position",
             "scored", "source"]].copy()
    for w in WINDOWS:
        r = sh.groupby("player_id", sort=False)[base].rolling(w, min_periods=2).mean()
        r.index = r.index.droplevel(0)
        r = r.reindex(d.index)
        for c in base:
            out[f"pl_{c}_r{w}"] = r[c]
    out["pl_apps_prior"] = g.cumcount().to_numpy()
    cum = g["goals"].cumsum() - d["goals"].fillna(0)
    out["pl_career_goals"] = cum
    out["pl_career_gpa"] = np.where(out["pl_apps_prior"] > 0,
                                    cum / out["pl_apps_prior"].replace(0, np.nan), np.nan)
    cmin = g["minutes"].cumsum() - d["minutes"].fillna(0)
    out["pl_career_g_per90"] = np.where(cmin > 0, cum / (cmin / 90.0), np.nan)
    for w in WINDOWS:
        mins = out[f"pl_minutes_r{w}"].replace(0, np.nan)
        out[f"pl_g_per90_r{w}"] = out[f"pl_goals_r{w}"] / (mins / 90.0)
    out["pl_pos_code"] = pd.Categorical(out["position"].astype(str)).codes.astype(float)
    cols = [c for c in out.columns if c.startswith("pl_")]
    return out, cols


def _fit(X, y, rows):
    zoo = FO.model_zoo(fast=True)
    keep = np.array([np.unique(X[rows, j][np.isfinite(X[rows, j])]).size >= 3
                     and np.isfinite(X[rows, j]).sum() >= 200 for j in range(X.shape[1])])
    if not keep.any() or len(np.unique(y[rows])) < 2:
        return None, None
    m = zoo["hgb"]()
    m.fit(X[np.ix_(rows, np.flatnonzero(keep))], y[rows])
    return m, keep


def run(*, start: str = "2023-02") -> tuple[pd.DataFrame, pd.DataFrame]:
    d = load()
    feat, cols = featurize(d)
    feat["is_recovered"] = (d["source"] == "fixture_player_cache").to_numpy()
    X = feat[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    y = feat["scored"].to_numpy(dtype=int)
    dates = pd.to_datetime(feat["date"])
    months = [m for m in pd.PeriodIndex(dates.dt.to_period("M").unique()).sort_values()
              if m >= pd.Period(start, freq="M")]
    print(f"[player-wf] {len(feat):,} eligible rows, {feat.player_id.nunique():,} players, "
          f"{len(months)} months from {months[0]}")
    print(f"[player-wf] recovered rows in the pool: {int(feat.is_recovered.sum()):,}")

    ledger, preds = [], []
    frozen, champion = {}, {}
    for variant in ("current", "canonical", "frozen"):
        pool = (~feat["is_recovered"]).to_numpy() if variant == "current" else np.ones(len(feat), bool)
        for mi, mon in enumerate(months):
            ms, me = mon.to_timestamp(), (mon + 1).to_timestamp()
            te = np.flatnonzero((dates >= ms) & (dates < me))
            tr = np.flatnonzero((dates < ms) & pool)
            if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
                continue
            if variant == "frozen":
                if "m" not in frozen:
                    mdl, keep = _fit(X, y, tr)
                    if mdl is None:
                        continue
                    frozen["m"], frozen["k"], frozen["mon"] = mdl, keep, str(mon)
                mdl, keep = frozen["m"], frozen["k"]
            else:
                mdl, keep = _fit(X, y, tr)
                if mdl is None:
                    continue
            p = mdl.predict_proba(X[np.ix_(te, np.flatnonzero(keep))])[:, 1]
            y_te = y[te]

            # BASELINE: each POSITION's prior scoring rate, from data available before this
            # month. A model that only learns "strikers score more" must not look skilful.
            prior = pd.Series(y[tr]).groupby(
                feat["pl_pos_code"].to_numpy()[tr]).mean()
            glob = float(y[tr].mean())
            p_base = np.array([prior.get(c, glob)
                               for c in feat["pl_pos_code"].to_numpy()[te]], dtype=float)

            ledger.append({
                "variant": variant, "month": str(mon), "target": "scored",
                "n_train": int(len(tr)), "n_test": int(len(te)),
                "prevalence": round(float(y_te.mean()), 4),
                "log_loss": round(M.log_loss(y_te, p), 5),
                "brier": round(M.brier(y_te, p), 5),
                "auc": round(M.auc(y_te, p), 4),
                "pr_auc": round(M.pr_auc(y_te, p), 4),
                "ece": round(M.ece(y_te, p), 5),
                "baseline_log_loss": round(M.log_loss(y_te, p_base), 5),
                "baseline_pr_auc": round(M.pr_auc(y_te, p_base), 4),
                "margin_vs_baseline_ll": round(M.log_loss(y_te, p_base) - M.log_loss(y_te, p), 5),
                "interpretable": True})
            preds.append(pd.DataFrame({
                "fixture_id": feat["fixture_id"].to_numpy()[te],
                "player_id": feat["player_id"].to_numpy()[te],
                "date": feat["date"].to_numpy()[te], "league": feat["league"].to_numpy()[te],
                "actual": y_te, "p": p, "variant": variant, "month": str(mon)}))
        print(f"   {variant:<10} done")
    return pd.DataFrame(ledger), (pd.concat(preds, ignore_index=True) if preds
                                  else pd.DataFrame())


def trends(led: pd.DataFrame) -> pd.DataFrame:
    from scipy import stats as st
    rows = []
    for v, g in led.groupby("variant"):
        g = g.sort_values("month")
        x = np.arange(len(g), dtype=float)
        for metric, better in (("log_loss", "down"), ("brier", "down"), ("ece", "down"),
                               ("auc", "up"), ("pr_auc", "up"),
                               ("margin_vs_baseline_ll", "up")):
            yv = g[metric].to_numpy(dtype=float)
            ok = np.isfinite(yv)
            if ok.sum() < 8:
                continue
            slope, _, lo, hi = st.theilslopes(yv[ok], x[ok], 0.95)
            tau, pv = st.kendalltau(x[ok], yv[ok])
            improving = (slope < 0) if better == "down" else (slope > 0)
            clear = bool(pv < 0.05 and (hi < 0 or lo > 0))
            rows.append({"variant": v, "metric": metric, "months": int(ok.sum()),
                         "slope_per_month": round(float(slope), 7),
                         "ci_lo": round(float(lo), 7), "ci_hi": round(float(hi), 7),
                         "p_value": round(float(pv), 5),
                         "verdict": ("IMPROVING" if improving and clear else
                                     "DEGRADING" if (not improving) and clear else "FLAT")})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    led, pr = run()
    if led.empty:
        print("no months evaluated")
        return 1
    print(f"\n[player-wf] {led.month.nunique()} months, {int(led.n_test.sum()):,} "
          f"player-appearance predictions")
    m = led.groupby("variant")[["log_loss", "brier", "auc", "pr_auc", "ece",
                                "margin_vs_baseline_ll", "baseline_pr_auc"]].mean()
    print("\nMEAN ACROSS MONTHS  (8% base rate — PR-AUC is the metric that moves)")
    print(m.round(5).to_string())

    tr = trends(led)
    print("\nLEARNING TREND")
    print(tr[tr.metric.isin(["pr_auc", "margin_vs_baseline_ll", "log_loss"])][
        ["variant", "metric", "months", "slope_per_month", "p_value",
         "verdict"]].to_string(index=False))

    if {"current", "canonical"} <= set(led.variant):
        from src.validation.multiple_testing import paired_bootstrap_p
        cur = pr[pr.variant == "current"][["fixture_id", "player_id", "actual", "p"]]
        can = pr[pr.variant == "canonical"][["fixture_id", "player_id", "p"]]
        j = cur.merge(can, on=["fixture_id", "player_id"], suffixes=("_cur", "_can"))
        if len(j):
            def ll(col):
                q = np.clip(j[col].to_numpy(float), 1e-15, 1 - 1e-15)
                yy = j["actual"].to_numpy(float)
                return -(yy * np.log(q) + (1 - yy) * np.log(1 - q))
            pv, obs, ci = paired_bootstrap_p(ll("p_can"), ll("p_cur"), n_boot=2000, block=8)
            print(f"\nDID RECOVERING 30,919 ROWS HELP?  paired on {len(j):,} identical "
                  f"appearances")
            print(f"  diff {obs:+.6f}  CI [{ci[0]:+.6f}, {ci[1]:+.6f}]  p={pv:.4f}  "
                  f"-> {'YES' if (ci[0] > 0) else 'NO' if ci[1] < 0 else 'no — inside noise'}")

    if a.write:
        led.to_csv(O() / "player_walkforward_performance.csv", index=False)
        tr.to_csv(O() / "player_walkforward_trends.csv", index=False)
        pr.to_parquet(O() / "walkforward_player_predictions.parquet", index=False)
        print(f"\n[player-wf] wrote ledger, trends and the player prediction store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
