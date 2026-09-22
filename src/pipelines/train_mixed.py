"""Mixed-model retrain — does combining the markets beat any single one?

    python -m src.pipelines.train_mixed [--write]

THE QUESTION. v9 trains one model per market, each in isolation, and that isolation is correct
for production (invariant 1). But a fixture carries SIX model opinions at once — O/U 2.5, O/U
1.5, O/U 3.5, BTTS and the two half-time markets — and they are all views of the same underlying
thing: how many goals this game will produce. If those views disagree in an informative way,
a model that sees all of them should predict the outcome better than the one that sees only its
own market.

That is a question isolation cannot answer, because it only exists ACROSS models. It is asked
here, in Pro, and it changes nothing in v9.

WHY THIS IS A RETRAIN AND NOT ANOTHER CORRELATION TABLE. `src/validation/cross_model.py` already
measures whether two models' SIGNALS co-occur profitably. That is a betting question on settled
bets. This is the modelling question underneath it: fit a challenger on the stacked
probabilities, and test whether it forecasts the OUTCOME better than the single-market incumbent
on rows neither has seen.

THE RULES IT OBEYS, each because the estate has been burned without it:

  * CHRONOLOGICAL SPLIT. Train on the earlier fixtures, test on the later ones. Never random —
    football is time-ordered and a random split leaks the future into the past.
  * BOTH MODELS SCORED ON EXACTLY THE SAME TEST ROWS (§6). Comparing a challenger on dataset A
    against an incumbent's historical metric from dataset B is how a worse model gets promoted.
    Here the baseline and the challenger are evaluated on one identical frame.
  * LOG LOSS AND BRIER, NOT ACCURACY (§7). Both are proper scoring rules; accuracy is not, and
    a model can gain accuracy while becoming worse calibrated — which is this estate's measured
    defect.
  * PER model_type AS WELL AS POOLED. standard and new_format are different populations; a
    pooled-only answer would hide one of them.
  * NOTHING IS PROMOTED. This writes a verdict and an artifact. It does not touch a v9 model,
    and it is not wired to anything that does.
"""
from __future__ import annotations

import argparse
import glob
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
MIN_TRAIN = 150
MIN_TEST = 80
TEST_FRACTION = 0.35


def _snapshots() -> pd.DataFrame:
    """One row per fixture, one column per market's model probability."""
    fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / "model_snapshots" /
                              "dt=*" / "run=*.parquet")))
    if not fs:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d["model_prob"] = pd.to_numeric(d["model_prob"], errors="coerce")
    d["observed_at"] = pd.to_datetime(d["observed_at"], errors="coerce")
    d = d[d["model_prob"].notna() & d["fixture_key"].notna()]
    # LAST opinion per fixture+market. A fixture is re-scored every predict run; the model's
    # view of it is one thing, not forty.
    d = d.sort_values("observed_at").drop_duplicates(["fixture_key", "market"], keep="last")
    piv = d.pivot_table(index="fixture_key", columns="market",
                        values="model_prob", aggfunc="last")
    piv.columns = [f"p_{c}" for c in piv.columns]
    meta = (d.sort_values("observed_at")
              .drop_duplicates("fixture_key", keep="last")
              .set_index("fixture_key")[["league", "match_date", "model_type"]])
    return piv.join(meta, how="inner")


def _outcomes() -> pd.DataFrame:
    """Did the fixture go over 2.5? Derived from settlements, side-independent."""
    fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / "settlements" /
                              "dt=*" / "run=*.parquet")))
    if not fs:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d[d["result"].isin(["WIN", "LOSS"]) & (d["market"].astype(str) == "OU25")].copy()
    side = d["side"].astype(str).str.upper()
    d = d[side.isin(["OVER", "UNDER"])]
    won = d["result"].eq("WIN")
    # A bet on UNDER that WON means the game went under. Scoring the EVENT, never the bet.
    d["y"] = np.where(side.eq("OVER"), won, ~won).astype(int)
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce")
    return (d.sort_values("match_date")
              .drop_duplicates("fixture_key", keep="first")[["fixture_key", "y"]]
              .set_index("fixture_key"))


def _metrics(p, y) -> dict:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, dtype=int)
    ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    br = float(np.mean((p - y) ** 2))
    edges = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(p, edges) - 1, 0, 9)
    ece = float(sum((idx == b).mean() * abs(p[idx == b].mean() - y[idx == b].mean())
                    for b in range(10) if (idx == b).any()))
    return {"logloss": ll, "brier": br, "ece": ece, "n": int(len(y))}


