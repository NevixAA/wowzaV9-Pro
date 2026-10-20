"""v9's O/U training frame with club ALIASES MERGED before features are built (owner 2026-10-19).

Run with cwd = a wowza-betting checkout and v9's interpreter:

    python canonical_names_probe.py --out frame_canonical.parquet --aliases aliases.json

v9 stores the same match twice when football-data and the API-Football bank spell a club
differently, so each spelling carries only part of the club's history and its rolling form is built
from an incomplete record. This probe:
  1. finds alias pairs from EVIDENCE only: two rows, same league, same date, same score, and both
     clubs matching by identity tokens — a same-match copy, never a guess from names alone;
  2. maps every alias to one canonical spelling per league (the most frequent one);
  3. drops the now-exact duplicate rows and builds features with v9's own builder.
READ-ONLY against v9.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

_GENERIC = {"fc", "cf", "sc", "afc", "cd", "ac", "ss", "as", "us", "if", "fk", "sk", "bk", "club",
            "cp", "sd", "de", "la", "el", "the", "ca", "cs", "ud", "rc", "fsv", "sv", "vfl", "vfb",
            "tsg", "bsc", "ifk", "calcio", "1"}
_ALIAS = {"utd": "united", "jrs": "juniors", "jr": "juniors", "dep": "deportivo",
          "atl": "atletico", "ind": "independiente", "est": "estudiantes", "gimn": "gimnasia"}


def _toks(name) -> set:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return {(_ALIAS.get(t, t)) for t in s.split() if t and _ALIAS.get(t, t) not in _GENERIC and not t.isdigit()}


def same_club(a, b) -> bool:
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return all(any(t == o or (len(t) >= 3 and o.startswith(t)) or (len(o) >= 3 and t.startswith(o))
                   for o in big) for t in small)


def find_aliases(raw):
    """league -> {alias: canonical}, from same-match evidence only."""
    import pandas as pd
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    d = raw.dropna(subset=["home_goals", "away_goals"])
    for _, g in d.groupby(["league", "date", "home_goals", "away_goals"], sort=False):
        if len(g) < 2:
            continue
        rows = list(zip(g["home_team"], g["away_team"]))
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                (h1, a1), (h2, a2) = rows[i], rows[j]
                if (h1, a1) != (h2, a2) and same_club(h1, h2) and same_club(a1, a2):
                    lg = g["league"].iloc[0]
                    union((lg, h1), (lg, h2))
                    union((lg, a1), (lg, a2))
    freq = Counter()
    for lg, h, a in zip(raw["league"], raw["home_team"], raw["away_team"]):
        freq[(lg, h)] += 1
        freq[(lg, a)] += 1
    groups = {}
    for node in list(parent):
        root = find(node)
        groups.setdefault(root, {root}).add(node)       # the root is never a key of `parent`
    out = {}
    for members in groups.values():
        canon = max(members, key=lambda m: freq[m])
        for m in members:
            if m != canon:
                out.setdefault(m[0], {})[m[1]] = canon[1]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--aliases", required=True)
    a = ap.parse_args()
    import pandas as pd
    import config
    from src.data_loader import load_all_matches
    from src.feature_engineering import build_features

    raw = load_all_matches()
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    if config.EXCLUDE_COVID_SEASONS:
        raw = raw[~raw["season"].isin(config.COVID_SEASONS)]
    aliases = find_aliases(raw)
    n_alias = sum(len(v) for v in aliases.values())
    for col in ("home_team", "away_team"):
        raw[col] = [aliases.get(lg, {}).get(t, t) for lg, t in zip(raw["league"], raw[col])]
    before = len(raw)
    # COALESCE the copies rather than keeping one: the two sources carry different fields (the
    # API-Football bank often lacks corners/fouls, football-data lacks xG), and keeping an arbitrary
    # copy threw away the fuller one (corners NaN 23.1% -> 27.8%). groupby().first() takes each
    # column's first NON-NULL value across the copies.
    keys = ["league", "date", "home_team", "away_team"]
    dup = raw.duplicated(keys, keep=False)
    if dup.any():
        merged = raw[dup].groupby(keys, sort=False, as_index=False).first()
        raw = pd.concat([raw[~dup], merged], ignore_index=True).sort_values("date", kind="mergesort")
    feat = build_features(raw)
    valid = feat.dropna(subset=["over25", "home_scored_last5"]).copy()
    valid["track"] = valid["league"].map(
        lambda l: "standard" if l in config.STANDARD_FORMAT_LEAGUES
        else "new_format" if l in config.NEW_FORMAT_LEAGUES else "other")
    keep = [c for c in valid.columns if valid[c].dtype.kind in "fiub" or c in
            ("date", "league", "season", "home_team", "away_team", "track")]
    valid[keep].to_parquet(a.out, index=False)
    Path(a.aliases).write_text(json.dumps({"aliases": aliases, "n_aliases": n_alias,
                                           "raw_rows_before": before, "raw_rows_after": len(raw),
                                           "frame_rows": len(valid)}, indent=1, default=str),
                               encoding="utf-8")
    print("aliases", n_alias, "raw", before, "->", len(raw), "frame", len(valid))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
