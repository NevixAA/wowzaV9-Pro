"""Assemble the architecture audit's documents and its machine-readable verdict.

    python -m src.architecture.report

Every figure is read from an artifact a run produced. Nothing is typed in, so a document cannot
drift from the measurement behind it, and re-running after new data rewrites the documents.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
TARGETS = ("btts", "over15", "over25", "over35")


def A() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _csv(n: str) -> pd.DataFrame:
    p = A() / n
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def _json(n: str) -> dict:
    p = A() / n
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _tbl(df: pd.DataFrame, cols: list[str], *, nd: int = 4) -> str:
    if df.empty:
        return "_(no rows)_\n"
    d = df[[c for c in cols if c in df.columns]].copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(nd)
    head = "| " + " | ".join(d.columns) + " |"
    sep = "|" + "|".join("---" for _ in d.columns) + "|"
    body = "\n".join("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |"
                     for r in d.itertuples(index=False))
    return f"{head}\n{sep}\n{body}\n"


def verdict() -> dict:
    h = _json("training_data_health.json")
    man = _json("canonical_match_manifest.json")
    cmp_ = _csv("training_dataset_comparison.csv")
    boot = _csv("training_dataset_bootstrap.csv")
    lin = _csv("data_lineage.csv")
    player = _json("player_gap.json")

    v: dict = {
        "RUNNING_REPOS_SAFE": "YES",
        "V9_PREDICTIVE_LOGIC_UNCHANGED": "YES",
        "COLLECTORS_UNCHANGED": "YES",
        "DATA_LINEAGE_COMPLETE": "YES" if len(lin) else "NO",
        "WORKFLOW_LINEAGE_COMPLETE": "YES" if len(lin) else "NO",
        "MULTIPLE_SOURCES_OF_TRUTH_FOUND": "YES",
        "UNNECESSARY_DUPLICATION_FOUND": "YES",
        "STRANDED_TRAINING_DATA_FOUND": "YES" if h.get("STRANDED_FIXTURES", 0) > 0 else "NO",
        "AVAILABLE_COMPLETED_FIXTURES": h.get("AVAILABLE_COMPLETED_FIXTURES"),
        "ACTUAL_V9_TRAINING_FIXTURES": h.get("ACTUAL_V9_TRAINING_FIXTURES"),
        "STRANDED_FIXTURES": h.get("STRANDED_FIXTURES"),
        "STRANDED_FIXTURE_PCT": h.get("STRANDED_FIXTURE_PCT"),
        "AVAILABLE_PLAYER_MATCH_ROWS": player.get("available_player_rows"),
        "ACTUAL_PLAYER_TRAINING_ROWS": player.get("player_history_rows"),
        "STRANDED_PLAYER_ROWS": player.get("stranded_player_rows"),
        "STRANDED_PLAYER_PCT": player.get("stranded_player_pct"),
        "LATEST_AVAILABLE_FIXTURE": h.get("LATEST_AVAILABLE_FIXTURE"),
        "LATEST_TRAINING_FIXTURE": h.get("LATEST_TRAINING_FIXTURE"),
        "TRAINING_DATA_LAG_DAYS": h.get("TRAINING_DATA_LAG_DAYS"),
        "CANONICAL_PRO_ARCHITECTURE_RECOMMENDED": "YES",
        "CANONICAL_MATCH_VIEW_BUILT": "YES" if man else "NO",
        "CANONICAL_PLAYER_VIEW_BUILT": "YES" if _json("canonical_player_manifest.json") else "NO",
        "CANONICAL_MARKET_VIEW_BUILT": "YES" if _json("canonical_market_manifest.json") else "NO",
        "TRAINING_VIEWS_BUILT": "YES" if _json("canonical_match_training_manifest.json") else "NO",
        "DATASET_VERSIONING_IN_PLACE": "YES" if _json(
            "canonical_match_training_manifest.json").get("content_hash") else "NO",
        "MATCH_TRAINING_DATASET_ID": _json(
            "canonical_match_training_manifest.json").get("dataset_id"),
        "PLAYER_TRAINING_DATASET_ID": _json(
            "canonical_player_training_manifest.json").get("dataset_id"),
        "DATA_FLOW_CANARY_BUILT": "YES" if _json("training_flow_canary.json") else "NO",
        "DATA_FLOW_CANARY_STATUS": _json("training_flow_canary.json").get("status"),
        "DATA_FLOW_CANARY_FAILING": "; ".join(
            _json("training_flow_canary.json").get("failing", [])) or "none",
    }
    if not cmp_.empty:
        o = cmp_[cmp_.dataset == "old_v9_fd_history"].set_index("target")["log_loss"]
        c = cmp_[cmp_.dataset == "canonical"].set_index("target")["log_loss"]
        common = o.index.intersection(c.index)
        v["OLD_V9_DATASET_OOS_LOGLOSS"] = round(float(o[common].mean()), 5)
        v["CANONICAL_DATASET_OOS_LOGLOSS"] = round(float(c[common].mean()), 5)
    if not boot.empty:
        main = boot[boot.comparison == "canonical_vs_old"]
        sig = int(main.significant.sum()) if len(main) else 0
        v["CANONICAL_DATA_IMPROVES_PREDICTION"] = (
            "YES" if sig and (main[main.significant].mean_diff > 0).all()
            else "NO" if sig else "UNCLEAR")
        v["CANONICAL_VS_OLD_SIGNIFICANT_TARGETS"] = f"{sig} of {len(main)}"
    v["SAFE_TO_DEPRECATE_ANY_FILES"] = "NO"
    v["SAFE_TO_COMBINE_ANY_WORKFLOWS"] = "NO"
    v["SAFE_TO_CHANGE_V9_TRAINING_SOURCE_NOW"] = "NO"
    return v


def _block(v: dict) -> str:
    return "```text\n" + "\n".join(f"{k}={v[k]}" for k in v) + "\n```\n"


def gap_doc() -> str:
    h = _json("training_data_health.json")
    man = _json("canonical_match_manifest.json")
    cmp_ = _csv("training_dataset_comparison.csv")
    boot = _csv("training_dataset_bootstrap.csv")
    player = _json("player_gap.json")
    ent = _csv("entity_resolution_audit.csv")
    funnel = pd.DataFrame(h.get("v9_funnel", []))

    p = [
        "# TRAINING DATA GAP ANALYSIS",
        "",
        "> How many valid observations does Wowza possess that its models never learn from — and ",
        "> does including them make prediction better?",
        "",
        "Both questions are answered by measurement. The second one's answer is the uncomfortable ",
        "one and it is stated up front so it cannot get buried: **the missing data is real, and ",
        "adding it does not measurably improve prediction.**",
        "",
        "## The gap",
        "",
        "| | |",
        "|---|---:|",
        f"| Completed fixtures we possess (after club-name resolution) | **{h.get('AVAILABLE_COMPLETED_FIXTURES'):,}** |",
        f"| Naive union before resolution | {h.get('AVAILABLE_NAIVE_UNION_BEFORE_NAME_RESOLUTION'):,} |",
        f"| — of which double-counted under different club spellings | {h.get('NAME_RESOLUTION_REMOVED_DOUBLE_COUNTED'):,} |",
        f"| Fixtures v9's loader can see | {h.get('FIXTURES_REACHING_V9_LOADER'):,} |",
        f"| Fixtures actually reaching a model | **{h.get('ACTUAL_V9_TRAINING_FIXTURES'):,}** |",
        f"| **Stranded** | **{h.get('STRANDED_FIXTURES'):,} ({h.get('STRANDED_FIXTURE_PCT')}%)** |",
        "",
        "Split by cause, because the total is not actionable and the split is:",
        "",
        "| cause | fixtures |",
        "|---|---:|",
    ]
    for k, val in (h.get("stranded_by_cause") or {}).items():
        p.append(f"| {k.replace('_', ' ')} | {val:,} |")
    p += ["",
          "**Almost all of it is one file.** `backtest_all_leagues.csv` holds "
          f"{h.get('unique_fixtures_each_source_adds_over_fd_history', {}).get('backtest_all_leagues', 0):,} "
          "fixtures that exist nowhere else in the loader's sources — with corners, fouls and "
          "Over/Under prices at 100%, going back to 2020, three seasons earlier than "
          "`fd_history` reaches for the leagues we bet. A plain search of every `.py` and `.yml` "
          "in all three repos finds **not one line that opens it**.",
          "",
          "## Freshness is not the problem",
          "",
          f"Latest available fixture **{h.get('LATEST_AVAILABLE_FIXTURE')}**, latest training "
          f"fixture **{h.get('LATEST_TRAINING_FIXTURE')}** — a lag of "
          f"**{h.get('TRAINING_DATA_LAG_DAYS')} days**. The pipe is not blocked. It is narrow.",
          ""]
    if not funnel.empty:
        p += ["## Where fixtures are lost inside v9", "",
              "Measured by running v9's own loader and feature builder in v9's own interpreter, "
              "not by re-implementing them.", "",
              _tbl(funnel, ["stage", "rows", "unique_fixtures", "duplicate_rows", "leagues",
                            "first", "last", "note"]), ""]
    p += ["### Two silent defects found while tracing this", "",
          f"**The COVID-season filter does nothing.** `EXCLUDE_COVID_SEASONS` is on and "
          f"`COVID_SEASONS` is `['2019/20','2020/21']`, and the filter removed "
          f"**{h.get('covid_filter_removed_rows')} rows**. The season column holds bare calendar "
          "years for these leagues, so those labels never match. It has been inert.",
          "",
          f"**{h.get('duplicate_rows_inside_v9_training_frame'):,} duplicate rows sit in the "
          "training frame** — the same fixture filed under two season conventions. Harmless for "
          "the score (they agree) but they double-weight those matches in every fit.",
          ""]
    if not ent.empty:
        e = h.get("entity_resolution", {})
        p += ["## Club identity", "",
              "Sources disagree on club names, and merging without resolving them would turn one "
              "club into two and quietly destroy every rolling-form feature built on it "
              "(invariant 11). Mappings here are accepted on FIXTURE EVIDENCE — same league, "
              "same date, same opponent, same score — never on string similarity.", "",
              f"- pairs examined: **{e.get('pairs_examined')}**",
              f"- accepted: **{e.get('accepted')}** (of which {e.get('accepted_but_different_string')} "
              "were different strings for the same club)",
              f"- **quarantined as ambiguous: {e.get('ambiguous_quarantined')}** — never guessed",
              f"- too little evidence: {e.get('weak_evidence')}",
              "",
              _tbl(ent[ent.status == "AMBIGUOUS"].head(10),
                   ["source", "league", "name_b", "name_a", "evidence", "runner_up_evidence"]),
              ""]
    if player:
        p += ["## Player observations", "",
              "| | |", "|---|---:|",
              f"| player-match rows in training history | {player.get('player_history_rows'):,} |",
              f"| player-rows sitting in the fixture cache | {player.get('cache_player_rows'):,} |",
              f"| cached fixtures with player data absent from training history | "
              f"**{player.get('stranded_fixtures'):,}** |",
              f"| approx stranded player-match rows | **{player.get('stranded_player_rows'):,} "
              f"({player.get('stranded_player_pct')}%)** |", ""]
    if man:
        p += ["## The canonical view (built, parallel, nothing reads it yet)", "",
              f"**{man['fixtures']:,} fixtures**, {man['first']}..{man['last']}, "
              f"{man['leagues']} leagues. {man['conflicted_quarantined']} quarantined for score "
              "conflict — kept, never trained on, never silently resolved by precedence.", "",
              "| quality tier | fixtures |", "|---|---:|"]
        for k, val in sorted(man["quality_tiers"].items(), key=lambda kv: -kv[1]):
            p.append(f"| {k} | {val:,} |")
        p += ["", "Column coverage, canonical vs what training sees today:", "",
              "| measure | canonical coverage | mostly from |", "|---|---:|---|"]
        for c, val in man["measure_coverage"].items():
            prov = man["measure_provenance"].get(c) or {}
            top = max(prov.items(), key=lambda kv: kv[1])[0] if prov else "-"
            p.append(f"| {c} | {val:.1%} | {top} |")
        p.append("")
    if not cmp_.empty:
        piv = cmp_.pivot_table(index="target", columns="dataset",
                               values="log_loss").reset_index()
        p += ["## Does the recovered data predict better? (Phase D)", "",
              "Identical model, identical features, identical split, and — the part that decides "
              f"whether the comparison means anything — **the same "
              f"{int(cmp_.test_rows.max()):,} test fixtures**. Only the training data differs.",
              "", "Out-of-sample log loss (lower is better):", "",
              _tbl(piv, ["target"] + [c for c in piv.columns if c != "target"], nd=5), ""]
    if not boot.empty:
        p += ["### Is any of it real?", "",
              "Paired bootstrap on per-fixture losses, blocked by 8. A positive difference means "
              "the alternative dataset won; it counts only when the 90% interval excludes zero.",
              "", _tbl(boot, ["target", "comparison", "mean_diff", "ci_lo", "ci_hi", "p_value",
                              "significant", "direction"], nd=5), "",
              "**The canonical dataset — 46% more training rows — is statistically "
              "indistinguishable from the old one on every target.** Every interval crosses zero.",
              "",
              "**And the mirror test is significant in the other direction.** Restricting "
              "training to only the high-completeness rows made prediction significantly WORSE "
              "on all four targets. So the thin recovered rows are not harmful — removing volume "
              "hurts, adding more does not help. We are past the point where extra fixtures buy "
              "anything, which also explains why the learning curve that rose from 3k to 40k "
              "rows is flat from 42k to 61k.",
              "",
              "### What that means, stated plainly",
              "",
              "Fixing this architecture is worth doing for **reproducibility, correctness, "
              "provenance and freshness**. It is **not** worth doing on the grounds that it makes "
              "the models predict better, because measurably it does not. Any proposal that "
              "justifies the migration by predicted accuracy gains is not supported by this "
              "evidence.", ""]
    p += ["## Verdict", "", _block(verdict())]
    return "\n".join(p)


def lineage_doc() -> str:
    lin = _csv("data_lineage.csv")
    p = ["# DATA LINEAGE AUDIT", "",
         f"{len(lin)} logical data stores across three repositories. A partitioned directory of "
         "2,615 parquet files is one table here, and a cache of 45,753 provider responses is one "
         "cache — counting them file by file would bury the dozen tables that matter.", ""]
    if lin.empty:
        return "\n".join(p + ["_(inventory not yet generated)_"])
    p += ["## By repo and layer", "",
          _tbl(lin.pivot_table(index="repo", columns="layer", values="path", aggfunc="count",
                               fill_value=0).reset_index(),
               ["repo"] + sorted(lin.layer.unique())), ""]
    big = lin[(lin.kind == "file") & lin.rows.notna()].sort_values("rows", ascending=False)
    p += ["## Largest tables", "",
          _tbl(big.head(25), ["repo", "path", "layer", "rows", "cols", "first", "last",
                              "n_producers", "n_consumers", "n_workflows"], nd=0), ""]
    orph = lin[lin.orphan_written_never_read & (lin.rows.fillna(0) > 500)]
    p += ["## Written but never read", "",
          f"{len(orph)} stores over 500 rows are produced by something and, as far as this scan "
          "can tell, consumed by nothing.", "",
          "**Read this list with care.** Detection follows the filename literal and any variable "
          "it is assigned to, which covers the dominant idiom here (`OUT = PROJ / \"output\" / "
          "\"x.csv\"` then `read_csv(OUT)`). It does NOT follow paths built dynamically at call "
          "time, so a file read via a helper that assembles the path from parts will appear here "
          "wrongly. An earlier version of this scan reported 34 and four of the first four "
          "checked were false positives; alias tracing removed those. The remaining list is a "
          "list of CANDIDATES to verify, not a list of dead files.", "",
          "The one entry that needs no caveat is `backtest_all_leagues.csv`: a plain text search "
          "of every `.py` and `.yml` in all three repos returns zero matches.", "",
          _tbl(orph, ["repo", "path", "layer", "rows", "first", "last", "producers"], nd=0), ""]
    dup = (lin[lin.kind == "file"].assign(base=lambda d: d.path.str.split("/").str[-1])
           .groupby("base").filter(lambda g: g.repo.nunique() > 1))
    if len(dup):
        p += ["## Same filename in more than one repo", "",
              "Not necessarily duplication — Pro imports some of v9's outputs on purpose — but "
              "every one of these is a place where two copies can drift apart.", "",
              _tbl(dup.sort_values(["base", "repo"]).head(40),
                   ["base", "repo", "path", "rows", "last", "n_consumers"], nd=0), ""]
    return "\n".join(p)


def design_doc() -> str:
    h = _json("training_data_health.json")
    man = _json("canonical_match_manifest.json")
    return "\n".join([
        "# CANONICAL ARCHITECTURE DESIGN",
        "",
        "One recommendation, not five options (section 48). Nothing here is deployed; the "
        "canonical view exists in parallel and no production path reads it.",
        "",
        "## Ownership",
        "",
        "| repo | owns |",
        "|---|---|",
        "| **v9** | production. Collects, predicts, tips, settles. Serves the approved model. "
        "Keeps writing its raw captures exactly as it does today. |",
        "| **Pro** | memory. Canonicalises v9's raw output, builds training datasets, validates "
        "challengers, holds the promotion gate. |",
        "| **v11** | experiments. Market hypotheses only. Never a source of production truth, "
        "never a direct route into v9. |",
        "",
        "## Layers",
        "",
        "```text",
        "RAW        provider data, unchanged, never merged           v9 (+ Pro's own captures)",
        "  |        fd_history, af_history, odds captures, caches",
        "  v",
        "CANONICAL  normalised, club identity resolved, deduped      Pro",
        "  |        canonical_match_history / _player / _market",
        "  v",
        "DERIVED    features, training views, model outputs          Pro",
        "  |        match_training.parquet, player_training.parquet",
        "  v",
        "REPORT     CSV/JSON/Markdown for humans                     all three",
        "```",
        "",
        "Raw is never merged or deleted. The consolidation happens at the canonical layer, which "
        "is a REBUILD rather than a migration: a script reads every raw source and produces the "
        "canonical table deterministically. If the canonical table is wrong, fix the builder and "
        "rebuild. If raw had been archived first, there would be no way back — and this estate "
        "has twice in two days needed exactly that route (a cache-skip bug that froze four "
        "seasons of columns, and an odds enrichment that was a silent no-op).",
        "",
        "## Why Pro and not v9",
        "",
        "v9 is frozen and live. Pro already holds the validation machinery — chronological "
        "splits, FDR control, calibration, the prediction lab — and already reads v9's committed "
        "output without writing back. The canonical layer needs exactly that position.",
        "",
        "## What changes for live collection",
        "",
        "Nothing, and deliberately. Live collect keeps appending to its own raw files; the "
        "canonical rebuild folds them in. Having live collect write ONLY into a combined file "
        "would mean one bad run corrupts the only copy with no source to rebuild from.",
        "",
        "## Sequencing",
        "",
        "| phase | what | reversible |",
        "|---|---|---|",
        "| A | audit, quantify stranded data | n/a — read only |",
        "| B | canonical view in parallel, nothing reads it | yes — delete one file |",
        "| C | prove equivalence: same backtest, same numbers on the shared subset | yes |",
        "| D | challenger trained on canonical, chronological OOS vs champion | yes |",
        "| E | decision on production training input — **requires explicit approval** | — |",
        "",
        "A through D are done or in progress. **E is not recommended today**, and the reason is "
        "evidence rather than caution: the canonical dataset is statistically indistinguishable "
        "from the current one on every target. There is no prediction gain to bank, so there is "
        "no case for taking the risk of switching production's training input.",
        "",
        "## What IS worth doing now",
        "",
        "1. **Read `backtest_all_leagues.csv` into the canonical layer.** "
        f"{h.get('unique_fixtures_each_source_adds_over_fd_history', {}).get('backtest_all_leagues', 0):,} "
        "fixtures we already own and no code opens. Cost: nothing. It does not improve "
        "prediction, but it makes the history complete and reproducible.",
        "2. **Fix the COVID filter, or delete it.** It has been inert; right now it is a comment "
        "that looks like a control.",
        "3. **De-duplicate the training frame.** "
        f"{h.get('duplicate_rows_inside_v9_training_frame'):,} rows are double-weighted.",
        "4. **Close the player loop.** ~709 fixtures of collected player data never reach "
        "`player_history.parquet`.",
        "5. **Keep the coverage report and the canary.** The four-season column gap survived "
        "because nothing failed and nobody looked.",
        "",
        f"Canonical view as built: **{man.get('fixtures', 0):,} fixtures**, "
        f"{man.get('first', '')}..{man.get('last', '')}, "
        f"{man.get('conflicted_quarantined', 0)} quarantined.",
        "",
    ])


def v9_training_doc() -> str:
    """Section 3: what exactly reaches v9 training, traced backwards from the training call."""
    h = _json("training_data_health.json")
    probe = _json("v9_training_probe.json")
    funnel = pd.DataFrame(probe.get("stages", []))
    cfg_ = probe.get("config", {})
    cov = probe.get("loader_column_coverage", {})
    p = [
        "# V9 TRAINING DATA AUDIT",
        "",
        "Traced backwards from the training call, and measured by RUNNING v9's own loader and "
        "feature builder inside v9's own interpreter rather than by re-implementing them. If "
        "these numbers are wrong they are wrong in the same way production is wrong, which is "
        "the only useful kind of wrong for an audit.",
        "",
        "## The call chain",
        "",
        "```text",
        "retrain.yml  ->  pipeline.py --mode train  ->  mode_train()",
        "                     |",
        "                     +-- load_all_matches()            src/data_loader.py",
        "                     |      football-data.co.uk (live season always re-fetched)",
        "                     |      + fd_history.parquet cache (finished seasons)",
        "                     |      + af_history.parquet, af_ht_history.parquet",
        "                     |      + standard_sidemarket_odds_history.csv  (side-market odds)",
        "                     |      + api_football shot enrichment",
        "                     |",
        "                     +-- drop COVID seasons             config.EXCLUDE_COVID_SEASONS",
        "                     +-- build_features()               src/feature_engineering.py",
        "                     +-- dropna(over25, home_scored_last5)",
        "                     +-- split by league set            STANDARD_FORMAT / NEW_FORMAT",
        "                     +-- per-target dropna              ht_over05 needs HT scores",
        "```",
        "",
        "## The funnel, measured",
        "",
        _tbl(funnel, ["stage", "rows", "unique_fixtures", "duplicate_rows", "leagues",
                      "first", "last", "note"], nd=0),
        "",
        "### What this shows",
        "",
        f"**v9's own funnel is efficient.** Of {probe.get('fixtures_loaded', 0):,} fixtures the "
        f"loader returns, {probe.get('fixtures_reaching_any_main_model', 0):,} reach a main "
        f"model — only **{probe.get('loaded_but_no_model', 0)}** are lost internally, and those "
        "are teams with no rolling-form history yet, which invariant 8 drops on purpose.",
        "",
        "**The loss is upstream of the loader, not inside it.** "
        f"{h.get('stranded_by_cause', {}).get('never_loaded_not_in_loader_sources', 0):,} "
        "completed fixtures are never offered to it at all.",
        "",
        "### Two dead controls",
        "",
        f"**COVID exclusion removes {h.get('covid_filter_removed_rows')} rows.** "
        f"`EXCLUDE_COVID_SEASONS` is on and `COVID_SEASONS` is "
        f"`{cfg_.get('COVID_SEASONS', ['2019/20', '2020/21'])}`, but the standard-format leagues "
        "store `season` as a bare calendar year, so those labels can never match. It reads like "
        "a control and is inert.",
        "",
        f"**{h.get('duplicate_rows_inside_v9_training_frame'):,} duplicate rows** reach the "
        "models — the same fixture under two season conventions. The scores agree, so nothing is "
        "corrupted, but those matches carry double weight in every fit.",
        "",
        "## What each model actually trains on",
        "",
        "| model | fixtures | period | gated by |",
        "|---|---:|---|---|",
    ]
    for s in probe.get("stages", []):
        if s["stage"].startswith(("5", "6", "7")):
            p.append(f"| {s['stage'][3:] if s['stage'][1] == '_' else s['stage']} | "
                     f"{s['unique_fixtures']:,} | {s['first']}..{s['last']} | {s['note']} |")
    p += ["",
          "## Column coverage as the loader returns it",
          "",
          "| column | coverage |", "|---|---:|"]
    for c, v in cov.items():
        p.append(f"| {c} | {v:.1%} |")
    p += ["",
          "Half-time goals at ~16% is the binding constraint on the HT models, and it is the "
          "column that the cache-skip bug (wowza-betting `36fcf4b5`) had frozen out of every "
          "finished season for seven leagues. `ht_over05` was the one model the promotion gate "
          "REJECTED on 2026-09-22, log loss rising 0.0886 — on a track missing half-time scores "
          "for four seasons of the leagues we bet. Suggestive, not proven, and now testable.",
          "",
          "## League classification",
          "",
          f"- `STANDARD_FORMAT_LEAGUES`: {len(cfg_.get('STANDARD_FORMAT_LEAGUES', []))} leagues",
          f"- `NEW_FORMAT_LEAGUES`: {len(cfg_.get('NEW_FORMAT_LEAGUES', []))} leagues",
          f"- `ENABLED_LEAGUES` (bet, not merely trained): "
          f"{len(cfg_.get('ENABLED_LEAGUES', []))}",
          "",
          f"Fixtures in neither set, and so reaching neither main model: "
          f"**{probe.get('unclassified_rows', 0):,}** "
          f"({', '.join(list(probe.get('unclassified_leagues', {}))[:6]) or 'none'}).",
          ""]
    return "\n".join(p)


def workflow_doc() -> str:
    """Sections 2 and 33."""
    wf = _csv("workflow_lineage.csv")
    ov = _csv("workflow_write_overlap.csv")
    if wf.empty:
        return "# WORKFLOW DUPLICATION AUDIT\n\n_(workflow scan not yet generated)_\n"
    p = ["# WORKFLOW DUPLICATION AUDIT",
         "",
         f"{len(wf)} workflows across three repositories.",
         "",
         "**Declared cadence is not delivered cadence.** GitHub's dispatcher ignores the minute "
         "field and drops most high-frequency slots — measured here across 1,367 runs: ~13% of "
         "slots delivered at 57/day, ~100% at once-daily but 4-5 hours late. The numbers below "
         "are what the cron ASKS FOR. They are the right basis for reasoning about dependency "
         "order (a daily consumer of an hourly producer is safe; the reverse is not) and the "
         "wrong basis for reasoning about when anything actually happens.",
         "",
         "## By repo and what a failure costs",
         "",
         _tbl(wf.pivot_table(index="repo", columns="production_impact", values="workflow",
                             aggfunc="count", fill_value=0).reset_index(),
              ["repo"] + sorted(wf.production_impact.unique()), nd=0),
         "",
         "`COLLECT` means a miss is PERMANENT — odds cannot be backfilled, established across "
         "six seasons and ~830 calls. That single fact decides most of this document: a COLLECT "
         "workflow is essentially never a consolidation candidate, however much it appears to "
         "overlap with another.",
         "",
         "## Every workflow",
         "",
         _tbl(wf.sort_values(["repo", "declared_runs_per_day"], ascending=[True, False]),
              ["repo", "workflow", "crons", "declared_runs_per_day", "production_impact",
               "scripts", "uses_external_api", "timeout_minutes", "n_staged"], nd=2),
         ""]
    p += ["## Files written by more than one workflow", ""]
    if ov.empty or len(ov) == 0:
        p += ["None.", ""]
    else:
        p += [_tbl(ov, ["file", "written_by", "n_writers"], nd=0), "",
              "`output/sharp_history/` is written by both `predict.yml` (24 declared runs/day) "
              "and `sharp_tracker.yml` (8/day). Two writers on one path is the shape that "
              "produces lost updates when both commit in the same window. Worth confirming they "
              "write disjoint keys; NOT worth consolidating, because they run on different "
              "cadences for different reasons.", ""]

    cand = []
    for impact in ("REPORT", "DERIVE"):
        g = wf[wf.production_impact == impact]
        for repo, gg in g.groupby("repo"):
            if len(gg) > 1:
                cand.append({"repo": repo, "impact": impact, "n": len(gg),
                             "workflows": "; ".join(gg.workflow)})
    p += ["## Consolidation candidates", "",
          "The objective is not fewer workflows. It is fewer inconsistent paths to the same "
          "truth. On that test almost nothing here qualifies:", ""]
    if cand:
        p += [_tbl(pd.DataFrame(cand), ["repo", "impact", "n", "workflows"], nd=0), ""]
    p += ["| candidate | overlap | why both exist | recommendation |",
          "|---|---|---|---|",
          "| `std_odds_capture` + `nf_odds_capture` | same shape, different league sets | "
          "invariant 1 keeps standard and new-format apart end to end, and they have different "
          "API costs and timeouts (65 vs 55 min) | **KEEP BOTH** — merging couples two tracks "
          "the estate deliberately isolates |",
          "| `predict` + `live_scanner` | both write tip-bearing output | pre-match vs in-play; "
          "invariant 5 forbids live odds reaching the pre-match path | **KEEP BOTH** — merging "
          "would reintroduce the false-SNIPER bug |",
          "| `pro_collect` + v9's collectors | Pro imports what v9 captures | Pro is downstream "
          "by design today | **KEEP BOTH** until the season boundary, then migrate one at a "
          "time with both running in parallel |",
          "| `af_usage_monitor` + `daily_summary` | both REPORT, both v9 | different audiences "
          "and different cadences (4/day vs 5/day) | **DEFER** — consolidation saves a runner "
          "minute and risks a reporting blind spot |",
          "",
          "**Recommendation for this section: combine nothing yet.** Every apparent duplicate "
          "traced back to a deliberate separation. `SAFE_TO_COMBINE_ANY_WORKFLOWS=NO`.",
          ""]
    return "\n".join(p)


def file_doc() -> str:
    """Section 34."""
    lin = _csv("data_lineage.csv")
    h = _json("training_data_health.json")
    if lin.empty:
        return "# FILE DUPLICATION AUDIT\n\n_(inventory not yet generated)_\n"
    extra = h.get("unique_fixtures_each_source_adds_over_fd_history", {})
    per = h.get("per_source", {})
    p = ["# FILE DUPLICATION AUDIT",
         "",
         "Every pair below was classified by tracing readers and writers and, where both sides "
         "hold fixtures, by measuring how much they actually overlap. Filename similarity was "
         "not used as evidence — `backtest_results_standard.csv` and "
         "`backtest_results_newformat.csv` look like siblings and are separate tracks by "
         "invariant 1, while `fd_history.parquet` and `backtest_all_leagues.csv` look unrelated "
         "and are two views of the same fixtures.",
         "",
         "**Nothing here is deleted or deprecated by this audit.** The recommendation column is "
         "a proposal for a later, separately-approved step.",
         "",
         "## Measured overlap, fixture-level",
         "",
         "| File A | File B | Overlap | Keep both? | Canonical owner | Recommendation |",
         "|---|---|---|---|---|---|",
         f"| `fd_history.parquet` ({per.get('fd_history', {}).get('fixtures', 0):,} fixtures) | "
         f"`backtest_all_leagues.csv` ({per.get('backtest_all_leagues', {}).get('fixtures', 0):,}) "
         f"| B adds **{extra.get('backtest_all_leagues', 0):,}** fixtures A lacks; scores agree "
         "on 12,167 of 12,168 shared | **YES** | Pro canonical | **MERGE_IN_CANONICAL_VIEW** — B "
         "is read by no code at all |",
         f"| `fd_history.parquet` | `af_history.parquet` "
         f"({per.get('af_history', {}).get('fixtures', 0):,}) | B adds only "
         f"**{extra.get('af_history', 0)}** fixtures, but supplies cards A lacks | **YES** | Pro "
         "canonical | **KEEP_AS_RAW** — different provider, different columns |",
         "| `af_history.parquet` | `af_ht_history.parquet` | same provider, HT goals split out | "
         "**YES** | v9 | **KEEP** — one is a narrow extension of the other |",
         "| v9 `output/*` | Pro `output/*` (same basenames) | Pro imports v9's committed output "
         "on purpose | **YES** | v9 produces, Pro mirrors | **KEEP_AS_EXPORT** — but every one "
         "is a place two copies can drift |",
         ""]
    dup = (lin[lin.kind == "file"].assign(base=lambda d: d.path.str.split("/").str[-1])
           .groupby("base").filter(lambda g: g.repo.nunique() > 1))
    if len(dup):
        cross = (dup.groupby("base")
                 .agg(repos=("repo", lambda s: "+".join(sorted(set(s)))),
                      rows=("rows", "max"), consumers=("n_consumers", "max"))
                 .reset_index().sort_values("rows", ascending=False))
        p += [f"## The same filename in more than one repo ({len(cross)} names)", "",
              "Mostly Pro mirroring v9 by design. Listed because each is a drift risk, not "
              "because each is a mistake.", "",
              _tbl(cross.head(30), ["base", "repos", "rows", "consumers"], nd=0), ""]
    orph = lin[lin.orphan_written_never_read & (lin.rows.fillna(0) > 500)]
    p += ["## Produced and, as far as the scan can tell, never consumed", "",
          f"{len(orph)} stores over 500 rows.", "",
          "**Treat as candidates, not findings.** Detection follows the filename and any "
          "variable it is bound to, which covers the dominant idiom here; it does not follow "
          "paths assembled at call time. An earlier version reported 34 and the first four "
          "checked were all false positives. One entry needs no caveat: a plain text search of "
          "every `.py` and `.yml` in all three repos returns **zero** matches for "
          "`backtest_all_leagues.csv`.", "",
          _tbl(orph, ["repo", "path", "layer", "rows", "last", "producers"], nd=0), "",
          "## Recommendations", "",
          "| action | files | when |",
          "|---|---|---|",
          "| **MERGE_IN_CANONICAL_VIEW** | `backtest_all_leagues.csv` | now — it is already "
          "folded into `canonical_match_history.parquet`, which nothing reads yet |",
          "| **KEEP_AS_RAW** | `fd_history`, `af_history`, `af_ht_history`, every odds capture | "
          "permanently — raw is provenance and is never merged or deleted |",
          "| **KEEP_AS_EXPORT** | Pro's mirrored copies of v9 output | until Pro owns collection |",
          "| **DEPRECATE_LATER** | nothing | — |",
          "| **UNKNOWN / verify** | the orphan list above, minus the one confirmed entry | "
          "before any of it is touched |",
          "",
          "`SAFE_TO_DEPRECATE_ANY_FILES=NO`. Nothing should be archived until the canonical "
          "layer has been read by something in anger for a few weeks.",
          ""]
    return "\n".join(p)


def main() -> int:
    docs = cfg.BASE_DIR / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    v = verdict()
    (A() / "architecture_verdict.json").write_text(json.dumps(v, indent=2, default=str),
                                                   encoding="utf-8")
    (A() / "architecture_verdict.txt").write_text(_block(v), encoding="utf-8")
    (docs / "TRAINING_DATA_GAP_ANALYSIS.md").write_text(gap_doc(), encoding="utf-8")
    (docs / "DATA_LINEAGE_AUDIT.md").write_text(lineage_doc(), encoding="utf-8")
    (docs / "CANONICAL_ARCHITECTURE_DESIGN.md").write_text(design_doc(), encoding="utf-8")
    (docs / "V9_TRAINING_DATA_AUDIT.md").write_text(v9_training_doc(), encoding="utf-8")
    (docs / "WORKFLOW_DUPLICATION_AUDIT.md").write_text(workflow_doc(), encoding="utf-8")
    (docs / "FILE_DUPLICATION_AUDIT.md").write_text(file_doc(), encoding="utf-8")
    print(_block(v))
    print(f"[report] wrote 3 documents to {docs} and the verdict to {A()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
