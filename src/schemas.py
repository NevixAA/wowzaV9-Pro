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
    "_status": PLANNED_OPTIONAL,
    "_grain": "one row per (fixture, team, event) — an event log, NOT a fixture summary",
    "_why_empty": "No reliable timestamped team-news source is wired. Lineups are obtainable "
                  "~1h before kickoff; injury and suspension news with a trustworthy "
                  "publication time is not, and that timestamp is the whole point.",
    "_blocked_on": "a source that publishes an event WITH its publication time",
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
    "_why_empty": "Not empty — 23,604 rows as of 2026-08-27. What is PARTIAL is the field list "
                  "below: xg reaches ~88% coverage in bet leagues this season, and six intended "
                  "fields have no available source at all.",
    "_blocked_on": "nothing for the table; six individual fields are UNAVAILABLE (see below)",
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
    # PLANNED_OPTIONAL only until the first scheduled run lands. The collector is written and
    # verified against the live API (216 rows, 5 fixtures, median odds age 25.6s), but nothing
    # has been persisted yet because local writes to the canonical store are refused by design.
    "_status": PLANNED_OPTIONAL,
    "_grain": "one row per (fixture, snapshot, market, selection) — many lines quoted at once",
    "_why_empty": "Collector verified against the live API but not yet run on a schedule. Flip "
                  "to ACTIVE once pro_live_odds.yml has completed a match-day window.",
    "_blocked_on": "nothing — the workflow needs to run",
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


TABLES: dict[str, dict] = {
    "live_odds_snapshots": LIVE_ODDS_SNAPSHOTS,
    "team_news": TEAM_NEWS,
    "team_match_stats": TEAM_MATCH_STATS,
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
