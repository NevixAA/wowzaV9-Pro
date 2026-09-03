"""
Intended schemas and lifecycle status for the canonical tables.
==============================================================

`season_store.REQUIRED` declares the KEY columns a table must carry to be interpretable. It
deliberately says nothing about the rest, because importers may add whatever they have. That is
the right rule for a table being written today, and useless for a table that does not exist yet:
`team_news` and `team_match_stats` are both empty, and "empty" currently reads identically to
"broken".

This module supplies the missing half — the full intended field list, per field whether the data
is actually obtainable, and a lifecycle status for the table as a whole (brief sections 10, 11,
27).

WHY A STATUS AND NOT JUST A SCHEMA

`registry.refresh` reports "N/M tables populated" and names the empty ones. With two permanently
planned tables in the list, that line will read as a two-table outage every run, forever — and a
health signal that is always slightly red is a health signal nobody reads. `PLANNED_OPTIONAL`
lets an empty table be *expected* to be empty, so a genuinely unexpected empty table stands out.

WHAT THIS DOES NOT DO

It does not populate anything. Section 10 is explicit: keep the table empty and mark it
PLANNED / SOURCE_REQUIRED rather than inventing observations. A synthetic row in a canonical
table is worse than no row, because every downstream measurement then quietly includes it.

THE FIELD THAT MATTERS MOST

`known_at`. A team-news row without it is just a lineup, and the entire research question is
timing: information published at T-60m cannot be used in a T-12h prediction. `event_ts` (when the
thing happened) and `known_at` (when WE could first have seen it) are different, and only the
second is safe to build a feature on. `first_seen_ts` is already REQUIRED in the store for this
reason; `known_at` is its more precise sibling, sourced from the publisher rather than from our
own polling.
"""
from __future__ import annotations

# ── Lifecycle statuses ───────────────────────────────────────────────────────
ACTIVE = "ACTIVE"                      # written today, expected non-empty
PLANNED_OPTIONAL = "PLANNED_OPTIONAL"  # schema agreed, collector not built, empty is CORRECT
SOURCE_REQUIRED = "SOURCE_REQUIRED"    # blocked on a data source we do not have
DEPRECATED = "DEPRECATED"

# ── Per-field availability ───────────────────────────────────────────────────
AVAILABLE = "AVAILABLE"          # obtainable now from a source we already call
OBTAINABLE = "OBTAINABLE"        # a source exists and is reachable; collector not written
UNAVAILABLE = "UNAVAILABLE"      # no source we have access to provides it
DERIVED = "DERIVED"              # computed from other fields, never stored raw

# API-Football's /fixtures/statistics persists historically (unlike /odds, which is pre-match
# only and unbackfillable) — that is what makes team_match_stats OBTAINABLE rather than
# forward-only. Established by probe, recorded in v9's CLAUDE.md.
_AF_STATS = "api-football /fixtures/statistics"


