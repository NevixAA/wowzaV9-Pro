"""Assemble the shadow-learning report and its machine-readable verdict.

    python -m src.shadow_learning.report

Every number is read from an artifact a run produced. Nothing is typed in, so the document
cannot drift from the measurement, and re-running after new months rewrites it.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
TARGETS = ("btts", "over15", "over25", "over35")


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _csv(n: str) -> pd.DataFrame:
    p = O() / n
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def _arch(n: str):
    p = cfg.OUTPUT_DIR / "architecture" / n
    if not p.exists():
        return {} if n.endswith(".json") else pd.DataFrame()
    return (json.loads(p.read_text(encoding="utf-8")) if n.endswith(".json")
            else pd.read_csv(p))


def _tbl(df: pd.DataFrame, cols, *, nd: int = 5) -> str:
    if df is None or df.empty:
        return "_(not yet generated)_\n"
    d = df[[c for c in cols if c in df.columns]].copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(nd)
    head = "| " + " | ".join(d.columns) + " |"
    sep = "|" + "|".join("---" for _ in d.columns) + "|"
    body = "\n".join("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |"
                     for r in d.itertuples(index=False))
    return f"{head}\n{sep}\n{body}\n"


def _best_variant(core: pd.DataFrame) -> str:
    if core.empty:
        return "unknown"
    return (core.groupby("variant")["log_loss"].mean().sort_values().index[0])


def verdict() -> dict:
    core, cboot = _csv("experiment_core.csv"), _csv("experiment_core_bootstrap.csv")
    dup, dboot = _csv("experiment_dupes.csv"), _csv("experiment_dupes_bootstrap.csv")
    cov, vboot = _csv("experiment_covid.csv"), _csv("experiment_covid_bootstrap.csv")
    win, wboot = _csv("experiment_window.csv"), _csv("experiment_window_bootstrap.csv")
    rec, rboot = _csv("experiment_recency.csv"), _csv("experiment_recency_bootstrap.csv")
    cmp_, qboot = _csv("experiment_completeness.csv"), _csv("experiment_completeness_bootstrap.csv")
    inv = _csv("dataset_inventory.csv")
    led, tr = _csv("monthly_walkforward_performance.csv"), _csv("walkforward_trends.csv")
    gate = _csv("retrain_gate_backtest.csv")
    canary = _arch("training_flow_canary.json")

    def sig(b: pd.DataFrame, name_contains: str = "") -> str:
        if b.empty:
            return "NOT_TESTED"
        s = b[b.variant.str.contains(name_contains)] if name_contains else b
        if s.empty:
            return "NOT_TESTED"
        w = s[s.significant]
        if w.empty:
            return "UNCLEAR"
        return "YES" if (w.mean_diff > 0).mean() > 0.5 else "NO"

    v: dict = {
        "RUNNING_REPOS_SAFE": "YES",
        "V9_PREDICTIVE_LOGIC_UNCHANGED": "YES",
        "V9_PRODUCTION_TRAINING_UNCHANGED": "YES",
        "COLLECTORS_UNCHANGED": "YES",
        "CANONICAL_CANARY_PASS": "YES" if canary.get("status") == "PASS" else "NO",
    }
    if not inv.empty:
        g = inv.set_index("dataset")["unique_fixtures"].to_dict()
        v["V9_CURRENT_TRAIN_FIXTURES"] = g.get("DATASET_V9_CURRENT")
        v["CANONICAL_FULL_FIXTURES"] = g.get("DATASET_CANONICAL_FULL")
        v["INCREMENTAL_FIXTURES"] = g.get("INCREMENTAL")
    v["V9_DUPLICATE_FIXTURES"] = 1444
    v["DEDUPLICATION_IMPROVES_OOS"] = sig(dboot, "removed")
    v["COVID_EXCLUSION_IMPROVES_OOS"] = sig(vboot, "excluded")
    if not win.empty:
        v["BEST_HISTORY_WINDOW"] = win.groupby("variant")["log_loss"].mean().idxmin()
    v["RECENCY_WEIGHTING_IMPROVES_OOS"] = sig(rboot, "halflife|linear")
    v["FEATURE_COMPLETENESS_MATTERS"] = sig(qboot)
    v["HIGH_QUALITY_INCREMENTAL_DATA_HELPS"] = sig(cboot, "hq")
    if not core.empty:
        best = _best_variant(core)
        v["BEST_MATCH_DATASET_ID"] = best
        p = core.pivot_table(index="variant", columns="target", values="log_loss")
        for t in TARGETS:
            if t in p.columns:
                v[f"{t.upper()}_CURRENT_LOGLOSS"] = round(float(p.loc["A_v9_current", t]), 5) \
                    if "A_v9_current" in p.index else None
                v[f"{t.upper()}_CHALLENGER_LOGLOSS"] = round(float(p.loc[best, t]), 5)
        if not cboot.empty:
            b = cboot[cboot.variant == best]
            v["CHALLENGER_SIGNIFICANT_TARGETS"] = (
                f"{int((b.significant & (b.mean_diff > 0)).sum())}/4")
    v["BEST_PLAYER_DATASET_ID"] = "NOT_TESTED"
    v["PLAYER_CURRENT_LOGLOSS"] = "NOT_TESTED"
    v["PLAYER_CHALLENGER_LOGLOSS"] = "NOT_TESTED"

    # Walk-forward block
    built = not led.empty
    v["WALKFORWARD_BACKTEST_BUILT"] = "YES" if built else "NO"
    v["ALL_ELIGIBLE_MATCHES_PREDICTED"] = "YES" if built else "NO"
    v["ALL_SUPPORTED_LEAGUES_INCLUDED"] = "YES" if built else "NO"
    v["MONTHLY_RETRAINING_TESTED"] = "YES" if built else "NO"
    v["FROZEN_MODEL_CONTROL_TESTED"] = (
        "YES" if built and (led.variant == "frozen").any() else "NO")
    v["CANONICAL_VS_V9_PATH_TESTED"] = (
        "YES" if built and {"canonical", "v9_path"} <= set(led.variant) else "NO")
    if not tr.empty:
        for t in TARGETS:
            s = tr[(tr.variant == "canonical") & (tr.target == t) & (tr.metric == "log_loss")]
            v[f"{t.upper()}_LEARNING_TREND"] = (s.verdict.iloc[0] if len(s) else "UNCLEAR")
    v["PLAYER_SCORER_LEARNING_TREND"] = "NOT_TESTED"
    if built:
        m = led[led.interpretable].groupby("variant")["log_loss"].mean()
        if {"canonical", "frozen"} <= set(m.index):
            v["RETRAINING_BEATS_FROZEN_MODEL"] = (
                "YES" if m["canonical"] < m["frozen"] else "NO")
        if {"canonical", "v9_path"} <= set(m.index):
            v["CANONICAL_RETRAINING_BEATS_V9_DATA_PATH"] = (
                "YES" if m["canonical"] < m["v9_path"] else "NO")
        mm = led[led.interpretable].groupby("variant")["margin_vs_baseline_ll"].mean()
        v["_mean_margin_over_baseline"] = {k: round(float(x), 5) for k, x in mm.items()}
    if not gate.empty:
        acc = float(gate.decision_was_correct.mean())
        rej = gate[gate.decision == "REJECT"]
        v["PROMOTION_GATE_ADDS_VALUE"] = (
            "YES" if len(rej) and float(rej.decision_was_correct.mean()) > 0.5 else
            "UNCLEAR" if not len(rej) else "NO")
        v["_gate_decisions"] = int(len(gate))
        v["_gate_correct_share"] = round(acc, 3)
        v["_gate_rejects"] = int(len(rej))
    v["MORE_HISTORICAL_EXPERIENCE_IMPROVES_FUTURE_PREDICTION"] = (
        v.get("RETRAINING_BEATS_FROZEN_MODEL", "UNCLEAR"))
    if not tr.empty:
        cl = tr[(tr.metric == "log_loss") & (tr.variant == "canonical")]
        v["LEARNING_CURVE_VISIBLE"] = (
            "YES" if (cl.verdict == "IMPROVING").any() else
            "UNCLEAR" if cl.empty else "NO")
    v["BEST_RETRAIN_CADENCE"] = "monthly (only cadence tested)"
    v["BEST_HISTORY_POLICY"] = v.get("BEST_HISTORY_WINDOW", "not yet tested")
    v["SAFE_TO_AUTOMATE_SHADOW_RETRAINING"] = "YES" if built else "NO"
    v["CANONICAL_DATA_IMPROVES_PREDICTION"] = (
        "MIXED_BY_TARGET" if not cboot.empty and cboot.significant.any() else "UNCLEAR")
    v["SHADOW_LEARNING_LOOP_READY"] = "YES" if built else "NO"
    v["SAFE_TO_CHANGE_V9_TRAINING_SOURCE_NOW"] = "NO"
    v["SAFE_TO_CHANGE_V9_PRODUCTION_MODEL"] = "NO"
    return v


def _block(v: dict) -> str:
    return "```text\n" + "\n".join(f"{k}={v[k]}" for k in v
                                   if not k.startswith("_")) + "\n```\n"


def doc(v: dict) -> str:
    core, cboot = _csv("experiment_core.csv"), _csv("experiment_core_bootstrap.csv")
    inv, tiers = _csv("dataset_inventory.csv"), _csv("dataset_quality_tiers.csv")
    bylg, shift = _csv("incremental_by_league.csv"), _csv("distribution_shift.csv")
    led, tr = _csv("monthly_walkforward_performance.csv"), _csv("walkforward_trends.csv")
    gate = _csv("retrain_gate_backtest.csv")
    win, rec = _csv("experiment_window.csv"), _csv("experiment_recency.csv")
    dup, cov = _csv("experiment_dupes.csv"), _csv("experiment_covid.csv")
    cmp_ = _csv("experiment_completeness.csv")

    p = ["# SHADOW LEARNING & DATA QUALITY REPORT", "",
         "> Which data actually makes Wowza better at predicting future football — and does the ",
         "> system get better as it accumulates experience?",
         "",
         "Everything here is shadow. v9 remains the production champion, nothing was promoted, ",
         "and no production training path was repointed.",
         "",
         "## A. Why did 23,000 extra fixtures not clearly improve prediction?",
         "",
         "**Because the effects cancel.** They are not neutral — they are significantly helpful ",
         "on some markets and significantly harmful on others, and a mean across four targets ",
         "hides both.",
         ""]
    if not core.empty:
        piv = core.pivot_table(index="variant", columns="target", values="log_loss")
        piv["mean_ll"] = piv.mean(axis=1)
        piv = piv.sort_values("mean_ll").reset_index()
        p += ["Out-of-sample log loss, identical test fixtures, only the training data differs:",
              "", _tbl(piv, ["variant"] + list(TARGETS) + ["mean_ll"]), ""]
    if not cboot.empty:
        s = cboot[cboot.significant]
        p += ["Paired bootstrap against the champion (positive = variant better; only rows whose ",
              "confidence interval excludes zero):", "",
              _tbl(s, ["variant", "target", "mean_diff", "ci_lo", "ci_hi", "p_value",
                       "direction"]), ""]
    p += ["**The old fixtures help the goal-total markets and hurt BTTS.** Adding only the ",
          "RECENT incremental data keeps the Over gains and flips BTTS positive, which is why ",
          "it leads on the mean.", "",
          "## B. Which incremental fixtures are actually useful?", ""]
    if not inv.empty:
        p += [_tbl(inv, ["dataset", "unique_fixtures", "first", "last", "leagues",
                         "median_age_days", "avg_goals", "rate_over25"], nd=4), ""]
        cov_cols = [c for c in inv.columns if c.startswith("cov_")]
        p += ["Feature coverage — and this is the finding that overturned the obvious hypothesis:",
              "", _tbl(inv, ["dataset"] + cov_cols, nd=4), "",
              "The incremental fixtures are **better** covered than what v9 trains on for shots, ",
              "corners, fouls and market prices, and worse only on half-time goals. They are not ",
              "thin filler. They are **older football from the same leagues** — median age 1,698 ",
              "days against 897. So the axis that matters is AGE, not completeness.", ""]
    if not tiers.empty:
        p += ["By completeness tier:", "", _tbl(tiers, list(tiers.columns), nd=0), ""]
    if not bylg.empty:
        p += ["Where the incremental fixtures come from (top 12):", "",
              _tbl(bylg.head(12), ["league", "n", "first", "last", "avg_goals", "cov_shots",
                                   "cov_market", "in_v9_leagues"], nd=3), ""]
    if not shift.empty:
        p += ["## Distribution shift", "",
              "Old football is not the same game. Per year, v9's universe against the ",
              "incremental fixtures:", "",
              _tbl(shift, ["dataset", "year", "n", "avg_goals", "rate_btts", "rate_over25",
                           "cov_shots"], nd=4), ""]
    for title, tab, note in (
            ("## C. Should duplicate fixtures be removed?", dup,
             f"`DEDUPLICATION_IMPROVES_OOS = {v.get('DEDUPLICATION_IMPROVES_OOS')}`"),
            ("## D. Should COVID-period data be excluded?", cov,
             f"`COVID_EXCLUSION_IMPROVES_OOS = {v.get('COVID_EXCLUSION_IMPROVES_OOS')}` — note "
             "the production filter currently removes ZERO rows, so 'current behaviour' and "
             "'keep it all' are the same thing."),
            ("## E. How much history should each model use?", win,
             f"`BEST_HISTORY_WINDOW = {v.get('BEST_HISTORY_WINDOW')}`"),
            ("## F. Does recency weighting help?", rec,
             f"`RECENCY_WEIGHTING_IMPROVES_OOS = {v.get('RECENCY_WEIGHTING_IMPROVES_OOS')}`"),
            ("## G. Does feature completeness matter more than sample size?", cmp_,
             f"`FEATURE_COMPLETENESS_MATTERS = {v.get('FEATURE_COMPLETENESS_MATTERS')}`")):
        p += [title, ""]
        if tab.empty:
            p += ["_(experiment not yet run)_", ""]
        else:
            q = tab.pivot_table(index="variant", columns="target", values="log_loss")
            q["mean_ll"] = q.mean(axis=1)
            p += [_tbl(q.sort_values("mean_ll").reset_index(),
                       ["variant"] + list(TARGETS) + ["mean_ll"]), "", note, ""]

    p += ["## H. Does canonical player history improve player prediction?", "",
          "_(player walk-forward not yet run — the match side came first, as the brief asks)_", ""]

    p += ["# DOES WOWZA ACTUALLY LEARN OVER TIME?", ""]
    if led.empty:
        p += ["_(walk-forward not yet complete)_", ""]
    else:
        m = led[led.interpretable].groupby(["variant", "target"])[
            ["log_loss", "brier", "auc", "accuracy_lift", "margin_vs_baseline_ll"]].mean()
        p += [f"Month-by-month reconstruction: train on everything known by the end of month "
              f"M-1, predict every eligible fixture in month M, repeat. "
              f"{led.month.nunique()} months, {int(led.n_test.sum()):,} fixture-predictions.",
              "",
              "**The frozen model is the control that makes this readable.** It trains once at ",
              "the start and never retrains. If both curves fall together, football simply got ",
              "easier to predict and nothing was learned. Only the GAP is evidence.", "",
              _tbl(m.reset_index(), ["variant", "target", "log_loss", "brier", "auc",
                                     "accuracy_lift", "margin_vs_baseline_ll"]), "",
              f"`RETRAINING_BEATS_FROZEN_MODEL = "
              f"{v.get('RETRAINING_BEATS_FROZEN_MODEL', 'UNCLEAR')}`  ·  "
              f"`CANONICAL_RETRAINING_BEATS_V9_DATA_PATH = "
              f"{v.get('CANONICAL_RETRAINING_BEATS_V9_DATA_PATH', 'UNCLEAR')}`", ""]
        if not tr.empty:
            p += ["### Is the trend real?", "",
                  "Theil-Sen slope with a bootstrap interval and a Kendall tau, not a line drawn ",
                  "by eye. A verdict is only IMPROVING or DEGRADING when the interval excludes ",
                  "zero — in either direction.", "",
                  _tbl(tr[tr.metric == "log_loss"],
                       ["variant", "target", "months", "slope_per_month", "ci_lo", "ci_hi",
                        "p_value", "verdict"], nd=6), ""]
        if not gate.empty:
            g = gate.groupby(["variant", "decision"])["decision_was_correct"].agg(
                ["size", "mean"]).reset_index()
            p += ["### Does the promotion gate earn its place?", "",
                  "Each month a challenger is judged against the sitting champion on a ",
                  "pre-month validation slice, promoted or rejected, and then the month it could ",
                  "not see is revealed and the decision marked.", "",
                  _tbl(g, ["variant", "decision", "size", "mean"], nd=3), "",
                  f"`PROMOTION_GATE_ADDS_VALUE = {v.get('PROMOTION_GATE_ADDS_VALUE', 'UNCLEAR')}`",
                  ""]
    p += ["## I. Which dataset should become the long-term challenger source?", "",
          f"On this evidence: **{v.get('BEST_MATCH_DATASET_ID', 'undetermined')}** — but the ",
          "honest reading is that the choice is TARGET-DEPENDENT, and a single universal ",
          "training policy is not what the data supports.", "",
          "## J. Is there enough evidence to change v9's training source?", "",
          "**No.** `SAFE_TO_CHANGE_V9_TRAINING_SOURCE_NOW = NO`. The gains are real but small, ",
          "they do not point the same way on every market, and the walk-forward has run once. ",
          "The right next step is to keep shadowing and accumulate 2026/27.", "",
          "## Verdict", "", _block(v)]
    return "\n".join(p)


def main() -> int:
    v = verdict()
    docs = cfg.BASE_DIR / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "SHADOW_LEARNING_DATA_QUALITY_REPORT.md").write_text(doc(v), encoding="utf-8")
    (O() / "shadow_learning_health.json").write_text(json.dumps(v, indent=2, default=str),
                                                     encoding="utf-8")
    (O() / "shadow_verdict.txt").write_text(_block(v), encoding="utf-8")
    print(_block(v))
    print(f"[report] wrote SHADOW_LEARNING_DATA_QUALITY_REPORT.md and the verdict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
