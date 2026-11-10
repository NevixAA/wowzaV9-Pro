"""Scout Data Truth — the ONE reader every scout evaluation goes through (audit 2026-11-10).

The raw season-store tables are append-only and are never rewritten. Every correction is applied
HERE, beside the committed rows, so the report, the league status, the hypotheses, the promotion
review and the regression harness all see the same served truth:

  results        one row per fixture (latest ingest); finished only; AET / PEN on the 90-minute score
                 (score.fulltime, owner settlement rule) from the row itself or from the
                 scout_results_ft90 correction table — and MISSING when neither has it, never the
                 120-minute `goals`; club names = the latest provider name per team id, trimmed.
  odds           one row per (fixture, market, selection, book, snapshot): identical repeats collapse,
                 a key with two different prices is dropped whole (ambiguous, not picked).
  close          the hypotheses rule, everywhere: the last quote before the ACTUAL kickoff per key,
                 observed at most CRITERIA.genuine_close.max_minutes_before_kickoff before it;
                 Pinnacle, else the cross-book median with >= 3 books.
  model          the first frozen row per fixture, frozen before the ACTUAL kickoff, with real
                 probabilities (no UNKNOWN_TEAM), not FEATURE_DEGRADED, and the SAME league, home and
                 away team ids as the result (the provider has re-used a fixture id for another
                 matchup after the freeze).
  reschedule     a fixture whose kickoff moved more than 48 h from the kickoff the scout priced is
                 VOID (owner settlement rule 2026-11): no close, no model, no result in any score.

Nothing here invents a value: a fixture that fails a rule is left out and counted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.scout import parse

#: Owner settlement rule (memory: settlement-decisions): a kickoff moved > 48 h voids the bet.
RESCHEDULE_VOID_HOURS = 48
#: Owner audit brief 2026-11-10: a result is due by kickoff + 3 h ...
RESULT_GRACE_HOURS = 3
#: ... and a league in season with no update for > 10 days is stale.
STALE_DAYS = 10
SIDE = {"ou15": ("over", "under"), "ou25": ("over", "under"), "ou35": ("over", "under"),
        "btts": ("yes", "no")}
MODEL_COL = {"ou15": "p_ou15_over", "ou25": "p_ou25_over", "ou35": "p_ou35_over",
             "btts": "p_btts_yes"}
ODDS_KEY = list(parse.ODDS_KEY)
DEGRADED_FLAGS = ("FEATURE_DEGRADED", "UNKNOWN_TEAM")


def close_max_minutes() -> float:
    """The genuine-close age limit, read from the frozen hypotheses criteria (never typed twice)."""
    from src.scout.hypotheses import CRITERIA
    return float(CRITERIA["genuine_close"]["max_minutes_before_kickoff"])


def outcome(market: str, hg, ag):
    tg = hg + ag
    return {"ou15": tg > 1.5, "ou25": tg > 2.5, "ou35": tg > 3.5,
            "btts": (hg > 0) & (ag > 0)}[market].astype(float)


_EPOCH0 = pd.Timestamp("1970-01-01", tz="UTC")


def _epoch(s) -> pd.Series:
    """ISO timestamps -> epoch seconds (float; missing stays NaN). Resolution-safe: pandas may hold
    datetimes in s / ms / us / ns, so never cast the raw int64."""
    t = pd.to_datetime(pd.Series(s), utc=True, errors="coerce")
    return (t - _EPOCH0).dt.total_seconds()


# ── results ──────────────────────────────────────────────────────────────────────────────────
def canonical_names(raw: pd.DataFrame) -> dict:
    """{team_id: latest provider name, trimmed} over every stored result row (Data Truth R14)."""
    if raw is None or raw.empty or "home_id" not in raw.columns:
        return {}
    order = [c for c in ("kickoff_ts", "ingested_at") if c in raw.columns]
    parts = []
    for side in ("home", "away"):
        if f"{side}_team" not in raw.columns:
            continue
        p = raw[[f"{side}_id", f"{side}_team"] + order].rename(
            columns={f"{side}_id": "id", f"{side}_team": "name"})
        parts.append(p)
    if not parts:
        return {}
    t = pd.concat(parts, ignore_index=True).dropna(subset=["id", "name"])
    t["name"] = t["name"].astype(str).str.strip()
    t = t[t["name"] != ""]
    if order:
        t = t.sort_values(order, kind="mergesort")
    return {int(k): v for k, v in t.drop_duplicates("id", keep="last").set_index("id")["name"].items()}


def results(raw: pd.DataFrame, ft90: pd.DataFrame | None = None) -> pd.DataFrame:
    """Served results: one row per fixture, finished only, 90-minute goals, canonical names.

    A row of an AET / PEN fixture that does not carry its 90-minute score keeps the original in
    `goals_home_api` / `goals_away_api` and gets MISSING home/away goals unless the ft90 correction
    table has the provider's score.fulltime for it."""
    if raw is None or raw.empty:
        return pd.DataFrame() if raw is None else raw
    r = raw.copy()
    if "ingested_at" in r.columns:
        r = r.sort_values("ingested_at", kind="mergesort")
    r = r.drop_duplicates("fixture_id", keep="last")
    if "status" in r.columns:
        r = r[r["status"].isin(parse.FINISHED)]
    for c in ("home_goals", "away_goals"):
        r[c] = pd.to_numeric(r[c], errors="coerce")
    if "status" in r.columns:
        basis = r["goals_basis"] if "goals_basis" in r.columns else pd.Series(None, index=r.index, dtype=object)
        et = r["status"].isin(parse.EXTRA_TIME) & (basis.astype(str) != "fulltime_90")
        if et.any():
            if "goals_home_api" not in r.columns:
                r["goals_home_api"], r["goals_away_api"] = np.nan, np.nan
            keep_api = et & r["goals_home_api"].isna()
            r.loc[keep_api, "goals_home_api"] = r.loc[keep_api, "home_goals"]
            r.loc[keep_api, "goals_away_api"] = r.loc[keep_api, "away_goals"]
            fh = fa = pd.Series(dtype=float)
            if ft90 is not None and not ft90.empty:
                f = ft90.sort_values("ingested_at", kind="mergesort") if "ingested_at" in ft90.columns else ft90
                f = f.dropna(subset=["ft90_home", "ft90_away"]).drop_duplicates("fixture_id", keep="last")
                fh = f.set_index("fixture_id")["ft90_home"]
                fa = f.set_index("fixture_id")["ft90_away"]
            r.loc[et, "home_goals"] = pd.to_numeric(r.loc[et, "fixture_id"].map(fh), errors="coerce")
            r.loc[et, "away_goals"] = pd.to_numeric(r.loc[et, "fixture_id"].map(fa), errors="coerce")
            r["goals_basis"] = basis
            r.loc[et, "goals_basis"] = np.where(r.loc[et, "home_goals"].notna(), "fulltime_90_corrected",
                                                "missing_90")
    names = canonical_names(raw)
    if names:
        for side in ("home", "away"):
            if f"{side}_id" in r.columns:
                mapped = r[f"{side}_id"].map(lambda x: names.get(int(x)) if pd.notna(x) else None)
                r[f"{side}_team"] = mapped.where(mapped.notna(), r.get(f"{side}_team"))
    return r


