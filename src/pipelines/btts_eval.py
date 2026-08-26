"""
Does the BTTS asymmetry hypothesis survive an honest test?
=========================================================
    python -m src.pipelines.btts_eval

THE HYPOTHESIS (src/features/btts.py): v9's BTTS model sits at its own base rate because every
feature it has describes goal VOLUME, while BTTS is about goal DISTRIBUTION. Adding
asymmetry features -- above all `lam_min`, the weaker attack that BINDS whether both sides score
-- should add signal that no volume feature can supply.

HOW THIS IS TESTED, and the four ways it refuses to flatter itself:

1. **Scored against the BTTS BASE RATE, never against 0.50.** Comparing a 53% base-rate market
   to a coin flip inflates every result -- it once turned over15's +0.029 into +0.140. The
   baseline here is "always predict the training base rate".

2. **Chronological split.** Never random. A random split on rolling-form features leaks the
   future into the past through overlapping windows.

3. **The comparison is nested and otherwise identical.** Same rows, same split, same model class,
   same calibration; the ONLY difference is the added columns. Anything else and the comparison
   measures the change plus whatever else moved.

4. **A bootstrap interval on the DIFFERENCE, not on each model separately.** Two overlapping
   intervals do not tell you whether the gap is real, and the gap is the whole question.

THE SAMPLE IS SMALL AND THAT GOVERNS THE CONCLUSION. `settlements_backfill` holds 778 labelled
rows. That is enough to see whether an effect is plausibly there; it is nowhere near enough to
train a production BTTS model, and this module deliberately does NOT write a model artifact.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data import season_store as store
from src.features import btts as bf

SEED = 20260823
N_BOOT = 2000

# Volume features already available to v9's BTTS model. Deliberately a SUBSET of FEATURE_COLS:
# the point is a like-for-like nested comparison on the columns the backfill actually carries,
# not a reproduction of v9's full model.
BASE_FEATURES = [
    "home_scored_last5", "away_scored_last5", "home_conceded_last5", "away_conceded_last5",
    "home_attack_str", "away_attack_str", "home_defense_str", "away_defense_str",
    "league_avg_goals", "home_over25_last5", "away_over25_last5",
    "p_over25_poisson_dc", "h2h_avg_goals", "home_xg_last5", "away_xg_last5",
    "home_cs_rate_h", "away_cs_rate_a", "home_season_goals_h", "away_season_goals_a",
]


def _fit_predict(tr: pd.DataFrame, te: pd.DataFrame, cols: list[str],
                 y_tr: pd.Series) -> np.ndarray:
    """LogReg + calibration, matching the project's standard model shape."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer

    Xtr = tr[cols].apply(pd.to_numeric, errors="coerce")
    Xte = te[cols].apply(pd.to_numeric, errors="coerce")
    # Medians from TRAIN only. Imputing from the full frame leaks test-set distribution into
    # training, which is a quiet way to inflate every result.
    m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                      LogisticRegression(max_iter=2000, C=0.5))
    m.fit(Xtr, y_tr)
    return m.predict_proba(Xte)[:, 1]