TEAM_NEWS: dict[str, dict] = {
    # ACTIVE since 2026-09-02: 48 rows over 3 runs, 2026-08-30 to 2026-09-01, once the API key
    # was added. The collector produces rows, so the table is in use and an empty one is a fault.
    #
    # The original objection still stands and is NOT resolved by the table having rows: neither
    # /fixtures/lineups nor /injuries carries a PUBLICATION time, so `known_at` remains
    # SOURCE_REQUIRED at the FIELD level and `first_seen_ts` is only our own polling resolution.
    # That is why the field list below is unchanged. A table can be active while the one field
    # that makes it usable for leakage-safe research is still missing — and marking the field,
    # not the table, is what keeps that distinction visible.
    "_status": ACTIVE,
    "_grain": "one row per (fixture, team, event) — an event log, NOT a fixture summary",
    "_why_empty": "Not empty — 48 rows over 3 runs as of 2026-09-02. What remains missing is the "
                  "publication TIMESTAMP (`known_at`), without which these rows must not be used "
                  "for out-of-sample timing claims.",
    "_blocked_on": "nothing for the table; `known_at` still needs a source that publishes an "
                   "event WITH its publication time",
    "fields": {
        "event_id":         (AVAILABLE, "DERIVED hash of (fixture_key, team, event_type, event_ts)"),
        "fixture_key":      (AVAILABLE, "joins the canonical fixtures table"),
        "team":             (AVAILABLE, "resolved via src/team_names — league-scoped"),
        "player_id":        (OBTAINABLE, "api-football player id; null for team-level events"),
        "player_name":      (OBTAINABLE, "for readability only, never a join key"),
        "event_type":       (AVAILABLE, "LINEUP_CONFIRMED | PLAYER_OUT | PLAYER_IN | "
                                        "GOALKEEPER_CHANGE | KEY_ATTACKER_OUT | "
                                        "KEY_DEFENDER_OUT | SUSPENSION | MANAGER_CHANGE | "
                                        "WEATHER_UPDATE | REST_ADVANTAGE | TRAVEL | "
                                        "FIXTURE_CONGESTION"),
        "event_ts":         (OBTAINABLE, "when the thing HAPPENED"),
        "known_at":         (SOURCE_REQUIRED, "when it became PUBLIC. The leakage-safety field: "
                                              "a feature may only use rows where "
                                              "known_at <= prediction time. Distinct from "
                                              "event_ts and from ingested_at."),
        "first_seen_ts":    (AVAILABLE, "when WE first saw it. A safe lower bound for known_at "
                                        "when the publisher gives no timestamp, and it is the "
                                        "field already REQUIRED by the store."),
        "source":           (AVAILABLE, "provider identifier"),
        "source_quality":   (AVAILABLE, "OFFICIAL | PROVIDER | AGGREGATOR | UNVERIFIED"),
        "expected_impact":  (UNAVAILABLE, "signed effect on the modelled market. Requires a "
                                          "fitted impact model; must NOT be hand-assigned."),
        "raw_value":        (AVAILABLE, "provider payload as given"),
        "normalized_value": (DERIVED, "raw_value mapped to our vocabulary"),
        "ingested_at":      (AVAILABLE, "our write time — for provenance, never for features"),
        "source_sha":       (AVAILABLE, "hash of the payload, so a silent revision is visible"),
        "quality_flags":    (AVAILABLE, "pipe-joined src/quality.py flags. Present from row one: "
                                        "a table added without it lands as NOT_CLASSIFIED."),
    },
}


