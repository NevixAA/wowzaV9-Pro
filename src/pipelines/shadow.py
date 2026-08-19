"""
Phase 5: the market-relative test on REAL settled fixtures.
==========================================================
    python -m src.pipelines.shadow [--min-books 1] [--no-write]

Everything in Phases 2-4 was verified against synthetic data with known answers, which is the
right way to test machinery but tells you nothing about football. This joins the season store's
three tables into the one dataset that answers the central question:

    settlements     -> y      did OVER 2.5 actually happen
    market_snapshots-> p_market  de-vigged two-sided consensus
    model_snapshots -> p_model   what v9 thought

and runs A (model) / B (market) / C (market+model). Only C beating B means the model knows
something the price does not.

TARGET CONVENTION. Settlements record the side that was TAKEN plus WIN/LOSS, not the match
outcome. Those are different things, and conflating them silently inverts half the rows:

    side=OVER,  WIN  -> over happened      y = 1
    side=OVER,  LOSS -> over did not       y = 0
    side=UNDER, WIN  -> over did NOT happen y = 0     <- the inversion
    side=UNDER, LOSS -> over happened       y = 1

WHAT THIS DELIBERATELY DOES NOT DO. It does not choose the blend weight from these rows. The
weight is a fixed input, because fitting it here and then reporting the improvement it produces
is the same in-sample error that made v9's ensemble AUC meaningless. A sweep belongs in a
chronologically earlier block.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg
from src.data import season_store as store
from src.market.devig import devig
from src.models.registry import hash_manifest
from src.pipelines.experiment import (Experiment, ExperimentManifest, experiment_id,
                                      git_sha, write_system_registry)
from src.validation.market_relative import compare_by, ece, log_loss, brier
from src.validation.multiple_testing import benjamini_hochberg, paired_bootstrap_p

# The OVER side of the main line, however the source happened to label it.
_OVER_LABELS = {"over25", "OVER25", "o25"}
_UNDER_LABELS = {"under25", "UNDER25", "u25"}


def _two_sided_prices(mk: pd.DataFrame) -> pd.DataFrame:
    """Collapse market_snapshots into one row per fixture with both sides of OU 2.5.

    Two shapes arrive here: the odds-capture histories use market='over25'/'under25', while the
    predictions importer uses market='OU25' with side='OVER'/'UNDER'. Both are handled rather
    than one being preferred, because dropping either loses fixtures.
    """
    m = mk.copy()
    m["odds"] = pd.to_numeric(m["odds"], errors="coerce")
    m = m[m["odds"].notna() & (m["odds"] > 1.0)]

    lab = m["market"].astype(str)
    side = m["side"].astype(str).str.upper() if "side" in m.columns else ""
    is_over = lab.isin(_OVER_LABELS) | ((lab == "OU25") & (side == "OVER"))
    is_under = lab.isin(_UNDER_LABELS) | ((lab == "OU25") & (side == "UNDER"))
    m = m[is_over | is_under].copy()
    m["_side"] = np.where(is_over[m.index], "OVER", "UNDER")

    # Best available price per fixture per side. Best, not last: this is the executable price,
    # and using the median here would blur two different concepts (see src/market/consensus.py).
    g = (m.groupby(["fixture_key", "_side"])
          .agg(odds=("odds", "max"), n_quotes=("odds", "size"),
               league=("league", "first"), match_date=("match_date", "first"))
          .reset_index())
    piv = g.pivot(index="fixture_key", columns="_side", values="odds")
    cnt = g.pivot(index="fixture_key", columns="_side", values="n_quotes")
    meta = g.groupby("fixture_key").agg(league=("league", "first"),
                                        match_date=("match_date", "first"))
    out = piv.join(cnt, rsuffix="_n").join(meta).reset_index()
    return out.rename(columns={"OVER": "over_odds", "UNDER": "under_odds",
                               "OVER_n": "over_quotes", "UNDER_n": "under_quotes"})


def _backfill_dataset() -> pd.DataFrame:
    """The UNBIASED sample: match outcomes for fixtures v9 evaluated, INCLUDING the declined ones.

    This is the table the whole backfill exists to produce, and it is self-contained — one row
    carries the outcome, both sides of the price and v9's own probability — so unlike the ledger
    path it needs no join against market_snapshots/model_snapshots and cannot lose rows to a
    failed join.

    Why it must be a SEPARATE source rather than more rows in `settlements`: a settlement answers
    "did the bet win" and only exists where a bet was placed. 176 of these 264 fixtures were
    DECLINED, so they have no side, no result, and no settlement — but they do have an outcome.
    They are the controls, and without them the market is being scored only on the fixtures v9
    picked for maximum model-market disagreement, which is precisely where a real market looks
    worst. That is what the selection-bias warning below has been reporting.
    """
    b = store.read("settlements_backfill")
    if b.empty:
        return pd.DataFrame()
    b = b[b["market"].astype(str).str.upper() == "OU25"].copy()
    b["y"] = pd.to_numeric(b["y"], errors="coerce")
    b = b[b["y"].isin([0, 1])]
    for c in ("odds_over25", "odds_under25", "p_over25"):
        b[c] = pd.to_numeric(b.get(c), errors="coerce")
    # No imputation: a fixture missing a price or a model probability cannot be scored, and
    # inventing either would fabricate the very number under test (invariant 9).
    b = b[b["odds_over25"].notna() & b["odds_under25"].notna() & b["p_over25"].notna()]
    if b.empty:
        return pd.DataFrame()
    dv = b.apply(lambda r: devig(r["odds_over25"], r["odds_under25"]), axis=1)
    b["p_market"] = [d.prob for d in dv]
    b["overround"] = [d.overround for d in dv]
    b["devig_reason"] = [d.reason for d in dv]
    b["over_odds"] = b["odds_over25"]
    b["under_odds"] = b["odds_under25"]
    b["over_quotes"] = 1
    b["under_quotes"] = 1
    b["p_model"] = b["p_over25"]
    b["p_model_source"] = "backfill_predictions_csv"
    b["was_bet"] = b["bet"].astype(str).str.upper().isin(["OVER", "UNDER"])
    b["sample_source"] = "backfill"
    b = b[b["p_market"].notna()]
    return b.sort_values("observed_at").drop_duplicates("fixture_key", keep="last")


def build_dataset(*, min_quotes: int = 1) -> pd.DataFrame:
    """Union of the two settled-outcome sources, deduplicated per fixture.

    The BACKFILL row wins where a fixture appears in both, because it records what the match did
    (`y` straight from the score) whereas the ledger row records what a bet did and has to be
    un-inverted through side+WIN/LOSS. Same fact, but one derivation has fewer ways to be wrong.
    """
    ledger = _ledger_dataset(min_quotes=min_quotes)
    back = _backfill_dataset()
    if ledger.empty and back.empty:
        return pd.DataFrame()
    if not ledger.empty:
        ledger = ledger.copy()
        ledger["sample_source"] = "ledger"
        if "was_bet" not in ledger.columns:
            # Every ledger row IS a bet by construction — it only exists because a side was taken.
            ledger["was_bet"] = True
    keep = ["fixture_key", "y", "league", "match_date", "model_type", "p_market", "p_model",
            "p_model_source", "overround", "devig_reason", "over_odds", "under_odds",
            "over_quotes", "under_quotes", "was_bet", "sample_source", "signal_tier"]
    frames = []
    for f in (back, ledger):                      # backfill FIRST so keep='first' prefers it
        if f is None or f.empty:
            continue
        g = f.copy()
        for c in keep:
            if c not in g.columns:
                g[c] = np.nan
        frames.append(g[keep])
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates("fixture_key", keep="first")
    df["p_model"] = pd.to_numeric(df["p_model"], errors="coerce").clip(0.001, 0.999)
    df["p_market"] = pd.to_numeric(df["p_market"], errors="coerce").clip(0.001, 0.999)
    df = df[df["p_model"].notna() & df["p_market"].notna() & df["y"].notna()]
    return df.reset_index(drop=True)


def _ledger_dataset(*, min_quotes: int = 1) -> pd.DataFrame:
    """Join settled outcomes, two-sided prices and model probabilities on fixture_key."""
    st = store.read("settlements")
    mk = store.read("market_snapshots")
    md = store.read("model_snapshots")
    if st.empty or mk.empty or md.empty:
        return pd.DataFrame()

    # ── y: did OVER 2.5 happen ───────────────────────────────────────────────
    s = st[st["market"].astype(str).str.upper().isin(["OU25"])].copy()
    s["res"] = s["result"].astype(str).str.upper()
    s = s[s["res"].isin(["WIN", "LOSS"])]
    s["side"] = s["side"].astype(str).str.upper()
    s = s[s["side"].isin(["OVER", "UNDER"])]
    won = s["res"] == "WIN"
    s["y"] = np.where(s["side"] == "OVER", won.astype(int), (~won).astype(int))
    # One settled outcome per fixture. A fixture cannot have two different results, so repeats
    # are re-imports of the same fact; keep the last snapshot of it.
    s = s.sort_values("observed_at").drop_duplicates("fixture_key", keep="last")

    # ── p_market: de-vigged from both sides ──────────────────────────────────
    prices = _two_sided_prices(mk)
    prices = prices[(prices.get("over_quotes", 0) >= min_quotes)
                    & (prices.get("under_quotes", 0) >= min_quotes)]
    dv = prices.apply(lambda r: devig(r.get("over_odds"), r.get("under_odds")), axis=1)
    prices["p_market"] = [d.prob for d in dv]
    prices["overround"] = [d.overround for d in dv]
    prices["devig_reason"] = [d.reason for d in dv]

    # ── p_model ──────────────────────────────────────────────────────────────
    m = md[md["market"].astype(str).str.upper() == "OU25"].copy()
    m["model_prob"] = pd.to_numeric(m["model_prob"], errors="coerce")
    m = m[m["model_prob"].notna()]
    # LAST pre-settlement view per fixture. The store holds every capture, which is the point,
    # but a single comparison needs one probability per fixture.
    m = m.sort_values("observed_at").drop_duplicates("fixture_key", keep="last")

    cols = ["fixture_key", "y", "league", "match_date", "model_type", "odds",
            "closing_odds", "clv_pct", "signal_tier"]
    if "p_model_over" in s.columns:
        cols.append("p_model_over")

    df = (s[cols]
          .merge(prices[["fixture_key", "over_odds", "under_odds", "p_market", "overround",
                         "devig_reason", "over_quotes", "under_quotes"]],
                 on="fixture_key", how="inner")
          .merge(m[["fixture_key", "model_prob", "model_id", "git_sha"]],
                 on="fixture_key", how="left"))
    df = df[df["p_market"].notna()]

    # Prefer a genuine model_snapshot; fall back to the ledger reconstruction.
    #
    # These cannot overlap yet and that is structural, not a bug: model_snapshots come from
    # predictions.csv, which is PRE-MATCH only, while settlements are by definition finished.
    # Nothing Pro has snapshotted has settled yet. The ledger's edge_pct is therefore the only
    # record of what v9 thought about a fixture that already has a result — a year of it —
    # and it reconstructs the probability exactly from v9's own definition.
    snap = pd.to_numeric(df.get("model_prob"), errors="coerce")
    ledger = pd.to_numeric(df.get("p_model_over"), errors="coerce") \
        if "p_model_over" in df.columns else pd.Series(np.nan, index=df.index)
    df["p_model"] = snap.where(snap.notna(), ledger)
    df["p_model_source"] = np.where(snap.notna(), "model_snapshot", "ledger_edge_pct")
    df = df[df["p_model"].notna()]
    df["p_model"] = df["p_model"].clip(0.001, 0.999)
    df["p_market"] = df["p_market"].clip(0.001, 0.999)
    return df.reset_index(drop=True)


def run(*, weight: float = 0.20, min_quotes: int = 1, write: bool = True) -> dict:
    df = build_dataset(min_quotes=min_quotes)
    print(f"[shadow] joined dataset: {len(df)} settled fixtures with both a price and a model "
          f"probability")
    if df.empty:
        print("[shadow] nothing to compare yet — the join produced no rows.")
        return {"n": 0}

    print(f"[shadow] date range {df.match_date.min()} .. {df.match_date.max()}")
    print(f"[shadow] base rate (over 2.5 hit) {df.y.mean():.3f}")
    print(f"[shadow] by model_type {df.model_type.value_counts().to_dict()}")

    res = compare_by(df, y_col="y", market_col="p_market", model_col="p_model",
                     by=["model_type"], weight=weight)
    overall = res[res.segment == "overall"].iloc[0].to_dict()

    # Is the difference distinguishable from noise? Paired, because both forecasts score the
    # same fixtures; blocked, because same-matchday fixtures share conditions.
    y = df.y.to_numpy(dtype=float)
    lm = -(y * np.log(df.p_market) + (1 - y) * np.log(1 - df.p_market))
    b = weight * df.p_model + (1 - weight) * df.p_market
    lb = -(y * np.log(b) + (1 - y) * np.log(1 - b))
    p_val, diff, ci = paired_bootstrap_p(lb, lm, n_boot=4000, block=5)

    print("\n=== A / B / C on REAL settled fixtures ===")
    print(f"  n = {overall['n']}   label = {overall['sample_label']}")
    print(f"  A model only    logloss {overall['model_logloss']:.5f}  "
          f"brier {overall['model_brier']:.5f}  auc {overall['model_auc']}")
    print(f"  B market only   logloss {overall['market_logloss']:.5f}  "
          f"brier {overall['market_brier']:.5f}  auc {overall['market_auc']}")
    print(f"  C market+model  logloss {overall['blend_logloss']:.5f}  "
          f"brier {overall['blend_brier']:.5f}  auc {overall['blend_auc']}   (w={weight})")
    print(f"  C vs B          logloss {overall['logloss_improvement']:+.6f}  "
          f"brier {overall['brier_improvement']:+.6f}")
    print(f"  paired bootstrap p = {p_val:.4f}   mean diff {diff:+.6f}  90% CI "
          f"[{ci[0]:+.6f}, {ci[1]:+.6f}]")
    print(f"  VERDICT: {overall['verdict']}")

    # ── SELECTION-BIAS SANITY CHECK ──────────────────────────────────────────
    # A real bookmaker market must beat a constant "always predict the base rate" forecast. If
    # it does not, the SAMPLE is wrong, not the market — and every comparison above inherits
    # that. This is the check that turns an apparently good result into an interpretable one.
    base = float(y.mean())
    const_ll = log_loss(y, np.full(len(y), base))
    print("\n=== is this sample trustworthy? ===")
    print(f"  base rate {base:.3f} -> a constant forecast scores logloss {const_ll:.5f}")
    print(f"  market scores {overall['market_logloss']:.5f}")
    # Composition FIRST, because it decides how to read the line above. "The market is worse than
    # the base rate" means something completely different on a bet-only sample (expected, the
    # sample is selected for disagreement) than on a sample containing declined fixtures (a real
    # anomaly that needs explaining).
    n_ctrl = int((~df["was_bet"].fillna(True).astype(bool)).sum())
    n_bet = len(df) - n_ctrl
    src = df["sample_source"].value_counts().to_dict() if "sample_source" in df else {}
    print(f"  composition: {n_bet} bet, {n_ctrl} DECLINED controls  sources={src}")
    selection_warning = overall["market_logloss"] > const_ll
    has_controls = n_ctrl >= 20
    if selection_warning and not has_controls:
        print("  *** WARNING: the market is WORSE than predicting the base rate. A real market "
              "is not. ***")
        print(f"  Only {n_ctrl} declined control(s) in this sample, so these rows are effectively")
        print("  just fixtures v9 CHOSE TO BET — selected for maximum model-market disagreement.")
        print("  On such a subset the market looks bad by construction, so 'the blend beats the")
        print("  market' is close to circular.")
        print("  Prompt 3 section 17 requires outcomes for BET, PAPER and NO_BET controls.")
        print("  TREAT THE RESULT ABOVE AS A MACHINERY TEST, NOT AS EVIDENCE OF EDGE.")
    elif selection_warning and has_controls:
        print(f"  *** the market still scores worse than the base rate WITH {n_ctrl} controls "
              f"present. ***")
        print("  Selection bias is no longer a sufficient explanation, so this is now a real")
        print("  finding to chase rather than a known artefact — candidates: the sample is still")
        print("  small and league-skewed, these are OPENING prices rather than closing, and the")
        print("  leagues present are summer/second-tier competitions rather than the deep markets.")
    else:
        print("  market beats the constant baseline — the sample looks sane")
    metrics_extra = {"base_rate": base, "constant_logloss": const_ll,
                     "selection_bias_warning": bool(selection_warning),
                     "n_declined_controls": n_ctrl, "n_bet": n_bet,
                     "has_controls": bool(has_controls),
                     "sample_sources": src}

    # Per-segment p-values need FDR control before any of them is believed.
    seg = res[res.segment != "overall"].copy()
    if len(seg):
        pv = []
        for _, r in seg.iterrows():
            g = df[df.model_type == r.segment]
            if len(g) < 20:
                pv.append(np.nan)
                continue
            gy = g.y.to_numpy(dtype=float)
            glm = -(gy * np.log(g.p_market) + (1 - gy) * np.log(1 - g.p_market))
            gb = weight * g.p_model + (1 - weight) * g.p_market
            glb = -(gy * np.log(gb) + (1 - gy) * np.log(1 - gb))
            pv.append(paired_bootstrap_p(glb, glm, n_boot=2000, block=5)[0])
        bh = benjamini_hochberg(pv, q=0.05)
        seg["p_raw"] = bh["p_raw"].to_numpy()
        seg["q_value"] = bh["p_adjusted"].to_numpy()
        seg["significant_after_fdr"] = bh["significant"].to_numpy()
        print("\n=== by model type (FDR-controlled) ===")
        for _, r in seg.iterrows():
            print(f"  {r.segment:12} n={int(r.n):5}  logloss {r.logloss_improvement:+.6f}  "
                  f"q={r.q_value if pd.notna(r.q_value) else float('nan'):.3f}  "
                  f"{'SIGNIFICANT' if r.significant_after_fdr else 'not significant'}  "
                  f"[{r.sample_label}]")

    metrics = {**{k: v for k, v in overall.items() if not isinstance(v, (dict, list))},
               "bootstrap_p": p_val, "bootstrap_mean_diff": diff,
               "bootstrap_ci_low": ci[0], "bootstrap_ci_high": ci[1],
               "blend_weight": weight, "min_quotes": min_quotes,
               "market_ece": ece(y, df.p_market.to_numpy()),
               "model_ece": ece(y, df.p_model.to_numpy()),
               "real_odds_coverage": float((df.over_odds.notna()
                                            & df.under_odds.notna()).mean()),
               **metrics_extra}

    if write:
        cfgh = hash_manifest({"weight": weight, "min_quotes": min_quotes, "market": "OU25"})
        eid = experiment_id(name="shadow-ou25", git=git_sha(), config_hash=cfgh)
        mf = ExperimentManifest(
            experiment_id=eid, name="shadow-ou25", market="OU25", scope="all",
            validation_type="real_settled_join", odds_policy="REAL_ONLY",
            holdout_start=str(df.match_date.min()), holdout_end=str(df.match_date.max()),
            rows={"settled_fixtures": int(len(df))}, config_hash=cfgh,
            notes="A/B/C on real settled fixtures from the season store. Blend weight is a "
                  "FIXED input, not fitted on these rows.")
        d = Experiment(mf).save(metrics=metrics, by_league=seg if len(seg) else None,
                                bets=df)
        print(f"\n[shadow] experiment written -> {d}")
        write_system_registry(store_stats=store.stats(),
                             collect_health={"shadow_last_run": mf.created_at,
                                             "shadow_n": int(len(df)),
                                             "shadow_verdict": overall["verdict"]})
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser(description="Market-relative test on real settled fixtures")
    ap.add_argument("--weight", type=float, default=0.20)
    ap.add_argument("--min-quotes", type=int, default=1)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    m = run(weight=a.weight, min_quotes=a.min_quotes, write=not a.no_write)
    return 0 if m.get("n") else 1


if __name__ == "__main__":
    raise SystemExit(main())
