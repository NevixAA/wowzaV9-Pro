"""
Re-key the season warehouse from fixture_key v1 to v2 (Data Truth round 2, 2026-11-02).
=====================================================================================
    python -m src.pipelines.migrate_fixture_key_v2 [--season season_2026_27] [--dry-run]

Needs V9_LOCAL (v9's registry, resolver and output/clv_records.csv + player_ledger.csv).

WHAT IT DOES, per partition file (rewritten in place; nothing is appended, no run is re-collected):

  * `fixture_key`          -> the v2 key (src/data/fixture_key_v2.py), or None when it cannot be
                              built honestly (unknown league, unparseable date, no source row).
  * `old_fixture_key`      -> the v1 key the row was stored with. Always kept, so every artifact
                              that still holds a v1 key can be joined to the migrated rows.
  * `fixture_key_version`  -> 'fk2'.
  * `fixture_key_status`   -> RESOLVED | CLUB_UNRESOLVED | CLUB_COLLISION | LEAGUE_UNKNOWN |
                              DATE_UNPARSEABLE | CLUB_MISSING | V1_UNMAPPED | V1_AMBIGUOUS.

  Tables that hold the club names (fixtures, book_odds_snapshots, market_snapshots from the odds
  histories, team_match_stats, team_news, settlements_backfill; combo_candidates and
  combo_settlements through their 'Home vs Away' `match`) are keyed from those names. Every other
  keyed table (model/feature snapshots, signals, settlements, live_signals, player_props,
  combo_legs) carries only the v1 key, so it gets the v2 key through the v1 -> v2 map built from
  the named rows. A v1 key that maps to no v2 key, or to more than one, gets None and is listed -
  never the first match.

  clv rows stored before 2026-11-01 were keyed on an EMPTY league and date (every meeting of two
  clubs in any season hashed together), so their v1 key identifies nothing. Their identity is
  recovered from v9's own output/clv_records.csv on (ts_bet, player, market) with the same rule the
  importer uses since round 1 (match date from bet_id, league from v9's player_ledger); a row that
  does not recover keeps no key and is listed.

  combo ids are '<fixture_key>|<legs hash>' (pipelines/bet_builder), so `combo_id` is re-prefixed
  with the v2 key (old value in `old_combo_id`) in candidates, legs and settlements alike.

DATES. `kickoff_utc` in book_odds_snapshots and settlements_backfill (two formats mixed in one
column, and the string 'nan') is rewritten as 'YYYY-MM-DDTHH:MM:SSZ' from the explicit format list;
a value matching no format becomes None and is counted. clv `match_date` '' becomes the recovered
date or None.

DEDUPE. Rows that are exact copies of another row of the SAME partition file (every column equal,
run id included) carry no information and are dropped. Rows sharing the table's canonical grain
but differing in any value are NOT touched - which copy is right is not ours to guess - and are
counted in the report.

OUTPUT. output/fixture_key_v2/migration_report.json, unresolved_clubs.csv, unmapped_v1_keys.csv.
Re-runnable: the v1 key is read from `old_fixture_key` when present.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg  # noqa: E402
from src.data import entities as ent  # noqa: E402
from src.data import fixture_key_v2 as fk2  # noqa: E402

NAMED = ("fixtures", "book_odds_snapshots", "market_snapshots", "team_match_stats", "team_news",
         "settlements_backfill")
MATCH_NAMED = ("combo_candidates", "combo_settlements")
MAPPED = ("model_snapshots", "feature_snapshots", "signals", "settlements", "live_signals",
          "player_props", "combo_legs", "clv")
COMBO = ("combo_candidates", "combo_legs", "combo_settlements")
KICKOFF_FIX = ("book_odds_snapshots", "settlements_backfill")
DEDUPE_ONLY = ("scout_odds", "scout_results")

# The grain at which two rows describe the same observation. Used only to COUNT conflicting
# copies after the exact-copy dedupe; nothing is removed on it.
GRAIN = {
    "fixtures": ["fixture_key", "run_id"],
    "book_odds_snapshots": ["fixture_key", "market", "side", "bookmaker", "snapshot_ts"],
    "market_snapshots": ["fixture_key", "market", "side", "bookmaker", "run_id", "captured_at"],
    "settlements": ["fixture_key", "market", "side", "run_id"],
    "player_props": ["fixture_key", "player_name", "market", "run_id"],
    "team_match_stats": ["fixture_id"],
    "team_news": ["fixture_key", "team", "first_seen_ts"],
    "combo_settlements": ["combo_id", "run_id"],
    "scout_odds": ["fixture_id", "market", "selection", "bookmaker", "snapshot_ts"],
}


def _files(root: Path, table: str) -> list[Path]:
    return sorted((root / table).glob("dt=*/run=*.parquet"))


def _v1(d: pd.DataFrame) -> pd.Series:
    if "old_fixture_key" in d.columns:
        return d["old_fixture_key"]
    if "fixture_key" in d.columns:
        return d["fixture_key"]
    return pd.Series([None] * len(d), index=d.index, dtype=object)


def _names(d: pd.DataFrame, table: str) -> pd.DataFrame | None:
    """(league, match_date, home_team, away_team) for a row, from the table's own columns."""
    if table in MATCH_NAMED:
        if not {"league", "match_date", "match"} <= set(d.columns):
            return None
        h, a = ent.split_match(d["match"].astype(object).where(d["match"].notna(), ""))
        return pd.DataFrame({"league": d["league"], "match_date": d["match_date"],
                             "home_team": h.where(h.astype(str).str.strip() != ""),
                             "away_team": a.where(a.astype(str).str.strip() != "")}, index=d.index)
    if {"league", "match_date", "home_team", "away_team"} <= set(d.columns):
        return d[["league", "match_date", "home_team", "away_team"]]
    return None


