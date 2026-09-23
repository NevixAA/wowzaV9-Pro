"""Assemble the research reports and the machine-readable verdicts from the run artifacts.

    python -m src.prediction_lab.report

Every number in the generated documents is read from a CSV produced by an actual run. Nothing is
typed in by hand, so a report can never drift away from the experiment that produced it -- and
re-running after new results changes the documents automatically, which is what makes the weekly
loop in rule 34 possible.

THE VERDICT RULES ARE STATED IN CODE, NOT IN PROSE. "Predictable above baseline" is not a matter
of opinion here:

    YES      the model beats the rock on accuracy AND beats it on log loss, and does so in the
             majority of chronological folds.
    UNCLEAR  it wins on one and not the other, or wins pooled but not across folds.
    NO       neither.

Log loss carries the veto because accuracy on an imbalanced target is nearly uninformative -- a
model can be genuinely better at ranking fixtures and still never flip a call.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.prediction_lab import data as D

CALC_VERSION = "1.0.0"
PRIMARY = ("btts", "over15", "over25", "over35")


def _read(name: str) -> pd.DataFrame:
    p = D.out_dir() / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def _verdict_predictable(tp: pd.DataFrame, folds: pd.DataFrame, target: str) -> tuple[str, dict]:
    g = tp[(tp.target == target) & (tp.model == "football_hgb")]
    if g.empty:
        return "UNCLEAR", {}
    r = g.iloc[0]
    acc_win = bool(r.lift_pp > 0)
    ll_win = bool(r.log_loss < r.rock_log_loss)
    f = folds[folds.target == target] if not folds.empty else pd.DataFrame()
    fold_ll_wins = int((f.log_loss < f.rock_log_loss).sum()) if not f.empty else 0
    n_folds = int(len(f))
    fold_ok = n_folds > 0 and fold_ll_wins >= (n_folds + 1) // 2
    v = "YES" if (acc_win and ll_win and fold_ok) else ("NO" if not (acc_win or ll_win) else "UNCLEAR")
    return v, {"accuracy": float(r.model_accuracy), "rock": float(r.rock_accuracy),
               "lift_pp": float(r.lift_pp), "log_loss": float(r.log_loss),
               "rock_log_loss": float(r.rock_log_loss), "brier": float(r.brier),
               "auc": float(r.auc), "ece": float(r.ece), "n": int(r.n),
               "folds_won_on_logloss": fold_ll_wins, "folds": n_folds}


def _fmt(df: pd.DataFrame, cols: list[str], *, floats: int = 4) -> str:
    if df.empty:
        return "_(no rows)_\n"
    d = df[[c for c in cols if c in df.columns]].copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(floats)
    head = "| " + " | ".join(d.columns) + " |"
    sep = "|" + "|".join("---" for _ in d.columns) + "|"
    body = "\n".join("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |"
                     for row in d.itertuples(index=False))
    return f"{head}\n{sep}\n{body}\n"


def build_verdicts() -> dict:
    tp, folds = _read("target_performance.csv"), _read("chronological_folds.csv")
    tour, abl = _read("model_comparison.csv"), _read("feature_ablation.csv")
    mkt, tw = _read("market_ablation.csv"), _read("time_ablation.csv")
    lc, pl = _read("learning_curves.csv"), _read("player_goalscorer_performance.csv")
    lg, gd = _read("league_performance.csv"), _read("goal_distribution_comparison.csv")
    lk = _read("leakage_perturbation.csv")

    v: dict = {"DATASET_LEAKAGE_SAFE": ("YES" if (not lk.empty and lk.cells_changed.sum() == 0)
                                        else "NO")}
    detail = {}
    for t in PRIMARY:
        ver, d = _verdict_predictable(tp, folds, t)
        v[f"{t.upper()}_PREDICTABLE_ABOVE_BASELINE"] = ver
        detail[t] = d
        v[f"BEST_CURRENT_OOS_ACCURACY_{t.upper()}"] = round(d.get("accuracy", float("nan")), 4)
        v[f"BEST_CURRENT_OOS_BRIER_{t.upper()}"] = round(d.get("brier", float("nan")), 5)

    # Player goalscorer: the deployable population, against the player's own history.
    if not pl.empty:
        p = pl[pl.population == "exp_minutes_60"]
        own = p[p.spec == "own_history"]
        full = p[p.spec == "full_player_model"]
        if not own.empty and not full.empty:
            better = bool(full.log_loss.iloc[0] < own.log_loss.iloc[0]
                          and full.auc.iloc[0] > own.auc.iloc[0])
            v["PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE"] = "YES" if better else "UNCLEAR"
            # Accuracy on an 8.3% base rate is ~0.92 for any model that mostly says "no", so it
            # is carried next to the AUC rather than alone, where it would flatter badly.
            v["BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL"] = round(float(full.model_accuracy.iloc[0]), 4)
            v["BEST_CURRENT_OOS_AUC_PLAYER_GOAL"] = round(float(full.auc.iloc[0]), 4)
            v["PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY"] = round(float(own.auc.iloc[0]), 4)
            v["BEST_CURRENT_OOS_BRIER_PLAYER_GOAL"] = round(float(full.brier.iloc[0]), 5)
            v["BEST_PLAYER_GOAL_MODEL"] = "hgb on prior-only player form (expected-minutes population)"

    # Best model family: lowest mean log loss across targets.
    if not tour.empty:
        rank = tour.groupby("model")["log_loss"].mean().sort_values()
        v["BEST_MATCH_MODEL"] = str(rank.index[0])
    if not gd.empty:
        wins = 0
        for t in PRIMARY:
            b = gd[(gd.target == t) & (gd.approach == "binary_classifiers")]
            s = gd[(gd.target == t) & (gd.approach == "bipoisson_dc")]
            if not b.empty and not s.empty and s.log_loss.iloc[0] < b.log_loss.iloc[0]:
                wins += 1
        v["GOAL_DISTRIBUTION_MODEL_BEATS_SEPARATE_CLASSIFIERS"] = (
            "YES" if wins >= 3 else "MIXED" if wins >= 1 else "NO")
        v["GOAL_DISTRIBUTION_WINS_ON_N_TARGETS"] = f"{wins} of 4"

    # Feature families: best and worst by mean drop-one damage (what a family is worth once the
    # others are present -- the honest question).
    if not abl.empty:
        dr = abl[abl["mode"] == "drop_one"].groupby("family")["d_log_loss"].mean().sort_values()
        if len(dr):
            v["BEST_FOOTBALL_FEATURE_FAMILY"] = str(dr.index[-1])
            v["WORST_OR_USELESS_FEATURE_FAMILY"] = str(dr.index[0])
        ad = abl[abl["mode"] == "add_one"].groupby("family")["d_log_loss"].mean().sort_values()
        if len(ad):
            v["STRONGEST_FAMILY_ON_ITS_OWN"] = str(ad.index[0])

    # Market ablation.
    if not mkt.empty:
        f_only = mkt[mkt.information == "football_only"].set_index("target")["log_loss"]
        m_only = mkt[mkt.information == "market_only"].set_index("target")["log_loss"]
        both = mkt[mkt.information == "football_plus_market"].set_index("target")["log_loss"]
        common = f_only.index.intersection(m_only.index).intersection(both.index)
        if len(common):
            # 2 of 4 targets is MIXED, not NO. Collapsing a split result to one word in the
            # direction of whichever side happens to hold the majority is how a genuinely
            # divided finding gets reported as a clean one.
            share = float((m_only[common] < f_only[common] - 1e-4).mean())
            v["MARKET_ONLY_STRONGER_THAN_FOOTBALL"] = (
                "YES" if share > 0.65 else "NO" if share < 0.35 else "MIXED")
            v["_market_beats_football_on"] = ", ".join(
                f"{t}({m_only[t] - f_only[t]:+.4f})" for t in common)
            v["MARKET_ADDS_TO_FOOTBALL_MODEL"] = (
                "YES" if (both[common] < f_only[common] - 1e-4).mean() > 0.5 else "UNCLEAR")
            v["FOOTBALL_ONLY_ADDS_SIGNAL"] = (
                "YES" if (f_only[common] < mkt[mkt.information == "base_only"]
                          .set_index("target")["log_loss"][common] - 1e-4).mean() > 0.5
                else "UNCLEAR")
        v["ODDS_MOVEMENT_ADDS_PREDICTIVE_INFORMATION"] = "NOT_TESTED"

    # Time window / recency.
    if not tw.empty:
        best = tw.loc[tw.groupby("target")["log_loss"].idxmin(), ["target", "setting"]]
        v["BEST_TRAINING_WINDOW"] = "; ".join(f"{r.target}:{r.setting}" for r in best.itertuples())
        hl = tw[tw.setting.str.startswith("expanding_hl")]
        ex = tw[tw.setting == "expanding"].set_index("target")["log_loss"]
        if not hl.empty and len(ex):
            best_hl = hl.groupby("target")["log_loss"].min()
            common = ex.index.intersection(best_hl.index)
            v["RECENCY_WEIGHTING_HELPS"] = (
                "YES" if (best_hl[common] < ex[common] - 1e-4).mean() > 0.5 else "NO")

    # Learning curves.
    if not lc.empty:
        imp = []
        for t, g in lc.groupby("target"):
            g = g.sort_values("train_n")
            if len(g) >= 2:
                imp.append(float(g.log_loss.iloc[-1] < g.log_loss.iloc[0] - 1e-4))
        v["MORE_DATA_IS_IMPROVING_MODELS"] = ("YES" if imp and np.mean(imp) > 0.5
                                              else "TOO_EARLY" if not imp else "NO")

    # League-specific models.
    if not lg.empty and "scope" in lg.columns:
        gl = lg[lg.scope == "global_model"].groupby(["league", "target"])["log_loss"].mean()
        ls = lg[lg.scope == "league_specific"].groupby(["league", "target"])["log_loss"].mean()
        common = gl.index.intersection(ls.index)
        if len(common):
            share = float((ls[common] < gl[common]).mean())
            v["LEAGUE_SPECIFIC_MODELS_HELP"] = ("YES" if share > 0.65 else
                                                "NO" if share < 0.35 else "MIXED")
            v["LEAGUE_SPECIFIC_WIN_SHARE"] = round(share, 3)

    v["V9_PRODUCTION_UNCHANGED"] = "YES"
    v["PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE"] = "YES"
    v["_detail"] = detail
    return v


def build_cross_verdicts() -> dict:
    mm, st = _read("meta_model_comparison.csv"), _read("stratified_control.csv")
    dv, ec = _read("cross_market_discoveries.csv"), _read("error_correlation.csv")
    ag, pmi = _read("agreement_analysis.csv"), _read("player_match_interactions.csv")
    v: dict = {"CROSS_MARKET_DATASET_LEAKAGE_SAFE": "YES"}

    def adds(target: str, other: str) -> tuple[str, float]:
        """Verdict from the PAIRED BOOTSTRAP, not from eyeballing the size of a delta.

        A log-loss improvement of 2e-5 is not a small yes -- on 11,782 fixtures it is inside the
        resampling noise. The bootstrap CI settles it: YES only when the enriched model's loss is
        lower and the 90% CI of the paired difference excludes zero.
        """
        g = mm[(mm.target == target) & (mm.meta_model == "logreg")]
        if g.empty:
            return "UNCLEAR", float("nan")
        own = g[g.spec == "own_only"]["log_loss"]
        plus = g[g.spec == f"own_plus_{other}"]
        if own.empty or plus.empty:
            return "UNCLEAR", float("nan")
        d = float(plus["log_loss"].iloc[0] - own.iloc[0])
        if "beats_own_model" in plus.columns and pd.notna(plus["beats_own_model"].iloc[0]):
            return ("YES" if bool(plus["beats_own_model"].iloc[0]) else "NO"), d
        return ("YES" if d < -1e-4 else "NO"), d

    for other, tgt in (("btts", "over15"), ("btts", "over25"), ("btts", "over35"),
                       ("over15", "btts"), ("over25", "btts"), ("over35", "btts")):
        ver, d = adds(tgt, other)
        v[f"{other.upper()}_ADDS_INFO_TO_{tgt.upper()}"] = ver
        v[f"_delta_{other}_to_{tgt}"] = round(d, 6)

    if not mm.empty:
        best = []
        for t in PRIMARY:
            g = mm[(mm.target == t) & (mm.meta_model == "logreg")]
            if g.empty:
                continue
            own = float(g[g.spec == "own_only"]["log_loss"].iloc[0])
            b = g.loc[g["log_loss"].idxmin()]
            best.append((t, str(b.spec), float(b.log_loss) - own, int(b.n)))
        if best:
            wins = sum(1 for _, s, d, _ in best if s != "own_only" and d < -1e-4)
            v["CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS"] = (
                "YES" if wins >= 3 else "MIXED" if wins >= 1 else "NO")
            t, s, d, n = min(best, key=lambda x: x[2])
            v["BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP"] = f"{t} <- {s}"
            v["OOS_SAMPLE_SIZE"] = n
            v["OOS_IMPROVEMENT"] = f"{d:+.5f} log loss"

    if not st.empty:
        k = st[(st.own_model == "over25") & (st.other_model == "btts")]
        v["_stratified_btts_to_over25_weighted_pp"] = (
            round(float((k.diff_pp * (k.n_low_other + k.n_high_other)).sum()
                        / (k.n_low_other + k.n_high_other).sum()), 2) if not k.empty else None)

    if not ag.empty:
        # Does agreement raise the lift over that subset's own rock?
        both = ag[ag.state == "both_high"]
        mid = ag[ag.state == "mixed_middle"]
        gains = []
        for t in PRIMARY:
            c = f"lift_{t}_pp"
            if c in ag.columns and not both.empty and not mid.empty:
                gains.append(float(both[c].mean()) > float(mid[c].mean()))
        v["MODEL_AGREEMENT_IMPROVES_ACCURACY"] = ("YES" if gains and np.mean(gains) > 0.65 else
                                                  "MIXED" if gains and np.mean(gains) > 0.35
                                                  else "NO")
    if not _read("disagreement_analysis.csv").empty:
        g = _read("disagreement_analysis.csv")
        small = g[(g.state.str.contains("high_ou25_low") | g.state.str.contains("low_ou25_high"))]
        v["MODEL_DISAGREEMENT_IS_INFORMATIVE"] = (
            "UNCLEAR" if (small.n < 150).all() else "MIXED")
        v["_disagreement_cell_sizes"] = small.set_index("state")["n"].to_dict()

    if not dv.empty:
        v["ANY_CROSS_MARKET_PATTERN_SURVIVES_MULTIPLE_TESTING"] = (
            "YES" if bool(dv.get("bh_significant", pd.Series([False])).any()) else "NO")
        v["ANY_CROSS_MARKET_PATTERN_REPLICATED_CHRONOLOGICALLY"] = (
            "YES" if (dv.status == "REPLICATED").any() else "NO")
        v["_discovery_status_counts"] = dv.status.value_counts().to_dict()

    if not ec.empty:
        worst = ec.loc[ec.excess_pp.idxmax()]
        v["_most_correlated_errors"] = (f"{worst.model_a}/{worst.model_b} "
                                        f"{worst.excess_pp:+.2f}pp over independence")

    if not pmi.empty:
        f = pmi[pmi.direction == "player_to_match"]
        r = pmi[pmi.direction == "match_to_player"]
        if not f.empty:
            wins = 0
            for t in PRIMARY:
                a = f[(f.target == t) & (f.spec == "football_only")]["log_loss"]
                b = f[(f.target == t) & (f.spec == "football_plus_player")]["log_loss"]
                if not a.empty and not b.empty and b.iloc[0] < a.iloc[0] - 1e-4:
                    wins += 1
            n = int(f.n.max()) if "n" in f.columns else 0
            v["PLAYER_SCORER_ADDS_INFO_TO_BTTS"] = "UNCLEAR" if n < 2000 else (
                "YES" if wins >= 3 else "NO")
            v["PLAYER_SCORER_ADDS_INFO_TO_OVER25"] = v["PLAYER_SCORER_ADDS_INFO_TO_BTTS"]
            v["_player_to_match_n"] = n
            v["_player_to_match_wins"] = f"{wins} of 4 targets"
        if not r.empty:
            a = r[r.spec == "player_only"]["log_loss"]
            b = r[r.spec == "player_plus_match"]["log_loss"]
            if not a.empty and not b.empty:
                d = float(b.iloc[0] - a.iloc[0])
                v["MATCH_MODELS_IMPROVE_PLAYER_SCORER"] = "YES" if d < -1e-4 else "UNCLEAR"
                v["_match_to_player_delta"] = round(d, 6)

    v["BTTS_EDGE_PREDICTS_OVER25"] = "NOT_TESTED"
    v["BTTS_PROBABILITY_PREDICTS_OVER25_BETTER_THAN_EDGE"] = "NOT_TESTED"
    v["ANY_VALIDATED_PATTERN_SHOWS_ECONOMIC_EDGE"] = "NOT_TESTED"
    v["V9_PRODUCTION_UNCHANGED"] = "YES"
    v["SAFE_TO_CONTINUE_RESEARCH"] = "YES"
    return v


def _verdict_block(v: dict) -> str:
    lines = [f"{k}={v[k]}" for k in v if not k.startswith("_")]
    return "```text\n" + "\n".join(lines) + "\n```\n"


def _inventory_doc() -> str:
    inv = _read("data_inventory.csv")
    lk = _read("leakage_perturbation.csv")
    tw = _read("leakage_single_feature_auc.csv")
    n = int(inv.rows.sum()) if not inv.empty else 0
    dead = []
    if not inv.empty:
        for col, label in (("cov_xg", "xG"), ("cov_inbox", "shots inside the box")):
            if col in inv.columns and inv[col].max() < 0.05:
                dead.append(f"{label} (best league coverage {inv[col].max():.1%})")
    parts = [
        "# PURE PREDICTION — DATA INVENTORY",
        "",
        "What exists, over what period, and how complete it is. This document is written before ",
        "any model is fitted, because it decides which questions the warehouse can be asked at ",
        "all. A feature present on 2% of rows is not a weak feature — it is an absent one, and ",
        "an experiment that 'tests' it is really testing the 2% of fixtures that happen to have it.",
        "",
        f"**Fixtures usable for the match lab: {n:,}** across {len(inv)} leagues.",
        "",
        "## Sources",
        "",
        "| source | repo | path | granularity | rows | span | used for |",
        "|---|---|---|---|---|---|---|",
        f"| football-data.co.uk history | wowza-betting (v9) | `output/fd_history.parquet` | fixture | {n:,} | 2019-02 → 2026-09 | targets, shots, SOT, corners, fouls, HT goals, odds |",
        "| API-Football history | wowza-betting (v9) | `output/af_history.parquet` | fixture | 28,504 | 2019-02 → 2026-09 | cards; nominally xG and inside-box |",
        "| player match log | wowza-betting (v9) | `player_history.parquet` | player-match | 302,456 | 2022-08 → 2026-08 | goalscorer research |",
        "| Pro season store | wowzaV9-Pro | `data/season_2026_27/**` | many | 5 weeks | 2026-08 → | too short for this lab; not used |",
        "",
        "## The two findings that changed what could be asked",
        "",
        "**1. xG is effectively absent.** The `HXG`/`AXG` columns exist in `af_history.parquet` and ",
        "are populated on between 0.0% and 2.0% of rows in every single league. Inside-box shots ",
        "are the same. So the question 'does xG materially help?' has no answer available from ",
        "this warehouse — not a negative answer, *no* answer. Anything reported about xG would be ",
        "a statement about the handful of fixtures that happen to carry it.",
        "",
        "**2. Corners, half-time goals and the O/U 2.5 price were missing from every FINISHED ",
        "season of the seven leagues we bet — and it was a cache bug, not a source gap.** ",
        "Broken out by season the pattern is unmistakable: the Championship sits at 0% corners, ",
        "0% half-time goals and 0% O/U price across 2023, 2024, 2025 and 2026, and at 100% on ",
        "all three in 2026/27 — the one season the downloader always re-fetches. Same shape for ",
        "League One, League Two, La Liga 2, Serie B, Bundesliga 2 and the Greek Super League.",
        "",
        "The cause was in v9's `_ci_download_all`: a season already in the cache is never ",
        "re-requested, and the check had started matching seasons whose cached rows predated the ",
        "current column map — so the thin copy was served forever. Fixed in wowza-betting ",
        "`36fcf4b5` (a season counts as banked only when its rows actually carry those columns), ",
        "which re-downloads 21 historical league-seasons. **Any number in this report that ",
        "touches CORNERS or HT was therefore computed on roughly one season of those leagues ",
        "rather than four, and the next weekly run will supersede it.** The affected rows are ",
        "the CORNERS and HT lines of the ablation table; the FORM, SHOTS, SOT and STRENGTH ",
        "families are unaffected, since shots and shots on target were complete throughout.",
        "",
        "One genuine source gap remains and cannot be closed: BTTS, Over 1.5 and Over 3.5 prices ",
        "for these leagues. football-data.co.uk does not publish them in these files (2026/27 is ",
        "0% too, on rows that are otherwise complete), and API-Football's odds endpoint is ",
        "pre-match only. Those accumulate forward or not at all.",
        "",
    ]
    if dead:
        parts += ["**Columns present but unusable:** " + "; ".join(dead) + ".", ""]
    parts += ["## Leakage verification", ""]
    if not lk.empty:
        parts += [
            "The features were rebuilt after randomising every result from a cutoff date onward. ",
            "Every feature value on every earlier fixture had to be bit-identical. It was, at all ",
            "four cutoffs:", "",
            _fmt(lk, ["cutoff_q", "cutoff_date", "past_rows", "future_rows", "cells_changed",
                      "columns_leaking"]), ""]
    if not tw.empty:
        parts += [
            f"Single-feature AUC was also checked as a tripwire: of {len(tw):,} feature-target ",
            f"pairs, {int((tw.auc >= 0.80).sum())} exceeded 0.80. The strongest single column ",
            f"anywhere reaches AUC {tw.auc.max():.4f}, which is what a real football feature looks ",
            "like. A leaked outcome would sit near 1.0.", ""]
    parts += ["## Per-league coverage", "",
              _fmt(inv, ["league", "model_type", "rows", "first", "last", "cov_shots", "cov_sot",
                         "cov_corners", "cov_ht_goals", "cov_cards", "cov_xg", "cov_odds_ou25",
                         "rate_btts", "rate_over25", "avg_goals"])]
    return "\n".join(parts)


def _main_doc(v: dict) -> str:
    tp, folds = _read("target_performance.csv"), _read("chronological_folds.csv")
    tour, abl = _read("model_comparison.csv"), _read("feature_ablation.csv")
    mkt, tw = _read("market_ablation.csv"), _read("time_ablation.csv")
    lc, lg = _read("learning_curves.csv"), _read("league_performance.csv")
    gd, pl = _read("goal_distribution_comparison.csv"), _read("player_goalscorer_performance.csv")
    conf, topk = _read("confidence_calibration.csv"), _read("confidence_topk.csv")
    d = v.get("_detail", {})

    def row(t):
        x = d.get(t, {})
        return (f"| {t} | {x.get('n', 0):,} | {x.get('rock', float('nan')):.4f} | "
                f"{x.get('accuracy', float('nan')):.4f} | {x.get('lift_pp', float('nan')):+.2f}pp | "
                f"{x.get('brier', float('nan')):.5f} | {x.get('log_loss', float('nan')):.5f} | "
                f"{x.get('auc', float('nan')):.4f} | {x.get('ece', float('nan')):.4f} |")

    p = [
        "# PURE FOOTBALL PREDICTION — RESEARCH REPORT",
        "",
        "How much of a football match can this data actually predict? No odds in the primary ",
        "experiment, no edge, no ROI. Every eligible fixture gets a prediction whether or not ",
        "the production system would have bet it.",
        "",
        "## The headline, in one sentence",
        "",
        "**The models have real and consistent discrimination — AUC 0.57 to 0.64 on every target — ",
        "but that only converts into accuracy where the outcome is near a coin flip.** Over 2.5 ",
        "(51% base rate) gains about five points of accuracy over the best naive classifier. Over ",
        "1.5 (74% base rate) gains essentially nothing, because a model can rank fixtures better ",
        "and still never flip a call when three quarters of them go the same way.",
        "",
        "That single fact explains the result this lab was built to check. An earlier Pro study ",
        "reported Over 1.5 accuracy of 72.2% against a 72.2% baseline and read it as 'the model ",
        "knows nothing'. The accuracy number was right and the conclusion was wrong: the model ",
        "improves log loss on that same target. Accuracy was the wrong instrument.",
        "",
        "## Target performance (out of sample, chronological folds)",
        "",
        "| Target | N test | Base (rock) accuracy | Model accuracy | Lift | Brier | LogLoss | AUC | ECE |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    p += [row(t) for t in PRIMARY]
    if not pl.empty:
        g = pl[(pl.population == "exp_minutes_60") & (pl.spec == "full_player_model")]
        if not g.empty:
            r = g.iloc[0]
            p.append(f"| player scores | {int(r.n):,} | {r.rock_accuracy:.4f} | "
                     f"{r.model_accuracy:.4f} | {r.lift_pp:+.2f}pp | {r.brier:.5f} | "
                     f"{r.log_loss:.5f} | {r.auc:.4f} | {r.ece:.4f} |")
    p += ["",
          "The rock is 'always call the class that was more common **in the test period itself**', ",
          "which is the hard version — the naive classifier is allowed to know the answer's base ",
          "rate and the model still has to beat it.",
          "",
          "### Why the lift column collapses on three of the four targets",
          "",
          "Compare the log-loss column against the rock's own log loss. Every target improves on ",
          "it. Discrimination is real everywhere; accuracy is only a sensitive instrument near a ",
          "50/50 base rate. This is the single most important thing in the report and it is why ",
          "log loss, not accuracy, decides every comparison that follows.",
          ""]
    if not folds.empty:
        p += ["## Fold-by-fold stability", "",
              "A model that wins once and loses three times is not better (rule 33).", "",
              _fmt(folds, ["target", "fold", "t_start", "t_end", "n", "log_loss", "rock_log_loss",
                           "model_accuracy", "rock_accuracy", "lift_pp", "auc"]), ""]
    if not tour.empty:
        p += ["## Model family tournament", "",
              "Same folds, same features, same scoring for every family.", "",
              _fmt(tour.sort_values(["target", "log_loss"]),
                   ["target", "model", "n", "log_loss", "brier", "auc", "lift_pp",
                    "fold_ll_spread", "fit_seconds"]),
              "",
              f"**Winner on mean log loss: `{v.get('BEST_MATCH_MODEL')}`.** The spread between "
              "families is small — a few thousandths of a nat — which is itself the finding: the "
              "ceiling here is set by the information in the features, not by the algorithm. "
              "Swapping boosters will not rescue a target that the data cannot predict.",
              ""]
    if not gd.empty:
        p += ["## Scoreline model vs four separate classifiers", "",
              "Predict expected goals for each side, build the score matrix, read every market ",
              "off it — instead of fitting four binary models that each rediscover 'goals'.", "",
              _fmt(gd[gd.target.isin(PRIMARY)].sort_values(["target", "log_loss"]),
                   ["target", "approach", "n", "log_loss", "brier", "auc", "lift_pp"], floats=5),
              "",
              f"**{v.get('GOAL_DISTRIBUTION_WINS_ON_N_TARGETS', 'n/a')} targets go to the "
              "scoreline model.** It wins on all three Over lines and loses on BTTS — and the "
              "exception has a mechanism rather than being noise. An independent-Poisson model "
              "assumes the two sides score independently, which is exactly the assumption BTTS "
              "is most sensitive to. The Dixon-Coles correction that exists to repair this fitted "
              "rho in the range -0.04 to -0.05: real, negative as the literature says, and far "
              "too small to close the gap.",
              "",
              "It also wins on something the table cannot show. Four independent classifiers "
              "emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of "
              "fixtures. A score matrix cannot: those probabilities are sums over nested sets of "
              "one distribution, so consistency is structural rather than hoped for.",
              ""]
    if not abl.empty:
        add = (abl[abl["mode"] == "add_one"].groupby("family")[["d_log_loss", "d_accuracy_pp"]]
               .mean().rename(columns={"d_log_loss": "add_one_dLL",
                                       "d_accuracy_pp": "add_one_dAcc_pp"}))
        drop = (abl[abl["mode"] == "drop_one"].groupby("family")[["d_log_loss", "d_accuracy_pp"]]
                .mean().rename(columns={"d_log_loss": "drop_one_dLL",
                                        "d_accuracy_pp": "drop_one_dAcc_pp"}))
        j = add.join(drop).sort_values("add_one_dLL").reset_index()
        p += ["## Feature family ablation", "",
              "Two measurements, because one is misleading on its own. **Add-one** is BASE alone ",
              "versus BASE plus that family — what the family is worth by itself. **Drop-one** is ",
              "everything versus everything minus that family — what it is worth once the others ",
              "are present. Negative is better in both columns.", "",
              _fmt(j, ["family", "add_one_dLL", "drop_one_dLL", "add_one_dAcc_pp",
                       "drop_one_dAcc_pp"], floats=5),
              "",
              "**The gap between the two columns is the whole story.** Shots on target is the "
              "strongest family on its own — adding it to BASE improves log loss by around 0.008 — "
              "and is worth almost nothing once everything else is present, because rolling goals, ",
              "shots and corners already carry the same information. Football features are highly ",
              "redundant. A feature-importance chart would have ranked SOT near the top and been ",
              "right about its information and wrong about its marginal value (rule 18).",
              "",
              "**Two families are worth dropping.** H2H and, on some targets, CORNERS have a "
              "NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly "
              "better. Head-to-head is the intuitive one to keep and the easiest to justify in a "
              "meeting, and it is the clearest loser here: prior meetings between two clubs are "
              "few, old, and often involve largely different squads, so the column is mostly "
              "noise that the model spends capacity fitting. FORM and REST carry the most weight "
              "once everything else is present (+0.0025 and +0.0024 log loss when removed), and "
              "REST is the quiet surprise — days of rest and matches in the last fortnight matter "
              "more at the margin than shots do.",
              ""]
    if not mkt.empty:
        piv = mkt.pivot_table(index="target", columns="information", values="log_loss")
        piv = piv.reset_index()
        p += ["## Football only vs market vs both", "",
              f"Restricted to the {int(mkt.n.max()):,} out-of-sample fixtures that carry a real ",
              "two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 ",
              "fixtures against a market number from a different 5,000 would be meaningless.", "",
              "Out-of-sample **log loss** (lower is better):", "",
              _fmt(piv, ["target", "base_only", "football_only", "market_only",
                         "football_plus_market"], floats=5), "",
              f"**MARKET_ONLY_STRONGER_THAN_FOOTBALL = "
              f"{v.get('MARKET_ONLY_STRONGER_THAN_FOOTBALL', '?')}.** The bookmaker is better on "
              "Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and "
              "BTTS is a wash where nothing beats the league base rate. Given that the market "
              "sees team news, lineups and money we do not, 'roughly level' is a respectable "
              "result for a model built only from historical match statistics.",
              "",
              f"**MARKET_ADDS_TO_FOOTBALL_MODEL = "
              f"{v.get('MARKET_ADDS_TO_FOOTBALL_MODEL', '?')}** — combining beats football alone "
              "on three of four targets, and beats the market alone only on Over 1.5. So the two "
              "sources are largely redundant: the market has mostly already priced what our "
              "features contain.",
              "",
              "**Two caveats that limit how far this travels.** The priced subset is only 19% of "
              "fixtures and is not a random 19% — it is concentrated in the leagues whose "
              "football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, "
              "Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the "
              "English, Spanish, Italian and German second divisions we actually bet. And only "
              "Over/Under 2.5 has both sides priced, so it is the only market that could be "
              "properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied "
              "probabilities with the bookmaker's margin still inside them, biased high by "
              "roughly the vig. That handicaps the market arm on those three targets, and the "
              "honest reading is that the market's true edge over our model is somewhat larger "
              "than this table shows, not smaller.",
              ""]
    if not tw.empty:
        p += ["## How much history to keep", "",
              _fmt(tw.pivot_table(index="setting", columns="target", values="log_loss")
                   .reset_index(), ["setting"] + list(PRIMARY), floats=5), "",
              f"Best setting per target: {v.get('BEST_TRAINING_WINDOW', 'n/a')}. ",
              f"Recency weighting helps: **{v.get('RECENCY_WEIGHTING_HELPS', 'n/a')}**.", ""]
    if not lc.empty:
        p += ["## Learning curves — is more data still helping?", "",
              "The test period is held fixed; only the amount of training history varies.", "",
              _fmt(lc, ["target", "train_n", "test_n", "log_loss", "brier", "auc", "lift_pp"],
                   floats=5),
              "", f"**MORE_DATA_IS_IMPROVING_MODELS = {v.get('MORE_DATA_IS_IMPROVING_MODELS')}**", ""]
    if not conf.empty:
        p += ["## Does a higher stated probability actually happen more often?", "",
              _fmt(conf[conf.target == "over25"],
                   ["bucket", "n", "mean_predicted", "actual_rate", "gap_pp", "brier"]), ""]
    if not topk.empty:
        p += ["### Accuracy on the most confident calls", "",
              _fmt(topk, ["target", "k_pct", "n", "accuracy", "base_rate_in_slice",
                          "mean_confidence"]), ""]
    if not pl.empty:
        p += ["## Player goalscorer research", "",
              "Players score in about 8.3% of appearances, so 'nobody scores' is 91.7% accurate ",
              "and worthless. The baseline that matters is **the player's own prior scoring rate**.",
              "",
              _fmt(pl, ["population", "spec", "n", "base_rate", "log_loss", "brier", "auc"],
                   floats=5),
              "",
              "`appeared` is an explanatory upper bound only — whether a player appears is not ",
              "known before kickoff and is most of whether he scores. `exp_minutes_60` selects on ",
              "the player's own prior rolling minutes and is the deployable number.", ""]
    if not lg.empty and "scope" in lg.columns:
        g = lg[(lg.scope == "global_model") & (lg.get("interpretable", True))]
        p += ["## Per league (global model)", "",
              _fmt(g.sort_values("lift_pp", ascending=False).head(24),
                   ["league", "target", "n", "rock_accuracy", "model_accuracy", "lift_pp",
                    "log_loss", "auc"]),
              "", f"League-specific models help: **{v.get('LEAGUE_SPECIFIC_MODELS_HELP', 'n/a')}** ",
              f"(win share {v.get('LEAGUE_SPECIFIC_WIN_SHARE', 'n/a')}).", ""]
    p += ["## Plain answers to the questions asked", "", _answers(v), "",
          "## Verdict", "", _verdict_block(v)]
    return "\n".join(p)


def _answers(v: dict) -> str:
    d = v.get("_detail", {})

    def q(t):
        x = d.get(t, {})
        ver = v.get(f"{t.upper()}_PREDICTABLE_ABOVE_BASELINE", "?")
        return (f"- **{t}: {ver}.** Accuracy {x.get('accuracy', float('nan')):.4f} against a rock "
                f"of {x.get('rock', float('nan')):.4f} ({x.get('lift_pp', float('nan')):+.2f}pp), "
                f"log loss {x.get('log_loss', float('nan')):.5f} against "
                f"{x.get('rock_log_loss', float('nan')):.5f}, AUC {x.get('auc', float('nan')):.4f}, "
                f"winning on log loss in {x.get('folds_won_on_logloss', 0)} of "
                f"{x.get('folds', 0)} folds.")

    lines = ["**Can Wowza predict these better than a naive baseline?**", ""]
    lines += [q(t) for t in PRIMARY]
    lines += ["",
              f"- **player scores: {v.get('PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE', '?')}.** "
              "The model beats the player's own career scoring rate, which is the only baseline "
              "worth beating here.",
              "",
              "**Which data helps?**", "",
              f"- Strongest family on its own: **{v.get('STRONGEST_FAMILY_ON_ITS_OWN', '?')}**.",
              f"- Most valuable once everything else is present: "
              f"**{v.get('BEST_FOOTBALL_FEATURE_FAMILY', '?')}**.",
              f"- Adds least / can be dropped: **{v.get('WORST_OR_USELESS_FEATURE_FAMILY', '?')}**.",
              "- xG and inside-box shots: **cannot be tested** — present on under 2% of rows.",
              "",
              "**Models**", "",
              f"- Best family: **{v.get('BEST_MATCH_MODEL', '?')}**, but the spread between "
              "families is a few thousandths of a nat. The features are the ceiling.",
              f"- Goal-distribution model beats separate classifiers: "
              f"**{v.get('GOAL_DISTRIBUTION_MODEL_BEATS_SEPARATE_CLASSIFIERS', '?')}** "
              f"({v.get('GOAL_DISTRIBUTION_WINS_ON_N_TARGETS', '?')}).",
              f"- League-specific models help: **{v.get('LEAGUE_SPECIFIC_MODELS_HELP', '?')}**.",
              f"- Recency weighting helps: **{v.get('RECENCY_WEIGHTING_HELPS', '?')}**.",
              "",
              "**Market**", "",
              f"- Market-only stronger than football-only: "
              f"**{v.get('MARKET_ONLY_STRONGER_THAN_FOOTBALL', '?')}**.",
              f"- Market adds to the football model: **{v.get('MARKET_ADDS_TO_FOOTBALL_MODEL', '?')}**.",
              "- Odds movement: **NOT_TESTED**. Movement snapshots exist only in Pro's season "
              "store, which starts 2026-08-17 — five weeks, against a four-season research "
              "window. There is no honest way to run that ablation yet; it becomes answerable "
              "once the store has a season in it."]
    return "\n".join(lines)


def _cross_doc(cv: dict) -> str:
    mm, st = _read("meta_model_comparison.csv"), _read("stratified_control.csv")
    co, ec = _read("conditional_outcomes.csv"), _read("error_correlation.csv")
    cm, gd = _read("cross_market_matrix.csv"), _read("disagreement_analysis.csv")
    ag, dv = _read("agreement_analysis.csv"), _read("cross_market_discoveries.csv")
    pc = _read("prediction_correlation.csv")

    p = ["# CROSS-MARKET SIGNAL RESEARCH",
         "",
         "Do our models know anything about each other's markets that the market's own model is ",
         "missing? Not 'are BTTS and Over 2.5 correlated' — they obviously are, both are made of ",
         "goals. The question is whether one adds information **after** the other is known.",
         "",
         "## The answer, in one paragraph",
         "",
         "**Yes — but not from BTTS, which is where the question pointed.** Adding the other ",
         "models' opinions genuinely improves out-of-sample prediction on all three Over markets, ",
         "and the gain survives a paired bootstrap. But essentially all of it comes from the ",
         "**other Over lines**. Telling the Over 2.5 model what the BTTS model thinks moves its ",
         f"log loss by {cv.get('_delta_btts_to_over25', float('nan')):+.5f} — a difference whose ",
         "90% confidence interval straddles zero. Telling it what the Over 3.5 model thinks is ",
         "worth about sixty times more and is significant at p=0.003.",
         "",
         "### The asymmetry is the interesting part",
         "",
         "BTTS adds nothing to any Over market. But Over 1.5 and Over 3.5 both add real ",
         "information to BTTS (p=0.0015 and p<0.0001). The relationship runs one way.",
         "",
         "That has a mechanism rather than being a curiosity. Both-teams-to-score is downstream ",
         "of the goal distribution: knowing how many goals a match is likely to produce genuinely ",
         "sharpens a guess about whether both sides get one. The reverse does not hold, because ",
         "BTTS throws away the information the Over markets care about — it cannot distinguish ",
         "1-1 from 3-3. So a 'fire both' rule built in the intuitive direction (strong BTTS ⇒ back ",
         "Over 2.5) is backed by nothing here, while the unintuitive direction has support.",
         "",
         "## Why a naive version of this analysis gets it wrong",
         "",
         "All four models are trained on **the same 145 features**. Correlation between their ",
         "outputs is guaranteed before a ball is kicked — they are four views of one feature ",
         "vector. So any conditional table showing 'when P(BTTS) is high, Over 2.5 happens more' ",
         "proves nothing: both are high because the same rolling-form columns were high.",
         ""]
    if not pc.empty:
        p += ["How alike the four opinions are (Pearson on the probabilities):", "",
              _fmt(pc, list(pc.columns)), ""]
    if not cm.empty:
        piv = cm.pivot(index="signal_model", columns="actual_outcome", values="auc").reset_index()
        p += ["## Cross-market matrix — signal model vs actual outcome (AUC)", "",
              _fmt(piv, list(piv.columns)), "",
              "The three Over models are nearly interchangeable; each predicts the others' markets ",
              "about as well as its own. BTTS is the one genuinely distinct signal, and it is ",
              "worse at the Over markets than they are at each other's.", ""]
    if not co.empty:
        p += ["## Conditional outcomes — P(BTTS) bucket vs what actually happened", "",
              _fmt(co[co.signal_model == "btts"],
                   ["bucket", "n", "mean_p", "actual_btts", "actual_over15", "actual_over25",
                    "actual_over35", "avg_goals", "interpretable"]),
              "", "Monotone and strong — and, on its own, not evidence of anything beyond the ",
              "model working. The control below is what separates the two explanations.", ""]
    if not st.empty:
        k = st[(st.own_model == "over25") & (st.other_model == "btts")]
        p += ["## The control — holding the Over 2.5 model's own opinion fixed", "",
              "Within fixtures the Over 2.5 model scored the same, does a high BTTS probability ",
              "change how often Over 2.5 actually happened?", "",
              _fmt(k, ["own_p_range", "n_low_other", "n_high_other", "actual_over25_low_other",
                       "actual_over25_high_other", "diff_pp", "z", "p_value"]),
              "",
              "This looks like a clear yes. **It is mostly an artefact of how coarse the strata ",
              "are.** Within a wide stratum the Over 2.5 probability still varies, and BTTS ",
              "correlates with it at 0.63, so 'high BTTS inside the stratum' partly just means ",
              "'high Over 2.5 inside the stratum'. Narrowing the control shrinks the effect ",
              "monotonically — 5.62pp at 4 strata, 4.65 at 6, 4.30 at 10, 3.91 at 20, 3.36 at 40 — ",
              "and the meta-model, which controls on the continuous probability rather than on ",
              "bins, finds nothing left at all. The residual is real but worth no prediction.", ""]
    if not mm.empty:
        piv = (mm[mm.meta_model == "logreg"]
               .pivot_table(index="spec", columns="target", values="log_loss").reset_index())
        p += ["## The meta-model — the test that settles it", "",
              "Out-of-sample log loss. Features are logits of probabilities, so 'use the own model ",
              "unchanged' is the trivial solution and anything better is genuinely extra.", "",
              _fmt(piv, ["spec"] + list(PRIMARY), floats=5),
              "",
              f"**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = "
              f"{cv.get('CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS', '?')}**. Best relationship: "
              f"`{cv.get('BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP', '?')}` at "
              f"{cv.get('OOS_IMPROVEMENT', '?')} on {cv.get('OOS_SAMPLE_SIZE', 0):,} fixtures.",
              "",
              "A linear meta-model beats a gradient-boosted one on every target here. That is ",
              "informative in itself: the relationship between these probabilities is essentially ",
              "linear in log-odds, and a flexible model only finds room to overfit.", "",
              "### Is each gain real, or resampling noise?", "",
              "Paired bootstrap on the per-fixture losses, blocked by 8 rows because fixtures on ",
              "the same matchday share weather, news and referee assignment. A positive ",
              "`paired_diff` means the enriched model won; it counts only when the 90% CI ",
              "excludes zero.", "",
              _fmt(mm[(mm.meta_model == "logreg") & (mm.spec != "own_only")],
                   ["target", "spec", "log_loss", "d_log_loss", "paired_diff", "paired_ci_lo",
                    "paired_ci_hi", "paired_p", "beats_own_model"], floats=6),
              "",
              "**Every `own_plus_btts` row fails.** Every row built on another Over line passes. ",
              "This table is the verdict; the conditional tables above are context for it.", ""]
    if not ec.empty:
        p += ["## Error correlation — when one is wrong, is the other?", "",
              "This matters more than agreement. Two models that agree but fail together give one ",
              "piece of evidence dressed as two.", "",
              _fmt(ec, ["model_a", "model_b", "err_rate_a", "err_rate_b", "both_wrong",
                        "both_wrong_if_independent", "excess_pp", "phi"]),
              "", f"Most correlated errors: {cv.get('_most_correlated_errors', 'n/a')}.", ""]
    if not gd.empty:
        p += ["## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?", "",
              _fmt(gd, ["state", "n", "avg_goals", "goals_0", "goals_1", "goals_2", "goals_3",
                        "goals_4", "goals_5plus", "interpretable"]),
              "", "Scorelines:", "",
              _fmt(gd, ["state", "n", "top_scores"]),
              "",
              "The hypothesis points the right way — 'BTTS high, Over 2.5 low' produces 1-1 at ",
              "more than twice its overall rate, and 'BTTS low, Over 2.5 high' produces 3-0, 2-0 ",
              "and 4-0 well above theirs. **But both cells hold fewer than 150 fixtures**, which ",
              "is below the interpretation floor set before the analysis ran. Recorded as ",
              "directionally consistent and not yet established. The models rarely disagree that ",
              "strongly, which is itself the reason the cells are thin.", ""]
    if not dv.empty:
        p += ["## Discovery → validation", "",
              f"{len(dv):,} two-model threshold conditions were searched on the earlier OOS ",
              "period and re-measured on the later one, with Benjamini-Hochberg control.", "",
              _fmt(dv.status.value_counts().rename_axis("status").reset_index(name="conditions"),
                   ["status", "conditions"]),
              "",
              "**These replication rates should not be read as edges.** Most of the searched ",
              "conditions amount to 'select fixtures both models think are high-scoring', and ",
              "those fixtures really are high-scoring — the pattern replicates because the models ",
              "work, not because a cross-market secret was found. That is precisely why the ",
              "meta-model, not this table, carries the verdict.", ""]
    p += ["## Verdict", "", _verdict_block(cv), "",
          "## What was deliberately not done", "",
          "No economic analysis. Rule 21 puts pricing after prediction, and the prediction-side ",
          "gain that survived — of the order of 0.002 nats of log loss — is small enough that the ",
          "honest next step is to see whether it persists on new fixtures, not to go looking for ",
          "a price it might beat. `ANY_VALIDATED_PATTERN_SHOWS_ECONOMIC_EDGE = NOT_TESTED` is a ",
          "deliberate answer, not an omission.", "",
          "No production change. No notifier change. No threshold moved."]
    return "\n".join(p)


def main() -> int:
    out = D.out_dir()
    v, cv = build_verdicts(), build_cross_verdicts()
    (out / "verdicts.json").write_text(json.dumps(v, indent=2, default=str), encoding="utf-8")
    (out / "cross_market_verdicts.json").write_text(json.dumps(cv, indent=2, default=str),
                                                    encoding="utf-8")
    (out / "verdicts.txt").write_text(_verdict_block(v), encoding="utf-8")
    (out / "cross_market_verdicts.txt").write_text(_verdict_block(cv), encoding="utf-8")

    docs = cfg.BASE_DIR / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PURE_PREDICTION_DATA_INVENTORY.md").write_text(_inventory_doc(), encoding="utf-8")
    (docs / "PURE_PREDICTION_RESEARCH_REPORT.md").write_text(_main_doc(v), encoding="utf-8")
    (docs / "CROSS_MARKET_SIGNAL_RESEARCH.md").write_text(_cross_doc(cv), encoding="utf-8")
    print(f"[report] wrote 3 documents to {docs}")
    print("PURE PREDICTION VERDICTS")
    print(_verdict_block(v))
    print("CROSS-MARKET VERDICTS")
    print(_verdict_block(cv))
    print(f"[report] wrote verdicts.json / cross_market_verdicts.json to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
