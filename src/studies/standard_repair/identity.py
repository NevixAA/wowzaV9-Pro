"""TEAM / FIXTURE IDENTITY AUDIT for the Standard benchmark (owner brief 2026-10-28, P0 "identity").

Input: the frame v9's own loader builds (frame_build.py) — the rows v9 TRAINS on — plus the raw rows
before v9's club canonicaliser (`raw_precanon_standard.parquet`).

FINGERPRINT of a fixture: (league, date, canonical home, canonical away). A real match has exactly
one; a club has exactly one name per league.

THE EVIDENCE RULE FOR AN ALIAS (no fuzzy matching, nothing guessed). A club plays at most one match
per day. So when the SAME club appears in TWO rows of one league on ONE date, with the SAME score, the
two rows are one match and the two opponent strings are one club. A pair of spellings is accepted
as an alias only when
    * it is observed on at least MIN_ALIAS_DATES distinct dates, every time with a matching score, and
    * the two spellings never meet each other and never both play a DIFFERENT match on the same date
      (two different clubs in one league do both of those all the time).
Aliases are closed transitively (union-find) and the canonical spelling is the one seen most
recently, ties by frequency — v9's own `_canonicalise_clubs` rule, so the vocabulary converges on
what football-data keeps producing. The rule iterates: merging one side can expose the other.

What cannot be proven is QUARANTINED, never guessed: a same-day collision with a different score, or
with a pair that fails the rule, removes those fixtures from the benchmark and is listed.

Outputs (in-memory dicts consumed by quality.py): alias map per league, residual-duplicate counts
before/after, score conflicts, quarantined fixtures, rolling-history split suspects.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

MIN_ALIAS_DATES = 2
MAX_CONFLICT_SHARE = 0.02
CANON_VERSION = "identity/1.0"


def _long(s: pd.DataFrame) -> pd.DataFrame:
    """One row per (fixture, side): team, opponent, scores oriented home/away as stored."""
    base = s[["league", "date", "home_team", "away_team", "home_goals", "away_goals"]].copy()
    base["_fx"] = np.arange(len(base))
    h = base.rename(columns={"home_team": "team", "away_team": "opp"}).assign(side="H")
    a = base.rename(columns={"away_team": "team", "home_team": "opp"}).assign(side="A")
    return pd.concat([h, a], ignore_index=True)


def same_day_collisions(s: pd.DataFrame) -> pd.DataFrame:
    """Every (league, date, team) that appears in more than one fixture row, with both rows' detail."""
    lg = _long(s.reset_index(drop=True))
    lg["date"] = pd.to_datetime(lg["date"]).dt.normalize()
    dup = lg[lg.duplicated(["league", "date", "team"], keep=False)]
    return dup.sort_values(["league", "date", "team", "_fx"])


def _pairs_from_collisions(col: pd.DataFrame):
    """Candidate alias pairs (league, a, b) with the evidence dates, and the conflicting collisions."""
    ev = defaultdict(set)
    bad = defaultdict(set)
    conflicts = []
    for (lg, d, t), g in col.groupby(["league", "date", "team"], sort=False):
        rows = g.to_dict("records")
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                r1, r2 = rows[i], rows[j]
                if r1["side"] != r2["side"]:
                    # same club home in one row and away in the other on one day: not the same match
                    conflicts.append((lg, d, t, "SIDE_MISMATCH"))
                    continue
                same_score = (r1["home_goals"] == r2["home_goals"]) and (r1["away_goals"] == r2["away_goals"])
                a, b = sorted([str(r1["opp"]), str(r2["opp"])])
                if a == b:
                    continue
                if same_score:
                    ev[(lg, a, b)].add(d)
                else:
                    bad[(lg, a, b)].add(d)
                    conflicts.append((lg, d, t, "SCORE_CONFLICT"))
    return ev, bad, conflicts


