"""Canonical club identity for Pro research frames (R2 finding 11, 2026-11-01).

WHY THIS EXISTS. The Prediction Lab grouped every rolling feature by the RAW team string, so a
club stored under two source spellings (Hull / Hull City, Sp Gijon / Sporting Gijon, ...) was two
"teams": the match was counted twice and each copy's rolling history held only half of the club's
games. v9 already repaired this for the Standard OU2.5 recipe (`src/identity_repair.py`, serving
recipe `v9_repaired`) with an EVIDENCE-BACKED, LEAGUE-SCOPED alias map (identity/1.1, 143 aliases,
18 leagues, each pair proven by >= 2 same-day same-score duplicate dates, plus the owner-accepted
Bray Wanderers -> Bray pair on one such date; ambiguous pairs refused).

WHAT THIS MODULE IS. A faithful port of v9's two identity stages, in v9's order:

  STAGE 1 -- v9 ``data_loader._canonicalise_clubs`` (port): within ONE league, spellings with the
     same v9 ``team_names.identity_key`` (``BK Hacken`` / ``Hacken``, ``FC St. Pauli`` /
     ``St Pauli``) are one club; the most recently seen spelling wins; score conflicts dropped;
     richest row kept. The identity alias map is expressed in the vocabulary this stage
     produces, so it MUST run first.

  STAGE 2 -- v9 ``identity_repair.canonicalise_and_dedupe(frame, frozen_map, derive=False)``:

  1. rename (league, name) -> canonical via the FROZEN map only (no derivation, no fuzzy match,
     no cross-league lookup -- a name unknown to the map is kept as-is and counted as unmapped);
  2. quarantine fixtures whose copies disagree on the score (dropped AND reported, never guessed);
  3. dedupe on (date, league, home, away) keeping the most complete row.

The map is a byte-identical copy of v9 ``config/standard_ou25_identity_aliases.json`` stored at
``registry/identity/club_aliases_identity_1.1.json``; its map hash is pinned below and checked on
load, so a silently edited map fails closed instead of changing research results.

WHY NOT ``src/data/club_resolver``. That module answers a DIFFERENT question: mapping OddsAPI-style
names onto football-data names by token-subset inference (with two-way ambiguity refusal). It is
inference from vocabulary, not evidence from duplicated matches, and it would e.g. propose aliases
inside one source that the same-day evidence rule never saw. It is not equivalent and is not used
here. The equivalence that IS proven (tests/test_lab_identity.py) is against v9's own
``identity_repair.canonicalise_and_dedupe`` with ``derive=False``.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

ALIAS_SOURCE_VERSION = "identity/1.1"
ALIAS_MAP_PATH = cfg.REGISTRY_DIR / "identity" / "club_aliases_identity_1.1.json"
# sha256 of json.dumps(map, sort_keys=True, ensure_ascii=False) -- identical to v9's file.
# identity/1.1 (v9 data-truth-100, 2026-11-02) = identity/1.0 + the owner-accepted Ireland Premier
# Division pair Bray Wanderers -> Bray (v9 identity_repair IDENTITY_VERSION v9r-identity-1.1).
# The 1.0 file stays in registry/identity/ unchanged (frozen) for anything that cites it.
ALIAS_MAP_SHA256 = "2441d47f5a1bf3bacac6b625548996fb82c438f22ca8e29ade7ff440e0e6ecf3"
IDENTITY_VERSION = "pro-identity-1.1+identity/1.1"


# ---- STAGE 1: port of v9 src/data_loader.py::_canonicalise_clubs.
# tests/test_lab_identity.py extracts v9's source and proves identical output.
# Since v9 2026-11-02 the club key is v9's src/team_names.identity_key (the resolver's token rule:
# same identity tokens once club-form words and bare numbers are removed, reserve sides apart), no
# longer the affix-stripping _norm_club. Loaded from the v9 checkout (src/data/v9_config), never
# copied, so the two cannot drift; without a v9 checkout this raises FileNotFoundError rather than
# keying clubs some other way.
def _identity_key(t: str) -> str:
    """v9 _canonicalise_clubs._key: identity_key, or the raw spelling when it carries no identity
    token (such a name is never merged with anything)."""
    from src.data import v9_config
    k = v9_config.team_names().identity_key(t)
    return k if k is not None else f"raw|{t}"


def unify_affix_spellings(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """v9 _canonicalise_clubs. Returns (frame, stats)."""
    if not {"league", "home_team", "away_team"}.issubset(df.columns):
        return df, {}
    d = df.copy()
    for c in ("home_team", "away_team"):
        d[c] = d[c].astype(str).str.strip()
    long = pd.concat([d[["league", "home_team", "date"]].rename(columns={"home_team": "t"}),
                      d[["league", "away_team", "date"]].rename(columns={"away_team": "t"})])
    long["k"] = long["t"].map(_identity_key)
    long["date"] = pd.to_datetime(long["date"], errors="coerce")
    agg = (long.groupby(["league", "k", "t"])
               .agg(last=("date", "max"), n=("t", "size")).reset_index()
               .sort_values(["league", "k", "last", "n"], ascending=[True, True, False, False]))
    winner = agg.drop_duplicates(["league", "k"], keep="first")
    mapping = {(lg, k): t for lg, k, t in zip(winner["league"], winner["k"], winner["t"])}
    n_multi = int((agg.groupby(["league", "k"])["t"].transform("size") > 1).sum())
    for c in ("home_team", "away_team"):
        keys = list(zip(d["league"].astype(str), d[c].map(_identity_key)))
        d[c] = [mapping.get(kk, orig) for kk, orig in zip(keys, d[c])]
    key = (d["date"].astype(str).str.slice(0, 10) + "|" + d["league"].astype(str) + "|"
           + d["home_team"] + "|" + d["away_team"])
    conflict = key.isin(
        key[d.groupby(key)[["home_goals", "away_goals"]].transform("nunique").max(axis=1) > 1])
    n_conflict = int(key[conflict].nunique())
    if n_conflict:
        d = d[~conflict]
    before = len(d)
    d = d.assign(_completeness=d.notna().sum(axis=1))
    d = (d.sort_values(["date", "_completeness"], kind="mergesort")
           .drop_duplicates(["date", "league", "home_team", "away_team"], keep="last")
           .drop(columns=["_completeness"]))
    return d, {"stage1_spellings_unified": n_multi, "stage1_duplicate_rows_removed": before - len(d),
               "stage1_score_conflicts": n_conflict}


class IdentityMapError(ValueError):
    """The alias map is not usable (hash mismatch, cycle, collapse). Research must stop."""


def map_sha256(amap: dict) -> str:
    return hashlib.sha256(json.dumps(amap, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def validate_alias_map(amap: dict) -> dict:
    """Structural checks that must hold for any league-scoped alias map.

    * no cycles (a -> b -> a) and no chains (a canonical name must not itself be an alias);
    * no self-alias;
    * keys are leagues; a name maps to exactly one canonical inside its league (dict guarantees
      it, we still verify after chain resolution).
    Returns counts; raises IdentityMapError on any violation.
    """
    n = 0
    for lg, m in amap.items():
        if not isinstance(m, dict):
            raise IdentityMapError(f"{lg}: map is not a dict")
        for a, c in m.items():
            n += 1
            if a == c:
                raise IdentityMapError(f"{lg}: self alias {a!r}")
            if c in m:
                raise IdentityMapError(f"{lg}: chain/cycle {a!r} -> {c!r} -> {m[c]!r}")
    return {"leagues": len(amap), "aliases": n}


def load_alias_map(path: Path | str | None = None, *, verify_hash: bool = True) -> dict:
    p = Path(path) if path else ALIAS_MAP_PATH
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("version") != ALIAS_SOURCE_VERSION:
        raise IdentityMapError(f"alias map version {d.get('version')!r} != {ALIAS_SOURCE_VERSION}")
    amap = {str(lg): {str(k): str(v) for k, v in (m or {}).items()}
            for lg, m in (d.get("map") or {}).items()}
    if verify_hash and map_sha256(amap) != ALIAS_MAP_SHA256:
        raise IdentityMapError(f"alias map hash differs from the pinned {ALIAS_SOURCE_VERSION} hash; "
                               "a new map needs a new IDENTITY_VERSION, not a silent edit")
    validate_alias_map(amap)
    return amap


def apply_aliases(df: pd.DataFrame, amap: dict,
                  cols: tuple[str, ...] = ("home_team", "away_team")) -> tuple[pd.DataFrame, int]:
    """League-scoped rename. Returns (copy, team cells renamed)."""
    d = df.copy()
    renamed = 0
    lgs = d["league"].astype(str).to_numpy()
    for c in cols:
        old = d[c].astype(str).to_numpy()
        new = np.asarray([amap.get(lg, {}).get(t, t) for lg, t in zip(lgs, old)], dtype=object)
        renamed += int((old != new).sum())
        d[c] = new
    return d, renamed


def canonicalise_fixtures(df: pd.DataFrame, amap: dict | None = None):
    """Stage 1 (v9 _canonicalise_clubs) then stage 2 (v9 identity_repair.canonicalise_and_dedupe,
    derive=False). Returns (frame, report)."""
    amap = load_alias_map() if amap is None else amap
    d, st1 = unify_affix_spellings(df)
    d, rep2 = alias_and_dedupe(d, amap)
    rep2.update(st1)
    return d, rep2


def alias_and_dedupe(df: pd.DataFrame, amap: dict):
    """Stage 2 only: port of v9 identity_repair.canonicalise_and_dedupe(derive=False)."""
    d, n_renamed = apply_aliases(df, amap)
    d["_d"] = pd.to_datetime(d["date"]).dt.normalize()
    key = ["_d", "league", "home_team", "away_team"]
    played = d["home_goals"].notna() & d["away_goals"].notna()
    sc = d[played].groupby(key)[["home_goals", "away_goals"]].nunique().max(axis=1)
    bad = set(sc[sc > 1].index)
    kk = list(zip(d["_d"], d["league"], d["home_team"], d["away_team"]))
    conflict = np.array([k in bad for k in kk], dtype=bool)
    quarantine = d[conflict].drop(columns=["_d"]).assign(reason="score_conflict_across_spellings")
    d = d[~conflict]
    before = len(d)
    d = (d.assign(_c=d.notna().sum(axis=1))
           .sort_values(["_d", "_c"], kind="mergesort")
           .drop_duplicates(key, keep="last").drop(columns=["_c", "_d"]))
    d = d.sort_values("date", kind="mergesort").reset_index(drop=True)
    report = {"identity_version": IDENTITY_VERSION, "alias_source": ALIAS_SOURCE_VERSION,
              "alias_map_sha256": map_sha256(amap),
              "n_aliases": int(sum(len(m) for m in amap.values())),
              "team_cells_renamed": n_renamed,
              "duplicate_rows_removed": int(before - len(d)),
              "quarantined_fixtures": int(len(quarantine)),
              "quarantine": quarantine}
    return d, report


# ------------------------------------------------------------------------------------------------
# Reconciliation diagnostics (before vs after). Pure functions of a fixture frame.

def same_day_team_collisions(df: pd.DataFrame) -> int:
    """(league, date, team) cells appearing in more than one fixture. A club plays once a day, so
    every such cell is either a duplicated match (identity split) or two clubs collapsed."""
    d = df[["league", "date", "home_team", "away_team"]].copy()
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    lg = pd.concat([d[["league", "date", "home_team"]].rename(columns={"home_team": "t"}),
                    d[["league", "date", "away_team"]].rename(columns={"away_team": "t"})])
    s = lg.groupby(["league", "date", "t"]).size()
    return int((s > 1).sum())


def same_day_same_score_duplicates(df: pd.DataFrame) -> int:
    """Rows in a (league, date, score) group of size > 1 whose home AND away names both differ
    from another row of the group -- the signature of one match stored under two spellings."""
    d = df[df["home_goals"].notna()].copy()
    d["_d"] = pd.to_datetime(d["date"]).dt.normalize()
    n = 0
    for _, g in d.groupby(["league", "_d", "home_goals", "away_goals"], sort=False):
        if len(g) < 2:
            continue
        rows = list(zip(g["home_team"].astype(str), g["away_team"].astype(str)))
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                if rows[i][0] != rows[j][0] and rows[i][1] != rows[j][1]:
                    n += 1
    return n


def collapse_check(df_before: pd.DataFrame, amap: dict) -> list[dict]:
    """Two DIFFERENT clubs collapsed onto one canonical name: an alias and its canonical (or two
    aliases of one canonical) that MEET each other, or that both play a different fixture on the
    same date. Must be empty."""
    d = df_before[["league", "date", "home_team", "away_team"]].astype({"home_team": str,
                                                                        "away_team": str}).copy()
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    out = []
    groups: dict = defaultdict(lambda: defaultdict(set))
    for lg, m in amap.items():
        for a, c in m.items():
            groups[lg][c].update({a, c})
    for lg, canon in groups.items():
        g = d[d["league"].astype(str) == lg]
        if g.empty:
            continue
        for c, names in canon.items():
            met = g[g["home_team"].isin(names) & g["away_team"].isin(names)]
            if len(met):
                out.append({"league": lg, "canonical": c, "problem": "names_meet",
                            "rows": int(len(met))})
    return out


def rolling_history_lengths(df: pd.DataFrame) -> pd.Series:
    """Matches per (league, team) -- the length of the history a rolling feature can see."""
    lg = pd.concat([df[["league", "home_team"]].rename(columns={"home_team": "t"}),
                    df[["league", "away_team"]].rename(columns={"away_team": "t"})])
    return lg.groupby(["league", "t"]).size()


def unmapped_names(df: pd.DataFrame, amap: dict) -> dict:
    """Per league: names that are neither an alias nor a canonical in the map. They are kept
    verbatim (no evidence either way) -- this is the residual, reported not guessed."""
    out = {}
    for lg, g in df.groupby("league"):
        names = set(g["home_team"].astype(str)) | set(g["away_team"].astype(str))
        m = amap.get(str(lg), {})
        known = set(m) | set(m.values())
        out[str(lg)] = int(len(names - known))
    return out


def reconcile(raw: pd.DataFrame, canon: pd.DataFrame, report: dict, amap: dict) -> dict:
    """Before/after reconciliation. Nothing here mutates either frame."""
    def teams(x):
        return int(len(set(zip(x["league"], x["home_team"])) | set(zip(x["league"], x["away_team"]))))
    hb, ha = rolling_history_lengths(raw), rolling_history_lengths(canon)
    unm = unmapped_names(canon, amap)
    per_league = []
    for lg in sorted(set(raw["league"].astype(str))):
        r, c = raw[raw["league"].astype(str) == lg], canon[canon["league"].astype(str) == lg]
        per_league.append({
            "league": lg, "fixtures_before": int(len(r)), "fixtures_after": int(len(c)),
            "teams_before": teams(r), "teams_after": teams(c),
            "collisions_before": same_day_team_collisions(r),
            "collisions_after": same_day_team_collisions(c),
            "median_history_before": float(hb.loc[lg].median()) if lg in hb.index.get_level_values(0) else 0.0,
            "median_history_after": float(ha.loc[lg].median()) if lg in ha.index.get_level_values(0) else 0.0,
            "aliases_in_map": int(len(amap.get(lg, {}))),
            "names_outside_map": unm.get(lg, 0)})
    return {
        "identity_version": IDENTITY_VERSION, "alias_map_sha256": report["alias_map_sha256"],
        "fixtures_before": int(len(raw)), "fixtures_after": int(len(canon)),
        "unique_teams_before": teams(raw), "unique_teams_after": teams(canon),
        "stage1_spellings_unified": report.get("stage1_spellings_unified"),
        "stage1_duplicate_rows_removed": report.get("stage1_duplicate_rows_removed"),
        "stage1_score_conflicts": report.get("stage1_score_conflicts"),
        "team_cells_renamed": report["team_cells_renamed"],
        "duplicate_rows_removed": report["duplicate_rows_removed"],
        "quarantined_score_conflicts": report["quarantined_fixtures"],
        "same_day_same_score_pairs_upper_bound_before": same_day_same_score_duplicates(raw),
        "same_day_same_score_pairs_upper_bound_after": same_day_same_score_duplicates(canon),
        "same_day_team_collisions_before": same_day_team_collisions(raw),
        "same_day_team_collisions_after": same_day_team_collisions(canon),
        "collapsed_clubs": collapse_check(raw, amap),
        "rolling_history_median_before": float(hb.median()),
        "rolling_history_median_after": float(ha.median()),
        "rolling_history_mean_before": round(float(hb.mean()), 2),
        "rolling_history_mean_after": round(float(ha.mean()), 2),
        "names_outside_map_total": int(sum(unm.values())),
        "per_league": per_league,
    }