TEAM_MATCH_STATS: dict[str, dict] = {
    # ACTIVE, not PLANNED_OPTIONAL. The brief lists this table as empty and it is NOT: the store
    # holds 23,604 rows, written by src/pipelines/team_stats.py. Declaring it planned-empty would
    # have suppressed alarms on a table that is genuinely in use — the opposite of what section 27
    # is for. Checked by running registry.refresh rather than by trusting the description.
    "_status": ACTIVE,
    # Fixture grain with home_/away_ pairs, matching how feature_engineering already consumes it
    # (_team_recent reads a home_xg / away_xg pair). A per-team grain would be more normalised
    # and would force every consumer to pivot.
    "_grain": "one row per FIXTURE, with home_/away_ column pairs",
    # CORRECTED 2026-08-30. The previous note here read "Not empty — 23,604 rows as of
    # 2026-08-27" and cited a registry run as proof. That measurement was taken on a LAPTOP.
    # In the repository the table has ZERO committed partitions, while 88 parquet files sit
    # untracked in the local working tree, every one of them written by a `run=local...` id.
    # Verified by counting run tokens in `git ls-files data/season_2026_27`: every other
    # canonical table is CI-dominated (fixtures 127 ci / 2 local, market_snapshots 137/3);
    # team_match_stats is 0 ci / 0 tracked.
    #
    # The cause was that `pro_collect.yml`'s team-stats step needs APIFOOTBALL_KEY, team_stats.py
    # RAISES without one, and the step is `continue-on-error: true` — so every daily sweep since
    # 2026-08-26 skipped it and stayed green. The secret was added to the Pro repo on 2026-08-30;
    # the table stays ACTIVE and the next daily sweep is what confirms it.
    #
    # The lesson is the one this file exists for: a lifecycle status must be set from what the
    # SHARED store holds, never from what a laptop holds.
    "_why_empty": "0 rows in the committed store as of 2026-08-30 (88 local-only partitions "
                  "exist on one laptop). Stays ACTIVE because the collector is written and the "
                  "credential it needs was added on 2026-08-30 — an empty table on the NEXT "
                  "daily sweep is a real fault and must alarm. Also PARTIAL by field: xg reaches "
                  "~88% coverage in bet leagues, and six intended fields have no source at all.",
    "_blocked_on": "nothing — awaiting the first CI run that has APIFOOTBALL_KEY available",
    "fields": {
        "fixture_key":              (AVAILABLE, "canonical join key"),
        "league":                   (AVAILABLE, ""),
        "match_date":               (AVAILABLE, ""),
        "home_team":                (AVAILABLE, ""),
        "away_team":                (AVAILABLE, ""),
        "home_xg / away_xg":        (OBTAINABLE, _AF_STATS + " — 88.3% coverage measured in bet "
                                                  "leagues this season"),
        "home_np_xg / away_np_xg":  (UNAVAILABLE, "non-penalty xG is not separated by the "
                                                  "provider; would need penalty xG subtracted "
                                                  "from event data we do not collect"),
        "home_xga / away_xga":      (DERIVED, "the opponent's xg on the same fixture row"),
        "home_shots / away_shots":  (OBTAINABLE, _AF_STATS),
        "home_sot / away_sot":      (OBTAINABLE, _AF_STATS),
        "home_shots_box / away_shots_box": (UNAVAILABLE, "shot location is not in the statistics "
                                                         "payload"),
        "home_xg_per_shot / away_xg_per_shot": (DERIVED, "xg / shots; null when shots = 0 rather "
                                                         "than 0, which would be a different "
                                                         "claim"),
        "home_big_chances / away_big_chances": (UNAVAILABLE, "Sofascore-style metric; not in the "
                                                             "api-football payload"),
        "home_set_piece_xg / away_set_piece_xg": (UNAVAILABLE, "needs event-level data"),
        "home_possession / away_possession": (OBTAINABLE, _AF_STATS),
        "home_red_cards / away_red_cards":   (OBTAINABLE, _AF_STATS),
        "home_first_half_xg / away_first_half_xg": (UNAVAILABLE, "statistics are full-match "
                                                                 "totals; no half split"),
        "home_score_state_adj_xg / away_score_state_adj_xg": (UNAVAILABLE, "needs minute-level "
                                                                           "xg and scoreline"),
        "data_provider":            (AVAILABLE, "api-football"),
        "observed_at":              (AVAILABLE, "when the provider considered the match final"),
        "ingested_at":              (AVAILABLE, "our write time"),
        "quality_flags":            (AVAILABLE, "includes XG_UNAVAILABLE, already defined in "
                                                "src/quality.py"),
    },
}