def _clv_lookup(log: dict) -> dict:
    """(ts_bet, player, market) -> (league, match_date, home, away) from v9's clv_records, with the
    importer's own identity rule. Keys that occur twice with different identities are dropped."""
    from src.importers.current_wowza import clv_identity
    from src.data.v9_source import fetch_csv
    raw = fetch_csv("output/clv_records.csv", required=False)
    if raw.empty:
        log["clv_recovery"] = "v9 output/clv_records.csv unavailable"
        return {}
    ident = clv_identity(raw)
    k = list(zip(raw.get("ts_bet", pd.Series(index=raw.index, dtype=object)).astype(str),
                 raw.get("player", pd.Series(index=raw.index, dtype=object)).astype(str),
                 raw.get("market", pd.Series(index=raw.index, dtype=object)).astype(str)))
    vals = list(zip(ident["league"], ident["match_date"], ident["home_team"], ident["away_team"]))
    seen: dict = defaultdict(set)
    for kk, v in zip(k, vals):
        seen[kk].add(tuple(None if pd.isna(x) else x for x in v))
    out = {kk: next(iter(v)) for kk, v in seen.items() if len(v) == 1}
    log["clv_recovery"] = {"source_rows": int(len(raw)), "keys": len(seen),
                           "ambiguous_keys": sum(1 for v in seen.values() if len(v) > 1),
                           "with_league_and_date": sum(1 for v in out.values() if v[0] and v[1])}
    return out


# v9 files whose rows the importer keyed (src/importers/current_wowza.py) and which still hold the
# club names: settlements (bets_ledger, side_bets_ledger), player_props (player_ledger) and
# live_signals (live_signals_history, 'Home vs Away' in `match`). The importer built the v1 key from
# exactly these strings (match_date cut to 10 characters), so recomputing v1 here reproduces the
# stored key and the same strings give the v2 key. Read through v9_source (archives included).
V9_NAMED_SOURCES = (
    ("output/bets_ledger.csv", "match_date", None),
    ("output/side_bets_ledger.csv", "match_date", None),
    ("output/player_ledger.csv", "match_date", None),
    ("output/live_signals_history.csv", "date", "match"),
)


