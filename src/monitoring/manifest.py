"""
output/output_manifest.json — who owns which artifact (Prompt 1.5 sections 28-29).
=================================================================================
    python -m src.monitoring.manifest [--write]

WHAT PROBLEM THIS SOLVES

Three repositories now emit well over a hundred CSV and JSON artifacts between them, and nothing
states which are RAW evidence, which are canonical, which are derived research, and which are
merely health. Without that, two failure modes are indistinguishable from the outside:

  * a derived file that has gone stale looks identical to one that is correctly unchanged
  * two artifacts computing the same concept in different repos look like corroboration
    rather than duplication

CANONICAL DESTINATION IS THE LOAD-BEARING FIELD. For every RAW artifact it names the canonical
table that is supposed to absorb it. That is what makes "v9 produced it but Pro never imported it"
a question anyone can ask mechanically — which is exactly the failure that left four combo tables
empty for four days while their importer ran successfully on every pass.

WHAT THIS IS NOT

Not a file inventory. Listing everything on disk would be noise and would go stale the moment
anyone writes a scratch CSV. This lists artifacts that something DEPENDS ON, each with a stated
owner. An artifact nobody depends on and nobody owns should be deleted, not documented.

DECLARED, NOT DISCOVERED. The entries are written down rather than globbed, because the point is
to record INTENT — what should exist and who owns it. A discovered manifest can only ever say
what does exist, which is the thing being audited, not the standard to audit against. Presence is
then checked against reality and reported per entry, so a missing artifact is visible instead of
silently absent from the list.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import config.pro_config as cfg

CALC_VERSION = "1.0.0"

RAW = "RAW"
CANONICAL = "CANONICAL"
DERIVED = "DERIVED_RESEARCH"
HEALTH = "HEALTH"
REPORT = "REPORT"

V9 = "NevixAA/wowza-betting"
PRO = "NevixAA/wowzaV9-Pro"
V11 = "NevixAA/wowza_v11"


def _e(repo, path, owner, atype, *, source=None, dest=None, no_dest_reason=None,
       append_only=False, lifecycle="ACTIVE", research_status="RESEARCH", note=""):
    """One manifest entry.

    A RAW artifact must either name the canonical table it feeds, or say WHY it feeds none.
    Silence is not an option, because "no destination recorded" and "never imported" look
    identical from outside — and the second is the defect that left four combo tables empty.
    """
    return {"repo": repo, "path": path, "owner": owner, "artifact_type": atype,
            "source_artifacts": source or [], "canonical_destination": dest,
            "no_canonical_destination_reason": no_dest_reason,
            "append_only": append_only, "calculation_version": CALC_VERSION,
            "lifecycle": lifecycle, "research_status": research_status, "note": note}


# ── v9: the raw evidence producer ────────────────────────────────────────────
# Everything here is OPERATIONAL first and evidence second: v9 is frozen and these files exist to
# run the tipping system. Pro's canonical tables are the research copy.
_V9 = [
    _e(V9, "output/predictions.csv", "v9/predict", RAW,
       dest="fixtures, model_snapshots, market_snapshots, feature_snapshots, signals",
       research_status="OPERATIONAL",
       note="CURRENT-STATE file, overwritten every predict run. Each Pro capture is one point "
            "on the model's path to kickoff; a missed capture is a horizon that never existed."),
    _e(V9, "output/bets.csv", "v9/predict", RAW, dest="signals", research_status="OPERATIONAL"),
    _e(V9, "output/bets_ledger.csv", "v9/update_results", RAW, dest="settlements",
       append_only=True, research_status="OPERATIONAL"),
    _e(V9, "output/clv_records.csv", "v9/predict", RAW, dest="clv", append_only=True,
       research_status="OPERATIONAL"),
    _e(V9, "output/standard_odds_history.csv", "v9/std_odds_capture", RAW,
       dest="market_snapshots", append_only=True, research_status="OPERATIONAL",
       note="FORWARD-ONLY. /odds is pre-match only, proven by probe across 2019-2025 at a cost "
            "of ~830 calls. A day not captured is gone permanently."),
    _e(V9, "output/standard_sidemarket_odds_history.csv", "v9/std_odds_capture", RAW,
       dest="market_snapshots", append_only=True, research_status="OPERATIONAL"),
    _e(V9, "output/newformat_odds_history.csv", "v9/nf_odds_capture", RAW,
       dest="market_snapshots", append_only=True, research_status="OPERATIONAL"),
    _e(V9, "output/newformat_odds_dense.csv", "v9/predict", RAW, dest="market_snapshots",
       append_only=True, research_status="OPERATIONAL"),
    _e(V9, "output/player_tips.csv", "v9/player_props", RAW, dest="player_props",
       research_status="PAPER",
       note="Props are PAPER ONLY, PERMANENTLY (root invariant 2)."),
    _e(V9, "output/player_prop_odds_history.csv", "v9/prop_odds_snapshot", RAW,
       dest="player_props", append_only=True, research_status="PAPER"),
    _e(V9, "output/inplay_snapshots.csv", "v9/live_scanner", RAW, dest="live_signals",
       research_status="OPERATIONAL",
       note="Match STATE (score, minute, SOT). NOT prices — v9 has no live odds source."),
    _e(V9, "output/live_games.csv", "v9/live_scanner", RAW, dest="live_signals",
       research_status="OPERATIONAL",
       note="fair_under_odds / fair_over_odds are MODEL fair odds, not bookmaker prices. "
            "Mistaking them for market data would fabricate a live market."),
    _e(V9, "output/api_usage_log.csv", "v9/af_usage_monitor", HEALTH,
       research_status="OPERATIONAL",
       note="The estate's only API-Football meter. Pro reads it rather than re-polling."),
    _e(V9, "output/sharp_tips.csv", "v9/sharp_tracker", RAW,
       no_dest_reason="Sharp-money tracking is a v9 operational feature; Pro's market research "
                      "reads prices, not v9's interpretation of them.",
       research_status="OPERATIONAL"),
    _e(V9, "player_history.parquet", "v9/player_history_extend", RAW, append_only=True,
       research_status="OPERATIONAL",
       no_dest_reason="Read in place, not imported. Pro's bet_builder reads it directly for team "
                      "card rates (src/pipelines/bet_builder._card_rates) because Pro holds "
                      "prop PROBABILITIES, not outcomes. Copying an 83 MB match-level log into "
                      "the canonical store would duplicate v9's own record for one consumer.",
       note="Match-level log. A player belongs to his LATEST CLUB, never to every club he has "
            "played for (root invariant 12)."),
]

# ── Pro: the canonical store ─────────────────────────────────────────────────
_PRO_TABLES = [
    ("fixtures", "the board v9 evaluated"),
    ("model_snapshots", "what v9 believed, when. Carries model_content_sha."),
    ("market_snapshots", "what the market showed at that moment"),
    ("feature_snapshots", "the inputs behind the opinion"),
    ("signals", "the decision, including NO_BET and AVOID"),
    ("settlements", "bet outcomes"),
    ("settlements_backfill", "MATCH outcomes, including fixtures never bet"),
    ("clv", "closing-line value, raw preserved and clean derived"),
    ("player_props", "paper only, permanently"),
    ("live_signals", "OUR in-play opinion"),
    ("live_odds_snapshots", "the MARKET's in-play price. Never merge with live_signals."),
    ("movement_observations", "v11 research, archived verbatim with provenance"),
    ("data_quality", "per-(table, flag) findings"),
    ("team_match_stats", "xG / possession / inside-box per fixture"),
    ("team_news", "event log; `known_at` still SOURCE_REQUIRED at field level"),
    ("combo_candidates", "one builder opinion at one moment"),
    ("combo_legs", "normalized legs, one row each"),
    ("combo_dependencies", "market-pair dependence, versioned"),
    ("combo_settlements", "graded combos"),
    ("combo_price_snapshots", "EMPTY BY DESIGN — no bookmaker builder price exists"),
]

_PRO = [
    _e(PRO, f"data/season_*/{t}/", "pro/season_store", CANONICAL, append_only=True, note=note)
    for t, note in _PRO_TABLES
] + [
    _e(PRO, "output/system_registry.json", "pro/registry", HEALTH,
       source=["data/season_*/*"],
       note="States what the store HOLDS. Counts are always measured, never inherited."),
    _e(PRO, "output/collect_health.json", "pro/pro_collect", HEALTH),
    _e(PRO, "output/combo_import_health.json", "pro/bet_builder", HEALTH,
       source=["output/bet_builder_candidates.csv", "output/bet_builder_settled.csv"],
       note="Rows seen / imported / skipped per combo table. Distinguishes 'the importer ran' "
            "from 'the importer stored anything'."),
    _e(PRO, "output/scheduler_health.json", "pro/monitoring.scheduler", HEALTH,
       note="OBSERVED cadence, measured from stored timestamps. Never inferred from a cron."),
    _e(PRO, "output/high_activity_coverage.json", "pro/monitoring.scheduler", HEALTH),
    _e(PRO, "output/weekly_audit.json", "pro/monitoring.weekly_audit", HEALTH),
    _e(PRO, "output/snapshot_coverage.json", "pro/monitoring", HEALTH),
    _e(PRO, "output/output_manifest.json", "pro/monitoring.manifest", HEALTH,
       note="This file."),
    _e(PRO, "output/bet_builder_candidates.csv", "pro/bet_builder", DERIVED,
       dest="combo_candidates, combo_legs", research_status="PAPER",
       note="CURRENT-STATE, rewritten every run. The canonical tables are its history."),
    _e(PRO, "output/bet_builder_settled.csv", "pro/bet_builder", DERIVED,
       dest="combo_settlements", research_status="PAPER"),
    _e(PRO, "output/combo_dependency_matrix.csv", "pro/combo.dependency", DERIVED,
       dest="combo_dependencies", research_status="RESEARCH"),
    _e(PRO, "output/player_combo_dependency.csv", "pro/combo.player_dependency", DERIVED,
       dest="combo_dependencies", research_status="RESEARCH"),
    _e(PRO, "output/combo_dependency_stability.csv", "pro/combo.dependency", DERIVED,
       research_status="RESEARCH"),
    _e(PRO, "output/clv_enriched.csv", "pro/market.clv_schema", DERIVED),
    # Pro's, not v9's — train_1x2.py lives in src/pipelines here. Filed under v9 in the first
    # draft of this manifest and immediately reported missing, which is the manifest doing its
    # job on its own author.
    _e(PRO, "output/model_1x2_eval.csv", "pro/train_1x2", DERIVED,
       research_status="EARLY_RESEARCH",
       note="Scheduled in NO workflow — refreshes only when a human runs it. Current result: "
            "USA MLS and China Super League both beats_baseline = False."),
    _e(PRO, "output/model_1x2.json", "pro/train_1x2", DERIVED,
       research_status="EARLY_RESEARCH"),
    _e(PRO, "docs/OUTPUT_ARCHITECTURE_HARDENING_REPORT.md", "pro/docs", REPORT),
    _e(PRO, "docs/V9_FROZEN_PROSPECTIVE_VALIDATION_PLAN.md", "pro/docs", REPORT),
    _e(PRO, "docs/PROMPT_1_5_HARDENING_COMPLETION_REPORT.md", "pro/docs", REPORT),
    _e(PRO, "docs/WORKFLOW_MAP.md", "pro/docs", REPORT),
    _e(PRO, "docs/ARTIFACT_ROLES.md", "pro/docs", REPORT),
]

# ── v11: the market research lab ─────────────────────────────────────────────
_V11 = [
    _e(V11, "output/v11_shadow_snapshots.csv", "v11/shadow", RAW, append_only=True,
       no_dest_reason="v11-internal. Pro imports only v11_market_movement_detail.csv "
                      "(src/importers/v11_research.py). These raw snapshots stay in v11, which "
                      "owns market microstructure by the ownership rule — copying them into Pro "
                      "would create a second definition of the same observations.",
       note="v11's own market observations, the input to every movement result below."),
    _e(V11, "output/v11_shadow_log.csv", "v11/shadow", DERIVED),
    _e(V11, "output/v11_graded.csv", "v11/grade", DERIVED),
    _e(V11, "output/v11_scoreboard.csv", "v11/grade", DERIVED),
    _e(V11, "output/v11_residual.csv", "v11/residual", DERIVED),
    _e(V11, "output/v11_market_movement_detail.csv", "v11/market_movement", DERIVED,
       dest="movement_observations", append_only=True),
    _e(V11, "output/v11_movement_summary.csv", "v11/market_movement", DERIVED),
    _e(V11, "output/v11_movement_by_residual.csv", "v11/market_movement", DERIVED),
    _e(V11, "output/v11_movement_by_time.csv", "v11/market_movement", DERIVED),
    _e(V11, "output/v11_movement_by_league.csv", "v11/market_movement", DERIVED),
    _e(V11, "output/v11_movement_by_model.csv", "v11/market_movement", DERIVED),
    _e(V11, "output/v11_market_microstructure.csv", "v11/microstructure", DERIVED),
    _e(V11, "output/v11_microstructure_segments.csv", "v11/microstructure", DERIVED),
    _e(V11, "output/v11_microstructure_coverage.csv", "v11/microstructure", DERIVED),
    _e(V11, "output/v11_momentum_control.csv", "v11/momentum_control", DERIVED,
       source=["output/v11_shadow_snapshots.csv"],
       note="The controlled version of the toward-Wowza headline. First run: the residual "
            "coefficient does not survive momentum, and a placebo reproduces most of it."),
    _e(V11, "output/v11_momentum_roles.csv", "v11/momentum_control", DERIVED,
       note="WOWZA_LEADS / AGREES / OPPOSES. NOT a strategy table — the opposing bucket's high "
            "toward-rate is mean-reversion arithmetic."),
    _e(V11, "output/v11_research_health.json", "v11/research_state", HEALTH),
    _e(V11, "output/research_state.json", "v11/research_state", HEALTH),
    _e(V11, "output/v11_evidence.json", "v11/fit_evidence", DERIVED),
]

ENTRIES = _V9 + _PRO + _V11


def _repo_root(repo: str) -> Path | None:
    """Where each repo is checked out, when it is. Pro is where we run; v9 may be beside us or
    at V9_LOCAL; v11 is only present on a workstation."""
    base = cfg.BASE_DIR
    if repo == PRO:
        return base
    if repo == V9:
        for c in (os.getenv("V9_LOCAL", ""), str(base.parent / "v9"), str(base.parent / "_v9")):
            if c and Path(c).exists():
                return Path(c)
        return None
    if repo == V11:
        for c in (str(base.parent / "wowza-v11"), str(base.parent / "_v11")):
            if Path(c).exists():
                return Path(c)
    return None


def build() -> dict:
    entries = []
    for e in ENTRIES:
        row = dict(e)
        root = _repo_root(e["repo"])
        if root is None:
            # Not checked out here, so presence is UNKNOWN rather than False. Reporting a missing
            # repo as a missing artifact would flag ~35 healthy files every time Pro runs alone.
            row["present"] = None
            row["repo_checked_out"] = False
        else:
            row["repo_checked_out"] = True
            p = e["path"]
            row["present"] = bool(list(root.glob(p))) if ("*" in p) else (root / p).exists()
        entries.append(row)

    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e["artifact_type"]] = by_type.get(e["artifact_type"], 0) + 1
    checked = [e for e in entries if e["repo_checked_out"]]
    missing = sorted(e["path"] for e in checked if e["present"] is False)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "calculation_version": CALC_VERSION,
        "n_entries": len(entries),
        "by_artifact_type": by_type,
        "by_repo": {r: sum(1 for e in entries if e["repo"] == r) for r in (V9, PRO, V11)},
        "repos_checked_out": sorted({e["repo"] for e in checked}),
        "n_checked": len(checked),
        "n_missing": len(missing),
        "missing": missing,
        "entries": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    m = build()
    print(f"[manifest] {m['n_entries']} entries · "
          + " · ".join(f"{k} {v}" for k, v in sorted(m["by_artifact_type"].items())))
    print(f"[manifest] repos checked out: {', '.join(m['repos_checked_out']) or 'none'} "
          f"({m['n_checked']} entries verifiable)")
    if m["missing"]:
        print(f"[manifest] MISSING ({m['n_missing']}):")
        for p in m["missing"]:
            print(f"    {p}")
    else:
        print("[manifest] every verifiable artifact is present")
    if a.write:
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = cfg.OUTPUT_DIR / "output_manifest.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(m, indent=2, sort_keys=True, default=str), encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8"))
        os.replace(tmp, p)
        print(f"[manifest] wrote {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
