"""Readers for the REAL inputs of the props matchup track, each with explicit provenance.

Every reader returns (frame, Provenance). A missing file is an EMPTY frame with exists=False - never
a substitute file, never a typed value. Nothing is filled: a count the provider did not send stays
missing, a row whose counts are not verified carries count_source 'zeros_unverified' and the feature
builder treats its counts as missing.

Where v9 data comes from: cfg.V9_LOCAL (env V9_LOCAL; CI checks wowza-betting out into _v9), the same
pattern as src/data/v9_source.py and src/player_v3/data.py. v9 is read only, never written. For this
track V9_LOCAL must point at a checkout of wowza-betting branch data-truth-100.

THE OBSERVATION CLOCK (`pit`). Every source says what its timestamp means, because the matchup test
lives or dies on "was this known before kickoff?":
  observed_pre_kickoff    stamped by OUR poll before kickoff (Pro team_news, Pro injury_snapshots
                          rows with pre_kickoff=True, v9 prop odds snapshot_ts)
  fetched_after_the_fact  collected after the match (v9 injuries / lineups backfill, sidelined spells):
                          the CONTENT may be pre-match information, but WHEN it became known is
                          unproven; usable only under an explicitly flagged assumption
  outcome                 known only after full time (player_history counts, fullstats, settlement)
"""
from __future__ import annotations

import glob
import importlib.util
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

PIT_PRE = "observed_pre_kickoff"
PIT_AFTER = "fetched_after_the_fact"
PIT_OUTCOME = "outcome"

#: count_source values, as v9 defines them (player_model/player_stat_nulls.py, owner 2026-11-04,
#: fix round 9). tests/test_props_matchup.py checks these against v9's file when a checkout exists.
SOURCE_COL = "count_source"
PARSED_WITH_RULE = "provider_rule"
REFETCHED = "refetched"
UNVERIFIED = "zeros_unverified"
VERIFIED_SOURCES = frozenset({PARSED_WITH_RULE, REFETCHED})


@dataclass
class Provenance:
    name: str
    repo: str                       # 'wowza-betting' | 'wowzaV9-Pro'
    path: str                       # repo-relative
    exists: bool
    rows: int
    pit: str
    repo_sha: str = "unknown"
    read_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def v9_root(root: Path | None = None) -> Path:
    return Path(root) if root is not None else Path(cfg.V9_LOCAL)


def pro_root(root: Path | None = None) -> Path:
    return Path(root) if root is not None else Path(cfg.BASE_DIR)