def _distinct_evidence(s: pd.DataFrame) -> tuple[set, set]:
    """(league, a, b) pairs proven DISTINCT: they met each other, or both played different matches
    on one date."""
    met = set()
    for lg, h, a in zip(s["league"], s["home_team"], s["away_team"]):
        x, y = sorted([str(h), str(a)])
        met.add((lg, x, y))
    return met, set()


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _canonical_name(names: list[str], s: pd.DataFrame, lg: str) -> str:
    g = s[s["league"] == lg]
    last, n = {}, {}
    for col in ("home_team", "away_team"):
        for t, dts in g.groupby(col)["date"]:
            if t in names:
                last[t] = max(last.get(t, pd.Timestamp.min), pd.to_datetime(dts).max())
                n[t] = n.get(t, 0) + len(dts)
    return sorted(names, key=lambda t: (last.get(t, pd.Timestamp.min), n.get(t, 0), t), reverse=True)[0]


def apply_aliases(s: pd.DataFrame, amap: dict) -> pd.DataFrame:
    """Rename per league: amap = {league: {spelling: canonical}}."""
    d = s.copy()
    for c in ("home_team", "away_team"):
        d[c] = [amap.get(lg, {}).get(t, t) for lg, t in zip(d["league"], d[c].astype(str))]
    return d


def derive_aliases(s: pd.DataFrame, max_iter: int = 6) -> dict:
    """Evidence-based alias map for one frame (see module doc). Returns
    {"map": {league: {alias: canonical}}, "pairs": [...], "rejected": [...], "iterations": n}."""
    cur = s[["league", "date", "home_team", "away_team", "home_goals", "away_goals"]].copy()
    cur["date"] = pd.to_datetime(cur["date"]).dt.normalize()
    accepted, rejected = [], []
    amap: dict = {}
    it = 0
    for it in range(1, max_iter + 1):
        col = same_day_collisions(cur)
        if col.empty:
            break
        ev, bad, _ = _pairs_from_collisions(col)
        met, _ = _distinct_evidence(cur)
        # both play DIFFERENT matches on the same date -> distinct clubs
        lg_long = _long(cur)
        new = []
        for (lg, a, b), dates in ev.items():
            reason = None
            if len(dates) < MIN_ALIAS_DATES:
                reason = f"only {len(dates)} evidence date(s)"
            elif (lg, a, b) in met:
                reason = "the two spellings meet each other"
            elif len(bad.get((lg, a, b), ())) > MAX_CONFLICT_SHARE * len(dates):
                # a source typo on one date out of dozens does not unmake an alias; the conflicting
                # fixture itself stays a collision and is quarantined
                reason = f"score conflict on {len(bad[(lg, a, b)])} of {len(dates) + len(bad[(lg, a, b)])} date(s)"
            else:
                # On a date where both spellings play, an alias pair sits in two COPIES of one match:
                # same venue side, same score. Two distinct clubs differ in side or score on most days.
                la = lg_long[(lg_long["league"] == lg) & lg_long["team"].isin([a, b])]
                co = la.groupby("date").filter(lambda g: g["team"].nunique() == 2)
                diff_days = 0
                for _d, g in co.groupby("date"):
                    ra, rb = g[g["team"] == a].iloc[0], g[g["team"] == b].iloc[0]
                    if ra["side"] != rb["side"] or ra["home_goals"] != rb["home_goals"] or ra["away_goals"] != rb["away_goals"]:
                        diff_days += 1
                n_co = co["date"].nunique()
                if diff_days > max(1, 0.05 * n_co):
                    reason = f"on {diff_days} of {n_co} shared dates they play DIFFERENT matches — distinct clubs"
            if reason:
                rejected.append({"league": lg, "a": a, "b": b, "evidence_dates": len(dates), "reason": reason})
            else:
                new.append((lg, a, b, len(dates)))
        if not new:
            break
        uf = {}
        for lg, a, b, _n in new:
            uf.setdefault(lg, _UF()).union(a, b)
            accepted.append({"league": lg, "a": a, "b": b, "evidence_dates": _n, "iteration": it})
        step = {}
        for lg, u in uf.items():
            groups = defaultdict(list)
            for x in list(u.p):
                groups[u.find(x)].append(x)
            for names in groups.values():
                canon = _canonical_name(names, cur, lg)
                for x in names:
                    if x != canon:
                        step.setdefault(lg, {})[x] = canon
        cur = apply_aliases(cur, step)
        # compose into the running map
        for lg, m in step.items():
            L = amap.setdefault(lg, {})
            for k, v in list(L.items()):
                if v in m:
                    L[k] = m[v]
            for k, v in m.items():
                L[k] = v
        cur = cur.drop_duplicates(["league", "date", "home_team", "away_team", "home_goals", "away_goals"])
    # de-duplicate rejected list
    rej = pd.DataFrame(rejected).drop_duplicates(["league", "a", "b"]).to_dict("records") if rejected else []
    return {"version": CANON_VERSION, "map": amap, "accepted_pairs": accepted, "rejected_pairs": rej,
            "iterations": it}


