"""The canonical research dataset: every eligible fixture, its outcome, and nothing from after
kickoff.

    python -m src.prediction_lab.data --inventory --write

WHERE THE DATA COMES FROM. Two committed v9 tables carry the history, read from a local
wowza-betting checkout when V9_LOCAL points at one and over raw HTTP otherwise -- the same
discipline v11 uses. Pro never writes into v9.

    fd_history.parquet   58,156 fixtures, 30 leagues, 2019-02 .. 2026-09.
                         Goals (the targets), plus shots, shots on target, corners, fouls and
                         half-time goals. Also carries odds, which the primary experiment
                         deliberately ignores.
    af_history.parquet   28,504 fixtures, the 15 new-format leagues. Adds cards, and nominally
                         xG and inside-box shots.

A FINDING FROM THE INVENTORY ITSELF, recorded here because it changes what can be asked:
xG IS EFFECTIVELY ABSENT. HXG/AXG are populated on 0-2% of rows in every single league, and
inside-box shots on 0-3%. The column exists; the data does not. So "does xG help?" cannot be
answered from this warehouse -- only "xG is present too rarely to test", which is a different
and much less interesting answer. Run --inventory to see it per league.

THE SPINE IS fd_history. af_history is joined for the columns fd lacks. Where af has no row the
card feature is null -- handled as a feature FAMILY that is unavailable for that fixture, never as
a zero, because a zero would claim "no cards were shown" when the truth is "we did not look".

DATA VERSION 2.0 (R2, 2026-11-01). Version 1.0 grouped by RAW team strings, so a club stored under
two source spellings was two teams (double-counted matches, rolling history split in half), the af
join ignored the league, and `season_label` was an Aug-Jul bucket for every league. 2.0:
  * canonical league-scoped club identity (src/data/canonical_identity, the frozen identity/1.0
    alias map shared with v9's v9_repaired serving recipe); score conflicts quarantined;
  * af joined on (league, date, canonical home, canonical away), many-to-one validated, row count
    asserted unchanged;
  * `league_season` / `season_type` / `season_status` from the league-aware season calendar
    (src/data/season_calendar). `season_label` is KEPT as the Jul-Jun CHRONOLOGICAL BUCKET it
    always was (folds and other callers use it as a time bucket, not as a season);
  * outputs go to output/pure_prediction/data_v2/ -- version 1.0 outputs are never overwritten --
    and every written table carries data_version + identity_version.
`identity="raw"` reproduces 1.0 exactly, for the before/after reconciliation only.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
DATA_VERSION = "lab-data/2.0"
LEGACY_DATA_VERSION = "lab-data/1.0"

# Targets derived purely from the final score. Nothing else in this lab may define one.
TARGETS = ("btts", "over15", "over25", "over35",
           "home_scores", "away_scores", "home_2plus", "away_2plus")

# Invariant 1: standard and new-format never mix. The track lists are NOT typed here (Data Truth
# 2026-11-01): they are v9's registry (config/leagues.json model_type) through src/data/v9_config,
# so a league added to or moved in the registry is picked up without a second copy to edit.
# `STANDARD_FORMAT_LEAGUES` / `NEW_FORMAT_LEAGUES` stay readable as module attributes.
def __getattr__(name):
    from src.data import v9_config
    if name == "STANDARD_FORMAT_LEAGUES":
        return set(v9_config.standard_leagues())
    if name == "NEW_FORMAT_LEAGUES":
        return set(v9_config.new_format_leagues())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _v9_dirs():
    env = os.getenv("V9_LOCAL", "")
    cands = [Path(env)] if env else []
    cands.append(Path(getattr(cfg, "V9_LOCAL", cfg.BASE_DIR.parent / "v9")))
    cands.append(cfg.BASE_DIR.parent / "v9")
    return cands


def _read_v9_parquet(rel: str, *, required: bool = True) -> pd.DataFrame:
    """Local checkout first, raw HTTP second. Parquet, so it cannot go through fetch_csv."""
    for base in _v9_dirs():
        try:
            p = Path(base) / rel
        except TypeError:
            continue
        if p.exists():
            return pd.read_parquet(p)
    import io

    import requests
    url = f"{cfg.V9_RAW_BASE}/{rel.split('output/')[-1]}"
    r = requests.get(url, timeout=120)
    if r.status_code != 200:
        if required:
            raise RuntimeError(f"cannot read v9 {rel} (HTTP {r.status_code}). "
                               f"Set V9_LOCAL to a wowza-betting checkout.")
        return pd.DataFrame()
    return pd.read_parquet(io.BytesIO(r.content))


def _norm_team(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip()


def model_type_for_league(league) -> str | None:
    """'standard' | 'new_format' from the registry (canonical name or alias); None for a league
    the registry does not type - never the placeholder 'unknown'."""
    from src.data import v9_config
    return v9_config.model_type(league)


def _season_label(d: pd.Series) -> np.ndarray:
    """A CHRONOLOGICAL BUCKET (Jul-Jun), not a season. Use `league_season` (season calendar) for
    anything that means "this league's season". Kept for folds and existing callers.

    Original note -- Aug-Jul seasons. Calendar-year leagues (MLS, Brazil, Japan, Scandinavia) get labelled by
    the same rule, which is wrong for them as a "season" but right as a CHRONOLOGICAL BUCKET --
    and a chronological bucket is the only thing it is ever used for."""
    y = d.dt.year
    return np.where(d.dt.month >= 7,
                    y.astype(str) + "/" + (y + 1).astype(str).str[-2:],
                    (y - 1).astype(str) + "/" + y.astype(str).str[-2:])


def _attach_targets(d: pd.DataFrame) -> pd.DataFrame:
    """What actually happened. Derived from the final score and nothing else."""
    hg, ag = d["home_goals"], d["away_goals"]
    tot = hg + ag
    d["total_goals"] = tot
    d["btts"] = ((hg > 0) & (ag > 0)).astype(int)
    d["over15"] = (tot >= 2).astype(int)
    d["over25"] = (tot >= 3).astype(int)
    d["over35"] = (tot >= 4).astype(int)
    d["home_scores"] = (hg > 0).astype(int)
    d["away_scores"] = (ag > 0).astype(int)
    d["home_2plus"] = (hg >= 2).astype(int)
    d["away_2plus"] = (ag >= 2).astype(int)
    d["goals_bucket"] = np.minimum(tot, 5).astype(int)      # 0,1,2,3,4,5+ for the goal model
    return d


def _load_fixtures_legacy(fd: pd.DataFrame, af: pd.DataFrame) -> pd.DataFrame:
    """Data version 1.0, verbatim: raw strings, league-blind af join. Reconciliation only."""
    if not af.empty:
        fd = fd.merge(af, on=["date", "home_team", "away_team"], how="left")
    return (fd.sort_values("date", kind="mergesort")
              .drop_duplicates(["date", "league", "home_team", "away_team"], keep="last")
              .reset_index(drop=True))


def _join_af_canonical(fd: pd.DataFrame, af: pd.DataFrame, amap: dict) -> tuple[pd.DataFrame, dict]:
    """League-scoped, identity-resolved, many-to-one join. Never expands rows."""
    from src.data import canonical_identity as CI
    stats = {"af_rows": int(len(af)), "af_duplicate_keys_dropped": 0, "af_matched": 0}
    if af.empty or "league" not in af.columns:
        return fd, stats
    af, _ = CI.apply_aliases(af, amap)
    key = ["league", "date", "home_team", "away_team"]
    n0 = len(af)
    af = af.drop_duplicates(key, keep="last")
    stats["af_duplicate_keys_dropped"] = int(n0 - len(af))
    n_left = len(fd)
    out = fd.merge(af.assign(_af=1), on=key, how="left", validate="many_to_one")
    if len(out) != n_left:
        raise AssertionError(f"af enrichment changed row count {n_left} -> {len(out)}")
    stats["af_matched"] = int(out["_af"].notna().sum())
    return out.drop(columns=["_af"]), stats


def load_fixtures(*, min_date: str | None = None, identity: str = "canonical",
                  report: dict | None = None) -> pd.DataFrame:
    """Every fixture with a final score. One row per fixture. Targets attached, no features.

    Deduplicated on (date, league, home, away). Duplicates exist because fd_history is appended
    on every retrain and re-downloading a season re-adds its rows; keeping both would
    double-count a match in every rate this lab reports.
    """
    fd = _read_v9_parquet("output/fd_history.parquet")
    fd["date"] = pd.to_datetime(fd["date"], errors="coerce")
    for c in ("home_goals", "away_goals", "home_shots", "away_shots", "home_sot", "away_sot",
              "home_corners", "away_corners", "home_fouls", "away_fouls",
              "ht_home_goals", "ht_away_goals",
              "odds_over25", "odds_under25", "odds_btts", "odds_over15", "odds_over35"):
        if c in fd.columns:
            fd[c] = pd.to_numeric(fd[c], errors="coerce")
    fd["home_team"] = _norm_team(fd["home_team"])
    fd["away_team"] = _norm_team(fd["away_team"])
    fd = fd.dropna(subset=["date", "home_goals", "away_goals"])
    fd = fd[fd["home_team"].ne("") & fd["away_team"].ne("")]

    af = _read_v9_parquet("output/af_history.parquet", required=False)
    if not af.empty:
        af["date"] = pd.to_datetime(af["date"], errors="coerce")
        af["home_team"] = _norm_team(af["home_team"])
        af["away_team"] = _norm_team(af["away_team"])
        for c in ("HY", "AY", "HR", "AR", "HXG", "AXG", "HIB", "AIB"):
            if c in af.columns:
                af[c] = pd.to_numeric(af[c], errors="coerce")
        keep = ["league", "date", "home_team", "away_team", "HY", "AY", "HR", "AR",
                "HXG", "AXG", "HIB", "AIB"]
        keep = [c for c in keep if c in af.columns]
        af = (af.dropna(subset=["date", "home_team", "away_team"])[keep]
                .rename(columns={"HY": "home_yellow", "AY": "away_yellow",
                                 "HR": "home_red", "AR": "away_red",
                                 "HXG": "home_xg", "AXG": "away_xg",
                                 "HIB": "home_inbox", "AIB": "away_inbox"}))

    if identity == "raw":
        if not af.empty:
            af = (af.drop(columns=["league"], errors="ignore")
                    .drop_duplicates(["date", "home_team", "away_team"], keep="last"))
        fd = _load_fixtures_legacy(fd, af)
        ident_version, rep_d = "raw", {}
    elif identity == "canonical":
        from src.data import canonical_identity as CI
        amap = CI.load_alias_map()
        fd, rep_d = CI.canonicalise_fixtures(fd, amap)
        fd, af_stats = _join_af_canonical(fd, af, amap)
        rep_d["af_join"] = af_stats
        ident_version = CI.IDENTITY_VERSION
    else:
        raise ValueError(f"identity must be 'canonical' or 'raw', not {identity!r}")
    if report is not None:
        report.update(rep_d)
    if min_date:
        fd = fd[fd["date"] >= pd.Timestamp(min_date)].reset_index(drop=True)

    fd["fixture_key"] = (fd["date"].dt.strftime("%Y-%m-%d") + "|" + fd["league"].astype(str)
                         + "|" + fd["home_team"] + "|" + fd["away_team"])
    fd["model_type"] = fd["league"].map(model_type_for_league)
    fd["season_label"] = _season_label(fd["date"])        # chronological bucket, NOT a season
    if identity == "canonical":
        from src.data import season_calendar as SC
        fd = fd.join(SC.league_season_frame(fd["league"], fd["date"]))
        if report is not None:
            report["season_calendar"] = SC.health(fd["league"], fd["date"])
    fd = _attach_targets(fd)
    fd.attrs["identity_version"] = ident_version
    fd.attrs["data_version"] = DATA_VERSION if identity == "canonical" else LEGACY_DATA_VERSION
    return fd


def team_match_long(d: pd.DataFrame) -> pd.DataFrame:
    """One row per TEAM per match -- the frame every rolling feature is built on.

    Rolling form has to be computed per team across all of its matches regardless of which side
    it played, so the fixture frame is unpivoted first. Doing it the other way (rolling within
    home rows and within away rows separately) is the mistake that produces a "home form"
    feature which silently ignores every away game the team played in between.
    """
    def side(pfx: str, opp: str, is_home: int) -> pd.DataFrame:
        out = pd.DataFrame({
            "fixture_key": d["fixture_key"], "date": d["date"], "league": d["league"],
            "season_label": d["season_label"],
            "league_season": (d["league_season"] if "league_season" in d.columns
                              else pd.Series(np.nan, index=d.index, dtype=object)),
            "season_status": (d["season_status"] if "season_status" in d.columns
                              else pd.Series(np.nan, index=d.index, dtype=object)),
            "team": d[f"{pfx}_team"],
            "opponent": d[f"{opp}_team"], "is_home": is_home,
            "gf": d[f"{pfx}_goals"], "ga": d[f"{opp}_goals"],
        })
        for src, dst in (("shots", "shots"), ("sot", "sot"), ("corners", "corners"),
                         ("fouls", "fouls"), ("yellow", "yellow"), ("red", "red"),
                         ("xg", "xg"), ("inbox", "inbox")):
            if f"{pfx}_{src}" in d.columns:
                out[f"{dst}_f"] = d[f"{pfx}_{src}"]
                out[f"{dst}_a"] = d[f"{opp}_{src}"]
        if "ht_home_goals" in d.columns:
            out["ht_gf"] = d["ht_home_goals"] if is_home else d["ht_away_goals"]
            out["ht_ga"] = d["ht_away_goals"] if is_home else d["ht_home_goals"]
        return out

    long = pd.concat([side("home", "away", 1), side("away", "home", 0)], ignore_index=True)
    long["total_goals"] = long["gf"] + long["ga"]
    long["btts"] = ((long["gf"] > 0) & (long["ga"] > 0)).astype(int)
    return long.sort_values(["team", "date"], kind="mergesort").reset_index(drop=True)


def inventory(d: pd.DataFrame) -> pd.DataFrame:
    """Per league: rows, span, and how complete each feature source actually is.

    This is the table that answers "which questions can this warehouse even be asked?" before a
    single model is fitted. A feature at 2% coverage is not a weak feature, it is an absent one.
    """
    rows = []
    for lg, g in d.groupby("league"):
        r = {"league": lg, "model_type": g["model_type"].iloc[0], "rows": len(g),
             "first": str(g["date"].min().date()), "last": str(g["date"].max().date()),
             "seasons": int(pd.Series(g["season_label"]).nunique()),
             "teams": len(set(g.home_team) | set(g.away_team))}
        for name, col in (("goals", "home_goals"), ("shots", "home_shots"), ("sot", "home_sot"),
                          ("corners", "home_corners"), ("fouls", "home_fouls"),
                          ("ht_goals", "ht_home_goals"), ("cards", "home_yellow"),
                          ("xg", "home_xg"), ("inbox", "home_inbox"),
                          ("odds_ou25", "odds_over25"), ("odds_btts", "odds_btts"),
                          ("odds_ou15", "odds_over15"), ("odds_ou35", "odds_over35")):
            r[f"cov_{name}"] = round(float(g[col].notna().mean()), 4) if col in g.columns else 0.0
        for t in ("btts", "over15", "over25", "over35"):
            r[f"rate_{t}"] = round(float(g[t].mean()), 4)
        r["avg_goals"] = round(float(g["total_goals"].mean()), 3)
        rows.append(r)
    return pd.DataFrame(rows).sort_values("rows", ascending=False)


def out_dir() -> Path:
    """Data-version 2.0 outputs. The 1.0 files in output/pure_prediction/ are left untouched."""
    p = cfg.OUTPUT_DIR / "pure_prediction" / "data_v2"
    p.mkdir(parents=True, exist_ok=True)
    return p


def version_stamp() -> dict:
    from src.data import canonical_identity as CI
    from src.data import season_calendar as SC
    return {"data_version": DATA_VERSION, "identity_version": CI.IDENTITY_VERSION,
            "season_calendar_version": SC.calendar_version()}


def stamp(df: pd.DataFrame) -> pd.DataFrame:
    """Every table this lab writes carries the versions that produced it."""
    out = df.copy()
    for k, v in version_stamp().items():
        out[k] = v
    return out


def reconciliation() -> dict:
    """Before (data 1.0, raw strings) vs after (data 2.0, canonical identity)."""
    from src.data import canonical_identity as CI
    raw = load_fixtures(identity="raw")
    rep: dict = {}
    can = load_fixtures(identity="canonical", report=rep)
    amap = CI.load_alias_map()
    out = CI.reconcile(raw, can, rep, amap)
    out.update(version_stamp())
    out["af_join_after"] = rep.get("af_join")
    for nm, fr in (("before", raw), ("after", can)):
        out[f"af_cards_coverage_{nm}"] = (round(float(fr["home_yellow"].notna().mean()), 4)
                                          if "home_yellow" in fr.columns else 0.0)
    out["season_calendar"] = rep.get("season_calendar")
    differs = can["league_season"].astype(str) != pd.Series(can["season_label"]).astype(str)
    out["league_season_differs_from_bucket_rows"] = int(differs.sum())
    q = rep.get("quarantine")
    out["quarantine_sample"] = ([] if q is None or q.empty else
                                q[["date", "league", "home_team", "away_team", "home_goals",
                                   "away_goals"]].astype(str).head(20).to_dict("records"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--reconcile", action="store_true",
                    help="before/after identity reconciliation -> identity_reconciliation.json")
    a = ap.parse_args()
    if a.reconcile:
        import json
        r = reconciliation()
        summary = {k: v for k, v in r.items() if k not in ("per_league", "quarantine_sample")}
        print(json.dumps(summary, indent=2, default=str))
        if a.write:
            (out_dir() / "identity_reconciliation.json").write_text(
                json.dumps(r, indent=2, default=str), encoding="utf-8")
            stamp(pd.DataFrame(r["per_league"])).to_csv(
                out_dir() / "identity_reconciliation_by_league.csv", index=False)
            print(f"[data] wrote identity_reconciliation.json to {out_dir()}")
        return 0
    d = load_fixtures()
    print(f"[data] {len(d):,} fixtures  {d.date.min().date()}..{d.date.max().date()}  "
          f"{d.league.nunique()} leagues  {pd.Series(d.season_label).nunique()} season buckets")
    print("[data] model_type:", d.model_type.value_counts().to_dict())
    print("[data] base rates:", {t: round(float(d[t].mean()), 4)
                                 for t in ("btts", "over15", "over25", "over35")})
    if a.inventory:
        inv = inventory(d)
        with pd.option_context("display.width", 260, "display.max_columns", 40):
            print(inv.to_string(index=False))
        if a.write:
            stamp(inv).to_csv(out_dir() / "data_inventory.csv", index=False)
            print(f"\n[data] wrote {out_dir() / 'data_inventory.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