def _v9_named_frames(log: dict):
    """(source, frame of league/match_date/home_team/away_team) per v9 source that is readable."""
    from src.data.v9_source import fetch_csv_all
    seen = {}
    for rel, dcol, mcol in V9_NAMED_SOURCES:
        try:
            raw = fetch_csv_all(rel, required=False)
        except Exception as e:                      # a missing source is reported, never invented
            seen[rel] = f"unreadable: {type(e).__name__}"
            continue
        if raw.empty or "league" not in raw.columns or dcol not in raw.columns:
            seen[rel] = "empty or missing columns"
            continue
        if mcol:
            if mcol not in raw.columns:
                seen[rel] = f"no {mcol} column"
                continue
            h, a = ent.split_match(raw[mcol])
        elif {"home_team", "away_team"} <= set(raw.columns):
            h, a = raw["home_team"], raw["away_team"]
        else:
            seen[rel] = "no club columns"
            continue
        nm = pd.DataFrame({"league": raw["league"], "match_date": raw[dcol].astype(str).str[:10],
                           "home_team": h, "away_team": a}).drop_duplicates()
        seen[rel] = int(len(nm))
        yield rel, nm
    log["v9_named_sources"] = seen


def _add_to_map(m: dict, v1: pd.Series, k: pd.DataFrame) -> None:
    for a, b, s in zip(v1, k["fixture_key"], k["fixture_key_status"]):
        if a is not None and not pd.isna(a) and b is not None:
            m[str(a)][b] = s


def build_map(root: Path, log: dict, *, v9_sources: bool = True) -> tuple[dict, pd.DataFrame]:
    """v1 -> {v2: status} from every named row (warehouse + v9's named ledgers), plus the
    unresolved-club listing."""
    m: dict = defaultdict(dict)
    unres: Counter = Counter()
    mism = Counter()
    for t in NAMED + MATCH_NAMED:
        for f in _files(root, t):
            d = pd.read_parquet(f)
            nm = _names(d, t)
            if nm is None:
                continue
            k = fk2.add_keys(nm, log_unresolved=False)
            v1 = _v1(d)
            mism[t] += int((v1.astype(str) != k["old_fixture_key"].astype(str)).sum())
            _add_to_map(m, v1, k)
            for _, r in fk2.unresolved_names(nm).iterrows():
                unres[(t, r["league"], r["name"])] += int(r["rows"])
    if v9_sources:
        for rel, nm in _v9_named_frames(log):
            k = fk2.add_keys(nm, log_unresolved=False)
            _add_to_map(m, k["old_fixture_key"], k)
            for _, r in fk2.unresolved_names(nm).iterrows():
                unres[(f"v9:{rel}", r["league"], r["name"])] += int(r["rows"])
    log["v1_recomputed_differs_from_stored"] = dict(mism)
    u = pd.DataFrame([{"table": t, "league": lg, "name": n, "rows": c}
                      for (t, lg, n), c in sorted(unres.items())],
                     columns=["table", "league", "name", "rows"])
    return dict(m), u


def _status_from_map(v1, m: dict) -> tuple[str | None, str]:
    if v1 is None or pd.isna(v1) or str(v1) == "":
        return None, "V1_UNMAPPED"
    hit = m.get(str(v1))
    if not hit:
        return None, "V1_UNMAPPED"
    if len(hit) > 1:
        return None, "V1_AMBIGUOUS"
    (k, s), = hit.items()
    return k, s