LIVE_ODDS_SNAPSHOTS: dict[str, dict] = {
    # ACTIVE since 2026-09-02. The previous note said "flip to ACTIVE once pro_live_odds.yml has
    # completed a match-day window" — it has, repeatedly: 10,151 rows across 10 runs spanning
    # 2026-08-30 to 2026-09-02, once APIFOOTBALL_KEY was added to this repository.
    #
    # ACTIVE rather than an opportunistic status, deliberately. The source is a scheduled hourly
    # sweep against a provider endpoint that answers reliably, so an empty day is a FAULT and
    # should alarm. What is genuinely opportunistic is the CONTENT — no live fixtures means no
    # rows — and that is a per-run condition the scheduler health reports, not a property of the
    # table's lifecycle. Confusing "nothing was in play" with "the collector is optional" is how
    # a broken live collector would go unnoticed for a month.
    "_status": ACTIVE,
    "_grain": "one row per (fixture, snapshot, market, selection) — many lines quoted at once",
    "_why_empty": "Not empty — 10,151 rows over 10 runs as of 2026-09-02. Individual runs may "
                  "legitimately store nothing when no fixture is in play; that is a run-level "
                  "condition, not a table-level one.",
    "_blocked_on": "nothing",
    "fields": {
        "fixture_id": (AVAILABLE, "API-Football fixture id, as /odds/live returns it"),
        "snapshot_ts": (AVAILABLE, "our fetch time"),
        "odds_updated_at": (AVAILABLE, "the MARKET's timestamp, from the API's `update` field"),
        "odds_age_seconds": (DERIVED, "fetch minus market timestamp — section 140's staleness "
                                      "test, real rather than inferred"),
        "match_minute": (AVAILABLE, ""), "match_seconds": (AVAILABLE, "e.g. '71:33'"),
        "home_score / away_score": (AVAILABLE, "from teams.home.goals, NOT a top-level block"),
        "market_family": (AVAILABLE, "TOTALS_LINE | BTTS | AH | AH_3WAY | HOME_GOALS | AWAY_GOALS"),
        "line": (AVAILABLE, "from the `handicap` field; the DYNAMIC live line, 1.25-6.25 seen"),
        "is_main_line": (AVAILABLE, "the book's headline line among several quoted"),
        "suspended": (AVAILABLE, "kept, not dropped — a suspension is itself a reaction"),
        "home_team / away_team": (UNAVAILABLE, "names are absent from /odds/live; ids only"),
        "quality_flags": (DERIVED, "STALE_LIVE_ODDS | SUSPENDED | NO_ODDS_TIMESTAMP | ..."),
    },
}


# ── Bet Builder evidence (Prompt 01 section 4) ───────────────────────────────
# `_BUILDER_PRICE` is stated once and referenced from three tables, because it is the single
# fact that governs how all builder evidence may be read: WE HAVE NO BOOKMAKER BUILDER PRICE.
_BUILDER_PRICE = ("no bookmaker same-game-builder price is collected in any repo; a book "
                  "applies its own correlation adjustment, so multiplying singles does NOT "
                  "reconstruct it")