# ── odds ─────────────────────────────────────────────────────────────────────────────────────
def clean_odds(odds: pd.DataFrame) -> pd.DataFrame:
    """One row per (fixture, market, selection, book, snapshot); conflicting keys dropped."""
    if odds is None or odds.empty:
        return pd.DataFrame() if odds is None else odds
    o = odds.drop_duplicates(ODDS_KEY + ["odds"])
    n = o.groupby(ODDS_KEY)["odds"].transform("size")
    return o[n == 1]


def odds_duplicates(odds: pd.DataFrame) -> dict:
    if odds is None or odds.empty:
        return {"dup_groups": 0, "dup_rows": 0, "conflict_groups": 0, "conflict_fixtures": 0}
    d = odds[odds.duplicated(ODDS_KEY, keep=False)]
    g = d.groupby(ODDS_KEY)["odds"].nunique()
    conf = g[g > 1]
    return {"dup_groups": int(len(g)), "dup_rows": int(len(d)), "conflict_groups": int(len(conf)),
            "conflict_fixtures": int(len({k[0] for k in conf.index}))}


def fair_prob(q: pd.DataFrame) -> pd.DataFrame:
    """Proportional de-vig of each (fixture, market, book) pair -> P(first side)."""
    if q is None or q.empty:
        return pd.DataFrame(columns=["fixture_id", "market", "bookmaker", "p", "odds_first"])
    w = q.pivot_table(index=["fixture_id", "market", "bookmaker"], columns="selection",
                      values="odds", aggfunc="last").reset_index()
    rows = []
    for m, (a, b) in SIDE.items():
        s = w[w["market"] == m]
        if s.empty or a not in s or b not in s:
            continue
        s = s.dropna(subset=[a, b])
        ia, ib = 1 / s[a], 1 / s[b]
        rows.append(pd.DataFrame({"fixture_id": s["fixture_id"], "market": m,
                                  "bookmaker": s["bookmaker"], "p": ia / (ia + ib),
                                  "odds_first": s[a]}))
    return (pd.concat(rows, ignore_index=True) if rows
            else pd.DataFrame(columns=["fixture_id", "market", "bookmaker", "p", "odds_first"]))


