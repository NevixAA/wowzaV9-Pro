"""Runner for the match-level research. Every phase is a subcommand.

    python -m src.prediction_lab.run all
    python -m src.prediction_lab.run baselines tournament ablation

Phases, in the order the research actually has to happen (rule 41):

    dataset      build + cache the leakage-safe feature matrix
    baselines    rock vs league-prior vs football model, per target   -> target_performance.csv
    tournament   which model family, consistently across folds        -> model_comparison.csv
    ablation     which FEATURE FAMILIES carry the information         -> feature_ablation.csv
    windows      how much history to keep, and does recency help      -> time_ablation.csv
    market       football vs market vs both                           -> market_ablation.csv
    leagues      per league, and whether league-specific models help  -> league_performance.csv
    curves       is more data still improving anything                -> learning_curves.csv
    confidence   does a higher stated probability really happen more  -> confidence_calibration.csv

Nothing here writes to v9, loads a v9 model, or changes a threshold that anything reads.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import pandas as pd

from src.prediction_lab import data as D
from src.prediction_lab import experiments as E
from src.prediction_lab import features as F
from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M

PRIMARY_TARGETS = ("btts", "over15", "over25", "over35")
SECONDARY_TARGETS = ("home_scores", "away_scores", "home_2plus", "away_2plus")
CACHE = "feature_matrix.parquet"


def load(*, rebuild: bool = False) -> pd.DataFrame:
    p = D.out_dir() / CACHE
    if p.exists() and not rebuild:
        return pd.read_parquet(p)
    fx = D.load_fixtures()
    df = F.build(fx)
    df.to_parquet(p, index=False)
    return df


def _say(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------------------------

def phase_baselines(df, fl, out):
    """The headline table. Every target, against the rock it has to beat."""
    fc = F.feature_columns(df, F.FOOTBALL_FAMILIES)
    rows, oofs, conf, topk = [], {}, [], []
    for t in PRIMARY_TARGETS + SECONDARY_TARGETS:
        for name, oof in (("majority", E.baseline_majority(df, t, fl)),
                          ("league_prior", E.baseline_league_prior(df, t, fl)),
                          ("football_hgb", E.walk_forward(df, t, fc, model="hgb", fold_list=fl))):
            r = E.score(oof, label=f"{t}/{name}", boot=(name == "football_hgb"))
            r.update({"target": t, "model": name})
            rows.append(r)
            if name == "football_hgb":
                oofs[t] = oof
                c = M.confidence_table(oof.y.to_numpy(), oof.p.to_numpy()); c["target"] = t
                conf.append(c)
                k = M.top_k_table(oof.y.to_numpy(), oof.p.to_numpy()); k["target"] = t
                topk.append(k)
        _say(f"  {t:<12} rock={rows[-1]['rock_accuracy']:.4f}  "
             f"prior={rows[-3]['model_accuracy']:.4f}  football={rows[-1]['model_accuracy']:.4f} "
             f"(lift {rows[-1]['lift_pp']:+.2f}pp, auc {rows[-1]['auc']:.4f})")
    pd.DataFrame(rows).to_csv(out / "target_performance.csv", index=False)
    pd.concat(conf).to_csv(out / "confidence_calibration.csv", index=False)
    pd.concat(topk).to_csv(out / "confidence_topk.csv", index=False)
    # Per-fold stability for the football model on the four primary targets.
    pf = pd.concat([E.per_fold(oofs[t]).assign(target=t) for t in PRIMARY_TARGETS])
    pf.to_csv(out / "chronological_folds.csv", index=False)
    # The OOS probability frame is the input to the cross-market track. Keep it.
    allp = pd.concat([oofs[t] for t in PRIMARY_TARGETS + SECONDARY_TARGETS], ignore_index=True)
    allp.to_parquet(out / "oof_probabilities.parquet", index=False)
    return rows


def phase_tournament(df, fl, out, *, targets=PRIMARY_TARGETS):
    """Model families, scored the same way, on the same folds (rule 19)."""
    fc = F.feature_columns(df, F.FOOTBALL_FAMILIES)
    zoo = FO.model_zoo()
    rows = []
    for t in targets:
        for name in zoo:
            t0 = time.time()
            oof = E.walk_forward(df, t, fc, model=name, fold_list=fl, zoo=zoo)
            if oof.empty:
                continue
            r = E.score(oof, label=f"{t}/{name}")
            r.update({"target": t, "model": name, "fit_seconds": round(time.time() - t0, 1)})
            # Fold-level wins matter more than the pooled number (rule 33).
            pf = E.per_fold(oof)
            r["folds"] = len(pf)
            r["fold_ll_spread"] = float(pf["log_loss"].max() - pf["log_loss"].min())
            rows.append(r)
            _say(f"  {t:<8}{name:<15}ll={r['log_loss']:.4f} brier={r['brier']:.4f} "
                 f"auc={r['auc']:.4f} lift={r['lift_pp']:+.2f}pp  [{r['fit_seconds']}s]")
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "model_comparison.csv", index=False)
    return tab


def phase_ablation(df, fl, out, *, targets=PRIMARY_TARGETS, model="hgb"):
    """Which FEATURE FAMILIES carry information. Measured two ways, because one is not enough.

    ADD-ONE: BASE alone, then BASE + one family. Says what a family is worth on its own.
    DROP-ONE: everything, then everything minus one family. Says what a family is worth once the
    others are already there -- which is usually much less, because football features are highly
    redundant. A family can look useful in add-one and worthless in drop-one; that difference IS
    the finding, not a contradiction (rule 18).
    """
    fam = F.family_columns(df)
    full = [f for f in F.FOOTBALL_FAMILIES if fam.get(f)]
    rows = []
    for t in targets:
        base_cols = fam["BASE"]
        r0 = E.score(E.walk_forward(df, t, base_cols, model=model, fold_list=fl))
        rows.append({"target": t, "mode": "reference", "family": "BASE_only",
                     "n_features": len(base_cols), **_keep(r0)})
        r_full = E.score(E.walk_forward(df, t, F.feature_columns(df, full),
                                        model=model, fold_list=fl))
        rows.append({"target": t, "mode": "reference", "family": "ALL_FOOTBALL",
                     "n_features": len(F.feature_columns(df, full)), **_keep(r_full)})
        for f in full:
            if f == "BASE":
                continue
            cols = base_cols + fam[f]
            r = E.score(E.walk_forward(df, t, cols, model=model, fold_list=fl))
            rows.append({"target": t, "mode": "add_one", "family": f, "n_features": len(cols),
                         **_keep(r), "d_log_loss": r["log_loss"] - r0["log_loss"],
                         "d_brier": r["brier"] - r0["brier"],
                         "d_accuracy_pp": (r["model_accuracy"] - r0["model_accuracy"]) * 100})
            keep = [x for x in full if x != f]
            r2 = E.score(E.walk_forward(df, t, F.feature_columns(df, keep),
                                        model=model, fold_list=fl))
            rows.append({"target": t, "mode": "drop_one", "family": f,
                         "n_features": len(F.feature_columns(df, keep)), **_keep(r2),
                         "d_log_loss": r2["log_loss"] - r_full["log_loss"],
                         "d_brier": r2["brier"] - r_full["brier"],
                         "d_accuracy_pp": (r2["model_accuracy"] - r_full["model_accuracy"]) * 100})
            _say(f"  {t:<8}{f:<12} add dLL={rows[-2]['d_log_loss']:+.5f}   "
                 f"drop dLL={rows[-1]['d_log_loss']:+.5f}")
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "feature_ablation.csv", index=False)
    return tab


def _keep(r: dict) -> dict:
    return {k: r[k] for k in ("n", "log_loss", "brier", "auc", "model_accuracy",
                              "rock_accuracy", "lift_pp", "ece")}


def phase_windows(df, fl, out, *, targets=PRIMARY_TARGETS):
    """How much old football to remember, and whether recency weighting helps (rule 20)."""
    fc = F.feature_columns(df, F.FOOTBALL_FAMILIES)
    rows = []
    settings = [("expanding", None, None), ("last_4y", 1460, None), ("last_3y", 1095, None),
                ("last_2y", 730, None), ("last_1y", 365, None),
                ("expanding_hl_1y", None, 365.0), ("expanding_hl_2y", None, 730.0)]
    for t in targets:
        for name, win, hl in settings:
            oof = E.walk_forward(df, t, fc, model="hgb", fold_list=fl,
                                 train_window_days=win, halflife_days=hl)
            if oof.empty:
                continue
            r = E.score(oof, label=f"{t}/{name}")
            r.update({"target": t, "setting": name, "train_window_days": win, "halflife_days": hl})
            rows.append(r)
            _say(f"  {t:<8}{name:<18}ll={r['log_loss']:.4f} brier={r['brier']:.4f} "
                 f"lift={r['lift_pp']:+.2f}pp")
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "time_ablation.csv", index=False)
    return tab


def phase_market(df, fl, out, *, targets=PRIMARY_TARGETS):
    """Football-only vs market-only vs both. THE table (rule 38).

    Restricted to fixtures that actually carry a real de-vigged price, because a market model
    scored on rows with no market is not a market model. That subset is roughly a fifth of the
    data and is reported as such -- comparing a football number from 26,000 fixtures against a
    market number from 5,000 different ones would be meaningless.
    """
    fam = F.family_columns(df)
    mkt = fam["MARKET"]
    football = F.feature_columns(df, F.FOOTBALL_FAMILIES)
    have = df["mkt_p_over25"].notna().to_numpy()
    sub = df[have].reset_index(drop=True)
    _say(f"  market subset: {len(sub):,} of {len(df):,} fixtures ({have.mean():.1%}) "
         f"with a real two-sided OU2.5 price")
    if len(sub) < 3000:
        _say("  too few priced fixtures for a fold structure; skipping")
        return pd.DataFrame()
    sfl = FO.rolling_folds(sub, n_folds=3)
    rows = []
    for t in targets:
        for name, cols in (("base_only", fam["BASE"]),
                           ("football_only", football),
                           ("market_only", fam["BASE"] + mkt),
                           ("football_plus_market", football + mkt)):
            oof = E.walk_forward(sub, t, cols, model="hgb", fold_list=sfl)
            if oof.empty:
                continue
            r = E.score(oof, label=f"{t}/{name}")
            r.update({"target": t, "information": name, "n_features": len(cols)})
            rows.append(r)
            _say(f"  {t:<8}{name:<22}n={r['n']:,} ll={r['log_loss']:.4f} "
                 f"brier={r['brier']:.4f} auc={r['auc']:.4f} lift={r['lift_pp']:+.2f}pp")
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "market_ablation.csv", index=False)
    return tab


def phase_leagues(df, fl, out):
    """Per league, and whether a league-specific model beats the global one (rule 16)."""
    fc = F.feature_columns(df, F.FOOTBALL_FAMILIES)
    rows = []
    for t in PRIMARY_TARGETS:
        oof = E.walk_forward(df, t, fc, model="hgb", fold_list=fl)
        bl = E.by_league(oof)
        bl["target"] = t
        bl["scope"] = "global_model"
        rows.append(bl)
    glob = pd.concat(rows, ignore_index=True)

    # League-specific models, only where there is enough data to fit one honestly.
    big = (df.groupby("league").size().sort_values(ascending=False))
    per = []
    for lg in big[big >= 2500].index:
        sub = df[df.league == lg].reset_index(drop=True)
        try:
            lfl = FO.rolling_folds(sub, n_folds=3, min_train=1200)
        except ValueError:
            continue
        for t in PRIMARY_TARGETS:
            oof = E.walk_forward(sub, t, fc, model="hgb", fold_list=lfl)
            if oof.empty:
                continue
            r = E.score(oof, label=f"{lg}/{t}")
            r.update({"league": lg, "target": t, "scope": "league_specific",
                      "interpretable": r["n"] >= 150})
            per.append(r)
            _say(f"  {lg:<28}{t:<8}league-specific ll={r['log_loss']:.4f} "
                 f"lift={r['lift_pp']:+.2f}pp  (n={r['n']:,})")
    tab = pd.concat([glob, pd.DataFrame(per)], ignore_index=True) if per else glob
    tab.to_csv(out / "league_performance.csv", index=False)
    return tab


def phase_curves(df, out, *, targets=PRIMARY_TARGETS):
    fc = F.feature_columns(df, F.FOOTBALL_FAMILIES)
    rows = []
    for t in targets:
        c = E.learning_curve(df, t, fc)
        c["target"] = t
        rows.append(c)
        for _, r in c.iterrows():
            _say(f"  {t:<8}train={int(r.train_n):>6}  ll={r.log_loss:.4f}  "
                 f"brier={r.brier:.4f}  lift={r.lift_pp:+.2f}pp")
    tab = pd.concat(rows, ignore_index=True)
    tab.to_csv(out / "learning_curves.csv", index=False)
    return tab


PHASES = {"baselines": phase_baselines, "tournament": phase_tournament,
          "ablation": phase_ablation, "windows": phase_windows, "market": phase_market,
          "leagues": phase_leagues}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phases", nargs="*", default=["all"])
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--folds", type=int, default=FO.DEFAULT_N_FOLDS)
    a = ap.parse_args()
    want = a.phases or ["all"]
    if "all" in want:
        want = list(PHASES) + ["curves"]

    out = D.out_dir()
    t0 = time.time()
    df = load(rebuild=a.rebuild)
    fl = FO.rolling_folds(df, n_folds=a.folds)
    _say(f"[lab] {len(df):,} fixtures, {len(fl)} chronological folds")
    for f in fl:
        _say(f"      {f.describe()}")

    manifest = {"generated_at": pd.Timestamp.utcnow().isoformat(), "rows": int(len(df)),
                "folds": [f.describe() for f in fl], "phases": []}
    for p in want:
        _say(f"\n=== {p.upper()} ===")
        s = time.time()
        if p == "curves":
            phase_curves(df, out)
        else:
            PHASES[p](df, fl, out)
        manifest["phases"].append({"phase": p, "seconds": round(time.time() - s, 1)})
    (out / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str),
                                                encoding="utf-8")
    _say(f"\n[lab] done in {time.time() - t0:.0f}s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
