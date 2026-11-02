"""
Result-row guard: a score is only evidence for a match that has kicked off.
==========================================================================
ONE place for the two settlement rules every Pro grader shares (Data Truth round 3, 2026-11-02).

1. KICKOFF GUARD. A full-time result stored for a fixture whose kickoff is still in the future, or
   that was OBSERVED before its own kickoff, is not a result. Measured at origin/data-truth-100:

       team_match_stats  Grasshoppers v FC Basel 1893   kickoff 2026-11-28, 0-0, observed 2026-10-25
                         Lausanne v FC Sion             kickoff 2026-12-06, 0-1, observed 2026-10-25
                         Shakhtar Donetsk v Obolon'     kickoff 2027-05-08, 2-0, observed 2026-10-30
       scout_results     Sporting JAX v Birmingham      kickoff 2026-10-14, 0-1, observed 2026-10-10
                         Maghreb Fes v R. Berkane       kickoff 2026-10-29 20:00, observed 19:54

   The first two are API-Football marking the RETURN fixture FT with the first leg's result: the
   same run stored Basel v Grasshoppers 0-0 (2026-10-25, fixture 1555407) and Sion v Lausanne 1-0
   (2026-10-25) - the "future" rows are those scores mirrored onto the reverse fixtures. So the
   KICKOFF is right and the SCORE is wrong. Such a row must never settle anything, and a collector
   must not treat its fixture id as "already collected" (the real match would then never be read).

2. RESCHEDULED MATCHES (owner decision 2026-11-02). A tip whose match was moved settles on the
   match actually played when it kicked off within 48 hours of the tip's kickoff; otherwise the tip
   is VOID. Status codes (PST/CANC/ABD) are evidence; the age of a pending row alone is not.
"""
from __future__ import annotations

import pandas as pd

#: Owner decision 2026-11-02: played within this many hours of the original kickoff -> settle on
#: the actual match; later (or never) -> the tip is void.
RESCHEDULE_VOID_HOURS = 48.0

SAME = "SAME_KICKOFF"
SETTLE_ON_ACTUAL = "RESCHEDULED_SETTLE_ON_ACTUAL"
VOID_RESCHEDULED = "VOID_RESCHEDULED_GT_48H"
UNKNOWN = "KICKOFF_UNKNOWN"


def _ts(s: pd.Series, unit: str | None = None) -> pd.Series:
    if unit:
        return pd.to_datetime(pd.to_numeric(s, errors="coerce"), unit=unit, utc=True, errors="coerce")
    return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")


def unplayed_mask(df: pd.DataFrame, *, kickoff_col: str = "kickoff_utc",
                  observed_col: str = "observed_at", kickoff_unit: str | None = None,
                  now: pd.Timestamp | None = None) -> pd.Series:
    """True for a result row that cannot be a played match: its kickoff is after `now`, or after the
    moment the row was observed. A row with no kickoff is not judged here (False)."""
    if df is None or len(df) == 0 or kickoff_col not in df.columns:
        return pd.Series(False, index=getattr(df, "index", None), dtype=bool)
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    ko = _ts(df[kickoff_col], kickoff_unit)
    bad = ko.notna() & (ko > now)
    if observed_col in df.columns:
        obs = _ts(df[observed_col])
        bad |= ko.notna() & obs.notna() & (obs < ko)
    return bad.fillna(False).astype(bool)


def drop_unplayed(df: pd.DataFrame, label: str = "results", **kw) -> pd.DataFrame:
    """`df` without the rows `unplayed_mask` flags, and the count said out loud."""
    if df is None or len(df) == 0:
        return df
    bad = unplayed_mask(df, **kw)
    if bad.any():
        print(f"[result_guard] {label}: {int(bad.sum())} result row(s) dropped - full-time score "
              f"stored for a fixture that had not kicked off (provider error; never settles)")
    return df[~bad]


def reschedule_verdict(tip_kickoff, result_kickoff) -> str:
    """How a tip settles against the match actually played (owner rule 2026-11-02)."""
    a = pd.to_datetime(tip_kickoff, utc=True, errors="coerce")
    b = pd.to_datetime(result_kickoff, utc=True, errors="coerce")
    if pd.isna(a) or pd.isna(b):
        return UNKNOWN
    hours = abs((b - a).total_seconds()) / 3600.0
    if hours < 1e-9:
        return SAME
    return SETTLE_ON_ACTUAL if hours <= RESCHEDULE_VOID_HOURS else VOID_RESCHEDULED