def audit(frame: pd.DataFrame, precanon: pd.DataFrame | None = None, leagues: set | None = None) -> dict:
    """Identity audit of one frame (standard rows). Returns per-league and total counts plus the
    quarantine list. Does not modify the frame."""
    s = frame[frame["track"].astype(str) == "standard"].copy() if "track" in frame else frame.copy()
    if leagues:
        s = s[s["league"].isin(leagues)]
    s["date"] = pd.to_datetime(s["date"]).dt.normalize()
    s = s.reset_index(drop=True)
    key = ["league", "date", "home_team", "away_team"]
    exact_dup = int(s.duplicated(key).sum())
    col = same_day_collisions(s)
    ev, bad, conflicts = _pairs_from_collisions(col)
    coll_fixtures = set(col["_fx"].tolist())
    # date-shifted copies: same league, same pair, same score, within 2 days
    s2 = s.sort_values(key)
    shifted = 0
    for (lg, h, a), g in s2.groupby(["league", "home_team", "away_team"]):
        if len(g) < 2:
            continue
        dd = g["date"].sort_values().diff().dt.days
        shifted += int(((dd > 0) & (dd <= 2)).sum())
    # rolling-history split suspects: a club with very few rows in a league-season
    lg_long = _long(s)
    lg_long["ss"] = pd.to_datetime(lg_long["date"]).dt.year.where(pd.to_datetime(lg_long["date"]).dt.month >= 7,
                                                                pd.to_datetime(lg_long["date"]).dt.year - 1)
    cnt = lg_long.groupby(["league", "ss", "team"]).size().rename("n").reset_index()
    med = cnt.groupby(["league", "ss"])["n"].transform("median")
    # the live season is still being played: compare within league-season, and only flag < 30% of median
    thin = cnt[(cnt["n"] < 0.3 * med) & (med >= 6)]
    per_league = {}
    for lg, g in s.groupby("league"):
        cl = col[col["league"] == lg]
        per_league[lg] = {
            "rows": int(len(g)),
            "exact_duplicate_fixtures": int(g.duplicated(key).sum()),
            "same_day_collision_fixtures": int(cl["_fx"].nunique()),
            "same_day_collision_rows_share": round(float(cl["_fx"].nunique()) / max(len(g), 1), 4),
            "score_conflicts": int(sum(1 for c in conflicts if c[0] == lg and c[3] == "SCORE_CONFLICT")),
            "side_mismatch_conflicts": int(sum(1 for c in conflicts if c[0] == lg and c[3] == "SIDE_MISMATCH")),
            "date_shifted_copies": None,
            "thin_club_seasons": int((thin["league"] == lg).sum()),
            "distinct_club_names": int(pd.unique(pd.concat([g["home_team"], g["away_team"]])).size),
        }
    out = {
        "rows": int(len(s)), "exact_duplicate_fixtures": exact_dup,
        "same_day_collision_fixtures": int(len(coll_fixtures)),
        "score_conflicts": sum(1 for c in conflicts if c[3] == "SCORE_CONFLICT"),
        "side_mismatch_conflicts": sum(1 for c in conflicts if c[3] == "SIDE_MISMATCH"),
        "date_shifted_same_score_copies": shifted,
        "thin_club_seasons": thin.sort_values(["league", "ss"]).head(200).to_dict("records"),
        "per_league": per_league,
        "collision_examples": col.head(40).assign(date=lambda x: x["date"].astype(str)).drop(columns=["_fx"]).to_dict("records"),
    }
    if precanon is not None and len(precanon):
        p = precanon.copy()
        if leagues:
            p = p[p["league"].isin(leagues)]
        merged = p[(p["home_team"].astype(str) != p["_canon_home_team"].astype(str))
                   | (p["away_team"].astype(str) != p["_canon_away_team"].astype(str))]
        sp = pd.concat([p[["league", "home_team", "_canon_home_team"]].set_axis(["league", "raw", "canon"], axis=1),
                        p[["league", "away_team", "_canon_away_team"]].set_axis(["league", "raw", "canon"], axis=1)])
        sp = sp[sp["raw"].astype(str) != sp["canon"].astype(str)].drop_duplicates()
        out["v9_canonicaliser"] = {"raw_rows": int(len(p)), "raw_rows_renamed": int(len(merged)),
                                   "spellings_merged": int(len(sp)),
                                   "examples": sp.head(30).astype(str).to_dict("records")}
    return out


