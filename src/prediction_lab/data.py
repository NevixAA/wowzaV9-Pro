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

THE SPINE IS fd_history. af_history is joined on (date, home, away) for the columns fd lacks.
It covers new-format leagues only, so any card feature is null for every standard-format
fixture -- handled as a feature FAMILY that is simply unavailable for that track, never as a
zero, because a zero would claim "no cards were shown" when the truth is "we did not look".
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"

# Targets derived purely from the final score. Nothing else in this lab may define one.
TARGETS = ("btts", "over15", "over25", "over35",
           "home_scores", "away_scores", "home_2plus", "away_2plus")

# Invariant 1: standard and new-format never mix. Tags copied verbatim from v9's config so they
# cannot drift -- the same reason v11 copies them.
STANDARD_FORMAT_LEAGUES = {
    "League One", "League Two", "Bundesliga 2", "La Liga 2", "Ligue 2", "Championship",
    "Serie B", "Greek Super League", "National League", "Portuguese Primeira Liga",
    "Scottish Championship", "Scottish League One", "Scottish League Two",
    "Belgian First Division A", "Dutch Eredivisie", "Scottish Premiership", "Turkish Super Lig",
}
NEW_FORMAT_LEAGUES = {
    "Denmark Superliga", "Austrian Bundesliga", "Sweden Allsvenskan", "Romanian Superliga",
    "Norway Eliteserien", "Finland Veikkausliiga", "Ireland Premier Division",
    "Argentina Primera Division", "Brazil Serie A", "Japan J-League", "Mexico Liga MX",
    "China Super League", "USA MLS", "Saudi Pro League", "K-League 1",
}


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


def model_type_for_league(league) -> str:
    lg = str(league).strip()
    if lg in STANDARD_FORMAT_LEAGUES:
        return "standard"
    if lg in NEW_FORMAT_LEAGUES:
        return "new_format"
    return "unknown"


def _season_label(d: pd.Series) -> np.ndarray:
    """Aug-Jul seasons. Calendar-year leagues (MLS, Brazil, Japan, Scandinavia) get labelled by
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


def load_fixtures(*, min_date: str | None = None) -> pd.DataFrame:
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
        keep = ["date", "home_team", "away_team", "HY", "AY", "HR", "AR",
                "HXG", "AXG", "HIB", "AIB"]
        keep = [c for c in keep if c in af.columns]
        af = (af.dropna(subset=["date", "home_team", "away_team"])
                .drop_duplicates(["date", "home_team", "away_team"], keep="last")[keep]
                .rename(columns={"HY": "home_yellow", "AY": "away_yellow",
                                 "HR": "home_red", "AR": "away_red",
                                 "HXG": "home_xg", "AXG": "away_xg",
                                 "HIB": "home_inbox", "AIB": "away_inbox"}))
        fd = fd.merge(af, on=["date", "home_team", "away_team"], how="left")

    fd = (fd.sort_values("date", kind="mergesort")
            .drop_duplicates(["date", "league", "home_team", "away_team"], keep="last")
            .reset_index(drop=True))
    if min_date:
        fd = fd[fd["date"] >= pd.Timestamp(min_date)].reset_index(drop=True)

    fd["fixture_key"] = (fd["date"].dt.strftime("%Y-%m-%d") + "|" + fd["league"].astype(str)
                         + "|" + fd["home_team"] + "|" + fd["away_team"])
    fd["model_type"] = fd["league"].map(model_type_for_league)
    fd["season_label"] = _season_label(fd["date"])
    return _attach_targets(fd)


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
            "season_label": d["season_label"], "team": d[f"{pfx}_team"],
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
    p = cfg.OUTPUT_DIR / "pure_prediction"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
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
            inv.to_csv(out_dir() / "data_inventory.csv", index=False)
            print(f"\n[data] wrote {out_dir() / 'data_inventory.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