def migrate_frame(d: pd.DataFrame, table: str, m: dict, clv: dict | None = None,
                  stats: Counter | None = None) -> pd.DataFrame:
    """The migrated copy of one partition frame. Pure: no I/O."""
    stats = stats if stats is not None else Counter()
    out = d.copy()
    v1 = _v1(out).astype(object)
    nm = _names(out, table) if table in NAMED + MATCH_NAMED else None

    if table == "clv" and clv is not None:
        key = list(zip(out.get("ts_bet", pd.Series(index=out.index, dtype=object)).astype(str),
                       out.get("player", pd.Series(index=out.index, dtype=object)).astype(str),
                       out.get("market", pd.Series(index=out.index, dtype=object)).astype(str)))
        rec = [clv.get(k) for k in key]
        lg = [r[0] if r else None for r in rec]
        md = [r[1] if r else None for r in rec]
        nm = pd.DataFrame({"league": lg, "match_date": md,
                           "home_team": [r[2] if r else None for r in rec],
                           "away_team": [r[3] if r else None for r in rec]}, index=out.index)
        out["league"] = pd.Series(lg, index=out.index, dtype=object)
        out["match_date"] = pd.Series(md, index=out.index, dtype=object)
        stats["clv_rows_recovered"] += int(sum(1 for x, y in zip(lg, md) if x and y))
        stats["clv_rows_not_recovered"] += int(sum(1 for x, y in zip(lg, md) if not (x and y)))

    if nm is not None:
        k = fk2.add_keys(nm, log_unresolved=False)
        keys, status = k["fixture_key"].astype(object), k["fixture_key_status"].astype(object)
        # A named row whose names are blank (old odds rows, combos without `match`) falls back to
        # the v1 map rather than staying keyless.
        blank = keys.isna() & k["fixture_key_status"].eq(fk2.CLUB_MISSING)
        if blank.any():
            fb = [_status_from_map(x, m) for x in v1[blank]]
            keys[blank] = [x[0] for x in fb]
            status[blank] = [x[1] for x in fb]
    else:
        fb = [_status_from_map(x, m) for x in v1]
        keys = pd.Series([x[0] for x in fb], index=out.index, dtype=object)
        status = pd.Series([x[1] for x in fb], index=out.index, dtype=object)

    out["fixture_key"] = keys
    out["old_fixture_key"] = v1
    out["fixture_key_version"] = fk2.KEY_VERSION
    out["fixture_key_status"] = status
    for s, c in status.value_counts(dropna=False).items():
        stats[f"status:{s}"] += int(c)

    if table in COMBO and "combo_id" in out.columns:
        old = (out["old_combo_id"] if "old_combo_id" in out.columns else out["combo_id"]).astype(object)
        pre = old.astype(str).str.split("|", n=1).str[0]
        suf = old.astype(str).str.split("|", n=1).str[1]
        ok = keys.notna() & suf.notna() & pre.eq(v1.astype(str))
        out["old_combo_id"] = old
        out["combo_id"] = old.where(~ok, keys.astype(str) + "|" + suf)
        stats["combo_ids_reprefixed"] += int(ok.sum())
        stats["combo_ids_kept"] += int((~ok).sum())

    if table in KICKOFF_FIX and "kickoff_utc" in out.columns:
        before = out["kickoff_utc"]
        conv = before.map(fk2.to_utc_iso)
        had = before.notna() & before.astype(str).str.strip().ne("") & before.astype(str).ne("nan")
        stats["kickoff_normalised"] += int(conv.notna().sum())
        stats["kickoff_unparseable"] += int((had & conv.isna()).sum())
        stats["kickoff_blank_or_nan_to_none"] += int((~had).sum())
        out["kickoff_utc"] = conv.astype(object)
        # minutes_to_kickoff was computed with a format-guessing parser that gave up on the mixed
        # column, so it is NaN on those rows. Recomputed from the explicit-format values, ONLY
        # where it is NaN (a value already stored is never rewritten).
        if {"minutes_to_kickoff", "snapshot_ts"} <= set(out.columns):
            ts = out["snapshot_ts"].map(fk2.to_utc_iso)
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            mins = ((pd.to_datetime(conv, format=fmt, utc=True)
                     - pd.to_datetime(ts, format=fmt, utc=True)).dt.total_seconds() / 60.0).round(1)
            fill = pd.to_numeric(out["minutes_to_kickoff"], errors="coerce").isna() & mins.notna()
            out.loc[fill, "minutes_to_kickoff"] = mins[fill]
            if "is_post_kickoff" in out.columns:
                out.loc[fill, "is_post_kickoff"] = mins[fill] < 0
            stats["minutes_to_kickoff_recomputed"] += int(fill.sum())

    if table == "clv" and "match_date" in out.columns:
        out["match_date"] = out["match_date"].map(fk2.match_day).astype(object)
    return out


