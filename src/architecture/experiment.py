"""PHASE D — does the recovered data actually predict better? Old frame vs canonical frame.

    python -m src.architecture.experiment --write

The audit can prove that 23,169 completed fixtures never reach training. It cannot prove that
including them helps, and section 46 is explicit that more rows is not the same as better rows.
It is entirely possible that 22,000 recovered fixtures are noisier than the 58,000 we already
had and make prediction worse. That is a measurement, so this measures it.

THE ONLY THING THAT DIFFERS IS THE DATASET. Same feature builder, same model family, same
hyper-parameters, same chronological split, same targets, and -- the part that matters most --
THE SAME TEST FIXTURES. Evaluating A on its own fixtures and B on its own would compare two
different exams and report the difference as skill.

So the test set is the INTERSECTION of the two datasets, after a fixed date. Both models are
asked exactly the same questions; only their study material differs. Training rows come from
each dataset's own pre-cutoff history, which is the whole point: the canonical frame has more
history and, for the leagues that were thin, better-populated columns.

FEATURES COME FROM THE PREDICTION LAB, deliberately. `src.prediction_lab.features` is already
perturbation-tested -- randomise the future, rebuild, and every past value is bit-identical --
so reusing it means this experiment inherits that guarantee instead of re-earning it with a
second, unproven feature builder.

WHAT A NULL RESULT WOULD MEAN, stated before the run so it cannot be reinterpreted afterwards:
if the canonical frame does not beat the old one on log loss across most targets and folds, then
the architecture work is still worth doing for reproducibility and freshness, but it is NOT
worth doing on the grounds that it improves prediction, and the report must say so.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.architecture import canonical as C
from src.prediction_lab import data as D
from src.prediction_lab import experiments as E
from src.prediction_lab import features as F
from src.prediction_lab import folds as FO

CALC_VERSION = "1.0.0"
TARGETS = ("btts", "over15", "over25", "over35")


def _prepare(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Give a raw fixture frame everything the lab's feature builder expects."""
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date", "home_goals", "away_goals"])
    d["league"] = d["league"].astype(str).str.strip()
    for c in ("home_team", "away_team"):
        d[c] = d[c].astype(str).str.strip()
    # ALWAYS rebuild the key, never inherit one. The canonical frame arrives carrying a key of
    # the form date|home|away (entity.fixture_key, which has no league in it) while the old
    # frame has none at all, so trusting whatever is present produced two different key formats
    # and an intersection of exactly ZERO fixtures -- a comparison that would silently have had
    # nothing to compare.
    d["fixture_key"] = (d["date"].dt.strftime("%Y-%m-%d") + "|" + d["league"] + "|"
                        + d["home_team"] + "|" + d["away_team"])
    d["model_type"] = d["league"].map(D.model_type_for_league)
    d["season_label"] = D._season_label(d["date"])
    d = D._attach_targets(d)
    d = (d.sort_values("date", kind="mergesort")
           .drop_duplicates("fixture_key", keep="last").reset_index(drop=True))
    print(f"  [{label}] {len(d):,} fixtures {d.date.min().date()}..{d.date.max().date()}")
    return d


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    old = _prepare(D._read_v9_parquet("output/fd_history.parquet"), "OLD fd_history")
    can, _ = C.build()
    can = _prepare(can[can["trainable"]], "CANONICAL")
    return old, can


