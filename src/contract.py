"""
The cross-repo health contract: what Pro and v11 REQUIRE from v9, declared in one place.
======================================================================================
WHY. Pro and v11 both read v9's public outputs, and v9 is FROZEN — so the dependency is
one-directional and completely undocumented. Every consumer discovered its requirements by
crashing or, worse, by silently producing nothing:

  * the weekly audit looked for `player_history.parquet` under `output/` when it lives at the
    repo root, and reported "not present" — masking the stalled-collector bug it exists to catch
  * v11 grades from `bets_ledger.csv` and got 28% coverage, because nothing recorded that the
    ledger holds only TIPPED fixtures
  * `from_clv` builds a fixture key from `league` and `match_date` that `clv_records.csv` does
    not have, producing keys that match nothing (measured overlap: 0 of 57)

None of those are v9 bugs. They are undeclared expectations, and an undeclared expectation fails
silently by construction: the file exists, the read succeeds, the result is empty or wrong.

WHAT A CONTRACT ENTRY DECLARES:

    path            repo-relative path in v9, INCLUDING whether it is under output/ or at root
    consumers       which repos break if it stops
    required_cols   columns a consumer indexes by name. A missing one is a FAIL, not a warning:
                    pandas returns NaN for an absent column and the pipeline carries on
    max_age_h       staleness limit, or None where the artifact is legitimately static
    grain           what one row IS — the field that prevents the bets_ledger mistake
    caveat          the thing a new consumer would otherwise have to learn by being wrong

This module is DECLARATION ONLY. It reads nothing and enforces nothing; `weekly_audit`'s
`audit_contract` does the checking, so the statement of intent and the verification of it stay
separable and the declaration can be reviewed on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Artifact:
    path: str
    consumers: tuple[str, ...]
    required_cols: tuple[str, ...]
    max_age_h: float | None
    grain: str
    caveat: str = ""
    at_repo_root: bool = False
    parquet: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


CONTRACT: tuple[Artifact, ...] = (
    Artifact(
        path="output/predictions.csv",
        consumers=("pro", "v11"),
        # home_team/away_team, NOT `match` — v11 composes "Home vs Away" itself. My first
        # declaration asserted `match` and the audit FAILED on it, which is the contract check
        # working: an undeclared-vs-actual mismatch is exactly what it exists to surface.
        required_cols=("league", "home_team", "away_team", "p_over25", "odds_over25",
                       "odds_under25", "generated_at"),
        max_age_h=6.0,
        grain="one row per fixture on the CURRENT board — overwritten every 5 minutes",
        caveat="PRE-MATCH ONLY. predict skips kicked-off fixtures, so a fixture DISAPPEARS the "
               "moment it goes live. Never use presence here to decide which live fixtures to "
               "watch: that filter silenced the live scanner from 2026-08-09.",
    ),
    Artifact(
        path="output/bets_ledger.csv",
        consumers=("pro", "v11"),
        required_cols=("league", "home_team", "away_team", "match_date", "clv_pct"),
        max_age_h=48.0,
        grain="one row per TIPPED bet",
        caveat="HOLDS ONLY FIXTURES V9 TIPPED. Grading from it conditions the sample on v9 "
               "having disagreed with the market — 94/336 (28%) coverage, League Two 0/24. "
               "clv_pct here is a PERCENT, unlike clv_records.csv which stores a FRACTION.",
    ),
    Artifact(
        path="output/clv_records.csv",
        consumers=("pro",),
        required_cols=("match", "market", "odds_bet", "odds_close", "clv_pct"),
        max_age_h=48.0,
        grain="one row per settled bet with a recorded close",
        caveat="clv_pct is a FRACTION (0.125 = 12.5%), unlike bets_ledger.csv. Carries NO league "
               "and NO match_date, so any fixture key built from them matches nothing. Every "
               "row is a PLAYER PROP.",
    ),
    Artifact(
        path="output/book_odds_snapshots.csv",
        consumers=("pro",),
        required_cols=("snapshot_ts", "league", "match", "kickoff_utc", "bookmaker", "market",
                       "side", "odds"),
        max_age_h=6.0,
        grain="one row per (book, market, side) price CHANGE",
        caveat="CONSECUTIVE-DISTINCT DEDUPED: a poll where nothing moved writes no row. So "
               "`size > 1` guarantees movement and cannot be used as evidence OF movement.",
        tags=("unrecoverable",),
    ),
    Artifact(
        path="output/standard_sidemarket_odds_history.csv",
        consumers=("pro",),
        required_cols=("snapshot_ts", "match_date", "league", "match", "market", "odds"),
        max_age_h=12.0,
        grain="one row per (fixture, market) price observation",
        caveat="271 of 6,358 btts_yes rows are FIRST-HALF prices mislabelled as full-match "
               "(parser fixed 2026-08-23). Filter btts_yes odds > 3.20 on read.",
        tags=("unrecoverable",),
    ),
    Artifact(
        path="output/newformat_odds_history.csv",
        consumers=("pro",),
        required_cols=("snapshot_date", "league", "match", "market", "odds"),
        max_age_h=12.0,
        grain="one row per (fixture, market) price observation",
        caveat="WORSE THAN THE STANDARD FILE: 931 of 3,778 btts_yes rows (24.6%) are first-half "
               "prices. Filter btts_yes odds > 3.20 on read.",
        tags=("unrecoverable",),
    ),
    Artifact(
        path="output/player_tips.csv",
        consumers=("pro",),
        required_cols=("date", "kickoff_utc", "league", "match", "player_id", "player_name",
                       "team", "market", "model_prob"),
        max_age_h=24.0,
        grain="one row per (fixture, player, market) on the current prop board",
        caveat="There is no player_props_predictions.csv — I declared that name first and the "
               "audit FAILED on it. AVOID here usually means NEVER PRICED, not rejected "
               "(invariant 13), and `team` must come from the live squad, not appearance "
               "history (invariant 12). Carries player_id, so joins should use it, not the name.",
    ),
    Artifact(
        path="player_history.parquet",
        consumers=("pro",),
        required_cols=("player_id", "team", "date"),
        max_age_h=240.0,
        grain="one row per player per match APPEARANCE",
        caveat="AT THE REPO ROOT, not under output/ — the audit's first version looked in "
               "output/ and reported 'not present'. `team` is who the player played for THAT "
               "DAY, including internationals, so current club must come from the latest CLUB "
               "row (invariant 12).",
        at_repo_root=True, parquet=True,
    ),
    Artifact(
        path="output/prop_odds_coverage.json",
        consumers=("pro",),
        required_cols=(),
        max_age_h=48.0,
        grain="learned ledger of which leagues OddsAPI actually prices",
        caveat="Read this before theorising about prop coverage; it answers from evidence.",
    ),
)

BY_PATH = {a.path: a for a in CONTRACT}


def for_consumer(name: str) -> tuple[Artifact, ...]:
    return tuple(a for a in CONTRACT if name in a.consumers)


def unrecoverable() -> tuple[Artifact, ...]:
    """Artifacts whose gaps can NEVER be backfilled — /odds is pre-match only.

    Separated because it sets the severity: a missing odds snapshot is permanent data loss, while
    a stale prediction board is a delay.
    """
    return tuple(a for a in CONTRACT if "unrecoverable" in a.tags)
