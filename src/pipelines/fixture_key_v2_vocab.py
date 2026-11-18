"""
Build the FROZEN club vocabulary behind fixture_key v2 (run once per VOCAB_VERSION).
===================================================================================
    python -m src.pipelines.fixture_key_v2_vocab            (needs V9_LOCAL -> wowza-betting)

The vocabulary is v9's OWN canonical club identity, not a Pro invention:

  source   v9 output/fd_history.parquet + output/af_history.parquet (the history bank v9 trains
           on and resolves predict names against), league names through v9's registry.
  stage 1  v9 data_loader._canonicalise_clubs (Pro's verified port,
           src/data/canonical_identity.unify_affix_spellings).
  stage 2  v9 data_loader._canonical_identity_and_seasons, identity part: v9
           identity_repair.canonicalise_and_dedupe(derive=True) with the one-side same-day aliases
           (v9 data_loader._one_side_aliases, ported verbatim below) and the registry's
           same_club_spellings - exactly the order v9's loader runs.

Leagues the history bank does not hold (top flights, European cups, the World Cup) take their
names from Pro's own team_match_stats (API-Football's spellings) through stage 1 only; the source
is recorded per league. A league in neither source has NO vocabulary, so every club in it stays
CLUB_UNRESOLVED - listed, never guessed.

Vocabulary entries that v9's resolver pairs with ANOTHER entry of the same league are listed as
possible duplicate identities (`possible_duplicates`) for the identity-map owner. They are NOT
merged here: merging is v9's identity decision.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg  # noqa: E402
from src.data import canonical_identity as CI  # noqa: E402
from src.data import fixture_key_v2 as fk2  # noqa: E402
from src.data import season_store as store  # noqa: E402
from src.data import v9_config  # noqa: E402
from src.data.v9_source import v9_head_sha  # noqa: E402


def _v9_identity_repair():
    """v9's src/identity_repair.py loaded by path, with `_same_club` bound to v9's resolver loaded
    the same way (its own `from src.team_names import resolve` would hit Pro's `src`)."""
    p = cfg.V9_LOCAL / "src" / "identity_repair.py"
    spec = importlib.util.spec_from_file_location("_v9_identity_repair_via_pro", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    resolve = v9_config.team_names().resolve
    mod._same_club = lambda x, y: resolve(x, [y]) == y or resolve(y, [x]) == x
    return mod


def _one_side_aliases(df: pd.DataFrame, same_club, min_dates: int = 3) -> dict:
    """Verbatim port of v9 src/data_loader._one_side_aliases (2026-11-01)."""
    d = df[df["home_goals"].notna() & df["away_goals"].notna()].copy()
    d["_d"] = pd.to_datetime(d["date"]).dt.normalize()
    ev: dict = defaultdict(Counter)
    for (lg, dt, _hg, _ag), g in d.groupby(["league", "_d", "home_goals", "away_goals"], sort=False):
        if len(g) < 2:
            continue
        rows = list(zip(g["home_team"].astype(str), g["away_team"].astype(str)))
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                (h1, a1), (h2, a2) = rows[i], rows[j]
                if (h1 == h2) != (a1 == a2):
                    x, y = (a1, a2) if h1 == h2 else (h1, h2)
                    ev[lg][(tuple(sorted((x, y))), dt)] += 1
    last = pd.concat([d[["league", "home_team", "_d"]].rename(columns={"home_team": "t"}),
                      d[["league", "away_team", "_d"]].rename(columns={"away_team": "t"})]
                     ).groupby(["league", "t"])["_d"].max().to_dict()
    met = defaultdict(set)
    for lg, h, a in zip(d["league"], d["home_team"].astype(str), d["away_team"].astype(str)):
        met[lg].add(tuple(sorted((h, a))))
    out: dict = {}
    for lg, cnt in ev.items():
        dates = Counter(k for (k, _dt) in cnt)
        strong = [(k, n) for k, n in dates.items() if n >= min_dates and k not in met[lg]
                  and same_club(*k)]
        partners: dict = defaultdict(list)
        for (x, y), n in strong:
            partners[x].append((n, y))
            partners[y].append((n, x))
        m = {}
        for (x, y), n in strong:
            if max(partners[x])[1] != y or max(partners[y])[1] != x:
                continue
            canon, alias = sorted((x, y), key=lambda t: (last.get((lg, t), pd.Timestamp(0)), t),
                                  reverse=True)
            m[alias] = canon
        if m:
            out[lg] = m
    return out


def _bank() -> tuple[pd.DataFrame, list]:
    out, dropped = [], []
    for name, gh, ga in (("fd_history", "home_goals", "away_goals"), ("af_history", "FTHG", "FTAG")):
        p = cfg.V9_LOCAL / "output" / f"{name}.parquet"
        d = pd.read_parquet(p)
        d = d.rename(columns={gh: "home_goals", ga: "away_goals"})
        d = d[["date", "league", "home_team", "away_team", "home_goals", "away_goals"]].copy()
        canon = d["league"].map(lambda x: v9_config.canonical_league(x))
        for lg in sorted(set(d.loc[canon.isna(), "league"].astype(str))):
            dropped.append({"source": name, "league": lg, "reason": "league unknown to the registry"})
        d = d[canon.notna()].assign(league=canon[canon.notna()])
        out.append(d)
    b = pd.concat(out, ignore_index=True)
    b["date"] = pd.to_datetime(b["date"], format="%Y-%m-%d", errors="coerce")
    bad = int(b["date"].isna().sum())
    if bad:
        dropped.append({"source": "history_bank", "league": "*", "reason": f"{bad} row(s) with a date not in %Y-%m-%d"})
    return b.dropna(subset=["date"]), dropped


def build() -> dict:
    LR = v9_config.league_registry()
    ir = _v9_identity_repair()
    bank, dropped = _bank()
    st1, rep1 = CI.unify_affix_spellings(bank)
    one_side = _one_side_aliases(st1, ir._same_club)
    _last = pd.concat([st1[["league", "home_team", "date"]].rename(columns={"home_team": "t"}),
                       st1[["league", "away_team", "date"]].rename(columns={"away_team": "t"})]
                      ).groupby(["league", "t"])["date"].max().to_dict()
    for lg in sorted(set(st1["league"].astype(str))):
        for x, y in LR.same_club_spellings(lg):
            if (lg, x) in _last and (lg, y) in _last:
                canon, alias = sorted((x, y), key=lambda t: _last[(lg, t)], reverse=True)
                one_side.setdefault(lg, {})[alias] = canon
    st2, rep2 = ir.canonicalise_and_dedupe(st1, alias_map=one_side)
    leagues: dict = {}
    source: dict = {}
    for lg, g in st2.groupby("league"):
        leagues[str(lg)] = sorted(set(g["home_team"].astype(str)) | set(g["away_team"].astype(str)))
        source[str(lg)] = "v9 history bank (fd_history + af_history), v9 identity pipeline"

    tms = store.read("team_match_stats")
    if not tms.empty:
        tms = tms.assign(league=tms["league"].map(lambda x: v9_config.canonical_league(x)),
                         date=tms["match_date"])
        tms = tms[tms["league"].notna() & ~tms["league"].isin(list(leagues))]
        if not tms.empty:
            t1, _ = CI.unify_affix_spellings(
                tms[["date", "league", "home_team", "away_team", "home_goals", "away_goals"]])
            for lg, g in t1.groupby("league"):
                leagues[str(lg)] = sorted(set(g["home_team"].astype(str)) | set(g["away_team"].astype(str)))
                source[str(lg)] = "Pro team_match_stats (API-Football names), stage 1 only"

    resolve = v9_config.team_names().resolve
    dupes = []
    for lg, names in leagues.items():
        for n in names:
            hit = resolve(n, [x for x in names if x != n])
            if hit is not None:
                dupes.append({"league": lg, "name": n, "resolver_pairs_with": hit})
    return {
        "version": fk2.VOCAB_VERSION,
        "built_from": {
            "v9_commit": v9_head_sha(),
            "stage1": rep1,
            "stage2": {k: v for k, v in rep2.items() if k not in ("quarantine", "aliases")},
            "one_side_and_registry_aliases": {lg: dict(sorted(m.items())) for lg, m in sorted(one_side.items())},
            "dropped": dropped,
        },
        "league_source": dict(sorted(source.items())),
        "possible_duplicates": dupes,
        "leagues": {k: leagues[k] for k in sorted(leagues)},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=str(fk2.VOCAB_PATH))
    a = ap.parse_args(argv)
    v = build()
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"[fk2-vocab] {len(v['leagues'])} league(s), "
          f"{sum(len(x) for x in v['leagues'].values())} club name(s), "
          f"{len(v['possible_duplicates'])} possible duplicate(s) -> {p}")
    print(f"[fk2-vocab] sha256 {fk2.vocab_sha256(v['leagues'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