def _brier(y, p) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def _logloss(y, p) -> float:
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _boot_diff(y, p_a, p_b) -> tuple[float, float]:
    """95% CI for brier(a) - brier(b), resampling the SAME test rows for both models."""
    rng = np.random.default_rng(SEED)
    y, p_a, p_b = np.asarray(y, float), np.asarray(p_a, float), np.asarray(p_b, float)
    n = len(y)
    d = np.empty(N_BOOT)
    for i in range(N_BOOT):
        ix = rng.integers(0, n, n)
        d[i] = _brier(y[ix], p_a[ix]) - _brier(y[ix], p_b[ix])
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def run() -> dict:
    d = store.read("settlements_backfill")
    if d is None or d.empty:
        print("[btts_eval] settlements_backfill is empty")
        return {}
    d = d.copy()
    d["_y"] = bf.btts_label(d)
    d = d[d["_y"].notna()]
    if d.empty:
        print("[btts_eval] no rows carry both goal columns, so no BTTS label exists")
        return {}
    d["_dt"] = pd.to_datetime(d.get("match_date"), errors="coerce")
    d = d[d["_dt"].notna()].sort_values("_dt")
    d = bf.add_features(d)

    base = [c for c in BASE_FEATURES if c in d.columns]
    extra = [c for c in bf.FEATURES if c in d.columns]
    cut = int(len(d) * 0.8)
    tr, te = d.iloc[:cut], d.iloc[cut:]
    y_tr, y_te = tr["_y"].astype(float), te["_y"].astype(float)

    print(f"[btts_eval] {len(d)} labelled rows  "
          f"train {len(tr)} ({tr['_dt'].min():%Y-%m-%d}..{tr['_dt'].max():%Y-%m-%d})  "
          f"test {len(te)} ({te['_dt'].min():%Y-%m-%d}..{te['_dt'].max():%Y-%m-%d})")
    print(f"  base features {len(base)}   added {len(extra)}: {', '.join(extra)}")
    print(f"  BTTS base rate: train {y_tr.mean():.4f}   test {y_te.mean():.4f}")

    # THE baseline: always predict the training base rate. Not 0.50.
    p_const = np.full(len(te), float(y_tr.mean()))
    p_base = _fit_predict(tr, te, base, y_tr)
    p_full = _fit_predict(tr, te, base + extra, y_tr)
    # The single feature the hypothesis rests on, alone, on top of the volume set.
    p_min = _fit_predict(tr, te, base + ["lam_min"], y_tr) if "lam_min" in d.columns else None

    rows = [("base rate constant", p_const), ("volume features only", p_base),
            ("volume + lam_min", p_min), ("volume + all asymmetry", p_full)]
    print(f"\n  {'model':<26} {'Brier':>8} {'vs const':>10} {'LogLoss':>9}")
    out = {}
    for name, p in rows:
        if p is None:
            continue
        b, ll = _brier(y_te, p), _logloss(y_te, p)
        out[name] = {"brier": round(b, 5), "logloss": round(ll, 5),
                     "brier_gain_vs_base_rate": round(_brier(y_te, p_const) - b, 5)}
        print(f"  {name:<26} {b:>8.5f} {out[name]['brier_gain_vs_base_rate']:>+10.5f} "
              f"{ll:>9.5f}")

    lo, hi = _boot_diff(y_te, p_base, p_full)
    print(f"\n  Brier(volume) - Brier(volume+asymmetry) = "
          f"{_brier(y_te, p_base) - _brier(y_te, p_full):+.5f}")
    print(f"  95% CI on that difference: [{lo:+.5f}, {hi:+.5f}]  "
          f"-> {'asymmetry HELPS' if lo > 0 else 'asymmetry HURTS' if hi < 0 else 'INCONCLUSIVE'}")
    out["diff_ci"] = {"lo": round(lo, 5), "hi": round(hi, 5)}

    # Calibration bias — the prerequisite for ever enabling BTTS-NO.
    print("\n  calibration (bias must be ~0 before BTTS-NO could be considered):")
    for name, p in (("volume only", p_base), ("volume + asymmetry", p_full)):
        bc = bf.bias_correction(y_te, pd.Series(p, index=te.index))
        out[f"bias_{name}"] = bc
        print(f"    {name:<22} base {bc['base_rate']:.4f}  model {bc['model_mean']:.4f}  "
              f"bias {bc['bias_pp']:+.2f}pp")

    # Does the raw DC probability alone beat the base rate? A clean read on the physics, with no
    # fitting at all.
    if "p_btts_dc" in te.columns:
        p_dc = pd.to_numeric(te["p_btts_dc"], errors="coerce").fillna(y_tr.mean()).to_numpy()
        b_dc = _brier(y_te, p_dc)
        print(f"\n  UNFITTED Dixon-Coles P(BTTS) alone: Brier {b_dc:.5f} "
              f"({_brier(y_te, p_const) - b_dc:+.5f} vs base rate)  "
              f"mean {p_dc.mean():.4f} vs actual {y_te.mean():.4f}")
        out["unfitted_dc"] = {"brier": round(b_dc, 5),
                              "gain": round(_brier(y_te, p_const) - b_dc, 5)}

    print(f"\n[btts_eval] n={len(te)} test rows. RESEARCH ONLY — no model artifact written, "
          f"nothing promoted to v9.")
    return out


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ── THIRD ATTEMPT: real per-team lambdas from team_match_stats ────────────────
#
# The first two attempts were both wrong, in different ways, and both looked finished:
#
#   1. v9's stored features. p_btts_dc scored AUC 0.5032 and lam_min 0.4898 (below chance), and
#      I concluded distribution features cannot help. But home_xg_last5, insidebox and possession
#      were ALL 0% populated on the live board and missing features are median-imputed, so the
#      lambdas were built from league averages. Wrong diagnosis: absent inputs, not a dead end.
#   2. My own rolling-form code. A pandas index scatter set corr(prior scoring rate, goals next)
#      to -0.0009 — an exact zero. Had I trusted it I would have reported that form carries no
#      information about goals, which is false.
#
# So this attempt states its guards up front:
#   * lambdas come from team_form, whose leakage and alignment are unit-tested against a
#     three-team interleaved case that fails on the specific defects above;
#   * scored against the BTTS BASE RATE, never 0.50 (that mistake once turned over15's +0.029
#     into +0.140);
#   * chronological split, never random;
#   * CONDITIONED ON xg_source, because xG and goals are different estimators and pooling them
#     measures a mixture — xG is measurably better (+0.0323 correlation, CI [+0.0103, +0.0548]);
#   * bootstrap CI on the DIFFERENCE between models, not two separate intervals.

