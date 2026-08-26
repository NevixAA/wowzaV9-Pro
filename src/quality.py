"""
The quality taxonomy: RAW / CLEAN / STRICT_CLEAN, in one place.
==============================================================
WHY CENTRALISE. Quality decisions were scattered across importers, monitors and analyses, each
with its own idea of what "usable" meant. Three concrete consequences:

  * `_rolling_clv_stats` filtered CLV at |25%| while nothing else did, so one module's "clean"
    was another's raw.
  * v11's movement work invented its own flag vocabulary (`POST_KICKOFF_ENTRY`,
    `INSUFFICIENT_BOOKS`, ...) with no relationship to Pro's (`MARKET_MAPPING_INVALID`,
    `ENTITY_UNRESOLVED`).
  * A reader of any aggregate had no way to know which exclusions had been applied, so two
    numbers computed from the same table could legitimately disagree and neither was wrong.

THE THREE LEVELS, and the distinction that actually matters:

    RAW           Everything as captured. No exclusions at all. This is what auditing "did the
                  data arrive" needs, and it is the ONLY level that can measure contamination —
                  a filtered view cannot tell you how much it filtered.

    CLEAN         Excludes rows whose value is WRONG: a mislabelled market, an unresolved
                  entity, a post-kickoff price, an impossible CLV. Use for any measurement.

    STRICT_CLEAN  CLEAN, plus excludes rows whose quality could not be VERIFIED — unknown
                  bookmaker count, missing kickoff time, unknown provenance. Use for a headline
                  claim or a graduation decision.

CLEAN vs STRICT_CLEAN is the load-bearing distinction, and it is the one most systems get wrong
by collapsing. "We checked and it was fine" and "we could not check" are different statements.
Treating the second as passing inflates every sample; treating it as failing throws away most of
the data. Both are wrong as a default, which is why the caller must choose.

**Nothing here deletes.** Every function returns a filtered VIEW and the stored row is untouched,
so the contamination stays auditable and a level can be widened later without re-collecting.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

RAW, CLEAN, STRICT_CLEAN = "RAW", "CLEAN", "STRICT_CLEAN"
LEVELS = (RAW, CLEAN, STRICT_CLEAN)


@dataclass(frozen=True)
class Flag:
    """One quality condition. `wrong` is the field that decides which level excludes it.

    wrong=True   the value is definitely incorrect -> excluded from CLEAN and STRICT_CLEAN
    wrong=False  the value may be fine but is UNVERIFIED -> excluded from STRICT_CLEAN only
    """
    name: str
    wrong: bool
    why: str


# The registry. Adding a flag here is what makes it participate in the levels — a flag string
# written directly into a frame without an entry here is treated as unverified rather than
# silently ignored, so a typo degrades safety instead of removing it.
FLAGS: dict[str, Flag] = {f.name: f for f in (
    # ── definitely wrong ────────────────────────────────────────────────────
    Flag("MARKET_MAPPING_INVALID", True,
         "odds absent or the two-way overround is impossible; the row is not the market it "
         "claims to be"),
    Flag("BTTS_FIRST_HALF_MISLABEL", True,
         "first-half Both-Teams-Score price captured as full-match. The capture parser matched "
         "the bet NAME by substring, so bet 34 'Both Teams Score - First Half' (Yes ~5.50) "
         "overwrote bet 8 'Both Teams Score' (Yes ~1.91). Parser fixed 2026-08-23; 271 of 6,358 "
         "historical btts_yes rows are affected. The populations do not overlap (clean 1.34-2.97, "
         "contaminated 3.40-7.00, ZERO observations between 3.03 and 3.22), so the threshold "
         "cannot catch a real price"),
    Flag("ENTITY_UNRESOLVED", True,
         "club name could not be resolved to a known entity, so the row cannot be joined to a "
         "fixture without risking the wrong one"),
    Flag("POST_KICKOFF_PRICE", True,
         "price observed at or after kickoff. A price that has seen part of the match is not a "
         "forecast, and it manufactured the entire apparent CLV edge before 2026-08-10"),
    Flag("CLV_IMPLAUSIBLE", True,
         "|clv_pct| beyond CLV_PLAUSIBLE_ABS; arithmetically possible only from a mis-joined or "
         "in-play price"),
    Flag("SEASON_MISMATCH", True,
         "row's season does not match the fixture's season; a season-keyed join went wrong"),

    # ── unverified, not necessarily wrong ───────────────────────────────────
    Flag("MISSING_OPPOSITE_SIDE", False,
         "only one side of a two-way market was captured, so the pair cannot be de-vigged. Found "
         "in the live data on 6.25% of market_snapshots and 60.06% of player_props — registered "
         "because it was already being written by importers while absent from this registry, "
         "which is exactly the divergence centralising is meant to end"),
    Flag("INSUFFICIENT_BOOKS", False,
         "fewer than 3 books, or the count is unknown. A thin consensus may still be correct"),
    Flag("MISSING_KICKOFF", False,
         "no kickoff time, so pre/post-kickoff cannot be PROVEN either way"),
    Flag("MODEL_VERSION_UNKNOWN", False,
         "no model sha recorded, so the row cannot be attributed to a model version"),
    Flag("FEATURE_DEGRADED", False,
         "one or more features were median-imputed; the prediction is real but rests on "
         "substituted inputs"),
    Flag("PROVENANCE_UNKNOWN", False,
         "source commit or calculation version not recorded"),
    Flag("XG_UNAVAILABLE", False,
         "the fixture carries no expected_goals, so any lambda built from it falls back to GOALS. "
         "Not wrong — the fallback is documented and honest — but a DIFFERENT estimator, and xG "
         "is measurably better (+0.0323 correlation with next-match scoring, CI [+0.0103, "
         "+0.0548]). Coverage is league- and season-dependent: 32.4% in 2023, 43.7% in 2024, "
         "74.6% in 2025, and 0% for Bundesliga 2 / La Liga 2 / Japan / China / Ireland / Romania. "
         "Any evaluation pooling xG and goals rows measures a mixture, so this flag is what lets "
         "a reader condition on the estimator"),
    Flag("STALE_PRICE_UNASSESSED", False,
         "staleness could not be evaluated — no per-book quote timestamp exists. Deliberately "
         "NOT called stale: calling an unchanged price stale would misclassify a settled market"),
)}

WRONG_FLAGS = frozenset(n for n, f in FLAGS.items() if f.wrong)
UNVERIFIED_FLAGS = frozenset(n for n, f in FLAGS.items() if not f.wrong)

# Full-match BTTS-YES ceiling. Sits inside the empty gap between the two populations; see the
# BTTS_FIRST_HALF_MISLABEL flag. Duplicated as a literal in v9's data_loader read filter, which
# is frozen and cannot import this module.
BTTS_YES_MAX = 3.20

# |clv_pct| beyond this is not a bad price, it is a broken join. Matches v11's CLV_PLAUSIBLE_ABS.
CLV_PLAUSIBLE_ABS = 25.0


def split_flags(s) -> list[str]:
    """'A|B' -> ['A','B']. Empty/NaN -> []."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    return [p for p in str(s).split("|") if p]


