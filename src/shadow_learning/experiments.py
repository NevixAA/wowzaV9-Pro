"""Controlled dataset experiments: which observations actually earn their place?

    python -m src.shadow_learning.experiments --group core --write
    python -m src.shadow_learning.experiments --group all --write

Sections 7-11 and 20. Every variant is scored on THE SAME TEST FIXTURES with the same model,
the same features and the same chronological folds. Only the training data changes.

THE ONE DESIGN CHOICE WORTH ARGUING ABOUT, stated rather than buried. A "dataset variant" can
mean two different things and they answer different questions:

    (1) same feature matrix, fewer TRAINING ROWS      -> does adding rows to the fit help?
    (2) a smaller DATA UNIVERSE, features rebuilt      -> does having this data at all help?

Under (2) a fixture's rolling-form features change when you remove the matches behind them,
which is the realistic consequence of adopting or not adopting a dataset -- a team's last-5 form
is only computable if those five matches are in the universe. So the incremental-data variants
use (2), and the ones where the universe is genuinely identical and only the FIT changes
(duplicate handling, recency weighting) use (1). Each variant records which it used, because
comparing a (1) against a (2) and reading the difference as data value would be wrong.

TEST FIXTURES ARE THE INTERSECTION, always. A fixture only enters the test set if EVERY variant
can produce a prediction for it. Scoring one model on 5,000 fixtures and another on a different
4,000 and calling one better is the failure section 15 exists to prevent.

NOTHING HERE IS PROMOTED. v9 stays champion; these are shadow measurements.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.prediction_lab import data as D
from src.prediction_lab import experiments as E
from src.prediction_lab import features as F
from src.prediction_lab import folds as FO
from src.shadow_learning import datasets as DS

CALC_VERSION = "1.0.0"
TARGETS = ("btts", "over15", "over25", "over35")
N_FOLDS = 3
TEST_FRAC = 0.18
# COVID period by DATE, not by season label -- the label is exactly what does not match.
COVID_START, COVID_END = pd.Timestamp("2020-03-01"), pd.Timestamp("2021-06-30")


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _prepare(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date", "home_goals", "away_goals"])
    d["league"] = d["league"].astype(str).str.strip()
    for c in ("home_team", "away_team"):
        d[c] = d[c].astype(str).str.strip()
    d["fixture_key"] = (d["date"].dt.strftime("%Y-%m-%d") + "|" + d["league"] + "|"
                        + d["home_team"] + "|" + d["away_team"])
    d["model_type"] = d["league"].map(D.model_type_for_league)
    d["season_label"] = D._season_label(d["date"])
    d = D._attach_targets(d)
    return (d.sort_values("date", kind="mergesort")
              .drop_duplicates("fixture_key", keep="last").reset_index(drop=True))


def universes() -> dict:
    """Named fixture-key sets. Everything else is built from these."""
    v9u = DS.v9_universe()
    v9u["date"] = pd.to_datetime(v9u["date"], errors="coerce")
    can = DS.canonical()
    can = can[can["trainable"]]

    v9_keys = set(v9u.loc[v9u["in_v9_training"], "fixture_key"])
    can_keys = set(can["fixture_key"])
    inc = can[~can["fixture_key"].isin(v9_keys)].copy()
    inc["age_days"] = (pd.Timestamp.now().normalize() - inc["date"]).dt.days

    graded = DS._grade(inc)
    hq = set(graded.loc[graded["tier"].isin(("MARKET", "STANDARD_PLUS")), "fixture_key"])
    recent = set(inc.loc[inc["age_days"] <= 3 * 365, "fixture_key"])

    return {"v9": v9_keys, "canonical": can_keys, "incremental": set(inc["fixture_key"]),
            "incremental_recent": recent, "incremental_hq": hq,
            "incremental_recent_hq": recent & hq,
            "_can_frame": can, "_v9_frame": v9u}


def _variants(group: str, U: dict) -> list[dict]:
    """(name, fixture-key set, weight scheme, mode, note)."""
    v9, can, inc = U["v9"], U["canonical"], U["incremental"]
    out = []

    def add(name, keys, *, weights=None, mode="universe", note="", train_filter=None):
        out.append({"name": name, "keys": keys, "weights": weights, "mode": mode,
                    "note": note, "train_filter": train_filter})

    if group in ("core", "all"):
        add("A_v9_current", v9, note="the champion dataset, exactly as v9 builds it")
        add("B_canonical_full", can, note="everything")
        add("C_v9_plus_recent_incremental", v9 | U["incremental_recent"],
            note="incremental fixtures newer than 3 years")
        add("D_v9_plus_hq_incremental", v9 | U["incremental_hq"],
            note="incremental fixtures in the MARKET/STANDARD_PLUS tiers")
        add("E_v9_plus_recent_hq", v9 | U["incremental_recent_hq"],
            note="both filters")
    if group in ("window", "all"):
        for yrs in (1, 2, 3, 4, 5):
            add(f"W_last_{yrs}y", can, mode="fit",
                train_filter=("years", yrs),
                note=f"canonical universe, fit only on the last {yrs} year(s)")
        add("W_expanding", can, mode="fit", note="canonical universe, all of it")
    if group in ("recency", "all"):
        for hl in (180, 365, 730):
            add(f"R_halflife_{hl}d", can, weights=("halflife", hl), mode="fit",
                note=f"exponential decay, half-life {hl} days")
        add("R_linear_decay", can, weights=("linear", None), mode="fit",
            note="linear decay from oldest to newest")
        add("R_none", can, mode="fit", note="no weighting -- the control")
    if group in ("dupes", "all"):
        add("X_dupes_as_v9_does", v9, mode="fit_dupes",
            note="v9's actual behaviour: duplicate rows retained")
        add("X_dupes_removed", v9, mode="fit",
            note="one row per canonical fixture")
        add("X_dupes_as_weights", v9, mode="fit_dupeweight",
            note="deduplicated, but duplicated fixtures weighted 2x")
    if group in ("covid", "all"):
        add("V_covid_kept", can, mode="fit", note="current behaviour -- filter removes nothing")
        add("V_covid_excluded_by_date", can, mode="fit", train_filter=("covid", None),
            note="2020-03-01..2021-06-30 removed by DATE, not by season label")
    if group in ("completeness", "all"):
        g = DS._grade(U["_can_frame"])
        for tier in ("MARKET", "STANDARD_PLUS", "STANDARD"):
            keys = set(g.loc[g["tier"].isin(
                {"MARKET": ("MARKET",),
                 "STANDARD_PLUS": ("MARKET", "STANDARD_PLUS"),
                 "STANDARD": ("MARKET", "STANDARD_PLUS", "STANDARD")}[tier]), "fixture_key"])
            add(f"Q_{tier}_complete_only", keys,
                note=f"only fixtures reaching the {tier} completeness tier")
    return out


def _weights(dates: np.ndarray, scheme) -> np.ndarray | None:
    if scheme is None:
        return None
    kind, param = scheme
    d = pd.to_datetime(pd.Series(dates))
    age = (d.max() - d).dt.days.to_numpy().astype(float)
    if kind == "halflife":
        return np.power(0.5, age / float(param))
    if kind == "linear":
        span = max(age.max(), 1.0)
        return 1.0 - 0.9 * (age / span)
    return None


def run(group: str = "core") -> tuple[pd.DataFrame, pd.DataFrame]:
    U = universes()
    can = U["_can_frame"]
    v9u = U["_v9_frame"]
    base = _prepare(can)
    # v9-only fixtures that canonical lacks would make the intersection asymmetric; there is
    # exactly one, so the universes are effectively nested and the test set is unaffected.
    variants = _variants(group, U)
    print(f"[shadow] {len(variants)} variants in group '{group}'")

    # THE TEST SET: fixtures every variant can predict, i.e. present in all universes.
    common = set.intersection(*[v["keys"] for v in variants]) & set(base["fixture_key"])
    bd = base[base["fixture_key"].isin(common)]
    cutoff = pd.Timestamp(bd["date"].quantile(1 - TEST_FRAC))
    test_keys = set(bd.loc[bd["date"] >= cutoff, "fixture_key"])
    print(f"[shadow] common fixtures {len(common):,}; test set {len(test_keys):,} "
          f"from {cutoff.date()}")

    # DUPLICATES LIVE IN V9'S LOADER, NOT IN THE CANONICAL FRAME.
    #
    # The first version counted rows per fixture_key in the v9 universe frame -- but the probe
    # already deduplicated that frame, so every count came back 1 and all three duplicate
    # variants produced byte-identical results. A no-op experiment that looks like a null
    # result is worse than no experiment. The probe does carry `is_duplicate_row`, computed
    # BEFORE its dedupe, so that is the usable signal: a fixture v9 sees twice.
    dup_flag = (v9u.loc[v9u["in_v9_training"]].set_index("fixture_key")["is_duplicate_row"]
                if "is_duplicate_row" in v9u.columns else None)

    rows, losses = [], {}
    for v in variants:
        keys = v["keys"] | test_keys                 # test rows must exist in every frame
        sub = base[base["fixture_key"].isin(keys)].reset_index(drop=True)
        feat = F.build(sub) if v["mode"] == "universe" else F.build(base)
        if v["mode"] != "universe":
            feat = feat[feat["fixture_key"].isin(keys)].reset_index(drop=True)
        cols = F.feature_columns(feat, F.FOOTBALL_FAMILIES)
        dates = pd.to_datetime(feat["date"]).to_numpy()
        is_test = feat["fixture_key"].isin(test_keys).to_numpy()
        tr = np.flatnonzero((dates < np.datetime64(cutoff)) & ~is_test)

        tf = v.get("train_filter")
        if tf and tf[0] == "years":
            tr = tr[dates[tr] >= (np.datetime64(cutoff) - np.timedelta64(int(tf[1] * 365), "D"))]
        if tf and tf[0] == "covid":
            m = (dates[tr] < np.datetime64(COVID_START)) | (dates[tr] > np.datetime64(COVID_END))
            tr = tr[m]
        if len(tr) < 2000:
            print(f"   {v['name']:<32} skipped (only {len(tr)} training rows)")
            continue

        w = _weights(dates[tr], v["weights"])
        if v["mode"] in ("fit_dupes", "fit_dupeweight") and dup_flag is not None:
            rep = np.where(feat["fixture_key"].map(dup_flag).fillna(False).to_numpy()[tr],
                           2.0, 1.0)
            w = (w if w is not None else np.ones(len(tr))) * rep

        te = np.flatnonzero(is_test)
        vcut = np.quantile(dates[tr].astype("datetime64[ns]").astype("int64"), 0.88)
        va = tr[dates[tr].astype("datetime64[ns]").astype("int64") >= vcut]
        tr2 = tr[dates[tr].astype("datetime64[ns]").astype("int64") < vcut]
        fold = [FO.Fold(name="f1", train=tr2, val=va, test=te,
                        t_start=str(cutoff.date()), t_end=str(feat["date"].max())[:10])]
        for t in TARGETS:
            # Weights are built per TRAINING ROW; walk_forward indexes a full-length vector,
            # so scatter them back. The first version computed `w` and never passed it, which
            # is why all five recency variants returned identical numbers.
            sw = None
            if w is not None:
                sw = np.ones(len(feat), dtype=float)
                sw[tr] = w
            oof = E.walk_forward(feat, t, cols, model="hgb", fold_list=fold, sample_weight=sw)
            if oof.empty:
                continue
            r = E.score(oof, label=f"{v['name']}/{t}")
            r.update({"variant": v["name"], "target": t, "mode": v["mode"],
                      "note": v["note"], "train_rows": int(len(tr2)),
                      "test_rows": int(len(te)), "group": group})
            rows.append(r)
            g = oof.sort_values("fixture_key", kind="mergesort")
            p = np.clip(g["p"].to_numpy(float), 1e-15, 1 - 1e-15)
            y = g["y"].to_numpy(float)
            losses[(v["name"], t)] = -(y * np.log(p) + (1 - y) * np.log(1 - p))
        print(f"   {v['name']:<32} train={len(tr2):>6,} "
              f"ll={np.mean([r['log_loss'] for r in rows if r['variant']==v['name']]):.5f}")

    tab = pd.DataFrame(rows)
    # Each group needs its OWN control as the bootstrap baseline. The completeness group had
    # none -- it fell through to "W_expanding", which is not one of its variants -- so no
    # comparisons were produced and the bootstrap file came back empty.
    baseline = {"core": "A_v9_current", "all": "A_v9_current", "recency": "R_none",
                "dupes": "X_dupes_as_v9_does", "covid": "V_covid_kept",
                "completeness": "Q_STANDARD_complete_only",
                "window": "W_expanding"}.get(group, "W_expanding")
    boots = _bootstrap(losses, baseline=baseline)
    return tab, boots


def _bootstrap(losses: dict, *, baseline: str) -> pd.DataFrame:
    from src.validation.multiple_testing import paired_bootstrap_p
    rows = []
    for (name, t), arr in losses.items():
        if name == baseline:
            continue
        base = losses.get((baseline, t))
        if base is None or len(base) != len(arr):
            continue
        p, obs, ci = paired_bootstrap_p(arr, base, n_boot=2000, block=8)
        rows.append({"variant": name, "baseline": baseline, "target": t,
                     "mean_diff": obs, "ci_lo": ci[0], "ci_hi": ci[1], "p_value": p,
                     "significant": bool(ci[0] > 0 or ci[1] < 0),
                     "direction": "variant better" if obs > 0 else "baseline better"})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="core",
                    choices=["core", "window", "recency", "dupes", "covid",
                             "completeness", "all"])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    tab, boots = run(a.group)
    if tab.empty:
        print("no results")
        return 1
    piv = tab.pivot_table(index="variant", columns="target", values="log_loss")
    piv["mean_ll"] = piv.mean(axis=1)
    piv["train_rows"] = tab.groupby("variant")["train_rows"].first()
    print("\nOOS LOG LOSS (lower is better), identical test fixtures")
    print(piv.sort_values("mean_ll").round(5).to_string())
    if not boots.empty:
        print(f"\nPAIRED BOOTSTRAP vs {boots.baseline.iloc[0]} "
              f"(positive diff = variant better; counts only if the CI excludes zero)")
        print(boots[["variant", "target", "mean_diff", "ci_lo", "ci_hi", "p_value",
                     "significant"]].round(5).to_string(index=False))
        print(f"\n  significant: {int(boots.significant.sum())} of {len(boots)}")
    if a.write:
        suffix = a.group
        tab.to_csv(O() / f"experiment_{suffix}.csv", index=False)
        boots.to_csv(O() / f"experiment_{suffix}_bootstrap.csv", index=False)
        print(f"\n[shadow] wrote experiment_{suffix}.csv + bootstrap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