def run(d: pd.DataFrame, label: str, *, n_boot: int = 3000, seed: int = 61) -> dict | None:
    """Fit the stack on the earlier fixtures, score both models on the later ones."""
    from sklearn.linear_model import LogisticRegression
    rng = np.random.default_rng(seed)

    # FEATURE SET CHOSEN BY COVERAGE, not by wishing. The half-time markets exist only for
    # standard-format leagues (451 of 1,044 fixtures, and zero for new_format), so demanding
    # every market collapsed the usable sample to 212 rows and wiped new_format out entirely.
    # Keep the markets present on most of THIS subset's rows and drop the rest; a market that
    # is mostly missing cannot contribute to a stack anyway, and requiring it silently discards
    # the fixtures that would have trained it.
    base_col = "p_OU25"
    all_feats = [c for c in d.columns if c.startswith("p_")]
    if base_col not in all_feats:
        return None
    cover = d[all_feats].notna().mean()
    feats = [c for c in all_feats if cover[c] >= 0.80]
    dropped = [f"{c}({cover[c]:.0%})" for c in all_feats if c not in feats]
    if base_col not in feats:
        feats.append(base_col)
    d = d.dropna(subset=feats + ["y", "match_date"]).sort_values("match_date")
    cut = int(len(d) * (1 - TEST_FRACTION))
    if cut < MIN_TRAIN or (len(d) - cut) < MIN_TEST:
        return {"label": label, "status": "INSUFFICIENT_DATA", "n": int(len(d)),
                "n_train": int(cut), "n_test": int(len(d) - cut), "features": feats,
                "dropped_low_coverage": dropped}

    tr, te = d.iloc[:cut], d.iloc[cut:]
    # THE INCUMBENT: the single-market model, untouched, on the test rows.
    base = _metrics(te[base_col].to_numpy(), te["y"].to_numpy())
    # THE CHALLENGER: a stack over every market's probability, fitted on the train rows only.
    lr = LogisticRegression(max_iter=2000, C=1.0)
    lr.fit(tr[feats].to_numpy(), tr["y"].to_numpy())
    pc = lr.predict_proba(te[feats].to_numpy())[:, 1]
    chal = _metrics(pc, te["y"].to_numpy())

    # Paired bootstrap on the per-row log-loss difference. Negative = the stack is better.
    yv = te["y"].to_numpy()
    pb = np.clip(te[base_col].to_numpy(), 1e-6, 1 - 1e-6)
    pcc = np.clip(pc, 1e-6, 1 - 1e-6)
    d_ll = (-(yv * np.log(pcc) + (1 - yv) * np.log(1 - pcc))) - \
           (-(yv * np.log(pb) + (1 - yv) * np.log(1 - pb)))
    bs = rng.choice(d_ll, size=(n_boot, len(d_ll)), replace=True).mean(axis=1)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    better = bool(hi < 0)

    return {
        "label": label, "status": "OK", "calc_version": CALC_VERSION,
        "features": feats, "dropped_low_coverage": dropped, "n": int(len(d)), "n_train": int(cut), "n_test": int(len(te)),
        "train_from": str(tr["match_date"].min().date()),
        "train_to": str(tr["match_date"].max().date()),
        "test_from": str(te["match_date"].min().date()),
        "test_to": str(te["match_date"].max().date()),
        "incumbent": base, "challenger": chal,
        "delta_logloss": chal["logloss"] - base["logloss"],
        "ci_lo": float(lo), "ci_hi": float(hi),
        "challenger_better_oos": better,
        "coefficients": dict(zip(feats, map(float, lr.coef_[0]))),
        "decision": "PROMOTE_CANDIDATE" if better else "REJECT",
        "reason": ("stack beats the single-market model on untouched later fixtures, "
                   "bootstrap CI excludes zero" if better else
                   "no improvement beyond noise on untouched later fixtures"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=3000)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    snap, out = _snapshots(), _outcomes()
    if snap.empty or out.empty:
        print("[train_mixed] no model_snapshots or no settlements — nothing to mix")
        return 1
    d = snap.join(out, how="inner").reset_index()
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce")
    print(f"[train_mixed] {len(d):,} fixtures carrying both model opinions and an outcome")
    print(f"              markets available: {[c for c in d.columns if c.startswith('p_')]}")

    results = [run(d, "ALL", n_boot=a.boot)]
    for mt, g in d.groupby("model_type"):
        if str(mt) == "unknown":
            continue
        results.append(run(g, f"model_type={mt}", n_boot=a.boot))
    results = [r for r in results if r]

    print("\n" + "=" * 104)
    print("MIXED (STACKED) CHALLENGER vs SINGLE-MARKET INCUMBENT — same untouched test rows")
    print("=" * 104)
    for r in results:
        if r["status"] != "OK":
            print(f"  {r['label']:<22} INSUFFICIENT_DATA (n={r['n']}, "
                  f"train={r['n_train']}, test={r['n_test']})")
            continue
        i, c = r["incumbent"], r["challenger"]
        print(f"  {r['label']:<22} train {r['train_from']}..{r['train_to']} (n={r['n_train']})  "
              f"test {r['test_from']}..{r['test_to']} (n={r['n_test']})")
        print(f"      {'':14}{'logloss':>10}{'brier':>10}{'ECE':>9}")
        print(f"      {'incumbent':<14}{i['logloss']:>10.5f}{i['brier']:>10.5f}{i['ece']:>9.4f}")
        print(f"      {'challenger':<14}{c['logloss']:>10.5f}{c['brier']:>10.5f}{c['ece']:>9.4f}")
        print(f"      delta logloss {r['delta_logloss']:+.5f}  "
              f"CI [{r['ci_lo']:+.5f},{r['ci_hi']:+.5f}]  ->  {r['decision']}")
        print(f"      {r['reason']}")
        if r.get("dropped_low_coverage"):
            print(f"      dropped for low coverage: {', '.join(r['dropped_low_coverage'])}")
        top = sorted(r["coefficients"].items(), key=lambda kv: -abs(kv[1]))[:4]
        print(f"      strongest inputs: {', '.join(f'{k}={v:+.2f}' for k, v in top)}")
        print()

    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = cfg.OUTPUT_DIR / "mixed_model_eval.json"
        p.write_text(json.dumps({"generated_at": pd.Timestamp.utcnow().isoformat(),
                                 "results": results}, indent=2, default=str), encoding="utf-8")
        print(f"[train_mixed] wrote {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