def run(*, test_frac: float = 0.18, model: str = "hgb") -> tuple:
    old, can = load_frames()
    fo = F.build(old)
    fc = F.build(can)

    common = sorted(set(fo.fixture_key) & set(fc.fixture_key))
    print(f"\n  fixtures in BOTH datasets: {len(common):,}")
    cdates = fo.set_index("fixture_key").loc[common, "date"]
    cutoff = pd.Timestamp(cdates.quantile(1 - test_frac))
    test_keys = set(cdates[cdates >= cutoff].index)
    print(f"  common test set: {len(test_keys):,} fixtures from {cutoff.date()} onward")

    # QUALITY TIERS (sections 46-47). If the canonical frame does not win, the next question is
    # whether the recovered rows are simply thinner -- 22,448 of them are RESULT_ONLY, carrying a
    # score and nothing else. Training on "everything" and on "only the rows that carry shots"
    # separates "more data does not help" from "more data helps but this particular data is too
    # thin to help". Those are different findings with different consequences.
    variants = [("old_v9_fd_history", fo), ("canonical", fc)]
    if "quality_tier" in can.columns:
        rich_keys = set(can.loc[can.quality_tier.isin(("FULL_FEATURE", "ADVANCED")),
                                "fixture_key"])
        fc_rich = fc[fc.fixture_key.isin(rich_keys) | fc.fixture_key.isin(test_keys)].copy()
        variants.append(("canonical_full_feature_only", fc_rich))
        print(f"  canonical restricted to FULL_FEATURE/ADVANCED: {len(fc_rich):,} rows")

    rows = []
    per_row_loss: dict[tuple, np.ndarray] = {}
    for name, frame in variants:
        cols = F.feature_columns(frame, F.FOOTBALL_FAMILIES)
        is_test = frame["fixture_key"].isin(test_keys).to_numpy()
        is_train = (pd.to_datetime(frame["date"]) < cutoff).to_numpy()
        tr = np.flatnonzero(is_train)
        te_idx = {k: i for i, k in enumerate(frame["fixture_key"]) if k in test_keys}
        te = np.array([te_idx[k] for k in sorted(test_keys) if k in te_idx])
        if len(te) == 0 or len(tr) < 2000:
            continue
        # Validation = last 12% of the training period, for the decision threshold only.
        vcut = np.quantile(pd.to_datetime(frame["date"]).to_numpy()[tr].astype("datetime64[ns]")
                           .astype("int64"), 0.88)
        va = tr[pd.to_datetime(frame["date"]).to_numpy()[tr].astype("datetime64[ns]")
                .astype("int64") >= vcut]
        tr2 = tr[pd.to_datetime(frame["date"]).to_numpy()[tr].astype("datetime64[ns]")
                 .astype("int64") < vcut]
        fold = [FO.Fold(name="single", train=tr2, val=va, test=te,
                        t_start=str(cutoff.date()), t_end=str(frame["date"].max())[:10])]
        for t in TARGETS:
            oof = E.walk_forward(frame, t, cols, model=model, fold_list=fold)
            if oof.empty:
                continue
            r = E.score(oof, label=f"{name}/{t}")
            r.update({"dataset": name, "target": t, "train_rows": int(len(tr2)),
                      "test_rows": int(len(te)), "n_features": len(cols),
                      "cutoff": str(cutoff.date())})
            rows.append(r)
            g = oof.sort_values("fixture_key", kind="mergesort")
            pr = np.clip(g["p"].to_numpy(dtype=float), 1e-15, 1 - 1e-15)
            yy = g["y"].to_numpy(dtype=float)
            per_row_loss[(name, t)] = -(yy * np.log(pr) + (1 - yy) * np.log(1 - pr))
            print(f"   {name:<20}{t:<8}train={len(tr2):>6,} test={r['n']:>6,} "
                  f"ll={r['log_loss']:.5f} brier={r['brier']:.5f} auc={r['auc']:.4f} "
                  f"lift={r['lift_pp']:+.2f}pp")
    return pd.DataFrame(rows), per_row_loss


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    tab, losses = run()
    if tab.empty:
        print("no results")
        return 1
    print("\n" + "=" * 86)
    print("OLD vs CANONICAL — identical test fixtures, identical model, only the data differs")
    print("=" * 86)
    piv = tab.pivot_table(index="target", columns="dataset",
                          values=["log_loss", "brier", "auc", "lift_pp"])
    print(piv.round(5).to_string())
    wins = 0
    print(f"\n  {'target':<9}{'old ll':>10}{'canon ll':>11}{'delta':>10}  verdict")
    for t in TARGETS:
        o = tab[(tab.target == t) & (tab.dataset == "old_v9_fd_history")]["log_loss"]
        c = tab[(tab.target == t) & (tab.dataset == "canonical")]["log_loss"]
        if o.empty or c.empty:
            continue
        d = float(c.iloc[0] - o.iloc[0])
        better = d < 0
        wins += int(better)
        print(f"  {t:<9}{o.iloc[0]:>10.5f}{c.iloc[0]:>11.5f}{d:>+10.5f}  "
              f"{'canonical better' if better else 'old better'}")
    print(f"\n  canonical wins on {wins} of {len(TARGETS)} targets")

    # IS ANY OF THIS REAL? A log-loss delta of 0.0005 on 10,561 fixtures is well inside
    # resampling noise, and reading a 2-of-4 split as a verdict without testing it is the same
    # mistake as reading a coin flip as a trend. Paired on the per-fixture losses, blocked by 8
    # because same-matchday fixtures share weather, team news and referee assignment.
    from src.validation.multiple_testing import paired_bootstrap_p
    print(f"\n  {'target':<9}{'comparison':<30}{'diff':>10}{'90% CI':>23}{'p':>8}  real?")
    boots = []
    for t in TARGETS:
        base = losses.get(("old_v9_fd_history", t))
        for alt in ("canonical", "canonical_full_feature_only"):
            other = losses.get((alt, t))
            if base is None or other is None or len(base) != len(other):
                continue
            pv, obs, ci = paired_bootstrap_p(other, base, n_boot=3000, block=8)
            real = bool(ci[0] > 0 or ci[1] < 0)
            boots.append({"target": t, "comparison": f"{alt}_vs_old", "mean_diff": obs,
                          "ci_lo": ci[0], "ci_hi": ci[1], "p_value": pv, "significant": real,
                          "direction": "alt better" if obs > 0 else "old better"})
            print(f"  {t:<9}{alt + ' vs old':<30}{obs:>+10.5f}"
                  f"{f'[{ci[0]:+.5f},{ci[1]:+.5f}]':>23}{pv:>8.3f}  "
                  f"{'YES' if real else 'no - inside noise'}")
    print(f"\n  statistically distinguishable: {sum(1 for b in boots if b['significant'])} "
          f"of {len(boots)} comparisons")
    if a.write:
        out = cfg.OUTPUT_DIR / "architecture"
        out.mkdir(parents=True, exist_ok=True)
        tab.to_csv(out / "training_dataset_comparison.csv", index=False)
        pd.DataFrame(boots).to_csv(out / "training_dataset_bootstrap.csv", index=False)
        print(f"[experiment] wrote training_dataset_comparison.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