def _sha(root: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=root,
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:                                                   # noqa: BLE001
        return "unknown"


def _parts(p: Path) -> list[str]:
    return sorted(glob.glob(str(p / "**" / "*.parquet"), recursive=True)) if p.is_dir() else (
        [str(p)] if p.exists() else [])


def _read_parquet(p: Path, columns: list[str] | None = None) -> pd.DataFrame:
    import pyarrow.parquet as pq
    parts = _parts(p)
    if not parts:
        return pd.DataFrame(columns=columns or [])
    have = set(pq.read_schema(parts[0]).names)
    cols = None if columns is None else [c for c in columns if c in have]
    return pd.read_parquet(p if p.is_dir() else parts[0], columns=cols)


def v9_verified_sources(root: Path | None = None) -> frozenset | None:
    """VERIFIED_SOURCES as v9's own player_stat_nulls.py states it (None when not readable). Loaded
    by file path under a distinctive name, the same way src/data/v9_config.py loads v9 code."""
    p = v9_root(root) / "player_model" / "player_stat_nulls.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location("_v9_player_stat_nulls_via_pro_matchup", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return frozenset(getattr(mod, "VERIFIED_SOURCES", frozenset()))


# ── player_history (outcome counts; verification state per row) ──────────────────────────────────
HISTORY_COLS = ["fixture_id", "player_id", "player_name", "date", "league", "season", "team",
                "opponent", "home_team", "away_team", "is_home", "position", "minutes", "started",
                "goals", "shots_total", "shots_on_target", SOURCE_COL]
#: the counts whose verification count_source describes (the ones this track uses)
COUNT_COLS = ["minutes", "started", "goals", "shots_total", "shots_on_target"]


def read_player_history(root: Path | None = None, columns: list[str] | None = None
                        ) -> tuple[pd.DataFrame, Provenance]:
    """v9 player_history.parquet with `count_source` on every row, v9's rule
    (player_model/history_refetch.with_refetched): re-fetched (fixture_id, player_id) rows take the
    re-fetched counts and 'refetched'; rows parsed with the null rule keep 'provider_rule'; every other
    row is 'zeros_unverified'. Nothing is written back."""
    r = v9_root(root)
    p = r / "player_history.parquet"
    d = _read_parquet(p, columns or HISTORY_COLS)
    prov = Provenance("player_history", "wowza-betting", "player_history.parquet", bool(_parts(p)),
                      len(d), PIT_OUTCOME, _sha(r))
    if d.empty:
        return d, prov
    stored = d[SOURCE_COL] if SOURCE_COL in d.columns else pd.Series(None, index=d.index, dtype=object)
    if SOURCE_COL not in d.columns:
        prov.notes.append("no count_source column in the file: every row written by the old `or 0` "
                          "parser -> zeros_unverified")
    ruled = stored.eq(PARSED_WITH_RULE)
    d[SOURCE_COL] = np.where(ruled, PARSED_WITH_RULE, UNVERIFIED)
    rf_path = r / "output" / "collect" / "player_history_refetch.parquet"
    if rf_path.exists():
        rf = pd.read_parquet(rf_path)
        rf = rf.assign(fixture_id=pd.to_numeric(rf["fixture_id"], errors="coerce"),
                       player_id=pd.to_numeric(rf["player_id"], errors="coerce")
                       ).dropna(subset=["fixture_id", "player_id"]).drop_duplicates(
                           ["fixture_id", "player_id"], keep="last").set_index(["fixture_id", "player_id"])
        key = pd.MultiIndex.from_arrays([pd.to_numeric(d["fixture_id"], errors="coerce"),
                                         pd.to_numeric(d["player_id"], errors="coerce")])
        hit = key.isin(rf.index) & ~ruled.to_numpy()
        if hit.any():
            sel = rf.reindex(key[hit])
            for c in COUNT_COLS:
                if c in rf.columns and c in d.columns:
                    col = pd.to_numeric(d[c], errors="coerce").astype(float)
                    col.loc[hit] = pd.to_numeric(sel[c], errors="coerce").astype(float).to_numpy()
                    d[c] = col
            d.loc[hit, SOURCE_COL] = REFETCHED
        prov.notes.append(f"refetch file present: {int(hit.sum()):,} rows carry re-fetched counts")
    else:
        prov.notes.append("output/collect/player_history_refetch.parquet absent: no row re-fetched yet")
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    if "position" in d.columns:
        d["position"] = d["position"].astype(str).str.upper().str[:1].replace({"": None, "N": None})
    return d, prov


# ── absences ─────────────────────────────────────────────────────────────────────────────────────
def read_sidelined(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """v9 sidelined spells (player_id, type, start, end) with the fetch time of each player's list.
    Fetched after the fact (one pull 2026-11-02): a spell's dates come from the provider today, so
    whether the absence was KNOWN before a given kickoff is not proven by this file."""
    r = v9_root(root)
    ps, pp = r / "output/collect/sidelined_spells.parquet", r / "output/collect/sidelined_players.parquet"
    s = _read_parquet(ps)
    prov = Provenance("sidelined_spells", "wowza-betting", "output/collect/sidelined_spells.parquet",
                      ps.exists(), len(s), PIT_AFTER, _sha(r))
    if s.empty:
        return s, prov
    if pp.exists():
        s = s.merge(_read_parquet(pp, ["player_id", "fetched_at"]), on="player_id", how="left")
    s["start"] = pd.to_datetime(s["start"], errors="coerce")
    s["end"] = pd.to_datetime(s["end"], errors="coerce")       # NaT = open spell, kept as NaT
    prov.notes.append(f"{int(s['end'].isna().sum()):,} spells have no end date (open or unknown) - kept missing")
    return s, prov


def read_injuries(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """v9 output/collect/injuries.parquet (API-Football /injuries, collection from 2026-11-05).
    Observed time = fetched_at; for a fixture already played at fetch it is fetched_after_the_fact."""
    r = v9_root(root)
    p = r / "output/collect/injuries.parquet"
    d = _read_parquet(p)
    prov = Provenance("v9_injuries", "wowza-betting", "output/collect/injuries.parquet", p.exists(),
                      len(d), PIT_AFTER, _sha(r))
    if not p.exists():
        prov.notes.append("MISSING: collection starts 2026-11-05")
    return d, prov


def read_lineups(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """v9 output/collect/lineups/players_<league>_<season>.parquet + the journal's fetched_at."""
    r = v9_root(root)
    lp = r / "output/collect/lineups"
    parts = sorted(lp.glob("players_*.parquet")) if lp.exists() else []
    d = pd.concat([pd.read_parquet(x) for x in parts], ignore_index=True) if parts else pd.DataFrame()
    prov = Provenance("v9_lineups", "wowza-betting", "output/collect/lineups/", bool(parts), len(d),
                      PIT_AFTER, _sha(r))
    j = r / "output/collect/lineups_fixtures.parquet"
    if parts and j.exists():
        d = d.merge(pd.read_parquet(j)[["fixture_id", "fetched_at"]], on="fixture_id", how="left")
    if not parts:
        prov.notes.append("MISSING: collection starts 2026-11-05")
    return d, prov


def read_injury_snapshots(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """Pro output/studies/injury_snapshots.parquet: API-Football's injury list as Pro saw it, stamped
    captured_at, with pre_kickoff. The ONLY injury source with a proven pre-kickoff clock today."""
    r = pro_root(root)
    p = r / "output/studies/injury_snapshots.parquet"
    d = _read_parquet(p)
    prov = Provenance("pro_injury_snapshots", "wowzaV9-Pro", "output/studies/injury_snapshots.parquet",
                      p.exists(), len(d), PIT_PRE, _sha(r))
    if len(d):
        d["captured_at"] = pd.to_datetime(d["captured_at"], utc=True, errors="coerce")
        d["fixture_ts"] = pd.to_datetime(d["fixture_ts"], utc=True, errors="coerce")
    return d, prov


def read_team_news(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """Pro data/<season>/team_news: lineups as first seen by Pro's poll (first_seen_ts, kickoff_utc).
    Starters are stored as NAMES only (no provider ids): matching them to player ids is a name match,
    which this track does not do (UNIDENTIFIABLE until ids are stored)."""
    r = pro_root(root)
    frames, rels = [], []
    for sdir in sorted((r / "data").glob("season_*/team_news")):
        frames.append(_read_parquet(sdir))
        rels.append(sdir.relative_to(r).as_posix())
    d = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    prov = Provenance("pro_team_news", "wowzaV9-Pro", ",".join(rels) or "data/season_*/team_news",
                      bool(frames), len(d), PIT_PRE, _sha(r),
                      ["starters are names, not provider ids"])
    return d, prov


# ── opponent concessions ─────────────────────────────────────────────────────────────────────────
def read_fullstats(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """v9 af_history_fullstats_fill.parquet in LONG form: one row per (fixture_id, team side) with
    shots / SoT for and against. NaN stays NaN."""
    r = v9_root(root)
    p = r / "output/collect/af_history_fullstats_fill.parquet"
    w = _read_parquet(p)
    prov = Provenance("af_fullstats", "wowza-betting", "output/collect/af_history_fullstats_fill.parquet",
                      p.exists(), len(w), PIT_OUTCOME, _sha(r))
    if w.empty:
        return w, prov
    dup = w[w["fixture_id"].duplicated(keep=False)]
    if len(dup):
        stat = ["home_sot", "away_sot", "home_shots", "away_shots"]
        conflict = int((dup.groupby("fixture_id")[stat].nunique(dropna=False) > 1).any(axis=1).sum())
        prov.notes.append(f"{len(dup):,} rows share a fixture_id with another row ({dup['fixture_id'].nunique():,} "
                          f"ids, e.g. club-name aliases); {conflict:,} of those ids disagree on shots/SoT")
    return fullstats_long(w), prov


def fullstats_long(w: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for me, op in (("home", "away"), ("away", "home")):
        rows.append(pd.DataFrame({
            "fixture_id": pd.to_numeric(w["fixture_id"], errors="coerce"),
            "date": pd.to_datetime(w["date"], errors="coerce"),
            "league": w.get("league"),
            "team": w[f"{me}_team"], "team_id": w.get(f"{me}_id"), "opponent": w[f"{op}_team"],
            "shots_for": pd.to_numeric(w[f"{me}_shots"], errors="coerce"),
            "sot_for": pd.to_numeric(w[f"{me}_sot"], errors="coerce"),
            "shots_against": pd.to_numeric(w[f"{op}_shots"], errors="coerce"),
            "sot_against": pd.to_numeric(w[f"{op}_sot"], errors="coerce")}))
    return pd.concat(rows, ignore_index=True)


def read_profiles(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    r = v9_root(root)
    p = r / "output/collect/player_profiles.parquet"
    d = _read_parquet(p)
    return d, Provenance("player_profiles", "wowza-betting", "output/collect/player_profiles.parquet",
                         p.exists(), len(d), PIT_AFTER, _sha(r))


# ── prices and settlement ────────────────────────────────────────────────────────────────────────
def read_prop_odds(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """v9 player_prop_odds_history (rolling: archive + live). A DISTINCT-PRICE append log
    (scripts/snapshot_prop_odds.py, every 4 h): a row is written when a price is first seen or
    changes, so 'one row' means 'one distinct price', not 'one look'. Keyed by player NAME and a
    'Home vs Away' string: no player_id, no fixture_id, no kickoff time."""
    from src.data import v9_source as S
    r = v9_root(root)
    rel = "output/player_prop_odds_history.csv"
    d = S.read_v9_all(rel, root=r, dtype=str, keep_default_na=False, na_values=[""])
    prov = Provenance("prop_odds_history", "wowza-betting", rel + " (+ _archive/)",
                      bool(len(d)), len(d), PIT_PRE, _sha(r),
                      ["distinct-price append; no player_id / fixture_id / kickoff time"])
    if len(d):
        d["snapshot_ts"] = pd.to_datetime(d["snapshot_ts"], utc=True, errors="coerce")
        d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    return d, prov


def read_prop_clv(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """v9 output/clv_records.csv: props bet price vs the last pre-kickoff price (best of books)."""
    r = v9_root(root)
    p = r / "output/clv_records.csv"
    d = pd.read_csv(p, dtype=str) if p.exists() else pd.DataFrame()
    return d, Provenance("prop_clv_records", "wowza-betting", "output/clv_records.csv", p.exists(),
                         len(d), PIT_PRE, _sha(r),
                         ["odds_close = best of books at the last snapshot before kickoff"])


def read_player_ledger(root: Path | None = None) -> tuple[pd.DataFrame, Provenance]:
    """v9 output/player_ledger.csv: props tips with the price at signal and the settled result."""
    r = v9_root(root)
    p = r / "output/player_ledger.csv"
    d = pd.read_csv(p, dtype=str) if p.exists() else pd.DataFrame()
    return d, Provenance("player_ledger", "wowza-betting", "output/player_ledger.csv", p.exists(),
                         len(d), PIT_OUTCOME, _sha(r))