def genuine_close(odds: pd.DataFrame, kickoff: pd.Series) -> pd.DataFrame:
    """Reference close per (fixture, market): fixture_id, market, p_close, close_book, close_minutes.

    `kickoff`: {fixture_id: ACTUAL kickoff epoch} (the result's). Quotes at or after it are not
    pre-match; the last quote before it per key must be at most close_max_minutes() old."""
    cols = ["fixture_id", "market", "p_close", "close_book", "close_minutes"]
    if odds is None or odds.empty or kickoff is None or len(kickoff) == 0:
        return pd.DataFrame(columns=cols)
    o = clean_odds(odds)
    o = o[o["fixture_id"].isin(kickoff.index)].copy()
    if o.empty:
        return pd.DataFrame(columns=cols)
    o["_snap"] = _epoch(o["snapshot_ts"])
    o["_ko"] = o["fixture_id"].map(kickoff).astype(float)
    o = o[o["_snap"] < o["_ko"]].sort_values("_snap", kind="mergesort")
    last = o.drop_duplicates(["fixture_id", "market", "selection", "bookmaker"], keep="last").copy()
    last["close_minutes"] = (last["_ko"] - last["_snap"]) / 60.0
    last = last[last["close_minutes"] <= close_max_minutes()]
    flags = last["quality_flags"].fillna("") if "quality_flags" in last.columns else pd.Series("", index=last.index)
    ok = (last["bookmaker"] == "pinnacle") | ((last["bookmaker"] == "median")
                                             & ~flags.astype(str).str.contains("INSUFFICIENT_BOOKS"))
    last = last[ok]
    fair = fair_prob(last)
    if fair.empty:
        return pd.DataFrame(columns=cols)
    age = last.groupby(["fixture_id", "market", "bookmaker"])["close_minutes"].max()
    fair = fair.join(age, on=["fixture_id", "market", "bookmaker"])
    fair["rank"] = (fair["bookmaker"] != "pinnacle").astype(int)
    ref = fair.sort_values("rank", kind="mergesort").drop_duplicates(["fixture_id", "market"])
    return ref.rename(columns={"p": "p_close", "bookmaker": "close_book"})[cols].reset_index(drop=True)