COMBO_CANDIDATES: dict[str, dict] = {
    "_status": ACTIVE,
    "_grain": "one row per (combo_id, snapshot_ts) — the SAME combo re-observed as kickoff nears",
    "_why_empty": "Not empty from the first scheduled run. Backfilled once from the 476 rows in "
                  "bet_builder_candidates.csv, which had no history because that file is "
                  "rewritten in place.",
    "_blocked_on": "nothing",
    "fields": {
        "combo_id":        (AVAILABLE, "stable hash of (fixture_key, sorted leg selections). "
                                       "Stable across runs BY DESIGN — that is what makes a "
                                       "re-observation joinable to the first one"),
        "fixture_key":     (AVAILABLE, "SAME_MATCH only; null for CROSS_MATCH"),
        "snapshot_ts":     (AVAILABLE, "when this opinion was formed"),
        "kickoff_ts":      (AVAILABLE, ""),
        "minutes_to_kickoff": (DERIVED, "kickoff_ts - snapshot_ts. The horizon axis for every "
                                        "builder question"),
        "league":          (AVAILABLE, ""),
        "combo_type":      (AVAILABLE, "SAME_MATCH | CROSS_MATCH"),
        "n_legs":          (AVAILABLE, ""),
        "joint_probability": (AVAILABLE, "dependency-aware. NOT p1*p2*p3 — section 3 forbids it"),
        "independence_probability": (AVAILABLE, "the naive product, kept as the CONTROL: the "
                                                "difference is the entire dependency claim"),
        "dependency_ratio": (DERIVED, "joint / independence"),
        "joint_probability_method": (AVAILABLE, "which estimator produced it, e.g. "
                                                "DIXON_COLES | MEASURED_PAIR | FRECHET_BOUNDED"),
        "fair_odds":       (DERIVED, "1 / joint_probability"),
        "independence_fair_odds": (DERIVED, "1 / independence_probability"),
        "offered_odds":    (UNAVAILABLE, _BUILDER_PRICE + " — real for CROSS_MATCH only"),
        "implied_probability": (UNAVAILABLE, "requires offered_odds"),
        "market_probability": (UNAVAILABLE, "requires a de-viggable two-sided builder market"),
        "model_edge":      (UNAVAILABLE, "NULL, not 0.0, wherever offered_odds is null. A zero "
                                         "would be read as 'measured no edge'"),
        "quality_status":  (AVAILABLE, "RAW | CLEAN | STRICT_CLEAN, from src/quality.py"),
        "research_status": (AVAILABLE, "CANDIDATE | RESEARCH | PAPER | REJECTED | AVOID | "
                                       "BLOCKED. Rejections are STORED — a file of only the "
                                       "attractive combos cannot answer whether the filter works"),
        "calculation_version": (AVAILABLE, ""),
        "source_run_id":   (AVAILABLE, ""),
    },
}

COMBO_LEGS: dict[str, dict] = {
    "_status": ACTIVE,
    "_grain": "one row per (combo_id, leg_index), 1-based",
    "_why_empty": "Not empty. Replaces the leg1_/leg2_/leg3_/leg4_ column blocks, which cannot "
                  "express a 5-leg combo and cannot be grouped by market without unpivoting.",
    "_blocked_on": "nothing",
    "fields": {
        "combo_id":        (AVAILABLE, ""), "leg_index": (AVAILABLE, "1-based"),
        "fixture_key":     (AVAILABLE, "per LEG — differs across legs in a CROSS_MATCH combo"),
        "market_family":   (AVAILABLE, "GOALS | BTTS | CARDS | PLAYER_SHOTS | PLAYER_GOALS | ..."),
        "market":          (AVAILABLE, ""), "line": (AVAILABLE, ""),
        "selection":       (AVAILABLE, "OVER | UNDER | YES | NO | ..."),
        "player_id":       (OBTAINABLE, "player legs only"),
        "player_name":     (AVAILABLE, "readability only, never a join key (invariant 12)"),
        "model_probability": (AVAILABLE, ""),
        "market_probability": (AVAILABLE, "de-vigged where a two-sided price exists"),
        "odds":            (AVAILABLE, "the REAL single price. Present for cross-match legs and "
                                       "for any same-match leg that is separately quoted"),
        "fair_odds":       (DERIVED, "1 / model_probability"),
        "edge":            (DERIVED, "model_probability - market_probability; NULL without odds"),
        "model_type":      (AVAILABLE, "standard | newformat | props — never mixed (invariant 1)"),
        "model_version":   (AVAILABLE, ""),
        "snapshot_ts":     (AVAILABLE, ""),
        "source_snapshot_id": (AVAILABLE, "the market_snapshots/player_props row behind the price"),
        "quality_flags":   (AVAILABLE, ""),
    },
}