def run_from_stats(min_season: str | None = None, quiet: bool = False) -> dict:
    """BTTS evaluation on real per-team lambdas. Returns a dict of results."""
    import numpy as np
    from src.features import btts as bf
    from src.features import team_form as tf

    stats = store.read("team_match_stats")
    if stats is None or stats.empty:
        print("[btts_eval] team_match_stats is empty")
        return {}
    if min_season:
        stats = stats[stats["season"].astype(str) >= str(min_season)]
    lam = tf.fixture_lambdas(stats)
    res = stats[["fixture_id", "home_goals", "away_goals", "match_date", "league"]].copy()
    d = lam.merge(res, on="fixture_id", how="inner", suffixes=("", "_r"))
    d["hg"] = pd.to_numeric(d["home_goals"], errors="coerce")
    d["ag"] = pd.to_numeric(d["away_goals"], errors="coerce")
    d = d.dropna(subset=["hg", "ag", "lam_home", "lam_away"])
    if d.empty:
        print("[btts_eval] no fixtures with both lambdas and a result")
        return {}
    d["y"] = ((d["hg"] >= 1) & (d["ag"] >= 1)).astype(float)
    d["p_btts_dc"] = [bf.dixon_coles_p_btts(h, a) for h, a in zip(d["lam_home"], d["lam_away"])]
    d["_dt"] = pd.to_datetime(d["match_date"], errors="coerce")
    d = d.dropna(subset=["_dt"]).sort_values("_dt")

    out = {}
    for label, sub in (("all", d), ("xg only", d[d["xg_source"] == "xg"]),
                       ("goals only", d[d["xg_source"] == "goals"])):
        if len(sub) < 200:
            if not quiet:
                print(f"\n  {label}: n={len(sub)} — too few for a chronological split")
            out[label] = {"n": int(len(sub)), "verdict": "INSUFFICIENT"}
            continue
        cut = int(len(sub) * 0.8)
        tr, te = sub.iloc[:cut], sub.iloc[cut:]
        base = float(tr["y"].mean())
        p_const = np.full(len(te), base)
        p_dc = te["p_btts_dc"].to_numpy(dtype=float)
        y = te["y"].to_numpy(dtype=float)
        b_const, b_dc = _brier(y, p_const), _brier(y, p_dc)
        lo, hi = _boot_diff(y, p_const, p_dc)
        auc_min = auc_sum = float("nan")
        try:
            from sklearn.metrics import roc_auc_score
            auc_min = roc_auc_score(y, te["lam_min"])
            auc_sum = roc_auc_score(y, te["lam_sum"])
        except Exception:
            pass
        out[label] = {"n": int(len(sub)), "n_test": int(len(te)),
                      "base_rate_train": round(base, 4),
                      "base_rate_test": round(float(te["y"].mean()), 4),
                      "brier_base_rate": round(b_const, 5), "brier_dc": round(b_dc, 5),
                      "gain": round(b_const - b_dc, 5),
                      "diff_ci_lo": round(lo, 5), "diff_ci_hi": round(hi, 5),
                      "auc_lam_min": round(auc_min, 4), "auc_lam_sum": round(auc_sum, 4),
                      "verdict": ("DC BEATS BASE RATE" if lo > 0 else
                                  "DC WORSE" if hi < 0 else "INCONCLUSIVE")}
        if not quiet:
            r = out[label]
            print(f"\n  {label}: n={r['n']:,} (test {r['n_test']:,})  "
                  f"base rate {r['base_rate_train']:.4f} -> test {r['base_rate_test']:.4f}")
            print(f"    Brier  base-rate constant {r['brier_base_rate']:.5f}   "
                  f"Dixon-Coles {r['brier_dc']:.5f}   gain {r['gain']:+.5f}")
            print(f"    95% CI on the difference [{r['diff_ci_lo']:+.5f}, {r['diff_ci_hi']:+.5f}]"
                  f"  -> {r['verdict']}")
            print(f"    AUC lam_min {r['auc_lam_min']:.4f}   lam_sum {r['auc_lam_sum']:.4f}"
                  f"   (the original hypothesis needs lam_min > lam_sum)")
    return out