# ── model ────────────────────────────────────────────────────────────────────────────────────
def first_freeze(mdl: pd.DataFrame) -> pd.DataFrame:
    if mdl is None or mdl.empty:
        return pd.DataFrame() if mdl is None else mdl
    return mdl.sort_values("frozen_ts", kind="mergesort").drop_duplicates("fixture_id", keep="first")


def model_ok(m0: pd.DataFrame) -> pd.Series:
    """Rows of a first-freeze frame with a REAL prediction (Data Truth R9)."""
    ok = pd.Series(True, index=m0.index)
    if "quality_flags" in m0.columns:
        f = m0["quality_flags"].fillna("").astype(str)
        for flag in DEGRADED_FLAGS:
            ok &= ~f.str.contains(flag)
    for c in ("home_games", "away_games"):                 # the pre-fix 1.0 stand-in rows
        if c in m0.columns:
            ok &= pd.to_numeric(m0[c], errors="coerce").fillna(0) > 0
    return ok


# ── the settled evaluation frame ─────────────────────────────────────────────────────────────
def settled(res_raw: pd.DataFrame, odds: pd.DataFrame, mdl: pd.DataFrame | None,
            ft90: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per settled fixture x market that has a GENUINE close, with the frozen model's
    probability where an eligible one exists (else p_model missing). attrs['excluded'] counts
    what was left out and why."""
    cols = ["fixture_id", "league_id", "market", "kickoff_ts", "matchday", "home_id", "away_id",
            "home_goals", "away_goals", "y", "p_close", "close_book", "close_minutes", "p_model",
            "frozen_ts"]
    out = pd.DataFrame(columns=cols)
    out.attrs["excluded"] = {}
    r = results(res_raw, ft90)
    if r is None or r.empty or odds is None or odds.empty:
        return out
    exc = {"aet_pen_missing_90": int((r.get("goals_basis", pd.Series(dtype=object)) == "missing_90").sum())}
    r = r.dropna(subset=["home_goals", "away_goals", "kickoff_ts"])
    if "league_id" in odds.columns:                         # a quote must belong to the result's league
        ol = odds.drop_duplicates("fixture_id").set_index("fixture_id")["league_id"]
        bad = r["fixture_id"].map(ol)
        mism = bad.notna() & (bad != r["league_id"])
        exc["odds_league_mismatch"] = int(mism.sum())
        r = r[~mism]
    ko = r.set_index("fixture_id")["kickoff_ts"].astype(float)
    # stated kickoff = what the scout priced / froze against
    stated = pd.Series(dtype=float)
    if "kickoff_ts" in odds.columns:
        stated = odds.assign(_s=_epoch(odds["snapshot_ts"])).sort_values("_s", kind="mergesort") \
            .drop_duplicates("fixture_id").set_index("fixture_id")["kickoff_ts"].astype(float)
    m0 = first_freeze(mdl) if mdl is not None else pd.DataFrame()
    if not m0.empty and "kickoff_ts" in m0.columns:
        stated = m0.set_index("fixture_id")["kickoff_ts"].astype(float).combine_first(stated)
    moved = (ko - stated.reindex(ko.index)).abs() > RESCHEDULE_VOID_HOURS * 3600
    void = set(ko.index[moved.fillna(False)])
    exc["rescheduled_void"] = len(void)
    r = r[~r["fixture_id"].isin(void)]
    ko = ko[~ko.index.isin(void)]
    close = genuine_close(odds, ko)
    priced = set(odds["fixture_id"]) & set(r["fixture_id"])
    exc["settled_priced"] = len(priced)
    exc["settled_genuine_close"] = int(close["fixture_id"].nunique())
    exc["settled_stale_or_thin_close"] = len(priced - set(close["fixture_id"]))
    if close.empty:
        out.attrs["excluded"] = exc
        return out
    # eligible model rows: identity, frozen before ACTUAL kickoff, real prediction
    mod = pd.DataFrame(columns=["fixture_id"])
    if not m0.empty:
        need = {"league_id", "home_id", "away_id", "frozen_ts"}
        if need <= set(m0.columns):
            j = m0.merge(r[["fixture_id", "league_id", "home_id", "away_id", "kickoff_ts"]],
                         on="fixture_id", suffixes=("", "_r"))
            ident = ((j["league_id"].astype(float) == j["league_id_r"].astype(float))
                     & (j["home_id"].astype(float) == j["home_id_r"].astype(float))
                     & (j["away_id"].astype(float) == j["away_id_r"].astype(float)))
            before = _epoch(j["frozen_ts"]) < j["kickoff_ts_r"].astype(float)
            ok = model_ok(j)
            exc["model_identity_mismatch"] = int((~ident).sum())
            exc["model_frozen_after_actual_kickoff"] = int((ident & ~before).sum())
            exc["model_not_eligible"] = int((ident & before & ~ok).sum())
            mod = j[ident & before & ok]
        else:
            exc["model_missing_identity_columns"] = int(len(m0))
    rows = []
    rr = r.set_index("fixture_id")
    for m in SIDE:
        c = close[close["market"] == m].set_index("fixture_id")
        if c.empty:
            continue
        x = rr[["league_id", "kickoff_ts", "home_id", "away_id", "home_goals", "away_goals"]].join(
            c[["p_close", "close_book", "close_minutes"]], how="inner")
        col = MODEL_COL[m]
        if len(mod) and col in mod.columns:
            pm = mod.set_index("fixture_id")[[col, "frozen_ts"]].rename(columns={col: "p_model"})
            x = x.join(pm, how="left")
        else:
            x["p_model"], x["frozen_ts"] = np.nan, None
        x["p_model"] = pd.to_numeric(x["p_model"], errors="coerce")
        x["y"] = outcome(m, x["home_goals"].astype(float), x["away_goals"].astype(float))
        x["market"] = m
        x["matchday"] = pd.to_datetime(x["kickoff_ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
        rows.append(x.reset_index())
    if rows:
        out = pd.concat(rows, ignore_index=True)
        out["league_id"] = out["league_id"].astype(int)
        out = out[cols]
    out.attrs["excluded"] = exc
    return out


def base_rate_before(res: pd.DataFrame, league_id: int, market: str, cutoff: pd.Series) -> pd.Series:
    """League base rate of `market` from results kicking off strictly BEFORE each cutoff epoch
    (Data Truth R11). Missing when the league has no earlier result."""
    r = res[(res["league_id"] == league_id)].dropna(subset=["home_goals", "away_goals", "kickoff_ts"])
    r = r.sort_values("kickoff_ts")
    if r.empty:
        return pd.Series(np.nan, index=cutoff.index)
    y = outcome(market, r["home_goals"].astype(float), r["away_goals"].astype(float)).to_numpy()
    cs = np.concatenate([[0.0], np.cumsum(y)])
    k = np.searchsorted(r["kickoff_ts"].astype(float).to_numpy(), cutoff.astype(float).to_numpy(), side="left")
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.where(k > 0, cs[k] / np.maximum(k, 1), np.nan)
    return pd.Series(rate, index=cutoff.index)


# ── the audit counts (health output, promotion data quality) ─────────────────────────────────
def audit(res_raw: pd.DataFrame, odds: pd.DataFrame, mdl: pd.DataFrame,
          ft90: pd.DataFrame | None = None, status: pd.DataFrame | None = None,
          now: pd.Timestamp | None = None) -> dict:
    """Every Data Truth count, on the RAW tables. Pure; pass one league's slices for a league."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    out: dict = {}
    raw = res_raw if res_raw is not None else pd.DataFrame()
    if len(raw):
        g = raw.groupby("fixture_id")
        n = g.size()
        out["result_rows"] = int(len(raw))
        out["result_fixtures"] = int(len(n))
        out["result_duplicate_fixtures"] = int((n > 1).sum())
        keycols = [c for c in ("home_goals", "away_goals", "kickoff_ts", "league_id", "home_id", "away_id")
                   if c in raw.columns]
        dup = raw[raw["fixture_id"].isin(n[n > 1].index)]
        conf = dup.groupby("fixture_id")[keycols].nunique(dropna=False).gt(1).any(axis=1) if len(dup) else pd.Series(dtype=bool)
        out["result_conflicting_duplicates"] = int(conf.sum())
        st = raw["status"] if "status" in raw.columns else pd.Series("", index=raw.index)
        last = raw.drop_duplicates("fixture_id", keep="last")
        lst = last["status"] if "status" in last.columns else pd.Series("", index=last.index)
        out["aet_pen_fixtures"] = int(lst.isin(parse.EXTRA_TIME).sum())
        served = results(raw, ft90)
        b = served.get("goals_basis", pd.Series(dtype=object))
        out["aet_pen_corrected_90"] = int(((b == "fulltime_90_corrected") | ((b == "fulltime_90")
                                          & served["status"].isin(parse.EXTRA_TIME))).sum()) if len(served) else 0
        out["aet_pen_missing_90"] = int((b == "missing_90").sum()) if len(served) else 0
        names = pd.concat([raw.get("home_team", pd.Series(dtype=object)), raw.get("away_team", pd.Series(dtype=object))]).dropna().astype(str)
        out["names_with_whitespace"] = int(names[names != names.str.strip()].nunique())
        t = pd.concat([raw[["home_id", "home_team"]].set_axis(["id", "name"], axis=1),
                       raw[["away_id", "away_team"]].set_axis(["id", "name"], axis=1)]) \
            if {"home_id", "home_team", "away_id", "away_team"} <= set(raw.columns) else pd.DataFrame(columns=["id", "name"])
        out["team_ids_with_several_raw_names"] = int((t.dropna().groupby("id")["name"].nunique() > 1).sum())
        out["kickoff_zero_or_missing"] = int((pd.to_numeric(raw.get("kickoff_ts"), errors="coerce").fillna(0) <= 0).sum())
    o = odds if odds is not None else pd.DataFrame()
    out.update({f"odds_{k}": v for k, v in odds_duplicates(o).items()})
    m0 = first_freeze(mdl) if mdl is not None and len(mdl) else pd.DataFrame()
    if len(m0):
        out["model_fixtures"] = int(len(m0))
        out["model_duplicate_rows"] = int(len(mdl) - len(m0))
        out["model_unknown_team_or_degraded"] = int((~model_ok(m0)).sum())
    # missing results: priced or frozen fixtures past stated kickoff + grace
    stated = pd.Series(dtype=float)
    if len(o) and "kickoff_ts" in o.columns:
        stated = o.groupby("fixture_id")["kickoff_ts"].max().astype(float)
    if len(m0) and "kickoff_ts" in m0.columns:
        stated = stated.combine(m0.set_index("fixture_id")["kickoff_ts"].astype(float), max, fill_value=0)
    due = stated[stated + RESULT_GRACE_HOURS * 3600 < now.timestamp()]
    have = set(raw["fixture_id"]) if len(raw) else set()
    nores = set(due.index) - have
    reason = set()
    if status is not None and len(status):
        reason = set(status["fixture_id"])
    out["due_fixtures"] = int(len(due))
    out["due_without_result"] = len(nores)
    out["due_without_result_explained"] = len(nores & reason)
    out["due_without_result_unexplained"] = len(nores - reason)
    s = settled(raw, o, mdl, ft90) if len(raw) and len(o) else pd.DataFrame()
    exc = s.attrs.get("excluded", {}) if len(raw) and len(o) else {}
    out.update({f"settled_{k}" if not k.startswith("settled") else k: v for k, v in exc.items()})
    out["evidence_rows"] = int(s["p_model"].notna().sum()) if len(s) else 0
    out["evidence_duplicate_rows"] = int(s[s["p_model"].notna()].duplicated(["fixture_id", "market"]).sum()) if len(s) else 0
    return out