COMBO_DEPENDENCIES: dict[str, dict] = {
    "_status": ACTIVE,
    "_grain": "one row per (market_a, market_b, segment, sample window, calc_version)",
    "_why_empty": "Not empty — backfilled from combo_dependency_matrix.csv (1,400+ pairs) and "
                  "player_combo_dependency.csv, both of which are currently rewritten in place.",
    "_blocked_on": "nothing",
    "fields": {
        "market_a": (AVAILABLE, ""), "market_b": (AVAILABLE, ""),
        "league": (AVAILABLE, ""), "model_type": (AVAILABLE, ""),
        "segment": (AVAILABLE, "which slice the estimate was measured on"),
        "window_start": (AVAILABLE, ""), "window_end": (AVAILABLE, ""),
        "n": (AVAILABLE, "sample size — the gate on whether the estimate may be used at all"),
        "p_a": (AVAILABLE, ""), "p_b": (AVAILABLE, ""),
        "observed_joint": (AVAILABLE, ""), "independence_joint": (DERIVED, "p_a * p_b"),
        "dependency_ratio": (DERIVED, ""), "excess_pp": (DERIVED, ""),
        "phi": (AVAILABLE, "correlation of the two binary outcomes"),
        "joint_ci_lo": (AVAILABLE, ""), "joint_ci_hi": (AVAILABLE, ""),
        "frechet_lo": (DERIVED, "max(0, p_a + p_b - 1)"),
        "frechet_hi": (DERIVED, "min(p_a, p_b)"),
        "frechet_ok": (DERIVED, "a joint outside these bounds is arithmetically impossible and "
                                "means the estimator is wrong, not that the market is odd"),
        "independence_within_ci": (DERIVED, "if TRUE the pair shows no measurable dependence"),
        "sample_status": (AVAILABLE, "OK | THIN | TOO_SMALL"),
        "calculation_version": (AVAILABLE, "VERSIONED, never overwritten: a combo priced under "
                                           "v1.0.0 must stay auditable after v1.1.0 lands"),
        "generated_at": (AVAILABLE, ""),
    },
}

COMBO_SETTLEMENTS: dict[str, dict] = {
    "_status": ACTIVE,
    "_grain": "one row per settled combo_id",
    "_why_empty": "Not empty — backfilled from the 8,394 rows of bet_builder_settled.csv.",
    "_blocked_on": "nothing",
    "fields": {
        "combo_id": (AVAILABLE, ""), "fixture_key": (AVAILABLE, ""),
        "settled_at": (AVAILABLE, ""), "final_score": (AVAILABLE, ""),
        "leg_results": (AVAILABLE, "per-leg outcome, aligned to combo_legs.leg_index"),
        "n_legs_won": (DERIVED, ""),
        "result": (AVAILABLE, "WIN | LOSS | VOID | PARTIAL_VOID | UNKNOWN. UNKNOWN is a real "
                              "state and is kept: an ungradeable combo is not a loss"),
        "offered_odds": (UNAVAILABLE, _BUILDER_PRICE),
        "stake": (UNAVAILABLE, "Pro does not stake this season"),
        "profit": (UNAVAILABLE, "requires offered_odds and a stake; NULL, never 0.0"),
        "settlement_quality": (AVAILABLE, "GRADED | PARTIAL | UNGRADEABLE"),
        "quality_flags": (AVAILABLE, ""),
    },
}

COMBO_PRICE_SNAPSHOTS: dict[str, dict] = {
    # SOURCE_REQUIRED, not PLANNED_OPTIONAL. PLANNED means "collector not built yet" and would
    # imply someone should go build it; the truth is that the DATA DOES NOT EXIST TO COLLECT for
    # the same-match case, and no amount of engineering here changes that. Section 6 draws
    # exactly this distinction and it is the honest label.
    "_status": SOURCE_REQUIRED,
    "_grain": "one row per (combo_id, snapshot_ts, price_basis)",
    "_why_empty": "For SAME_MATCH combos: " + _BUILDER_PRICE + ". CROSS_MATCH multiples are "
                  "fillable today — their legs are separately executable, so the product of real "
                  "single prices is a genuine price — but the builder currently emits same-match "
                  "combos only, so there is nothing yet to observe.",
    "_blocked_on": "a bookmaker builder-price feed (same-match); cross-match combo generation "
                   "(component product)",
    "fields": {
        "combo_id": (AVAILABLE, ""), "snapshot_ts": (AVAILABLE, ""),
        "kickoff_ts": (AVAILABLE, ""),
        "horizon_bucket": (DERIVED, "T-6h | T-3h | T-1h | T-30m | T-10m | OTHER"),
        "price_basis": (AVAILABLE, "REAL_BUILDER | REAL_COMPONENT_PRODUCT | MODEL_FAIR_ONLY. "
                                   "REQUIRED and never blank. This column is what prevents a "
                                   "reconstructed price being read as executable CLV (section 14)"),
        "price": (AVAILABLE, "meaning depends entirely on price_basis"),
        "bookmaker": (UNAVAILABLE, "same-match; real for a component product"),
        "executable": (AVAILABLE, "TRUE only for REAL_BUILDER and REAL_COMPONENT_PRODUCT"),
        "quality_flags": (AVAILABLE, ""),
    },
}