def dedupe_exact(d: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop rows that are exact copies (every column) of an earlier row of the same frame."""
    h = pd.util.hash_pandas_object(d.astype(str), index=False)
    dup = h.duplicated(keep="first")
    return d[~dup.to_numpy()], int(dup.sum())


# Ingestion bookkeeping: the same observation stored by two runs differs only here.
META = ("ingested_at", "observed_at", "run_id", "source", "source_sha", "pro_git_sha")


def dedupe_canonical(d: pd.DataFrame, table: str) -> tuple[pd.Series, pd.DataFrame]:
    """Table-wide dedupe on the CANONICAL grain (fixture_key v2 for keyed tables).

    A row is dropped only when an earlier-ingested row has the same grain AND the same value in
    every column except ingestion bookkeeping (META, unless META is part of the grain) - the same
    observation stored twice. Rows sharing the grain but differing in any value are KEPT and
    returned as conflicts: which copy is right is not ours to guess. Rows whose grain has a missing
    part (no v2 key) are never grain-deduped. Returns (drop mask, conflicting rows)."""
    g = [c for c in GRAIN.get(table, []) if c in d.columns]
    drop = pd.Series(False, index=d.index)
    if not g or d.empty:
        return drop, d.iloc[0:0]
    ok = d[g].notna().all(axis=1)
    x = d[ok]
    payload = [c for c in x.columns if c not in META or c in g]
    h = pd.util.hash_pandas_object(x[payload].astype(str), index=False)
    drop.loc[x.index] = h.duplicated(keep="first").to_numpy()
    kept = x[~drop.loc[x.index].to_numpy()]
    conf = kept[kept.duplicated(subset=g, keep=False)]
    return drop, conf


def grain_conflicts(d: pd.DataFrame, table: str) -> int:
    return int(len(dedupe_canonical(d, table)[1]))


# ── output records keyed on fixture_key (combo + paper + challenger records) ─────────────────────
# The frozen forward-shadow files (output/standard_repair/*) keep v1: their row ids are registered
# (registry/standard_repair/forward_shadow_v1.json) and must not move. clv_enriched.csv is a
# DERIVED artifact of the clv table and is rebuilt from it (src/market/clv_schema --write).
RECORDS = {
    "bet_builder_candidates.csv": "match",
    "bet_builder_daily.csv": "match",
    "bet_builder_settled.csv": "match",
    "studies/ou_challenger_forward.csv": "names",
    "paper_1x2.csv": "names",
}


def migrate_record(d: pd.DataFrame, name: str, m: dict, stats: Counter | None = None) -> pd.DataFrame:
    """Re-key one output record. v2 from the record's own names (league, match_date, clubs); a row
    whose names cannot key falls back to the v1 -> v2 map on its stored key. combo_id is
    re-prefixed (old value in old_combo_id); paper_1x2's row_id, which hashes the key, is
    recomputed with paper_1x2's own rule (old value in old_row_id) so the next run does not log
    the same fixture again. Pure: no I/O."""
    stats = stats if stats is not None else Counter()
    out = d.copy()
    n = len(out)
    if RECORDS.get(name) == "match" and {"league", "match_date", "match"} <= set(out.columns):
        nm = _names(out, "combo_settlements")
    elif {"league", "match_date", "home_team", "away_team"} <= set(out.columns):
        nm = out[["league", "match_date", "home_team", "away_team"]]
    else:
        nm = None
    if "old_fixture_key" in out.columns:
        v1 = out["old_fixture_key"].astype(object)
    elif "fixture_key" in out.columns:
        v1 = out["fixture_key"].astype(object)
    elif "combo_id" in out.columns:                 # bet_builder_daily: the key is the id prefix
        v1 = out["combo_id"].astype(str).str.split("|", n=1).str[0].astype(object)
    else:
        v1 = pd.Series([None] * n, index=out.index, dtype=object)
    if nm is not None:
        k = fk2.add_keys(nm, log_unresolved=False)
        keys, status = k["fixture_key"].astype(object), k["fixture_key_status"].astype(object)
        fbm = keys.isna() & status.eq(fk2.CLUB_MISSING)
    else:
        keys = pd.Series([None] * n, index=out.index, dtype=object)
        status = pd.Series([None] * n, index=out.index, dtype=object)
        fbm = pd.Series(True, index=out.index)
    if fbm.any():
        fb = [_status_from_map(x, m) for x in v1[fbm]]
        keys[fbm] = [x[0] for x in fb]
        status[fbm] = [x[1] for x in fb]
    out["fixture_key"] = keys
    out["old_fixture_key"] = v1
    out["fixture_key_version"] = fk2.KEY_VERSION
    out["fixture_key_status"] = status
    for s, c in status.value_counts(dropna=False).items():
        stats[f"status:{s}"] += int(c)
    if "combo_id" in out.columns:
        old = (out["old_combo_id"] if "old_combo_id" in out.columns else out["combo_id"]).astype(object)
        sp = old.astype(str).str.split("|", n=1)
        pre, suf = sp.str[0], sp.str[1]
        ok = old.notna() & keys.notna() & suf.notna() & pre.eq(v1.astype(str))
        out["old_combo_id"] = old
        out["combo_id"] = old.where(~ok, keys.astype(str) + "|" + suf)
        stats["combo_ids_reprefixed"] += int(ok.sum())
        stats["combo_ids_kept"] += int((old.notna() & ~ok).sum())
    if name == "paper_1x2.csv" and "row_id" in out.columns:
        from src.pipelines.paper_1x2 import _row_id
        old = (out["old_row_id"] if "old_row_id" in out.columns else out["row_id"]).astype(object)
        out["old_row_id"] = old
        has = keys.notna()
        # paper_1x2's own rule: _row_id(fixture_key, ...) hashes the key when there is one.
        # A row without a v2 key keeps its id (it was already logged under it).
        out["row_id"] = old.where(~has, [_row_id(str(k), "", "", "") if h else None
                                         for k, h in zip(keys, has)])
        stats["row_ids_rekeyed"] += int(has.sum())
    return out


def migrate_records(m: dict, dry_run: bool, base: Path | None = None) -> dict:
    base = base or cfg.OUTPUT_DIR
    rep = {}
    for name in RECORDS:
        p = base / name
        if not p.exists():
            rep[name] = "absent"
            continue
        d = pd.read_csv(p, low_memory=False, dtype=object)
        st = Counter(rows=len(d))
        new = migrate_record(d, name, m, st)
        rep[name] = dict(st)
        print(f"[fk2-migrate] record {name:34} {dict(st)}")
        if not dry_run:
            new.to_csv(p, index=False)
    return rep


def run(season: str | None = None, dry_run: bool = False, out_dir: Path | None = None,
        records: bool = True) -> dict:
    root = cfg.DATA_DIR / (season or cfg.season_label())
    log: dict = {"key_version": fk2.KEY_VERSION, "vocab_version": fk2.VOCAB_VERSION,
                 "vocab_sha256": fk2.VOCAB_SHA256, "season": root.name, "dry_run": dry_run}
    m, unresolved = build_map(root, log)
    amb = {k: v for k, v in m.items() if len(v) > 1}
    log["v1_keys_in_map"] = len(m)
    log["v1_keys_ambiguous"] = len(amb)
    clv = _clv_lookup(log)
    tables: dict = {}
    unmapped = Counter()
    conflict_rows = []
    for t in NAMED + MATCH_NAMED + MAPPED + DEDUPE_ONLY:
        st = Counter()
        files = _files(root, t)
        frames = []
        for i, f in enumerate(files):
            d = pd.read_parquet(f)
            st["rows_before"] += len(d)
            new = d if t in DEDUPE_ONLY else migrate_frame(d, t, m, clv if t == "clv" else None, st)
            new, nd = dedupe_exact(new)
            st["exact_copies_dropped"] += nd
            frames.append(new.assign(_file=i, _changed=(t not in DEDUPE_ONLY) or nd > 0))
        if not frames:
            tables[t] = dict(st)
            continue
        allr = pd.concat(frames, ignore_index=True)
        drop, conf = dedupe_canonical(allr.drop(columns=["_file", "_changed"]), t)
        st["canonical_copies_dropped"] = int(drop.sum())
        st["grain_conflicting_rows"] = int(len(conf))
        if len(conf):
            g = [c for c in GRAIN[t] if c in conf.columns]
            for kv, grp in conf.groupby(g, dropna=False):
                conflict_rows.append({"table": t, "grain": "|".join(g),
                                      "value": "|".join(map(str, kv if isinstance(kv, tuple) else (kv,))),
                                      "rows": int(len(grp))})
        touched = set(allr.loc[drop.to_numpy(), "_file"])
        allr = allr[~drop.to_numpy()]
        st["rows_after"] = int(len(allr))
        if t not in DEDUPE_ONLY:
            bad = allr["fixture_key"].isna()
            for v1 in allr.loc[bad, "old_fixture_key"].dropna().astype(str):
                unmapped[(t, v1)] += 1
        if not dry_run:
            parts = {i: g for i, g in allr.groupby("_file")}
            for i, f in enumerate(files):
                g = parts.get(i)
                if g is None:
                    f.unlink()                      # every row was a stored copy of another
                    st["files_emptied_and_removed"] += 1
                    continue
                if bool(g["_changed"].iloc[0]) or i in touched:
                    g.drop(columns=["_file", "_changed"]).to_parquet(f, index=False)
        tables[t] = dict(st)
        print(f"[fk2-migrate] {t:22} {dict(st)}")
    log["tables"] = tables
    if "scout_results" in tables:
        log["scout_results_name_duplicates"] = scout_name_duplicates(root)
    log["records"] = migrate_records(m, dry_run) if records else "skipped"
    log["unresolved_club_names"] = int(len(unresolved.drop_duplicates(["league", "name"])))
    out = out_dir or (cfg.OUTPUT_DIR / "fixture_key_v2")
    if not dry_run:
        out.mkdir(parents=True, exist_ok=True)
        (out / "migration_report.json").write_text(json.dumps(log, indent=1, default=str) + "\n",
                                                   encoding="utf-8")
        unresolved.to_csv(out / "unresolved_clubs.csv", index=False)
        um = pd.DataFrame([{"table": t, "old_fixture_key": k, "rows": c,
                            "ambiguous_v2": "|".join(sorted(amb[k])) if k in amb else ""}
                           for (t, k), c in sorted(unmapped.items())],
                          columns=["table", "old_fixture_key", "rows", "ambiguous_v2"])
        um.to_csv(out / "unmapped_v1_keys.csv", index=False)
        pd.DataFrame(conflict_rows, columns=["table", "grain", "value", "rows"]).to_csv(
            out / "grain_conflicts.csv", index=False)
    return log


def scout_name_duplicates(root: Path) -> list:
    """scout_results rows that share (match_date, home_team, away_team) under DIFFERENT
    API-Football fixture ids. Listed for the owner; neither id is preferred here."""
    files = _files(root, "scout_results")
    if not files:
        return []
    d = pd.concat([pd.read_parquet(f, columns=["fixture_id", "league_id", "match_date", "home_team",
                                                "away_team"]) for f in files], ignore_index=True)
    d = d.drop_duplicates()
    g = d.groupby(["match_date", "home_team", "away_team"])["fixture_id"].nunique()
    hit = g[g > 1].index
    out = []
    for md, h, a in hit:
        x = d[(d["match_date"] == md) & (d["home_team"] == h) & (d["away_team"] == a)]
        out.append({"match_date": str(md), "home_team": h, "away_team": a,
                    "fixture_ids": sorted(map(str, x["fixture_id"].unique())),
                    "league_ids": sorted(map(str, x["league_id"].unique()))})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Re-key the season warehouse to fixture_key v2")
    ap.add_argument("--season", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    run(a.season, a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
