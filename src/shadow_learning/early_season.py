"""Does labelling stale form fix the season-start weak spot? Test it where the problem is.

    python -m src.shadow_learning.early_season --write

THE PROBLEM, DIAGNOSED RATHER THAN ASSUMED. The walk-forward found prediction is worst at the
start of a season and that retraining helps least there. The obvious reading -- "there is no
form data yet" -- is wrong, and checking took one query: rolling form is populated on 94.9% of
opening-20% fixtures.

What is actually wrong is that the numbers are stale and UNLABELLED. On a team's first match of
a season the whole five-match window is last season's football (median gap: 57 days), played by
a partly different squad and occasionally in a different division -- and `gf_r5` looks identical
to a mid-season `gf_r5`. The model cannot discount what it cannot see.

So the EARLY family does not invent data. It says when the data came from: how many matches of
this season are behind the number, whether this is the opener, whether the team changed division,
and an explicit previous-season carry-over.

THE TEST IS RUN WHERE THE PROBLEM IS. A global average would drown a season-start effect in
four-fifths of fixtures that never had the problem, so the comparison is scored on the SAME test
fixtures split by season phase -- and the number that matters is the opening-20% column, with
the closing-20% column beside it as a control. If the family helps everywhere equally it is not
fixing this; it is just more features.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.prediction_lab import experiments as E
from src.prediction_lab import features as F
from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M
from src.shadow_learning import experiments as X

CALC_VERSION = "1.0.0"
TARGETS = ("btts", "over15", "over25", "over35")
TEST_FRAC = 0.20


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _phase(d: pd.DataFrame) -> pd.Series:
    """Position inside each league-season, 0..1. Not the calendar month."""
    g = d.groupby(["league", "season_label"])["date"]
    span = (g.transform("max") - g.transform("min")).dt.days.replace(0, np.nan)
    return ((d["date"] - g.transform("min")).dt.days / span).fillna(0.5)


def run() -> pd.DataFrame:
    U = X.universes()
    base = X._prepare(U["_can_frame"])
    feat = F.build(base)
    feat["date"] = pd.to_datetime(feat["date"])
    feat["phase"] = _phase(feat)

    without = [f for f in F.FOOTBALL_FAMILIES if f != "EARLY"]
    specs = {"without_EARLY": F.feature_columns(feat, without),
             "with_EARLY": F.feature_columns(feat, F.FOOTBALL_FAMILIES)}
    print(f"[early] {len(feat):,} fixtures  |  {len(specs['without_EARLY'])} features without, "
          f"{len(specs['with_EARLY'])} with")

    dates = feat["date"].to_numpy()
    cutoff = np.datetime64(pd.Timestamp(feat["date"].quantile(1 - TEST_FRAC)))
    tr_all = np.flatnonzero(dates < cutoff)
    te = np.flatnonzero(dates >= cutoff)
    vcut = np.quantile(dates[tr_all].astype("datetime64[ns]").astype("int64"), 0.88)
    va = tr_all[dates[tr_all].astype("datetime64[ns]").astype("int64") >= vcut]
    tr = tr_all[dates[tr_all].astype("datetime64[ns]").astype("int64") < vcut]
    fold = [FO.Fold(name="f1", train=tr, val=va, test=te,
                    t_start=str(pd.Timestamp(cutoff).date()),
                    t_end=str(feat["date"].max())[:10])]
    print(f"[early] train {len(tr):,}  test {len(te):,} from {pd.Timestamp(cutoff).date()}")

    phase_te = feat["phase"].to_numpy()[te]
    bands = {"opening 20%": phase_te <= 0.2, "middle 60%": (phase_te > 0.2) & (phase_te < 0.8),
             "closing 20%": phase_te >= 0.8}

    rows, store = [], {}
    for name, cols in specs.items():
        for t in TARGETS:
            oof = E.walk_forward(feat, t, cols, model="hgb", fold_list=fold)
            if oof.empty:
                continue
            oof = oof.sort_values("fixture_key", kind="mergesort")
            store[(name, t)] = oof
            key = feat["fixture_key"].to_numpy()[te]
            order = {k: i for i, k in enumerate(key)}
            idx = np.array([order[k] for k in oof["fixture_key"]])
            for band, mask in bands.items():
                m = mask[idx]
                if m.sum() < 300:
                    continue
                y, p = oof["y"].to_numpy()[m], oof["p"].to_numpy()[m]
                rows.append({"spec": name, "target": t, "band": band, "n": int(m.sum()),
                             "log_loss": round(M.log_loss(y, p), 5),
                             "brier": round(M.brier(y, p), 5),
                             "auc": round(M.auc(y, p), 4)})
            print(f"   {name:<16}{t:<8}done")

    tab = pd.DataFrame(rows)

    # Paired bootstrap per band, on identical fixtures.
    from src.validation.multiple_testing import paired_bootstrap_p
    sig = []
    for t in TARGETS:
        a, b = store.get(("with_EARLY", t)), store.get(("without_EARLY", t))
        if a is None or b is None:
            continue
        j = a[["fixture_key", "y", "p"]].merge(b[["fixture_key", "p"]], on="fixture_key",
                                               suffixes=("_w", "_wo"))
        key = feat.set_index("fixture_key")["phase"]
        ph = j["fixture_key"].map(key).to_numpy()
        def ll(col):
            q = np.clip(j[col].to_numpy(float), 1e-15, 1 - 1e-15)
            y = j["y"].to_numpy(float)
            return -(y * np.log(q) + (1 - y) * np.log(1 - q))
        for band, mask in {"opening 20%": ph <= 0.2,
                           "middle 60%": (ph > 0.2) & (ph < 0.8),
                           "closing 20%": ph >= 0.8}.items():
            if mask.sum() < 300:
                continue
            pv, obs, ci = paired_bootstrap_p(ll("p_w")[mask], ll("p_wo")[mask],
                                             n_boot=3000, block=8)
            sig.append({"target": t, "band": band, "n": int(mask.sum()),
                        "gain_from_EARLY": round(obs, 6),
                        "ci_lo": round(ci[0], 6), "ci_hi": round(ci[1], 6),
                        "p_value": round(pv, 4),
                        "significant": bool(ci[0] > 0 or ci[1] < 0)})
    return tab, pd.DataFrame(sig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    tab, sig = run()
    if tab.empty:
        print("nothing evaluated")
        return 1
    piv = tab.pivot_table(index=["target", "band"], columns="spec", values="log_loss")
    piv["gain"] = piv["without_EARLY"] - piv["with_EARLY"]
    print("\nLOG LOSS BY SEASON PHASE — identical test fixtures")
    print(piv.round(5).to_string())
    print("\nIS THE GAIN REAL?  (positive = the EARLY family helped)")
    print(sig.to_string(index=False))
    op = sig[sig.band == "opening 20%"]
    print(f"\n  opening-20% cells where it significantly helped: "
          f"{int((op.significant & (op.gain_from_EARLY > 0)).sum())} of {len(op)}")
    if a.write:
        tab.to_csv(O() / "early_season_experiment.csv", index=False)
        sig.to_csv(O() / "early_season_significance.csv", index=False)
        print("\n[early] wrote early_season_experiment.csv + significance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
