"""Matchup features with point-in-time correctness.

    from src.props_matchup import features as F
    feats, absentees, audit = F.build(targets, appearances, team_stats, absences,
                                      lookback_matches=..., form_matches=...)

THE CLOCK. Every target row carries `decision_ts` (UTC): the moment the tip would be made. Then:
  * an absence counts only if it was OBSERVED at or before decision_ts (observed_at <= decision_ts).
    An absence with no observation time is dropped and counted in the audit - never assumed known;
  * an absence whose clock is 'fetched_after_the_fact' (backfilled injuries / lineups / sidelined
    spells) is used ONLY when the caller passes allow_after_the_fact=True, and every feature row it
    touches is marked absence_clock='assumed' (for exploratory history work, never for the edge test);
  * every outcome-derived number (importance, with/without concessions, attacker form) uses matches
    whose DATE is strictly before the target's date. Same-day matches are excluded on purpose:
    player_history has a date, not a kickoff time, so same-day order is unprovable.

MISSING STAYS MISSING. Counts from a row whose count_source is not verified are treated as missing
(verified_only=True, the default for this track). A window that contains a missing count gives a
missing feature - not an average of the rest - because "the rest" is a silently different sample.
An absentee never seen for his team has unknown importance (NaN), not 0.

`lookback_matches` and `form_matches` are research parameters with no default: they are fixed in the
pre-registration (reports/R_PROPS_MATCHUP_SPEC.md) before any real data is looked at.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.props_matchup import DEFENSIVE_POSITIONS
from src.props_matchup.inputs import PIT_AFTER, PIT_PRE, SOURCE_COL, VERIFIED_SOURCES

TARGET_COLS = ["fixture_id", "player_id", "team", "opponent", "date", "decision_ts"]
ABSENCE_COLS = ["fixture_id", "team", "player_id", "observed_at", "pit", "source"]


def _verified_counts(app: pd.DataFrame, cols: list[str], verified_only: bool) -> pd.DataFrame:
    a = app.copy()
    for c in cols:
        a[c] = pd.to_numeric(a[c], errors="coerce").astype(float)
    if verified_only:
        ok = a[SOURCE_COL].isin(VERIFIED_SOURCES) if SOURCE_COL in a.columns else pd.Series(False, index=a.index)
        a.loc[~ok, cols] = np.nan
    return a


def known_absences(absences: pd.DataFrame, targets: pd.DataFrame, *, allow_after_the_fact: bool
                   ) -> tuple[pd.DataFrame, dict]:
    """Absences of each target's OPPONENT that were observed by the target's decision time."""
    audit = {"absences_in": int(len(absences))}
    if absences.empty:
        return absences.assign(decision_ts=pd.Series(dtype="datetime64[ns, UTC]")), {**audit, "kept": 0}
    a = absences.copy()
    a["observed_at"] = pd.to_datetime(a["observed_at"], utc=True, errors="coerce")
    no_clock = a["observed_at"].isna()
    audit["dropped_no_observation_time"] = int(no_clock.sum())
    a = a[~no_clock]
    allowed = {PIT_PRE} | ({PIT_AFTER} if allow_after_the_fact else set())
    bad_pit = ~a["pit"].isin(allowed)
    audit["dropped_clock_not_allowed"] = int(bad_pit.sum())
    a = a[~bad_pit]
    t = targets[["fixture_id", "opponent", "decision_ts"]].drop_duplicates()
    m = a.merge(t, left_on=["fixture_id", "team"], right_on=["fixture_id", "opponent"], how="inner")
    late = m["observed_at"] > m["decision_ts"]
    audit["dropped_observed_after_decision"] = int(late.sum())
    m = m[~late].drop(columns=["opponent"])
    m = m.drop_duplicates(["fixture_id", "team", "player_id", "decision_ts"])
    audit["kept"] = int(len(m))
    return m, audit


def absentee_profile(app: pd.DataFrame, team: str, player_id, before: pd.Timestamp,
                     team_stats: pd.DataFrame, lookback_matches: int) -> dict:
    """One absentee's importance and the team's concessions with / without him, from the team's last
    `lookback_matches` matches strictly before `before` (a date)."""
    tm = app[(app["team"] == team) & (app["date"] < before)]
    fx = (tm[["fixture_id", "date"]].drop_duplicates().sort_values(["date", "fixture_id"])
          .tail(lookback_matches))
    out = {"team_matches": int(len(fx)), "position": None, "minutes_share": np.nan, "start_share": np.nan,
           "n_with": 0, "n_without": 0, "shots_against_with": np.nan, "shots_against_without": np.nan,
           "sot_against_with": np.nan, "sot_against_without": np.nan}
    if fx.empty:
        return out
    w = tm[tm["fixture_id"].isin(fx["fixture_id"])]
    me = w[w["player_id"] == player_id]
    if me.empty:
        return out                                    # never seen for this team: importance unknown
    pos = me["position"].dropna()
    out["position"] = pos.mode().iloc[0] if len(pos) else None
    if w["minutes"].isna().any() or w["started"].isna().any():
        return out                                    # a missing count in the window -> unknown
    team_min = float(w["minutes"].sum())
    out["minutes_share"] = float(me["minutes"].sum()) / team_min * 11 if team_min > 0 else np.nan
    out["start_share"] = float(me["started"].sum()) / len(fx)
    started_in = set(me.loc[me["started"] > 0, "fixture_id"])
    ts = team_stats[(team_stats["team"] == team) & team_stats["fixture_id"].isin(fx["fixture_id"])]
    ts = ts.drop_duplicates("fixture_id")
    with_ = ts[ts["fixture_id"].isin(started_in)]
    without = ts[~ts["fixture_id"].isin(started_in)]
    out["n_with"], out["n_without"] = int(len(with_)), int(len(without))
    for col in ("shots_against", "sot_against"):
        # a match without the stat is not 0 conceded: the mean is over the matches that HAVE it, and
        # n_with / n_without count only those (a NaN anywhere makes that side's mean NaN)
        for side, frame in (("with", with_), ("without", without)):
            v = frame[col]
            out[f"{col}_{side}"] = float(v.mean()) if len(v) and v.notna().all() else np.nan
    return out


def attacker_form(app: pd.DataFrame, player_id, before: pd.Timestamp, form_matches: int) -> dict:
    p = app[(app["player_id"] == player_id) & (app["date"] < before)].sort_values(["date", "fixture_id"])
    p = p.tail(form_matches)
    out = {"form_n": int(len(p)), "form_sot_p90": np.nan, "form_shots_p90": np.nan,
           "form_goals_p90": np.nan, "form_minutes_mean": np.nan, "form_start_share": np.nan}
    if p.empty or p[["minutes", "started", "shots_on_target", "shots_total", "goals"]].isna().any().any():
        return out
    mins = float(p["minutes"].sum())
    if mins > 0:
        out["form_sot_p90"] = float(p["shots_on_target"].sum()) / mins * 90
        out["form_shots_p90"] = float(p["shots_total"].sum()) / mins * 90
        out["form_goals_p90"] = float(p["goals"].sum()) / mins * 90
    out["form_minutes_mean"] = mins / len(p)
    out["form_start_share"] = float(p["started"].sum()) / len(p)
    return out


def observed_lists(lists: pd.DataFrame, targets: pd.DataFrame, *, allow_after_the_fact: bool) -> set:
    """(fixture_id, team, decision_ts) whose absence list - possibly EMPTY - was observed by the
    decision time. Without such an observation 'no absentee' is unknown, not zero."""
    if lists is None or lists.empty:
        return set()
    l = lists.copy()
    l["observed_at"] = pd.to_datetime(l["observed_at"], utc=True, errors="coerce")
    allowed = {PIT_PRE} | ({PIT_AFTER} if allow_after_the_fact else set())
    l = l[l["observed_at"].notna() & l["pit"].isin(allowed)]
    m = l.merge(targets[["fixture_id", "opponent", "decision_ts"]].drop_duplicates(),
                left_on=["fixture_id", "team"], right_on=["fixture_id", "opponent"], how="inner")
    m = m[m["observed_at"] <= m["decision_ts"]]
    return set(zip(m["fixture_id"], m["team"], m["decision_ts"]))


ABSENCE_FEATURES = ["opp_absent_n", "opp_def_absent_n", "opp_def_absent_minutes_share", "opp_gk_absent_n",
                    "opp_gk_absent_start_share", "opp_unknown_position_absent_n", "top_def_n_with",
                    "top_def_n_without", "top_def_sot_against_delta", "top_def_shots_against_delta"]


def build(targets: pd.DataFrame, appearances: pd.DataFrame, team_stats: pd.DataFrame,
          absences: pd.DataFrame, lists: pd.DataFrame, *, lookback_matches: int, form_matches: int,
          verified_only: bool = True, allow_after_the_fact: bool = False
          ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(features per target row, one row per known absentee, audit).

    `lists`: one row per OBSERVED absence list (fixture_id, team, observed_at, pit), including lists
    with no absentee. A target whose opponent has no list observed by decision_ts gets NaN absence
    features and absence_clock 'none'."""
    missing = [c for c in TARGET_COLS if c not in targets.columns]
    if missing:
        raise ValueError(f"targets lack {missing}: decision_ts must be explicit (no implied clock)")
    t = targets.copy()
    t["date"] = pd.to_datetime(t["date"]).dt.normalize()
    t["decision_ts"] = pd.to_datetime(t["decision_ts"], utc=True)
    app = _verified_counts(appearances, ["minutes", "started", "shots_on_target", "shots_total", "goals"],
                           verified_only)
    app["date"] = pd.to_datetime(app["date"]).dt.normalize()
    ts = team_stats.copy()
    ts["date"] = pd.to_datetime(ts["date"]).dt.normalize()

    known, audit = known_absences(absences, t, allow_after_the_fact=allow_after_the_fact)
    seen = observed_lists(lists, t, allow_after_the_fact=allow_after_the_fact)
    if len(known):                                   # a known absentee implies an observed list
        seen |= set(zip(known["fixture_id"], known["team"], known["decision_ts"]))
    prof_rows = []
    for r in known.itertuples(index=False):
        date = t.loc[(t["fixture_id"] == r.fixture_id), "date"].iloc[0]
        pr = absentee_profile(app, r.team, r.player_id, date, ts, lookback_matches)
        prof_rows.append({"fixture_id": r.fixture_id, "team": r.team, "player_id": r.player_id,
                          "decision_ts": r.decision_ts, "observed_at": r.observed_at, "pit": r.pit,
                          "source": getattr(r, "source", None), **pr})
    absentees = pd.DataFrame(prof_rows)

    rows = []
    for r in t.itertuples(index=False):
        a = absentees[(absentees["fixture_id"] == r.fixture_id) & (absentees["team"] == r.opponent)
                      & (absentees["decision_ts"] == r.decision_ts)] if len(absentees) else absentees
        d = a[a["position"].isin(DEFENSIVE_POSITIONS)] if len(a) else a
        gk = d[d["position"] == "G"] if len(d) else d
        _sum = (lambda s: float(s.sum()) if s.notna().all() else np.nan)  # noqa: E731
        top = d.sort_values("minutes_share", ascending=False, na_position="first").head(1) if len(d) else d
        row = {"fixture_id": r.fixture_id, "player_id": r.player_id, "decision_ts": r.decision_ts,
               "opp_absent_n": int(len(a)), "opp_def_absent_n": int(len(d)),
               "opp_def_absent_minutes_share": _sum(d["minutes_share"]) if len(d) else 0.0,
               "opp_gk_absent_n": int(len(gk)),
               "opp_gk_absent_start_share": _sum(gk["start_share"]) if len(gk) else 0.0,
               "opp_unknown_position_absent_n": int(a["position"].isna().sum()) if len(a) else 0,
               "absence_clock": ("assumed" if len(a) and (a["pit"] == PIT_AFTER).any() else "observed")}
        if len(top):
            x = top.iloc[0]
            row.update({"top_def_absentee": x["player_id"], "top_def_n_with": x["n_with"],
                        "top_def_n_without": x["n_without"],
                        "top_def_sot_against_delta": x["sot_against_without"] - x["sot_against_with"],
                        "top_def_shots_against_delta": x["shots_against_without"] - x["shots_against_with"]})
        else:
            row.update({"top_def_absentee": None, "top_def_n_with": 0, "top_def_n_without": 0,
                        "top_def_sot_against_delta": np.nan, "top_def_shots_against_delta": np.nan})
        if (r.fixture_id, r.opponent, r.decision_ts) not in seen:
            for k in ABSENCE_FEATURES:
                row[k] = np.nan
            row["top_def_absentee"] = None
            row["absence_clock"] = "none"
        row.update(attacker_form(app, r.player_id, r.date, form_matches))
        rows.append(row)
    feats = pd.DataFrame(rows)
    audit["targets"] = int(len(t))
    audit["targets_without_observed_list"] = int((feats["absence_clock"] == "none").sum()) if len(feats) else 0
    return feats, absentees, audit