def add_flag(series: pd.Series, mask, flag: str) -> pd.Series:
    """Append `flag` to the pipe-delimited flags in `series` where `mask` is True.

    Appends rather than assigns. Several importers previously did `df.loc[mask, "quality_flags"]
    = "X"`, which silently DISCARDED any flag already present — a row that was both
    entity-unresolved and market-invalid ended up reporting only whichever check ran last.
    """
    out = series.fillna("").astype(str)
    if flag not in FLAGS:
        # Not raised: an unknown flag must still be recorded, and a typo should degrade to
        # "unverified" rather than vanish. But say so loudly.
        print(f"[quality] WARNING: '{flag}' is not in the FLAGS registry; it will be treated as "
              f"UNVERIFIED (excluded from STRICT_CLEAN only). Add it to src/quality.py.")
    add = out.where(~mask, (out + "|" + flag).str.strip("|"))
    return add


def flag_btts_first_half(df: pd.DataFrame, *, market_col: str = "market",
                         odds_col: str = "odds",
                         flags_col: str = "quality_flags") -> pd.DataFrame:
    """Flag (never drop) btts_yes rows carrying a first-half price."""
    if market_col not in df.columns or odds_col not in df.columns:
        return df
    d = df.copy()
    if flags_col not in d.columns:
        d[flags_col] = ""
    bad = (d[market_col].astype(str) == "btts_yes") & \
          (pd.to_numeric(d[odds_col], errors="coerce") > BTTS_YES_MAX)
    if bad.any():
        d[flags_col] = add_flag(d[flags_col], bad, "BTTS_FIRST_HALF_MISLABEL")
    return d


def level_of(flags) -> str:
    """The highest level a row qualifies for."""
    fl = set(split_flags(flags))
    if not fl:
        return STRICT_CLEAN
    if fl & WRONG_FLAGS:
        return RAW
    # Unknown flags are treated as unverified, not as harmless.
    return CLEAN


def at_level(df: pd.DataFrame, level: str, *, flags_col: str = "quality_flags") -> pd.DataFrame:
    """A VIEW of `df` at the requested level. Never mutates, never deletes.

    RAW returns everything, deliberately including a frame with no flags column at all — a table
    that has never been flagged is raw by definition, and silently returning it as CLEAN would be
    the worst possible default.
    """
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    if level == RAW or df.empty:
        return df
    if flags_col not in df.columns:
        print(f"[quality] '{flags_col}' absent; cannot filter to {level}. Returning RAW and "
              f"saying so rather than implying a filter was applied.")
        return df
    lv = df[flags_col].map(level_of)
    if level == CLEAN:
        return df[lv.isin((CLEAN, STRICT_CLEAN))]
    return df[lv == STRICT_CLEAN]


def summarise(df: pd.DataFrame, *, flags_col: str = "quality_flags") -> dict:
    """Counts per level and per flag — the numbers the audit and data_quality table report."""
    n = len(df)
    if not n or flags_col not in df.columns:
        # `classified: False` and NULL level counts, NOT zeros. Reporting 0 clean rows for a
        # table that has simply never been flagged reads as "everything is bad" when it means
        # "cannot assess" — the same conflation the CLEAN/STRICT_CLEAN split exists to prevent.
        # Three tables are in this state today (fixtures, feature_snapshots,
        # movement_observations), and the first version of this function reported all three as
        # having zero clean rows out of twelve thousand.
        return {"rows": n, "classified": False,
                "levels": {RAW: n, CLEAN: None, STRICT_CLEAN: None},
                "flags": {}, "flagged_rows": None}
    lv = df[flags_col].map(level_of)
    counts: dict[str, int] = {}
    for s in df[flags_col]:
        for f in split_flags(s):
            counts[f] = counts.get(f, 0) + 1
    return {
        "rows": n,
        "classified": True,
        "levels": {RAW: n,
                   CLEAN: int(lv.isin((CLEAN, STRICT_CLEAN)).sum()),
                   STRICT_CLEAN: int((lv == STRICT_CLEAN).sum())},
        "flags": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "flagged_rows": int((lv != STRICT_CLEAN).sum()),
    }