TABLES: dict[str, dict] = {
    "live_odds_snapshots": LIVE_ODDS_SNAPSHOTS,
    "team_news": TEAM_NEWS,
    "team_match_stats": TEAM_MATCH_STATS,
    "combo_candidates": COMBO_CANDIDATES,
    "combo_legs": COMBO_LEGS,
    "combo_dependencies": COMBO_DEPENDENCIES,
    "combo_settlements": COMBO_SETTLEMENTS,
    "combo_price_snapshots": COMBO_PRICE_SNAPSHOTS,
}

# Tables whose emptiness is EXPECTED. Consulted by registry/data_quality so an intentionally
# future table does not read as an outage, and so a table that drops out of this set starts
# being alarmed on.
PLANNED_TABLES: tuple[str, ...] = tuple(
    name for name, spec in TABLES.items() if spec["_status"] == PLANNED_OPTIONAL)


def status(table: str) -> str:
    """Lifecycle status. Anything not declared here is ACTIVE — the safe default, because an
    undeclared table that turns up empty SHOULD be alarming."""
    return TABLES.get(table, {}).get("_status", ACTIVE)


def is_planned(table: str) -> bool:
    return status(table) == PLANNED_OPTIONAL


# Statuses under which an empty table is the CORRECT state. SOURCE_REQUIRED belongs here and was
# missing: `combo_price_snapshots` is empty because no bookmaker builder price exists to collect,
# which is a settled fact about the world, not an outage. Without this it would have joined
# `tables_unexpected_empty` on every run — re-creating the always-slightly-red signal that
# PLANNED_OPTIONAL was introduced to remove.
#
# The distinction is worth keeping sharp:
#   PLANNED_OPTIONAL  the data exists; we have not written the collector yet  -> someone can act
#   SOURCE_REQUIRED   the data does not exist to collect                      -> nobody can act
_EMPTY_IS_CORRECT = (PLANNED_OPTIONAL, SOURCE_REQUIRED, DEPRECATED)


def is_expected_empty(table: str) -> bool:
    """True when zero rows is the right answer for this table, for any reason."""
    return status(table) in _EMPTY_IS_CORRECT


def field_summary(table: str) -> dict[str, int]:
    """How much of the intended schema is actually obtainable — the honest answer to
    'why not just build it'."""
    spec = TABLES.get(table)
    if not spec:
        return {}
    out: dict[str, int] = {}
    for _, (avail, _note) in spec["fields"].items():
        out[avail] = out.get(avail, 0) + 1
    return out


def describe(table: str) -> str:
    spec = TABLES.get(table)
    if not spec:
        return f"{table}: not declared (implicitly ACTIVE)"
    counts = field_summary(table)
    parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    return (f"{table}: {spec['_status']} · {len(spec['fields'])} fields ({parts})\n"
            f"  grain: {spec['_grain']}\n"
            f"  empty because: {spec['_why_empty']}\n"
            f"  blocked on: {spec['_blocked_on']}")