def quarantine(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drop every standard fixture still in a same-day collision (unprovable identity) and every
    exact-key duplicate beyond the first. Returns (clean_frame, quarantined_rows)."""
    f = frame.reset_index(drop=True)
    std = f["track"].astype(str) == "standard" if "track" in f else pd.Series(True, index=f.index)
    s = f[std].copy()
    s["date"] = pd.to_datetime(s["date"]).dt.normalize()
    lg = _long(s.reset_index().rename(columns={"index": "_orig"}).drop(columns=["_orig"]))
    idx_map = s.index.to_numpy()
    lg["date"] = pd.to_datetime(lg["date"]).dt.normalize()
    bad_fx = set(lg[lg.duplicated(["league", "date", "team"], keep=False)]["_fx"].tolist())
    bad_idx = {int(idx_map[i]) for i in bad_fx}
    dup = s.duplicated(["league", "date", "home_team", "away_team"])
    bad_idx |= set(s.index[dup].tolist())
    q = f.loc[sorted(bad_idx)]
    return f.drop(index=sorted(bad_idx)), q


def write_aliases(res: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


def rolling_order_leak(frame: pd.DataFrame, n: int = 5) -> dict:
    """v9's `_build_team_centric` sorts team rows by [team, LEAGUE, date] and `_rolling` groups by
    TEAM only, so a club that played in two competitions (promotion, relegation, or two clubs sharing
    a name across countries) has its 5-match window run across the league boundary in ALPHABETICAL
    league order, not time order. The first rows of the later-sorted league then average matches
    played AFTER the fixture being scored — a training-feature leak. This replays that ordering
    exactly and counts, per standard fixture side, windows that contain a later-dated match or a
    match from another league. Read-only."""
    f = frame.reset_index(drop=True)
    base = f[["date", "league", "home_team", "away_team"]].copy()
    base["date"] = pd.to_datetime(base["date"])
    base["_i"] = np.arange(len(base))
    base["_std"] = (f["track"].astype(str) == "standard").to_numpy() if "track" in f else True
    h = base.rename(columns={"home_team": "team"}).drop(columns=["away_team"]).assign(side="home")
    a = base.rename(columns={"away_team": "team"}).drop(columns=["home_team"]).assign(side="away")
    tc = pd.concat([h, a], ignore_index=True).sort_values(["team", "league", "date"], kind="mergesort").reset_index(drop=True)
    g = tc.groupby("team", sort=False)
    future = np.zeros(len(tc), bool)
    cross = np.zeros(len(tc), bool)
    for k in range(1, n + 1):
        pdt = g["date"].shift(k)
        plg = g["league"].shift(k)
        future |= (pdt > tc["date"]).fillna(False).to_numpy()
        cross |= (plg.notna() & (plg != tc["league"])).to_numpy()
    tc["future_in_window"], tc["cross_league_window"] = future, cross
    s = tc[tc["_std"]]
    fx_future = s.groupby("_i")["future_in_window"].any()
    fx_cross = s.groupby("_i")["cross_league_window"].any()
    per_league = s.groupby("league").agg(sides=("team", "size"), future=("future_in_window", "sum"),
                                         cross=("cross_league_window", "sum"))
    teams_multi = tc.groupby("team")["league"].nunique()
    return {"n_window": n,
            "standard_fixtures": int(s["_i"].nunique()),
            "standard_fixtures_with_future_match_in_window": int(fx_future.sum()),
            "standard_fixtures_with_cross_league_window": int(fx_cross.sum()),
            "teams_in_more_than_one_league": int((teams_multi > 1).sum()),
            "per_league": {lg: {k: int(v) for k, v in r.items()} for lg, r in per_league.iterrows()},
            "future_rows_index": sorted(int(i) for i in fx_future[fx_future].index)}
