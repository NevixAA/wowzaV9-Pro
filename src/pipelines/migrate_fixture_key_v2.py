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


def build_map(root: Path, log: dict) -> tuple[dict, pd.DataFrame]:
    """v1 -> {v2: status} from every named row, plus the unresolved-club listing."""
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
            for a, b, s in zip(v1, k["fixture_key"], k["fixture_key_status"]):
                if a is not None and not pd.isna(a) and b is not None:
                    m[str(a)][b] = s
            for _, r in fk2.unresolved_names(nm).iterrows():
                unres[(t, r["league"], r["name"])] += int(r["rows"])
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

    if table == "clv" and "match_date" in out.columns:
        out["match_date"] = out["match_date"].map(fk2.match_day).astype(object)
    return out


def dedupe_exact(d: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop rows that are exact copies (every column) of an earlier row of the same frame."""
    h = pd.util.hash_pandas_object(d.astype(str), index=False)
    dup = h.duplicated(keep="first")
    return d[~dup.to_numpy()], int(dup.sum())


def grain_conflicts(d: pd.DataFrame, table: str) -> int:
    g = [c for c in GRAIN.get(table, []) if c in d.columns]
    if not g or d.empty:
        return 0
    x = d.dropna(subset=[g[0]])
    return int(x.duplicated(subset=g, keep=False).sum())


def run(season: str | None = None, dry_run: bool = False, out_dir: Path | None = None) -> dict:
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
    for t in NAMED + MATCH_NAMED + MAPPED + DEDUPE_ONLY:
        st = Counter()
        conflicts = 0
        for f in _files(root, t):
            d = pd.read_parquet(f)
            st["rows_before"] += len(d)
            new = d if t in DEDUPE_ONLY else migrate_frame(d, t, m, clv if t == "clv" else None, st)
            new, nd = dedupe_exact(new)
            st["exact_copies_dropped"] += nd
            st["rows_after"] += len(new)
            conflicts += grain_conflicts(new, t)
            if t not in DEDUPE_ONLY:
                bad = new["fixture_key"].isna()
                for v1 in new.loc[bad, "old_fixture_key"].dropna().astype(str):
                    unmapped[(t, v1)] += 1
            if not dry_run and (t not in DEDUPE_ONLY or nd):
                new.to_parquet(f, index=False)
        st["grain_conflicting_rows"] = conflicts
        tables[t] = dict(st)
        print(f"[fk2-migrate] {t:22} {dict(st)}")
    log["tables"] = tables
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
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Re-key the season warehouse to fixture_key v2")
    ap.add_argument("--season", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    run(a.season, a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
